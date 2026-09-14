# -*- coding: utf-8 -*-
"""V146 `procedure_instances.suggestion_state` 迁移与 ORM 一致性守卫。

Feature: procedure-trimming-and-delegation-intelligence — Task 11
Requirements: 6.4, 8.1

═══ 判据为何必须「扫全部 V*.sql 派生列集」而不是手写清单 ═══

平台已因手写列清单栽过一次（`wp_formula` 的三层一致性守卫）：手写清单的失效方式是
「加了新迁移但没人记得改它」⇒ 每次跑都报「ORM 与期望不符」，把**真漂移**和**守卫
自己过期**混为一谈（长期红会被当噪声跳过，比不写守卫更坏）。

故本文件的列集判据一律**从迁移文件派生**：各次 `ALTER TABLE ... ADD COLUMN`
（本表无 `CREATE TABLE`，见下），报错**按方向区分**：

- ORM 有该列而迁移无 ⇒ 新增列没写迁移（表里没这列，写入静默失败）
- 迁移有该列而 ORM 无 ⇒ ORM 漏 `mapped_column`（列在表里存在而代码写不进去）

═══ 🔴 `procedure_instances` 的建表语句不在任何 `V*.sql` 里（2026-08-09 实证）═══

首版判据是「ORM 列集 ≡ 迁移派生**全列集**」，一跑就红 —— 派生列集只有
`suggestion_state` 一项。探针实测原因：

| 表 | `CREATE TABLE` 在 `V*.sql` 里 |
|---|---|
| `procedure_instances` | **否** |
| `procedure_trim_schemes` | **否** |
| `procedure_row_tasks` | 是（V105） |

迁移目录共 139 张 `CREATE TABLE`，这两张不在其中 —— 它们是 Phase 9 早期经
`Base.metadata.create_all` 建的，`MigrationRunner` 时代之后新建的表才有建表迁移。

⇒ 「全列集相等」这条判据对本表**结构上不可满足**，不是代码漂移。收窄为
**「迁移新增列 ⊆ ORM」+「ORM 中属本 spec 的列必须有迁移」双向**，并配
:class:`TestBaselineTableWithoutCreateMigration` 的 **stale 检测** —— 哪天有人给
`procedure_instances` 补了建表迁移，该断言会打红提醒把判据升级回全列集比对，
使这条豁免不会变成永久盲区（同 memory 已记的「豁免必须配 stale 检测」）。

═══ 断言分类（Wave 1 范式）═══

本任务的实现与守卫同轮交付，故**全部应绿**；类 A 与类 B 的区分体现在失败消息上：
派生器自检（类 A）失败说明守卫坏了，列集比对（类 B）失败说明代码/迁移漂移。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
MIGRATIONS = BACKEND / "migrations"
TABLE = "procedure_instances"

MIGRATION_VERSION = "146"
MIGRATION_FILE = "V146__procedure_instance_suggestion_state.sql"
ROLLBACK_FILE = "R146__procedure_instance_suggestion_state.sql"

# SoftDeleteMixin / TimestampMixin 带来的列（不由 procedure_instances 的迁移显式声明，
# 由早期建表迁移或 mixin 统一注入）。派生比对时两侧都排除，避免把 mixin 差异
# 误报成漂移。
_MIXIN_COLUMNS = {"is_deleted", "deleted_at", "created_at", "updated_at"}

# 🔴 pre-migration 基线：`procedure_instances` 的 CREATE TABLE **不在任何 V*.sql 里**
#    （2026-08-09 实证，详见模块 docstring）。这些列属早期建表遗留，派生器抽不到，
#    不是「漏写迁移」。**本清单只许缩短，不许增长** —— 三道锁见
#    `test_pre_migration_baseline_is_exact_not_an_escape_hatch`。
_PRE_MIGRATION_COLUMNS = {
    "id",
    "project_id",
    "audit_cycle",
    "procedure_code",
    "procedure_name",
    "parent_id",
    "sort_order",
    "status",
    "skip_reason",
    "is_custom",
    "assigned_to",
    "assigned_at",
    "execution_status",
    "wp_code",
    "wp_id",
}

# 条目数上限（== 当前实际值）。写死上限是为了让「往基线里再加一条」这个动作打红，
# 而不是让它悄悄通过 —— 只做「实际 ⊆ 基线」单向断言时该动作可以绕过。
_PRE_MIGRATION_CAP = 15

# 上限的**天花板**：`_PRE_MIGRATION_CAP` 只许下调，不许上调。
#
# 🔴 为什么要两层常量：只写 `len(基线) <= 上限` 这一条断言时，「往基线里再加一条」
#    可以靠**把上限从 15 改成 99** 绕过 —— 而那正是本守卫要禁止的动作（平台已在
#    别处踩过：变异 M9 把上限调高后守卫全绿）。天花板独立存在，改上限即打红。
_CAP_CEILING = 15


# ────────────────────────── 迁移列集派生器 ──────────────────────────

def _sql_files() -> list[Path]:
    return sorted(MIGRATIONS.glob("V*.sql"))


def _strip_sql_comments(sql: str) -> str:
    """剥 `--` 行注释（本仓库迁移不用 /* */）。

    🔴 必须剥：V146 的注释里写了 `ADD COLUMN IF NOT EXISTS`/`suggestion_state`
    作为说明文字，不剥会让派生器把注释数成真实 DDL。
    """
    return "\n".join(re.sub(r"--.*$", "", ln) for ln in sql.splitlines())


def _create_table_columns(sql: str, table: str) -> set[str]:
    """抽 `CREATE TABLE <table> ( ... )` 的列名（圆括号配对，跳过表级约束行）。"""
    m = re.search(
        rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?{table}\b",
        sql,
        re.I,
    )
    if not m:
        return set()
    i = sql.index("(", m.end())
    depth = 0
    for j in range(i, len(sql)):
        if sql[j] == "(":
            depth += 1
        elif sql[j] == ")":
            depth -= 1
            if depth == 0:
                body = sql[i + 1 : j]
                break
    else:  # pragma: no cover - 迁移文件括号不配对
        return set()

    cols: set[str] = set()
    depth = 0
    buf: list[str] = []
    parts: list[str] = []
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    parts.append("".join(buf))

    constraint_kw = (
        "primary", "foreign", "unique", "check", "constraint", "exclude", "like",
    )
    for part in parts:
        tok = part.strip()
        if not tok:
            continue
        first = tok.split()[0].strip('"').lower()
        if first in constraint_kw:
            continue
        cols.add(first)
    return cols


def _added_columns(sql: str, table: str) -> set[str]:
    """抽 `ALTER TABLE <table> ADD COLUMN [IF NOT EXISTS] <col>` 的列名。"""
    cols: set[str] = set()
    pattern = re.compile(
        rf"ALTER\s+TABLE\s+(?:public\.)?{table}\b(.*?)(?=;|\Z)",
        re.I | re.S,
    )
    for m in pattern.finditer(sql):
        for am in re.finditer(
            r"ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?\"?([a-zA-Z_][\w]*)\"?",
            m.group(1),
            re.I,
        ):
            cols.add(am.group(1).lower())
    return cols


def derive_migration_columns(table: str = TABLE) -> set[str]:
    """从全部 V*.sql 派生某表的列集（建表列 ∪ 各次 ADD COLUMN）。"""
    cols: set[str] = set()
    for p in _sql_files():
        sql = _strip_sql_comments(p.read_text(encoding="utf-8", errors="replace"))
        cols |= _create_table_columns(sql, table)
        cols |= _added_columns(sql, table)
    return cols


def _orm_columns() -> set[str]:
    from app.models.procedure_models import ProcedureInstance

    return {c.name.lower() for c in ProcedureInstance.__table__.columns}


# ────────────────────────── 类 A：派生器自检 ──────────────────────────

class TestDeriverSelfCheck:
    """证明派生器真的在工作（防「扫描面为空 ⇒ 断言空转」）。"""

    def test_migration_files_scanned(self):
        files = _sql_files()
        assert len(files) >= 100, (
            f"只扫到 {len(files)} 个 V*.sql —— 迁移目录路径可能算错，"
            f"此时列集比对会因两侧都为空而假绿"
        )

    def test_derived_columns_non_empty(self):
        """派生器对本表至少要抽到 V146 新增的那一列（否则后续比对全部空转）。"""
        cols = derive_migration_columns()
        assert cols, "派生列集为空 —— 派生器失效，后续比对全部空转"
        assert "suggestion_state" in cols, (
            f"派生列集缺 suggestion_state —— ALTER 抽取有缺陷：{sorted(cols)}"
        )

    def test_create_table_extractor_works_on_a_table_that_has_one(self):
        """`CREATE TABLE` 抽取器本身有效 —— 用确实有建表迁移的表验证。

        本表无建表迁移（见模块 docstring），故不能用它自证抽取器；改用
        `procedure_row_tasks`（V105 建表），否则「抽不到列」与「抽取器坏了」
        不可区分。
        """
        cols = derive_migration_columns("procedure_row_tasks")
        assert cols, "procedure_row_tasks 派生列集为空 —— CREATE TABLE 抽取器失效"
        # 🔴 探针列必须**实际存在**于 V105 建表语句里。首版写了 `definition_id`
        #    ——该列在 V105 与 ORM 两侧都不存在（2026-08-09 实证：`procedure_row_tasks`
        #    的身份列是 `definition_key` + `definition_revision_hash`，`definition_id`
        #    只出现在 `procedure_row_definitions.id` 上）。用不存在的列做自检会让本条
        #    **恒红且零信号**：它既不能证明抽取器有效，也不指向任何真实漂移，
        #    还会把「抽取器坏了」和「探针列名写错了」混为一谈。
        for known in ("project_id", "definition_key", "workflow_status"):
            assert known in cols, (
                f"procedure_row_tasks 派生列集缺 {known}，"
                f"CREATE TABLE 抽取有缺陷：{sorted(cols)}"
            )
        # 反向自检：不存在的列必须抽不到（否则上面的正向断言可能是「什么都命中」）
        assert "definitely_not_a_real_column" not in cols

    def test_comment_stripping_works(self):
        """反向自检：注释里的 DDL 字样不得被派生成列。"""
        raw = (MIGRATIONS / MIGRATION_FILE).read_text(encoding="utf-8")
        assert "ADD COLUMN IF NOT EXISTS" in raw, "样本前提变了，请更新本自检"
        stripped = _strip_sql_comments(raw)
        # 注释段里出现过的说明文字不应残留
        assert "语义" not in stripped or stripped.count("语义") < raw.count("语义"), (
            "注释未被剥除 —— 派生器会把说明文字当 DDL"
        )

    def test_fake_sql_does_not_leak_columns(self):
        """派生器对不相关表的 DDL 必须零命中。"""
        fake = "ALTER TABLE some_other_table ADD COLUMN IF NOT EXISTS zzz JSONB;"
        assert _added_columns(fake, TABLE) == set()


# ────────────────────────── 类 B：迁移与 ORM ──────────────────────────

class TestMigrationFilePresence:
    def test_forward_migration_exists(self):
        p = MIGRATIONS / MIGRATION_FILE
        assert p.exists(), f"缺 {MIGRATION_FILE}"

    def test_rollback_migration_exists(self):
        p = MIGRATIONS / ROLLBACK_FILE
        assert p.exists(), (
            f"缺 {ROLLBACK_FILE} —— 平台约定 R1xx 配对回滚脚本；"
            f"备份没有还原路径等于没备份"
        )

    def test_migration_number_not_reused(self):
        """迁移号永不复用：不得有第二个 V146__*。"""
        same = [p.name for p in _sql_files() if p.name.startswith(f"V{MIGRATION_VERSION}__")]
        assert same == [MIGRATION_FILE], (
            f"V{MIGRATION_VERSION} 被多个文件占用：{same}。"
            f"MigrationRunner 对同号会静默跳过其中一个"
        )

    def test_forward_is_idempotent_ddl(self):
        """幂等：必须 ADD COLUMN IF NOT EXISTS（MigrationRunner 铁律）。"""
        sql = _strip_sql_comments(
            (MIGRATIONS / MIGRATION_FILE).read_text(encoding="utf-8")
        )
        assert re.search(
            r"ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+suggestion_state",
            sql,
            re.I,
        ), "V146 未使用 ADD COLUMN IF NOT EXISTS ⇒ 二次应用会报错"

    def test_rollback_is_idempotent_ddl(self):
        sql = _strip_sql_comments(
            (MIGRATIONS / ROLLBACK_FILE).read_text(encoding="utf-8")
        )
        assert re.search(
            r"DROP\s+COLUMN\s+IF\s+EXISTS\s+suggestion_state", sql, re.I
        ), "R146 未使用 DROP COLUMN IF EXISTS"

    def test_forward_only_touches_target_table(self):
        """V146 不得顺带改别的表（additive 单点变更）。"""
        sql = _strip_sql_comments(
            (MIGRATIONS / MIGRATION_FILE).read_text(encoding="utf-8")
        )
        tables = {m.group(1).lower() for m in re.finditer(
            r"ALTER\s+TABLE\s+(?:public\.)?(\w+)", sql, re.I
        )}
        assert tables == {TABLE}, f"V146 触及了额外表：{sorted(tables)}"

    def test_column_is_jsonb(self):
        sql = _strip_sql_comments(
            (MIGRATIONS / MIGRATION_FILE).read_text(encoding="utf-8")
        )
        m = re.search(
            r"ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+suggestion_state\s+(\w+)", sql, re.I
        )
        assert m and m.group(1).upper() == "JSONB", (
            f"suggestion_state 类型应为 JSONB，实测 {m.group(1) if m else 'None'}"
        )


class TestOrmMigrationColumnParity:
    """ORM 列集 ≡ 迁移派生列集（方向可区分报错）。"""

    def test_orm_has_suggestion_state(self):
        cols = _orm_columns()
        assert "suggestion_state" in cols, (
            "ProcedureInstance 缺 suggestion_state 的 mapped_column ⇒ "
            "列在表里存在但代码写不进去（memory 已记铁律）"
        )

    def test_orm_column_is_jsonb(self):
        from app.models.procedure_models import ProcedureInstance

        col = ProcedureInstance.__table__.columns["suggestion_state"]
        assert "JSON" in type(col.type).__name__.upper(), (
            f"suggestion_state ORM 类型为 {type(col.type).__name__}，应为 JSONB"
        )
        assert col.nullable is True, "suggestion_state 必须可空（additive 列，存量行为 NULL）"

    def test_no_orm_column_missing_migration(self):
        """ORM 列 ⊆（迁移派生列 ∪ pre-migration 基线）。

        方向：ORM 多出 ⇒ 新增列没写迁移（表里没这列，写入静默失败）。
        `_PRE_MIGRATION_COLUMNS` 是本表**建表不在迁移体系内**这一历史事实的登记
        （见模块 docstring），不是逃逸阀 —— 它有条目上限与 stale 检测两道锁。
        """
        orm = _orm_columns() - _MIXIN_COLUMNS
        derived = derive_migration_columns() - _MIXIN_COLUMNS
        extra = orm - derived - _PRE_MIGRATION_COLUMNS
        assert not extra, (
            f"ORM 多出 {sorted(extra)} —— 这些列既无对应迁移也不在 pre-migration "
            f"基线内，写入时会因表里无该列而失败。若确为新增列请补迁移；"
            f"若确属早期建表遗留请在 _PRE_MIGRATION_COLUMNS 登记并说明依据"
        )

    def test_no_migration_column_missing_orm(self):
        """方向：迁移有而 ORM 缺 ⇒ 漏 `mapped_column`（列存在但代码写不进去）。"""
        orm = _orm_columns() - _MIXIN_COLUMNS
        derived = derive_migration_columns() - _MIXIN_COLUMNS
        missing = derived - orm
        assert not missing, (
            f"迁移有而 ORM 缺 {sorted(missing)} —— 列在表里存在但代码写不进去"
        )

    def test_pre_migration_baseline_is_exact_not_an_escape_hatch(self):
        """基线只许缩短、且每一条都必须仍然「不在迁移里」（stale 检测）。

        三道锁：
        1. **精确相等**而非子集 —— 往基线里多加一条（那正是要禁的动作）即打红
        2. 条目数封顶 —— 防把「补迁移」偷换成「加登记」
        3. stale：某列哪天真进了迁移，就必须从基线移出（否则登记变成永久盲区）
        """
        orm = _orm_columns() - _MIXIN_COLUMNS
        derived = derive_migration_columns() - _MIXIN_COLUMNS
        actual_gap = orm - derived
        assert actual_gap == _PRE_MIGRATION_COLUMNS, (
            f"pre-migration 基线与实际缺口不符。\n"
            f"  实际缺口：{sorted(actual_gap)}\n"
            f"  已登记  ：{sorted(_PRE_MIGRATION_COLUMNS)}\n"
            f"  基线多出（应移出）：{sorted(_PRE_MIGRATION_COLUMNS - actual_gap)}\n"
            f"  实际多出（应补迁移或登记）：{sorted(actual_gap - _PRE_MIGRATION_COLUMNS)}"
        )
        assert len(_PRE_MIGRATION_COLUMNS) <= _PRE_MIGRATION_CAP, (
            f"pre-migration 基线条目数 {len(_PRE_MIGRATION_COLUMNS)} 超上限 "
            f"{_PRE_MIGRATION_CAP} —— 新增列必须写迁移，不得往基线里加"
        )

    def test_suggestion_state_is_not_in_pre_migration_baseline(self):
        """反向自检：本 spec 新增的列必须靠迁移承载，不得混进历史基线。"""
        assert "suggestion_state" not in _PRE_MIGRATION_COLUMNS, (
            "suggestion_state 被登记进 pre-migration 基线 —— 它是 V146 新增列，"
            "登记进基线会让「迁移丢了」这件事永久静默"
        )
        assert "suggestion_state" in derive_migration_columns(), (
            "suggestion_state 不在迁移派生列集内 —— V146 可能被删或写坏"
        )


class TestPreMigrationBaselineLocks:
    """三道锁的自检 —— 证明 pre-migration 基线不会退化成「什么都放行」。

    基线常量的失效方式是「有人往里加一条就绕过了守卫」，故必须双向锁死：
    子集断言 + 条目数封顶 + stale 检测（基线里的列若不再属于 ORM 即打红）。
    """

    def test_baseline_is_subset_of_orm(self):
        """stale 检测：基线列必须仍是 ORM 的列。

        某列被从 ORM 删掉后若仍留在基线里，基线就成了永久盲区。
        """
        orm = _orm_columns()
        stale = _PRE_MIGRATION_COLUMNS - orm
        assert not stale, (
            f"基线里的 {sorted(stale)} 已不在 ORM 中 —— 请从 _PRE_MIGRATION_COLUMNS 移除；"
            f"留着会让这些列名成为永久豁免"
        )

    def test_baseline_count_is_capped(self):
        """条目数封顶且只许缩短：防「对不齐就往基线里加一条」。"""
        assert len(_PRE_MIGRATION_COLUMNS) <= _PRE_MIGRATION_CAP, (
            f"基线有 {len(_PRE_MIGRATION_COLUMNS)} 条，超过上限 "
            f"{_PRE_MIGRATION_CAP}。新增列必须写迁移，不是往基线里加一条。"
            f"上限本身只许下调"
        )
        assert _PRE_MIGRATION_CAP <= _CAP_CEILING, (
            f"上限被调高到 {_PRE_MIGRATION_CAP}（天花板 {_CAP_CEILING}）"
            f" —— 调高上限正是本守卫要禁止的动作"
        )

    def test_baseline_excludes_suggestion_state(self):
        """本任务新增的列绝不能进基线（否则等于自我豁免）。"""
        assert "suggestion_state" not in _PRE_MIGRATION_COLUMNS, (
            "suggestion_state 是本任务新增列，必须由 V146 派生而来，"
            "进基线等于绕过「新增列必须有迁移」这条判据"
        )

    def test_baseline_is_not_whole_orm(self):
        """反向自检：基线不得覆盖全部 ORM 列，否则比对恒真。"""
        orm = _orm_columns() - _MIXIN_COLUMNS
        assert _PRE_MIGRATION_COLUMNS != orm, (
            "基线等于 ORM 全集 ⇒ 「ORM 多出」判据恒真、永远抓不到漏迁移"
        )

    def test_parity_would_catch_undeclared_column(self):
        """替身自检：凭空多一个既不在基线也不在迁移里的列，必须被判红。"""
        orm = (_orm_columns() - _MIXIN_COLUMNS) | {"zzz_未声明列"}
        derived = derive_migration_columns() - _MIXIN_COLUMNS
        extra = orm - derived - _PRE_MIGRATION_COLUMNS
        assert extra == {"zzz_未声明列"}, (
            f"替身列未被判据捕获（实测 extra={sorted(extra)}）"
            f" —— 「ORM 多出」这条判据已失效"
        )


class TestSuggestionStateShape:
    """结构约定：五键（design Data Models）。"""

    EXPECTED_KEYS = {"reason_code", "rejected", "rejected_by", "rejected_at", "evidence"}

    def test_migration_documents_all_five_keys(self):
        raw = (MIGRATIONS / MIGRATION_FILE).read_text(encoding="utf-8")
        for k in self.EXPECTED_KEYS:
            assert k in raw, (
                f"V146 注释未说明键 {k} —— 结构约定必须随迁移留痕，"
                f"否则下个会话不知道这个 jsonb 该放什么"
            )

    def test_orm_documents_rationale_against_trim_schemes(self):
        """留痕「为何不落 procedure_trim_schemes.trim_data」，防后续会话搬家。"""
        src = (BACKEND / "app/models/procedure_models.py").read_text(encoding="utf-8")
        assert "procedure_trim_schemes" in src and "suggestion_state" in src, (
            "ORM 未留痕落点选择理由 —— 该判断来自实测（trim_data 是带日期的历史快照），"
            "不留痕会被重复提议搬家"
        )


def test_import_guard():
    """顶层不 import 生产模块（Wave 范式）：import 失败要 fail 而不是 collection error。"""
    try:
        from app.models.procedure_models import ProcedureInstance  # noqa: F401
    except Exception as e:  # pragma: no cover
        pytest.fail(f"ProcedureInstance 导入失败：{e}")
