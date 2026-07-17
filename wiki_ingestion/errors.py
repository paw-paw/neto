"""Expected failures for tournament wiki ingestion."""


class WikiIngestionError(RuntimeError):
    """Base class for user-facing wiki ingestion failures."""


class TournamentUrlError(WikiIngestionError):
    """The supplied URL is invalid or unsupported."""


class WikiConfigurationError(WikiIngestionError):
    """A provider is supported but required server configuration is missing."""


class WikiApiError(WikiIngestionError):
    """A supported provider API request failed."""


class WikiStructureError(WikiIngestionError):
    """The API response cannot provide reliable required match fields."""
