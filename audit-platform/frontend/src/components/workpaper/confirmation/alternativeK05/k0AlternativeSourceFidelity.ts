/**
 * k0AlternativeSourceFidelity — K0-5 / K0-6 替代程序检查表的源模板字面真源
 *
 * spec: k0-confirmation-source-alignment，Task 13（Requirements 7.1 ~ 7.5）
 *
 * 源：`backend/wp_templates/K/K0 管理循环函证.xlsx` 的
 *     `其他应收款替代程序K0-5` / `其他应付款替代程序K0-6` 两张 sheet。
 * 后端 `backend/tests/test_k0_source_template_facts.py` 以 openpyxl 直读同一份 xlsx
 * 做裁决（`ALT_BLOCK1_EVIDENCE` / `ALT_RED_HINT` / `ALT_PREPARATION_ITEMS`），
 * 本文件与它双向锁死（守卫 `__tests__/k0AlternativeBlocks.spec.ts`）。
 *
 * ─── 三条落手前必读的判断 ────────────────────────────────────────────────────
 *
 * **① 段②/③/④ 的「具体化证据列」不是缺陷，勿按段① 的样子重构它们。**
 * 源模板 `O15`/`O26`/`O38` 三处红字逐字写着「检查的关键证据和要素根据被审计单位具体情况
 * 修改」—— 这是模板作者对**具体化**的明确授权。平台把段② 具体化成「审批单 / 借据协议」、
 * 段③ 具体化成「原始单据 / 审批」正是照此办理；R7.3 要求做的是把这条红字**展示出来**，
 * 让那些列的源模板依据对用户可见，而不是把它们改回泛化的「支持性文件1/2」。
 *
 * **② 两侧段① 的对方当事人用词必须不同，统一即业务方向搞反。**
 * K0-5 是其他应收款 → 期后**收回**款项 → 银行回单上的对方是**付款方**（源 `G16`）；
 * K0-6 是其他应付款 → 期后**付出**款项 → 银行回单上的对方是**收款方**（源 `I16`）。
 * 守卫对此有反向自检（统一成同一个词即打红）。
 *
 * **③ 源模板 `K0-5!M46 = SUM(M40:M45)` 是对「索引号」文本列求和 = 笔误，不实现。**
 * 登记在 `K0_ALT_SOURCE_TYPOS`，供守卫断言「平台段③ 的索引号列不得带 `sumField`」。
 */

/** 段① 一个证据分组（`group` 对应源模板合并段头，`leaves` 对应其下叶子列） */
export interface K0AltEvidenceGroup {
  /** 源模板段头锚点（如 `F15`） */
  anchor: string
  /** 段头文字（逐字） */
  group: string
  /** 叶子列：[锚点, 逐字 label] */
  leaves: readonly (readonly [string, string])[]
}

/** K0-5 段①「1、期后收款检查」的源模板证据结构（源 `A15:K16`） */
export const K05_BLOCK1_SOURCE: readonly K0AltEvidenceGroup[] = Object.freeze([
  Object.freeze({
    anchor: 'A15',
    group: '记账凭证',
    leaves: Object.freeze([]) as readonly (readonly [string, string])[],
  }),
  Object.freeze({
    anchor: 'F15',
    group: '银行回单',
    leaves: Object.freeze([
      Object.freeze(['F16', '日期'] as const),
      // 🔴 其他应收款是「收回」→ 对方是付款方。与 K0-6 的「收款方」必须不同。
      Object.freeze(['G16', '付款方'] as const),
      Object.freeze(['H16', '金额'] as const),
    ]),
  }),
  Object.freeze({
    anchor: 'I15',
    group: '支持性文件1',
    leaves: Object.freeze([
      Object.freeze(['I16', '识别特征'] as const),
      Object.freeze(['J16', '信息1'] as const),
      Object.freeze(['K16', '信息2'] as const),
    ]),
  }),
]) as readonly K0AltEvidenceGroup[]

/** K0-6 段①「①期后付款检查」的源模板证据结构（源 `A15:J16`） */
export const K06_BLOCK1_SOURCE: readonly K0AltEvidenceGroup[] = Object.freeze([
  Object.freeze({
    anchor: 'A15',
    group: '记账凭证',
    leaves: Object.freeze([]) as readonly (readonly [string, string])[],
  }),
  Object.freeze({
    anchor: 'F15',
    group: '付款审批单',
    leaves: Object.freeze([
      Object.freeze(['F16', '日期/编号'] as const),
      Object.freeze(['G16', '是否经过恰当审批'] as const),
    ]),
  }),
  Object.freeze({
    anchor: 'H15',
    group: '银行回单',
    leaves: Object.freeze([
      Object.freeze(['H16', '日期'] as const),
      // 🔴 其他应付款是「付出」→ 对方是收款方。与 K0-5 的「付款方」必须不同。
      Object.freeze(['I16', '收款方'] as const),
      Object.freeze(['J16', '金额'] as const),
    ]),
  }),
]) as readonly K0AltEvidenceGroup[]

/** 两侧段① 的对方当事人（守卫的反向自检对象） */
export const K0_ALT_COUNTERPARTY = Object.freeze({
  'K0-5': Object.freeze({ anchor: 'G16', label: '付款方' }),
  'K0-6': Object.freeze({ anchor: 'I16', label: '收款方' }),
})

// ─── 源模板红字（方法论上下文，R7.3） ────────────────────────────────────────

/** 红字原文（两表逐字相同） */
export const K0_ALT_RED_HINT = '检查的关键证据和要素根据被审计单位具体情况修改'

/**
 * 红字所在区块（源 `O15`/`O26`/`O38` 三处；**`O48` 没有**，勿凭空补第 4 处）。
 *
 * 键 = 平台区块 key，值 = 源模板锚点。段④（block4）是源外增强区块
 * （已在 `SOURCE_EXTRA_MANIFEST` 登记），源模板无红字 ⇒ 不在此表。
 */
export const K0_ALT_RED_HINT_BLOCKS: Readonly<Record<string, string>> = Object.freeze({
  block1: 'O15',
  block2: 'O26',
  block3: 'O38',
})

// ─── 编制说明 3 条替代程序要点（源 `B68:B70`，两表逐字相同，R7.4） ──────────

export interface K0AltPreparationItem {
  anchor: string
  text: string
}

export const K0_ALT_PREPARATION_ITEMS: readonly K0AltPreparationItem[] = Object.freeze([
  Object.freeze({ anchor: 'B68', text: '①检查本期付款、期后收货或回收；' }),
  Object.freeze({
    anchor: 'B69',
    text: '②检查原始凭证：合同、订货单、发票或收据、银行回单、支票存根等；',
  }),
  Object.freeze({ anchor: 'B70', text: '③对回函可能性不高的、余额重大的，发函同时执行替代程序。' }),
]) as readonly K0AltPreparationItem[]

// ─── 源模板笔误登记（不实现，R7.5） ─────────────────────────────────────────

export interface K0AltSourceTypo {
  sourceRef: string
  literal: string
  note: string
}

export const K0_ALT_SOURCE_TYPOS: readonly K0AltSourceTypo[] = Object.freeze([
  Object.freeze({
    sourceRef: '其他应收款替代程序K0-5!M46',
    literal: '=SUM(M40:M45)',
    note: '源模板笔误：M 列是「索引号」文本列，对其求和无意义 ⇒ 平台不实现该合计，索引号列不得带 sumField',
  }),
]) as readonly K0AltSourceTypo[]
