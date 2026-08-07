# Feature: custom-workpaper-formula-binding — 组①三层一致验收（迁移 DDL + ORM）
"""wp_formula 迁移 DDL 列/索引与 ORM WpFormula 一致。

🔴 **判据已由「手写按迁移分组的列清单」改为「扫全部 `V*.sql` 抽取」**
（2026-08-07，spec formula-management-runtime-closure 归档复核发现）。

改前该断言**恒红且零信号**：清单只写到 V100，而 **V104**
（`V104__formula_runtime_outbox.sql`）又给 `wp_formula` 加了三列
``lifecycle_state`` / ``definition_version`` / ``definition_hash``，
ORM 早已跟进（HEAD 侧即有该三列）而清单没人维护 ⇒ 每次跑都报
「ORM 列与期望不符」，把「真漂移」与「守卫自己过期」混为一谈。

手写清单的结构性问题 = 「每加一次 `ALTER TABLE` 都要有人记得改它」。
改为扫迁移后，判据自动跟随：

* **迁移有、ORM 无** → 打红（ORM 漏 `mapped_column`，属 memory 已记的
  「表里有列、代码写不进去」那类静默缺陷）
* **ORM 有、迁移无** → 打红（新增 DB 列没写迁移）

另配抽取器自检（抽到的列非空、必含若干已知列、约束名不得被当列名），
防正则失效让主断言退化成「空集 == 空集」的空转。
"""

from __future__ import annotations

import re
from pathlib import Path

from app.models.workpaper_models import WpFormula

BACKEND_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = BACKEND_ROOT / "migrations"
V052 = MIGRATIONS / "V052__wp_formula.sql"
R052 = MIGRATIONS / "R052__wp_formula_rollback.sql"
# formula-management-library V100 扩展 wp_formula 的列（三类型治理）
V100 = MIGRATIONS / "V100__formula_management_library.sql"
# formula-runtime V104 扩展 wp_formula 的列（生命周期 + 定义版本/哈希）
V104 = MIGRATIONS / "V104__formula_runtime_outbox.sql"

# V052 建表基线列（只作抽取器自检的下限，不作主断言的期望集）
_V052_BASE_COLUMNS = {
    "id",
    "project_id",
    "wp_id",
    "sheet_name",
    "target_cell",
    "expression",
    "category",
    "description",
    "created_by",
    "created_at",
    "updated_at",
}
# V100 扩展列（三类型 + 最近计算时间 + 规范化引用 + 来源）
_V100_EXTENSION_COLUMNS = {
    "formula_type",
    "last_computed_at",
    "refs",
    "issue_description",
    "hint_text",
    "formula_source",
    "reference_formula_id",
}
# V104 扩展列（定义生命周期 + 版本 + 定义哈希）
_V104_EXTENSION_COLUMNS = {
    "lifecycle_state",
    "definition_version",
    "definition_hash",
}

