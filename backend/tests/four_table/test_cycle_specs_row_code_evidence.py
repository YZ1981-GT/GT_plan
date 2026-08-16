"""`*_cycle_specs.py` 的 `row_code` ↔ `report_config` 行名实证冻结。

**为什么需要这条守卫（2026-08-03 对账后新建）**

各 per-cycle spec 的 `row_code` **从未与 `report_config` 对过账** ——
只对过 `fallback_standard_codes`。实测 18 个声明文件里查出**一整批错位**::

    循环  声明 row_code   该行实际是什么                    危害
    M1   BS-048         应付职工薪酬（公式 TB('2211')）     层③把应付股利解析成应付职工薪酬
    M2   BS-070         负债合计                          —
    M3   BS-071         其他非流动负债 / 应付福利费          —
    M4   BS-072         #其中：职工奖励及福利基金 / 非流动负债合计 —
    M5   BS-074         其中：应交税金 / 股东权益：          —
    M7   BS-075         其他应付款 / 股本                  —
    M8   BS-076         其中：应付股利 / 其他权益工具        —
    M9   BS-073         应交税费 / 负债合计                 —
    M10  BS-077         ▲应付手续费及佣金 / 其中：优先股     —
    I5   BS-039         资产总计                          —
    I6   IS-007         财务费用（公式 TB('6603')）         层③把研发费用解析成财务费用
    L3   BS-060         非流动负债：（节标题）              —
    L4   BS-061         长期借款                          层③把应付债券解析成长期借款
    L6   BS-065         预计负债（K5 的行，公式 TB('2801')） 层③把专项应付款解析成预计负债
    L7   BS-066         递延收益（K7 的行）                层③把其他非流动负债解析成递延收益
    L8   IS-009         利息收入                          —
    N2   BS-052         一年内到期的非流动负债（公式 TB('2501')）层③把应交税费解析成长期借款

标「层③…」的四条是**活的数字级错误**（那些行有公式且码在科目表里存在）；
其余因公式为 None 或指向 `ROW()` 派生行而暂时惰性 —— 但一旦有人补上公式就立刻变成
「越正确接入共享件、取数越错」。

**本守卫不连库**：把对账结论冻结成常量表（`_ROW_CODE_EVIDENCE`），
断言 spec 声明与冻结值一致。DB 侧的真实性由
`scripts/diagnose/audit_render_hardcoded_account_codes.py` + 本文件的证据表注释共同保证。

spec: .kiro/specs/semantic-account-resolver-full-rollout/
"""
from __future__ import annotations

import pytest

