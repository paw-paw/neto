"""NETO v0 Streamlit application."""

from __future__ import annotations

import base64
import hashlib
import html
import re
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import pandas as pd
import streamlit as st

from official_web import (
    OfficialScheduleRequest,
    fetch_official_schedule,
    list_official_sources,
)
from parser import (
    fingerprint_workbook,
    load_parser_keys,
    normalize_parser_key,
    parse_workbook,
    rank_parser_keys,
    validate_parser_key_upload,
)
from parser.export import issues_dataframe
from parser.models import ParseResult, ParserKey
from parser.registration import ParserKeyRegistrationError
from parser.presentation import (
    canonical_view_dataframe,
    presentation_dataframe,
)
from parser.suggestions import ParserKeySuggestion, WorkbookFingerprintError
from parser.ui_exports import canonical_csv_bytes, markdown_bytes, pdf_bytes, xlsx_bytes
from wiki_ingestion import fetch_tournament_schedule, parse_tournament_url
from wiki_ingestion.errors import TournamentUrlError


APP_ROOT = Path(__file__).resolve().parent
PARSER_KEYS_DIR = APP_ROOT / "parser_keys"
ASSETS_DIR = APP_ROOT / "assets"
LOGO_PATH = ASSETS_DIR / "neto-logo.png"
THEME_CSS_PATH = ASSETS_DIR / "neto-theme.css"
FONT_ASSETS = {
    "__JETBRAINS_MONO_REGULAR__": ASSETS_DIR
    / "fonts"
    / "JetBrainsMono-Regular.woff2",
    "__JETBRAINS_MONO_MEDIUM__": ASSETS_DIR
    / "fonts"
    / "JetBrainsMono-Medium.woff2",
    "__DM_SANS_REGULAR_MEDIUM__": ASSETS_DIR
    / "fonts"
    / "DMSans-Regular-Medium.woff2",
}
PARSERKEY_CREATOR_URL = (
    "https://chatgpt.com/g/g-6a579fdaa2948191b59a59f34f8f688d-"
    "neto-parserkey-creator"
)


def _data_uri(path: Path, mime_type: str) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


@lru_cache(maxsize=1)
def _load_app_styles() -> str:
    """Load the project theme and embed local fonts for offline deployments."""

    stylesheet = THEME_CSS_PATH.read_text(encoding="utf-8")
    for placeholder, font_path in FONT_ASSETS.items():
        stylesheet = stylesheet.replace(
            placeholder, _data_uri(font_path, "font/woff2")
        )
    return f"<style>{stylesheet}</style>"


@lru_cache(maxsize=1)
def _logo_data_uri() -> str:
    return _data_uri(LOGO_PATH, "image/png")


def _render_brand_header() -> None:
    st.markdown(
        f"""
        <header class="neto-brand" aria-label="NETO application header">
            <img
                class="neto-brand__logo"
                src="{_logo_data_uri()}"
                alt="NETO mascot"
                width="112"
                height="112"
            />
            <div class="neto-brand__copy">
                <h1 class="neto-brand__title">NETO v0</h1>
                <p class="neto-brand__subtitle">
                    Normalized Esports Tournament Output — deterministic schedule parser
                </p>
            </div>
        </header>
        """,
        unsafe_allow_html=True,
    )


def _input_signature(
    file_bytes: bytes | None,
    parser_key_id: str | None,
    extra: str = "",
) -> str:
    digest = hashlib.sha256()
    digest.update(file_bytes or b"")
    digest.update(b"\0")
    digest.update((parser_key_id or "").encode("utf-8"))
    digest.update(b"\0")
    digest.update(extra.encode("utf-8"))
    return digest.hexdigest()


class _OfficialFetchFailed(RuntimeError):
    def __init__(self, result: ParseResult) -> None:
        super().__init__(result.technical_error or "Official schedule fetch failed.")
        self.result = result


class _WikiFetchFailed(RuntimeError):
    def __init__(self, result: ParseResult) -> None:
        super().__init__(result.technical_error or "Tournament schedule fetch failed.")
        self.result = result


