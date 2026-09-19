/**
 * confirmationDicts.ts — 函证模块统一枚举字典 key 注册表
 *
 * 归集 D0-1 ~ D0-8 全部 11 类枚举 key，去重统一。
 * 后端 system_dicts.py 中 confirmation_dicts 命名空间一一对应。
 * 前端通过 GET /dicts 拉取后按此 key 取值。
 *
 * Sprint 1 Task 1.1: 统一 confirmation_dicts 命名空间
 */

// ─── 统一字典 key 常量（11 类） ──────────────────────────────────────────────

export const CONFIRMATION_DICTS = {
  /** 1. 科目大类（应收账款/合同负债/其他应收款/预付账款/应付账款/其他应付款/短期借款/长期借款/银行存款/定期存款/理财产品/其他货币资金/其他） */
  ACCOUNT_TYPE: 'confirmation_account_type',

  /** 2. 函证方式（积极式/消极式） */
  METHOD: 'confirmation_method',

  /** 3. 回函方式（原件寄回/传真/电子邮件/当面确认） */
  REPLY_METHOD: 'confirmation_reply_method',

  /** 4. 发函结果（送抵/退回/无法送达） */
  SEND_RESULT: 'confirmation_send_result',

  /** 5. 跟函场景（现场确认/留函后收回/电话核实） */
  FOLLOWUP_SCENARIO: 'confirmation_followup_scenario',

  /** 6. 差异类型（时间性差异/记账差异/未达账项/其他） */
  DIFF_TYPE: 'confirmation_diff_type',

  /** 7. 抽样方式（统计抽样/非统计抽样/全部发函/其他） */
  SAMPLING_METHOD: 'sampling_method',

  /** 8. 回函可靠性结论（可靠/部分可靠/不可靠） */
  REPLY_RELIABILITY: 'confirmation_reply_reliability',

  /** 9. 函证状态（12 态状态机） */
  STATUS: 'confirmation_status',

  /** 10. 是/否 */
  YES_NO: 'yes_no',

  /** 11. 是/否/不适用 */
  YES_NO_NA: 'yes_no_na',

  /** 12. 相符情况（相符/不符/未回函） */
  MATCH_STATUS: 'confirmation_match',

  // ─── 源模板 DV 驱动的三个枚举（h0-confirmation-source-fidelity-and-linkage R7） ───
  // 🔴 六枢纽（D0/F0/G0/H0/K0/L0）的 X0-2!C7 / X0-2!L7 / X0-1!C8 数据验证取值
  //    实测**完全同构** → 声明为七枢纽共享枚举而非 H0 专属。

  /**
   * 13. 发函渠道（邮寄/跟函/电子函证/其他）—— 源模板 `X0-2!C7`
   *
   * 🔴 与 `METHOD`（积极式/消极式）是**两个不同维度**：
   * 前者是发函渠道（源模板「函证方式」列的实际取值），后者是准则 1312 的程序层面概念
   * （X0A 程序 1「以积极方式…进行函证」）。X0-1 的「函证方式」列由 VLOOKUP 自
   * `X0-2!C` 列带入 → 两处必须绑定本 key，绑到 `METHOD` 会拿到错误维度的取值。
   */
  SEND_CHANNEL: 'confirmation_send_channel',

  /** 14. 选取样本目的（A. 大额/B.异常/C.余额为0/D.账龄长/E.随机）—— 源模板 `X0-1!C8` */
  SAMPLE_PURPOSE: 'confirmation_sample_purpose',

  /** 15. 地址不一致的核实方式（6 项）—— 源模板 `X0-2!L7` */
  ADDR_VERIFY: 'confirmation_addr_verify',

  /** 16. 差异调节表科目（X0-4「账户/交易」列） */
  SUBJECT: 'confirmation_subject',
} as const

export type ConfirmationDictKey = typeof CONFIRMATION_DICTS[keyof typeof CONFIRMATION_DICTS]

// ─── 按组件使用频次映射（方便各 D0 组件引用） ────────────────────────────────

/** D0-1 函证汇总表使用的字典 */
export const D01_DICT_KEYS = [
  CONFIRMATION_DICTS.ACCOUNT_TYPE,
  CONFIRMATION_DICTS.METHOD,
  CONFIRMATION_DICTS.REPLY_METHOD,
  CONFIRMATION_DICTS.SAMPLING_METHOD,
  CONFIRMATION_DICTS.STATUS,
  CONFIRMATION_DICTS.YES_NO,
] as const

/** D0-2 核实被函证单位使用的字典 */
export const D02_DICT_KEYS = [
  CONFIRMATION_DICTS.ACCOUNT_TYPE,
  CONFIRMATION_DICTS.SEND_RESULT,
  CONFIRMATION_DICTS.YES_NO,
  CONFIRMATION_DICTS.YES_NO_NA,
] as const