# ──────────────────────────────────────────────────────────────────────────────
# 冻结证据：row_code -> (report_config 行名, 公式摘要)
#
# 全部取自 2026-08-03 对 `report_config` 的只读查询（10 个项目库同一张配置表）。
# 行名跨 4 个 applicable_standard 若不同则用 " / " 连接（按 row_code, standard 排序）。
# ──────────────────────────────────────────────────────────────────────────────
_ROW_CODE_EVIDENCE: dict[str, tuple[str, str | None]] = {
    # ── 资产 ──
    "BS-003": ("交易性金融资产", "TB"),
    "BS-005": ("应收票据", "TB"),
    "BS-006": ("应收账款", "TB"),
    "BS-007": ("应收款项融资", "TB"),
    "BS-008": ("预付款项", "TB"),
    "BS-010": ("存货", "TB"),
    "BS-011": ("合同资产", "TB"),
    "BS-021": ("债权投资", "TB"),
    "BS-022": ("其他债权投资", "TB"),
    "BS-023": ("长期应收款", "TB"),
    "BS-024": ("长期股权投资", "TB"),
    "BS-025": ("其他权益工具投资", "TB"),
    "BS-026": ("其他非流动金融资产", "TB"),
    "BS-027": ("投资性房地产", "TB"),
    "BS-028": ("固定资产", "TB"),
    "BS-029": ("在建工程", "TB"),
    "BS-030": ("生产性生物资产", "TB"),
    "BS-031": ("使用权资产", "TB"),
    "BS-032": ("无形资产", "TB"),
    "BS-033": ("开发支出", "TB"),
    "BS-034": ("商誉", "TB"),
    "BS-035": ("长期待摊费用", "TB"),
    "BS-036": ("递延所得税资产", "TB"),
    "BS-037": ("其他非流动资产", "TB"),  # = TB('1911')；1911 全库两张科目表都不存在
    "BS-039": ("资产总计", "ROW"),       # 派生行，不是科目行
    # ── K 循环资产侧（2026-08-09 连库对账登记，四变体全部同名、无一码两义）──
    "BS-009": ("其他应收款", "TB"),      # K1 正解；soe_standalone 公式含 −TB('1231-03')+TB('1131')
    "BS-012": ("持有待售资产", "TB"),     # K6 正解；= TB('1481')，备抵在 IMP-007
    "BS-014": ("其他流动资产", None),     # K2 正解；四变体公式全 NULL ⇒ 恒退兜底 1901
    # ── 负债 ──
    "BS-041": ("短期借款", "TB"),
    "BS-042": ("交易性金融负债", "TB"),
    "BS-044": ("应付票据", "TB"),
    "BS-045": ("应付账款", "TB"),
    "BS-046": ("预收款项", "TB"),
    "BS-047": ("合同负债", "TB"),
    "BS-048": ("应付职工薪酬", "TB"),    # 🔴 M1 曾误当「应付股利」
    "BS-049": ("应交税费", "TB"),        # N2 正解
    "BS-052": ("一年内到期的非流动负债", "TB"),  # 🔴 公式 TB('2501') 实为长期借款
    "BS-050": ("其他应付款", "TB"),      # K3 正解；listed/soe_standalone 含 +TB('2231') 应付利息
    "BS-051": ("持有待售负债", "TB"),     # K6 负债侧；= TB('2245')
    "BS-053": ("其他流动负债", None),     # K4 正解；四变体公式全 NULL（2301 全库零命中）
    "BS-055": ("应付股利", None),        # M1 正解（仅 listed，公式 None）
    "BS-060": ("非流动负债：", None),     # 节标题
    "BS-061": ("长期借款", "TB"),        # L3 正解
    "BS-062": ("应付债券", "TB"),        # L4 正解
    "BS-063": ("租赁负债", "TB"),        # H9
    "BS-064": ("长期应付款", "TB"),      # L5
    "BS-065": ("预计负债", "TB"),        # K5
    "BS-066": ("递延收益", "TB"),        # K7
    "BS-067": ("递延所得税负债", "TB"),   # N3
    "BS-068": ("其他非流动负债", "TB"),   # L7 正解；= TB('2911')，2911 全库不存在
    # ── 权益 ──
    "BS-081": ("实收资本（或股本）", "TB"),  # M2 正解
    "BS-082": ("其他权益工具", "TB"),        # M10 正解；🔴 公式 TB('4003') 实为 OCI
    "BS-083": ("资本公积", "TB"),            # M4
    "BS-084": ("减：库存股", "TB"),          # M3 正解；🔴 公式 TB('4005') 该码不存在
    "BS-085": ("其他综合收益", "TB"),        # M9 正解；🔴 公式 TB('4102') 该码不存在
    "BS-086": ("专项储备", "TB"),            # M7 正解；🔴 公式 TB('4103') 实为本年利润
    "BS-087": ("盈余公积", "TB"),            # M5
    "BS-088": ("未分配利润", "TB"),          # M6
    "BS-124": ("△一般风险准备", None),        # M8 正解（仅 soe，公式 None）
    # ── 利润表 ──
    "IS-001": ("一、营业收入", "TB"),
    "IS-002": ("减：营业成本", "TB"),
    "IS-003": ("税金及附加", "TB"),      # N4
    "IS-004": ("销售费用", "TB"),        # K8 正解；= TB('6601')
    "IS-005": ("管理费用", "TB"),        # K9 正解；= TB('6602')
    "IS-006": ("研发费用", "TB"),        # I6 正解；= TB('6604')
    "IS-007": ("财务费用", "TB"),        # L8 正解；= TB('6603')
    "IS-009": ("利息收入", None),
    "IS-010": ("加：其他收益", "TB"),     # K10 正解；= TB('6117')
    "IS-011": ("投资收益", "TB"),
    "IS-014": ("净敞口套期收益", None),
    "IS-015": ("公允价值变动收益", "TB"),
    "IS-016": ("信用减值损失", "TB"),
    "IS-017": ("资产减值损失", "TB"),     # K11 正解；= TB('6701')
    "IS-018": ("资产处置收益", "TB"),
    "IS-020": ("加：营业外收入", "TB"),   # K12 正解；= TB('6301')
    "IS-021": ("减：营业外支出", "TB"),   # K13 正解；= TB('6711')
    "IS-023": ("减：所得税费用", "TB"),   # N5
}

