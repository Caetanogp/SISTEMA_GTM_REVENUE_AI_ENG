# ADR-0014: Knowledge admin API contract

- **Status:** accepted
- **Date:** 2026-09-30
- **Context spec:** SPEC-007

## Context

SPEC-007 requires tenant-scoped administrative access to knowledge versions, but the earlier
specification described capabilities without fixing the public HTTP contract. Implementing the
API without a shared contract would make URLs, response shapes, status codes, and idempotency
semantics product decisions inside an executor.

## Decision

Expose the following JSON endpoints under `/v1/knowledge`:

| Method | Path | Purpose | Idempotency-Key |
|---|---|---|---|
| POST | `/versions` | Create a draft document version | Required |
| GET | `/versions` | List tenant-owned version metadata | Not applicable |
| GET | `/versions/{version_id}` | Inspect one tenant-owned version | Not applicable |
| POST | `/versions/{version_id}/confirm` | Confirm and dispatch processing | Not applicable |
| POST | `/versions/{version_id}/retire` | Logically retire a version | Not applicable |
| POST | `/revisions/{revision_id}/activate` | Explicitly activate a historical revision | Required |

All endpoints require a bearer token and an administrator principal. The organization in the
token is the only tenant scope; client-supplied organization identifiers are not trusted. List
responses contain metadata only and never full document content. Detail responses may contain the
document content because the caller is an authorized administrator of that organization.

Create accepts the controlled document fields from `SubmitKnowledgeDocumentArgs` and returns the
version resource with `201 Created`; an idempotent replay returns the same resource with `200 OK`.
Confirmation and retirement return the version resource with `200 OK`; confirmation is accepted
only for a draft or replayable confirmed/processing version. Activation returns the revision
resource with `200 OK`; an idempotent replay returns the same revision.

Invalid input returns `400`, missing or invalid authentication returns `401`, insufficient role
returns `403`, a tenant-inaccessible resource returns `404`, an idempotency conflict or invalid
lifecycle transition returns `409`, and an accepted asynchronous dispatch failure returns `503`.
Validation errors use the existing FastAPI/Pydantic `422` response convention.

## Consequences

- API tests can assert a stable public contract without depending on implementation details.
- Tenant isolation is enforced from the authenticated principal through the application port.
- The API composition root maps application errors to HTTP responses; business rules remain in
  application/domain layers.
- Future breaking changes require a new API version or a new ADR rather than silent route drift.

## Rejected alternatives

- Accepting a client-supplied organization id would make cross-tenant access easier to introduce.
- Returning full content from list endpoints increases data exposure and violates the metadata-only
  list requirement.
- Using `POST /versions/{id}/activate` for both version publication and historical revision
  activation obscures the immutable revision contract.
