# Feature: procedure-trimming-and-delegation-intelligence — Task 1（Wave 1 先打红）
"""B50 认定层次读取器的三字段扩展守卫 —— Wave 1「先打红」。

Task 1 / Requirements 1.1–1.5, 14.6。

## 断言分两类（防「全红分不清是功能未做还是守卫写坏」）

- **类 A = 独立口径判据**：守卫自己算出的事实（键形态判定 / 连库查询可执行 / 既有输出
  快照 / 反向自检）。**现在就应全绿** —— 绿了才证明判据基础设施有效而非空转，同时天然
  兑现「不拿被测函数证明自己」。
- **类 B = 被测实现**：`load_b50_accounts` 返回项须含 `balance` / `category` /
  `is_estimate` 三键。**现在应全红**，失败消息写明「尚未实现（Wave 1 Task 2）」。

## 🔴 spec 原文的反向自检样本不足以证明前缀锚定闸（本轮实证后修正）

tasks.md Task 1 写「移除 ``body == item_id`` 守卫后，``B50-T3-balance-货币资金`` 必须被
误判成矩阵格（证明该守卫是防误判的唯一保障）」。逐行读 `_parse_matrix_item_id` 后该措辞
**不成立** —— 它有三道**互相独立**的闸：

1. 前缀锚定 ``body == item_id`` → 非 ``B50-T3-matrix-`` 前缀直接 None
2. suffix 白名单 ``suffix not in _ASSERTION_SUFFIXES``
3. assertion 白名单 ``assertion not in ASSERTION_CN``

``B50-T3-balance-货币资金`` 的末段是 ``货币资金``，即便移除闸 1 也会被**闸 2** 挡住 ⇒ 该
样本证明不了闸 1 承重。故本守卫改用能**穿透闸 2/3** 的构造样本
``B50-T3-otherprefix-货币资金-existence-RMM``（末两段恰为合法 assertion + suffix），移除
闸 1 后它会被误判成矩阵格 ⇒ 闸 1 的承重性得证。

同时仍保留「四种新键在真实实现下一律 None」的正向断言（那是 Task 2 additive 扩展的前提）。

## 前端写入形态（实证 `useB50RiskMatrix.ts`，Task 2 解析必须按此）

| item_id | 值所在列 | 取值 |
|---|---|---|
| ``B50-T3-balance-{account}`` | **remark** | 数值字符串；空值写 ``None`` |
| ``B50-T3-category-{account}`` | **conclusion** | ``scot`` / ``amount_only`` / ``other``；空写 ``None`` |
| ``B50-T3-estimate-{account}`` | **conclusion** | ``Y`` / ``N``；空写 ``None`` |

⚠️ ``balance`` 走 remark 而另两个走 conclusion —— 照抄同一列会让三者有两个恒空。
"""
from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

# 🔴 有意不在模块顶层 import 生产模块：顶层 import 失败会让整个文件 collection error、
# 零断言执行，那时"全红"既可能是功能没做也可能是守卫自己写坏。改为测试内 try-import
# 后 pytest.fail（不是 skip —— skip 会让缺陷静默）。

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2]  # backend/
_READER_PATH = _BACKEND / "app" / "services" / "b50_risk_reader.py"

_NOT_IMPLEMENTED_HINT = "尚未实现（Wave 1 Task 2）。本条红是**预期**的 Wave 1 打红结果。"

# 前端确实在写、而后端 Task 2 之前完全不解析的三个键 + 本 spec 新增的完整性清单覆盖键。
_UNPARSED_KEYS = (
    "B50-T3-balance-货币资金",
    "B50-T3-category-货币资金",
    "B50-T3-estimate-货币资金",
    "B50-T3-cscope-L",
)


def _reader():
    """测试内 import；失败 fail 而非 skip。"""
    try:
        from app.services import b50_risk_reader as mod
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"无法 import app.services.b50_risk_reader: {e!r}")
    return mod