#: `report_config` 公式已被 DB 实证为**错码**的行 —— 引用它们的 spec 必须
#: `trust_report_config=False`。每条写明错在哪。
#:
#: 🔴🔴 **跨 spec 接缝（2026-08-03 立 → 2026-08-05 已收口）**：
#: `.kiro/specs/report-config-account-code-integrity/` 的**迁移 V138** 已应用，
#: 把 `report_config` 的 13 行错码改对，其中 4 行原本登记在本表：
#: `BS-082 4003→4401` / `BS-084 4005→4201` / `BS-085 4102→4003` / `BS-086 4103→4301`
#: （另有 `EQ-015 4201→4301`，无 spec 引用它）。
#:
#: → 这 4 行**已从本表移出**，`m_cycle_specs` 里 M3/M7/M9/M10 的
#: `trust_report_config=False` 同步移除、层③恢复启用。
#: 那批 flag 是**针对错码的临时防护**，数据改对后继续关掉层③会让
#: 「客户科目表缺该科目」的项目白白取不到数（层③本来能救）。
#:
#: 🔴 剩下的 `IS-006` **与 V138 无关**、必须保留：它不是错码而是
#: 「同一码在不同客户科目表里是不同科目」（`6604` standard 侧 6 个项目叫「研发费用」，
#: client 侧 1 个项目叫「勘探费用」）—— 改 `report_config` 解决不了，只能关层③。
#:
#: 本表**静态冻结、不连库**，过期不会自己打红 →
#: `test_wrong_formula_rows_exclude_v138_fixed_rows` 与
#: `CODE_CORRECTIONS` 交叉锁死，把「该移出却没移出」变成硬失败。
_WRONG_FORMULA_ROWS: dict[str, str] = {
    "IS-006": "研发费用 = TB('6604')，6604 在 1 个客户表里是「勘探费用」",
}


#: 声明表里「一个 spec 携带多个 row_code」的字段名（按声明顺序）。
#:
#: 🔴 K 循环的 `KCycleSpec` 是 **`row_code_listed` / `row_code_soe` 双字段**
#:    （两准则行号可能不同），而其余循环的 `SemanticAccountSpec` 是单字段
#:    `row_code`。本文件全部判据原先只读 `spec.row_code` ⇒ 把 K 直接加进
#:    `_all_specs()` 会让 `getattr(spec, 'row_code', None)` 恒返 None、
#:    每条断言静默跳过 = **空转**（比不加更坏：看起来覆盖了 K，其实没有）。
#:    故统一改为经 :func:`_row_codes_of` 取「该 spec 声明的全部 row_code」。
_MULTI_ROW_CODE_FIELDS: tuple[str, ...] = ("row_code_listed", "row_code_soe")


def _row_codes_of(spec: object) -> list[tuple[str, str]]:
    """取 spec 声明的全部 row_code，返回 ``[(字段名, row_code), ...]``。

    - 单字段形态（`SemanticAccountSpec`）→ ``[('row_code', 'BS-055')]``
    - 双字段形态（`KCycleSpec`）→ ``[('row_code_listed', ...), ('row_code_soe', ...)]``

    `None`/空串一律剔除（L6 专项应付款声明 `row_code=None` 是有意的）。
    """
    out: list[tuple[str, str]] = []
    single = getattr(spec, "row_code", None)
    if isinstance(single, str) and single.strip():
        out.append(("row_code", single))
    for f in _MULTI_ROW_CODE_FIELDS:
        v = getattr(spec, f, None)
        if isinstance(v, str) and v.strip():
            out.append((f, v))
    return out