@st.cache_data(ttl=300, max_entries=64, show_spinner=False)
def _cached_fetch_official(
    source_id: str,
    start_date_iso: str,
    end_date_iso: str,
    range_timezone: str,
) -> ParseResult:
    result = fetch_official_schedule(
        OfficialScheduleRequest(
            source_id=source_id,
            start_date=date.fromisoformat(start_date_iso),
            end_date=date.fromisoformat(end_date_iso),
            range_timezone=range_timezone,
        )
    )
    if result.status == "failed":
        raise _OfficialFetchFailed(result)
    return result


@st.cache_data(ttl=3600, max_entries=64, show_spinner=False)
def _cached_fetch_tournament(
    url: str,
) -> ParseResult:
    result = fetch_tournament_schedule(url)
    if result.status == "failed":
        raise _WikiFetchFailed(result)
    return result


@st.cache_data(max_entries=16, show_spinner=False)
def _cached_workbook_fingerprint(file_bytes: bytes, file_name: str):
    return fingerprint_workbook(file_bytes, file_name)


def _session_parser_keys() -> list[ParserKey]:
    registered = st.session_state.get("neto_registered_parser_keys", {})
    if not isinstance(registered, dict):
        return []
    keys: list[ParserKey] = []
    for parser_key_id, raw_data in registered.items():
        if not isinstance(raw_data, dict):
            continue
        try:
            key = normalize_parser_key(raw_data, source_file=f"session:{parser_key_id}")
        except ValueError:
            continue
        keys.append(key)
    return keys


def _download_filename(uploaded_name: str, parser_key_id: str, extension: str) -> str:
    stem = Path(uploaded_name).stem
    combined = f"neto_{stem}_{parser_key_id}"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", combined).strip("._")
    return f"{safe or 'neto_output'}.{extension}"


def _preview_style(dataframe: pd.DataFrame) -> pd.io.formats.style.Styler:
    colors = {
        "valid": (
            "background-color: rgba(0, 188, 125, 0.16); "
            "color: #c9ffed; font-weight: 500"
        ),
        "warning": (
            "background-color: rgba(240, 177, 0, 0.17); "
            "color: #fff3bf; font-weight: 500"
        ),
        "invalid": (
            "background-color: rgba(255, 32, 86, 0.17); "
            "color: #ffd3df; font-weight: 500"
        ),
    }

    def style_status(value: object) -> str:
        return colors.get(str(value), "")

    return dataframe.style.map(style_status, subset=["row_status"])


def _presentation_dataframe(
    result: ParseResult,
    *,
    descending: bool = True,
    search: str = "",
    stages: list[str] | None = None,
    bos: list[str] | None = None,
    statuses: list[str] | None = None,
    competitions: list[str] | None = None,
    match_states: list[str] | None = None,
    date_format: str = "DD-MM-YYYY",
    display_timezone: str | None = None,
) -> pd.DataFrame:
    canonical = canonical_view_dataframe(
        result,
        descending=descending,
        search=search,
        stages=stages,
        bos=bos,
        statuses=statuses,
        competitions=competitions,
        match_states=match_states,
    )
    return presentation_dataframe(
        canonical,
        date_format=date_format,
        display_timezone=display_timezone,
    )


def _preview_column_config() -> dict[str, st.column_config.Column]:
    return {
        "date": st.column_config.TextColumn("Date", width="small"),
        "time": st.column_config.TextColumn("Time", width="small"),
        "team_a": st.column_config.TextColumn("Team A", width="medium"),
        "team_b": st.column_config.TextColumn("Team B", width="medium"),
        "bo": st.column_config.TextColumn("BO", width="small"),
        "stage": st.column_config.TextColumn("Stage", width="medium"),
        "match_label": st.column_config.TextColumn("Match", width="medium"),
        "timezone": st.column_config.TextColumn("Timezone", width="medium"),
        "start_time_utc": st.column_config.TextColumn("Start time UTC", width="medium"),
        "row_status": st.column_config.TextColumn("Status", width="small"),
    }


