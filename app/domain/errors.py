"""Domain errors.

The API layer maps each of these onto an RFC 9457 problem document. Nothing in
the domain or application layer imports HTTP machinery.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for expected, client-attributable failures."""

    status_code: int = 400
    title: str = "Bad Request"
    problem_type: str = "about:blank"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class NotFoundError(DomainError):
    status_code = 404
    title = "Not Found"
    problem_type = "https://freddricklogan.github.io/student-engagement-api/problems/not-found"


class ConflictError(DomainError):
    status_code = 409
    title = "Conflict"
    problem_type = "https://freddricklogan.github.io/student-engagement-api/problems/conflict"


class ValidationError(DomainError):
    status_code = 422
    title = "Unprocessable Entity"
    problem_type = (
        "https://freddricklogan.github.io/student-engagement-api/problems/validation-error"
    )


class AuthenticationError(DomainError):
    status_code = 401
    title = "Unauthorized"
    problem_type = "https://freddricklogan.github.io/student-engagement-api/problems/unauthorized"


class AuthorizationError(DomainError):
    status_code = 403
    title = "Forbidden"
    problem_type = "https://freddricklogan.github.io/student-engagement-api/problems/forbidden"


class RateLimitError(DomainError):
    status_code = 429
    title = "Too Many Requests"
    problem_type = (
        "https://freddricklogan.github.io/student-engagement-api/problems/rate-limit-exceeded"
    )
