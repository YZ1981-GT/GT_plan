"""推送叶子取数真库守卫（spec formula-hub-integrity-closure 任务 10；需求 4.4；ADR-FHIC-03）。

被测：生产 ``formula_push.sources.load_tb_audited``，调用形状照生产 —— 每个已注册 binding 以自己的
``account_prefixes`` 各调一次（``bindings.watched_prefixes``），另以推送规则公式 ``TB()`` 引用的科目再调一次。
金标准：测试内独立 SQL —— 本项目本年度未删的 ``trial_balance`` 行，标准码字面前缀（``starts_with``）取宽集合，
叶子 = 宽集合内没有以本码为前缀且更长的其他码（在 SQL 里判定，不调用 ``tb_leaf_codes``）；期末余额 ←
``audited_amount``、年初余额 ← ``opening_balance``、本期发生额 = 期末 − 年初（对应 ``TbAuditedSnapshot.tb_data`` 三列）。

- 真实数据：全部活项目（未软删）× 推送科目；年度 = 项目 ``audit_year`` ∪ 该项目试算表未删行出现的年度。每个
  (项目, 年度, 科目) 的三列都须 = 独立 SQL 叶子和；「前缀和 ≠ 叶子和」的组合只打印报告，不作判据。
- 合成夹具：``pg_tx`` 内新建【测试】项目，``1122`` 父子并存且父行 ≠ 叶子和（另有一条已删除的更长码），取数须 =
  叶子和且 ≠ 前缀和 —— 推送科目的宽集合在真实数据里没有父子并存时，靠它保证判据不空转。
只连快照库（库名 ``fh_snap_`` 开头）：别的库没有这份真实数据 —— ``GT_REQUIRE_PG=1`` 时失败，否则跳过。
``pg_tx`` 结束一律回滚。
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.core import Project
from app.services.formula_push.bindings import watched_prefixes
from app.services.formula_push.rules import load_rules, rules_for
from app.services.formula_push.sources import load_tb_audited
from tests.formula_hub._pg_harness import SNAPSHOT_PREFIX, TEST_PROJECT_PREFIX, pg_required

pytestmark = pytest.mark.pg_only

D = Decimal
#: 推送规则公式里 ``TB('码', '列')`` 的码（``SUM_TB`` 不算；规则清单现在没有 SUM_TB）
_TB_CODE = re.compile(r"(?<![A-Z_])TB\(\s*(['\"])([^'\"]+)\1")
FIXTURE_CODE, FIXTURE_YEAR = "1122", 2025
#: (码, 期末余额, 年初余额, 已删除)：父 1122 ≠ 下级合计；已删除的 1122-0101 既不计入、也不让 1122-01 变成父行
_FIXTURE_ROWS = (
    ("1122", "100.00", "60.00", False),
    ("1122-01", "40.00", "25.00", False),
    ("1122-02", "50.00", "20.00", False),
    ("1122-0101", "999.00", "999.00", True),
)

_PAIRS_SQL = text(
    "SELECT p.id, p.name, y.year FROM projects p CROSS JOIN LATERAL ("
    " SELECT p.audit_year AS year WHERE p.audit_year IS NOT NULL"
    " UNION SELECT t.year FROM trial_balance t WHERE t.project_id = p.id AND t.is_deleted = false) AS y"
    " WHERE p.is_deleted = false ORDER BY p.name, y.year")
_GOLD_SQL = text("""
WITH codes AS (SELECT DISTINCT unnest(CAST(:codes AS text[])) AS code),
tb AS (
    SELECT standard_account_code AS acct, COALESCE(audited_amount, 0) AS audited,
           COALESCE(opening_balance, 0) AS opening
    FROM trial_balance WHERE project_id = :pid AND year = :year AND is_deleted = false
),
wide AS (SELECT c.code, t.acct, t.audited, t.opening FROM codes c JOIN tb t ON starts_with(t.acct, c.code)),
marked AS (
    SELECT w.code, w.audited, w.opening,
           EXISTS (SELECT 1 FROM wide o WHERE o.code = w.code AND length(o.acct) > length(w.acct)
                   AND starts_with(o.acct, w.acct)) AS is_parent
    FROM wide w
)
SELECT c.code, count(m.code) AS n_rows, count(m.code) FILTER (WHERE m.is_parent) AS n_parent,
       COALESCE(sum(m.audited) FILTER (WHERE NOT m.is_parent), 0) AS leaf_audited,
       COALESCE(sum(m.opening) FILTER (WHERE NOT m.is_parent), 0) AS leaf_opening,
       COALESCE(sum(m.audited), 0) AS prefix_audited, COALESCE(sum(m.opening), 0) AS prefix_opening
