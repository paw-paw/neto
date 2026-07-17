"""Errors raised by the public Google Sheets workbook provider."""

from __future__ import annotations


class GoogleSheetsError(RuntimeError):
    """Base error for Google Sheets ingestion."""


class GoogleSheetsUrlError(GoogleSheetsError):
    """Raised when a user-provided URL is invalid or unsupported."""


class GoogleSheetsAccessError(GoogleSheetsError):
    """Raised when a sheet is unavailable to an anonymous viewer."""


class GoogleSheetsDownloadError(GoogleSheetsError):
    """Raised when Google does not return a safe XLSX workbook."""
