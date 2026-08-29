<!-- Conventions · updated 2026-08-27 · status: active -->

# Conventions

[← INDEX](INDEX.md)

- Python 3.12+, `uv` for installs
- Ruff format ≠ lint (`ruff format` then `ruff check`, no `ruff check --fix`)
- Tests: pytest-asyncio strict; external brokers skip when ports closed
- Prefer Protocols + adapters over hard-wired vendors
- Do not import `tests/_fakes` from application code
