"""OAuth2 password-grant token endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from app.adapters.api.deps import AuthServiceDep, CurrentUser
from app.adapters.api.ratelimit import auth_rate_limit
from app.application.dto import CurrentUserResponse, Problem, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/token",
    response_model=TokenResponse,
    summary="Exchange username and password for a JWT",
    responses={
        401: {"model": Problem, "description": "Bad credentials"},
        429: {"model": Problem, "description": "Too many attempts"},
    },
    dependencies=[Depends(auth_rate_limit)],
)
async def issue_token(
    request: Request,
    auth: AuthServiceDep,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> TokenResponse:
    """OAuth2 password grant.

    The demo account (`demo` / `demo-viewer-2026`) is **read-only**: it can call
    every `GET`, and every write returns `403` as `application/problem+json`.
    """
    _user, token, expires_in = await auth.authenticate(form.username, form.password)
    request.state.username = _user.username
    request.state.role = _user.role.value
    return TokenResponse(access_token=token, expires_in=expires_in, role=_user.role)


@router.get(
    "/me",
    response_model=CurrentUserResponse,
    status_code=status.HTTP_200_OK,
    summary="Identity and role for the presented token",
    responses={401: {"model": Problem, "description": "Missing or invalid token"}},
)
async def whoami(user: CurrentUser) -> CurrentUserResponse:
    return CurrentUserResponse(username=user.username, role=user.role)