def _issues_summary(result: ParseResult) -> pd.DataFrame:
    details = issues_dataframe(result)
    if details.empty:
        return pd.DataFrame(columns=["severity", "code", "count"])
    summary = (
        details.groupby(["severity", "code"], sort=False)
        .size()
        .reset_index(name="count")
    )
    priority = {"blocking_error": 0, "warning": 1}
    summary["_priority"] = summary["severity"].map(priority).fillna(2)
    return summary.sort_values(
        ["_priority", "count", "code"],
        ascending=[True, False, True],
        kind="stable",
    ).drop(columns="_priority")


def _render_key_summary(parser_key: ParserKey) -> None:
    st.markdown(f"**{parser_key.key_name}**")
    st.caption(f"Tournament · {parser_key.tournament_name}")
    st.caption(f"Timezone · {parser_key.base_timezone or '(missing)'}")
    st.caption(f"Sheet · {parser_key.target_sheet}")
    st.caption(f"Layout · {parser_key.layout_type}")


def _render_suggestions(suggestions: list[ParserKeySuggestion]) -> None:
    st.markdown("**Structural matches**")
    if not suggestions:
        st.info("No ParserKeys are available to rank.")
        return
    strongest = suggestions[0]
    if strongest.confidence == "Low":
        st.warning(
            "No confident ParserKey match was found. Review the best available candidates manually."
        )
    else:
        st.success(
            f"Recommended · {strongest.parser_key.key_name} · "
            f"{strongest.confidence} confidence"
        )
    for index, suggestion in enumerate(suggestions, start=1):
        label = (
            "Recommended"
            if index == 1 and suggestion.confidence != "Low"
            else ("Best available" if index == 1 else f"Candidate {index}")
        )
        st.markdown(
            f"**{label}:** {suggestion.parser_key.key_name} "
            f"· {suggestion.confidence} ({suggestion.score}/100)"
        )
        st.caption(" · ".join(suggestion.reasons) or "No strong structural signals.")


def _render_registration_notice() -> None:
    notice = st.session_state.pop("neto_registration_notice", None)
    if not isinstance(notice, dict):
        return
    message = str(notice.get("message") or "")
    st.success(message)


def _render_parser_key_registration(existing_keys: list[ParserKey]) -> None:
    with st.expander("Create or upload a ParserKey"):
        st.caption(
            "Upload the XLSX to the NETO ParserKey Creator, download its JSON, "
            "then return here and upload that ParserKey."
        )
        st.link_button(
            "Open NETO ParserKey Creator",
            PARSERKEY_CREATOR_URL,
            width="stretch",
        )
        parser_key_file = st.file_uploader(
            "Upload ParserKey JSON",
            type=["json"],
            accept_multiple_files=False,
            max_upload_size=1,
            key="parser_key_upload",
        )
        st.caption(
            "Temporary registration only: the key is available in this browser session "
            "and is discarded when the session or app restarts."
        )

        if st.button(
            "Validate and register",
            key="register_parser_key",
            disabled=parser_key_file is None,
            width="stretch",
        ):
            try:
                validated = validate_parser_key_upload(
                    parser_key_file.getvalue(),
                    source_file=parser_key_file.name,
                    existing_keys=existing_keys,
                )
                registered = dict(
                    st.session_state.get("neto_registered_parser_keys", {})
                )
                registered[validated.parser_key.parser_key_id] = validated.parser_key.raw_data
                st.session_state["neto_registered_parser_keys"] = registered
                st.session_state["neto_registration_notice"] = {
                    "message": (
                        f"{validated.parser_key.key_name} validated and available "
                        "for this session."
                    ),
                }
                st.rerun()
            except ParserKeyRegistrationError as exc:
                st.error(str(exc))


