"""FastAPI dependency wiring: DB session, repositories, services, RBAC."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Coroutine, Iterable
from typing import Annotated, Any

import structlog
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.repositories import (
    SqlAlchemyAnalyticsRepository,
    SqlAlchemyEventRepository,
    SqlAlchemySessionRepository,
    SqlAlchemyStudentRepository,
    SqlAlchemyUserRepository,
)
from app.application.services import (
    AnalyticsService,
    AuthService,
    EventService,
    SessionService,
    StudentService,
)
from app.domain.entities import READ_ROLES, WRITE_ROLES, Role, User
from app.domain.errors import AuthenticationError, AuthorizationError
from app.infrastructure.db import session_scope
from app.infrastructure.security import decode_access_token
from app.infrastructure.settings import Settings, get_settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """One SQLAlchemy session per request."""
    async for session in session_scope():
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_student_service(session: DbSession) -> StudentService:
    return StudentService(SqlAlchemyStudentRepository(session))


def get_session_service(session: DbSession) -> SessionService:
    return SessionService(
        SqlAlchemySessionRepository(session), SqlAlchemyStudentRepository(session)
    )


def get_event_service(session: DbSession) -> EventService:
    return EventService(SqlAlchemyEventRepository(session), SqlAlchemySessionRepository(session))


def get_analytics_service(session: DbSession) -> AnalyticsService:
    return AnalyticsService(
        SqlAlchemyAnalyticsRepository(session),
        SqlAlchemyStudentRepository(session),
        SqlAlchemyEventRepository(session),
    )


def get_auth_service(session: DbSession, settings: SettingsDep) -> AuthService:
    return AuthService(SqlAlchemyUserRepository(session), settings)


StudentServiceDep = Annotated[StudentService, Depends(get_student_service)]
SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]
EventServiceDep = Annotated[EventService, Depends(get_event_service)]
AnalyticsServiceDep = Annotated[AnalyticsService, Depends(get_analytics_service)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


async def get_current_user(
    request: Request,
    settings: SettingsDep,
    token: Annotated[str | None, Depends(oauth2_scheme)] = None,
) -> User:
    """Resolve the bearer token into a ``User``.

    Raises ``AuthenticationError`` (-> 401 problem+json) when the token is
    missing, malformed, expired or signed by the wrong key.
    """
    if not token:
        raise AuthenticationError("An OAuth2 bearer token is required.")
    claims = decode_access_token(token, settings)
    user = User(
        id=0,
        username=str(claims["sub"]),
        role=Role(str(claims["role"])),
        is_active=True,
    )
    # Bind identity to the request and the log context for this request only.
    request.state.username = user.username
    request.state.role = user.role.value
    structlog.contextvars.bind_contextvars(user=user.username, role=user.role.value)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(
    *allowed: Role,
) -> Callable[[User], Coroutine[Any, Any, User]]:
    """Build a dependency that admits only the listed roles.

    Composition, not decoration: the dependency runs *after* authentication in
    FastAPI's resolution order, so a route declares one thing —
    ``user: Annotated[User, Depends(require_roles(Role.ADMIN))]`` — and gets both.
    """
    permitted: frozenset[Role] = frozenset(allowed)

    async def _checker(user: CurrentUser) -> User:
        if user.role not in permitted:
            names = ", ".join(sorted(r.value for r in permitted))
            raise AuthorizationError(
                f"Role '{user.role.value}' may not perform this action. Required: {names}."
            )
        return user

    return _checker


def _roles(roles: Iterable[Role]) -> tuple[Role, ...]:
    return tuple(roles)


#: Any authenticated role may read.
RequireReader = Annotated[User, Depends(require_roles(*_roles(READ_ROLES)))]
#: Only analyst/admin may write.
RequireWriter = Annotated[User, Depends(require_roles(*_roles(WRITE_ROLES)))]
#: Admin-only operations.
RequireAdmin = Annotated[User, Depends(require_roles(Role.ADMIN))]
