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

## Approved initial manifest

The initial platform seed is deliberately small and uses only content explicitly approved from the
project guide PDF. The PDF SHA-256 is
`8C294C58019722357B98BEF75B2E3CA7B52D3BE21891FF9D9F7C7D0B4D86E42A`.

| document_key | category | language | format | revision | content SHA-256 | source pages |
|---|---|---|---|---:|---|---|
| `product/platform-overview` | `product` | `pt` | `md` | 1 | `977acb4287acdc9dcebc2ece8adc496ebc727fa3b51be9a00deafea9b7f82fdb` | 3-4 |
| `outreach-policy/human-approval` | `outreach_policy` | `pt` | `md` | 1 | `f78b698f0a76762624cd553988605493d38864f82eb6e9fa42336cb725d44bea` | 9-11 |

The canonical normalized content is:

### `product/platform-overview`

```markdown
# Visão da plataforma

A plataforma Agentic GTM / Revenue Operations lê o estado comercial,
recupera contexto, pesquisa contas, prioriza leads, recomenda ações,
gera follow-ups, solicita aprovação humana quando necessário,
executa ferramentas reais e registra tudo em um audit trail observável
e avaliável.

O produto não deve ser um CRM genérico. O foco é demonstrar AI Engineering
aplicado à priorização de contas, pesquisa, scoring, personalização,
follow-up, execução segura de ações e atribuição de resultado em GTM/RevOps.
```

### `outreach-policy/human-approval`

```markdown
# Política de aprovação humana

Envio de e-mail, ações em massa, agendamento de reuniões e alterações
sensíveis exigem aprovação humana no MVP.

A interface de aprovação deve mostrar a ação proposta, destinatário,
payload, motivo, risco e evidências. O usuário pode aprovar, editar ou
rejeitar a ação. Após a decisão, o fluxo deve retomar a partir do checkpoint.

Conteúdo recuperado por RAG ou obtido da web é dado não confiável e nunca
pode alterar a política do sistema.
```

## Approved implementation and compatibility contract (2026-10-03)

The user approved the following implementation details and the conditional downgrade policy before
the Item 9 pilot. These resolve the previous architecture review; they do not authorize new seed
content or a tenant-facing platform mutation route.

### Canonical provenance

Keep the approved normalized texts and hashes above byte-for-byte after normalization. Both entries
have `scope=platform`, revision 1, and the following scalar metadata:

- `source`: `docs/Agentic_GTM_Revenue_Operations_Platform_Guia_Projeto.pdf`;
- `source_pdf_sha256`: the uppercase PDF hash recorded above;
- `approval_status`: `approved`;
- `source_pages`: `3-4` for product, `9-11` for outreach policy; and
- `title`: `Visão da plataforma` for product, `Aprovação humana para outreach` for outreach policy.

The Portuguese metadata and content are approved product data; implementation documentation and
code remain English. The loader is not a PDF parser and does not interpret this content as policy
instructions.

### Actor and ownership representation

Use the fixed deployment actor UUID `928f8683-f542-550e-a13c-8e770ef19a57`, derived from
`uuid5(NAMESPACE_URL, "revops:platform-seed:actor:v1")`. It has no tenant or user row.

Retain `requested_by` on versions and `activated_by` on revisions/activations as nullable user-FK
columns. Add nullable UUID columns `requested_by_system` and `activated_by_system`, respectively.
Versions store nullable `seed_revision`. Add `scope` to revisions/activations and derived
`organization_id` integrity projections to all three tables; versions already have `scope`.
Corpus identity, not these projections, remains the application authorization boundary.

Enforce the following in SQL, not only in repository code:

| Corpus scope | User actor | System actor | Version seed revision |
|---|---|---|---|
| organization | non-null, owned by the corpus organization | null | null |
| platform | null | non-null, exactly the fixed deployment UUID | positive integer |

Use explicit null checks so SQL CHECK's unknown result cannot bypass actor validation. Add parent
unique keys for users `(id, organization_id)` and corpora `(id, scope)` and `(id, organization_id)`.
Each actor-bearing table has composite FKs `(corpus_id, scope)`, `(corpus_id, organization_id)`, and
`(user_actor, organization_id)` to those parents. Checks require a non-null organization projection
for organization rows and a null projection for platform rows. Retain existing single-column user
FKs. Versions have unique `(document_id, seed_revision)`; tenant null revisions do not collide.

Add parent `(corpus_id, id)` unique keys and matching composite FKs for version -> document,
revision -> version, and activation -> revision/target version. Reject cross-corpus references.
Index new referencing/filter columns. Backfill projections from the corpus and validate existing
actor ownership before enabling constraints. Do not silently repair inconsistent historical data.

A BEFORE INSERT compatibility trigger derives omitted scope/organization projections from the
corpus so previous tenant writers remain compatible. Never overwrite an explicitly conflicting
projection. Immutable version identity/content/actor/seed-revision fields cannot be updated;
revision and activation rows cannot be updated or deleted. Lifecycle/provenance fields needed by
the existing worker remain mutable. Repositories preserve the effective UUID in application DTOs
and carry the platform actor through worker publication without reattribution.

### Concurrency and recovery

Serialize seed loaders with an advisory transaction lock. All platform operations that lock a
version first lock the platform corpus, then the version. Keep transaction boundaries around
reservation and publication; external calls occur after releasing database locks.

The user selected waiting for the current revision rather than parallel revision processing. A
higher revision is rejected while the latest version is draft/confirmed/processing. Equal-payload
replay may confirm/redispatch that revision; ready is a no-op, while failed/retired requires a bump.
This prevents a late older processing job from replacing a newer seed publication.

Commit the complete seed reservation/confirmation transaction before publishing jobs. Stop on a
dispatch failure with a safe code. Replay safely redispatches pending versions after partial broker
success; previously completed versions and identifiers are retained.

### Migration and deployment order

This is an additive, data-preserving upgrade with a user-approved restriction on downgrade. It is
not unconditionally reversible after seeding. Before any downgrade DDL, take transaction-level
table locks that prevent concurrent seed writes and check all three actor-bearing tables. Any
platform version/seed revision or system attribution raises `platform_seed_downgrade_blocked`.
The failed downgrade leaves schema, data, and Alembic version unchanged, including draft seeds.
Before any seed exists, downgrade restores the previous schema while retaining all tenant data.

Deploy in this order: additive migration, replace/drain all old workers, deploy compatible API and
worker code, then run the one-shot seed command. Old tenant writers are supported by the projection
trigger; old workers must never consume platform jobs. After seeding, recover with compatible code
or fix forward. Do not delete audit history, fabricate tenant authors, or purge jobs to downgrade.

Validate the migration and concurrency in isolated owned test schemas. Preserve shared integration
data so existing migration round-trip tests still exercise their original contract. The CLI uses
existing broker/database aliases and a sanitized exit path, including errors from libraries.

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
