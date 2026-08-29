"""Unit tests for BuilderContext and menu orchestration."""

from __future__ import annotations

from fastapi_template.input_model import (
    BuilderContext,
    MenuCollection,
    MenuEntry,
    MultiselectMenuModel,
    SingularMenuModel,
)
from fastapi_template.profiles import expand_profile


def test_builder_context_attr_get_set_and_dict_copy() -> None:
    ctx = BuilderContext(db="postgresql")
    assert ctx.db == "postgresql"

    ctx.enable_redis = True
    assert ctx["enable_redis"] is True
    assert ctx.enable_redis is True

    snapshot = ctx.dict()
    snapshot["db"] = "mysql"
    assert ctx.db == "postgresql"
    assert snapshot == {"db": "mysql", "enable_redis": True}


def test_is_set_none_vs_false() -> None:
    ctx = BuilderContext()
    assert ctx.is_set("enable_redis") is False

    ctx.enable_redis = None
    assert ctx.has("enable_redis") is True
    assert ctx.is_set("enable_redis") is False

    ctx.enable_redis = False
    assert ctx.is_set("enable_redis") is True


def test_multiselect_marks_unselected_false() -> None:
    menu = MultiselectMenuModel(
        title="Features",
        entries=[
            MenuEntry(code="enable_redis", user_view="Redis", description="Redis"),
            MenuEntry(code="enable_taskiq", user_view="Taskiq", description="Taskiq"),
            MenuEntry(code="enable_llm", user_view="LLM", description="LLM"),
        ],
        before_ask=lambda _ctx: [
            MenuEntry(code="enable_redis", user_view="Redis", description="Redis"),
        ],
    )
    ctx = BuilderContext()
    result = menu.ask(ctx)

    assert result is not None
    assert result.enable_redis is True
    assert result.enable_taskiq is False
    assert result.enable_llm is False


def test_expand_profile_with_is_set_preserves_false() -> None:
    ctx = BuilderContext(otlp_enabled=False)
    expanded = expand_profile("saas", ctx)

    assert expanded.otlp_enabled is False
    assert expanded.enable_redis is True
    assert expanded.db == "postgresql"


def test_menu_collection_skips_need_ask_false() -> None:
    asked: list[str] = []

    class TrackingSingular(SingularMenuModel):
        def ask(self, context: BuilderContext) -> BuilderContext | None:
            asked.append(self.code)
            return super().ask(context)

    menus = MenuCollection(
        [
            TrackingSingular(
                title="API",
                code="api_type",
                entries=[
                    MenuEntry(code="rest", user_view="REST", description="REST"),
                ],
                before_ask_fun=lambda _ctx: MenuEntry(
                    code="rest",
                    user_view="REST",
                    description="REST",
                ),
            ),
            TrackingSingular(
                title="CI",
                code="ci_type",
                entries=[
                    MenuEntry(code="none", user_view="None", description="None"),
                    MenuEntry(code="github", user_view="GitHub", description="GitHub"),
                ],
                before_ask_fun=lambda _ctx: MenuEntry(
                    code="none",
                    user_view="None",
                    description="None",
                ),
            ),
        ]
    )

    ctx = BuilderContext(api_type="rest")
    result = menus.ask(ctx)

    assert result is not None
    assert asked == ["ci_type"]
    assert result.api_type == "rest"
    assert result.ci_type == "none"