def _render_status(result: ParseResult) -> None:
    messages = {
        "parsed": (st.success, "Parse completed successfully."),
        "parsed_with_warnings": (
            st.warning,
            "Parse completed with warnings. Review the validation issues before export.",
        ),
        "blocked": (
            st.error,
            "Parse blocked. Fix critical row errors before exporting.",
        ),
        "failed": (st.error, "Parse failed. Review the error and inputs."),
    }
    renderer, message = messages.get(result.status, (st.info, result.status))
    if result.ingestion and result.ingestion.legitimate_empty:
        renderer, message = st.info, (
            "No schedule was found for this tournament page."
            if result.ingestion.method == "wiki_tournament"
            else "The official source returned no matches for this range."
        )
    renderer(message)

    metrics = (
        ("Matches", result.total_matches),
        ("Valid", result.valid_matches),
        ("Warning rows", result.warning_matches),
        ("Invalid", result.invalid_matches),
        ("Issues", result.warnings_count + result.errors_count),
    )
    cards = "".join(
        (
            '<div class="neto-metric-card">'
            f'<span class="neto-metric-label">{label}</span>'
            f'<span class="neto-metric-value">{value}</span>'
            "</div>"
        )
        for label, value in metrics
    )
    st.markdown(f'<div class="neto-metric-grid">{cards}</div>', unsafe_allow_html=True)

    if result.notice:
        st.caption(f"ℹ️ {result.notice}")
    if result.ingestion:
        ingestion = result.ingestion
        st.markdown(
            f"[{ingestion.source_label}]({ingestion.source_url}) · "
            f"`{ingestion.strategy}`"
        )
        st.caption(
            f"Fetched {ingestion.fetched_at_utc} · {ingestion.request_count} API request(s)"
        )
        state_counts: dict[str, int] = {}
        for match in result.matches:
            if match.official:
                state = match.official.match_state
                state_counts[state] = state_counts.get(state, 0) + 1
        if state_counts:
            st.caption(
                "Match states · "
                + " · ".join(
                    f"{state}: {count}" for state, count in sorted(state_counts.items())
                )
            )
    if result.technical_error:
        st.error(result.technical_error)


def _render_validation_issues(result: ParseResult | None) -> None:
    st.subheader("Validation issues")
    if result is None:
        st.caption("Issues will appear after parsing.")
        return
    if not result.issues:
        st.success("No status-affecting issues.")
        return

    summary = _issues_summary(result)
    st.dataframe(
        summary,
        hide_index=True,
        width="stretch",
        height=min(245, 38 + 35 * len(summary)),
        column_config={
            "severity": st.column_config.TextColumn("Severity", width="small"),
            "code": st.column_config.TextColumn("Code", width="medium"),
            "count": st.column_config.NumberColumn("#", width="small"),
        },
        key="validation_summary",
    )

    with st.expander(f"Row details ({len(result.issues)})"):
        details = issues_dataframe(result).copy()
        details.insert(
            0,
            "source",
            details.apply(
                lambda row: (
                    f"{row['source_sheet']}!{int(row['source_row'])}"
                    if row["source_sheet"] and pd.notna(row["source_row"])
                    else (str(int(row["source_row"])) if pd.notna(row["source_row"]) else "—")
                ),
                axis=1,
            ),
        )
        st.dataframe(
            details[["source", "severity", "code", "affected_field", "message"]],
            hide_index=True,
            width="stretch",
            height=300,
            key="validation_issues",
        )