def _all_specs() -> dict[str, dict[str, object]]:
    """{文件标签: {spec 名: SemanticAccountSpec | KCycleSpec}}"""
    from app.services.four_table import (
        d_cycle_specs, f_cycle_specs, g_cycle_specs, i_cycle_specs,
        k_cycle_specs, l_cycle_specs, m_cycle_specs, n_cycle_specs,
    )

    out: dict[str, dict[str, object]] = {}
    for label, mod, attr in [
        ("D", d_cycle_specs, "D_CYCLE_SPECS"),
        ("F", f_cycle_specs, "F_CYCLE_SPECS"),
        ("G", g_cycle_specs, "G_CYCLE_SPECS"),
        ("I", i_cycle_specs, "I_CYCLE_SPECS"),
        # 🔴 K 于 2026-08-09 接入（spec k-cycle-…-closure Task 6）。它是双 row_code
        #    形态，判据须走 `_row_codes_of`；直接读 `.row_code` 会静默空转。
        ("K", k_cycle_specs, "K_CYCLE_SPECS"),
        ("L", l_cycle_specs, "L_CYCLE_SPECS"),
        ("M", m_cycle_specs, "M_CYCLE_SPECS"),
        ("N", n_cycle_specs, "N_CYCLE_SPECS"),
    ]:
        registry = getattr(mod, attr, None)
        if isinstance(registry, dict):
            out[label] = dict(registry)
    return out


def test_multi_row_code_extraction_actually_covers_k():
    """反向自检：`_row_codes_of` 对双字段形态真的抽出两个码。

    这条专门钉死上面注释里说的「空转」缺陷 —— 若有人把判据改回裸
    `spec.row_code`，K 的覆盖会静默消失而其余断言仍全绿。
    """
    specs = _all_specs()
    assert "K" in specs, "K_CYCLE_SPECS 未被收集（注册表名或导入路径失效）"
    k3 = specs["K"]["K3"]
    # 单字段访问必须拿不到（证明「裸 .row_code」确实会空转）
    assert getattr(k3, "row_code", None) is None, (
        "KCycleSpec 不应有单字段 `row_code`；若已改为单字段，"
        "请同时简化 `_row_codes_of` 并移除本断言"
    )
    pairs = _row_codes_of(k3)
    fields = {f for f, _ in pairs}
    assert fields == {"row_code_listed", "row_code_soe"}, (
        f"K3 应抽出两个 row_code 字段，实为 {sorted(fields)}"
    )
    assert all(rc.startswith("BS-") for _, rc in pairs), pairs
    # 单字段形态仍要能抽出来（防改坏其余 7 个循环）
    m1 = specs["M"]["M1"]
    assert _row_codes_of(m1) == [("row_code", m1.row_code)]


# ──────────────────────────────────────────────────────────────────────────────
# 反向自检
# ──────────────────────────────────────────────────────────────────────────────

def test_specs_are_importable():
    specs = _all_specs()
    assert len(specs) >= 6, f"只导入到 {sorted(specs)}，注册表名或路径失效"
    total = sum(len(v) for v in specs.values())
    assert total >= 40, f"只收集到 {total} 个 spec，疑似注册表结构变了"


def test_evidence_table_not_empty():
    assert len(_ROW_CODE_EVIDENCE) >= 50
    assert _WRONG_FORMULA_ROWS


def test_wrong_formula_rows_are_in_evidence():
    """反向自检：错码清单里的行必须也在证据表里（防清单指向不存在的行）。"""
    missing = sorted(r for r in _WRONG_FORMULA_ROWS if r not in _ROW_CODE_EVIDENCE)
    assert not missing, f"错码清单引用了证据表里没有的行：{missing}"


