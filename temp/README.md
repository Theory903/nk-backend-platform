# Reference clones

Optional upstream references — patterns are implemented as **NK-native feature packs**, not copied code.

## awesome-llm-apps (LLM / agents)

```bash
git clone --depth 1 https://github.com/Shubhamsaboo/awesome-llm-apps.git temp/awesome-llm-apps
python3 scripts/build_llm_feature_catalog.py   # refresh catalog.yaml (102 templates)
python3 scripts/scaffold_llm_feature_packs.py  # regenerate pack modules if needed
```

### 13 LLM feature packs → 102 upstream templates

| Pack | Upstream category | NK module |
|------|-------------------|-----------|
| `chat_over_docs` | rag_tutorials, chat_with_X | `llm/features/chat_over_docs` |
| `agentic_rag` | agentic RAG tutorials | `llm/features/agentic_rag` |
| `deep_research` | research agents | `llm/features/deep_research` |
| `data_analyst` | CSV/Excel agents | `llm/features/data_analyst` |
| `starter_agents` | starter_ai_agents | `llm/features/starter_agents` |
| `advanced_agents` | advanced_ai_agents | `llm/features/advanced_agents` |
| `mcp_assistant` | mcp_ai_agents | `llm/features/mcp_assistant` + `agents/mcp_bridge` |
| `memory_chat` | memory tutorials | `llm/features/memory_chat` |
| `voice_multimodal` | voice_ai_agents | `llm/features/voice_multimodal` |
| `always_on` | always_on_agents | `llm/features/always_on` |
| `generative_ui` | generative_ui_agents | `llm/features/generative_ui` |
| `structured_agents` | SDK crash course | `llm/features/structured_agents` |
| `coding_skills` | agent_skills | `agents/skills/` |

```bash
uv run nk features list
uv run nk skills list
curl -X POST /api/llm/deep-research/research -d '{"input":"topic"}'
```

---

## erpnext (ERP domain)

```bash
git clone --depth 1 https://github.com/frappe/erpnext.git temp/erpnext
python3 scripts/build_erp_feature_catalog.py   # refresh catalog.yaml (536 doctypes + 170 reports)
python3 scripts/scaffold_erp_feature_packs.py    # regenerate pack modules if needed
```

