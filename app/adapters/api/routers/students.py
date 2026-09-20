"""Student endpoints. Reads: any role. Writes: analyst/admin."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from app.adapters.api.deps import RequireReader, RequireWriter, StudentServiceDep
from app.application.dto import (
    PageNumber,
    PageSize,
    Problem,
    StudentCreate,
    StudentListResponse,
    StudentResponse,
)
from app.domain.entities import Student, StudentStatus

router = APIRouter(prefix="/students", tags=["students"])


def to_response(student: Student) -> StudentResponse:
    return StudentResponse(
        id=student.id,
        student_id=student.student_id,
        first_name=student.first_name,
        last_name=student.last_name,
        email=student.email,
        major=student.major,
        enrollment_date=student.enrollment_date,
        status=student.status,
        created_at=student.created_at,
    )


@router.get(
    "",
    response_model=StudentListResponse,
    summary="List students",
    responses={401: {"model": Problem}, 403: {"model": Problem}},
)
async def list_students(
    _user: RequireReader,
    service: StudentServiceDep,
    major: Annotated[str | None, Query(max_length=100)] = None,
    status_filter: Annotated[StudentStatus | None, Query(alias="status")] = StudentStatus.ACTIVE,
    page: Annotated[PageNumber, Query()] = 1,
    per_page: Annotated[PageSize, Query(alias="per_page")] = 20,
) -> StudentListResponse:
    """Page size is bounded at 100; the legacy endpoint accepted any integer."""
    result = await service.list_students(
        major=major, status=status_filter, page=page, page_size=per_page
    )
    return StudentListResponse(
        students=[to_response(s) for s in result.items],
        total=result.total,
        page=result.page,
        pages=result.pages,
    )


@router.get(
    "/{student_id}",
    response_model=StudentResponse,
    summary="Get one student",
    responses={401: {"model": Problem}, 403: {"model": Problem}, 404: {"model": Problem}},
)
async def get_student(
    _user: RequireReader,
    service: StudentServiceDep,
    student_id: Annotated[int, Path(ge=1)],
) -> StudentResponse:
    return to_response(await service.get_student(student_id))


@router.post(
    "",
    response_model=StudentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a student",
    responses={
        401: {"model": Problem},
        403: {"model": Problem, "description": "Viewer role cannot write"},
        409: {"model": Problem, "description": "Duplicate student_id or email"},
        422: {"model": Problem},
    },
)
async def create_student(
    _user: RequireWriter,
    service: StudentServiceDep,
    payload: StudentCreate,
) -> StudentResponse:
    student = await service.create_student(
        student_id=payload.student_id,
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=str(payload.email),
        major=payload.major,
        enrollment_date=payload.enrollment_date,
        status=payload.status,
    )
    return to_response(student)
