import functools
from collections import defaultdict
from typing import Any

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, model_validator


def cfg_field(default: Any = None, *, one_of: str | None = None, at_most_one_of: str | None = None) -> Any:
    """Typed field helper carrying exclusivity markers for BaseConfig."""  # noqa: D103
    extras: dict[str, str] = {}
    if one_of:
        extras["one_of"] = one_of
    if at_most_one_of:
        extras["at_most_one_of"] = at_most_one_of
    return Field(default=default, json_schema_extra=extras if extras else None)  # type: ignore[arg-type]


class BaseConfig(BaseModel):
    """
    Strict config kernel for every settings/options model.

    - extra="forbid": typos fail construction instead of silently ignoring.
    - cfg_field(one_of="g") / at_most_one_of="g": grouped exclusivity.
    - pretty_print(): legible YAML dump for logs.
    """

    model_config = ConfigDict(extra="forbid")

    @classmethod
    @functools.lru_cache(maxsize=None)
    def _marker_map(cls, marker: str) -> dict[str, list[str]]:
        groups: defaultdict[str, list[str]] = defaultdict(list)
        for name, field_info in cls.model_fields.items():
            extras = field_info.json_schema_extra
            if not isinstance(extras, dict):
                continue
            group = extras.get(marker)
            if isinstance(group, str) and group:
                groups[group].append(name)
        return dict(groups)

    @model_validator(mode="after")
    def _validate_exclusive_groups(self) -> "BaseConfig":
        for marker in ("one_of", "at_most_one_of"):
            for group_fields in self._marker_map(marker).values():
                set_count = sum(
                    getattr(self, field_name, None) is not None
                    for field_name in group_fields
                )
                if marker == "one_of" and set_count != 1:
                    raise ValueError(
                        f"exactly one of {','.join(group_fields)} is required "
                        f"(got {set_count})",
                    )
                if marker == "at_most_one_of" and set_count > 1:
                    raise ValueError(
                        f"at most one of {','.join(group_fields)} allowed "
                        f"(got {set_count})",
                    )
        return self

    def pretty_print(self) -> str:
        """Return a human-readable YAML dump of this config."""
        return yaml.dump(self.model_dump(), sort_keys=False)
