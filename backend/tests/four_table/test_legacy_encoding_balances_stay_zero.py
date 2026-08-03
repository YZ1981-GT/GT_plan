"""数据触发型守卫：旧制《企业会计制度》(2001) 编码不得带非零余额。

**为什么是守卫而不是迁移**（2026-08-03 定向名单实证结论）

`account_chart` / `trial_balance` / `tb_balance` 在同一个 `source='standard'` 下
**并存两套编码体系**：

- 旧《企业会计制度》(2001)：`3xxx` 权益 / `4xxx` 成本 / `5xxx` 损益
- CAS 2006：`3xxx` **共同类**（衍生工具 / 套期工具）/ `4xxx` 权益 /
  `5xxx` **成本类**（生产成本 / 制造费用 / 研发支出）/ `6xxx` 损益

N4(`6403`) · N5(`6801`) · F5(`6401`/`6402`/`6404`) 与 M 循环的取数**硬编码 CAS 2006 码**。
它们当前不少算，**唯一依据是「旧制码在两张余额表里几乎全是零余额骨架行」**
（当期/审定口径实测：`trial_balance` 170 行仅 1 行非零、`tb_balance` 357 行 0 行非零）。
这是**当前数据的性质，不是不变量** —— 一旦某项目在 `5401 主营业务成本` /
`5801 所得税费用` / `3201 利润分配` 上出现真余额，那些策略会**静默少算**
（不抛异常、不打红、溯源面板也看不出）。

故本 spec 把批量语义迁移**判定为不该做**（买不到东西 + 会丢 listed/soe 变体行号 +
下游属性不兼容），改立本守卫：**把「该迁移了」这个判断交给数据，而不是靠猜**。
本文件一旦打红，就是启动 N4/N5/F5/M 语义迁移的信号。

**白名单为什么必须按「码 + 科目名」两元组**

`^(3\\d{3}|5\\d{3})` 同时命中两套体系：同一个 `3201` 在旧制是「利润分配」（权益）、
在 CAS 2006 是「套期工具」（共同类）；同一个 `5001` 在旧制是「主营业务收入」、
在 CAS 2006 是「基本生产成本」。按**码**放行会把真正的触发条件一起放掉
（`3201 利润分配` 实测在 `b39809ed` 有 25,630,018.69 的期初余额）。
`test_whitelist_cannot_silence_legacy_semantics` 从仓库内旧制科目表反向锁死这一点。

**金额口径（🔴 与 tasks.md 原文的一处显式偏离，见 spec Notes）**

tasks.md 写「金额恒为 0」并给出基线「170 行 / 1 行非零」。逐列复核后确认该基线
对应的是**当期 / 审定口径**（`unadjusted_amount` / `aje_adjustment` /
`rje_adjustment` / `audited_amount`）—— 那也正是 N4/N5/F5 实际读的列
（`TB('6403','本期发生额')` → `unadjusted_amount`）。
`trial_balance.opening_balance` 上另有 2 行非零（`3102 其他综合收益` 619,000.00 /
`3201 利润分配` 25,630,018.69，均在 `b39809ed`）。

处置：**不静默排除**。拆成两条同样是硬断言的检查 ——

1. `test_trial_balance_legacy_codes_have_zero_current_amounts`（当期/审定口径，
   对应策略真实读的列）
2. `test_trial_balance_legacy_opening_balances_match_frozen_baseline`
   （期初口径按「已知 (码,名) 集合」冻结；**新增**任何一对即打红）

`tb_balance` 侧四个核心金额列（期初/借方/贷方/期末）**全部**纳入第 1 类检查
（实测 0 行非零，可以从严）。

**为什么用 `get_active_filter` 而不是裸 `is_deleted = false`**

`tb_balance` 存在多 dataset 版本（实测 `2aa00f57` 的 active dataset 只含少数科目），
裸 `is_deleted` 扫描会把 staged/superseded 版本的行一起算进来 → 假红。
本文件先按 `(project_id, year)` 枚举再逐对取 active 过滤条件。

🔴 只读，不写库。无 DB 时 `pytest.skip` 并**打印 skip 原因**
（静默 skip 是假绿源；`test_skip_helper_prints_reason` 反向自检该打印真的发生）。

spec: semantic-account-resolver-full-rollout（Task 30）
Validates: Requirements 4.4, 4.6
"""
from __future__ import annotations

