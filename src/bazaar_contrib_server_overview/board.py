"""The overview page: the content the account may see, in the order it chose."""

from __future__ import annotations

from contextlib import asynccontextmanager
lazy from collections.abc import AsyncIterator
lazy from typing import cast

lazy from bazaar_contrib_server import Account, Pages
lazy from bazaar_contrib_storage import (
    Column,
    Compare,
    Database,
    Delete,
    Insert,
    Select,
    Session,
    Value,
)
lazy from pydantic import BaseModel, ValidationError
lazy from starlette.exceptions import HTTPException
lazy from starlette.requests import Request
lazy from starlette.responses import Response
lazy from starlette.routing import Route
lazy from starlette.types import ASGIApp

lazy from .contracts import OverviewItem


class _Arrangement(BaseModel):
    # the keys of the content shown, in the order the account put them
    order: str


class Board:
    """OVERVIEW: the content registered on the overview, and its page."""

    def __init__(self, pages: Pages, database: Database) -> None:
        self._pages = pages
        self._database = database
        self._items: list[OverviewItem] = []
        self.app: ASGIApp = pages.application(
            [
                Route("/", self._page),
                Route("/arrange", self._arrange, methods=["POST"]),
            ]
        )

    @asynccontextmanager
    async def register(self, item: OverviewItem) -> AsyncIterator[None]:
        if any(registered.key == item.key for registered in self._items):
            raise ValueError(f"overview content {item.key!r} is already registered")
        self._items.append(item)
        try:
            yield
        finally:
            self._items.remove(item)

    async def _positions(self, account: Account) -> dict[str, int]:
        rows = await self._database.read(
            lambda session: session.select(
                Select(
                    table="overview_positions",
                    where=Compare(
                        left=Column(name="account_id"),
                        operator="=",
                        right=Value(value=account.id),
                    ),
                )
            )
        )
        return {cast(str, row["key"]): cast(int, row["position"]) for row in rows}

    def _ordered(
        self, account: Account, positions: dict[str, int]
    ) -> list[OverviewItem]:
        """The content the account may see, in the order it chose; what it
        never placed follows, by its order and then as it was registered."""
        return sorted(
            (
                item
                for item in self._items
                if item.permission is None or account.allows(item.permission)
            ),
            key=lambda item: (
                item.key not in positions,
                positions.get(item.key, 0),
                item.order,
            ),
        )

    async def _page(self, request: Request) -> Response:
        account: Account = request.state.account
        return await self._pages.render(
            request,
            "overview/overview.html",
            items=self._ordered(account, await self._positions(account)),
        )

    async def _arrange(self, request: Request) -> Response:
        account: Account = request.state.account
        try:
            arrangement = _Arrangement.model_validate(dict(await request.form()))
        except ValidationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        positions = await self._positions(account)
        keys = [item.key for item in self._ordered(account, positions)]
        arranged = arrangement.order.split(",")
        if sorted(arranged) != sorted(keys):
            raise HTTPException(status_code=422)
        # what the account cannot see now keeps its place for when it can again
        shown = iter(arranged)
        order = [
            next(shown) if key in keys else key
            for key in [
                *sorted(positions, key=positions.__getitem__),
                *(key for key in keys if key not in positions),
            ]
        ]

        async def save(session: Session) -> None:
            mine = Compare(
                left=Column(name="account_id"),
                operator="=",
                right=Value(value=account.id),
            )
            await session.delete(Delete(table="overview_positions", where=mine))
            await session.insert(
                Insert(
                    table="overview_positions",
                    rows=tuple(
                        {"account_id": account.id, "key": key, "position": place}
                        for place, key in enumerate(order)
                    ),
                )
            )

        await self._database.transaction(save)
        return Response(status_code=204)
