from __future__ import annotations


class TrafficServiceError(Exception):
    pass


class InvalidCoordinatesError(TrafficServiceError):
    pass


class GoogleRoutesAPIError(TrafficServiceError):
    pass


class QuotaExceededError(TrafficServiceError):
    def __init__(self, message: str, used: int, cap: int) -> None:
        super().__init__(message)
        self.used = used
        self.cap = cap

