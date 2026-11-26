"""Мэдэгдлийн имэйлийн дарааллыг харах, унасныг дахин илгээх (`make outbox`, `make outbox-retry`).

Агуулгыг хэзээ ч хэвлэхгүй, хаягийг нууцална: гаралт terminal-ийн түүх, дэлгэцийн зурагт үлддэг."""

import argparse
import asyncio
import sys

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from angel.core.config import get_settings
from angel.db.engine import create_engine
from angel.repositories.system.outbox import OutboxRepository

FAILED_SHOWN = 20


def _masked(address: str) -> str:
    local, _, domain = address.partition("@")
    return f"{local[:1]}***@{domain}"


async def describe_outbox(engine: AsyncEngine) -> str:
    async with async_sessionmaker(engine)() as session, session.begin():
        outbox = OutboxRepository(session)
        counts = await outbox.counts()
        lines = [
            f"pending: {counts.get('pending', 0)}  sent: {counts.get('sent', 0)}  "
            f"failed: {counts.get('failed', 0)}"
        ]
        failed = await outbox.failed(FAILED_SHOWN)
        lines += [
            f"  #{row.id}  {row.created_at:%Y-%m-%d %H:%M}  {_masked(row.to_address)}  "
            f"attempts={row.attempts}  {row.last_error}  {row.subject}"
            for row in failed
        ]
    if counts.get("failed", 0) > len(failed):
        lines.append(f"  ... and {counts['failed'] - len(failed)} more")
    return "\n".join(lines)


async def retry_failed(engine: AsyncEngine) -> str:
    async with async_sessionmaker(engine)() as session, session.begin():
        queued = await OutboxRepository(session).requeue_failed()
    return f"{queued} emails queued again"


async def _run(command: str) -> str:
    engine = create_engine(get_settings().database_url)
    try:
        return await (describe_outbox if command == "status" else retry_failed)(engine)
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="outbox", description=__doc__)
    parser.add_argument("command", choices=("status", "retry"))
    print(asyncio.run(_run(parser.parse_args(argv).command)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