import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.audit_platform_models import TbBalance, TrialBalance
from app.services.dataset_query import get_active_filter

# ---------------------------------------------------------------------------
# 判定规则（纯函数区 —— 不连库，DB 断言与反向自检共用同一套逻辑）
# ---------------------------------------------------------------------------

#: tasks.md 原文的口径：`^(3\d{3}|5\d{3})`（不锚定尾部 → 6 位子码 `320104`
#: 与点号子码 `5101.07.01` 同样命中，这是有意的）。
LEGACY_CODE_RE = re.compile(r"^(3\d{3}|5\d{3})")

#: postgres 侧同口径正则（用于把扫描面收窄到旧制区间，避免全表拉取）。
LEGACY_CODE_SQL_RE = r"^(3[0-9]{3}|5[0-9]{3})"

#: CAS 2006 语义的 (一级码, 科目名) → 放行理由。
#:
#: 🔴 这些**不是**旧制码，只是恰好落在 `3xxx`/`5xxx` 区间：CAS 2006 的 `3xxx` 是
#: 共同类、`5xxx` 是成本类。它们带真余额是完全正常的会计事实，与
#: 「N4/N5/F5/M 少算」的风险无关。
#:
#: 全部来自 postgres 只读普查（2026-08-03，`trial_balance` ∪ `tb_balance`，
#: active dataset）。点号子码（如 `5101.07.01 制造费用_修理费_房屋维修费`）
#: 由 `_matches_whitelist` 的「一级码 + 名称前缀」规则一并放行，无需逐条登记。
CAS2006_WHITELIST: dict[tuple[str, str], str] = {
    ("3101", "衍生工具"): "CAS 2006 共同类（旧制 3101 是盈余公积）",
    ("3201", "套期工具"): (
        "CAS 2006 共同类（旧制 3201 是利润分配）；"
        "df5b8403 实测 −4,314,686.92 —— 全库唯一带真金额的 3xxx/5xxx 行"
    ),
    ("3202", "被套期项目"): "CAS 2006 共同类（旧制无 3202）",
    ("5001", "基本生产成本"): "CAS 2006 成本类（旧制 5001 是主营业务收入）",
    ("5001", "生产成本"): "CAS 2006 成本类（同上，个别项目用父级名）",
    ("5002", "辅助生产成本"): "CAS 2006 成本类（旧制无 5002）",
    ("5101", "制造费用"): "CAS 2006 成本类（旧制制造费用挂 4101）",
    ("5201", "劳务成本"): "CAS 2006 成本类（旧制无 5201）",
    ("5301", "研发支出"): "CAS 2006 成本类（旧制 5301 是营业外收入）",
}

#: `trial_balance` 里策略真实读取的金额列（当期 / 审定口径）。
TRIAL_BALANCE_CURRENT_AMOUNT_COLS: tuple[str, ...] = (
    "unadjusted_amount",
    "aje_adjustment",
    "rje_adjustment",
    "audited_amount",
)

#: `tb_balance` 的四个核心金额列（实测 0 行非零 → 从严全查）。
TB_BALANCE_AMOUNT_COLS: tuple[str, ...] = (
    "opening_balance",
    "debit_amount",
    "credit_amount",
    "closing_balance",
)

#: `trial_balance.opening_balance` 上**已知**带非零值的旧制 (码, 名) 对。
#: 新增任何一对即打红 —— 那意味着又有一个旧制科目开始承载真金额。
TRIAL_BALANCE_OPENING_KNOWN: dict[tuple[str, str], str] = {
    ("3102", "其他综合收益"): "b39809ed 期初 619,000.00（当期/审定列均为 0）",
    ("3201", "利润分配"): (
        "b39809ed 期初 25,630,018.69（当期/审定列均为 0）；"
        "M 循环取数走 tb_balance 客户原始码，而 tb_balance 侧无任何旧制权益行 → 当前不构成少算"
    ),
}

#: 旧制科目表（仓库内 `standard_account_chart.json` 的 3xxx/5xxx 段实测就是旧制口径）
#: 用作白名单的反向锚点，防「把 `3201 利润分配` 加进白名单来消红」。
_STANDARD_CHART_JSON = (
    Path(__file__).resolve().parents[2] / "data" / "standard_account_chart.json"
)