/** D0-3 跟函过程控制使用的字典 */
export const D03_DICT_KEYS = [
  CONFIRMATION_DICTS.FOLLOWUP_SCENARIO,
  CONFIRMATION_DICTS.YES_NO,
] as const

/** D0-4 差异调节表使用的字典 */
export const D04_DICT_KEYS = [
  CONFIRMATION_DICTS.ACCOUNT_TYPE,
  CONFIRMATION_DICTS.DIFF_TYPE,
  CONFIRMATION_DICTS.YES_NO,
] as const

/** D0-4b 差异检查表使用的字典 */
export const D04B_DICT_KEYS = [
  CONFIRMATION_DICTS.ACCOUNT_TYPE,
] as const

/** D0-5/D0-6 替代程序使用的字典 */
export const D05_D06_DICT_KEYS = [
  CONFIRMATION_DICTS.ACCOUNT_TYPE,
  CONFIRMATION_DICTS.SAMPLING_METHOD,
  CONFIRMATION_DICTS.YES_NO,
] as const

/** D0-7 回函可靠性验证使用的字典 */
export const D07_DICT_KEYS = [
  CONFIRMATION_DICTS.REPLY_METHOD,
  CONFIRMATION_DICTS.REPLY_RELIABILITY,
  CONFIRMATION_DICTS.YES_NO,
] as const

/** D0-8 舞弊风险评价使用的字典 */
export const D08_DICT_KEYS = [
  CONFIRMATION_DICTS.YES_NO_NA,
  CONFIRMATION_DICTS.STATUS,
] as const

/** H0-1 函证结果汇总表使用的字典（H 循环品种 + 渠道 + 选样目的） */
export const H01_DICT_KEYS = [
  CONFIRMATION_DICTS.ACCOUNT_TYPE,
  CONFIRMATION_DICTS.SEND_CHANNEL,
  CONFIRMATION_DICTS.SAMPLE_PURPOSE,
  CONFIRMATION_DICTS.REPLY_METHOD,
  CONFIRMATION_DICTS.MATCH_STATUS,
  CONFIRMATION_DICTS.YES_NO,
] as const

/** H0-2 核实被函证单位信息使用的字典 */
export const H02_DICT_KEYS = [
  CONFIRMATION_DICTS.SEND_CHANNEL,
  CONFIRMATION_DICTS.ADDR_VERIFY,
  CONFIRMATION_DICTS.REPLY_METHOD,
  CONFIRMATION_DICTS.SEND_RESULT,
  CONFIRMATION_DICTS.YES_NO,
] as const

// ─── 辅助：全量字典 key 数组（批量拉取用） ──────────────────────────────────

export const ALL_CONFIRMATION_DICT_KEYS = Object.values(CONFIRMATION_DICTS)

// ─── 组件内置回退（**唯一真源**，禁止各组件再写一份字面量数组） ──────────────

/**
 * `CONFIRMATION_DICT_FALLBACK` — 后端 `/dicts` 不可用时的回退取值。
 *
 * 🔴 为什么需要它作单一真源：改造前 `GtConfirmationSummary.vue` 与
 * `GtConfirmationDiffReconcile.vue` **各写一份**内置字面量数组，且**都与后端不一致**：
 * - Summary 的 `confirmation_account_type` 只有 7 项（后端 22 项）→ H 循环品种
 *   （固定资产/工程物资/使用权资产/租赁负债…）一个都选不出来 → H0-1 下区矩阵按品种
 *   SUMIF 恒空；
 * - Summary 的 `confirmation_reply_method` 写的是「邮寄/传真/电子邮件/第三方平台/当面递交」，
 *   后端是「原件寄回/传真/电子邮件/当面确认」+ 源模板三项，两侧标签集合几乎不重叠；
 * - DiffReconcile 的 `subjectOptions` 13 项同样无一个 H 类科目。
 *
 * 现在：**权威部分逐字镜像后端 `system_dicts`**，前端历史遗留取值另行登记
 * （见 `FRONTEND_LEGACY_DICT_EXTRAS`，保留是为了让既有持久化值仍可渲染/可选）。
 * 守卫 `h0DictConsumption.spec.ts` 三方交叉锁死：后端字典 ↔ 本常量 ↔ 矩阵默认品种。
 *
 * spec: h0-confirmation-source-fidelity-and-linkage R1.3 / Property 1, 30
 */
