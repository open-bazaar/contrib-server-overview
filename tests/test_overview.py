"""The overview behind the real login, with a module putting things on it,
over real HTTP and in a real browser."""

from __future__ import annotations

import logging
import re
from contextlib import AsyncExitStack, asynccontextmanager
lazy import asyncio
lazy from collections.abc import AsyncIterator, Sequence
lazy from itertools import pairwise
lazy from typing import Any

import httpx
from bazaar_contrib_http import HTTP
from bazaar_contrib_server import SERVER
from bazaar_core import Context, Contrib, ContribEntry, ContribHub, ContribSpec, load
from playwright.async_api import FrameLocator, Page, async_playwright
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

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


SHELF = (
    OverviewItem(key="first", title="first", src="/ui/first"),
    OverviewItem(key="second", title="second", src="/ui/second", columns=2),
    OverviewItem(key="kept", title="kept", src="/ui/kept", permission="kept.view"),
)


@asynccontextmanager
async def signed_in(
    items: Sequence[OverviewItem] = SHELF,
) -> AsyncIterator[tuple[str, httpx.AsyncClient, Overview]]:
    """The entries running, a module with the items on the overview and goods
    of the height asked for at /ui/goods/<name>?height=, and the admin
    logged in."""
    found: dict[str, Any] = {}
    printed: list[str] = []

    class Printed(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            printed.append(record.getMessage())

    @asynccontextmanager
    async def shelf(ctx: Context) -> AsyncIterator[None]:
        found["url"] = ctx.accept(HTTP).url
        board = found["board"] = ctx.accept(OVERVIEW)
        pages = await ctx.accept(SERVER).pages("goods", "goods")

        async def good(request: Request) -> Response:
            return await pages.render(
                request,
                "goods/good.html",
                name=request.path_params["name"],
                height=int(request.query_params["height"]),
            )

        async with (
            ctx.accept(SERVER).module(
                "goods", ui=pages.application([Route("/{name}", good)])
            ),
            AsyncExitStack() as stack,
        ):
            for item in items:
                await stack.enter_async_context(board.register(item))
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
                    definition=Contrib(
                        accepts=[HTTP, SERVER, OVERVIEW], lifespan=shelf
                    ),
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
        arranged = await session.post(
            f"{url}/ui/overview/arrange", data={"order": "second,first,kept"}
        )
        assert arranged.status_code == 204
        again = await session.get(f"{url}/ui/overview/")
        assert again.text.index("/ui/second") < again.text.index("/ui/first")
        # an order that is not of what is shown is refused
        for order in ("first,absent,kept", "second,first"):
            refused = await session.post(
                f"{url}/ui/overview/arrange", data={"order": order}
            )
            assert refused.status_code == 422


async def test_content_away_for_a_while_comes_back_to_its_place():
    async with signed_in() as (url, session, board):

        async def arrange(*keys: str) -> None:
            arranged = await session.post(
                f"{url}/ui/overview/arrange", data={"order": ",".join(keys)}
            )
            assert arranged.status_code == 204

        third = OverviewItem(key="third", title="third", src="/ui/third")
        async with board.register(third):
            await arrange("third", "first", "second", "kept")
        # with the contrib bringing it stopped, the rest is put in another order
        await arrange("kept", "first", "second")
        async with board.register(third):
            page = await session.get(f"{url}/ui/overview/")
        assert page.text.index("/ui/third") < page.text.index("/ui/first")


async def test_the_overview_greets_the_account_and_gives_content_its_columns():
    async with signed_in() as (url, session, _):
        page = await session.get(f"{url}/ui/overview/")
        second = re.search(
            r'<article class="([^"]*)"[^>]*>(?:(?!</article>).)*/ui/second',
            page.text,
            re.DOTALL,
        )
        assert second is not None
        assert "c2" in second.group(1).split()
        greeting = re.search(r'<h2 class="greeting".*?</h2>', page.text, re.DOTALL)
        assert greeting is not None
        assert "admin" in greeting.group(0)


def slot(board: FrameLocator, key: str):
    """Where the overview put the content of the key."""
    return board.locator(f'article.slot:has(iframe[title="{key}"])')


async def fitted(page: Page, board: FrameLocator, which: str) -> None:
    """Wait until every content shown, or some of it, is as tall as its
    page says: the shortest goods are taller than a frame starts."""
    await board.locator("#board").wait_for()
    overview = next(frame for frame in page.frames if "/ui/overview/" in frame.url)
    await overview.wait_for_function(
        f"[...document.querySelectorAll('.slot iframe')].{which}("
        "(frame) => frame.offsetHeight >= 160)"
    )


async def test_the_overview_lays_content_out_by_its_order_columns_and_rows():
    # registered out of order: a stall two rows tall, with what needs the
    # account and what went on lately down its side
    items = (
        OverviewItem(
            key="feed",
            title="feed",
            src="/ui/goods/feed?height=240",
            order=40,
        ),
        OverviewItem(
            key="usage",
            title="usage",
            src="/ui/goods/usage?height=160",
            order=10,
            columns=3,
        ),
        OverviewItem(
            key="attention",
            title="attention",
            src="/ui/goods/attention?height=200",
            order=30,
        ),
        OverviewItem(
            key="stall",
            title="stall",
            src="/ui/goods/stall?height=520",
            order=20,
            columns=2,
            rows=2,
        ),
    )
    async with signed_in(items) as (url, session, _), async_playwright() as driver:
        browser = await driver.chromium.launch()
        try:
            context = await browser.new_context(
                locale="zh-CN", viewport={"width": 1440, "height": 900}
            )
            await context.add_cookies(
                [
                    {"name": cookie.name, "value": cookie.value or "", "url": url}
                    for cookie in session.cookies.jar
                ]
            )
            page = await context.new_page()
            await page.goto(f"{url}/overview")
            board = page.frame_locator("iframe.frame")
            await fitted(page, board, "every")
            usage, stall, attention, feed = [
                await slot(board, key).bounding_box()
                for key in ("usage", "stall", "attention", "feed")
            ]
            assert usage and stall and attention and feed
            assert usage["y"] + usage["height"] <= stall["y"]
            assert stall["x"] + stall["width"] <= attention["x"]
            assert attention["x"] == feed["x"]
            assert attention["y"] == stall["y"]
            assert attention["y"] + attention["height"] <= feed["y"]
            assert feed["y"] < stall["y"] + stall["height"]

            # a phone: all of it one above another, in its order
            await page.set_viewport_size({"width": 390, "height": 844})
            await page.reload()
            board = page.frame_locator("iframe.frame")
            await fitted(page, board, "every")
            boxes = [
                await slot(board, key).bounding_box()
                for key in ("usage", "stall", "attention", "feed")
            ]
            assert all(boxes)
            for above, below in pairwise(boxes):
                assert above and below
                assert above["x"] == below["x"]
                assert above["y"] + above["height"] <= below["y"]
        finally:
            await browser.close()


async def test_a_card_dragged_while_arranged_takes_its_new_place():
    items = tuple(
        OverviewItem(key=key, title=key, src=f"/ui/goods/{key}?height=200")
        for key in ("first", "second", "third")
    )
    async with signed_in(items) as (url, session, _), async_playwright() as driver:
        browser = await driver.chromium.launch()
        try:
            context = await browser.new_context(
                locale="zh-CN", viewport={"width": 1440, "height": 900}
            )
            await context.add_cookies(
                [
                    {"name": cookie.name, "value": cookie.value or "", "url": url}
                    for cookie in session.cookies.jar
                ]
            )
            page = await context.new_page()
            await page.goto(f"{url}/overview")
            board = page.frame_locator("iframe.frame")
            await fitted(page, board, "every")
            overview = next(one for one in page.frames if "/ui/overview/" in one.url)
            await overview.evaluate(
                "document.querySelectorAll('.slot iframe')"
                ".forEach((frame) => (frame.contentWindow.kept = true))"
            )
            await board.get_by_role("button", name="自定义").click()
            # the third card taken by the mouse and let go over the first
            taken = await slot(board, "third").bounding_box()
            onto = await slot(board, "first").bounding_box()
            assert taken and onto
            await page.mouse.move(
                taken["x"] + taken["width"] / 2, taken["y"] + taken["height"] / 2
            )
            await page.mouse.down()
            for step in range(1, 11):
                await page.mouse.move(
                    taken["x"] + (onto["x"] + 8 - taken["x"]) * step / 10,
                    taken["y"] + (onto["y"] + 8 - taken["y"]) * step / 10,
                )
            async with page.expect_response(
                lambda answer: answer.url.endswith("/ui/overview/arrange")
            ) as arranged:
                await page.mouse.up()
            assert (await arranged.value).status == 204
            # then the first moved a place on by its grip's arrow key, from
            # where the cards show now
            await slot(board, "first").locator(".grip").focus()
            async with page.expect_response(
                lambda answer: answer.url.endswith("/ui/overview/arrange")
            ) as arranged:
                await page.keyboard.press("ArrowRight")
            assert (await arranged.value).status == 204
            await board.get_by_role("button", name="完成").click()
            # the cards made room without loading their pages again
            assert await overview.evaluate(
                "[...document.querySelectorAll('.slot iframe')]"
                ".every((frame) => frame.contentWindow.kept === true)"
            )
            third, second, first = [
                await slot(board, key).bounding_box()
                for key in ("third", "second", "first")
            ]
            assert third and second and first
            assert third["x"] < second["x"] < first["x"]
            await page.reload()
            board = page.frame_locator("iframe.frame")
            await fitted(page, board, "every")
            keys = await board.locator("article.slot").evaluate_all(
                "(slots) => slots.map((one) => one.dataset.key)"
            )
            assert keys.index("third") < keys.index("second") < keys.index("first")
        finally:
            await browser.close()
