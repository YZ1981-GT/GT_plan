"""D 循环（应收/预收/营收）语义科目定位规格 — 跨 D1~D7 单一真源。

.. warning::
   🔴 **本文件当前不接线**（2026-08-05 定论，勿再发起迁移）

   D 类 7 个 render **不使用** 本文件的 :class:`SemanticAccountSpec`，而是走
   ``report_line_accounts`` 路径（D1 → ``d1_account_resolver``、D2~D7 →
   ``d_cycle_extraction.d_account_resolver``、D4 → ``D4AccountScope``）。

   **不接线的实证理由**（曾按「grep resolve_semantic_accounts 得 0」误判为
   「D 类完全没接科目映射」，那个判据是错的）：

   1. **D1 早已有完整链路** —— 走共享件 ``four_table/report_line_accounts.py``，
      且已实现名称过滤、双态标注（``provision_resolved_from`` / ``provision_exact``）、
      fail-open 与零回归守卫。K1/K2/F1 是同一共享件的其它消费者。
   2. **D 类科目码在项目间基本一致** —— ``1121`` / ``1122`` / ``2203`` / ``6001``
      各项目相同 ⇒ 换成按名定位买不到东西；而唯一码不一致的 D7（client ``2204``
      vs standard ``2205``）靠 ``account_mapping`` 反解已足够（反解行已存在）。
   3. **机械换解析器有已实证风险** —— F3/F4 曾因「下游读 ``accounts.gross`` 而新类型
      没有该字段」被弄坏，且 962 例测试全绿一个没抓到。

   本文件保留的价值：① 它是 D 类科目语义的**声明式文档**（含逐项 DB 实证注释）
   ② :attr:`SemanticAccountSlot.subject_keywords` 由本文件首次引入，现已被
   ``d_account_resolver`` 的 ``D_SUBJECT_KEYWORDS`` 实际使用
   ③ 将来若 D 类科目码开始跨项目分叉，可直接启用。

   守卫 ``test_d_provision_filter.TestSemanticSpecNotWired`` 会断言本段说明存在，
   并断言全库无生产消费方 —— 哪天真接线了它会打红，提醒同步更新本段。

科目映射真源 = `report_config` DB 实证（`d-cycle-extraction-chain-completion` spec）：
  D1 `BS-005` = `TB('1121','期末余额') − TB('1231-01','期末余额')`（应收票据）
  D2 `BS-006` = `TB('1122','期末余额') − TB('1231-02','期末余额')`（应收账款）
  D3 `BS-046` = `TB('2203','期末余额')`（预收款项 / 合同负债旧科目）
  D4 营业收入（IS 行，损益类）
  D5 `BS-007` = `TB('1124','期末余额')`（应收款项融资）—— 🔴 1124 在活体科目表不存在
  D6 `BS-011` = `TB('1141','期末余额')`（合同资产）
  D7 `BS-047` = `TB('2205','期末余额')`（合同负债）

🔴 D3/D7 为负债类（`is_liability=True`）—— 2203 预收款项 / 2205 合同负债方向均为贷方。

spec: .kiro/specs/semantic-account-resolver-full-rollout/

.. note::
   **兜底码已逐项 DB 实证**（2026-08-03，双向对账 `account_chart`：① 该码实际叫什么名
   ② 该名实际挂在哪个码）。曾修正的错码见各槽行内注释。

.. warning::
   🔴 **`account_chart` 并存两套编码体系** —— 同一码在 ``source='client'`` 与
   ``source='standard'`` 下可能是**完全不同的科目**（实证 10 个项目）::

       码     client 表（8 项目）    standard 表（5 项目）
       4001   实收资本               生产成本
       4101   盈余公积               制造费用
       4401   其他权益工具           工程施工
       4301   专项储备               研发支出

   故 :func:`resolve_semantic_accounts` 的「**client chart 优先**按名定位」不是优化
   而是**正确性前提**：硬编码码值 + 走 standard 表会在那 5 个项目取到成本类科目。
   同族已知现象见 memory「存货科目编码语义在项目间冲突」。

   另：本文件的兜底码只在「按名定位失败」时生效，且要求该码**在本项目科目表里确实存在**
   （见 `semantic_account_resolver` 定位链路第 ④ 层），故一码两义不会因兜底而取错。
"""
from __future__ import annotations