# ═══════════════════════════════════════════════════════════════════════════
# 替身 session：按 SQL 文本分流（load_b50_accounts 会先查 wp_index 再查 responses）
# ═══════════════════════════════════════════════════════════════════════════
class _FakeResult:
    def __init__(self, *, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar

    def fetchall(self):
        return self._rows


class _FakeSession:
    """只实现 `load_b50_accounts` 真实走到的两条查询。

    🔴 必须按 SQL 文本分流：同一个替身要区分「定位 B50 wp_id」与「拉 checklist_responses」，
    不分流会让其中一条拿到另一条的结果而**不报错**（表现为返回空列表 = 与"没数据"不可区分）。
    """

    def __init__(self, rows, *, wp_id: str | None = "wp-b50"):
        self._rows = rows
        self._wp_id = wp_id
        self.seen_sql: list[str] = []

    async def execute(self, stmt, params=None):  # noqa: ANN001
        sql = str(stmt)
        self.seen_sql.append(sql)
        if "wp_index" in sql:
            return _FakeResult(scalar=self._wp_id)
        if "checklist_responses" in sql:
            return _FakeResult(rows=self._rows)
        raise AssertionError(f"替身收到未预期的 SQL: {sql[:120]}")


def _row(item_id: str, conclusion=None, remark=None):
    return SimpleNamespace(item_id=item_id, conclusion=conclusion, remark=remark)


def _load(rows):
    mod = _reader()
    return asyncio.run(mod.load_b50_accounts(_FakeSession(rows), "p-1"))


def _by_account(items: list[dict]) -> dict[str, dict]:
    return {it["account"]: it for it in items}


# ═══════════════════════════════════════════════════════════════════════════
# 类 A-1：模块与函数齐备（现在应绿）
# ═══════════════════════════════════════════════════════════════════════════
def test_reader_module_and_symbols_available():
    mod = _reader()
    for name in ("load_b50_accounts", "_parse_matrix_item_id", "ASSERTION_CN", "_ASSERTION_SUFFIXES"):
        assert hasattr(mod, name), f"b50_risk_reader 缺少 {name}"
    assert _READER_PATH.exists(), f"读取器源码路径不存在: {_READER_PATH}"


def test_assertion_domain_is_six_cn_assertions():
    """六认定取值域冻结 —— 完整性豁免判据（W2）读的正是 ``cells['completeness']``。"""
    mod = _reader()
    assert set(mod.ASSERTION_CN) == {
        "existence",
        "completeness",
        "accuracy",
        "cutoff",
        "classification",
        "presentation",
    }
    assert mod.ASSERTION_CN["completeness"] == "完整性"


# ═══════════════════════════════════════════════════════════════════════════
# 类 A-2：新键一律不被矩阵解析器接受（现在应绿）
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("item_id", _UNPARSED_KEYS)
def test_parse_matrix_rejects_scope_and_cscope_keys(item_id):
    mod = _reader()
    assert mod._parse_matrix_item_id(item_id) is None, (
        f"{item_id} 被误判成矩阵格 —— 会污染 cells 并让 max_risk/has_special 出错"
    )


def test_parse_matrix_accepts_real_matrix_key():
    """正样本 —— 证明上一条不是「解析器对什么都返回 None」的空转。"""
    mod = _reader()
    got = mod._parse_matrix_item_id("B50-T3-matrix-货币资金-completeness-RMM")
    assert got == ("货币资金", "completeness", "RMM")


def test_cscope_key_is_silently_skipped_by_all_branches():
    """``B50-T3-cscope-{cycle}``（W2 完整性清单项目覆盖落点）不得被任何分支解析成科目。

    这是 design 选它作持久化落点的前提：与 B50 同生命周期 + 零迁移 + 不污染既有解析。
    """
    items = _load([
        _row("B50-T3-cycle-货币资金", conclusion="E"),
        _row("B50-T3-cscope-L", conclusion="on"),
        _row("B50-T3-cscope-J", conclusion="off"),
    ])
    names = {it["account"] for it in items}
    assert names == {"货币资金"}, f"cscope 键被解析成科目: {sorted(names)}"


# ═══════════════════════════════════════════════════════════════════════════
# 类 A-3：反向自检 —— 前缀锚定闸承重（现在应绿）
# ═══════════════════════════════════════════════════════════════════════════
_PREFIX_GUARD_SRC = "    if body == item_id:\n        return None\n"


def _mutant_without_prefix_anchor():
    """把 `_parse_matrix_item_id` 的前缀锚定闸切掉，返回变体函数。

    读真实源码做替换（不手写副本），故守卫形态变化时会立刻打红提醒同步。
    """
    mod = _reader()
    src = inspect.getsource(mod._parse_matrix_item_id)
    assert _PREFIX_GUARD_SRC in src, (
        "前缀锚定闸的源码形态已变，反向自检需同步更新（原形态：if body == item_id: return None）"
    )
    ns = {"ASSERTION_CN": mod.ASSERTION_CN, "_ASSERTION_SUFFIXES": mod._ASSERTION_SUFFIXES}
    exec(compile(src.replace(_PREFIX_GUARD_SRC, ""), "<mutant>", "exec"), ns)  # noqa: S102
    return ns["_parse_matrix_item_id"]


# 末两段恰为合法 assertion + suffix ⇒ 能穿透 suffix/assertion 两道白名单闸，
# 唯一挡住它的就是前缀锚定闸。
_PENETRATING_SAMPLE = "B50-T3-otherprefix-货币资金-existence-RMM"


def test_prefix_anchor_guard_is_load_bearing():
    """移除前缀锚定闸后，非 matrix 前缀的键会被误判成矩阵格 ⇒ 闸 1 承重。

    🔴 误判的**形态**是 account 段吞进整个前缀（`B50-T3-otherprefix-货币资金`）而不是
    纯科目名 —— 因为 `_parse_matrix_item_id` 只从右往左切两段（suffix / assertion），
    剩余部分**整段**当 account。故断言写「== ('货币资金', ...)」会假红（那是对误判形态
    的错误预期）；正确判据 = 「返回非 None」+「account 段被前缀污染」。
    """
    mod = _reader()
    assert mod._parse_matrix_item_id(_PENETRATING_SAMPLE) is None, "前缀锚定闸已失效"
    mutant = _mutant_without_prefix_anchor()
    got = mutant(_PENETRATING_SAMPLE)
    assert got is not None, (
        "移除前缀锚定闸后该样本仍未被误判 ⇒ 该反向自检已失去证明力，需换穿透样本"
    )
    account, assertion, suffix = got
    assert (assertion, suffix) == ("existence", "RMM"), (
        f"穿透样本的末两段应被解析为合法 assertion+suffix，实得 {(assertion, suffix)}"
    )
    # 误判形态：account 段吞进了本不属于科目名的前缀
    assert account == "B50-T3-otherprefix-货币资金", (
        f"误判形态已变（account 段实得 {account!r}）；请复核该反向自检是否仍证明闸 1 承重"
    )
    assert account != "货币资金", "account 段未被污染 ⇒ 说明另有闸在挡，本自检无证明力"


def test_spec_sample_is_blocked_by_suffix_whitelist_not_prefix_anchor():
    """如实登记：spec 原文举的 balance 样本被**闸 2** 挡住，证明不了闸 1。

    这条断言存在的意义是防止后续会话按 tasks.md 原文把反向自检改回那个样本（改回去
    会得到"移除闸 1 仍返回 None"的假绿结论，进而误判闸 1 可删）。
    """
    mutant = _mutant_without_prefix_anchor()
    assert mutant("B50-T3-balance-货币资金") is None


# ═══════════════════════════════════════════════════════════════════════════
# 类 A-4：既有三类键输出快照冻结（Task 2 的零回归基线，现在应绿）
# ═══════════════════════════════════════════════════════════════════════════
_LEGACY_ROWS = [
    _row("B50-T3-cycle-应收账款", conclusion="D"),
    _row("B50-T3-plan-应收账款-reliance", conclusion="部分信赖"),
    _row("B50-T3-plan-应收账款-subonly", conclusion="N"),
    _row("B50-T3-plan-应收账款-approach", conclusion="combined"),
    _row("B50-T3-matrix-应收账款-existence-RMM", conclusion="M"),
    _row("B50-T3-matrix-应收账款-completeness-RMM", conclusion="H"),
    _row("B50-T3-matrix-应收账款-completeness-SR", conclusion="Y"),
    _row("B50-T3-matrix-应收账款-accuracy-IR", conclusion="H"),  # IR 不落 cells 的 rmm
    _row("B50-T3-cycle-管理层凌驾控制", conclusion="pervasive"),
]

_LEGACY_EXPECTED = {
    "应收账款": {
        "cycle": "D",
        "reliance": "部分信赖",
        "substantive_only": "N",
        "approach": "combined",
        "max_risk": "H",
        "has_special": True,
        "cells": {
            "existence": {"rmm": "M", "special": False},
            "completeness": {"rmm": "H", "special": True},
            "accuracy": {"rmm": None, "special": False},
        },
    },
    "管理层凌驾控制": {
        "cycle": "pervasive",
        "reliance": None,
        "substantive_only": None,
        "approach": None,
        "max_risk": None,
        "has_special": True,  # CAS：管理层凌驾控制恒为特别风险
        "cells": {},
    },
}


def test_legacy_three_key_families_output_frozen():
    """cycle / plan / matrix 三个分支的输出逐字段冻结 —— Task 2 必须逐字不动它们。"""
    got = _by_account(_LOAD_LEGACY := _load(_LEGACY_ROWS))
    assert set(got) == set(_LEGACY_EXPECTED), f"科目集合漂移: {sorted(got)}"
    for name, exp in _LEGACY_EXPECTED.items():
        actual = got[name]
        for key, val in exp.items():
            assert actual[key] == val, f"{name}.{key}: 期望 {val!r} 实得 {actual[key]!r}"


def test_ir_cr_suffixes_do_not_set_rmm():
    """IR/CR 只建 cell 不写 rmm —— 该行为是既有语义，Task 2 不得改动。"""
    got = _by_account(_load([
        _row("B50-T3-matrix-存货-existence-IR", conclusion="H"),
        _row("B50-T3-matrix-存货-existence-CR", conclusion="H"),
    ]))
    assert got["存货"]["cells"]["existence"] == {"rmm": None, "special": False}
    assert got["存货"]["max_risk"] is None


# ═══════════════════════════════════════════════════════════════════════════
# 类 A-5：连库判据（现在应绿）—— 独立口径查询可执行
#
# 全库 `B50-T3-*` 实测 0 行，故断言按「查询可执行且返回 ≥0」而非「必须有数据」。
# 🔴 一次 asyncio.run 取完全部快照：连接池绑定首个事件循环，每个测试各自 async 会让
#    第二个起报 "Event loop is closed"；且必须用一次性 NullPool 引擎，借共享池会双向污染。
# ═══════════════════════════════════════════════════════════════════════════
_SCOPE_KEY_SQL = """
SELECT
  count(*) FILTER (WHERE item_id LIKE 'B50-T3-balance-%')  AS balance_rows,
  count(*) FILTER (WHERE item_id LIKE 'B50-T3-category-%') AS category_rows,
  count(*) FILTER (WHERE item_id LIKE 'B50-T3-estimate-%') AS estimate_rows,
  count(*) FILTER (WHERE item_id LIKE 'B50-T3-cscope-%')   AS cscope_rows,
  count(*) FILTER (WHERE item_id LIKE 'B50-T3-matrix-%')   AS matrix_rows,
  count(*) FILTER (WHERE item_id LIKE 'B50-T3-%')          AS all_t3_rows
FROM checklist_responses
"""


def _live_scope_counts():
    """独立 SQL 统计四类新键 + 矩阵键的真实行数（不经被测函数）。"""
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool

        from app.core.config import settings
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"连库依赖不可用: {e!r}")

    async def _run():
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                row = (await conn.execute(sa.text(_SCOPE_KEY_SQL))).one()
                return dict(row._mapping)
        finally:
            await engine.dispose()

    try:
        return asyncio.run(_run())
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"真实库不可达（本条为连库判据）: {e!r}")


