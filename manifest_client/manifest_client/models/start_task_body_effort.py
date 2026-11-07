from enum import StrEnum

class StartTaskBodyEffort(StrEnum):
    HIGH = "high"
    LOW = "low"
    MAX = "max"
    MEDIUM = "medium"
    ULTRA = "ultra"
    XHIGH = "xhigh"

    def __str__(self) -> str:
        return str(self.value)
