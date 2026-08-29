"""Domain models for the prompt management subsystem."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

PromptStatus = Literal[
    "draft",
    "validated",
    "candidate",
    "experiment",
    "active",
    "deprecated",
    "archived",
]

PromptVariableType = Literal[
    "string",
    "integer",
    "float",
    "boolean",
    "list[string]",
    "dict",
    "any",
]


ALLOWED_TRANSITIONS: dict[PromptStatus, frozenset[PromptStatus]] = {
    "draft": frozenset({"validated", "archived"}),
    "validated": frozenset({"candidate", "draft", "archived"}),
    "candidate": frozenset({"experiment", "active", "validated", "archived"}),
    "experiment": frozenset({"active", "candidate", "deprecated", "archived"}),
    "active": frozenset({"deprecated", "archived"}),
    "deprecated": frozenset({"archived", "active"}),
    "archived": frozenset(),
}


@dataclass(frozen=True, slots=True)
class PromptVariable:
    """Typed prompt input variable with observability flags."""

    name: str
    type: PromptVariableType = "string"
    required: bool = True
    default: Any = None
    description: str = ""
    secret: bool = False
    pii: bool = False
    log: bool = True


@dataclass(frozen=True, slots=True)
class PromptMessage:
    """A single role/content message in a structured prompt."""

    role: str
    content: str


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    """Immutable, versioned prompt artifact."""

    name: str
    version: int
    messages: tuple[PromptMessage, ...]

    variables: tuple[PromptVariable, ...] = ()

    status: PromptStatus = "draft"
    description: str = ""
    tags: frozenset[str] = frozenset()

    model: str | None = None
    provider: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None

    metadata: dict[str, Any] = field(default_factory=dict)

    created_at: datetime | None = None
    created_by: str | None = None
    checksum: str = ""

    @property
    def variable_names(self) -> frozenset[str]:
        return frozenset(v.name for v in self.variables)

    @property
    def required_variables(self) -> frozenset[str]:
        return frozenset(v.name for v in self.variables if v.required and v.default is None)

    @property
    def template(self) -> str:
        """Flattened content for simple string consumers / legacy APIs."""
        if len(self.messages) == 1:
            return self.messages[0].content
        return "\n\n".join(f"[{m.role}]\n{m.content}" for m in self.messages)

    def with_status(self, status: PromptStatus) -> PromptTemplate:
        return PromptTemplate(
            name=self.name,
            version=self.version,
            messages=self.messages,
            variables=self.variables,
            status=status,
            description=self.description,
            tags=self.tags,
            model=self.model,
            provider=self.provider,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            metadata=dict(self.metadata),
            created_at=self.created_at,
            created_by=self.created_by,
            checksum=self.checksum,
        )

    def snapshot(self) -> PromptTemplate:
        """Defensive copy so callers cannot mutate repository-held metadata."""
        return PromptTemplate(
            name=self.name,
            version=self.version,
            messages=self.messages,
            variables=self.variables,
            status=self.status,
            description=self.description,
            tags=self.tags,
            model=self.model,
            provider=self.provider,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            metadata=dict(self.metadata),
            created_at=self.created_at,
            created_by=self.created_by,
            checksum=self.checksum,
        )


@dataclass(frozen=True, slots=True)
class PromptAlias:
    """Named pointer to an immutable prompt version (e.g. production)."""

    name: str
    alias: str
    version: int


@dataclass(frozen=True, slots=True)
class PromptVariant:
    """Weighted experiment arm pointing at a prompt version."""

    id: str
    prompt_name: str
    version: int
    weight: float


@dataclass(frozen=True, slots=True)
class PromptExperiment:
    """Deterministic A/B (or N-way) experiment over prompt versions."""

    name: str
    prompt_name: str
    variants: tuple[PromptVariant, ...]
    active: bool = True
    salt: str = ""
    environment: str = "production"


@dataclass(frozen=True, slots=True)
class PromptSelector:
    """Resolution context for aliases, environments, and experiments."""

    environment: str = "production"
    subject_id: str | None = None
    tenant_id: str | None = None
    model: str | None = None
    segment: str | None = None


@dataclass(frozen=True, slots=True)
class RenderedPrompt:
    """Rendered prompt ready for an LLM call, with observability metadata."""

    name: str
    version: int
    messages: tuple[PromptMessage, ...]
    variables: dict[str, Any]
    variant: str | None = None
    checksum: str = ""
    model: str | None = None
    provider: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    input_tokens: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        if len(self.messages) == 1:
            return self.messages[0].content
        return "\n\n".join(f"[{m.role}]\n{m.content}" for m in self.messages)


@dataclass(frozen=True, slots=True)
class PromptEvaluation:
    """Evaluation result gate for promoting a prompt version."""

    prompt_name: str
    version: int
    dataset: str
    score: float
    metrics: dict[str, float]
    sample_count: int
    metadata: dict[str, Any] = field(default_factory=dict)


def compute_checksum(
    name: str,
    version: int,
    messages: tuple[PromptMessage, ...],
    variables: tuple[PromptVariable, ...],
    *,
    model: str | None = None,
    provider: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """Content hash for reproducibility of an immutable prompt version."""
    canonical = json.dumps(
        {
            "name": name,
            "version": version,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "variables": [
                {
                    "name": v.name,
                    "type": v.type,
                    "required": v.required,
                    "default": v.default,
                    "secret": v.secret,
                    "pii": v.pii,
                    "log": v.log,
                }
                for v in variables
            ],
            "model": model,
            "provider": provider,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_prompt(
    name: str,
    version: int,
    *,
    template: str | None = None,
    messages: tuple[PromptMessage, ...] | list[PromptMessage] | None = None,
    variables: tuple[PromptVariable, ...] | set[str] | frozenset[str] | None = None,
    status: PromptStatus = "draft",
    description: str = "",
    tags: frozenset[str] | set[str] | None = None,
    model: str | None = None,
    provider: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    metadata: dict[str, Any] | None = None,
    created_by: str | None = None,
) -> PromptTemplate:
    """Factory that normalizes legacy string templates into structured prompts."""
    if template is not None and messages is not None:
        raise ValueError("pass either template or messages, not both")
    if messages is None:
        if template is None:
            raise ValueError("either template or messages is required")
        msg_tuple: tuple[PromptMessage, ...] = (
            PromptMessage(role="user", content=template),
        )
    else:
        msg_tuple = tuple(messages)

    if variables is None:
        from {{cookiecutter.project_name}}.ai.prompts.parser import extract_variables

        names = extract_variables(msg_tuple)
        var_tuple: tuple[PromptVariable, ...] = tuple(
            PromptVariable(name=n) for n in sorted(names)
        )
    elif isinstance(variables, (set, frozenset)):
        var_tuple = tuple(PromptVariable(name=n) for n in sorted(variables))
    else:
        var_tuple = tuple(variables)

    created = datetime.now(timezone.utc)
    checksum = compute_checksum(
        name,
        version,
        msg_tuple,
        var_tuple,
        model=model,
        provider=provider,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return PromptTemplate(
        name=name,
        version=version,
        messages=msg_tuple,
        variables=var_tuple,
        status=status,
        description=description,
        tags=frozenset(tags or ()),
        model=model,
        provider=provider,
        temperature=temperature,
        max_tokens=max_tokens,
        metadata=dict(metadata or {}),
        created_at=created,
        created_by=created_by,
        checksum=checksum,
    )
