"""Phase 16: 取证包与版本链枚举定义"""
from enum import Enum


class VersionObjectType(str, Enum):
    report = "report"
    note = "note"
    workpaper = "workpaper"
    procedure = "procedure"


class ConflictResolution(str, Enum):
    accept_local = "accept_local"
    accept_remote = "accept_remote"
    manual_merge = "manual_merge"


class ConflictStatus(str, Enum):
    open = "open"
    resolved = "resolved"
    rejected = "rejected"


class HashCheckStatus(str, Enum):
    passed = "passed"
    failed = "failed"
