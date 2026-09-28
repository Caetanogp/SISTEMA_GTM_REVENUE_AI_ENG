"""Add explicit knowledge corpora, immutable versions, chunks, and revisions.

Revision ID: c7d8e9f0a1b2
Revises: a1b2c3d4e5f6
Create Date: 2026-09-28 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "c7d8e9f0a1b2"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
    op.create_table(
        "knowledge_corpora",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "scope IN ('platform', 'organization')", name="ck_knowledge_corpora_scope"
        ),
        sa.CheckConstraint(
            "(scope = 'platform' AND organization_id IS NULL) OR "
            "(scope = 'organization' AND organization_id IS NOT NULL)",
            name="ck_knowledge_corpora_scope_owner",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", name="uq_knowledge_corpora_organization"),
    )
    op.create_index(
        "ix_knowledge_corpora_organization_id", "knowledge_corpora", ["organization_id"]
    )
    op.create_index(
        "uq_knowledge_corpora_platform",
        "knowledge_corpora",
        ["scope"],
        unique=True,
        postgresql_where=sa.text("scope = 'platform'"),
    )

    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("document_key", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["corpus_id"], ["knowledge_corpora.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("corpus_id", "document_key", name="uq_knowledge_documents_key"),
    )
    op.create_index("ix_knowledge_documents_corpus_id", "knowledge_documents", ["corpus_id"])

    op.create_table(
        "knowledge_document_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("content", sa.String(length=1_048_576), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("embedding_model", sa.String(length=128), nullable=True),
        sa.Column("embedding_dimension", sa.Integer(), nullable=True),
        sa.Column("failure_code", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["corpus_id"], ["knowledge_corpora.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"]),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "corpus_id", "idempotency_key", name="uq_knowledge_versions_corpus_idempotency"
        ),
        sa.UniqueConstraint("document_id", "id", name="uq_knowledge_versions_document_id"),
    )
    op.create_index(
        "ix_knowledge_document_versions_document_id",
        "knowledge_document_versions",
        ["document_id"],
    )
    op.create_index(
        "ix_knowledge_document_versions_corpus_id", "knowledge_document_versions", ["corpus_id"]
    )

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(length=3_000), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.ForeignKeyConstraint(["corpus_id"], ["knowledge_corpora.id"]),
        sa.ForeignKeyConstraint(["version_id"], ["knowledge_document_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_id", "ordinal", name="uq_knowledge_chunks_version_ordinal"),
    )
    op.create_index("ix_knowledge_chunks_corpus_id", "knowledge_chunks", ["corpus_id"])
    op.create_index("ix_knowledge_chunks_version_id", "knowledge_chunks", ["version_id"])
    op.create_index(
        "ix_knowledge_chunks_embedding_hnsw",
        "knowledge_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "knowledge_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("activated_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["activated_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["corpus_id"], ["knowledge_corpora.id"]),
        sa.ForeignKeyConstraint(["version_id"], ["knowledge_document_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("corpus_id", "manifest_hash", name="uq_knowledge_revisions_manifest"),
    )
    op.create_index("ix_knowledge_revisions_corpus_id", "knowledge_revisions", ["corpus_id"])
    op.create_index("ix_knowledge_revisions_version_id", "knowledge_revisions", ["version_id"])

    op.create_table(
        "knowledge_corpus_heads",
        sa.Column("corpus_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["corpus_id"], ["knowledge_corpora.id"]),
        sa.ForeignKeyConstraint(["revision_id"], ["knowledge_revisions.id"]),
        sa.PrimaryKeyConstraint("corpus_id"),
        sa.UniqueConstraint("revision_id"),
    )


def downgrade() -> None:
    op.drop_table("knowledge_corpus_heads")
    op.drop_index("ix_knowledge_revisions_version_id", table_name="knowledge_revisions")
    op.drop_index("ix_knowledge_revisions_corpus_id", table_name="knowledge_revisions")
    op.drop_table("knowledge_revisions")
    op.drop_index("ix_knowledge_chunks_embedding_hnsw", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_version_id", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_corpus_id", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_index(
        "ix_knowledge_document_versions_corpus_id", table_name="knowledge_document_versions"
    )
    op.drop_index(
        "ix_knowledge_document_versions_document_id", table_name="knowledge_document_versions"
    )
    op.drop_table("knowledge_document_versions")
    op.drop_index("ix_knowledge_documents_corpus_id", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
    op.drop_index("uq_knowledge_corpora_platform", table_name="knowledge_corpora")
    op.drop_index("ix_knowledge_corpora_organization_id", table_name="knowledge_corpora")
    op.drop_table("knowledge_corpora")
