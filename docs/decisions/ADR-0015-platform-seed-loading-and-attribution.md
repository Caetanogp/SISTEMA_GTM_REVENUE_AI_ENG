# ADR-0015: Platform seed loading and attribution

## Status

Accepted

## Context

SPEC-007 needs a deployment-controlled way to load trusted shared knowledge without exposing
platform mutation through tenant-facing API routes. The seed must be reviewable, deterministic,
replay-safe, and attributable to the deployment rather than to a synthetic tenant user.

The repository uses setuptools package discovery but does not currently declare external package
data. Changing `pyproject.toml` only to package seed files would expand the autonomous authorization
surface without adding product value or a dependency.

## Decision

Use a one-shot `apps.platform_seed` composition root and a package-local seed source implemented as
immutable Python constants under `packages/core/revops/infrastructure/knowledge_seed/`. The source
contains the canonical manifest and UTF-8 content as reviewed, versioned data. It uses only the
standard library and the existing domain/application validation contracts; it does not read paths,
URLs, environment-selected files, or operator-provided content.

The loader will:

- validate the manifest, content hashes, positive revisions, and stable document keys;
- use a deployment-owned actor and a platform corpus, never a sentinel organization;
- reuse the existing application use case, repository, unit-of-work, and Celery dispatch ports;
- derive corpus-scoped idempotency from document key and revision;
- reuse an unchanged version, reject changed content under the same revision, and require a
  revision bump for a new immutable version;
- commit staged versions before dispatching processing;
- never implicitly retire or delete entries removed from the manifest; and
- remain unreachable from tenant-facing FastAPI mutation routes.

No `pyproject.toml` change is required or authorized by this ADR. The source module is part of the
existing package discovery rules in both the checkout and the built distribution.

## Consequences

The seed is intentionally small and code-reviewed. Adding or changing platform knowledge requires a
normal source change and review, which is preferable to an unvalidated runtime file path. The
deployment command remains deterministic and does not require a new package, service, credential, or
network call. Large or operator-supplied content belongs to the tenant ingestion API and is outside
this platform-seed contract.

## Rejected alternatives

- Adding package-data configuration to `pyproject.toml` for this bounded seed: unnecessary build
  surface for a small trusted source and outside the autonomous authorization.
- Loading a filesystem path or URL: permits deployment-time content substitution and bypasses the
  code-review trust boundary.
- Using a sentinel organization: corrupts tenant ownership semantics and risks cross-tenant access.
