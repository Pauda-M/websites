# ADR-0010: Cognitive Core

## Status

Accepted — 2026-07-13

## Context

Genesis Phase 7 (`docs/genesis/015_Roadmap.md`) requires the **Cognitive Core**: the
cognitive operating system every AI Employee consumes. The specification
(`003_Cognitive_Architecture.md`, `008_Memory_Engine.md`) calls for fifteen cooperating
subsystems — working / episodic / semantic / procedural memory, consolidation, memory
ranking, context and prompt builders, reflection, planning, goal management, the agent and
tool registries, the policy engine, and an event processor — all tenant-scoped, all
auditable, and all runnable on the existing PostgreSQL foundation.

Several forces shaped how this landed:

- The foundation already reserves module namespaces (ADR-0008) and mandates that every
  significant decision be attached to code (ADR-0009). The Cognitive Core is large enough
  to warrant its own placement and layering decision.
- `pb_api/core/` already exists and holds cross-cutting **infrastructure** (config,
  security, logging). "Cognitive core" is a product concept, not infrastructure, so the two
  meanings of "core" must not be conflated in the package tree.
- The specification names learned models (`MemoryRankNet`) and vector search (pgvector /
  bge embeddings) as targets, but `011_ML_Platform.md` and `004_Company_Brain.md` both
  sequence those behind the initial build. The core has to work end-to-end **before** any
  of that exists.
- Multi-tenancy and RLS are still a foundation delta (`000_Glossary.md` §13); the `User`
  model remains single-tenant-shaped until that delta lands.

## Decision

**Placement.** The Cognitive Core is a top-level bounded context at
`apps/api/src/pb_api/cognitive/`, deliberately **not** nested under `pb_api/core/`. It is
the platform's "core" in the product sense and is addressable at `/api/v1/cognitive`
(`pb_api.cognitive.api.cognitive_router`, mounted by `pb_api.api.router` under the
`/api/v1` prefix). Keeping it top-level preserves a clean module boundary: `pb_api/core/`
stays infrastructure, `pb_api/cognitive/` stays cognition.

**Layered internals.** The package is strictly layered, each layer depending only on the
one below:

- `domain/` — pure Pydantic models and value objects, persistence-agnostic (`MemoryItem`,
  `Goal`, `Policy`, `CognitiveEvent`, the `MemoryType` and A0-A5 `AuthorityLevel` enums,
  and dependency-free helpers `hash_embedding`, `cosine_similarity`, `estimate_tokens`).
- `db/models.py` — SQLAlchemy ORM rows on the shared platform `Base` (`pb_api.db.base`), so
  a single Alembic chain and one `metadata.create_all` cover them.
- `repositories/` — tenant-scoped async data access; every query is filtered by
  `tenant_id`.
- `services/` — the fifteen subsystems plus the `CognitiveCore` facade.
- `api/` — FastAPI routers, request schemas, and a per-request dependency.

**Single composition root.** `CognitiveCore` (`services/core.py`) is the only place wiring
happens: given one `AsyncSession` it constructs every repository and service and exposes
them as attributes (`core.episodic`, `core.policies`, `core.context_builder`, …). The API
layer and the tests both consume this facade, so there is exactly one assembly point.

**Event-sourced by default.** Every consequential operation records an immutable
`CognitiveEvent` through the `EventProcessor`, appended to the append-only `cog_event`
table. Event types follow the canonical `pb.<context>.<aggregate>.<past-verb>` pattern
(`005_Event_Model.md`, `000_Glossary.md` §9) as constants on `EventType`. The event store
is the audit and trace trail.

**Ranking is an interface with a heuristic default.** `MemoryRanker`
(`domain/ranking.py`) is a `Protocol`; the shipped implementation is
`HeuristicMemoryRanker` (`name = "heuristic-v1"`) — a deterministic weighted blend of
similarity, importance, strength, recency, and contextual match, each score carrying a
human-readable reason. There is **no ML**. A future `MemoryRankNet` replaces it behind the
same interface without touching callers.

