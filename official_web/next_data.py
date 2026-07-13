"""Extraction of JSON embedded in Next.js script#__NEXT_DATA__."""

from __future__ import annotations

import json
from html.parser import HTMLParser

from .errors import OfficialSchemaError
from .normalization import mapping


class _NextDataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.capture = False
        self.value: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "script" and attributes.get("id") == "__NEXT_DATA__":
            self.capture = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self.capture:
            self.capture = False

    def handle_data(self, data: str) -> None:
        if self.capture:
            self.value.append(data)


def parse_next_data(html: str, source_label: str) -> dict:
    parser = _NextDataParser()
    parser.feed(html)
    if not parser.value:
        raise OfficialSchemaError(
            f"{source_label} response is missing script#__NEXT_DATA__."
        )
    try:
        payload = json.loads("".join(parser.value))
    except json.JSONDecodeError as exc:
        raise OfficialSchemaError(
            f"{source_label} __NEXT_DATA__ is not valid JSON."
        ) from exc
    return mapping(payload, "__NEXT_DATA__")