def test_wrong_formula_rows_carry_v138_seam_note():
    """`_WRONG_FORMULA_ROWS` 是**临时**防护，必须带 V138 接缝说明。

    没有这条断言，V138 把 `report_config` 改对后本表会**静默过期**：
    静态冻结值不连库，不会打红，于是 `trust_report_config=False`
    永久留下去 —— 那会让「客户科目表缺该科目」的项目白白取不到数。
    """
    import inspect
    import sys

    src = inspect.getsource(sys.modules[__name__])
    assert "V138" in src, (
        "`_WRONG_FORMULA_ROWS` 必须写明 V138 落地后要清空 —— 否则这份临时防护会静默过期"
    )
    assert "report-config-account-code-integrity" in src, (
        "必须指向负责修数据的 spec，否则下个会话不知道去哪确认是否已修"
    )


def test_wrong_formula_rows_exclude_v138_fixed_rows():
    """🔴 与 V138 改码真源交叉锁死：已改对的行不得再留在本表。

    上一条断言只保证「有说明文字」，管不住「说明写了但没照做」。本条直接拿
    ``CODE_CORRECTIONS``（V138 的改码真源）做差集 —— 数据已改对却仍登记为错码，
    就会让 `trust_report_config=False` 永久留下去（层③被白白关掉）。

    反过来若将来 V139 又修了别的行，本断言会立刻要求把它从本表移出，无需人工记账。
    """
    from app.services.four_table.report_config_account_names import CODE_CORRECTIONS

    assert CODE_CORRECTIONS, "CODE_CORRECTIONS 为空 —— 判据真源失效，本断言会空转"

    stale = sorted(set(_WRONG_FORMULA_ROWS) & set(CODE_CORRECTIONS))
    assert not stale, (
        f"以下行已由 V138 改对（见 report_config_account_names.CODE_CORRECTIONS），"
        f"必须从 `_WRONG_FORMULA_ROWS` 移出，并同步删掉对应 spec 的 "
        f"`trust_report_config=False`：{stale}"
    )