FROM codes c LEFT JOIN marked m ON m.code = c.code GROUP BY c.code
""")


@dataclass(frozen=True)
class Gold:
    """一个 (项目, 年度, 科目) 的独立 SQL 结果：宽集合行数、其中父行数、各列叶子和 / 前缀和。"""

    rows: int
    parents: int
    leaf: dict[str, Decimal]
    prefix: dict[str, Decimal]


def _columns(audited: Decimal, opening: Decimal) -> dict[str, Decimal]:
    return {"期末余额": audited, "年初余额": opening, "本期发生额": audited - opening}


def _push_codes() -> tuple[dict[str, tuple[str, ...]], frozenset[str]]:
    """生产推送取数的科目：各 binding 传给 ``load_tb_audited`` 的 ``account_prefixes``；推送规则公式 ``TB()`` 引用的码。"""
    rule_codes = frozenset(match.group(2) for rule in rules_for(load_rules()) if rule.source.kind == "formula"
                           for match in _TB_CODE.finditer(rule.source.expression or ""))
    return watched_prefixes(), rule_codes


async def _require_snapshot(db) -> None:
    name = (await db.execute(text("SELECT current_database()"))).scalar_one()
    if not name.startswith(SNAPSHOT_PREFIX):
        reason = f"推送叶子取数守卫只连快照库（{SNAPSHOT_PREFIX}*），当前库 {name}"
        if pg_required():
            pytest.fail(reason, pytrace=False)
        pytest.skip(reason)


async def _gold(db, project_id, year: int, codes: list[str]) -> dict[str, Gold]:
    result = await db.execute(_GOLD_SQL, {"codes": codes, "pid": project_id, "year": year})
    return {code: Gold(n_rows, n_parent, _columns(D(la), D(lo)), _columns(D(pa), D(po)))
            for code, n_rows, n_parent, la, lo, pa, po in result.all()}


async def _check_pair(db, project_id, year: int, prefixes: dict[str, tuple[str, ...]],
                      rule_codes: frozenset[str]) -> tuple[dict[str, Gold], list[str], int]:
    """一个 (项目, 年度)：按生产调用形状逐个调 ``load_tb_audited``，逐科目逐列与独立 SQL 叶子和比对。"""
    calls = [*((f"binding {wp}", codes) for wp, codes in sorted(prefixes.items())),
             ("推送规则 TB()", tuple(sorted(rule_codes)))]
    gold = await _gold(db, project_id, year, sorted({c for _, codes in calls for c in codes}))
    problems: list[str] = []
    for label, codes in calls:
        snapshot = await load_tb_audited(db, project_id, year, codes)
        if set(snapshot.tb_data) != set(codes):
            problems.append(f"{label}：返回科目 {sorted(snapshot.tb_data)} ≠ 传入 {sorted(codes)}")
        for code in codes:
            got = snapshot.tb_data.get(code, {})
            problems += [f"{label} 科目 {code}（{col}）：load_tb_audited {got.get(col)} ≠ 独立 SQL 叶子和 {want}"
                         for col, want in gold[code].leaf.items() if got.get(col) != want]
    return gold, problems, len(calls)


async def test_push_tb_audited_equals_sql_leaf_sum_on_active_projects(pg_tx, capsys):
    await _require_snapshot(pg_tx)
    prefixes, rule_codes = _push_codes()
    binding_codes = {c for group in prefixes.values() for c in group}
    codes = sorted(rule_codes | binding_codes)
    assert rule_codes and codes, "推送规则 / binding 没有引用任何试算表科目：判据空转"
    active = (await pg_tx.execute(text("SELECT count(*) FROM projects WHERE is_deleted = false"))).scalar_one()
    pairs = (await pg_tx.execute(_PAIRS_SQL)).all()
    problems: list[str] = []
    report: list[str] = []
    combos = with_rows = calls = 0
    for project_id, name, year in pairs:
        gold, found, n_calls = await _check_pair(pg_tx, project_id, year, prefixes, rule_codes)
        problems += [f"{name} {year} 年 {item}" for item in found]
        calls += n_calls
        combos += len(gold)
        with_rows += sum(1 for g in gold.values() if g.rows)
        report += [f"  {name} {year} 年 科目 {code}：期末 前缀和 {g.prefix['期末余额']} / 叶子和 {g.leaf['期末余额']}；"
                   f"年初 前缀和 {g.prefix['年初余额']} / 叶子和 {g.leaf['年初余额']}"
                   for code, g in sorted(gold.items()) if g.prefix != g.leaf]
    with capsys.disabled():
        print(f"\n[推送叶子取数] 活项目 {active} 个，(项目, 年度) {len(pairs)} 组（{len({p for p, _, _ in pairs})} 个项目）"
              f" × 推送科目 {len(codes)} 个（规则 TB() {len(rule_codes)} 个 ∪ binding account_prefixes "
              f"{len(binding_codes)} 个）= {combos} 组合，其中有试算表行 {with_rows} 个；load_tb_audited 调用 {calls} 次")
        print(f"[推送叶子取数] 前缀和 ≠ 叶子和（只报告，不作判据）：{len(report)} 个组合")
        for line in report:
            print(line)
    assert combos == len(pairs) * len(codes) and combos > 0, "活项目 × 推送科目的组合为空：判据空转"
    assert with_rows > 0, "全部组合都没有试算表行：判据空转"
    assert not problems, f"{len(problems)} 处 load_tb_audited ≠ 独立 SQL 叶子和：\n" + "\n".join(problems[:20])


async def test_parent_child_fixture_reads_leaf_sum(pg_tx):
    await _require_snapshot(pg_tx)
    prefixes, rule_codes = _push_codes()
    assert any(FIXTURE_CODE in codes for codes in prefixes.values()), f"没有 binding 取 {FIXTURE_CODE}：夹具走不到生产调用"
    tag = uuid.uuid4().hex[:10]
    project = Project(name=f"{TEST_PROJECT_PREFIX}fh_push_leaf_{tag}", client_name=f"{TEST_PROJECT_PREFIX}推送叶子取数守卫")
    pg_tx.add(project)
    await pg_tx.flush()
    pg_tx.add_all(TrialBalance(
        project_id=project.id, year=FIXTURE_YEAR, company_code="001", standard_account_code=code,
        account_name=f"{TEST_PROJECT_PREFIX}{code}", account_category=AccountCategory.asset,
        audited_amount=D(audited), opening_balance=D(opening), is_deleted=deleted,
    ) for code, audited, opening, deleted in _FIXTURE_ROWS)
    await pg_tx.flush()

    gold, problems, _ = await _check_pair(pg_tx, project.id, FIXTURE_YEAR, prefixes, rule_codes)
    assert not problems, "\n".join(problems)
    family = gold[FIXTURE_CODE]
    assert (family.rows, family.parents) == (3, 1), family
    assert family.leaf == _columns(D("90.00"), D("45.00")), family
    assert family.prefix == _columns(D("190.00"), D("105.00")), family  # 父行 100 ≠ 叶子和 90：前缀相加会双计
    got = dict((await load_tb_audited(pg_tx, project.id, FIXTURE_YEAR, (FIXTURE_CODE,))).tb_data[FIXTURE_CODE])
    assert got == family.leaf and got != family.prefix, got
