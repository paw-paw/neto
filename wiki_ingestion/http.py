"""Connection-reusing HTTP client restricted to a provider's API host."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from .errors import WikiApiError


class WikiHttpClient:
    def __init__(self, allowed_hosts: tuple[str, ...], user_agent: str) -> None:
        self.allowed_hosts = {host.casefold() for host in allowed_hosts}
        self.request_count = 0
        self._client = httpx.Client(
            timeout=httpx.Timeout(25.0, connect=8.0),
            follow_redirects=True,
            headers={
                "User-Agent": user_agent,
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
            },
        )

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or (parsed.hostname or "").casefold() not in self.allowed_hosts:
            raise WikiApiError(f'Wiki adapter rejected non-allowlisted API URL "{url}".')

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        self._validate_url(url)
        self.request_count += 1
        try:
            response = self._client.get(url, params=params, headers=headers)
            self._validate_url(str(response.url))
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise WikiApiError(
                f"Wiki API request failed for {url}: {type(exc).__name__}: {exc}"
            ) from exc

    def close(self) -> None:
        self._client.close()
