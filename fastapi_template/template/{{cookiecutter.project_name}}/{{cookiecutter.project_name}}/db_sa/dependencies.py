from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

{%- if cookiecutter.add_users in [True, "True", "true", 1, "1"] and cookiecutter.db_info.name == "postgresql" %}
from {{cookiecutter.project_name}}.core.errors import Problem
from {{cookiecutter.project_name}}.data.rls import set_tenant_context
from {{cookiecutter.project_name}}.platform.tenancy import (
    get_tenant_authorization,
)
{%- endif %}
{%- if cookiecutter.enable_taskiq in [True, "True", "true", 1, "1"] %}
from taskiq import TaskiqDepends

{%- endif %}


async def get_db_session(request: Request {%- if cookiecutter.enable_taskiq in [True, "True", "true", 1, "1"] %} = TaskiqDepends(){%- endif %}) -> AsyncGenerator[AsyncSession, None]:
    """
    Create and get database session.

    :param request: current request.
    :yield: database session.
    """
    session: AsyncSession = request.app.state.db_session_factory()

    try:
        {%- if cookiecutter.add_users in [True, "True", "true", 1, "1"] and cookiecutter.db_info.name == "postgresql" %}
        principal = getattr(request.state, "principal", None)
        requested_org_id = request.headers.get("X-Org-Id")
        principal_org_id = getattr(principal, "org_id", None)
        if requested_org_id:
            requested_org_id = requested_org_id.strip()
            if not requested_org_id:
                raise Problem(
                    title="Organization Required",
                    status_code=400,
                    detail="X-Org-Id cannot be empty",
                )
            if principal is None or getattr(principal, "is_anonymous", True):
                raise Problem(
                    title="Not Authenticated",
                    status_code=401,
                    detail="authentication required for tenant selection",
                )
        elif principal_org_id:
            requested_org_id = principal_org_id

        if requested_org_id:
            if principal is None or getattr(principal, "is_anonymous", True):
                raise Problem(
                    title="Not Authenticated",
                    status_code=401,
                    detail="authentication required for tenant access",
                )
            context = await get_tenant_authorization().resolve_context(
                principal,
                org_id=requested_org_id,
            )
            requested_org_id = context.org_id
            await set_tenant_context(session, requested_org_id)
        {%- endif %}
        yield session
    except BaseException:
        await session.rollback()
        raise
    else:
        await session.commit()
    finally:
        await session.close()
