from __future__ import annotations

import abc
import builtins
from collections import UserDict
from collections.abc import Callable, Iterable
from typing import Any

import click
from prompt_toolkit.shortcuts import checkboxlist_dialog, radiolist_dialog
from pydantic import BaseModel, ConfigDict

try:
    from simple_term_menu import TerminalMenu
except Exception:  # pragma: no cover
    TerminalMenu = None

# ============================================================================
# Builder context
# ============================================================================


class BuilderContext(UserDict[str, Any]):
    """
    Mutable project-generation context.

    The context intentionally behaves like a dictionary because the
    cookiecutter/template system has a dynamic set of options.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(kwargs)

    def __getattr__(self, name: str) -> Any:
        """
        Allow attribute-style access:

            context.db
            context.enable_redis
        """
        try:
            return self.data[name]
        except KeyError as exc:
            raise AttributeError(
                f"{type(self).__name__!r} object has no attribute {name!r}"
            ) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        """
        Preserve UserDict internals while supporting:

            context.db = "postgresql"
        """
        if name == "data":
            object.__setattr__(self, name, value)
            return

        self.data[name] = value

    def dict(self) -> dict[str, Any]:
        """
        Backward-compatible dictionary representation.

        Returns a copy so callers cannot accidentally mutate the context
        without going through the context object.
        """
        return dict(self.data)

    def update_from(
        self,
        values: builtins.dict[str, Any],
        *,
        overwrite: bool = True,
    ) -> None:
        """Update context from a dictionary."""
        if overwrite:
            self.data.update(values)
            return

        for key, value in values.items():
            self.data.setdefault(key, value)

    def has(self, key: str) -> bool:
        """Return whether a key exists in the context."""
        return key in self.data

    def is_set(self, key: str) -> bool:
        """Return whether a key has a non-None value."""
        return self.data.get(key) is not None


# ============================================================================
# Database metadata
# ============================================================================


class Database(BaseModel):
    """Database definition used by the project generator."""

    name: str
    image: str | None = None
    driver: str | None = None
    async_driver: str | None = None
    port: int | None = None
    driver_short: str | None = None


# ============================================================================
# Menu entries
# ============================================================================


class MenuEntry(BaseModel):
    """
    One selectable project-generation option.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    code: str
    cli_name: str | None = None
    user_view: str
    description: str
    is_hidden: Callable[[BuilderContext], bool] | None = None
    additional_info: Any = None

    @property
    def generated_name(self) -> str:
        """Return the CLI parameter name."""
        return self.cli_name or self.code


SKIP_ENTRY = MenuEntry(
    code="skip",
    user_view="skip",
    description="skip",
)

# ============================================================================
# Base menu
# ============================================================================


