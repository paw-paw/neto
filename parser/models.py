"""Domain models shared by the parser and Streamlit UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


OUTPUT_COLUMNS: tuple[str, ...] = (
    "date_original",
    "time_original",
    "timezone",
    "start_time_utc",
    "team_a",
    "team_b",
    "stage",
    "bo",
    "match_label",
    "row_status",
)


@dataclass(frozen=True)
class ParserKey:
    parser_key_id: str
    key_name: str
    tournament_name: str
    base_timezone: str
    target_sheet: str
    layout_type: str
    header_row: int
    data_start_row: int
    field_mappings: dict[str, str | None]
    forward_fill_rules: dict[str, bool]
    schema_version: str = "neto.parser_key.v0"
    source_file: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def select_label(self) -> str:
        return f"{self.key_name} ({self.parser_key_id})"

    @property
    def status(self) -> str:
        value = self.raw_data.get("status")
        return value if isinstance(value, str) and value else "enabled"


@dataclass(frozen=True)
class ParserKeyLoadError:
    file_name: str
    message: str


@dataclass(frozen=True)
class ParserKeyCatalog:
    keys: list[ParserKey]
    errors: list[ParserKeyLoadError]


@dataclass(frozen=True)
class ValidationIssue:
    source_row: int | None
    severity: str
    code: str
    message: str
    affected_field: str | None = None
    source_sheet: str | None = None
    record_set_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_row": self.source_row,
            "source_sheet": self.source_sheet or "",
            "record_set_id": self.record_set_id or "",
            "severity": self.severity,
            "code": self.code,
            "affected_field": self.affected_field or "",
            "message": self.message,
        }


@dataclass(frozen=True)
class IngestionMetadata:
    method: str
    source_id: str
    source_label: str
    source_url: str
    strategy: str
    fetched_at_utc: str
    request_count: int = 0
    legitimate_empty: bool = False
    range_start: str | None = None
    range_end: str | None = None
    range_timezone: str | None = None


@dataclass(frozen=True)
class OfficialMatchMetadata:
    source_id: str
    match_id: str
    source_url: str
    competition_id: str = ""
    competition_name: str = ""
    region: str = ""
    match_state: str = "unknown"
    raw_state: str = ""
    time_is_tbd: bool = False


@dataclass
class ParsedMatch:
    source_row: int
    date_original: str
    time_original: str
    timezone: str
    start_time_utc: str
    team_a: str
    team_b: str
    stage: str
    bo: str
    match_label: str
    row_status: str = "valid"
    source_sheet: str | None = None
    record_set_id: str | None = None
    tile_id: str | None = None
    tile_origin: str | None = None
    field_provenance: dict[str, Any] = field(default_factory=dict, repr=False)
    official: OfficialMatchMetadata | None = None

    def as_output_dict(self) -> dict[str, str]:
        return {column: getattr(self, column) for column in OUTPUT_COLUMNS}


@dataclass
class ParseResult:
    status: str
    matches: list[ParsedMatch] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)
    notice: str | None = None
    technical_error: str | None = None
    ingestion: IngestionMetadata | None = None

    @property
    def exportable(self) -> bool:
        return self.status in {"parsed", "parsed_with_warnings"}

    @property
    def total_matches(self) -> int:
        return len(self.matches)

    @property
    def valid_matches(self) -> int:
        return sum(match.row_status == "valid" for match in self.matches)

    @property
    def warning_matches(self) -> int:
        return sum(match.row_status == "warning" for match in self.matches)

    @property
    def invalid_matches(self) -> int:
        return sum(match.row_status == "invalid" for match in self.matches)

    @property
    def warnings_count(self) -> int:
        return sum(issue.severity == "warning" for issue in self.issues)

    @property
    def errors_count(self) -> int:
        return sum(issue.severity == "blocking_error" for issue in self.issues)

    @property
    def counts(self) -> dict[str, int | str]:
        return {
            "total_matches": self.total_matches,
            "valid_matches": self.valid_matches,
            "warning_matches": self.warning_matches,
            "invalid_matches": self.invalid_matches,
            "warnings_count": self.warnings_count,
            "errors_count": self.errors_count,
            "parse_status": self.status,
        }

    @classmethod
    def failed(
        cls,
        message: str,
        *,
        notice: str | None = None,
        ingestion: IngestionMetadata | None = None,
    ) -> "ParseResult":
        return cls(
            status="failed",
            notice=notice,
            technical_error=message,
            ingestion=ingestion,
        )
