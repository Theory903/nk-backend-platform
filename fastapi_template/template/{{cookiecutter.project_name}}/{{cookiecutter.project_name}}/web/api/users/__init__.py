"""Legacy fastapi-users HTTP router (compatibility while migrating to identity)."""

from {{cookiecutter.project_name}}.web.api.users.views import router

__all__ = ["router"]