class BaseMenuModel(BaseModel, abc.ABC):
    """
    Base class for interactive/CLI configuration menus.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    title: str
    entries: list[MenuEntry]
    description: str = ""

    def preview(self, current_value: str) -> str:
        """Return the description for a selected menu value."""
        for entry in self.entries:
            if entry.user_view == current_value:
                return entry.description

        return "Unknown value"

    @abc.abstractmethod
    def get_cli_options(self) -> list[click.Option]:
        """Return Click options represented by this menu."""
        raise NotImplementedError

    @abc.abstractmethod
    def ask(self, context: BuilderContext) -> BuilderContext | None:
        """Ask the user for values interactively."""
        raise NotImplementedError

    @abc.abstractmethod
    def need_ask(self, context: BuilderContext) -> bool:
        """Return whether interactive input is still required."""
        raise NotImplementedError

    def after_ask(self, context: BuilderContext) -> BuilderContext:
        """Hook executed after the menu finishes."""
        return context


# ============================================================================
# Singular selection
# ============================================================================


class SingularMenuModel(BaseMenuModel):
    """
    Menu where exactly one entry is selected.

    Example:

        database:
            none
            postgresql
            mysql
    """

    code: str
    cli_name: str | None = None

    before_ask_fun: Callable[[BuilderContext], MenuEntry | None] | None = None

    after_ask_fun: Callable[[BuilderContext, "SingularMenuModel"], BuilderContext] | None = None

    parser: Callable[[str], Any] | None = None

    def get_cli_options(self) -> list[click.Option]:
        cli_name = self.cli_name or self.code

        choices = [entry.generated_name for entry in self.entries]

        return [
            click.Option(
                param_decls=[
                    f"--{cli_name}",
                    self.code,
                ],
                type=click.Choice(
                    choices,
                    case_sensitive=False,
                ),
                default=None,
                help=self.description,
            )
        ]

    def need_ask(self, context: BuilderContext) -> bool:
        return not context.is_set(self.code)

    def _visible_entries(
        self,
        context: BuilderContext,
    ) -> list[MenuEntry]:
        """Return entries that are currently selectable."""
        return [
            entry
            for entry in self.entries
            if entry.is_hidden is None or not entry.is_hidden(context)
        ]

    def _find_entry(
        self,
        context: BuilderContext,
    ) -> MenuEntry | None:
        """Resolve an existing context value into a menu entry."""
        current_value = context.data.get(self.code)

        if current_value is None:
            return None

        for entry in self.entries:
            if entry.code == current_value:
                return entry

        return None

    def _interactive_terminal_menu(
        self,
        context: BuilderContext,
        entries: list[MenuEntry],
    ) -> MenuEntry | None:
        if TerminalMenu is None:
            return None

        menu = TerminalMenu(
            title=self.title,
            menu_entries=[entry.user_view for entry in entries],
            multi_select=False,
            preview_title="Description",
            preview_command=self.preview,
            preview_size=0.5,
        )

        idx = menu.show()

        if idx is None:
            return None

        return entries[idx]

    def _interactive_prompt_toolkit(
        self,
        entries: list[MenuEntry],
    ) -> MenuEntry | None:
        selected = radiolist_dialog(
            title=self.title,
            text=self.description,
            values=[(entry, entry.user_view) for entry in entries],
        ).run()

        return selected or None

    def ask(
        self,
        context: BuilderContext,
    ) -> BuilderContext | None:
        chosen_entry: MenuEntry | None = None

        # Give the caller an opportunity to preselect an option.
        if self.before_ask_fun is not None:
            chosen_entry = self.before_ask_fun(context)

        # Respect an already supplied context value.
        if chosen_entry is None:
            chosen_entry = self._find_entry(context)

        # Interactive selection.
        if chosen_entry is None:
            available_entries = self._visible_entries(context)

            if not available_entries:
                return None

            if TerminalMenu is not None:
                chosen_entry = self._interactive_terminal_menu(
                    context,
                    available_entries,
                )
            else:
                chosen_entry = self._interactive_prompt_toolkit(
                    available_entries,
                )

            if chosen_entry is None:
                return None

        value: Any = chosen_entry.code

        if self.parser is not None:
            value = self.parser(value)

        setattr(context, self.code, value)

        return context

    def after_ask(
        self,
        context: BuilderContext,
    ) -> BuilderContext:
        if self.after_ask_fun is not None:
            return self.after_ask_fun(context, self)

        return super().after_ask(context)


# ============================================================================
# Multi-selection
# ============================================================================


class MultiselectMenuModel(BaseMenuModel):
    """
    Menu where multiple independent boolean options can be selected.

    Example:

        --enable-redis
        --enable-taskiq
        --enable-llm
    """

    code: str = "features"

    before_ask: (
        Callable[
            [BuilderContext],
            list[MenuEntry] | None,
        ]
        | None
    ) = None

    def get_cli_options(self) -> list[click.Option]:
        options: list[click.Option] = []

        for entry in self.entries:
            options.append(
                click.Option(
                    param_decls=[
                        f"--{entry.generated_name}",
                        entry.code,
                    ],
                    is_flag=True,
                    default=None,
                    help=entry.user_view,
                )
            )

        return options

    def need_ask(self, context: BuilderContext) -> bool:
        return any(not context.is_set(entry.code) for entry in self.entries)

    def _visible_entries(
        self,
        context: BuilderContext,
    ) -> list[MenuEntry]:
        return [
            entry
            for entry in self.entries
            if entry.is_hidden is None or not entry.is_hidden(context)
        ]

    def ask(
        self,
        context: BuilderContext,
    ) -> BuilderContext | None:
        chosen_entries: list[MenuEntry] | None = None

        # Programmatic override.
        if self.before_ask is not None:
            chosen_entries = self.before_ask(context)

        # Interactive mode.
        if chosen_entries is None:
            unknown_entries = [entry for entry in self.entries if not context.is_set(entry.code)]

            visible_entries = [
                entry
                for entry in unknown_entries
                if entry.is_hidden is None or not entry.is_hidden(context)
            ]

            if TerminalMenu is not None:
                menu = TerminalMenu(
                    title=self.title,
                    menu_entries=[entry.user_view for entry in visible_entries],
                    multi_select=True,
                    preview_title="Description",
                    preview_command=self.preview,
                )

                indexes = menu.show()

                if indexes is None:
                    return None

                chosen_entries = [visible_entries[index] for index in indexes]

            else:
                chosen_entries = checkboxlist_dialog(
                    title=self.title,
                    text=self.description,
                    values=[(entry, entry.user_view) for entry in visible_entries],
                ).run()

                if chosen_entries is None:
                    return None

        for entry in chosen_entries:
            setattr(context, entry.code, True)

        # Explicitly mark visible options that were not selected as False.
        selected_codes = {entry.code for entry in chosen_entries}

        for entry in self.entries:
            if entry.code not in selected_codes:
                if context.data.get(entry.code) is None:
                    setattr(context, entry.code, False)

        return context


# ============================================================================
# Menu collection
# ============================================================================


class MenuCollection:
    """
    Executes a collection of menus against one BuilderContext.

    This keeps menu orchestration outside individual menu implementations.
    """

    def __init__(
        self,
        menus: Iterable[BaseMenuModel],
    ) -> None:
        self.menus = list(menus)

    def get_cli_options(self) -> list[click.Option]:
        options: list[click.Option] = []

        for menu in self.menus:
            options.extend(menu.get_cli_options())

        return options

    def ask(
        self,
        context: BuilderContext,
    ) -> BuilderContext | None:
        current: BuilderContext | None = context

        for menu in self.menus:
            if current is None:
                return None
            if not menu.need_ask(current):
                continue

            current = menu.ask(current)

            if current is None:
                return None

            current = menu.after_ask(current)

        return current
