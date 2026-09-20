#!/usr/bin/env python3
"""Seed the database with deterministic demo data.

Unlike the legacy ``seed_data.py``, this script:

* does not import the web application (it depends on the database layer only);
* does not drop tables unless ``--reset`` is passed;
* refuses to touch a non-SQLite database without an explicit ``--force``, so
  pointing ``DATABASE_URL`` at production cannot destroy it by accident.

Usage::

    python -m scripts.seed              # create schema + demo users + data if empty
    python -m scripts.seed --reset      # drop and rebuild everything
    python -m scripts.seed --students 200 --seed 7
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.infrastructure.db import create_engine
from app.infrastructure.logging import configure_logging
from app.infrastructure.seed import (
    create_schema,
    ensure_demo_users,
    is_empty,
    seed_demo_data,
)
from app.infrastructure.settings import get_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset", action="store_true", help="drop every table before recreating it"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="allow running against a non-SQLite DATABASE_URL",
    )
    parser.add_argument("--students", type=int, default=40, help="number of students")
    parser.add_argument("--seed", type=int, default=None, help="RNG seed (default: DEMO_SEED)")
    return parser


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    configure_logging(settings.log_level, "console")

    if not settings.is_sqlite and not args.force:
        print(
            "Refusing to seed a non-SQLite database without --force.\n"
            f"DATABASE_URL points at: {settings.database_url.split('@')[-1]}",
            file=sys.stderr,
        )
        return 2

    engine = create_engine(settings)
    try:
        await create_schema(engine, reset=args.reset)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            created = await ensure_demo_users(session, settings)
            for account in created:
                print(f"created user: {account}")

            if args.reset or await is_empty(session):
                counts = await seed_demo_data(
                    session,
                    seed=args.seed if args.seed is not None else settings.demo_seed,
                    student_count=args.students,
                )
                for table, count in counts.items():
                    print(f"seeded {count} {table}")
            else:
                print("database already contains students; nothing seeded (use --reset)")

            await session.commit()
    finally:
        await engine.dispose()

    print("done.")
    return 0


def main() -> int:
    return asyncio.run(run(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
