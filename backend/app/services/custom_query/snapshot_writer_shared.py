"""回写共享定义：错误码、异常类、cell_ref 解析。

从 ``snapshot_writer.py`` 抽出（该文件已达 800 行门禁上限），供 ``snapshot_writer`` 与
其伴生模块（``snapshot_writer_modules`` / ``snapshot_writer_addr_id``）共用。

放在独立模块而不是让伴生模块反向 import ``snapshot_writer`` —— 后者会造成循环导入
（``snapshot_writer`` 在模块级 import 伴生模块）。

``snapshot_writer`` 对本模块的符号做 re-export，既有
``from app.services.custom_query.snapshot_writer import WritebackConflict`` 的调用方与
测试不受影响（异常类是同一对象，``isinstance`` / ``except`` 判定不变）。
"""

from __future__ import annotations

import re
from datetime import datetime

# ─── 错误码 ──────────────────────────────────────────────────────────────────
# 回写目标无法解析为有效 addr_id → 中止回写、数据不变（R3.4）
ERR_CODE_TARGET_UNRESOLVABLE = "TARGET_UNRESOLVABLE"
# Resolve_Service 不可用 / 超时 → 中止回写、数据不变（R3.5）
ERR_CODE_RESOLVE_UNAVAILABLE = "RESOLVE_UNAVAILABLE"
# 审计写入失败 → 回滚回写改动（R14.8「无审计不回写」）
ERR_CODE_AUDIT_WRITE_FAILED = "AUDIT_WRITE_FAILED"


# ─── Exceptions ──────────────────────────────────────────────────────────────


class WritebackConflict(Exception):
    """乐观锁冲突：opened_at < updated_at"""

    def __init__(self, latest_updated_at: datetime, latest_editor: str):
        self.latest_updated_at = latest_updated_at
        self.latest_editor = latest_editor
        super().__init__(
            f"Conflict: data updated at {latest_updated_at} by {latest_editor}"
        )


class WritebackPermissionDenied(Exception):
    """无写权限或非 workpaper 源"""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class WritebackTargetUnresolvable(Exception):
    """回写目标无法被 Resolve_Service 解析为有效 addr_id（R3.4）。

    字段缺失 / 格式非法 / 目标格不存在 → 中止回写、不修改任何数据。
    携带 `error_code=TARGET_UNRESOLVABLE` 供 router 转 HTTP 400。
    """

    error_code = ERR_CODE_TARGET_UNRESOLVABLE

    def __init__(self, target_hint: str, message: str | None = None):
        self.target_hint = target_hint
        self.message = message or f"回写目标无法解析为有效 addr_id：{target_hint}"
        super().__init__(self.message)


class WritebackResolveUnavailable(Exception):
    """Resolve_Service 不可用或 5 秒内无响应（R3.5）。

    中止回写、保持数据不变。携带 `error_code=RESOLVE_UNAVAILABLE` 供 router 转 HTTP 503。
    """

    error_code = ERR_CODE_RESOLVE_UNAVAILABLE

    def __init__(self, target_hint: str, message: str | None = None):
        self.target_hint = target_hint
        self.message = message or f"解析服务不可用或超时，回写已中止：{target_hint}"
        super().__init__(self.message)


class AuditWriteFailed(Exception):
    """回写成功但审计写入失败（R14.8「无审计不回写」）。

    把 `log_action` 纳入回写事务成功判定 —— 审计失败即回滚回写改动。
    携带 `error_code=AUDIT_WRITE_FAILED` 供 router 转 HTTP 500 并回滚。
    """

    error_code = ERR_CODE_AUDIT_WRITE_FAILED

    def __init__(self, message: str | None = None):
        self.message = message or "审计日志写入失败，回写已回滚（无审计不回写）。"
        super().__init__(self.message)


# ─── Cell reference parsing ──────────────────────────────────────────────────


def parse_cell_ref(cell_ref: str) -> tuple[int, int]:
    """解析 cell_ref (e.g. 'B7') 为 (row_0indexed, col_0indexed)。

    cell_ref 是 1-indexed (Excel 风格)，snapshot 用 0-indexed key (Univer 约定)。
    B7 → row=6, col=1
    """
    m = re.match(r"^([A-Z]+)(\d+)$", cell_ref.upper().strip())
    if not m:
        raise ValueError(f"Invalid cell_ref: {cell_ref}")

    col_letters = m.group(1)
    row_num = int(m.group(2))

    # 列字母转 0-indexed
    col = 0
    for ch in col_letters:
        col = col * 26 + (ord(ch) - 64)
    col -= 1  # 转为 0-indexed

    # 行号转 0-indexed
    row = row_num - 1

    return row, col