def root_code(code: str) -> str:
    """取一级码：截掉点号子级（`5101.07.01` → `5101`）。"""
    return str(code or "").strip().split(".", 1)[0]


def _matches_whitelist(code: str, name: str) -> str | None:
    """命中 CAS 2006 白名单则返回放行理由，否则 None。

    两级匹配（都要求**码 + 名**同时对上，绝不按码放行）：

    1. `(码, 名)` 精确命中；
    2. 点号子码：`(一级码, 一级名)` 命中 **且** 子科目名以该一级名开头
       （库内子科目名形态恒为 `{父名}_{子名}`）。
    """
    key = (str(code or "").strip(), str(name or "").strip())
    hit = CAS2006_WHITELIST.get(key)
    if hit:
        return hit
    parent = root_code(code)
    if parent == key[0]:
        return None  # 不是点号子码，第 2 级不适用
    child_name = key[1]
    for (w_code, w_name), reason in CAS2006_WHITELIST.items():
        if w_code == parent and child_name.startswith(w_name):
            return f"{reason}（子科目 {key[1]} 继承 {w_code} {w_name}）"
    return None


def nonzero_amounts(amounts: Mapping[str, object]) -> dict[str, Decimal]:
    """返回非零金额列（None 视为 0）。"""
    out: dict[str, Decimal] = {}
    for col, raw in amounts.items():
        if raw is None:
            continue
        try:
            val = Decimal(str(raw))
        except Exception:  # pragma: no cover - 防御：非数值列传进来
            continue
        if val != 0:
            out[col] = val
    return out


def legacy_encoding_violation(
    code: str, name: str, amounts: Mapping[str, object]
) -> dict[str, object] | None:
    """行级判定（唯一真源）：该行是否是「旧制码带真余额」的违规行。

    返回 None = 合规；返回 dict = 违规详情（含非零列与金额，供报错信息用）。

    三步：
    1. 码不在旧制区间 → 合规（与本守卫无关）；
    2. 全部金额为 0 → 合规（骨架行，这是当前的常态）；
    3. 命中 CAS 2006 白名单（码 + 名两元组）→ 合规（另一套体系的正常余额）。
    """
    raw_code = str(code or "").strip()
    if not LEGACY_CODE_RE.match(raw_code):
        return None
    hits = nonzero_amounts(amounts)
    if not hits:
        return None
    if _matches_whitelist(raw_code, name):
        return None
    return {
        "code": raw_code,
        "name": str(name or "").strip(),
        "nonzero": hits,
    }


def scan_rows(rows: Iterable[Mapping[str, object]], *, code_col: str,
              amount_cols: Sequence[str]) -> list[dict[str, object]]:
    """扫一批行（DB 行或内存行同一入口），返回违规清单。"""
    out: list[dict[str, object]] = []
    for row in rows:
        violation = legacy_encoding_violation(
            row.get(code_col),
            row.get("account_name"),
            {c: row.get(c) for c in amount_cols},
        )
        if violation is None:
            continue
        violation["project_id"] = str(row.get("project_id"))
        violation["year"] = row.get("year")
        out.append(violation)
    return out


# ---------------------------------------------------------------------------
# skip 可见性（静默 skip 是假绿源）
# ---------------------------------------------------------------------------

SKIP_MARKER = "[legacy-encoding-guard][SKIP]"


def skip_no_db(reason: str) -> None:
    """打印 skip 原因后再 skip。

    双写 stdout + stderr：pytest 默认捕获 stdout，`-rs` / `-s` 才展示；
    stderr 在 CI 日志里更容易被看到。CI job 已加 `-rs`。
    """
    message = f"{SKIP_MARKER} {reason}"
    print(message)
    print(message, file=sys.stderr)
    pytest.skip(reason)


_IS_PG = str(settings.DATABASE_URL or "").startswith("postgresql")


# ---------------------------------------------------------------------------
# DB 扫描
# ---------------------------------------------------------------------------


