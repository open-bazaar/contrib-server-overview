"""What modules hold the overview to: where they put what is worth a glance."""

from __future__ import annotations

from typing import Protocol
lazy from contextlib import AbstractAsyncContextManager

from bazaar_core import ServiceKey
from pydantic import BaseModel, ConfigDict, Field

# one segment of an address, as the server's own registrations take
NAME = r"^[a-z][a-z0-9-]*$"


class OverviewItem(BaseModel):
    """Content of the overview, loaded in an iframe, for the accounts holding
    its permission point; an account that never arranged the overview sees
    the content by its order, and as it was registered where that ties."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(pattern=NAME)
    title: str
    src: str
    permission: str | None = None
    order: int = 0
    # how many of the overview's three columns it takes; a phone has one
    columns: int = Field(default=1, ge=1, le=3)
    # how many rows it takes, those beside it stacking down its side
    rows: int = Field(default=1, ge=1, le=2)


class Overview(Protocol):
    def register(self, item: OverviewItem) -> AbstractAsyncContextManager[None]:
        """Show the content on the overview while open."""
        ...


OVERVIEW = ServiceKey[Overview]("server.overview")