#: `ALTER TABLE wp_formula ADD COLUMN <name>`（容忍 `IF NOT EXISTS` 与任意空白）
_ALTER_ADD_RE = re.compile(
    r"ALTER\s+TABLE\s+wp_formula\s+ADD\s+COLUMN\s+"
    r"(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)

_CONSTRAINT_HEADS = {
    "constraint",
    "primary",
    "unique",
    "foreign",
    "check",
    "exclude",
    "key",
}


def _create_table_columns() -> set[str]:
    """从 V052 的 `CREATE TABLE wp_formula (...)` 抽建表列名。

    用**圆括号配对**取建表体（禁固定字符窗口 —— memory 已记该坑：
    类型里的 `NUMERIC(18,2)` 会让按第一个 `)` 截断的写法提前收尾），
    再按顶层逗号切段、取每段首个标识符，并跳过表级约束段。
    """
    ddl = V052.read_text(encoding="utf-8")
    m = re.search(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?wp_formula\s*\(",
        ddl,
        re.IGNORECASE,
    )
    assert m, "V052 未找到 CREATE TABLE wp_formula（抽取器失效，不是列漂移）"

    start = m.end() - 1  # 指向左括号
    depth = 0
    end = -1
    for i in range(start, len(ddl)):
        if ddl[i] == "(":
            depth += 1
        elif ddl[i] == ")":
            depth -= 1
            if depth == 0:
                end = i
                break
    assert end > start, "V052 建表体括号未配对"
    body = ddl[start + 1 : end]

    segments: list[str] = []
    depth = 0
    seg_start = 0
    for i, ch in enumerate(body):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            segments.append(body[seg_start:i])
            seg_start = i + 1
    segments.append(body[seg_start:])

    cols: set[str] = set()
    for seg in segments:
        # 去掉行内注释后取首个 token
        line = re.sub(r"--.*", "", seg).strip()
        if not line:
            continue
        head = re.match(r'"?([A-Za-z_][A-Za-z0-9_]*)"?', line)
        if not head:
            continue
        name = head.group(1)
        if name.lower() in _CONSTRAINT_HEADS:
            continue
        cols.add(name)
    return cols


def _altered_columns() -> dict[str, set[str]]:
    """扫全部 `V*.sql`，返回 `{迁移文件名: 该迁移给 wp_formula 新增的列名集合}`。

    回滚脚本 `R*.sql` 不参与（它们 DROP 列，纳入会让列集反向漂移）。
    """
    out: dict[str, set[str]] = {}
    for path in sorted(MIGRATIONS.glob("V*.sql")):
        added = {
            mm.group(1) for mm in _ALTER_ADD_RE.finditer(path.read_text(encoding="utf-8"))
        }
        if added:
            out[path.name] = added
    return out


def _all_migration_columns() -> set[str]:
    """迁移侧 wp_formula 列全集 = 建表列 ∪ 各次 ALTER 新增列。"""
    cols = _create_table_columns()
    for added in _altered_columns().values():
        cols |= added
    return cols


def test_v052_r052_migration_pair_exists():
    assert V052.is_file(), "V052 migration missing"
    assert R052.is_file(), "R052 rollback missing"
    rollback = R052.read_text(encoding="utf-8")
    assert "DROP TABLE IF EXISTS wp_formula" in rollback


def test_wp_formula_orm_matches_migration_columns():
    """三层一致：ORM 列集 == **全部迁移**给 wp_formula 声明的列集。

    两侧不等时按方向分别报错，使「缺迁移」与「ORM 漏列」不混同。
    """
    orm_cols = {c.name for c in WpFormula.__table__.columns}
    mig_cols = _all_migration_columns()

    orm_only = orm_cols - mig_cols
    mig_only = mig_cols - orm_cols
    assert not orm_only, (
        f"ORM 有列但无任何迁移声明: {sorted(orm_only)} —— 新增 DB 列必须配 V*.sql"
    )
    assert not mig_only, (
        f"迁移声明了列但 ORM 缺 mapped_column: {sorted(mig_only)} —— "
        "ORM 写入时该列会被静默忽略（表里有列、代码写不进去）"
    )


def test_migration_column_extraction_is_not_vacuous():
    """抽取器自检 —— 防正则失效让主断言退化成「空集 == 空集」。"""
    base = _create_table_columns()
    assert _V052_BASE_COLUMNS <= base, (
        f"V052 建表列抽取不完整，缺: {sorted(_V052_BASE_COLUMNS - base)}"
    )
    # 判据有效性：约束名不得被当成列名
    assert not (_CONSTRAINT_HEADS & {c.lower() for c in base}), (
        f"抽取器把表级约束当成列名: {sorted(_CONSTRAINT_HEADS & {c.lower() for c in base})}"
    )

    altered = _altered_columns()
    assert altered, "未从任何 V*.sql 抽到 `ALTER TABLE wp_formula ADD COLUMN`（抽取器失效）"
    all_added: set[str] = set()
    for added in altered.values():
        all_added |= added
    assert _V100_EXTENSION_COLUMNS <= all_added, (
        f"V100 扩展列未被抽到: {sorted(_V100_EXTENSION_COLUMNS - all_added)}"
    )
    assert _V104_EXTENSION_COLUMNS <= all_added, (
        f"V104 扩展列未被抽到: {sorted(_V104_EXTENSION_COLUMNS - all_added)}"
    )


def test_extension_columns_live_in_their_own_migration():
    """扩展列必须出现在**声明它的那次**迁移里（防迁移号与列的归属漂移）。"""
    altered = _altered_columns()
    v100 = next((v for k, v in altered.items() if k.startswith("V100__")), set())
    v104 = next((v for k, v in altered.items() if k.startswith("V104__")), set())
    assert _V100_EXTENSION_COLUMNS <= v100, (
        f"V100 迁移未包含其扩展列: {sorted(_V100_EXTENSION_COLUMNS - v100)}"
    )
    assert _V104_EXTENSION_COLUMNS <= v104, (
        f"V104 迁移未包含其扩展列: {sorted(_V104_EXTENSION_COLUMNS - v104)}"
    )


def test_wp_formula_unique_index_in_orm_and_ddl():
    ddl = V052.read_text(encoding="utf-8")
    index_names = {idx.name for idx in WpFormula.__table__.indexes}
    assert "uq_wp_formula_wp_sheet_cell" in index_names
    assert "idx_wp_formula_project" in index_names
    assert "uq_wp_formula_wp_sheet_cell" in ddl
    assert "idx_wp_formula_project" in ddl
    assert re.search(
        r"uq_wp_formula_wp_sheet_cell[\s\S]*?wp_id\s*,\s*sheet_name\s*,\s*target_cell",
        ddl,
        re.IGNORECASE,
    )
