"""Typed failures for official schedule retrieval."""


class OfficialWebError(RuntimeError):
    """Base class for source and transport failures."""


class OfficialHttpError(OfficialWebError):
    """An official endpoint could not be retrieved."""


class OfficialSchemaError(OfficialWebError):
    """An official response no longer matches its expected contract."""


class OfficialRequestError(OfficialWebError):
    """The requested source or date range is invalid."""
