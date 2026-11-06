"""The overview behind the real login, with a module putting two things on it, over real HTTP."""

from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager
lazy import asyncio
lazy from collections.abc import AsyncIterator
lazy from typing import Any

import httpx
from bazaar_contrib_http import HTTP
from bazaar_core import Context, Contrib, ContribEntry, ContribHub, ContribSpec, load

from bazaar_contrib_server_overview import OVERVIEW, Overview, OverviewItem

ENTRIES = (
    ("timer-wheel", {}),
    ("http", {"listen": "127.0.0.1:0"}),
    ("server-database", {}),
    ("server-migrations", {}),
    ("server", {}),
    ("server-theme-night", {}),
    ("server-theme-day", {}),
    ("server-access", {}),
    ("server-overview", {}),
)


@asynccontextmanager
async def signed_in() -> AsyncIterator[tuple[str, httpx.AsyncClient, Overview]]:
    """The entries running, a module with things on the overview, and the
    admin logged in."""
    found: dict[str, Any] = {}
    printed: list[str] = []

    class Printed(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            printed.append(record.getMessage())

    @asynccontextmanager
    async def shelf(ctx: Context) -> AsyncIterator[None]:
        found["url"] = ctx.accept(HTTP).url
        board = found["board"] = ctx.accept(OVERVIEW)
        async with (
            board.register(OverviewItem(key="first", title="first", src="/ui/first")),
            board.register(
                OverviewItem(key="second", title="second", src="/ui/second", columns=2)
            ),
            board.register(
                OverviewItem(
                    key="kept", title="kept", src="/ui/kept", permission="kept.view"
                )
            ),
        ):
            yield

    composition = await asyncio.to_thread(
        load, [ContribSpec(contrib=name, config=config) for name, config in ENTRIES]
    )
    composition = composition.model_copy(
        update={
            "entries": (
                *composition.entries,
                ContribEntry(
                    name="shelf",
                    definition=Contrib(accepts=[HTTP, OVERVIEW], lifespan=shelf),
                ),
            )
        }
    )
    logger = logging.getLogger("bazaar_contrib_server_access")
    handler = Printed()
    logger.addHandler(handler)
    try:
        async with (
            ContribHub() as hub,
            hub.enable(composition),
            await asyncio.to_thread(httpx.AsyncClient, timeout=60) as session,
        ):
            password = next(
                created.group(1)
                for message in printed
                if (created := re.search(r"with password (\S+);", message))
            )
            await session.post(
                f"{found['url']}/login/", data={"name": "admin", "password": password}
            )
            yield found["url"], session, found["board"]
    finally:
        logger.removeHandler(handler)


async def test_home_leads_to_the_overview_in_the_workbench():
    async with signed_in() as (url, session, _):
        home = await session.get(f"{url}/")
        assert home.status_code == 307
        assert home.headers["location"] == "/overview"
        shell = await session.get(f"{url}/overview")
        assert 'href="/overview"' in shell.text
        assert "nav-group" in shell.text


async def test_the_overview_keeps_the_order_each_account_gives_it():
    async with signed_in() as (url, session, _):
        page = await session.get(f"{url}/ui/overview/")
        assert page.text.index("/ui/first") < page.text.index("/ui/second")
        # the admin may see everything, the content behind a point included
        assert "/ui/kept" in page.text
        moved = await session.post(
            f"{url}/ui/overview/move", data={"key": "first", "toward": "later"}
        )
        assert moved.status_code == 200
        again = await session.get(f"{url}/ui/overview/")
        assert again.text.index("/ui/second") < again.text.index("/ui/first")
        missing = await session.post(
            f"{url}/ui/overview/move", data={"key": "absent", "toward": "later"}
        )
        assert missing.status_code == 404


async def test_content_away_for_a_while_comes_back_to_its_place():
    async with signed_in() as (url, session, board):

        async def move(key: str, toward: str) -> None:
            moved = await session.post(
                f"{url}/ui/overview/move", data={"key": key, "toward": toward}
            )
            assert moved.status_code == 200

        third = OverviewItem(key="third", title="third", src="/ui/third")
        async with board.register(third):
            for _ in range(3):
                await move("third", "earlier")
        # with the contrib bringing it stopped, the rest is moved around
        await move("kept", "earlier")
        async with board.register(third):
            page = await session.get(f"{url}/ui/overview/")
        assert page.text.index("/ui/third") < page.text.index("/ui/first")


async def test_the_overview_greets_the_account_and_gives_content_its_columns():
    async with signed_in() as (url, session, _):
        page = await session.get(f"{url}/ui/overview/")
        second = re.search(
            r'<article class="([^"]*)">(?:(?!</article>).)*/ui/second',
            page.text,
            re.DOTALL,
        )
        assert second is not None
        assert "c2" in second.group(1).split()
        greeting = re.search(r'<h2 class="greeting".*?</h2>', page.text, re.DOTALL)
        assert greeting is not None
        assert "admin" in greeting.group(0)