Upstream: [frappe/erpnext](https://github.com/frappe/erpnext) (GPL-3.0). We port **business rules, calculations, mappers, and report logic** — not Frappe ORM, desk UI, or DocType JSON runtime.

### 13 ERP feature packs → 706 upstream artifacts

| Pack | ERPNext modules | NK module | Doctypes |
|------|-----------------|-----------|----------|
| `erp_masters` | Setup, Utilities, Portal | `erp/features/erp_masters` | 50 |
| `crm_pipeline` | CRM, Communication | `erp/features/crm_pipeline` | 39 |
| `pricing_taxes` | controllers (cross-cutting) | `erp/features/pricing_taxes` | 0 + patterns |
| `order_to_cash` | Selling | `erp/features/order_to_cash` | 21 |
| `procure_to_pay` | Buying, EDI | `erp/features/procure_to_pay` | 22 |
| `inventory_management` | Stock | `erp/features/inventory_management` | 81 |
| `financial_accounting` | Accounts | `erp/features/financial_accounting` | 192 |
| `billing_collections` | Accounts (AR/AP) | `erp/features/billing_collections` | cross-pack |
| `support_sla` | Support, Telephony | `erp/features/support_sla` | 18 |
| `projects_delivery` | Projects | `erp/features/projects_delivery` | 16 |
| `manufacturing_ops` | Manufacturing, Subcontracting | `erp/features/manufacturing_ops` | 64 |
| `assets_quality` | Assets, Quality, Maintenance | `erp/features/assets_quality` | 50 |
| `reporting_analytics` | Regional + all reports | `erp/features/reporting_analytics` | 170 reports |

```bash
uv run nk erp list
curl -X POST /api/erp/pricing/calculate-totals -d '{"items":[{"amount":100}]}'
```

Toggle packs in `platform.yaml` under `erp_features:`.

### First-party module layout (mirrors `agents/`)

```
erp/
├── bootstrap.py          # wire_erp_bootstrap → app.state.erp_runtime
├── runtime.py            # PricingService + valuation classes
├── patterns.py           # ERPNext upstream → NK port map
├── schemas/              # Pydantic (Lead, Issue, TransactionDocument, …)
├── services/             # pricing, valuation, masters, crm, support
└── features/             # 13 HTTP + agent tool packs (5 live)
db/models/erp_*           # SQLAlchemy (Item, Customer, Lead, Issue, …)
```

Default enabled (SQLAlchemy + DB): all 13 packs when users enabled; pricing/inventory/financial/assets/reports when DB-only.

### All 13 packs — NK-native (no 501 stubs)

| Pack | API prefix | NK service |
|------|------------|------------|
| `erp_masters` | `/api/erp/masters` | `MastersService` |
| `crm_pipeline` | `/api/erp/crm` | `CrmService` |
| `pricing_taxes` | `/api/erp/pricing` | `PricingService` |
| `order_to_cash` | `/api/erp/selling` | `DocumentService` (quotation, SO, DN) |
| `procure_to_pay` | `/api/erp/buying` | `DocumentService` (RFQ, PO, PR) |
| `inventory_management` | `/api/erp/stock` | `StockService` + FIFO/LIFO |
| `financial_accounting` | `/api/erp/accounts` | `LedgerService` |
| `billing_collections` | `/api/erp/billing` | `BillingService` |
| `support_sla` | `/api/erp/support` | `SupportService` |
| `projects_delivery` | `/api/erp/projects` | `ProjectsService` |
| `manufacturing_ops` | `/api/erp/manufacturing` | `ManufacturingService` |
| `assets_quality` | `/api/erp/assets` | `AssetsService` |
| `reporting_analytics` | `/api/erp/reports` | `ReportsService` (170+ report catalog) |

Migrations: `erp_core_20260901` (masters/CRM/support) + `erp_txn_20260901` (documents/GL/stock/projects/mfg/assets/billing).

### Highest-value portable patterns (copy targets)

| Pattern | Upstream file | Pack |
|---------|---------------|------|
| Tax/total engine | `controllers/taxes_and_totals.py` | `pricing_taxes` |
| FIFO/LIFO valuation | `stock/valuation.py` | `inventory_management` |
| GL posting | `accounts/general_ledger.py` | `financial_accounting` |
| Status workflows | `controllers/status_updater.py` | all transaction packs |
| Doc mappers (`make_*`) | `*/doctype/*/mapper.py` | CRM, selling, buying |
| SLA deadline calc | `support/doctype/service_level_agreement/` | `support_sla` |
| Report contract | `*/report/*/execute()` | `reporting_analytics` |

### Recommended build order

1. **`pricing_taxes`** — pure calculation, no ledger side effects (stub live at `/api/erp/pricing/calculate-totals`)
2. **`crm_pipeline`** — Lead/Opportunity + mappers, no GL dependency
3. **`support_sla`** — Issue lifecycle + SLA, small doctype surface
4. **`erp_masters`** — Item, Customer, Supplier SQLAlchemy models
5. **`inventory_management`** → **`order_to_cash`** / **`procure_to_pay`** → **`financial_accounting`**

### Not portable (rewrite required)

- `frappe.get_doc` / Document submit-cancel-amend lifecycle
- DocType JSON → SQLAlchemy + Pydantic schemas
- `frappe.model.mapper.get_mapped_doc` → explicit transform services
- `frappe.qb` → SQLAlchemy 2.0
- Desk JS, print formats, website portal routes
- Frappe role/profile permissions → FastAPI RBAC deps

Shared ERP logic lives in `erp/features/common/` (pricing facade first). Tools register via `agents/bootstrap.py` when agents + DB are enabled.

---

## AI platform OSS references

Clone all runtime/eval/architecture references:

```bash
./scripts/clone_ai_platform_refs.sh          # 26 repos → temp/oss/
python3 scripts/build_ai_platform_manifest.py # → platform/oss_manifest.yaml
```

**Categories:** runtime adapters · protocols · evaluators · **architecture references** (DeepSeek Harness) · **skills** (gstack) · **research** (Karpathy autoresearch) · minimal-model references (nanochat, nanoGPT, llm.c, …).

| Clone | Category | NK influence |
|-------|----------|--------------|
| `deepseek-harness` | architecture_reference | Plugin kernel, sessions, replay/fork (P21) |
| `gstack` | skill | Engineering SDLC skills (P22–P23) |
| `autoresearch` | research | Autonomous optimization loop (P26–P27) |
| `nanochat` | reference | `production-ai-local` profile |
| `langgraph` … `promptfoo` | runtime/eval | See [OSS map](../docs/wiki/references/ai-platform-oss-map.md) |

Master roadmap (replaces feature-pack-only plan): [docs/wiki/references/ai-platform-roadmap.md](../docs/wiki/references/ai-platform-roadmap.md)

```bash
fastapi-template --profile production-ai-local myapp   # no API keys
uv sync --extra ai-platform --extra ai-eval
```