async def _legacy_rows(table, code_col_name: str, amount_cols: Sequence[str]):
    """只读取回旧制区间行（按 active dataset 过滤）。"""
    if not _IS_PG:
        skip_no_db(
            "DATABASE_URL 不是 PostgreSQL（当前："
            f"{str(settings.DATABASE_URL or '')[:24]}…）→ 旧制编码余额守卫无法执行。"
            " 本用例需要连库，请在挂了 PG 的 CI DB job 里跑。"
        )
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True, echo=False)
    try:
        try:
            async with engine.connect() as conn:
                await conn.execute(sa.text("SELECT 1"))
        except Exception as exc:
            skip_no_db(
                f"PostgreSQL 不可达（{type(exc).__name__}: {exc}）→ 旧制编码余额守卫无法执行。"
                " 本用例需要连库，请在挂了 PG 的 CI DB job 里跑。"
            )
        factory = async_sessionmaker(engine, expire_on_commit=False)
        tbl = table.__table__
        code_col = tbl.c[code_col_name]
        async with factory() as db:
            pairs = (
                await db.execute(
                    sa.select(tbl.c.project_id, tbl.c.year)
                    .where(
                        code_col.op("~")(LEGACY_CODE_SQL_RE),
                        tbl.c.is_deleted == sa.false(),
                    )
                    .distinct()
                )
            ).all()
            rows: list[dict[str, object]] = []
            for project_id, year in pairs:
                active = await get_active_filter(db, tbl, project_id, year)
                selected = (
                    await db.execute(
                        sa.select(
                            tbl.c.project_id,
                            tbl.c.year,
                            code_col.label(code_col_name),
                            tbl.c.account_name,
                            *[tbl.c[c] for c in amount_cols],
                        ).where(active, code_col.op("~")(LEGACY_CODE_SQL_RE))
                    )
                ).mappings().all()
                rows.extend(dict(r) for r in selected)
            return rows
    finally:
        await engine.dispose()


def _fmt(violations: Sequence[Mapping[str, object]]) -> str:
    lines = []
    for v in violations:
        amounts = ", ".join(f"{k}={v}" for k, v in dict(v["nonzero"]).items())
        lines.append(
            f"  - {v['code']} {v['name']}  项目={str(v['project_id'])[:8]} "
            f"年度={v['year']}  {amounts}"
        )
    return "\n".join(lines)


_MIGRATION_HINT = (
    "\n\n🔴 这是启动 N4/N5/F5/M 语义迁移的信号：旧制编码开始承载真余额，"
    "而那些策略的取数硬编码 CAS 2006 码（6403/6801/6401/6402/6404）→ 会静默少算。"
    "\n若该行其实是 CAS 2006 语义（共同类/成本类），请把 (码, 科目名) 两元组"
    "连同 DB 实证依据加入 CAS2006_WHITELIST —— 但**不得**按码放行，"
    "也不得把旧制语义的名字加进白名单（test_whitelist_cannot_silence_legacy_semantics 会拦）。"
)