def test_is006_stays_because_it_is_not_a_wrong_code():
    """🔴 反面锁死：`IS-006` 不是错码，不得被「顺手」当成 V138 遗留一起清掉。

    它是「一码两义」——`6604` 在 standard 侧 6 个项目叫「研发费用」、client 侧
    1 个项目叫「勘探费用」。改 `report_config` 解决不了这类问题，只能靠关闭层③
    + 按科目名逐项目定位。清掉它会让那个客户项目的研发费用取到勘探费用。
    """
    from app.services.four_table.report_config_account_names import CODE_CORRECTIONS

    assert "IS-006" in _WRONG_FORMULA_ROWS, (
        "IS-006 被移出了 `_WRONG_FORMULA_ROWS` —— 它不是错码而是一码两义，"
        "移出后 I6 的 `trust_report_config=False` 会被判为「无理由关闭层③」而打红，"
        "且那个客户项目的研发费用会取到勘探费用"
    )
    assert "IS-006" not in CODE_CORRECTIONS, (
        "IS-006 出现在 V138 改码清单里 —— 与「一码两义无法靠改码解决」的判定矛盾，请复核"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 主断言
# ──────────────────────────────────────────────────────────────────────────────

def test_declared_row_codes_are_known():
    """每个 spec 声明的 `row_code` 必须在冻结证据表里（新增行须先对账后登记）。

    🔴 走 :func:`_row_codes_of` 而非裸 `.row_code` —— K 的双字段形态在裸读法下
    恒返 None，会让 14 个 K 码静默逃出登记检查。
    """
    unknown: list[str] = []
    for label, registry in _all_specs().items():
        for name, spec in registry.items():
            for field, rc in _row_codes_of(spec):
                if rc not in _ROW_CODE_EVIDENCE:
                    unknown.append(f"{label}/{name}.{field} -> {rc}")
    assert not unknown, (
        "以下 row_code 未在 `_ROW_CODE_EVIDENCE` 登记 —— 请先用\n"
        "  python backend/scripts/diagnose/audit_render_hardcoded_account_codes.py --reconcile\n"
        "或直查 report_config 对账，再把结论登记进证据表：\n"
        + "\n".join(f"  {u}" for u in unknown)
    )


#: 循环 -> (期望 row_code, 该行的语义)。**只登记本轮对账改正过的**，
#: 用于钉死「不得回退到错行」。
_CORRECTED: list[tuple[str, str, str, str]] = [
    ("M", "M1", "BS-055", "应付股利"),
    ("M", "M2", "BS-081", "实收资本（或股本）"),
    ("M", "M3", "BS-084", "减：库存股"),
    ("M", "M4", "BS-083", "资本公积"),
    ("M", "M5", "BS-087", "盈余公积"),
    ("M", "M7", "BS-086", "专项储备"),
    ("M", "M8", "BS-124", "△一般风险准备"),
    ("M", "M9", "BS-085", "其他综合收益"),
    ("M", "M10", "BS-082", "其他权益工具"),
    ("I", "I5", "BS-037", "其他非流动资产"),
    ("I", "I6", "IS-006", "研发费用"),
    ("L", "L3", "BS-061", "长期借款"),
    ("L", "L4", "BS-062", "应付债券"),
    ("L", "L7", "BS-068", "其他非流动负债"),
    ("L", "L8", "IS-007", "财务费用"),
    ("N", "N2", "BS-049", "应交税费"),
    # 🔴 K 类 9 处改正（2026-08-09，spec k-cycle-…-closure Task 4）。
    #    `_all_specs()` 对 K 用 `row_code_soe`（错位全在 soe 侧，listed 侧另有
    #    3 处 ROW 派生行错位由 `test_k_cycle_row_code_evidence` 连库守）。
    ("K", "K3", "BS-050", "其他应付款"),
    ("K", "K4", "BS-053", "其他流动负债"),
    ("K", "K5", "BS-065", "预计负债"),
    ("K", "K6", "BS-012", "持有待售资产"),
    ("K", "K7", "BS-066", "递延收益"),
    ("K", "K8", "IS-004", "销售费用"),
    ("K", "K9", "IS-005", "管理费用"),
    ("K", "K10", "IS-010", "加：其他收益"),
    ("K", "K11", "IS-017", "资产减值损失"),
    ("K", "K12", "IS-020", "加：营业外收入"),
    ("K", "K13", "IS-021", "减：营业外支出"),
]


@pytest.mark.parametrize("label,wp,expected_row,concept", _CORRECTED)
def test_corrected_row_codes_stay_corrected(
    label: str, wp: str, expected_row: str, concept: str
):
    """本轮对账改正的 row_code 不得回退。

    🔴 双字段形态（K）按「**每一个**声明的 row_code 都必须等于期望值」判 ——
    K 的 9 处改正后两准则同号（DB 实证），故 listed/soe 两侧都该是 `expected_row`；
    只校验其中一侧会让另一侧被改坏时不打红。
    """
    registry = _all_specs()[label]
    spec = registry[wp]
    pairs = _row_codes_of(spec)
    assert pairs, f"{label}/{wp} 未声明任何 row_code（判据会空转）"
    wrong = [(f, rc) for f, rc in pairs if rc != expected_row]
    assert not wrong, (
        f"{wp} 声明的 row_code 应全部为 {expected_row}（{concept}），"
        f"以下字段不符：{wrong}（全部声明：{pairs}）"
    )
    # 证据表里该行的名称必须与概念相符（防证据表本身被改坏）
    name, _ = _ROW_CODE_EVIDENCE[expected_row]
    assert concept in name or name in concept, (
        f"证据表里 {expected_row} 的行名是 {name!r}，与 {wp} 的概念 {concept!r} 不符"
    )


def test_l6_special_payable_has_no_row_code():
    """专项应付款在资产负债表无独立行 —— 不得再指向 `BS-065`（预计负债/K5）。"""
    spec = _all_specs()["L"]["L6"]
    assert spec.row_code is None, (
        f"L6 专项应付款不应声明 row_code（实为 {spec.row_code}）；"
        "BS-065 是预计负债（K5），层③会取到 2801"
    )


def test_specs_citing_wrong_formula_rows_distrust_report_config():
    """引用了「公式已实证为错码」的行，必须显式 `trust_report_config=False`。"""
    violations: list[str] = []
    for label, registry in _all_specs().items():
        for wp, spec in registry.items():
            if not getattr(spec, "trust_report_config", True):
                continue
            for field, rc in _row_codes_of(spec):
                if rc in _WRONG_FORMULA_ROWS:
                    violations.append(
                        f"{label}/{wp}.{field} 引用 {rc} 但未关闭层③ —— "
                        f"{_WRONG_FORMULA_ROWS[rc]}"
                    )
    assert not violations, "\n".join(violations)


def test_distrust_flag_only_used_where_justified():
    """反向：关闭层③必须有据（该行在错码清单里），防止无理由一律关闭。

    关闭层③会让「客户科目表缺该科目」的项目彻底取不到数 —— 这是有代价的，
    不能当万能开关用。
    """
    unjustified: list[str] = []
    for label, registry in _all_specs().items():
        for wp, spec in registry.items():
            if getattr(spec, "trust_report_config", True):
                continue
            codes = [rc for _f, rc in _row_codes_of(spec)]
            # 双 row_code 形态：只要**任一**声明的行在错码清单里就算有据
            # （关层③是 spec 级开关，不分准则）。
            if not any(rc in _WRONG_FORMULA_ROWS for rc in codes):
                unjustified.append(
                    f"{label}/{wp} 关闭了层③但声明的行 {codes or ['(无)']} "
                    "都不在 `_WRONG_FORMULA_ROWS` 清单里"
                )
    assert not unjustified, (
        "关闭 `trust_report_config` 必须在 `_WRONG_FORMULA_ROWS` 里登记理由：\n"
        + "\n".join(f"  {u}" for u in unjustified)
    )


def test_no_two_cycles_claim_same_row_code():
    """同一 `row_code` 不得被两个**循环**认领（除已知的合法共享）。

    🔴 归并粒度是「循环」不是「(循环, 字段)」—— K 的 `row_code_listed` 与
    `row_code_soe` 绝大多数同码（DB 实测两准则同号），若按 (循环,字段) 计数
    会把 K3 自己的两个字段算成「两个认领者」⇒ 11 个 K 循环全部假撞码。
    故先按 `label/wp` 去重再统计。
    """
    #: 合法共享：H1 固定资产与 H6 固定资产清理同属 `BS-028`；
    #: H2 在建工程与 H4 工程物资同属 `BS-029`（H4 是 H2 的子表）。
    allowed_shared = {"BS-028", "BS-029"}
    seen: dict[str, set[str]] = {}
    for label, registry in _all_specs().items():
        for wp, spec in registry.items():
            owner = f"{label}/{wp}"
            for _field, rc in _row_codes_of(spec):
                seen.setdefault(rc, set()).add(owner)
    dupes = {
        rc: sorted(owners)
        for rc, owners in seen.items()
        if len(owners) > 1 and rc not in allowed_shared
    }
    assert not dupes, f"row_code 被多个循环认领：{dupes}"


def test_collision_check_ignores_intra_cycle_dual_fields():
    """反向自检：同循环两准则同码**不算**撞码，跨循环同码**算**撞码。

    这条钉死上面那个归并粒度 —— 若有人把 `set` 改回 `list`，K 会全部假撞码；
    若有人连跨循环也一起去重，真撞码会被放过。
    """
    from dataclasses import dataclass

    @dataclass
    class _Dual:  # 替身：模拟 KCycleSpec 的双字段形态
        row_code_listed: str
        row_code_soe: str

    def _collide(registries: dict[str, dict[str, object]]) -> dict[str, list[str]]:
        seen: dict[str, set[str]] = {}
        for label, reg in registries.items():
            for wp, spec in reg.items():
                for _f, rc in _row_codes_of(spec):
                    seen.setdefault(rc, set()).add(f"{label}/{wp}")
        return {rc: sorted(o) for rc, o in seen.items() if len(o) > 1}

    # 同一循环两准则同码 → 不得报撞码
    assert _collide({"X": {"X1": _Dual("BS-999", "BS-999")}}) == {}
    # 两个循环同码 → 必须报撞码
    assert _collide(
        {"X": {"X1": _Dual("BS-999", "BS-999"), "X2": _Dual("BS-999", "BS-999")}}
    ) == {"BS-999": ["X/X1", "X/X2"]}
