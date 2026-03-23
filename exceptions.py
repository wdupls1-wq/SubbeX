class SubbeXError(Exception):
    """Base application error."""


class DependencyError(SubbeXError):
    """Raised when a required local dependency cannot be found."""


class JobError(SubbeXError):
    """Raised when a transcription job cannot complete."""