def test_live_scope_key_counts_query_is_executable():
    counts = _live_scope_counts()
    for key in ("balance_rows", "category_rows", "estimate_rows", "cscope_rows", "matrix_rows", "all_t3_rows"):
        assert key in counts, f"统计缺列 {key}"
        assert counts[key] >= 0
    # 如实登记真实库现状（全库 B50-T3-* 为 0 行是**真实业务状态**，不是接线缺陷）
    print(f"[live] B50-T3 键分布: {counts}")


def test_live_scope_keys_never_exceed_all_t3_rows():
    """自洽性：四类新键 + 矩阵键之和不可能超过 `B50-T3-%` 总数（证明 SQL 谓词无误）。"""
    c = _live_scope_counts()
    subset = c["balance_rows"] + c["category_rows"] + c["estimate_rows"] + c["cscope_rows"] + c["matrix_rows"]
    assert subset <= c["all_t3_rows"], f"子集计数 {subset} > 总数 {c['all_t3_rows']}，SQL 谓词有误"


# ═══════════════════════════════════════════════════════════════════════════
# 类 B：被测实现（Task 2 之前应全红）
# ═══════════════════════════════════════════════════════════════════════════
_SCOPE_ROWS = [
    _row("B50-T3-cycle-货币资金", conclusion="E"),
    _row("B50-T3-balance-货币资金", remark="1234567.89"),
    _row("B50-T3-category-货币资金", conclusion="scot"),
    _row("B50-T3-estimate-货币资金", conclusion="N"),
]