from .semantic_account_resolver import SemanticAccountSlot, SemanticAccountSpec

_PROVISION_WORDS = ("减值准备", "坏账准备", "跌价准备", "累计折旧", "累计摊销", "减值损失")


def _gross(key, names, fallback, label, extra_excludes=()):
    return SemanticAccountSlot(
        key=key, names=names, exclude_names=_PROVISION_WORDS + extra_excludes,
        fallback_standard_codes=fallback, label=label,
    )


def _provision(key, names, fallback, label, subject_keywords, row_code=None):
    """备抵槽。

    🔴 ``names`` 必须是**带主体前缀的全名**且覆盖横杠与下划线两种写法，
    禁裸「坏账准备」——  ``1231 坏账准备`` 本身就是**一级科目**，
    而 :func:`resolve_semantic_accounts` 只在一级科目层做名称匹配 ⇒
    裸通名会让 D1 与 D2 双双命中整个 ``1231``。

    真实库实证（2026-08-05）该错误的代价：``1231`` 全库期末合计
    190,479,717.05，其中 ``1231.02``（应收账款）占 186,648,869.59、
    ``1231.03``（其他应收款）占 3,811,793.41，而 ``1231.01``
    （应收票据坏账）**实际是 0.00** ⇒ D1 会把应收账款的坏账当成
    自己的备抵，与 K1 那次「虚增 31.6 倍」完全同源。

    ``subject_keywords`` 见 :class:`SemanticAccountSlot` 的字段说明
    （拦 ``account_mapping`` 的 ``1231.05 → 1231-02`` 错映射）。

    Args:
        row_code: 该备抵**自己那条报表行**（``IMP-*``），仅用于冲突检测的对照基准、
            **不参与定位**。不声明会让备抵槽拿 spec 级主行（只含原值码）比对而恒报
            假冲突（G7 曾实测 7/8 个项目恒亮）。

            🔴 **本文件当前不接线**（见模块 warning）⇒ 这里声明的 ``row_code``
            此刻**没有生产消费方**，不能说它「消除了线上假告警」；它修好的是
            **声明式文档的正确性**，并让 `test_semantic_slot_row_code` 的待办登记表
            能如实移出该条。将来 D 类真接线时即刻生效，不必回头补。
    """
    return SemanticAccountSlot(
        key=key, names=names, exclude_names=("减值损失",),
        fallback_standard_codes=fallback, label=label, is_provision=True,
        subject_keywords=subject_keywords, row_code=row_code,
    )


# ─────────────────────────────────── D1~D7 ───────────────────────────────────

D1_SPEC = SemanticAccountSpec(
    row_code="BS-005",
    slots=(
        _gross("gross", ("应收票据",), ("1121",), "应收票据"),
        _provision(
            "provision",
            # standard 表用横杠（10 项目）、client 表用下划线（4 项目），两者都要认
            ("坏账准备-应收票据", "坏账准备_应收票据"),
            ("1231-01",),
            "坏账准备-应收票据",
            ("应收票据", "票据"),
        ),
    ),
)

D2_SPEC = SemanticAccountSpec(
    row_code="BS-006",
    slots=(
        _gross("gross", ("应收账款",), ("1122",), "应收账款"),
        _provision(
            "provision",
            ("坏账准备-应收账款", "坏账准备_应收账款"),
            ("1231-02",),
            "坏账准备-应收账款",
            # 🔴 关键词只能是「应收账款」，**不能**写成「应收」——
            # 错映射进来的那条名叫「坏账准备_长期应收款」，它含「应收」
            # 但不含「应收账款」，正是靠这个差别拦住的。
            ("应收账款",),
        ),
    ),
)

D3_SPEC = SemanticAccountSpec(
    row_code="BS-046",
    slots=(_gross("gross", ("预收账款", "预收款项"), ("2203",), "预收账款"),),
)

D4_SPEC = SemanticAccountSpec(
    row_code="IS-001",
    slots=(_gross("gross", ("营业收入", "主营业务收入"), ("6001",), "营业收入"),),
)