class TestLiveDatabase:
    """连库断言（只读）。"""

    async def test_trial_balance_legacy_codes_have_zero_current_amounts(self):
        rows = await _legacy_rows(
            TrialBalance, "standard_account_code", TRIAL_BALANCE_CURRENT_AMOUNT_COLS
        )
        violations = scan_rows(
            rows,
            code_col="standard_account_code",
            amount_cols=TRIAL_BALANCE_CURRENT_AMOUNT_COLS,
        )
        print(
            f"[legacy-encoding-guard] trial_balance 旧制区间行数={len(rows)}"
            f" 违规={len(violations)}"
        )
        assert not violations, (
            f"trial_balance 有 {len(violations)} 行旧制编码带非零当期/审定金额：\n"
            f"{_fmt(violations)}{_MIGRATION_HINT}"
        )

    async def test_tb_balance_legacy_codes_have_zero_amounts(self):
        rows = await _legacy_rows(TbBalance, "account_code", TB_BALANCE_AMOUNT_COLS)
        violations = scan_rows(
            rows, code_col="account_code", amount_cols=TB_BALANCE_AMOUNT_COLS
        )
        print(
            f"[legacy-encoding-guard] tb_balance 旧制区间行数={len(rows)}"
            f" 违规={len(violations)}"
        )
        assert not violations, (
            f"tb_balance 有 {len(violations)} 行旧制编码带非零余额：\n"
            f"{_fmt(violations)}{_MIGRATION_HINT}"
        )

    async def test_trial_balance_legacy_opening_balances_match_frozen_baseline(self):
        """期初口径单列一条：已知 2 对非零，**新增**任何一对即打红。"""
        rows = await _legacy_rows(TrialBalance, "standard_account_code", ("opening_balance",))
        violations = scan_rows(
            rows, code_col="standard_account_code", amount_cols=("opening_balance",)
        )
        observed = {(str(v["code"]), str(v["name"])) for v in violations}
        known = set(TRIAL_BALANCE_OPENING_KNOWN)
        unexpected = sorted(observed - known)
        print(
            f"[legacy-encoding-guard] trial_balance.opening_balance 非零旧制对="
            f"{sorted(observed)} 已冻结={sorted(known)}"
        )
        assert not unexpected, (
            "trial_balance.opening_balance 出现**未登记**的旧制编码非零对："
            f"{unexpected}\n"
            f"{_fmt([v for v in violations if (str(v['code']), str(v['name'])) in set(unexpected)])}"
            f"{_MIGRATION_HINT}"
        )

    async def test_db_scan_channel_is_not_vacuous(self):
        """🔴 反向自检（DB 通道）：把虚构非零旧制行混进**活体行集合**必须被点名。

        证明上面三条「违规=0」不是因为扫描链路空转（取不到行 / 列名写错 / 正则失效
        都会让守卫恒绿）。顺带把普查计数打到日志里供人核对基线。
        """
        tb_rows = await _legacy_rows(TbBalance, "account_code", TB_BALANCE_AMOUNT_COLS)
        trial_rows = await _legacy_rows(
            TrialBalance, "standard_account_code", TRIAL_BALANCE_CURRENT_AMOUNT_COLS
        )
        whitelisted = sum(
            1
            for r in tb_rows + trial_rows
            if _matches_whitelist(
                r.get("account_code") or r.get("standard_account_code"),
                r.get("account_name"),
            )
        )
        print(
            "[legacy-encoding-guard] 普查："
            f"trial_balance={len(trial_rows)} 行 / tb_balance={len(tb_rows)} 行 / "
            f"其中 CAS2006 白名单命中={whitelisted} 行"
        )

        injected = list(trial_rows) + [
            {
                "project_id": "00000000-0000-0000-0000-0000000000ff",
                "year": 1999,
                "standard_account_code": "5401",
                "account_name": "主营业务成本",
                "unadjusted_amount": Decimal("888888.88"),
                "aje_adjustment": Decimal("0.00"),
                "rje_adjustment": Decimal("0.00"),
                "audited_amount": Decimal("888888.88"),
            }
        ]
        found = scan_rows(
            injected,
            code_col="standard_account_code",
            amount_cols=TRIAL_BALANCE_CURRENT_AMOUNT_COLS,
        )
        assert len(found) == 1, (
            "注入虚构非零旧制行后应恰好 1 条违规（活体 0 条 + 注入 1 条），"
            f"实际 {len(found)} 条：{_fmt(found)}"
        )
        assert found[0]["code"] == "5401" and found[0]["year"] == 1999


# ---------------------------------------------------------------------------
# 纯函数断言 + 反向自检（不连库，CI 无 DB 也必须跑）
# ---------------------------------------------------------------------------


