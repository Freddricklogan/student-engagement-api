"""Rate limiting.

Two layers:

* A global default bucket applied by ``SlowAPIMiddleware`` to every route.
* A tighter bucket on the credential endpoint, enforced by the
  ``auth_rate_limit`` dependency below.

The credential bucket is a dependency rather than slowapi's ``@limiter.limit``
decorator on purpose: that decorator replaces the endpoint with a
``(*args, **kwargs)`` wrapper, which destroys the signature FastAPI introspects
to resolve ``Annotated`` dependencies and form bodies. A dependency composes
cleanly and keeps the route's types intact.
"""

from __future__ import annotations

from limits import RateLimitItem, parse
from limits.aio.storage import MemoryStorage
from limits.aio.strategies import MovingWindowRateLimiter
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.domain.errors import RateLimitError
from app.infrastructure.settings import Settings, get_settings

_bootstrap = get_settings()

#: Global default bucket, consumed by ``SlowAPIMiddleware``.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[_bootstrap.rate_limit_default],
    enabled=_bootstrap.rate_limit_enabled,
    headers_enabled=True,
)

_storage = MemoryStorage()
_strategy = MovingWindowRateLimiter(_storage)
_auth_item: RateLimitItem = parse(_bootstrap.rate_limit_auth)
_auth_enabled: bool = _bootstrap.rate_limit_enabled


def configure_limiter(settings: Settings) -> Limiter:
    """Apply this app's settings to the process-wide limiters."""
    global _auth_item, _auth_enabled
    limiter.enabled = settings.rate_limit_enabled
    _auth_item = parse(settings.rate_limit_auth)
    _auth_enabled = settings.rate_limit_enabled
    return limiter


async def reset_limits() -> None:
    """Clear the credential bucket. Used by tests, never in a request path."""
    await _storage.reset()


async def auth_rate_limit(request: Request) -> None:
    """Consume one token from the credential bucket for this client address.

    Brute-forcing the password grant should cost something; the legacy API had
    no limiting of any kind.
    """
    if not _auth_enabled:
        return
    identity = get_remote_address(request)
    if not await _strategy.hit(_auth_item, identity, "auth"):
        raise RateLimitError(f"Too many authentication attempts. Limit: {_auth_item}.")
