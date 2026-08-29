# Epic 6 — FinTech Industry Pack — Scoping

**Status:** SCOPED | **Date:** 2026-08-27 | **Owner:** Sisyphus
**Dep:** Epic 2 (Data Hardening) complete | **Effort:** 18h (12h ledger + 6h compliance)

## Scope Decision

First industry pack *because* it forces correctness everywhere (append-only invariants,
integer money, idempotency, audit trail). Validates platform primitives under
real regulatory pressure.

**Out of scope for v1:**
- Real KYC/KYB provider integration (stub hook only)
- Real AML screening vendor (pluggable checker interface, `allow_all` stub)
- Multi-currency FX conversion
- Regulatory filing generation (only daily summary export)

## Architecture — Follows Platform Contract

```
industry/fintech/
  ledger/
    models.py      # Account, JournalEntry, LedgerLine — Pydantic + SQLAlchemy tables
    service.py     # post_transaction() atomic, balance, statement
  compliance/
    limits.py      # daily/monthly per-account/org checks
    kyc.py         # status flags + gating
    aml.py         # checker Protocol + stub
    audit.py       # links fintech ops → security events
  api/
    ledger_router.py
  tests/
```

**Provider abstractions (contracts not implementations):**
- `AmlChecker(Protocol): async def screen(...) -> ScreeningResult`
- `KycProvider(Protocol)` — stub returns `verified`

**Optional extra:** `fintech` — not installed for minimal/saas. Conditional via `conditional_files.toml` + `cookiecutter.json` `enable_fintech="False"` default, `agentic+fintech` profile enables.

**Money:** `amount_minor: int` (cents/paise) — never float. `currency: str` (ISO 4217). Overflow check against `2**63-1`.

## Task 6.1 — Double-Entry Ledger (12h)

| Subtask | File | Done |
|---|---|---|
| 6.1a | `industry/fintech/ledger/models.py` | Account(type enum), JournalEntry(immutable), LedgerLine(entry_id, account_id, amount_minor, direction) + Alembic migration with CHECK debits==credits deferred + immutable trigger |
| 6.1b | `industry/fintech/ledger/service.py` | `post_transaction(lines, external_ref, idempotency_key)` → validates balanced, atomic INSERT, uses `IdempotencyStore` for duplicate guard |
| 6.1c | integer money | enforced at Pydantic field validator `ge=0` |
| 6.1d | idempotent posting | external_reference UNIQUE constraint + service guard |
| 6.1e | maker-checker | threshold `FINTECH_MAKER_CHECKER_THRESHOLD_MINOR` → status `pending_approval`, separate approve endpoint |

**AC verifiable:**
```
uv run pytest tests/test_fintech_ledger.py -k "unbalanced|atomic|balance|idempotency|immutable|overflow"
```

## Task 6.2 — Limits + Compliance (6h)

| Subtask | File | Done |
|---|---|---|
| 6.2a | `industry/fintech/compliance/limits.py` | per-account/org daily/monthly counters (Redis CounterStore) |
| 6.2b | `kyc.py` | `KycStatus` enum gating `post_transaction` above `KYC_THRESHOLD_MINOR` |
| 6.2c | `aml.py` | `AmlChecker` Protocol + `AllowAllAmlChecker` stub |
| 6.2d | `reporting.py` | daily summary export `SELECT date, sum(amount_minor) GROUP BY date` |
| 6.2e | audit trail | every `post_transaction` emits `SecurityEvent(type="fintech.post")` + `JournalEntry` → `security_events` FK |

**AC verifiable:**
```
uv run pytest tests/test_fintech_compliance.py -k "limit|kyc|aml|summary|audit"
```

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Double-entry invariant violated by race | `SERIALIZABLE` isolation + advisor lock `pg_advisory_xact_lock(org_id)` |
| Float money introduced by contributor | Pydantic validator rejects float, CI grep `amount.*float` |
| Maker-checker bypass | service layer guard + RLS policy on `journal_entries.status` |
| Scope creep into real KYC vendor | explicit stub only, interface documented |

## Verification Plan

1. `uv run ruff check industry/fintech` — 0
2. `uv run mypy industry/fintech --strict` — 0 (add to existing 146-file clean)
3. `uv run pytest tests/test_fintech_*.py` — all AC green
4. Profile: `enable_fintech=False` prunes `industry/` entirely (conditional_files.toml)

## Next Action

Implement Task 6.1a→6.1e in one PR, then 6.2. Keep modular-monolith, no new infra.