class TestPredicate:
    """行级判定函数的正向 / 反向行为。"""

    @pytest.mark.parametrize(
        "code",
        ["3001", "3101", "3201", "320104", "5001", "5401", "5801", "5101.07.01"],
    )
    def test_regex_matches_legacy_range(self, code: str):
        assert LEGACY_CODE_RE.match(code), f"{code} 应落在旧制扫描区间"

    @pytest.mark.parametrize("code", ["1001", "2201", "4001", "6403", "6801", ""])
    def test_regex_skips_other_ranges(self, code: str):
        assert not LEGACY_CODE_RE.match(code), f"{code} 不应落在旧制扫描区间"

    def test_zero_amounts_are_compliant(self):
        """骨架行（全 0 / None）= 当前常态，必须判合规。"""
        assert (
            legacy_encoding_violation(
                "5401",
                "主营业务成本",
                {"unadjusted_amount": Decimal("0.00"), "audited_amount": None},
            )
            is None
        )

    def test_injected_nonzero_legacy_row_is_flagged(self):
        """🔴 反向自检 1：注入一条虚构非零旧制码行必须打红。"""
        violation = legacy_encoding_violation(
            "5401",
            "主营业务成本",
            {"unadjusted_amount": Decimal("123456.78"), "audited_amount": Decimal("0")},
        )
        assert violation is not None, "非零旧制损益码必须被判违规"
        assert violation["nonzero"] == {"unadjusted_amount": Decimal("123456.78")}

    def test_injected_row_survives_full_scan_path(self):
        """🔴 反向自检 2：把虚构行混进「真实形态」的行集合，`scan_rows` 必须点名它。

        这条走的是 DB 断言用的同一条 `scan_rows` 通道（内存行，不写库），
        证明「DB 全绿」不是因为扫描链路空转。
        """
        clean = [
            {
                "project_id": "b39809ed-0000-0000-0000-000000000000",
                "year": 2025,
                "standard_account_code": "5801",
                "account_name": "所得税费用",
                "unadjusted_amount": Decimal("0.00"),
                "aje_adjustment": Decimal("0.00"),
                "rje_adjustment": Decimal("0.00"),
                "audited_amount": Decimal("0.00"),
            },
            {
                "project_id": "df5b8403-0000-0000-0000-000000000000",
                "year": 2025,
                "standard_account_code": "3201",
                "account_name": "套期工具",  # CAS 2006 白名单
                "unadjusted_amount": Decimal("-4314686.92"),
                "aje_adjustment": Decimal("0.00"),
                "rje_adjustment": Decimal("0.00"),
                "audited_amount": Decimal("-4314686.92"),
            },
        ]
        assert (
            scan_rows(
                clean,
                code_col="standard_account_code",
                amount_cols=TRIAL_BALANCE_CURRENT_AMOUNT_COLS,
            )
            == []
        ), "干净行集合不应产生违规（否则 DB 断言会假红）"

        injected = clean + [
            {
                "project_id": "00000000-0000-0000-0000-0000000000ff",
                "year": 2025,
                "standard_account_code": "5801",
                "account_name": "所得税费用",
                "unadjusted_amount": Decimal("999999.99"),
                "aje_adjustment": Decimal("0.00"),
                "rje_adjustment": Decimal("0.00"),
                "audited_amount": Decimal("999999.99"),
            }
        ]
        found = scan_rows(
            injected,
            code_col="standard_account_code",
            amount_cols=TRIAL_BALANCE_CURRENT_AMOUNT_COLS,
        )
        assert len(found) == 1, f"注入的非零旧制行必须被点名，实际 {found}"
        assert found[0]["code"] == "5801"
        assert set(dict(found[0]["nonzero"])) == {"unadjusted_amount", "audited_amount"}

    def test_injected_legacy_equity_row_is_flagged(self):
        """🔴 反向自检 3：旧制权益码（`3201 利润分配`）带真余额必须打红。

        它与白名单里的 `3201 套期工具` **同码不同名** —— 证明白名单确实是
        两元组匹配，不是按码放行。
        """
        assert (
            legacy_encoding_violation(
                "3201", "利润分配", {"closing_balance": Decimal("25630018.69")}
            )
            is not None
        )
        assert (
            legacy_encoding_violation(
                "3201", "套期工具", {"closing_balance": Decimal("-4314686.92")}
            )
            is None
        )

    def test_whitelist_child_accounts_inherit_parent(self):
        """点号子码按「一级码 + 名称前缀」继承放行（`5101.07.01 制造费用_修理费_…`）。"""
        assert (
            legacy_encoding_violation(
                "5101.07.01",
                "制造费用_修理费_房屋维修费",
                {"closing_balance": Decimal("12345.00")},
            )
            is None
        )

    def test_whitelist_child_requires_name_prefix(self):
        """子码继承必须名称对得上 —— 挂在 `5101.` 下的旧制语义名不许蹭放行。"""
        assert (
            legacy_encoding_violation(
                "5101.01", "主营业务收入", {"closing_balance": Decimal("1.00")}
            )
            is not None
        )

    def test_none_amounts_are_not_nonzero(self):
        assert nonzero_amounts({"a": None, "b": Decimal("0"), "c": 0.0}) == {}
        assert nonzero_amounts({"a": Decimal("-0.01")}) == {"a": Decimal("-0.01")}


