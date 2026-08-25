# tests

| Directory | Scope | Needs docker |
|---|---|---|
| `unit/` | domain and application, with fakes for every port. Fast, no I/O | no |
| `integration/` | adapters against real Postgres and Redis, and the API end to end | yes |
| `adversarial/` | prompt injection, policy bypass, tool misuse, PII leakage | no |
| `architecture/` | Clean Architecture layer contracts (import-linter) | no |

Rules: the domain is tested without mocks (it is pure) · ports are faked, never patched by
monkeypatching internals · every tool gets a unit test and an eval case · every fixed bug gets a
regression test first.
