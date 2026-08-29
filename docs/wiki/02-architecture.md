<!-- Architecture · updated 2026-08-27 · status: active -->

# Architecture

[← INDEX](INDEX.md)

NK is a **framework on top of FastAPI**: cookiecutter factory + profiles + contracts + `nk` CLI.

- Profiles expand into BuilderContext (`fastapi_template/profiles.py`)
- Feature deps validated before bake (`fastapi_template/validation.py`)
- Template prune via `conditional_files.toml`
- Generated apps expose `nk` (`doctor` / `validate` / `check` / `dev` / `build` / `generate`)
- Trust model: headers = input; `request.state` after auth/tenant = trust
- AI fakes live only in `tests/_fakes.py`; real adapters under `ai/providers/`

North-star design: `docs/plans/2026-08-24-nk-system-design.md`  
Capability phases: `.sisyphus/plans/gold-master-plan.md`