class TestWhitelistIntegrity:
    """白名单不得成为消红工具。"""

    def test_whitelist_keys_are_code_name_pairs(self):
        for key, reason in CAS2006_WHITELIST.items():
            assert isinstance(key, tuple) and len(key) == 2, f"{key} 必须是 (码, 名) 两元组"
            code, name = key
            assert LEGACY_CODE_RE.match(code), f"{code} 不在旧制扫描区间，无需白名单"
            assert name and name.strip(), f"{code} 的科目名不得为空（否则退化成按码放行）"
            assert reason and len(reason) >= 8, f"{key} 必须写放行理由"

    def test_whitelist_cannot_silence_legacy_semantics(self):
        """🔴 反向锁死：白名单里的名字不得等于旧制科目表对该码的名字。

        真源 = 仓库内 `standard_account_chart.json`（其 3xxx/5xxx 段就是旧制口径：
        `3001 实收资本` / `3201 利润分配` / `5001 主营业务收入` / `5401 主营业务成本`）。
        这条断言意味着「把 `3201 利润分配` 加进白名单」这种消红手法会直接打红。
        """
        legacy = _legacy_chart_names()
        assert legacy, "旧制科目表锚点为空（正则/文件失效）→ 本断言会空转"
        assert legacy.get("3201") == "利润分配", (
            "standard_account_chart.json 的 3xxx/5xxx 段不再是旧制口径，"
            "本断言的锚点失效，需重新选真源"
        )
        for code, name in CAS2006_WHITELIST:
            legacy_name = legacy.get(code)
            if legacy_name is None:
                continue  # 旧制表无此码（如 5002/5101/5201/3202）→ 无冲突
            assert name != legacy_name, (
                f"白名单条目 ({code}, {name}) 与旧制科目表同名 —— "
                "这是在把真正的触发条件放行，禁止"
            )

    def test_frozen_opening_baseline_entries_are_legacy_semantics(self):
        """期初冻结集合里的对必须**不在**白名单（否则它们压根不会成为违规）。"""
        for key, note in TRIAL_BALANCE_OPENING_KNOWN.items():
            assert _matches_whitelist(*key) is None, (
                f"{key} 已在 CAS2006 白名单里，不该同时出现在期初冻结集合"
            )
            assert note and len(note) >= 8, f"{key} 必须写实证依据"


class TestSkipVisibility:
    """静默 skip 是假绿源 → 证明 skip 路径真的打印了原因。"""

    def test_skip_helper_prints_reason(self, capsys):
        with pytest.raises(pytest.skip.Exception):
            skip_no_db("单元自检：PG 不可达")
        captured = capsys.readouterr()
        assert SKIP_MARKER in captured.out, "skip 原因必须打到 stdout"
        assert SKIP_MARKER in captured.err, "skip 原因必须打到 stderr（CI 日志可见）"
        assert "单元自检：PG 不可达" in captured.out

    def test_db_tests_use_the_printing_skip_helper(self):
        """源码级：本文件里的 skip 一律走 `skip_no_db`，不得裸调 `pytest.skip`。"""
        src = Path(__file__).read_text(encoding="utf-8")
        body = _strip_comments_and_docstrings(src)
        assert "def skip_no_db" in body, "抽取失效（skip_no_db 定义没抓到）"
        bare = [
            line
            for line in body.splitlines()
            if "pytest.skip(" in line and "pytest.skip.Exception" not in line
        ]
        # 唯一合法出现点 = skip_no_db 自己的实现
        assert len(bare) == 1, f"发现裸 pytest.skip 调用：{bare}"


def _strip_comments_and_docstrings(src: str) -> str:
    """去注释 + 去三引号块（守卫说明里会写反例，不去掉会把说明数成代码）。"""
    without_docstrings = re.sub(r'"""(?:.|\n)*?"""', "", src)
    return "\n".join(
        re.sub(r"#.*$", "", line) for line in without_docstrings.splitlines()
    )


def _legacy_chart_names() -> dict[str, str]:
    """从 `standard_account_chart.json` 取 3xxx/5xxx 段的 (码 → 名)。"""
    import json

    assert _STANDARD_CHART_JSON.exists(), (
        f"缺 {_STANDARD_CHART_JSON.name} —— 白名单的反向锚点丢了，断言会空转"
    )
    data = json.loads(_STANDARD_CHART_JSON.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for acc in data.get("accounts", []):
        code = str(acc.get("code") or "")
        if LEGACY_CODE_RE.match(code):
            out[code] = str(acc.get("name") or "")
    return out
