"""Small defensive HTTP client restricted to official hosts."""

from __future__ import annotations

import time
from urllib.parse import urlparse

import httpx

from .errors import OfficialHttpError


class OfficialHttpClient:
    def __init__(self, allowed_hosts: tuple[str, ...]) -> None:
        self.allowed_hosts = {host.lower() for host in allowed_hosts}
        self.request_count = 0
        self._client = httpx.Client(
            timeout=httpx.Timeout(20.0, connect=8.0),
            follow_redirects=True,
            headers={"User-Agent": "NETO-official-schedule/0.1"},
        )

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or (parsed.hostname or "").lower() not in self.allowed_hosts:
            raise OfficialHttpError(f'Official adapter rejected non-allowlisted URL "{url}".')

    def _get(
        self,
        url: str,
        *,
        params: dict[str, str] | None,
        headers: dict[str, str] | None,
    ) -> httpx.Response:
        self._validate_url(url)
        last_error: Exception | None = None
        for attempt in range(2):
            self.request_count += 1
            try:
                response = self._client.get(url, params=params, headers=headers)
                self._validate_url(str(response.url))
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt == 0:
                        retry_after = response.headers.get("Retry-After", "0.5")
                        try:
                            delay = min(3.0, max(0.0, float(retry_after)))
                        except ValueError:
                            delay = 0.5
                        time.sleep(delay)
                        continue
                response.raise_for_status()
                return response
            except (httpx.HTTPError, OfficialHttpError) as exc:
                last_error = exc
                if attempt == 0 and isinstance(exc, httpx.TransportError):
                    time.sleep(0.5)
                    continue
                break
        raise OfficialHttpError(
            f"Official HTTP request failed for {url}: {type(last_error).__name__}: {last_error}"
        ) from last_error

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict:
        response = self._get(url, params=params, headers=headers)
        try:
            payload = response.json()
        except ValueError as exc:
            raise OfficialHttpError(f"Official endpoint returned invalid JSON: {url}") from exc
        if not isinstance(payload, dict):
            raise OfficialHttpError(f"Official endpoint returned a non-object JSON payload: {url}")
        return payload

    def get_text(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        return self._get(url, params=params, headers=headers).text

    def close(self) -> None:
        self._client.close()
