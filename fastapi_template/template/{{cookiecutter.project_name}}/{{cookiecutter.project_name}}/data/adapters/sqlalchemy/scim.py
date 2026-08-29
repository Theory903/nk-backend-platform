from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, UniqueConstraint, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from {{cookiecutter.project_name}}.core.identifiers import new_id
from {{cookiecutter.project_name}}.core.scim import (
    ScimEmail,
    ScimMeta,
    ScimName,
    ScimUser,
)
from {{cookiecutter.project_name}}.core.time import utcnow
from {{cookiecutter.project_name}}.data.optimistic_lock import (
    ConcurrencyConflictError,
)
from {{cookiecutter.project_name}}.data.scim_repository import (
    ScimUserRepository,
)
from {{cookiecutter.project_name}}.db.base import Base


class ScimUserRow(Base):
    """SQL persistence for SCIM User resources."""

    __tablename__ = "platform_scim_users"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
    )

    org_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    external_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    user_name: Mapped[str] = mapped_column(
        String(320),
        nullable=False,
    )

    email: Mapped[str | None] = mapped_column(
        String(320),
        nullable=True,
    )

    display_name: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )

    given_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    family_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    active: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
    )

    version: Mapped[int] = mapped_column(
        default=1,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "org_id",
            "user_name",
            name="uq_scim_org_username",
        ),
        UniqueConstraint(
            "org_id",
            "external_id",
            name="uq_scim_org_external_id",
        ),
        Index(
            "ix_scim_org_active",
            "org_id",
            "active",
        ),
    )


