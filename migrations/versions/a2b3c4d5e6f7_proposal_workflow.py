"""typed evidence-grounded proposal workflow

Revision ID: a2b3c4d5e6f7
Revises: f3a1c7e9b420
Create Date: 2026-09-14
"""

import sqlalchemy as sa
from alembic import op

revision = "a2b3c4d5e6f7"
down_revision = "f3a1c7e9b420"
branch_labels = None
depends_on = None


def _stamped(columns: list[sa.Column]) -> list[sa.Column]:
    return columns + [
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "proposals",
        *_stamped([
            sa.Column("project_id", sa.String(length=32), nullable=False),
            sa.Column("title", sa.String(length=500), nullable=False),
            sa.Column("kind", sa.String(length=40), nullable=False),
            sa.Column("client_question", sa.Text(), nullable=False),
            sa.Column("audience", sa.Text(), nullable=False),
            sa.Column("aims", sa.Text(), nullable=False),
            sa.Column("success_criteria", sa.Text(), nullable=False),
            sa.Column("constraints", sa.Text(), nullable=False),
            sa.Column("known_resources", sa.Text(), nullable=False),
            sa.Column("unanswered_questions", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("outline_state", sa.String(length=30), nullable=False),
            sa.Column("draft_revision", sa.Integer(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
            sa.PrimaryKeyConstraint("id"),
        ]),
    )
    op.create_index("ix_proposals_project_id", "proposals", ["project_id"])
    op.create_index("ix_proposals_project_status", "proposals", ["project_id", "status"])
    op.create_table(
        "proposal_sources",
        *_stamped([
            sa.Column("proposal_id", sa.String(length=32), nullable=False),
            sa.Column("source_id", sa.String(length=32), nullable=False),
            sa.Column("collection", sa.String(length=20), nullable=False),
            sa.Column("imported_snapshot_checksum", sa.String(length=64), nullable=False),
            sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"]),
            sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("proposal_id", "source_id"),
        ]),
    )
    op.create_index("ix_proposal_sources_proposal_id", "proposal_sources", ["proposal_id"])
    op.create_index("ix_proposal_sources_source_id", "proposal_sources", ["source_id"])
    op.create_index("ix_proposal_source_collection", "proposal_sources", ["proposal_id", "collection"])
    op.create_table(
        "proposal_passages",
        *_stamped([
            sa.Column("proposal_id", sa.String(length=32), nullable=False),
            sa.Column("source_id", sa.String(length=32), nullable=False),
            sa.Column("source_checksum", sa.String(length=64), nullable=False),
            sa.Column("chunk_index", sa.Integer(), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("locator", sa.String(length=300), nullable=False),
            sa.Column("checksum", sa.String(length=64), nullable=False),
            sa.Column("extraction_confidence", sa.String(length=40), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("manual_correction", sa.Boolean(), nullable=False),
            sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"]),
            sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("proposal_id", "source_id", "source_checksum", "chunk_index"),
        ]),
    )
    op.create_index("ix_proposal_passages_proposal_id", "proposal_passages", ["proposal_id"])
    op.create_index("ix_proposal_passages_source_id", "proposal_passages", ["source_id"])
    op.create_index("ix_proposal_passage_lookup", "proposal_passages", ["proposal_id", "source_id", "status"])
    op.create_table(
        "proposal_fit_rows",
        *_stamped([
            sa.Column("proposal_id", sa.String(length=32), nullable=False),
            sa.Column("client_need", sa.Text(), nullable=False),
            sa.Column("relevant_method", sa.Text(), nullable=False),
            sa.Column("why_it_might_transfer", sa.Text(), nullable=False),
            sa.Column("assumptions", sa.Text(), nullable=False),
            sa.Column("limitations", sa.Text(), nullable=False),
            sa.Column("fit_status", sa.String(length=30), nullable=False),
            sa.Column("validation_step", sa.Text(), nullable=False),
            sa.Column("need_label", sa.String(length=30), nullable=False),
            sa.Column("method_label", sa.String(length=30), nullable=False),
            sa.Column("transfer_label", sa.String(length=30), nullable=False),
            sa.Column("validation_label", sa.String(length=30), nullable=False),
            sa.Column("state", sa.String(length=20), nullable=False),
            sa.Column("basis_hash", sa.String(length=64), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"]),
            sa.PrimaryKeyConstraint("id"),
        ]),
    )
    op.create_index("ix_proposal_fit_rows_proposal_id", "proposal_fit_rows", ["proposal_id"])
    op.create_index("ix_proposal_fit_row_proposal_state", "proposal_fit_rows", ["proposal_id", "state"])
    op.create_table(
        "proposal_fit_evidence",
        *_stamped([
            sa.Column("fit_row_id", sa.String(length=32), nullable=False),
            sa.Column("passage_id", sa.String(length=32), nullable=False),
            sa.Column("role", sa.String(length=30), nullable=False),
            sa.ForeignKeyConstraint(["fit_row_id"], ["proposal_fit_rows.id"]),
            sa.ForeignKeyConstraint(["passage_id"], ["proposal_passages.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("fit_row_id", "passage_id", "role"),
        ]),
    )
    op.create_index("ix_proposal_fit_evidence_fit_row_id", "proposal_fit_evidence", ["fit_row_id"])
    op.create_index("ix_proposal_fit_evidence_passage_id", "proposal_fit_evidence", ["passage_id"])
    op.create_table(
        "proposal_sections",
        *_stamped([
            sa.Column("proposal_id", sa.String(length=32), nullable=False),
            sa.Column("heading", sa.String(length=300), nullable=False),
            sa.Column("purpose", sa.Text(), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("state", sa.String(length=20), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("basis_hash", sa.String(length=64), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("proposal_id", "position"),
        ]),
    )
    op.create_index("ix_proposal_sections_proposal_id", "proposal_sections", ["proposal_id"])
    op.create_index("ix_proposal_section_proposal_state", "proposal_sections", ["proposal_id", "state"])
    op.create_table(
        "proposal_section_citations",
        *_stamped([
            sa.Column("section_id", sa.String(length=32), nullable=False),
            sa.Column("passage_id", sa.String(length=32), nullable=False),
            sa.ForeignKeyConstraint(["section_id"], ["proposal_sections.id"]),
            sa.ForeignKeyConstraint(["passage_id"], ["proposal_passages.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("section_id", "passage_id"),
        ]),
    )
    op.create_index("ix_proposal_section_citations_section_id", "proposal_section_citations", ["section_id"])
    op.create_index("ix_proposal_section_citations_passage_id", "proposal_section_citations", ["passage_id"])
    op.create_table(
        "proposal_section_revisions",
        *_stamped([
            sa.Column("section_id", sa.String(length=32), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("before_text", sa.Text(), nullable=False),
            sa.Column("after_text", sa.Text(), nullable=False),
            sa.Column("origin", sa.String(length=20), nullable=False),
            sa.Column("basis_hash", sa.String(length=64), nullable=False),
            sa.Column("undone_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["section_id"], ["proposal_sections.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("section_id", "revision"),
        ]),
    )
    op.create_index("ix_proposal_section_revisions_section_id", "proposal_section_revisions", ["section_id"])
    op.create_table(
        "proposal_versions",
        *_stamped([
            sa.Column("proposal_id", sa.String(length=32), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("state", sa.String(length=20), nullable=False),
            sa.Column("basis_hash", sa.String(length=64), nullable=False),
            sa.Column("snapshot", sa.JSON(), nullable=False),
            sa.Column("review_note", sa.Text(), nullable=False),
            sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("proposal_id", "version"),
            sa.UniqueConstraint("proposal_id", "name"),
        ]),
    )
    op.create_index("ix_proposal_versions_proposal_id", "proposal_versions", ["proposal_id"])
    op.create_table(
        "proposal_version_exports",
        *_stamped([
            sa.Column("version_id", sa.String(length=32), nullable=False),
            sa.Column("format", sa.String(length=20), nullable=False),
            sa.Column("artifact", sa.JSON(), nullable=False),
            sa.Column("sha256", sa.String(length=64), nullable=False),
            sa.ForeignKeyConstraint(["version_id"], ["proposal_versions.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("version_id", "format"),
        ]),
    )
    op.create_index("ix_proposal_version_exports_version_id", "proposal_version_exports", ["version_id"])
    op.create_table(
        "proposal_generations",
        *_stamped([
            sa.Column("proposal_id", sa.String(length=32), nullable=False),
            sa.Column("kind", sa.String(length=30), nullable=False),
            sa.Column("idempotency_key", sa.String(length=100), nullable=False),
            sa.Column("state", sa.String(length=20), nullable=False),
            sa.Column("context_hash", sa.String(length=64), nullable=False),
            sa.Column("result_hash", sa.String(length=64), nullable=False),
            sa.Column("model", sa.String(length=120), nullable=False),
            sa.Column("provider_request_id", sa.String(length=200), nullable=False),
            sa.Column("simulated", sa.Boolean(), nullable=False),
            sa.Column("error", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("proposal_id", "idempotency_key"),
        ]),
    )
    op.create_index("ix_proposal_generations_proposal_id", "proposal_generations", ["proposal_id"])


def downgrade() -> None:
    for table, indexes in [
        ("proposal_generations", ["ix_proposal_generations_proposal_id"]),
        ("proposal_version_exports", ["ix_proposal_version_exports_version_id"]),
        ("proposal_versions", ["ix_proposal_versions_proposal_id"]),
        ("proposal_section_revisions", ["ix_proposal_section_revisions_section_id"]),
        (
            "proposal_section_citations",
            ["ix_proposal_section_citations_section_id", "ix_proposal_section_citations_passage_id"],
        ),
        ("proposal_sections", ["ix_proposal_sections_proposal_id", "ix_proposal_section_proposal_state"]),
        (
            "proposal_fit_evidence",
            ["ix_proposal_fit_evidence_fit_row_id", "ix_proposal_fit_evidence_passage_id"],
        ),
        ("proposal_fit_rows", ["ix_proposal_fit_rows_proposal_id", "ix_proposal_fit_row_proposal_state"]),
        (
            "proposal_passages",
            [
                "ix_proposal_passages_proposal_id",
                "ix_proposal_passages_source_id",
                "ix_proposal_passage_lookup",
            ],
        ),
        (
            "proposal_sources",
            [
                "ix_proposal_sources_proposal_id",
                "ix_proposal_sources_source_id",
                "ix_proposal_source_collection",
            ],
        ),
        ("proposals", ["ix_proposals_project_id", "ix_proposals_project_status"]),
    ]:
        for index in indexes:
            op.drop_index(index, table_name=table)
        op.drop_table(table)
