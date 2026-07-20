"""HTTP protocol shared by tournament-page adapters."""

from __future__ import annotations

from typing import Any, Protocol


class WikiHttpClientProtocol(Protocol):
    request_count: int

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any: ...