class SqlalchemyScimRepository(ScimUserRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        user: ScimUser,
        org_id: str,
    ) -> ScimUser:
        row = ScimUserRow(
            id=user.id or new_id("scim"),
            org_id=org_id,
            external_id=user.externalId,
            user_name=user.userName,
            email=self._primary_email(user),
            display_name=user.displayName,
            given_name=(
                user.name.givenName
                if user.name
                else None
            ),
            family_name=(
                user.name.familyName
                if user.name
                else None
            ),
            active=user.active,
            version=1,
            created_at=utcnow(),
            updated_at=utcnow(),
        )

        self.session.add(row)

        await self.session.flush()

        return self._to_domain(row)

    async def get(
        self,
        *,
        user_id: str,
        org_id: str,
    ) -> ScimUser | None:
        stmt = select(ScimUserRow).where(
            ScimUserRow.id == user_id,
            ScimUserRow.org_id == org_id,
            ScimUserRow.deleted_at.is_(None),
        )

        row = (
            await self.session.execute(stmt)
        ).scalar_one_or_none()

        return self._to_domain(row) if row else None

    async def get_by_external_id(
        self,
        *,
        external_id: str,
        org_id: str,
    ) -> ScimUser | None:
        stmt = select(ScimUserRow).where(
            ScimUserRow.external_id == external_id,
            ScimUserRow.org_id == org_id,
            ScimUserRow.deleted_at.is_(None),
        )

        row = (
            await self.session.execute(stmt)
        ).scalar_one_or_none()

        return self._to_domain(row) if row else None

    async def get_by_username(
        self,
        *,
        username: str,
        org_id: str,
    ) -> ScimUser | None:
        stmt = select(ScimUserRow).where(
            ScimUserRow.user_name == username,
            ScimUserRow.org_id == org_id,
            ScimUserRow.deleted_at.is_(None),
        )

        row = (
            await self.session.execute(stmt)
        ).scalar_one_or_none()

        return self._to_domain(row) if row else None

    async def replace(
        self,
        *,
        user_id: str,
        user: ScimUser,
        org_id: str,
        expected_version: int | None = None,
    ) -> ScimUser | None:
        # Read-then-write concurrency check (not atomic WHERE version=).
        stmt = select(ScimUserRow).where(
            ScimUserRow.id == user_id,
            ScimUserRow.org_id == org_id,
            ScimUserRow.deleted_at.is_(None),
        )

        row = (
            await self.session.execute(stmt)
        ).scalar_one_or_none()

        if row is None:
            return None

        if (
            expected_version is not None
            and row.version != expected_version
        ):
            raise ConcurrencyConflictError(
                user_id,
                expected_version,
                row.version,
            )

        row.external_id = user.externalId
        row.user_name = user.userName
        row.email = self._primary_email(user)
        row.display_name = user.displayName

        row.given_name = (
            user.name.givenName
            if user.name
            else None
        )

        row.family_name = (
            user.name.familyName
            if user.name
            else None
        )

        row.active = user.active
        row.version += 1
        row.updated_at = utcnow()

        await self.session.flush()

        return self._to_domain(row)

    async def deactivate(
        self,
        *,
        user_id: str,
        org_id: str,
    ) -> bool:
        stmt = select(ScimUserRow).where(
            ScimUserRow.id == user_id,
            ScimUserRow.org_id == org_id,
            ScimUserRow.deleted_at.is_(None),
        )

        row = (
            await self.session.execute(stmt)
        ).scalar_one_or_none()

        if row is None:
            return False

        row.active = False
        row.deleted_at = utcnow()
        row.updated_at = utcnow()
        row.version += 1

        await self.session.flush()

        return True

    async def list(
        self,
        *,
        org_id: str,
        filter_expression: Any | None,
        start_index: int,
        count: int,
    ) -> tuple[list[ScimUser], int]:
        stmt = select(ScimUserRow).where(
            ScimUserRow.org_id == org_id,
            ScimUserRow.deleted_at.is_(None),
        )

        if filter_expression is not None:
            stmt = self._apply_filter(
                stmt,
                filter_expression,
            )

        count_stmt = select(
            func.count(),
        ).select_from(
            stmt.subquery(),
        )

        total = int(
            (
                await self.session.execute(
                    count_stmt,
                )
            ).scalar_one(),
        )

        offset = start_index - 1

        stmt = (
            stmt
            .order_by(ScimUserRow.id.asc())
            .offset(offset)
            .limit(count)
        )

        rows = (
            await self.session.execute(stmt)
        ).scalars().all()

        return (
            [self._to_domain(row) for row in rows],
            total,
        )

    def _apply_filter(
        self,
        stmt: Any,
        expression: Any,
    ) -> Any:
        from {{cookiecutter.project_name}}.core.scim_filter import (
            FilterExpression,
            FilterGroup,
            FilterOperator,
        )

        if isinstance(expression, FilterGroup):
            clauses = [
                self._apply_filter(
                    select(ScimUserRow),
                    child,
                ).whereclause
                for child in expression.children
            ]

            clauses = [
                clause
                for clause in clauses
                if clause is not None
            ]

            if expression.operator == "and":
                return stmt.where(and_(*clauses))

            return stmt.where(or_(*clauses))

        if not isinstance(expression, FilterExpression):
            return stmt

        column = self._filter_column(
            expression.attribute,
        )

        if column is None:
            return stmt.where(False)

        op = expression.operator
        value = expression.value

        if op is FilterOperator.EQ:
            return stmt.where(column == value)

        if op is FilterOperator.NE:
            return stmt.where(column != value)

        if op is FilterOperator.CO:
            return stmt.where(
                column.ilike(f"%{value}%"),
            )

        if op is FilterOperator.SW:
            return stmt.where(
                column.ilike(f"{value}%"),
            )

        if op is FilterOperator.EW:
            return stmt.where(
                column.ilike(f"%{value}"),
            )

        if op is FilterOperator.GT:
            return stmt.where(column > value)

        if op is FilterOperator.GE:
            return stmt.where(column >= value)

        if op is FilterOperator.LT:
            return stmt.where(column < value)

        if op is FilterOperator.LE:
            return stmt.where(column <= value)

        if op is FilterOperator.PR:
            return stmt.where(column.is_not(None))

        return stmt

    @staticmethod
    def _filter_column(
        name: str,
    ) -> Any:
        mapping = {
            "id": ScimUserRow.id,
            "externalId": ScimUserRow.external_id,
            "userName": ScimUserRow.user_name,
            "displayName": ScimUserRow.display_name,
            "active": ScimUserRow.active,
            "emails.value": ScimUserRow.email,
            "name.givenName": ScimUserRow.given_name,
            "name.familyName": ScimUserRow.family_name,
        }

        return mapping.get(name)

    @staticmethod
    def _primary_email(
        user: ScimUser,
    ) -> str | None:
        for email in user.emails:
            if email.primary:
                return email.value

        return user.emails[0].value if user.emails else None

    @staticmethod
    def _to_domain(
        row: ScimUserRow,
    ) -> ScimUser:
        emails = []

        if row.email:
            emails.append(
                ScimEmail(
                    value=row.email,
                    type="work",
                    primary=True,
                ),
            )

        return ScimUser(
            id=row.id,
            externalId=row.external_id,
            userName=row.user_name,
            active=row.active,
            displayName=row.display_name,
            name=ScimName(
                givenName=row.given_name,
                familyName=row.family_name,
            ),
            emails=emails,
            meta=ScimMeta(
                resourceType="User",
                version=str(row.version),
            ),
        )


__all__ = [
    "ScimUserRow",
    "SqlalchemyScimRepository",
]