export const CONFIRMATION_DICT_FALLBACK: Readonly<Record<string, readonly string[]>> = Object.freeze({
  [CONFIRMATION_DICTS.ACCOUNT_TYPE]: Object.freeze([
    // 后端 confirmation_account_type 逐字（22 项，「其他」兜底在末位）
    '应收账款', '合同负债', '其他应收款', '预付账款', '应付账款', '其他应付款',
    '短期借款', '长期借款', '银行存款', '定期存款', '理财产品', '其他货币资金',
    // H 循环 9 品种（wp_system_map.json 固定资产循环 accounts 逐字，排除损益类「资产处置损益」）
    '固定资产', '在建工程', '投资性房地产', '工程物资', '油气资产',
    '固定资产清理', '生产性生物资产', '使用权资产', '租赁负债',
    '其他',
  ]),
  [CONFIRMATION_DICTS.SUBJECT]: Object.freeze([
    '应收账款', '合同负债', '销售收入', '应收票据', '合同资产', '预付账款',
    '应付账款', '预收账款', '其他应收款', '其他应付款', '银行存款',
    '短期借款', '长期借款',
    '固定资产', '在建工程', '投资性房地产', '工程物资', '油气资产',
    '固定资产清理', '生产性生物资产', '使用权资产', '租赁负债',
  ]),
  [CONFIRMATION_DICTS.METHOD]: Object.freeze(['积极式', '消极式']),
  [CONFIRMATION_DICTS.SEND_CHANNEL]: Object.freeze(['邮寄', '跟函', '电子函证', '其他']),
  // 🔴 空格/标点不一致是源模板 X0-1!C8 的原文，不得「顺手统一」
  [CONFIRMATION_DICTS.SAMPLE_PURPOSE]: Object.freeze(['A. 大额', 'B.异常', 'C.余额为0', 'D.账龄长', 'E.随机']),
  [CONFIRMATION_DICTS.ADDR_VERIFY]: Object.freeze([
    '发票/合同地址核实', '电话核实', '官网/公告查询', '地图查询', '邮件确认', '其他方式',
  ]),
  [CONFIRMATION_DICTS.REPLY_METHOD]: Object.freeze([
    '原件寄回', '传真', '电子邮件', '当面确认',
    // 源模板 X0-2!P7 取值
    '纸质原件', '电子函证', '其他介质',
    // 前端历史遗留（见 FRONTEND_LEGACY_DICT_EXTRAS）
    '邮寄', '第三方平台', '当面递交',
  ]),
  [CONFIRMATION_DICTS.MATCH_STATUS]: Object.freeze([
    '相符', '不符', '未回函',
    // 前端历史遗留
    '部分相符',
  ]),
  [CONFIRMATION_DICTS.YES_NO]: Object.freeze(['是', '否']),
  [CONFIRMATION_DICTS.YES_NO_NA]: Object.freeze(['是', '否', '不适用']),
  [CONFIRMATION_DICTS.SEND_RESULT]: Object.freeze(['送抵', '退回']),
  [CONFIRMATION_DICTS.SAMPLING_METHOD]: Object.freeze(['统计抽样', '非统计抽样', '全部发函', '其他']),
})

/**
 * 前端历史遗留取值登记（后端 `system_dicts` 无、但既有项目可能已持久化）。
 *
 * 保留理由：删掉会让历史行的该字段值落在选项集之外，`el-select` 显示为空。
 * 守卫据此放行「fallback ⊋ 后端标签集合」，但要求每条 extra 有登记理由。
 */
export const FRONTEND_LEGACY_DICT_EXTRAS: ReadonlyArray<{ dictKey: string; label: string; reason: string }> = [
  { dictKey: CONFIRMATION_DICTS.REPLY_METHOD, label: '邮寄', reason: '前端早期取值，后端对应「原件寄回」；历史行可能已持久化' },
  { dictKey: CONFIRMATION_DICTS.REPLY_METHOD, label: '第三方平台', reason: '前端早期取值，后端对应「电子函证」；历史行可能已持久化' },
  { dictKey: CONFIRMATION_DICTS.REPLY_METHOD, label: '当面递交', reason: '前端早期取值，后端对应「当面确认」；历史行可能已持久化' },
  { dictKey: CONFIRMATION_DICTS.MATCH_STATUS, label: '部分相符', reason: '前端早期取值，后端 confirmation_match 只有相符/不符/未回函；历史行可能已持久化' },
]

/** 取某字典的回退选项（未登记的 key 返回空数组，调用方据此显示「不可用」而非崩溃） */
export function fallbackOptions(dictKey: string): readonly string[] {
  return CONFIRMATION_DICT_FALLBACK[dictKey] ?? []
}

/** 取某字典的回退选项并转成 `{value,label}` 形态（`el-select` 直接消费） */
export function fallbackSelectOptions(dictKey: string): Array<{ value: string; label: string }> {
  return fallbackOptions(dictKey).map((label) => ({ value: label, label }))
}

// ─── 向后兼容别名（原 confirmationEnums.ts 导出） ─────────────────────────────

/** @deprecated 使用 CONFIRMATION_DICTS 代替 */
export const CONFIRMATION_DICT_KEYS = CONFIRMATION_DICTS
