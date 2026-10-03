"""Project-scoped research task HTTP surface; registered with existing auth helpers."""

from typing import Annotated, Literal

from fastapi import Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .ingest.files import IngestError
from .models import ResearchTask
from .providers.research_embeddings import SemanticUnavailable
from .providers.research_executor import ExecutorError, availability
from .research_contract import TaskBrief
from .services import research, research_runner, research_tasks


class StartIn(BaseModel):
    acknowledge_live_execution: bool = False


class RetrievalIn(BaseModel):
    query: str = Field(min_length=1, max_length=24000)
    topics: list[str] = Field(default_factory=list, max_length=12)
    mode: Literal["lexical", "hybrid"] = "lexical"
    recall: Literal["focused", "broad"] = "focused"


class FindingIn(BaseModel):
    agent_id: str = Field(min_length=1, max_length=64)
    finding_id: str = Field(min_length=1, max_length=64)
    purpose: Literal["finding", "proof", "novelty", "manuscript"] = "finding"
    expected_hash: str = Field(min_length=64, max_length=64)


class ReviewIn(FindingIn):
    decision: Literal["approved", "rejected"]
    note: str = Field(min_length=1, max_length=24000)


class PromoteIn(FindingIn):
    manuscript_id: str | None = None


def install(app, session_dependency, principal_dependency, require, bounded_upload, download_response):
    @app.post("/projects/{project_id}/research-retrieval")
    def retrieve_evidence(
        project_id: str, body: RetrievalIn,
        session: Session = Depends(session_dependency), user=Depends(principal_dependency),
    ):
        from .services.research_retrieval import retrieve

        require(session, project_id, user, "reviewer")
        if not body.query.strip() or any(not t.strip() or len(t) > 300 for t in body.topics):
            raise HTTPException(422, "Supply a query and topic labels of 1–300 characters")
        return retrieve(session, project_id, body.query, body.topics, mode=body.mode, recall=body.recall)

    @app.post("/projects/{project_id}/research-retrieval/index")
    def index_evidence(
        project_id: str, session: Session = Depends(session_dependency), user=Depends(principal_dependency),
    ):
        from .services.research_semantic import index_project

        require(session, project_id, user, "coauthor")
        result = index_project(session, project_id)
        session.commit()
        return result

    @app.exception_handler(research_tasks.TaskError)
    @app.exception_handler(SemanticUnavailable)
    @app.exception_handler(ExecutorError)
    async def task_error(_request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=422, content={"detail": str(exc)})

    def scoped(session, project_id, task_id, user, role="reviewer"):
        require(session, project_id, user, role)
        return research_tasks.task_for(session, project_id, task_id)

    @app.get("/projects/{project_id}/research-executors")
    def executors(
        project_id: str, session: Session = Depends(session_dependency), user=Depends(principal_dependency)
    ):
        require(session, project_id, user, "reviewer")
        research._project(session, project_id)
        return availability()

    @app.get("/projects/{project_id}/research-tasks")
    def list_tasks(
        project_id: str, session: Session = Depends(session_dependency), user=Depends(principal_dependency)
    ):
        require(session, project_id, user, "reviewer")
        research._project(session, project_id)
        rows = session.scalars(
            select(ResearchTask)
            .where(
                ResearchTask.project_id == project_id,
                ResearchTask.deleted_at.is_(None),
            )
            .order_by(ResearchTask.created_at.desc())
            .limit(100)
        )
        return [
            {
                "id": t.id,
                "question": t.contract["question"],
                "state": t.state,
                "executor": t.contract["executor"],
                "task_type": t.contract["task_type"],
            }
            for t in rows
        ]

    @app.post("/projects/{project_id}/research-tasks")
    def create(
        project_id: str,
        body: TaskBrief,
        session: Session = Depends(session_dependency),
        user=Depends(principal_dependency),
    ):
        require(session, project_id, user, "coauthor")
        task = research_tasks.create_task(session, project_id, body)
        session.commit()
        return research_tasks.snapshot(session, task)

    @app.get("/projects/{project_id}/research-tasks/{task_id}")
    def detail(
        project_id: str,
        task_id: str,
        session: Session = Depends(session_dependency),
        user=Depends(principal_dependency),
    ):
        task = scoped(session, project_id, task_id, user)
        research_runner.recover_expired(session, task)
        return research_tasks.snapshot(session, task)

    @app.post("/projects/{project_id}/research-tasks/{task_id}/attachments")
    async def attach(
        project_id: str,
        task_id: str,
        file: Annotated[UploadFile, File()],
        version: Annotated[str, Form()] = "unspecified",
        session: Session = Depends(session_dependency),
        user=Depends(principal_dependency),
    ):
        task = scoped(session, project_id, task_id, user, "coauthor")
        payload = await bounded_upload(file)
        try:
            research_tasks.attach(session, task, file.filename or "", payload, version=version)
        except IngestError as exc:
            raise HTTPException(422, str(exc)) from exc
        session.commit()
        return research_tasks.snapshot(session, task)

    @app.post("/projects/{project_id}/research-tasks/{task_id}/start", status_code=202)
    def start(
        project_id: str,
        task_id: str,
        body: StartIn,
        session: Session = Depends(session_dependency),
        user=Depends(principal_dependency),
    ):
        task = scoped(session, project_id, task_id, user, "coauthor")
        return research_runner.start(session, task, **body.model_dump())

    @app.post("/projects/{project_id}/research-tasks/{task_id}/cancel")
    def cancel(
        project_id: str,
        task_id: str,
        session: Session = Depends(session_dependency),
        user=Depends(principal_dependency),
    ):
        task = scoped(session, project_id, task_id, user, "coauthor")
        research_runner.cancel(session, task)
        return {"id": task.id, "state": task.state, "cancel_requested": task.cancel_requested}

    @app.get("/projects/{project_id}/research-tasks/{task_id}/download")
    def download(
        project_id: str,
        task_id: str,
        session: Session = Depends(session_dependency),
        user=Depends(principal_dependency),
    ):
        task = scoped(session, project_id, task_id, user)
        research_runner.recover_expired(session, task)
        payload = research_tasks.package(session, task)
        return download_response(payload, f"research-task-{task.id}.zip", "application/zip")

    @app.get("/projects/{project_id}/research-tasks/{task_id}/results.pdf")
    def results_pdf(
        project_id: str,
        task_id: str,
        session: Session = Depends(session_dependency),
        user=Depends(principal_dependency),
    ):
        from .services.research_results import render_results

        task = scoped(session, project_id, task_id, user)
        research_runner.recover_expired(session, task)
        result = render_results(research_tasks.snapshot(session, task))
        return download_response(result.data, f"research-results-{task.id}.pdf", "application/pdf")

    @app.get("/projects/{project_id}/manuscript-path")
    def manuscript_path(
        project_id: str,
        manuscript_id: str | None = None,
        session: Session = Depends(session_dependency),
        user=Depends(principal_dependency),
    ):
        from .services.manuscript_path import build_project_path

        require(session, project_id, user, "reviewer")
        return build_project_path(session, project_id, manuscript_id=manuscript_id)

    @app.get("/projects/{project_id}/manuscript-path/download")
    def manuscript_path_download(
        project_id: str,
        manuscript_id: str | None = None,
        session: Session = Depends(session_dependency),
        user=Depends(principal_dependency),
    ):
        from .services.manuscript_path import build_project_path, markdown

        require(session, project_id, user, "reviewer")
        payload = markdown(build_project_path(session, project_id, manuscript_id=manuscript_id)).encode()
        return download_response(payload, "path-to-manuscript.md", "text/markdown")

    @app.get("/projects/{project_id}/research-artifacts/download")
    def research_artifact_download(
        project_id: str,
        session: Session = Depends(session_dependency),
        user=Depends(principal_dependency),
    ):
        from .services.research_artifact_package import project_bundle

        require(session, project_id, user, "reviewer")
        payload = project_bundle(session, project_id)
        return download_response(payload, "research-artifacts.zip", "application/zip")

    @app.post("/projects/{project_id}/research-tasks/{task_id}/reviews")
    def review(
        project_id: str,
        task_id: str,
        body: ReviewIn,
        session: Session = Depends(session_dependency),
        user=Depends(principal_dependency),
    ):
        task = scoped(session, project_id, task_id, user, "coauthor")
        result = research_tasks.review_finding(
            session, task, **body.model_dump(), reviewer=getattr(user, "id", None) or "local_user"
        )
        session.commit()
        return result

    @app.post("/projects/{project_id}/research-tasks/{task_id}/promote")
    def promote(
        project_id: str,
        task_id: str,
        body: PromoteIn,
        session: Session = Depends(session_dependency),
        user=Depends(principal_dependency),
    ):
        task = scoped(session, project_id, task_id, user, "coauthor")
        result = research_tasks.promote(session, task, **body.model_dump())
        session.commit()
        return result
