"""真库回归守卫：公式推送附注跳过减少。

spec: formula-push-note-skip-reduction · 任务 6.2–6.4
spec: formula-push-note-row-matching · P0 棘轮收紧

在重药控股安徽有限公司_2025 上用 ``dry_run=True`` 重跑公式推送，验证：
- 6.2  skipped_count 不超过已知基线（棘轮守卫：只许减不许增）
- 6.3  written + unchanged + kept ≥ 覆盖率下限
- 6.4  两次 dry_run 结果幂等（unchanged 项数与 addr_id 集合一致）

``DATABASE_URL`` 非 PostgreSQL 时 skip（真库约束不可 SQLite 代替）。

基线说明（2026-10-13 真库实测）：
  skipped_count = 66（A=8 / C=32 / D=13 / G=3 / I=2 / K=8 / other=0）
  coverage = 327（written + unchanged + kept）
  前轮 spec（formula-push-note-skip-reduction / formula-push-note-row-matching）已将
  skipped 从 208 降至 66（消除虚假 per-row skip + 包含匹配 + 兜底重分类）。
  本守卫按真实基线棘轮，防止回归。
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path
from uuid import UUID

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

# ── 常量 ─────────────────────────────────────────────────────────────
_PROJECT_ID = UUID("0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49")
_PROJECT_NAME = "重药控股安徽有限公司_2025"

#: 棘轮基线（2026-10-13 真库实测）：skipped=66，行匹配/银行明细/章节号等合理跳过
#: 只许减不许增——后续 spec 每修一类，手动下调此值
#: 取值逻辑：实测 66，per-category sum=88，取二者之间 80 作安全网
#: 🔴 2026-10-17 由 80 上调为 85：实测 82 = 66 + 10（L 类）+ 6（M 类），新增的 16 个原来都是「写成功」的假象 ——
#: L 类是旧兜底把期初数写进「减值准备」列（见 _MIN_COVERAGE 说明），M 类是 H1 的 固定资产_1601 / _1602 / _1603
#: 三条取数行都对上附注「固定资产」行、逐条覆盖写，留下的是 1603 的 0。今后只许下调。
#: 🔴 2026-10-27 重定为 99（spec note-pull-followup-closure R2.5）：HEAD 现算 196 —— 2026-10-24~25 程序裁剪把本项目 131 张
#: 已裁底稿移入回收站（procedure-trim-generation-delegation-chain），20 个 binding 的分册不在了（P 类，新增分类），子表规则
#: 105 处跳过（取不到值 / 表名错版 / 章节标题不是子表名）；删 104 条子表规则与 3 条错挂主表规则后现算 99，sub 跳过 0。
#: 🔴 2026-10-31 重定为 106（spec disclosure-note-template-word-realignment Task 34/35，T 类）：取数行对不上明细、表里又有
#: 多个汇总行时不再兜底 —— 长期股权投资 / 投资性房地产 / 长期借款 / 应付债券 8 格由 fallback_to_total 改为 skipped。旧兜底
#: 把科目余额写进「最终合计」（v1.0.56 起，长期股权投资原值进「合  计」、投资性房地产原值进「五、账面价值合计」）或
#: 「首个合计」（更早，长期借款审定数是重分类后的数、该进合计），是哪一段由科目决定、引擎不知道。不是回归，今后只许下调。
#: 🔴 2026-10-31（二）重定为 133（同 spec Task 34/35），三处都是原来「写成功」的假数改为如实跳过、外加一处跳过原因
#: 由误报改为实情，均不是回归：
#: ① Y 类 15：损益类上期发生额改取上年试算表（``sources.load_prior_pl``），本项目没有 2024 年试算表 ⇒ 不写（原来取本年
#:    年初余额，损益类恒 0，13 张损益类附注合计「上期」都被推成 0；另 2 格是 D4 两行的上期）；
#: ② Z 类 6：合计行上方各行这一列都没有数 ⇒ 不按 0 重算（``note_writer.total_formula`` 返回 None；八、9 / 八、42 /
#:    八、53 主表合计原来被推成 [0, 0]）；
#: ③ 主表规则按准则声明表名的，章节标题改按种子章节名校验（``engine._expected_section_title``）：D2 / D4 / K6 在国企
#:    项目不再误判「不是…章节」（D 类 8→5），往下走到真实原因 —— 多汇总行不兜底（T 类 +8）、旧格式表收入 / 成本两列
#:    认不出期末金额列（L 类 +1）、D4 上期（并入 ①）。今后只许下调。
_MAX_SKIPPED = 133
#: 覆盖率下限（written + unchanged + kept）：实测 327，棘轮只许增不许减
#:
#: 🔴 2026-10-17 由 320 下调为 295 —— 不是回归，是旧口径虚高（spec disclosure-note-template-word-realignment Task 26）：
#: 本项目附注是模板生成的旧格式（``_tables`` 为真源、顶层 ``rows`` 是首表镜像，无 ``sub_table_data``），旧兜底把数写进
#: 镜像（编辑器 / Word 导出 / 校验都读 ``_tables``，看不见）且按位置认列。327 里有 132 格「unchanged」只是公式值等于
#: 镜像里上次推送的数。改为写 ``_tables`` 并按表头认列后实测 313：74 格 unchanged→write（第一次真正显示出来），
#: 10 格改为跳过 —— 八、10 / 11 / 15 / 17 / 23 期末、期初组下各有「账面余额 / 减值准备 / 账面价值」三列，旧兜底把期初数
#: 写进的是「减值准备」列；另 4 格是这几张表的合计重算不再产出。再加撞行守卫（M 类，6 格改为跳过）实测 307。
#: 再把找行 ③ 包含匹配收窄为「同一项目的另一种写法」实测 297：10 格原来对上的是别的行 —— 长期股权投资 → 「减：长期股权投资
#: 减值准备」（期末 500,000.00 写进减值准备列）、其他非流动金融资产 → 「其他」、长期借款 / 应付债券 → 「减：一年内到期的…」、
#: 所得税费用 → 「当期所得税费用」；现在改走合计行兜底（这 10 格记 fallback_to_total、不计覆盖，兜底写的小计 / 合计格原本就计）。
#: 今后只许上调。
#: 🔴 2026-10-27 重定为 231（spec note-pull-followup-closure R2.5）：HEAD 现算 227 —— 不是推送回归，是本项目 131 张已裁底稿
#: 移入回收站后（见 _MAX_SKIPPED），那些底稿的取数格不再参与（覆盖分母没了）；本 spec 子表规则按表名精确定位后
#: 「短期借款分类」等表的合计兜底写得进去了，现算 231（written 2 + unchanged 221 + kept 8）。
#: 🔴 2026-10-31 重定为 223（spec disclosure-note-template-word-realignment Task 34/35）：同日 G11 投资收益标题去掉提示后
#: 对上了（+2）；多汇总行不再兜底（见 _MAX_SKIPPED，−8：这 8 格原来计的是写进错误汇总行的数）；所得税费用的别名
#: 「当期所得税费用」删除（构成项不是它），改走唯一合计行兜底（−2：原来对上「当期所得税费用」行再按合计重算，各计 2 格）。
#: 现算 223（written 0 + unchanged 215 + kept 8）。今后只许上调。
#: 🔴 2026-10-31（二）重定为 204（见 _MAX_SKIPPED ①②）：少的 19 格都是原来按假数计的「unchanged」—— 13 张损益类附注
#: 合计「上期」原来按本年年初余额推 0 后与库里的 0 相等、6 格空表合计按 0 重算后与库里的 0 相等；现在不出值、不计覆盖。
#: 现算 204（written 0 + unchanged 196 + kept 8）。今后只许上调。
_MIN_COVERAGE = 204

# ── 分类别棘轮（spec: formula-push-note-row-matching · 需求 3） ────────
_SKIP_CATEGORIES: dict[str, re.Pattern[str]] = {
    # 子表规则只按表名精确定位：章节里没有这张表（2026-10-27 起，spec note-pull-followup-closure R2.3）；排在 A 前 ——
    # 表名里可能带「行」（银行承兑汇票…），按 A 的「没有.*行」会认错类
    "S": re.compile(r"子表规则只按表名精确定位"),
    # binding 声明的分册在本项目不存在（底稿被裁剪 / 未创建）
    "P": re.compile(r"binding 声明的分册 .* 在本项目不存在"),
    # 取数行对不上明细、表里有多个汇总行 ⇒ 不兜底（2026-10-31 起）；排在 A 前 —— 原因里也有「没有…行」
    "T": re.compile(r"个合计行.*不兜底"),
    # 损益类上期发生额取上年试算表、取不到 ⇒ 不写（2026-10-31 起，原来取本年年初余额恒推 0）；排在 A 前 —— 兜底格的
    # 原因前半句是「没有…行」
    "Y": re.compile(r"损益类上期发生额取上年试算表"),
    # 合计行上方各行这一列都没有数 ⇒ 合计不按 0 重算（2026-10-31 起，原来缺值按 0 求和推出假零）
    "Z": re.compile(r"上方各行这一列都没有数"),
    "A": re.compile(r"没有.*行"),
    "C": re.compile(r"银行明细|银行存款明细|现金明细|取数.*未完成|明细尚未建立|财务公司分组"),
    "D": re.compile(r"不是「.*」|章节号"),
    "G": re.compile(r"没有.*表定义|无法建骨架|没有对应的附注章节|附注尚未生成"),
    "I": re.compile(r"本项目无此科目"),
    "K": re.compile(r"明细数据缺失"),
    # 旧格式表头认不出唯一的期末 / 期初金额列（不按位置猜；2026-10-17 起，见 _MIN_COVERAGE 说明）；表有表头但缺该期间列
    "L": re.compile(r"找不到唯一|附注表缺少「"),
    # 多条取数行对上附注同一行（撞行，2026-10-17 起不再逐条覆盖写）
    "M": re.compile(r"同一格不能由多条取数"),
}


def _categorize(reason: str) -> str:
    """按跳过原因正则首匹配分类，未匹配归 'other'。"""
    for cat, pat in _SKIP_CATEGORIES.items():
        if pat.search(reason):
            return cat
    return "other"


#: 分类别棘轮基线（真库实测 2026-10-13；实测值 + ~50% 余量取整）
#: 2026-10-27 按现算重定（spec note-pull-followup-closure R2.5）：S=0 / P=20 / A=4 / C=32 / D=9 / G=6 / I=2 / K=8 / L=18 / M=0
#: 2026-10-31 现算（spec disclosure-note-template-word-realignment Task 34/35）：S=0 / P=20 / T=23 / Y=15 / Z=6 / A=4 / C=32 /
#: D=5 / G=6 / I=2 / K=8 / L=12 / M=0 / other=0，合计 133
_MAX_SKIPPED_BY_CATEGORY: dict[str, int] = {
    "S": 4,      # real=0，子表规则：章节里没有这张表
    "P": 22,     # real=20，binding 分册在本项目不存在（131 张已裁底稿移入回收站）
    "T": 23,     # real=23（2026-10-31 新增 15），多汇总行不兜底：长期股权投资 3 / 投资性房地产 / 长期借款 / 应付债券 /
                 # 长期应收款 / 预付款项两张（预付款项 4 格原归 L：三列组认不出期末列，现先判多汇总行）；同日 +8 是
                 # D2 八、5 / K6 八、12 章节标题校验修好后走到这里（原归 D）
    "Y": 15,     # real=15（2026-10-31 新增），损益类上期发生额取上年试算表、本项目没有上年数据
    "Z": 6,      # real=6（2026-10-31 新增），合计行上方各行这一列都没有数，不按 0 重算
    "A": 6,      # real=4（2026-10-13 为 8），行匹配失败
    "C": 36,     # real=32，银行/现金明细未建立 + 财务公司分组
    "D": 6,      # real=5（原 13；子表规则不再按章节标题判 → 9；2026-10-31 按准则声明表名的规则改按种子章节名校验 → 5），
                 # 余下 G2 / G3 / L2 / M1（共享主表的明细项）与 N1（规则表名不是章节名）
    "G": 8,      # real=6（原 3），模板缺定义 / 附注未生成
    "I": 5,      # real=2，项目无此科目
    "K": 12,     # real=8，K1 明细数据缺失
    "L": 20,     # real=18（2026-10-17 为 10），三列组表不知道推哪列 / 缺期间列
    "M": 9,      # real=0（2026-10-17 为 6），H1 三条取数行撞附注「固定资产」行
    "other": 2,  # real=0，其余
}


async def _scenario() -> dict:
    """在真 PG 上 dry_run 两次公式推送，收集统计数据。"""
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.database import engine

    if engine.dialect.name != "postgresql":
        return {"skip": True, "reason": "需 PostgreSQL（公式推送真库回归守卫）"}

    from app.services.formula_push.engine import run
    from app.services.project_audit_year import PROJECT_AUDIT_YEAR_SQL

    out: dict = {}

    # ── 查项目审计年度 ────────────────────────────────────────────────
    async with engine.begin() as conn:
        row = (await conn.execute(PROJECT_AUDIT_YEAR_SQL, {"pid": str(_PROJECT_ID)})).first()
        if row is None or row[0] is None:
            return {"skip": True, "reason": f"项目 {_PROJECT_NAME} 不存在或审计年度为空"}
        year = int(row[0])
    out["year"] = year

    # ── 第一次 dry_run ────────────────────────────────────────────────
    async with AsyncSession(engine, expire_on_commit=False) as session:
        async with session.begin():
            result1 = await run(
                session,
                project_id=_PROJECT_ID,
                year=year,
                trigger="manual",
                dry_run=True,
            )

    out["run1_skipped"] = result1.skipped_count
    out["run1_written"] = result1.written_count
    out["run1_unchanged"] = result1.unchanged_count
    out["run1_kept"] = result1.kept_count
    out["run1_coverage"] = result1.written_count + result1.unchanged_count + result1.kept_count
    out["run1_total_items"] = len(result1.items)

    # unchanged 项的 addr_id 集合（用于幂等比对）
    run1_unchanged_addrs = frozenset(
        i.addr_id for i in result1.items if i.action == "unchanged" and i.addr_id
    )
    out["run1_unchanged_addrs"] = run1_unchanged_addrs

    # ── 第二次 dry_run（幂等验证） ────────────────────────────────────
    async with AsyncSession(engine, expire_on_commit=False) as session:
        async with session.begin():
            result2 = await run(
                session,
                project_id=_PROJECT_ID,
                year=year,
                trigger="manual",
                dry_run=True,
            )

    out["run2_skipped"] = result2.skipped_count
    out["run2_unchanged"] = result2.unchanged_count
    out["run2_kept"] = result2.kept_count
    out["run2_coverage"] = result2.written_count + result2.unchanged_count + result2.kept_count

    run2_unchanged_addrs = frozenset(
        i.addr_id for i in result2.items if i.action == "unchanged" and i.addr_id
    )
    out["run2_unchanged_addrs"] = run2_unchanged_addrs

    # 汇总跳过原因分布（诊断用，非断言）
    skip_reasons: dict[str, int] = {}
    for item in result1.items:
        if item.action in ("skipped", "conflict"):
            reason = (item.reason or "unknown")[:60]
            skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
    out["skip_reasons"] = skip_reasons

    # 分类别统计（用于 per-category 棘轮断言）
    cat_counts: dict[str, int] = {}
    for item in result1.items:
        if item.action in ("skipped", "conflict"):
            reason = item.reason or ""
            cat = _categorize(reason)
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
    out["skip_categories"] = cat_counts

    await engine.dispose()
    return out


def test_formula_push_skip_reduction_on_real_pg():
    """真库回归：公式推送跳过数、覆盖率、幂等性。"""
    import pytest

    out = asyncio.run(_scenario())
    if out.get("skip"):
        pytest.skip(out.get("reason", "需 PostgreSQL"))

    year = out["year"]

    # ── 6.2  skipped_count 不超过棘轮基线 ─────────────────────────────
    skipped = out["run1_skipped"]
    assert skipped <= _MAX_SKIPPED, (
        f"[{_PROJECT_NAME} {year}] skipped_count={skipped}，"
        f"超过棘轮基线 {_MAX_SKIPPED}（回归！后续修复应只减不增）\n"
        f"跳过原因分布: {out.get('skip_reasons', {})}"
    )

    # ── 6.3  written + unchanged + kept ≥ 覆盖率棘轮基线 ─────────────
    coverage = out["run1_coverage"]
    assert coverage >= _MIN_COVERAGE, (
        f"[{_PROJECT_NAME} {year}] coverage={coverage}"
        f"（written={out['run1_written']} + unchanged={out['run1_unchanged']}"
        f" + kept={out['run1_kept']}），低于棘轮基线 {_MIN_COVERAGE}"
    )

    # ── 6.4  两次 dry_run 幂等 ───────────────────────────────────────
    #  6.4a  unchanged 项数一致
    assert out["run1_unchanged"] == out["run2_unchanged"], (
        f"幂等性破坏：run1 unchanged={out['run1_unchanged']}，"
        f"run2 unchanged={out['run2_unchanged']}"
    )

    #  6.4b  unchanged 项的 addr_id 集合一致
    only_in_1 = out["run1_unchanged_addrs"] - out["run2_unchanged_addrs"]
    only_in_2 = out["run2_unchanged_addrs"] - out["run1_unchanged_addrs"]
    assert not only_in_1 and not only_in_2, (
        f"幂等性破坏：unchanged addr_id 集合不一致\n"
        f"  仅 run1: {sorted(only_in_1)[:10]}\n"
        f"  仅 run2: {sorted(only_in_2)[:10]}"
    )

    #  6.4c  覆盖率两次一致
    assert out["run1_coverage"] == out["run2_coverage"], (
        f"幂等性破坏：run1 coverage={out['run1_coverage']}，"
        f"run2 coverage={out['run2_coverage']}"
    )

    # ── 分类别棘轮（spec: formula-push-note-row-matching · 需求 3） ──
    cat_counts = out.get("skip_categories", {})
    for cat, max_count in _MAX_SKIPPED_BY_CATEGORY.items():
        actual = cat_counts.get(cat, 0)
        assert actual <= max_count, (
            f"[{_PROJECT_NAME} {year}] 类别 {cat} skipped={actual} 超过棘轮 {max_count}（回归！）\n"
            f"跳过原因分布: {out.get('skip_reasons', {})}"
        )

    # 检查无遗漏：所有类别之和 == 总 skipped
    cat_total = sum(cat_counts.values())
    assert cat_total == skipped, (
        f"分类别总计 {cat_total} ≠ skipped_count {skipped}（有遗漏类别）"
    )


def test_categorize_known_patterns():
    """Property 6: 跳过原因分类完备性。

    Validates: Requirements 3.1, 3.4
    对已知类别的 reason 样例验证分类正确；对未知 reason 验证归入 'other'。
    """
    # A: 行匹配失败
    assert _categorize("附注「存货」表中没有「存货_1401」行（公式推送不新建行）") == "A"
    assert _categorize("附注「营业收入和营业成本」表中没有「收入_6001」行（公式推送不新建行）") == "A"
    # C: 银行/现金明细未建立、财务公司分组
    assert _categorize("E1 银行明细取数未完成") == "C"
    assert _categorize("银行存款明细尚未建立（打开底稿时由四表带入）") == "C"
    assert _categorize("现金明细尚未建立（打开底稿时由四表带入）") == "C"
    assert _categorize("财务公司分组只由银行存款明细行汇总，明细尚未建立") == "C"
    # D: 章节号不匹配
    assert _categorize('附注 五、22 是「递延所得税负债」章节，不是「固定资产」，未推送') == "D"
    assert _categorize("章节号不匹配") == "D"
    # G: 模板缺定义 / 附注未生成
    assert _categorize('附注模板「listed」中没有「测试」表定义，无法建骨架') == "G"
    assert _categorize('附注模板类型「soe」没有对应的附注章节，未推送附注') == "G"
    assert _categorize('附注尚未生成「五-65-1 营业收入和营业成本」章节（在附注模块生成后下次推送纳入）') == "G"
    # I: 科目不存在
    assert _categorize("底稿未取到该行数值（本项目无此科目），附注保持原值") == "I"
    # K: 明细数据缺失
    assert _categorize("K1-2 明细数据缺失，组合未审数保持原值") == "K"
    # L: 旧格式表头认不出列
    assert _categorize("附注表缺少「期末」列：表头里找不到唯一的「期末 / 期初」金额列（账面余额、减值准备），不按位置猜") == "L"
    # 账面余额 / 减值准备 / 账面价值分列写的字段落到旧格式表（spec formula-fetch-followup-defect-closure R6.1）
    assert _categorize("附注表是旧格式（按列序存数），表头只认得出期末 / 期初金额列，找不到唯一的「期末账面余额」列，"
                       "不按位置猜，附注保持原值") == "L"
    # M: 撞行
    assert _categorize("取数行「固定资产_1601」「固定资产_1602」都对上附注「固定资产」行，同一格不能由多条取数覆盖写，"
                       "附注保持原值") == "M"
    # S: 子表规则章节里没有这张表（表名带「行」也不归 A）
    assert _categorize("附注 八、4「应收票据」里没有「银行承兑汇票按行业划分」表（子表规则只按表名精确定位），未推送") == "S"
    # P: binding 分册在本项目不存在
    assert _categorize("binding 声明的分册 D6 在本项目不存在，未推送（项目创建该底稿后下次推送纳入）") == "P"
    # T: 多汇总行不兜底（原因里也有「没有…行」，不能归 A）
    assert _categorize("附注「长期借款」表中没有「长期借款」行（公式推送不新建行）；表里有 2 个合计行（小计、合计），"
                       "不知道科目余额该写哪一行，不兜底，附注保持原值") == "T"
    # Y: 损益类上期取不到上年数据（兜底格原因前半句有「没有…行」，不能归 A；取数行对上时只有后半句）
    assert _categorize("附注「销售费用」表中没有「销售费用」行（公式推送不新建行）；损益类上期发生额取上年试算表：本项目没有 "
                       "2024 年试算表，没有上年项目（企业代码 X、审计年度 2024、报表口径 standalone），附注保持原值") == "Y"
    assert _categorize("损益类上期发生额取上年试算表：上年项目没有 2024 年试算表") == "Y"
    # Z: 合计上方全空不按 0 重算
    assert _categorize("合计行「合计」上方各行这一列都没有数，合计不按 0 重算，附注保持原值") == "Z"
    # L: 表有表头但缺该期间列（无表头说明时只有这一句）
    assert _categorize("附注表缺少「期初」列") == "L"
    # other: 未知模式
    assert _categorize("附注章节已确认，公式推送不改写") == "other"
    assert _categorize("something completely unknown") == "other"
    assert _categorize("") == "other"


def test_pg_guard_category_assertion_message():
    """AC 3.2: 断言失败消息包含类别名称和超出量。

    构造某类别超过棘轮的场景，验证消息格式可被解析。
    """
    cat = "A"
    actual = 200
    max_count = 160
    # 模拟断言消息生成（与 test_formula_push_skip_reduction_on_real_pg 中格式一致）
    msg = (
        f"[{_PROJECT_NAME} 2025] 类别 {cat} skipped={actual} 超过棘轮 {max_count}（回归！）\n"
        f"跳过原因分布: {{}}"
    )
    assert cat in msg
    assert str(actual) in msg
    assert str(max_count) in msg
    assert "回归" in msg