@pytest.mark.parametrize("field", ["balance", "category", "is_estimate"])
def test_returned_item_has_scope_field(field):
    got = _by_account(_load(_SCOPE_ROWS))
    item = got.get("货币资金")
    assert item is not None, "货币资金未出现在返回中"
    assert field in item, f"返回项缺少 `{field}` 键 —— {_NOT_IMPLEMENTED_HINT}"


def test_balance_parsed_from_remark_as_float():
    """🔴 `balance` 的值在 **remark**（数值字符串），不在 conclusion。"""
    got = _by_account(_load(_SCOPE_ROWS))
    item = got.get("货币资金", {})
    assert item.get("balance") == pytest.approx(1234567.89), (
        f"balance 应从 remark 解析为 float，实得 {item.get('balance')!r} —— {_NOT_IMPLEMENTED_HINT}"
    )


def test_category_and_estimate_parsed_from_conclusion():
    """🔴 `category` / `is_estimate` 的值在 **conclusion**，与 balance 不同列。"""
    got = _by_account(_load(_SCOPE_ROWS))
    item = got.get("货币资金", {})
    assert item.get("category") == "scot", (
        f"category 应从 conclusion 解析，实得 {item.get('category')!r} —— {_NOT_IMPLEMENTED_HINT}"
    )
    assert item.get("is_estimate") == "N", (
        f"is_estimate 应从 conclusion 解析，实得 {item.get('is_estimate')!r} —— {_NOT_IMPLEMENTED_HINT}"
    )