def _render_export(
    result: ParseResult | None,
    uploaded_file: object | None,
    selected_key: ParserKey | None,
    canonical: pd.DataFrame | None,
    presentation: pd.DataFrame | None,
) -> None:
    st.subheader("5. Export")
    export_enabled = (
        result is not None
        and result.exportable
        and canonical is not None
        and presentation is not None
    )
    if result and result.ingestion:
        ingestion = result.ingestion
        if ingestion.method == "wiki_tournament":
            base_args = (f"{ingestion.source_id}_tournament.xlsx", "wiki")
        else:
            base_args = (
                f"{ingestion.source_id}_{ingestion.range_start}_{ingestion.range_end}.xlsx",
                "official",
            )
    elif uploaded_file is not None and selected_key is not None:
        base_args = (uploaded_file.name, selected_key.parser_key_id)
    else:
        base_args = ("output.xlsx", "matches")
    payloads = {
        "csv": canonical_csv_bytes(canonical) if export_enabled else b"",
        "md": markdown_bytes(presentation) if export_enabled else b"",
        "xlsx": xlsx_bytes(presentation) if export_enabled else b"",
        "pdf": pdf_bytes(presentation) if export_enabled else b"",
    }

    if export_enabled:
        st.success(f"{len(canonical)} filtered matches ready")
        if result and result.status == "parsed_with_warnings":
            st.caption("Warnings are included and do not block export.")
    elif result is None:
        st.caption("Parse a schedule to enable export.")
    else:
        st.error("Export blocked")

    first_row = st.columns(2, gap="small")
    second_row = st.columns(2, gap="small")
    formats = (
        (first_row[0], "CSV", "csv", "text/csv"),
        (first_row[1], "Markdown", "md", "text/markdown"),
        (
            second_row[0],
            "XLSX",
            "xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        (second_row[1], "PDF", "pdf", "application/pdf"),
    )
    for column, label, extension, mime in formats:
        with column:
            st.download_button(
                label,
                data=payloads[extension],
                file_name=_download_filename(*base_args, extension),
                mime=mime,
                disabled=not export_enabled,
                width="stretch",
                key=f"download_{extension}",
            )
    st.caption("Current filtered view · CSV keeps the canonical NETO schema")


def _non_empty_options(dataframe: pd.DataFrame, column: str) -> list[str]:
    values = dataframe[column].fillna("").astype(str).str.strip()
    return sorted(value for value in values.unique().tolist() if value)


def _table_context(
    *,
    visible: int,
    total: int,
    schedule_timezone: str,
) -> None:
    items = (
        ("Visible matches", f"{visible} / {total}"),
        ("Schedule timezone", schedule_timezone or "—"),
    )
    cards = "".join(
        (
            '<div class="neto-context-card">'
            f'<span class="neto-context-label">{html.escape(label)}</span>'
            f'<span class="neto-context-value" title="{html.escape(value)}">'
            f"{html.escape(value)}</span></div>"
        )
        for label, value in items
    )
    st.markdown(f'<div class="neto-table-context">{cards}</div>', unsafe_allow_html=True)


def _render_match_table(
    result: ParseResult | None,
    selected_key: ParserKey | None,
) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    st.subheader("6. Match Table")
    if result is None:
        st.caption("Run the parser to inspect and export normalized matches.")
        return None, None
    if not result.matches:
        st.caption("No match rows are available for this parse.")
        empty = canonical_view_dataframe(result)
        return empty, presentation_dataframe(empty)

    all_rows = canonical_view_dataframe(result)
    has_source_metadata = bool(
        result.ingestion
        and result.ingestion.method in {"official_web", "wiki_tournament"}
    )
    schedule_timezone = (
        "UTC"
        if has_source_metadata
        else (selected_key.base_timezone if selected_key else "UTC")
    )
    control_columns = st.columns([1.2, 1.8], gap="small")
    with control_columns[0]:
        sort_order = st.segmented_control(
            "Sort by start time",
            options=["↑ Ascending", "↓ Descending"],
            default="↓ Descending",
            key="preview_sort_order",
            width="stretch",
        )
    with control_columns[1]:
        search = st.text_input(
            "Search matches",
            placeholder="Team, stage, or match label",
            key="preview_search",
        )

    filter_columns = st.columns(4 if has_source_metadata else 2, gap="small")
    with filter_columns[0]:
        stages = st.multiselect(
            "Stage",
            options=_non_empty_options(all_rows, "stage"),
            placeholder="All stages",
            key="preview_stage",
        )
    with filter_columns[1]:
        statuses = st.multiselect(
            "Row status",
            options=_non_empty_options(all_rows, "row_status"),
            placeholder="All statuses",
            key="preview_status",
        )
    competitions: list[str] = []
    match_states: list[str] = []
    if has_source_metadata:
        with filter_columns[2]:
            competitions = st.multiselect(
                "Competition",
                options=_non_empty_options(all_rows, "_competition"),
                placeholder="All competitions",
                key="preview_competition",
            )
        with filter_columns[3]:
            match_states = st.multiselect(
                "Match state",
                options=_non_empty_options(all_rows, "_match_state"),
                placeholder="All states",
                key="preview_match_state",
            )

    canonical = canonical_view_dataframe(
        result,
        descending=sort_order == "↓ Descending",
        search=search,
        stages=stages,
        statuses=statuses,
        competitions=competitions,
        match_states=match_states,
    )
    presentation = presentation_dataframe(canonical)
    _table_context(
        visible=len(canonical),
        total=len(result.matches),
        schedule_timezone=schedule_timezone,
    )

    if canonical.empty:
        st.info("No matches satisfy the current filters.")
    st.dataframe(
        _preview_style(presentation),
        hide_index=True,
        width="stretch",
        height=560,
        column_config=_preview_column_config(),
        key="matches_preview",
    )
    if has_source_metadata:
        with st.expander(f"Source match metadata ({len(canonical)})"):
            metadata = canonical[
                [
                    "_official_match_id",
                    "_competition",
                    "_region",
                    "_match_state",
                    "_source_url",
                ]
            ].rename(
                columns={
                    "_official_match_id": "match_id",
                    "_competition": "competition",
                    "_region": "region",
                    "_match_state": "match_state",
                    "_source_url": "source_url",
                }
            )
            st.dataframe(
                metadata,
                hide_index=True,
                width="stretch",
                column_config={
                    "source_url": st.column_config.LinkColumn("Source page")
                },
                key="official_match_metadata",
            )
    return canonical, presentation


def main() -> None:
    st.set_page_config(page_title="NETO v0", page_icon=str(LOGO_PATH), layout="wide")
    st.markdown(_load_app_styles(), unsafe_allow_html=True)
    _render_brand_header()
    _render_registration_notice()

    ingestion_mode = st.segmented_control(
        "Ingestion method",
        options=["XLSX Upload", "Official Website", "Tournament Page"],
        default="XLSX Upload",
        key="ingestion_mode",
        width="content",
    )

    catalog = load_parser_keys(PARSER_KEYS_DIR)
    repository_ids = {key.parser_key_id for key in catalog.keys}
    session_keys = [
        key for key in _session_parser_keys() if key.parser_key_id not in repository_ids
    ]
    available_keys = sorted(
        [*catalog.keys, *session_keys],
        key=lambda key: (key.key_name.casefold(), key.parser_key_id.casefold()),
    )
    key_by_id = {key.parser_key_id: key for key in available_keys}
    official_sources = list_official_sources()
    official_by_id = {source.source_id: source for source in official_sources}

    uploaded_file = None
    file_bytes: bytes | None = None
    selected_key_id: str | None = None
    selected_key: ParserKey | None = None
    selected_source_id: str | None = None
    selected_source = None
    official_start: date | None = None
    official_end: date | None = None
    range_timezone = "America/Lima"
    official_range_valid = False
    parser_key_confirmed = False
    tournament_url = ""
    tournament_page = None
    tournament_ready = False

    with st.container(key="top_workflow"):
        first_column, second_column, run_column = st.columns(
            [1.15, 1.15, 0.7], gap="medium", vertical_alignment="top", border=True
        )

        if ingestion_mode == "XLSX Upload":
            with first_column:
                st.subheader("1. Upload XLSX")
                uploaded_file = st.file_uploader(
                    "Upload an esports schedule",
                    type=["xlsx"],
                    accept_multiple_files=False,
                    max_upload_size=25,
                    key="schedule_upload",
                )
                file_bytes = (
                    uploaded_file.getvalue() if uploaded_file is not None else None
                )
                if uploaded_file is None:
                    st.caption("No file uploaded.")
                else:
                    st.success(f"Loaded · {uploaded_file.name}")
                _render_parser_key_registration(available_keys)

            with second_column:
                st.subheader("2. Select ParserKey")
                suggestions: list[ParserKeySuggestion] = []
                if file_bytes is not None:
                    try:
                        fingerprint = _cached_workbook_fingerprint(
                            file_bytes, uploaded_file.name
                        )
                        suggestions = rank_parser_keys(
                            fingerprint, available_keys, limit=3
                        )
                        _render_suggestions(suggestions)
                    except WorkbookFingerprintError as exc:
                        st.warning(str(exc))

                recommended_id = (
                    suggestions[0].parser_key.parser_key_id
                    if suggestions and suggestions[0].confidence != "Low"
                    else None
                )
                workbook_signature = hashlib.sha256(file_bytes or b"").hexdigest()
                if (
                    st.session_state.get("neto_suggestion_workbook_signature")
                    != workbook_signature
                ):
                    st.session_state["neto_suggestion_workbook_signature"] = (
                        workbook_signature
                    )
                    if recommended_id:
                        st.session_state["parser_key_select"] = recommended_id
                    else:
                        st.session_state.pop("parser_key_select", None)
                    st.session_state["parser_key_confirm"] = False
                    st.session_state.pop("neto_confirmation_key", None)
                selected_key_id = st.selectbox(
                    "ParserKey",
                    options=list(key_by_id),
                    index=None,
                    placeholder="Select a parser key",
                    format_func=lambda key_id: key_by_id[key_id].select_label,
                    disabled=not key_by_id,
                    key="parser_key_select",
                    label_visibility="collapsed",
                )
                selected_key = (
                    key_by_id.get(selected_key_id) if selected_key_id else None
                )
                if not key_by_id:
                    st.error("No valid ParserKeys are available in parser_keys/.")
                if catalog.errors:
                    with st.expander(
                        "ParserKey loading errors", expanded=not key_by_id
                    ):
                        for error in catalog.errors:
                            st.error(f"{error.file_name}: {error.message}")
                if selected_key is not None:
                    _render_key_summary(selected_key)
                else:
                    st.caption("Choose the configuration matching this workbook.")
                if st.session_state.get("neto_confirmation_key") != selected_key_id:
                    st.session_state["neto_confirmation_key"] = selected_key_id
                    st.session_state["parser_key_confirm"] = False
                parser_key_confirmed = st.checkbox(
                    "I confirm this ParserKey for the uploaded workbook",
                    disabled=selected_key is None,
                    key="parser_key_confirm",
                )
        elif ingestion_mode == "Official Website":
            with first_column:
                st.subheader("1. Official Source")
                selected_source_id = st.selectbox(
                    "Official esports website",
                    options=[source.source_id for source in official_sources],
                    format_func=lambda source_id: official_by_id[source_id].label,
                    key="official_source_select",
                )
                selected_source = official_by_id.get(selected_source_id)
                if selected_source:
                    st.markdown(
                        f"[{selected_source.label}]({selected_source.source_url})"
                    )
                    st.caption(f"Strategy · {selected_source.strategy}")
                    st.caption("Official responses only · cached for 5 minutes")

            with second_column:
                st.subheader("2. Date Range")
                today = date.today()
                selected_dates = st.date_input(
                    "Inclusive date range",
                    value=(today, today + timedelta(days=14)),
                    key="official_date_range",
                )
                range_timezone = st.selectbox(
                    "Range timezone",
                    options=[
                        "America/Lima",
                        "UTC",
                        "Europe/Berlin",
                        "Europe/Madrid",
                        "Asia/Shanghai",
                        "America/Sao_Paulo",
                    ],
                    key="official_range_timezone",
                )
                if isinstance(selected_dates, (tuple, list)) and len(selected_dates) == 2:
                    official_start, official_end = selected_dates
                    range_days = (official_end - official_start).days + 1
                    official_range_valid = 1 <= range_days <= 90
                    if official_range_valid:
                        st.caption(f"{range_days} day(s) · maximum 90")
                    else:
                        st.error("Choose an inclusive range of 1 to 90 days.")
                else:
                    st.caption("Select both a start and end date.")
        else:
            with first_column:
                st.subheader("1. Tournament Page")
                tournament_url = st.text_input(
                    "Tournament-page URL",
                    placeholder="https://lol.fandom.com/wiki/...",
                    key="tournament_page_url",
                ).strip()
                if tournament_url:
                    try:
                        tournament_page = parse_tournament_url(tournament_url)
                    except TournamentUrlError as exc:
                        st.error(str(exc))
                    else:
                        st.success(
                            f"Supported · Leaguepedia · {tournament_page.game_label}"
                        )
                        st.caption(f"Page · {tournament_page.title}")
                        tournament_ready = True

            with second_column:
                st.subheader("2. Provider Details")
                st.markdown("- Leaguepedia / LoL Fandom")
                st.caption(
                    "All published matches are requested · successful responses cached for 1 hour"
                )
                st.caption(
                    "Preliminary release: Liquipedia ingestion is intentionally disabled."
                )

    signature_extra = ingestion_mode
    if ingestion_mode == "Official Website":
        signature_extra = "|".join(
            (
                ingestion_mode,
                selected_source_id or "",
                official_start.isoformat() if official_start else "",
                official_end.isoformat() if official_end else "",
                range_timezone,
            )
        )
    elif ingestion_mode == "Tournament Page":
        signature_extra = f"{ingestion_mode}|{tournament_url}"
    signature = _input_signature(file_bytes, selected_key_id, signature_extra)
    if st.session_state.get("neto_input_signature") != signature:
        st.session_state["neto_input_signature"] = signature
        st.session_state.pop("neto_parse_result", None)
        for widget_key in (
            "preview_sort_order",
            "preview_search",
            "preview_stage",
            "preview_status",
            "preview_competition",
            "preview_match_state",
        ):
            st.session_state.pop(widget_key, None)

    with run_column:
        is_official_mode = ingestion_mode == "Official Website"
        is_tournament_mode = ingestion_mode == "Tournament Page"
        st.subheader(
            "3. Fetch Schedule"
            if is_official_mode or is_tournament_mode
            else "3. Run Parse"
        )
        if is_official_mode:
            can_parse = selected_source is not None and official_range_valid
            readiness = (
                (selected_source is not None, "Official source"),
                (official_range_valid, "Date range"),
            )
        elif is_tournament_mode:
            can_parse = tournament_page is not None and tournament_ready
            readiness = (
                (tournament_page is not None, "Supported URL"),
                (tournament_ready, "Provider API ready"),
            )
        else:
            can_parse = (
                file_bytes is not None
                and selected_key is not None
                and parser_key_confirmed
            )
            readiness = (
                (file_bytes is not None, "XLSX file"),
                (selected_key is not None, "ParserKey selected"),
                (parser_key_confirmed, "ParserKey confirmed"),
            )
        for ready, label in readiness:
            st.markdown(
                f'<div class="neto-ready-line">{"✅" if ready else "○"} {label}</div>',
                unsafe_allow_html=True,
            )
        if st.button(
            "Fetch Schedule"
            if is_official_mode or is_tournament_mode
            else "Run Parse",
            type="primary",
            disabled=not can_parse,
            key="run_parse",
            width="stretch",
        ):
            with st.spinner(
                "Fetching schedule..."
                if is_official_mode or is_tournament_mode
                else "Parsing schedule..."
            ):
                if is_official_mode:
                    try:
                        fetched_result = _cached_fetch_official(
                            selected_source_id or "",
                            official_start.isoformat(),
                            official_end.isoformat(),
                            range_timezone,
                        )
                    except _OfficialFetchFailed as exc:
                        fetched_result = exc.result
                    st.session_state["neto_parse_result"] = fetched_result
                elif is_tournament_mode:
                    try:
                        fetched_result = _cached_fetch_tournament(tournament_url)
                    except _WikiFetchFailed as exc:
                        fetched_result = exc.result
                    st.session_state["neto_parse_result"] = fetched_result
                else:
                    st.session_state["neto_parse_result"] = parse_workbook(
                        file_bytes or b"", selected_key
                    )

    result: ParseResult | None = st.session_state.get("neto_parse_result")

    with st.container(key="results_workflow"):
        findings_column, issues_column, export_column = st.columns(
            [2.15, 1.35, 1], gap="medium", vertical_alignment="top"
        )

        # Render the full-width table before filling the columns above it so the
        # filtered view can also drive every export button.
        with st.container(border=True, key="table_card"):
            canonical_view, presentation_view = _render_match_table(
                result, selected_key
            )

        with findings_column:
            with st.container(border=True, key="findings_card"):
                st.subheader("4. Findings")
                if result is None:
                    st.caption("Parse findings will appear here.")
                else:
                    _render_status(result)

        with issues_column:
            with st.container(border=True, key="issues_card"):
                _render_validation_issues(result)

        with export_column:
            with st.container(border=True, key="export_card"):
                _render_export(
                    result,
                    uploaded_file,
                    selected_key,
                    canonical_view,
                    presentation_view,
                )


if __name__ == "__main__":
    main()
