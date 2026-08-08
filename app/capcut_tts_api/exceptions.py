"""
Exceptions for CapCut TTS API Client.
"""


class CapCutError(Exception):
    """Base exception for all CapCut client errors."""

    pass


class CapCutSignError(CapCutError):
    """Raised when cryptography or signing fails."""

    pass


class CapCutAPIError(CapCutError):
    """Raised when the API returns an error response or non-200 HTTP code."""

    def __init__(self, message: str, status_code: int = 0, response_data: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data or {}


class CapCutUploadError(CapCutError):
    """Raised when media upload to VOD fails."""

    pass


class CapCutTaskError(CapCutError):
    """Raised when a background TTS/STT task fails or times out."""

    pass