def test_unset_scope_fields_are_none_not_zero_or_empty_string():
    """未录入必须是 `None` —— `0` 会被重要性判据当「余额为 0」而误裁（宁缺勿造）。"""
    got = _by_account(_load([_row("B50-T3-cycle-存货", conclusion="F")]))
    item = got.get("存货", {})
    for field in ("balance", "category", "is_estimate"):
        assert field in item, f"返回项缺少 `{field}` 键 —— {_NOT_IMPLEMENTED_HINT}"
        assert item[field] is None, (
            f"{field} 未录入时应为 None，实得 {item[field]!r}"
            f"（0/'' 会与「确实为 0」不可区分）"
        )


def test_unparseable_balance_falls_back_to_none():
    """非数字 remark 不得抛异常也不得写 0 —— 只能是 None。"""
    got = _by_account(_load([
        _row("B50-T3-cycle-存货", conclusion="F"),
        _row("B50-T3-balance-存货", remark="待补充"),
    ]))
    item = got.get("存货", {})
    assert "balance" in item, f"返回项缺少 `balance` 键 —— {_NOT_IMPLEMENTED_HINT}"
    assert item["balance"] is None, f"非数字 remark 应回退 None，实得 {item['balance']!r}"


def test_scope_key_alone_creates_account_entry():
    """只填了余额、未填循环/矩阵的科目也要出现在返回中（否则重要性判据看不到它）。"""
    got = _by_account(_load([_row("B50-T3-balance-预付款项", remark="500")]))
    assert "预付款项" in got, (
        f"仅有 balance 键的科目未被建项 —— {_NOT_IMPLEMENTED_HINT}"
    )
    assert got["预付款项"].get("balance") == pytest.approx(500.0)


def test_scope_fields_do_not_disturb_legacy_output():
    """三键与既有三类键混合时，既有字段输出与纯 legacy 场景逐字段相同（零回归）。"""
    legacy_only = _by_account(_load(_LEGACY_ROWS))
    mixed = _by_account(_load(_LEGACY_ROWS + [
        _row("B50-T3-balance-应收账款", remark="88888"),
        _row("B50-T3-category-应收账款", conclusion="amount_only"),
        _row("B50-T3-estimate-应收账款", conclusion="Y"),
    ]))
    assert set(mixed) == set(legacy_only), "混入 scope 键后科目集合变了"
    for name, exp in _LEGACY_EXPECTED.items():
        for key, val in exp.items():
            assert mixed[name][key] == val, (
                f"混入 scope 键后 {name}.{key} 被改动：期望 {val!r} 实得 {mixed[name][key]!r}"
            )
