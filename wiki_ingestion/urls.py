"""Strict tournament-page URL routing independent of the Streamlit UI."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote, urlparse, urlunparse

from .errors import TournamentUrlError


LEAGUEPEDIA_HOSTS = {"lol.fandom.com", "leaguepedia.com", "www.leaguepedia.com"}
UNSAFE_TITLE = re.compile(r"[\x00-\x1f\x7f\[\]{}|\\;]")


@dataclass(frozen=True)
class TournamentPage:
    provider_id: str
    game_id: str
    game_label: str
    title: str
    url: str
    api_url: str

    @property
    def source_id(self) -> str:
        return f"{self.provider_id}_{self.game_id}" if self.game_id else self.provider_id


def _title(value: str) -> str:
    normalized = " ".join(unquote(value).replace("_", " ").split())
    if not normalized or len(normalized) > 500 or UNSAFE_TITLE.search(normalized):
        raise TournamentUrlError("The URL does not contain a safe tournament page title.")
    return normalized


def _clean_source_url(parsed) -> str:
    return urlunparse(("https", parsed.netloc.lower(), parsed.path, "", "", ""))


def parse_tournament_url(value: str) -> TournamentPage:
    text = str(value or "").strip()
    if not text:
        raise TournamentUrlError("Enter a tournament-page URL.")
    if len(text) > 2_000:
        raise TournamentUrlError("The tournament-page URL is too long.")
    parsed = urlparse(text)
    host = (parsed.hostname or "").casefold()
    try:
        port = parsed.port
    except ValueError as exc:
        raise TournamentUrlError("Tournament URL contains an invalid port.") from exc
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username
        or parsed.password
        or port not in {None, 443}
    ):
        raise TournamentUrlError("Tournament URLs must be public HTTPS URLs without credentials.")

    parts = [part for part in parsed.path.split("/") if part]
    if host in LEAGUEPEDIA_HOSTS:
        if len(parts) < 2 or parts[0].casefold() != "wiki":
            raise TournamentUrlError("Leaguepedia URLs must use the /wiki/<tournament> page form.")
        return TournamentPage(
            provider_id="leaguepedia",
            game_id="league_of_legends",
            game_label="League of Legends",
            title=_title("/".join(parts[1:])),
            url=_clean_source_url(parsed),
            api_url="https://lol.fandom.com/api.php",
        )

    raise TournamentUrlError(
        "Unsupported tournament URL. This preliminary release accepts only Leaguepedia / LoL Fandom pages."
    )
