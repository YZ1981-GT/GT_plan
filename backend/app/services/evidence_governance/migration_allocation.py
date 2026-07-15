"""动态迁移编号分配 + evidence-governance 迁移约定守卫（纯函数）。

Feature: attachment-ocr-ai-evidence-governance-hardening
Task: 2.1 (Wave 1 — 动态迁移与 PostgreSQL 治理模型)
Requirements: R14
Design: §8.1 MigrationRunner 编号与建表策略

本模块 **不建表、不写库、不固定 V 号**。它冻结两件事，供 Task 2.2–2.4 各自
在实施时调用：

1. **动态“下一可用 V”分配**（design §8.1）：先取 DB 已应用集合（`schema_version`）
   与目录扫描最高号，检测状态是否一致；一致则返回下一可用 V，不一致则抛
   ``MigrationStateInconsistency`` 停止实施（不猜号、不覆盖迁移）。

   “不一致”是指真正阻断的漂移，**不包括** 目录中存在但尚未应用的 pending 迁移
   —— 后者是 MigrationRunner 启动期正常行为（启动时按序应用）。阻断条件：
     * 已应用版本在目录中缺失（applied-but-missing：迁移被删/改名/校验漂移）
     * `schema_migration_failures` 存在任一失败记录
     * 目录存在重复版本号（MigrationRunner.scan_migrations 亦会抛错）

2. **evidence-governance 迁移约定 lint**（design §8.1）：additive-only、可重复检测
   （`IF NOT EXISTS` / `information_schema` 守卫）、不删除 legacy 列、所有 FK 默认
   ``ON DELETE RESTRICT``。Task 2.2–2.4 的每个迁移文件都必须通过 ``lint_migration_sql``。

单一真源：本模块。禁止在 2.2–2.4 内复制编号/约定逻辑。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


class MigrationStateInconsistency(RuntimeError):
    """迁移状态源与目录扫描不一致 —— 停止实施并人工解决（design §8.1）。"""


# ---------------------------------------------------------------------------
# 版本号规范化
# ---------------------------------------------------------------------------

_VERSION_FILE_RE = re.compile(r"^V(\d+)__.*\.sql$", re.IGNORECASE)


def normalize_version(v: str | int) -> int:
    """把 '102' / 'V102' / 102 归一化为 int 102。"""
    if isinstance(v, int):
        return v
    s = str(v).strip()
    if s.upper().startswith("V"):
        s = s[1:]
    # 允许 'V102__xxx.sql'
    m = _VERSION_FILE_RE.match(str(v))
    if m:
        return int(m.group(1))
    return int(s)


def format_version(n: int, width: int = 3) -> str:
    """把 int 106 格式化为 'V106'（宽度至少 3 位，与既有 V001..V105 对齐）。"""
    return "V" + str(int(n)).zfill(width)


def parse_dir_versions(filenames: list[str]) -> dict[int, list[str]]:
    """扫描迁移文件名列表，返回 {version_int: [filename, ...]}。"""
    out: dict[int, list[str]] = {}
    for name in filenames:
        m = _VERSION_FILE_RE.match(name)
        if m:
            out.setdefault(int(m.group(1)), []).append(name)
    return out


# ---------------------------------------------------------------------------
# 状态分析 + 下一可用 V
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MigrationStateReport:
    """迁移状态快照（纯数据，可复算，供文档/测试断言）。"""

    dir_highest: int | None
    applied_highest: int | None
    pending_versions: list[int]           # 目录有、DB 未应用（benign）
    applied_missing_in_dir: list[int]     # DB 已应用、目录缺失（BLOCKING）
    duplicate_versions: list[int]         # 目录重复版本号（BLOCKING）
    failure_versions: list[str]           # schema_migration_failures（BLOCKING）
    next_available: int | None
    blocking_reasons: list[str] = field(default_factory=list)

    @property
    def is_consistent(self) -> bool:
        return not self.blocking_reasons


def analyze_migration_state(
    dir_filenames: list[str],
    applied_versions: set[str] | set[int],
    failure_versions: set[str] | set[int] | None = None,
) -> MigrationStateReport:
    """纯函数：给定目录文件名、DB 已应用集合与失败集合，产出状态报告。

    不一致（blocking）会体现在 ``blocking_reasons`` 中；``next_available`` 仅在
    一致时给出（否则为 None，调用方须停止实施）。
    """
    by_version = parse_dir_versions(dir_filenames)
    dir_versions = set(by_version)
    applied = {normalize_version(v) for v in applied_versions}
    failures = sorted({str(normalize_version(v)) for v in (failure_versions or set())})

    duplicates = sorted(v for v, names in by_version.items() if len(names) > 1)
    applied_missing = sorted(applied - dir_versions)
    pending = sorted(dir_versions - applied)

    dir_highest = max(dir_versions) if dir_versions else None
    applied_highest = max(applied) if applied else None

    reasons: list[str] = []
    if duplicates:
        reasons.append(
            f"目录存在重复版本号（须重编号）：{[format_version(v) for v in duplicates]}"
        )
    if applied_missing:
        reasons.append(
            "DB 已应用但目录缺失（迁移被删/改名/校验漂移）："
            f"{[format_version(v) for v in applied_missing]}"
        )
    if failures:
        reasons.append(
            f"schema_migration_failures 存在失败记录：{[format_version(int(v)) for v in failures]}"
        )

    # 下一可用 = 目录与已应用并集的最高号 + 1；仅在一致时给出
    next_available: int | None = None
    if not reasons:
        highest = max([v for v in (dir_highest, applied_highest) if v is not None], default=0)
        next_available = highest + 1

    return MigrationStateReport(
        dir_highest=dir_highest,
        applied_highest=applied_highest,
        pending_versions=pending,
        applied_missing_in_dir=applied_missing,
        duplicate_versions=duplicates,
        failure_versions=failures,
        next_available=next_available,
        blocking_reasons=reasons,
    )


def next_available_version(
    dir_filenames: list[str],
    applied_versions: set[str] | set[int],
    failure_versions: set[str] | set[int] | None = None,
) -> int:
    """返回下一可用 V（int）；状态不一致时抛 ``MigrationStateInconsistency``。

    这是 Task 2.2–2.4 分配 V 号的唯一入口。pending 迁移（目录 > DB）不阻断。
    """
    report = analyze_migration_state(dir_filenames, applied_versions, failure_versions)
    if not report.is_consistent:
        raise MigrationStateInconsistency(
            "迁移状态源与目录扫描不一致，停止实施并人工解决（design §8.1）：\n  - "
            + "\n  - ".join(report.blocking_reasons)
        )
    assert report.next_available is not None
    return report.next_available


# ---------------------------------------------------------------------------
# evidence-governance 迁移约定 lint（additive / repeatable / no-drop / FK RESTRICT）
# ---------------------------------------------------------------------------

# 去掉行注释 (-- ...) 后再做正则，避免注释里的 DROP 之类误伤。
_LINE_COMMENT_RE = re.compile(r"--[^\n]*")
_CREATE_TABLE_RE = re.compile(r"\bCREATE\s+TABLE\b", re.IGNORECASE)
_CREATE_TABLE_INE_RE = re.compile(r"\bCREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\b", re.IGNORECASE)
_CREATE_INDEX_RE = re.compile(r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\b", re.IGNORECASE)
_CREATE_INDEX_INE_RE = re.compile(r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS\b", re.IGNORECASE)
# ADD COLUMN 必须 IF NOT EXISTS 或包在 information_schema DO 守卫里
_ADD_COLUMN_RE = re.compile(r"\bADD\s+COLUMN\b(?!\s+IF\s+NOT\s+EXISTS)", re.IGNORECASE)
_INFO_SCHEMA_RE = re.compile(r"information_schema", re.IGNORECASE)
# 存在性守卫（DO 块内任一即视为幂等可重复）：information_schema / pg_indexes /
# pg_class / pg_constraint / pg_type / to_regclass
_EXISTENCE_GUARD_RE = re.compile(
    r"information_schema|pg_indexes|pg_class|pg_constraint|pg_type|to_regclass",
    re.IGNORECASE,
)
# DO $$ ... $$ 块（PL/pgSQL 幂等守卫的常见载体）
_DO_BLOCK_RE = re.compile(r"DO\s+\$\$.*?\$\$", re.IGNORECASE | re.DOTALL)
# 破坏性语句（additive-only 禁止；不删除 legacy 列）
_DROP_TABLE_RE = re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE)
_DROP_COLUMN_RE = re.compile(r"\bDROP\s+COLUMN\b", re.IGNORECASE)
_TRUNCATE_RE = re.compile(r"\bTRUNCATE\b", re.IGNORECASE)
# 内联 FK：REFERENCES ...；须显式 ON DELETE RESTRICT
_REFERENCES_RE = re.compile(
    r"REFERENCES\s+[A-Za-z_][\w\.]*\s*(?:\([^)]*\))?(?P<tail>[^,\n)]*)",
    re.IGNORECASE,
)


def _strip_line_comments(sql: str) -> str:
    return _LINE_COMMENT_RE.sub("", sql)


def lint_migration_sql(sql: str, *, require_fk_restrict: bool = True) -> list[str]:
    """lint 单个 evidence-governance 迁移 SQL，返回违规列表（空=通过）。

    约定（design §8.1）：
      1. additive-only：禁止 DROP TABLE / DROP COLUMN / TRUNCATE（不删除 legacy 列）。
      2. 可重复检测：CREATE TABLE / CREATE INDEX 必须 IF NOT EXISTS；
         ADD COLUMN 必须 IF NOT EXISTS 或包在 information_schema DO 守卫内。
      3. 所有 FK（内联 REFERENCES）默认 ON DELETE RESTRICT。

    ``require_fk_restrict=False`` 用于 enum-only / 无 FK 的迁移（如 V105）跳过 FK 检查。
    """
    body = _strip_line_comments(sql)
    violations: list[str] = []

    # 1. additive-only（FK RESTRICT 检查前先做，全 body 扫描）
    if _DROP_TABLE_RE.search(body):
        violations.append("含 DROP TABLE：违反 additive-only，禁止删除既有表/legacy 结构")
    if _DROP_COLUMN_RE.search(body):
        violations.append("含 DROP COLUMN：违反 additive-only，禁止删除 legacy 列")
    if _TRUNCATE_RE.search(body):
        violations.append("含 TRUNCATE：违反 additive-only")

    # 2. 可重复检测。先剥离“存在性守卫的 DO 块”（information_schema / pg_indexes 等）——
    #    块内的 CREATE TABLE/INDEX/ADD COLUMN 已由守卫保证幂等，不要求 IF NOT EXISTS。
    #    剥离后剩余的裸 DDL 才要求 IF NOT EXISTS。
    unguarded = body
    for m in _DO_BLOCK_RE.finditer(body):
        block = m.group(0)
        if _EXISTENCE_GUARD_RE.search(block):
            unguarded = unguarded.replace(block, " ")

    n_create_table = len(_CREATE_TABLE_RE.findall(unguarded))
    n_create_table_ine = len(_CREATE_TABLE_INE_RE.findall(unguarded))
    if n_create_table != n_create_table_ine:
        violations.append(
            f"CREATE TABLE 未全部 IF NOT EXISTS（{n_create_table_ine}/{n_create_table}）：不可重复检测"
        )
    n_create_index = len(_CREATE_INDEX_RE.findall(unguarded))
    n_create_index_ine = len(_CREATE_INDEX_INE_RE.findall(unguarded))
    if n_create_index != n_create_index_ine:
        violations.append(
            f"CREATE INDEX 未全部 IF NOT EXISTS（{n_create_index_ine}/{n_create_index}）：不可重复检测"
        )
    if _ADD_COLUMN_RE.search(unguarded):
        violations.append(
            "ADD COLUMN 未用 IF NOT EXISTS 且不在 information_schema/pg_* 存在性守卫内：不可重复检测"
        )

    # 3. FK 默认 ON DELETE RESTRICT
    if require_fk_restrict:
        for m in _REFERENCES_RE.finditer(body):
            tail = m.group("tail") or ""
            if not re.search(r"ON\s+DELETE\s+RESTRICT", tail, re.IGNORECASE):
                snippet = m.group(0).strip()[:80]
                violations.append(
                    f"FK 未显式 ON DELETE RESTRICT：`{snippet}`"
                )

    return violations