D5_SPEC = SemanticAccountSpec(
    row_code="BS-007",
    slots=(
        # 🔴 **码与名双向零命中**（2026-08-05 真实库双向对账，10 个项目）：
        #    ① 码：`1124` 在 `account_chart` 两个 source 下均不存在
        #    ② 名：「应收款项融资」在 `account_chart` 两个 source 下均不存在
        #    ③ `account_mapping` 无 `1124` 的反解行；`tb_balance` 无 `1124%` 数据行
        #    ⇒ 这**不是错码**（`1124` 在 CAS 里确实是应收款项融资，财会[2019]6 号新增），
        #      而是**业务事实** —— 这批项目没有应收款项融资业务。
        #      故 fallback=() 宁缺勿造，本槽应恒返 found=False / amount=None，
        #      由前端呈现「本项目无此科目」而非 0。
        #    注：`report_config` 的 `BS-007` 四准则均写 `TB('1124')`，属同一业务事实，
        #      不在本 spec 修正范围（该表缺陷归 report-config-account-code-integrity）。
        SemanticAccountSlot(
            key="gross", names=("应收款项融资",),
            exclude_names=_PROVISION_WORDS,
            fallback_standard_codes=(), label="应收款项融资",
        ),
    ),
)

D6_SPEC = SemanticAccountSpec(
    row_code="BS-011",
    slots=(
        _gross("gross", ("合同资产",), ("1141",), "合同资产"),
        _provision(
            "provision",
            ("合同资产减值准备", "坏账准备-合同资产", "坏账准备_合同资产"),
            # 两个候选兜底码：`1142 合同资产减值准备`（standard 6 项目）与
            # `1231-05 坏账准备-合同资产`（standard 10 项目）。两者都在活体
            # 科目表里有定义，但 `tb_balance` 中**均无数据行** ⇒ 本槽在全库
            # 任何项目都应返 found=False / amount=None（恒空是数据事实）。
            # 不依赖 `IMP-004 三、合同资产减值准备` —— 该报表行 formula 四准则全 NULL。
            ("1142", "1231-05"),
            "合同资产减值准备",
            ("合同资产",),
            # 🔴 槽级 row_code：spec 级 `BS-011 = TB('1141')` 只含原值 ⇒ 备抵槽拿它
            # 比对必然无交集。`IMP-004 三、合同资产减值准备` 两变体公式**实测均为 NULL**
            # （2026-08-12 postgres 只读复核）⇒ 声明后 basis 为空、走三态跳过。
            #
            # 🔴 但请注意：**本文件当前不接线**（见模块 warning，D 类 7 个 render 走
            # `report_line_accounts` 路径）⇒ 此声明**此刻没有生产消费方**，
            # 不能说它消除了线上假告警。它修好的是声明式文档的正确性 +
            # 让待办登记表如实移出该条；D 类真接线时即刻生效。
            #
            # 与上面「不依赖 IMP-004」那句注释不矛盾：**定位**（兜底码）确实不依赖它，
            # 这里只把它用作**冲突检测的对照基准**（`row_code` 的语义就是「仅用于冲突
            # 检测，不参与定位」）。
            row_code="IMP-004",
        ),
    ),
)

D7_SPEC = SemanticAccountSpec(
    row_code="BS-047",
    slots=(_gross("gross", ("合同负债",), ("2205",), "合同负债"),),
)


D_CYCLE_SPECS: dict[str, SemanticAccountSpec] = {
    "D1": D1_SPEC,
    "D2": D2_SPEC,
    "D3": D3_SPEC,
    "D4": D4_SPEC,
    "D5": D5_SPEC,
    "D6": D6_SPEC,
    "D7": D7_SPEC,
}

#: 损益类 D 循环
D_PL_CYCLES = frozenset({"D4"})

D_PL_POSITIVE_SIDE: dict[str, str] = {
    "D4": "credit",  # 收入类贷方正方向
}


def spec_of(wp_code: str) -> SemanticAccountSpec | None:
    return D_CYCLE_SPECS.get(str(wp_code or "").strip().upper())


__all__ = [
    "D1_SPEC", "D2_SPEC", "D3_SPEC", "D4_SPEC", "D5_SPEC", "D6_SPEC", "D7_SPEC",
    "D_CYCLE_SPECS", "D_PL_CYCLES", "D_PL_POSITIVE_SIDE", "spec_of",
]
