"""四表库取数入口 —— 三条铁律**行为**守卫 + merge 不覆盖守卫（Task 6）.

spec: .kiro/specs/four-table-extraction-entry-completion/  (Task 6, Requirements 6.1, 6.2)
Properties: 1（active dataset 过滤不翻倍）/ 2（单一 aux_type 归集）/ 3（merge 不覆盖）

🔴 本文件断言的是**行为**而非"函数存在"（平台假绿三源之一：grep 式守卫只查字符串存在，
改成 `if False:` / 删调用 / 改名残留仍绿）。做法：

  * Property 1 / 2 用一个**会评估已编译 SQL 谓词**的假会话 `_SqlAwareSession`：它把
    `aggregate_aux_by_name_ex` 真正 emit 的 `sa.select(...)` 编译成文本，按其中是否含
    `dataset_id =`（active 过滤）与 `aux_type =`（维度锁定）谓词决定返回多少行、聚合到
    哪个维度。→ 去掉 `active_filter,` 会让金额**翻倍**（≥2×），去掉 `aux_type == aux_type`
    会让 `sum(closing)` 变成**跨全部 aux_type 的合计**。两者都能被本守卫的断言逮到，
    而不是靠"函数是否被调用"。
  * Property 3 直接对 D3 端点使用的 merge 逻辑做**字节级**断言：已有业务键行逐字节不变、
    只追加新键；overwrite 只能由显式参数驱动。

配套变异脚本：`backend/scripts/diagnose/mutate_four_table_entry_guards.py`
（锚点：去 active filter · 去 aux_type 锁定 · merge→overwrite；四态判定）。
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from app.services.four_table.aux_aggregation import aggregate_aux_by_name_ex


def _run(coro):
    return asyncio.run(coro)


# ─────────────────────────────────────────────────────────────────────────────
# SQL-aware 假会话：真正编译 `_ex` emit 的 select，按谓词存在与否模拟一张
# in-memory tb_aux_balance。这样守卫断言的是"SQL 真的带了那条谓词并因此改变了
# 聚合结果"，去掉谓词（变异）必然改变数字 → 守卫必红。
# ─────────────────────────────────────────────────────────────────────────────

# 单一账户 1221 挂两个 aux_type（客户 / 成本中心），且 active 数据集有两份冗余
# 副本（dataset A=active, dataset B=旧版本）。这是平台记录的两类双算来源：
#   ① 不按 active dataset 过滤 → A+B 双算（2×）
#   ② 不锁单一 aux_type → 客户+成本中心 双算（跨维度合计）
_ACTIVE_DATASET = "dataset-A-active"
_STALE_DATASET = "dataset-B-stale"

# (aux_type, aux_name, opening, debit, credit, closing, dataset_id)
_AUX_ROWS = [
    # 客户 维度（active 副本）
    ("客户", "甲公司", 100.0, 10.0, 0.0, 110.0, _ACTIVE_DATASET),
    ("客户", "乙公司", 50.0, 0.0, 0.0, 50.0, _ACTIVE_DATASET),
    # 客户 维度（stale 副本 —— 只有不过滤 active 时才会被算进来 → 双算）
    ("客户", "甲公司", 100.0, 10.0, 0.0, 110.0, _STALE_DATASET),
    ("客户", "乙公司", 50.0, 0.0, 0.0, 50.0, _STALE_DATASET),
    # 成本中心 维度（active 副本 —— 只有不锁 aux_type 时才会被算进来 → 跨维度双算）
    ("成本中心", "A中心", 999.0, 0.0, 0.0, 999.0, _ACTIVE_DATASET),
]

# 客户维度、active 副本的期末合计（正确结果） = 110 + 50
_CORRECT_CLOSING_SUM = 160.0
# 不过滤 active（含 stale 副本）→ 客户维度期末合计翻倍 = 320
_DOUBLED_BY_DATASET = 320.0
# 客户维度 active 户数
_CORRECT_UNITS = 2


class _RowsResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _SqlAwareSession:
    """按已编译 SQL 的谓词决定聚合结果的假会话。

    `_ex` 会 emit 两跳查询：
      跳1  GROUP BY aux_type  → 返回维度候选 (aux_type, n, amt)
      跳2  GROUP BY aux_name  → 返回锁定维度后的归集行

    本会话把 stmt 编译成字符串，判断：
      * 是否含 active dataset 谓词（`dataset_id`）—— 缺失=去了 active filter；
      * 跳2 是否含 `aux_type` 等值谓词 —— 缺失=去了维度锁定。
    据此从 `_AUX_ROWS` 过滤/聚合，模拟真库对该谓词的响应。
    """

    def __init__(self):
        self._calls = 0
        self.compiled_sql_log: list[str] = []

    async def execute(self, stmt, params=None):
        self._calls += 1
        sql_text = str(
            stmt.compile(compile_kwargs={"literal_binds": False})
        )
        self.compiled_sql_log.append(sql_text)

        has_active = "dataset_id" in sql_text
        # 跳2 才可能带 aux_type 等值锁；跳1 是对 aux_type 的 GROUP BY（不算锁定）。
        # 用 "aux_type =" / "aux_type IN" 之类等值/绑定谓词识别锁定。
        # 编译后维度锁定谓词形如 `tb_aux_balance.aux_type = :aux_type_1`。
        locks_aux_type = "aux_type =" in sql_text or "aux_type IN" in sql_text

        # active 过滤：缺谓词时把 stale 副本也算进来
        def _visible(row):
            _t, _n, _o, _d, _c, _cl, ds = row
            if has_active:
                return ds == _ACTIVE_DATASET
            return True  # 去了 active filter → active + stale 都可见（双算源①）

        rows = [r for r in _AUX_ROWS if _visible(r)]

        if self._calls == 1:
            # 跳1：GROUP BY aux_type
            agg: dict[str, list[float]] = {}
            for t, _n, _o, _d, _c, cl, _ds in rows:
                slot = agg.setdefault(t, [0, 0.0])
                slot[0] += 1
                slot[1] += abs(cl)
            return _RowsResult(
                SimpleNamespace(aux_type=t, n=int(v[0]), amt=float(v[1]))
                for t, v in agg.items()
            )

        # 跳2：GROUP BY aux_name。若 SQL 锁定了单一 aux_type，只算「客户」；
        # 否则跨全部 aux_type 合计（双算源②）。
        if locks_aux_type:
            rows = [r for r in rows if r[0] == "客户"]
        by_name: dict[str, list[float]] = {}
        for _t, n, o, d, c, cl, _ds in rows:
            slot = by_name.setdefault(n, [0.0, 0.0, 0.0, 0.0])
            slot[0] += o
            slot[1] += d
            slot[2] += c
            slot[3] += cl
        out = [
            SimpleNamespace(aux_name=name, opening=v[0], debit=v[1], credit=v[2], closing=v[3])
            for name, v in sorted(by_name.items())
        ]
        return _RowsResult(out)

    async def rollback(self):
        pass


@pytest.fixture(autouse=True)
def _stub_active_filter(monkeypatch):
    """`get_active_filter` 涉及真库，替换为一个仍 emit `dataset_id =` 谓词的假实现。

    关键：假实现返回的谓词里必须含 `dataset_id`，这样一旦生产代码去掉
    `active_filter,`，编译出的 SQL 就不再含 `dataset_id`，`_SqlAwareSession`
    据此放行 stale 副本 → 金额翻倍 → 守卫必红。
    """
    import app.services.dataset_query as dq
    import sqlalchemy as sa
    from app.models.audit_platform_models import TbAuxBalance

    async def _fake_active_filter(db, table, project_id, year, **kw):
        # 返回带 dataset_id 等值谓词的条件（模拟"已锁定 active dataset"）。
        return sa.and_(
            TbAuxBalance.is_deleted == sa.false(),
            TbAuxBalance.dataset_id == _ACTIVE_DATASET,
        )

    monkeypatch.setattr(dq, "get_active_filter", _fake_active_filter, raising=True)


# ── 铁律 ① active dataset 过滤：金额不翻倍（Property 1）──────────────────────

def test_iron_law_1_active_filter_does_not_double_amount():
    """当前实现（带 active_filter）：客户维度期末合计 = 160（单副本），非 320（双算）。

    行为断言：`_SqlAwareSession` 看到 SQL 含 `dataset_id` 谓词 → 只放行 active 副本。
    若生产代码去掉 `active_filter,`（变异 M1），SQL 不再含 `dataset_id` →
    stale 副本被算进来 → 合计变 320 → 本断言必红。
    """
    session = _SqlAwareSession()
    res = _run(aggregate_aux_by_name_ex(session, "p", 2025, ["1221"]))

    closing_sum = sum(e.closing for e in res.entries)
    assert closing_sum == _CORRECT_CLOSING_SUM, (
        f"active dataset 过滤失效：期末合计应为 {_CORRECT_CLOSING_SUM}（单副本），"
        f"实际 {closing_sum}（{_DOUBLED_BY_DATASET} 说明 stale 副本被双算）"
    )
    assert closing_sum != _DOUBLED_BY_DATASET, "金额翻倍 = active dataset 谓词丢失"
    # 行为佐证：emit 的 SQL 确实带 active dataset 谓词（非仅"函数存在"）
    assert any("dataset_id" in s for s in session.compiled_sql_log), (
        "emit 的 SQL 未包含 active dataset 谓词"
    )


# ── 铁律 ② 单一 aux_type 锁定：结果只来自一个维度（Property 2）───────────────

def test_iron_law_2_single_aux_type_lock():
    """当前实现（带 aux_type 锁定）：`sum(closing)` = 客户维度合计 160，
    不等于跨全部 aux_type 的合计（客户 160 + 成本中心 999 = 1159）。

    行为断言：`_SqlAwareSession` 跳2 看到 SQL 含 `aux_type =` 等值谓词 → 只算客户。
    若生产代码去掉 `TbAuxBalance.aux_type == aux_type`（变异 M2），跳2 SQL 不再含
    该等值谓词 → 跨维度合计（含成本中心 999）→ 本断言必红。
    """
    session = _SqlAwareSession()
    res = _run(aggregate_aux_by_name_ex(session, "p", 2025, ["1221"]))

    assert res.aux_type == "客户", f"应锁定含往来单位关键词的「客户」维度，实际 {res.aux_type}"
    closing_sum = sum(e.closing for e in res.entries)
    cross_aux_total = 160.0 + 999.0  # 客户 + 成本中心（未锁维度时的错误合计）
    assert closing_sum == _CORRECT_CLOSING_SUM, (
        f"单一 aux_type 锁定失效：应只来自「客户」维度 = {_CORRECT_CLOSING_SUM}，"
        f"实际 {closing_sum}（{cross_aux_total} 说明混入了成本中心）"
    )
    assert closing_sum != cross_aux_total, "结果混入了其它 aux_type = 维度锁定丢失"
    # 归集行里不得出现成本中心的单位「A中心」
    assert "A中心" not in {e.aux_name for e in res.entries}
    # 行为佐证：跳2 emit 的 SQL 确实带 aux_type 等值锁
    hop2 = session.compiled_sql_log[-1]
    assert "aux_type =" in hop2 or "aux_type IN" in hop2, (
        "跳2 emit 的 SQL 未锁定单一 aux_type"
    )


# ── 铁律 ③ 前缀匹配命中子科目（非精确等值）────────────────────────────────

def test_iron_law_3_prefix_like_matches_sub_accounts():
    """前缀 `2203` 用 LIKE 命中子科目 `2203.01`（证明非精确等值 `= '2203'`）。

    直接断言 `_prefix_predicate` emit 的是 `LIKE '2203%'`；若改成精确等值，
    `2203.01` 这类子科目将匹配不到（账套里科目通常落在子科目）。
    """
    import sqlalchemy as sa
    from app.services.four_table.aux_aggregation import _prefix_predicate

    pred = _prefix_predicate(sa.column("account_code"), ["2203"])
    sql = str(pred.compile(compile_kwargs={"literal_binds": True}))
    assert "LIKE" in sql.upper(), f"前缀匹配必须用 LIKE（命中子科目），实际 SQL: {sql}"
    assert "2203%" in sql, f"LIKE 模式必须是前缀通配 '2203%%'，实际 SQL: {sql}"
    # 反证：精确等值不会出现 % 通配
    assert "= '2203'" not in sql, "科目匹配退化为精确等值 = 命中不到子科目"


# ─────────────────────────────────────────────────────────────────────────────
# 铁律 merge 不覆盖（Property 3）—— 驱动**生产** D3 端点 `d3_import_aux_balance`
# 的真实 merge 路径，捕获它 emit 给 INSERT 的 `remark` 载荷做字节级断言。
#
# 生产 merge 见 `_d3_import_export.d3_import_aux_balance`：
#     existing_names = {r.get("customerName", "") for r in existing_rows}
#     new_rows = [r for r in rows_data if r["customerName"] not in existing_names]
#     merged = existing_rows + new_rows
# 变异脚本对生产的 `new_rows = [...]` 行做 merge→overwrite（`new_rows = rows_data`），
# 此守卫据「捕获的 remark 里已有手工行被冲掉/重复」必红（断言的是生产行为，非本地副本）。
# ─────────────────────────────────────────────────────────────────────────────

from app.services.four_table.aux_aggregation import AuxEntry  # noqa: E402


class _D3EndpointSession:
    """驱动生产 `d3_import_aux_balance` 的假会话，按 SQL 文本区分三跳并捕获写入载荷。

    跳序：
      1. SELECT wp.project_id, p.audit_year ...     → 返回 wp_row
      2. SELECT remark FROM checklist_responses ... → 返回已有行（含手工行）
      3. INSERT ... ON CONFLICT ... DO UPDATE       → 捕获 merge 后的 remark
    `aggregate_d_cycle_aux` 由测试 monkeypatch 掉（不查真库、不解析报表映射）。
    """

    def __init__(self, existing_rows: list[dict]):
        self._existing_remark = json.dumps(existing_rows, ensure_ascii=False)
        self.captured_remark: str | None = None
        self.committed = False

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "audit_year" in sql:
            return _RowsResult([SimpleNamespace(project_id="proj-1", audit_year=2025)])
        if "SELECT remark" in sql:
            return _RowsResult([SimpleNamespace(remark=self._existing_remark)])
        if "INSERT INTO checklist_responses" in sql:
            self.captured_remark = (params or {}).get("remark")
            return _RowsResult([])
        return _RowsResult([])

    async def commit(self):
        self.committed = True

    async def rollback(self):
        pass


def _drive_d3_merge(existing_rows: list[dict], incoming_names: list[str], monkeypatch) -> list[dict]:
    """调用生产 D3 端点，返回它写库前 merge 出的行（从捕获的 remark 反序列化）。"""
    import app.routers.wp_render_strategies._d3_import_export as d3mod
    from app.services.d_cycle_extraction.d_aux_import import DAuxImportResult

    async def _fake_agg(db, project_id, year, wp_code):
        entries = [AuxEntry(nm, 0.0, 0.0, 0.0, 0.0) for nm in incoming_names]
        return DAuxImportResult(entries, "客户", "ok", ["2203"], "BS-046", "report_config")

    # `d3_import_aux_balance` 在函数体内 `from ...d_aux_import import aggregate_d_cycle_aux`，
    # 故 patch 源模块 d_aux_import 上的名字。
    import app.services.d_cycle_extraction.d_aux_import as dai
    monkeypatch.setattr(dai, "aggregate_d_cycle_aux", _fake_agg, raising=True)

    session = _D3EndpointSession(existing_rows)
    _run(d3mod.d3_import_aux_balance("wp-1", db=session, current_user=object()))
    assert session.captured_remark is not None, "端点未写入 remark（merge 路径未执行）"
    return json.loads(session.captured_remark)


def test_merge_keeps_existing_rows_byte_for_byte(monkeypatch):
    """生产 D3 端点：已存在业务键（customerName）行逐字节不变，只追加新键。"""
    existing = [
        {"rowId": "r-1", "customerName": "甲公司", "priorUnadjusted": 100.0, "note": "手工改过"},
        {"rowId": "r-2", "customerName": "乙公司", "priorUnadjusted": 50.0},
    ]
    existing_snapshot = json.dumps(existing, ensure_ascii=False, sort_keys=True)

    # 归集回来「甲公司」(同键) + 「丙公司」(新键)
    merged = _drive_d3_merge(existing, ["甲公司", "丙公司"], monkeypatch)

    # 已有两行逐字节不变（顺序、字段、值都不变）
    assert json.dumps(merged[:2], ensure_ascii=False, sort_keys=True) == existing_snapshot
    # 甲公司 未被归集行覆盖（仍是手工的 100.0 / r-1 / note）
    jia = next(r for r in merged if r["customerName"] == "甲公司")
    assert jia["priorUnadjusted"] == 100.0 and jia["rowId"] == "r-1" and jia["note"] == "手工改过"
    # 只追加新键 丙公司，未重复追加同键 甲公司
    names = [r["customerName"] for r in merged]
    assert names == ["甲公司", "乙公司", "丙公司"], f"merge 应只追加新键，实际 {names}"
    assert len(merged) == 3


def test_merge_does_not_overwrite_on_duplicate_key(monkeypatch):
    """生产 D3 端点：全部为已存在键时 merge 结果 == 原表（0 追加、0 覆盖）。

    若把生产 merge 改成 overwrite（`new_rows = rows_data`），归集回来的同键行会被
    追加/冲掉手工行，此断言必红。
    """
    existing = [
        {"rowId": "r-1", "customerName": "甲公司", "priorUnadjusted": 100.0},
        {"rowId": "r-2", "customerName": "乙公司", "priorUnadjusted": 50.0},
    ]
    before = json.dumps(existing, ensure_ascii=False, sort_keys=True)

    # 归集回来全是已有键 —— 正确 merge 下应 0 追加
    merged = _drive_d3_merge(existing, ["甲公司", "乙公司"], monkeypatch)
    assert json.dumps(merged, ensure_ascii=False, sort_keys=True) == before, (
        "全部为已有键时 merge 不得改变原表（overwrite 会冲掉/重复手工行）"
    )
