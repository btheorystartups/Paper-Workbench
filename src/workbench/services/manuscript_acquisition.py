"""Explicit bounded acquisition and actual execution receipts for production review."""

import json
import time
from copy import deepcopy
from pathlib import Path

from .. import storage
from ..models import ComputeRun, SavedSearch, stable_hash, utcnow
from ..providers.scholarly import CrossrefAdapter, OpenAlexAdapter
from . import compute, literature, manuscript_verification, research_trace


def collect(runner, manuscript, campaign):
    session, task = runner.session, runner.task
    searches, checks, artifacts, imported_ids = [], [], [], []

    def persist():
        artifacts.clear()
        for receipt in [*searches, *checks]:
            artifacts.append(
                storage.store_content(
                    json.dumps(receipt, sort_keys=True).encode(),
                    filename=receipt["id"] + ".json",
                    namespace="research/quality-receipts",
                )
            )
        manuscript.body = {
            **manuscript.body,
            "quality_evidence": deepcopy(artifacts),
            "quality_verifier_artifacts": [r["reproduction"]["implementation_artifact"]
                for r in checks if r.get("reproduction")],
            "compute_run_ids": task.contract.get("compute_run_ids", []),
            "source_ids": sorted(set(manuscript.body["source_ids"]) | set(imported_ids)),
        }
        campaign.body = {
            **campaign.body,
            "search_receipts": deepcopy(searches),
            "verification_receipts": deepcopy(checks),
        }
        session.commit()

    for query in task.contract.get("literature_queries", []):
        runner.check()
        if not task.contract.get("allow_public_search"):
            raise ValueError("public searches were not authorized")
        span = research_trace.record(
            runner, "search_started", provider=query["provider"], query_sha256=stable_hash(query)
        )
        receipt = {
            "id": "search-" + str(len(searches) + 1),
            **query,
            "started_at": utcnow().isoformat(),
            "results": [],
            "status": "not_run",
        }
        if task.contract["executor"] == "offline":
            receipt["status"] = "simulated"
        else:
            adapter = {"crossref": CrossrefAdapter, "openalex": OpenAlexAdapter}[query["provider"]](
                timeout=max(0.1, min(15, runner.research_deadline - time.monotonic()))
            )
            try:
                works = adapter.search(query["query"], count=query["count"])
                receipt["status"] = "failed" if adapter.last_error else "completed"
                receipt["error_class"] = adapter.last_error
                saved = SavedSearch(
                    project_id=task.project_id,
                    provider=query["provider"],
                    query=query["query"],
                    filters={"count": query["count"], "quality_task_id": task.id},
                    last_run_at=utcnow(),
                    last_result_count=len(works),
                )
                session.add(saved)
                session.flush()
                receipt["saved_search_id"] = saved.id
                for work in works:
                    source, _ = literature.import_work(session, task.project_id, work)
                    imported_ids.append(source.id)
                    receipt["results"].append(
                        {
                            "source_id": source.id,
                            "title": work.title,
                            "authors": work.authors,
                            "year": work.year,
                            "doi": work.doi,
                            "url": work.url,
                            "access": str(source.access),
                            "provider_id": work.provider_id,
                        }
                    )
            except (ValueError, TypeError, KeyError, OSError) as exc:
                receipt["status"] = "failed"
                receipt["error_class"] = type(exc).__name__
            finally:
                if adapter._session is not None:
                    adapter._session.close()
        receipt.update(
            finished_at=utcnow().isoformat(),
            coverage="Bounded query, ranked result cap; no complete-literature claim.",
        )
        receipt["receipt_sha256"] = stable_hash(receipt)
        searches.append(receipt)
        persist()
        research_trace.record(
            runner,
            "search_finished",
            span_id=span,
            status=receipt["status"],
            result_count=len(receipt["results"]),
        )
    for name in task.contract.get("verification_routines", []):
        runner.check()
        span = research_trace.record(runner, "verification_started", routine=name)
        checks.append(
            manuscript_verification.execute_routine(
                name, deadline=runner.research_deadline, cancel=runner.cancel_event
            )
        )
        # Freeze trusted application code alongside the actual execution receipt.
        # It is inspectable evidence, never an attachment execution path.
        source = Path(manuscript_verification.__file__).read_bytes()
        implementation = storage.store_content(
            source, filename="manuscript_verification.py", namespace="research/quality-verifiers"
        )
        expected = manuscript_verification.deterministic_result(checks[-1])
        checks[-1]["reproduction"] = {
            "implementation_artifact": implementation,
            "implementation_text": source.decode("utf-8"),
            "dependencies": "Python >= 3.11 standard library only",
            "invocation": "python -m workbench.services.manuscript_verification --expected-sha256 "
            + checks[-1]["implementation_sha256"],
            "expected_output": expected,
            "execution_policy": "Run the reviewed installed module only; never execute manuscript "
            "attachments.",
        }
        checks[-1]["receipt_sha256"] = stable_hash(
            {k: v for k, v in checks[-1].items() if k != "receipt_sha256"}
        )
        persist()
        research_trace.record(
            runner, "verification_finished", span_id=span, receipt_sha256=checks[-1]["receipt_sha256"]
        )
    for identifier in task.contract.get("compute_run_ids", []):
        run = session.get(ComputeRun, identifier)
        if not run or run.project_id != task.project_id or run.deleted_at:
            raise ValueError("compute receipt belongs to another project or is unavailable")
        record = compute.run_out(session, run)
        compute._verify_output_artifacts(run)
        checks.append(
            {
                "id": run.id,
                "compute_run_id": run.id,
                "manifest": record,
                "outcome": "passed_within_scope"
                if (
                    run.state == "succeeded"
                    and run.review_state == "verified"
                    and run.review_note
                    and record["plan_status"].get("stale") is False
                )
                else "not_run",
                "receipt_sha256": stable_hash(record),
            }
        )
    persist()
