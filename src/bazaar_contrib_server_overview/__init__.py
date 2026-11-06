"""The overview: the place in the sidebar's workbench where modules put what is
worth a glance, each account ordering it as it likes."""

from __future__ import annotations

from contextlib import asynccontextmanager
lazy import asyncio
lazy from collections.abc import AsyncIterator
lazy from importlib.resources import files
lazy from pathlib import Path

from bazaar_contrib_server import SERVER, SidebarItem
from bazaar_contrib_server_database import SERVER_DB, SERVER_SCHEMA
from bazaar_contrib_server_migrations import SERVER_MIGRATIONS
from bazaar_core import Context, Contrib

from .contracts import OVERVIEW, Overview, OverviewItem
lazy from .board import Board
lazy from .schema import MODULE

__all__ = ["OVERVIEW", "Overview", "OverviewItem", "overview"]


@asynccontextmanager
async def _overview(ctx: Context) -> AsyncIterator[None]:
    server = ctx.accept(SERVER)
    async with ctx.accept(SERVER_SCHEMA).register(MODULE):
        resources = Path(str(files(__name__))) / "resources"
        icon = await asyncio.to_thread(
            (resources / "templates" / "overview" / "layout-dashboard.svg").read_text,
            encoding="utf-8",
        )
        board = Board(await server.pages("overview", __name__), ctx.accept(SERVER_DB))
        async with (
            server.module("overview", ui=board.app, locales=resources / "locales"),
            server.sidebar(
                SidebarItem(
                    text="overview.title",
                    icon=icon,
                    path="/overview",
                    group="server.sidebar.workbench",
                )
            ),
        ):
            ctx.offer(OVERVIEW, board)
            yield


overview = Contrib(
    accepts=[SERVER, SERVER_DB, SERVER_SCHEMA, SERVER_MIGRATIONS],
    offers=[OVERVIEW],
    lifespan=_overview,
)
