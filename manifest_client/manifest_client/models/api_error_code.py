from enum import StrEnum

class ApiErrorCode(StrEnum):
    BUSY = "busy"
    FORBIDDEN = "forbidden"
    INTERNAL = "internal"
    INVALID = "invalid"
    NOT_FOUND = "not_found"
    UNAVAILABLE = "unavailable"

    def __str__(self) -> str:
        return str(self.value)