**Embeddings are deterministic feature-hashing by default.** `hash_embedding` (the hashing
trick, blake2b-seeded, L2-normalised) is the default embeddings adapter, and
`cosine_similarity` the default similarity. This makes recall, dedup, and ranking work
end-to-end on the existing store. Embeddings and every list/dict field are stored as
portable `JSON` columns (non-native enums as `String`), so the same schema and the same
test suite run on both SQLite and PostgreSQL. pgvector / bge is the scale-up.

**Tenant isolation is by construction.** Every row carries `tenant_id` (on the abstract
`_Base`) and every repository query filters on it; cross-tenant reads are impossible in the
data-access layer. This holds even though the foundation `User` is still single-tenant
-shaped — the delta is recorded in `000_Glossary.md` §13 and enforced properly when
multi-tenancy / RLS lands.

## Alternatives Considered

- **Nest under `pb_api/core/`.** Rejected: `core/` is infrastructure. Co-locating a large
  product domain there overloads the word "core" and blurs the boundary the layering is
  meant to keep sharp.
- **A separate app or microservice.** Rejected for now: it would need its own deployment,
  auth, and migration chain for no current benefit. A bounded context inside the API keeps
  one session lifecycle, one Alembic chain, and one test harness; extraction stays possible
  later because the facade already isolates wiring.
- **Bake ranking logic directly into the recall/context code.** Rejected: it would hard-wire
  a heuristic that the roadmap explicitly plans to replace with a learned model, and make
  the swap invasive. The `MemoryRanker` interface is the seam.
- **Adopt a learned ranker / real embedding model now.** Rejected: premature. It adds a
  training pipeline, a model registry, and a serving dependency before the core is even
  exercised. The deterministic default is explainable and testable today.
- **Require pgvector (or an external embedding API) from day one.** Rejected: it would
  couple the core to a Postgres extension or a third-party service and break the
  SQLite-based test suite. JSON columns plus in-process cosine similarity keep the core
  portable and self-contained; the vector index is a later optimisation.

## Consequences

- The core runs end-to-end on the existing Postgres/SQLite foundation with no new
  infrastructure: recall, dedup, ranking, context building, and prompt assembly all work
  today.
- JSON-stored embeddings are **not** backed by a vector index, so similarity is computed in
  Python over candidate rows. This is fine at current scale but will not hold at large
  memory volumes until pgvector (or an external vector store) is adopted.
- The heuristic ranker is fully explainable (every score ships a reason string) but is
  **not learned** — it will not improve from feedback until `MemoryRankNet` replaces it.
- Consolidation (dedup / promote / archive / summarise) is implemented and idempotent, but
  runs only when invoked (via the service or `POST /api/v1/cognitive/memory/consolidate`).
  There is no background scheduler yet.
- The event store gives a complete, tenant-scoped audit trail, but events are currently
  persisted only — nothing is published to a platform `EventBus`, so cross-context
  reactions are not yet wired.
- Every write path carries an explicit `tenant_id` in the request body because tenant
  authentication is not yet in place; this is a deliberate, temporary shape that tightens
  when multi-tenancy lands.

## Future Considerations

- **`MemoryRankNet`** trained and served via `011_ML_Platform.md`, swapped in behind the
  `MemoryRanker` interface.
- **pgvector / bge embeddings** as a `VectorStore` adapter for indexed similarity at scale,
  replacing the JSON + in-process cosine default (`004_Company_Brain.md`).
- **A background scheduler** to run memory consolidation on a cadence rather than only on
  demand.
- **`EventBus` publication** from the `EventProcessor` so cognitive events drive
  cross-context projections and reactions (`005_Event_Model.md`), with no change to the
  processor's interface.
- **Tenant-authenticated requests** (dropping the explicit body `tenant_id`) and PostgreSQL
  RLS once the multi-tenancy foundation delta (`000_Glossary.md` §13) is implemented.
