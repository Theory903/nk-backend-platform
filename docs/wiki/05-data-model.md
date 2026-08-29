<!-- Data model · updated 2026-08-27 · status: active -->

# Data model

[← INDEX](INDEX.md)

- SQLAlchemy / Beanie adapters behind shared repository protocols when ORM enabled
- Outbox = durable DB → relay → broker
- Fintech pack: append-only ledger under `industry/fintech/`
- Tenancy: membership → TenantContext; RLS is defense-in-depth
