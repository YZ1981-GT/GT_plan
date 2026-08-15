/**
 * I 类六循环（I1~I6）科目口径 —— **单一真源**（零 Vue 依赖纯函数）。
 *
 * 后端真源 = `app/services/four_table/i_cycle_accounts.py`
 * （`I_CYCLE_ROW_CODES` / `I_CYCLE_SEGMENTS` 声明式规格）
 * → `resolve_i_cycle_accounts()` → `ICycleAccounts.as_dict()`
 * → `i_cycle_extraction.source_codes_payload()`
 * → render 下发 `html_data.tb_source_codes`。
 *
 * ## 为什么不复用 `shared/cycleAccountScope.ts` 工厂
 *
 * 那个工厂读的是 `semantic_account_resolver` 的 **`slots`** 形态
 * （`slots[key].standard_codes` / `.codes` / `.found`），G/K 类在用。
 * I 类六循环走的是 **`segments`** 形态（`segments[].standard` / `.original`），
 * 字段名与结构都不同 —— 二分 `gross`/`provision` 装不下 I1 的三段
 * （`1702 累计摊销` 名称不含「减值准备」，`split_gross_provision` 会判成 gross
 * → 原值口径变净额）。硬套工厂会读到 `undefined` 而静默退化到兜底码。
 *
 * 故本模块自建段化视图，但**同样只写声明、不写逻辑**：循环差异全部由
 * :data:`I_CYCLE_ACCOUNT_SPECS` 表达，六个循环共用同一套取值函数。
 *
 * ## 🔴 运行态口径优先级：render 下发值 > 兜底常量
 *
 * 兜底常量只在「render 未下发（灰度开关关闭 / 后端未重启 / 取数异常）」时兜住界面，
 * **不是**权威真源 —— 标准码在项目间并不一致（`account_mapping` 同一原始码在不同
 * 项目映射到不同标准码；`account_chart` 本身各项目也不同），权威口径只能来自
 * 后端逐项目解析结果。
 *
 * ## 🔴 「本项目无此科目」与「取数为 0」必须区分
 *
 * - `I3.impairment`（商誉减值准备）与 `I5.cost`（其他非流动资产）在
 *   `account_chart` 实证**不存在标准科目** ⇒ 后端段兜底为空 tuple（宁缺勿造）。
 * - 此时 :func:`iCycleQueryCodes` 返回**空数组**（绝不凭空造前缀），
 *   :func:`iCycleAccountAbsent` 返回 `true`，界面须提示「本项目无此科目」而非显示 0。
 * - render **未下发** ≠ 无此科目 ⇒ 此时 :func:`iCycleAccountAbsent` 返回 `false`（未知）。
 *
 * spec: .kiro/specs/i-cycle-extraction-formula-and-disclosure-closure/ Task 16
 *       Requirements 9.1 / 2.3
 */
import type { TbSegmentAccounts, TbSourceCodes } from './shared/tbSourceCodes'

// ─────────────────────────────────────────────────────────────────────────────
// 段键（逐字对齐后端 `i_cycle_accounts.SEGMENT_*`）
// ─────────────────────────────────────────────────────────────────────────────

/** 原值段（账面原值 / 开发支出 / 商誉账面原值 / 长期待摊费用 / 其他非流动资产） */
export const I_SEGMENT_COST = 'cost'
/** 累计摊销段（仅 I1） */
export const I_SEGMENT_AMORTIZATION = 'amortization'
/** 减值准备段（I1 / I3） */
export const I_SEGMENT_IMPAIRMENT = 'impairment'
/** 费用段（仅 I6，损益类取本期发生额） */
export const I_SEGMENT_EXPENSE = 'expense'

export type ICycleWpCode = 'I1' | 'I2' | 'I3' | 'I4' | 'I5' | 'I6'

/** 某段的声明（纯数据；与后端 `ISegmentSpec` 的前端可见子集对齐） */
export interface ICycleSegmentSpec {
  /** 段键，须与后端 `SEGMENT_*` 逐字一致 */
  segment: string
  /** 中文段名，逐字取自源模板层标题（后端 `ISegmentSpec.label`） */
  label: string
  /**
   * 兜底**标准码**集。仅在 render 未下发时用。
   *
   * 🔴 空数组 = 实证不存在该标准科目（`account_chart` 无此码）——
   * **绝不能**随便填一个码：填了会在「render 未下发」路径下产出一个查不到任何
   * 数据的假前缀，把「本项目无此科目」掩盖成 0。
   */
  fallback: readonly string[]
  /** 备抵段（累计摊销 / 减值准备）：对聚合结果取绝对值 */
  isProvision?: boolean
  /** 损益段：取本期发生额（走 `trial_balance`，不用余额表 debit−credit） */
  isOccurrence?: boolean
}

/** 某循环的科目定位声明 */
export interface ICycleAccountSpec {
  wpCode: ICycleWpCode
  /** 科目中文名（AI 上下文 / UI 文案统一取此常量） */
  accountName: string
  /**
   * 报表行编码。
   *
   * 🔴 I 类**四准则同码同名同公式** ⇒ listed / soe 取值相同。这不是平台通例
   * （J1 listed `BS-051` / soe `BS-069` 就不同），保留两键以表达该维度。
   */
  rowCode: { readonly listed: string; readonly soe: string }
  /** 段声明；**顺序 = 审定表 / 披露表展示顺序**，`segments[0]` 为主段 */
  segments: readonly ICycleSegmentSpec[]
}

// ─────────────────────────────────────────────────────────────────────────────
// 声明（唯一真源；守卫 `iCycleAccountScope.spec.ts` 与后端逐项交叉锁死）
// ─────────────────────────────────────────────────────────────────────────────

/**
 * 六循环科目定位声明。
 *
 * 🔴 **行编码取值 = 后端 `I_CYCLE_ROW_CODES` 逐行对账实证值（2026-08-09 修正后）**。
 * 改造前六个 `i{n}AccountScope.ts` 里 12 个取值有 11 个错，且是**整体错位**
 * （listed 侧 `BS-033/035/037/038/040` 分别是 I2/I4/I5 的行、非流动资产合计派生行、
 * 「流动负债：」节标题；soe 侧 `BS-045..050` + `IS-024` 全是负债段与派生行）。
 * 后端已按 `report_config` 实证修正，前端这六份**未同步** ⇒ 本表即同步结果。
 */
export const I_CYCLE_ACCOUNT_SPECS: Readonly<Record<ICycleWpCode, ICycleAccountSpec>> = {
  I1: {
    wpCode: 'I1',
    accountName: '无形资产',
    // 无形资产 = TB('1701','期末余额') - TB('1702','期末余额')
    rowCode: { listed: 'BS-032', soe: 'BS-032' },
    segments: [
      { segment: I_SEGMENT_COST, label: '账面原值', fallback: ['1701'] },
      { segment: I_SEGMENT_AMORTIZATION, label: '累计摊销', fallback: ['1702'], isProvision: true },
      { segment: I_SEGMENT_IMPAIRMENT, label: '减值准备', fallback: ['1703'], isProvision: true },
    ],
  },
  I2: {
    wpCode: 'I2',
    accountName: '开发支出',
    // 开发支出 = TB('1704','期末余额')
    rowCode: { listed: 'BS-033', soe: 'BS-033' },
    segments: [
      // 🔴 1704（`account_chart` 实证）；`report_config` 写 1703（无形资产减值准备）有误，
      //    后端不改写报表配置，只在 diagnostics 里报 chart_conflict。
      //    也不是 1717 —— 全库两张科目表都无此码（改造前前端写的就是 1717 → 取数恒空）。
      { segment: I_SEGMENT_COST, label: '开发支出', fallback: ['1704'] },
    ],
  },
  I3: {
    wpCode: 'I3',
    accountName: '商誉',
    // 商誉 = TB('1711','期末余额')
    rowCode: { listed: 'BS-034', soe: 'BS-034' },
    segments: [
      { segment: I_SEGMENT_COST, label: '商誉账面原值', fallback: ['1711'] },
      // 🔴 `account_chart` **无**「商誉减值准备」科目 → 空兜底（宁缺勿造）
      { segment: I_SEGMENT_IMPAIRMENT, label: '商誉减值准备', fallback: [], isProvision: true },
    ],
  },
  I4: {
    wpCode: 'I4',
    accountName: '长期待摊费用',
    // 长期待摊费用 = TB('1801','期末余额')
    rowCode: { listed: 'BS-035', soe: 'BS-035' },
    segments: [
      { segment: I_SEGMENT_COST, label: '长期待摊费用', fallback: ['1801'] },
    ],
  },
  I5: {
    wpCode: 'I5',
    accountName: '其他非流动资产',
    // 其他非流动资产 = TB('1911','期末余额')；🔴 `1911` 全库两张科目表都不存在
    rowCode: { listed: 'BS-037', soe: 'BS-037' },
    segments: [
      // 🔴 无标准科目且 report_config formula 为 None → 空兜底（宁缺勿造，R1.4）
      { segment: I_SEGMENT_COST, label: '其他非流动资产', fallback: [] },
    ],
  },
  I6: {
    wpCode: 'I6',
    accountName: '研发费用',
    // 研发费用 = TB('6604','本期发生额')（损益类，走 trial_balance 发生额）
    rowCode: { listed: 'IS-006', soe: 'IS-006' },
    segments: [
      // 🔴 6604；改造前前端/后端都写 6602（管理费用，全库借方 6.24 亿）→ 数字完全错
      { segment: I_SEGMENT_EXPENSE, label: '研发费用', fallback: ['6604'], isOccurrence: true },
    ],
  },
} as const

// ─────────────────────────────────────────────────────────────────────────────
// 取值函数（六循环共用；不含任何循环专属分支）
// ─────────────────────────────────────────────────────────────────────────────

function nonEmpty(list: readonly unknown[] | undefined | null): string[] {
  return (list || []).map((c) => String(c ?? '').trim()).filter(Boolean)
}

/** 循环声明；未知 wp_code 返 `undefined`（不抛，调用方按缺省处理） */
export function iCycleSpec(wpCode: string): ICycleAccountSpec | undefined {
  return I_CYCLE_ACCOUNT_SPECS[String(wpCode || '').toUpperCase() as ICycleWpCode]
}

/** 主段键（`segments[0].segment`）；未知循环返空串 */
export function iCyclePrimarySegment(wpCode: string): string {
  return iCycleSpec(wpCode)?.segments[0]?.segment || ''
}

/** 段声明；未指定段键时取主段 */
export function iCycleSegmentSpec(
  wpCode: string,
  segment?: string,
): ICycleSegmentSpec | undefined {
  const spec = iCycleSpec(wpCode)
  if (!spec) return undefined
  const key = segment || spec.segments[0]?.segment
  return spec.segments.find((s) => s.segment === key)
}

/**
 * 报表行编码。
 *
 * @param standards 项目适用准则集（命中任一 `soe*` 用国企编号，否则用上市编号）——
 *   与后端 `resolve_row_code()` 同判据。
 */
export function iCycleRowCode(
  wpCode: string,
  standards?: readonly string[] | null,
): string {
  const spec = iCycleSpec(wpCode)
  if (!spec) return ''
  const isSoe = (standards || []).some((s) => String(s || '').toLowerCase().startsWith('soe'))
  return isSoe ? spec.rowCode.soe || spec.rowCode.listed : spec.rowCode.listed || spec.rowCode.soe
}

/** render 下发的该段结果；未下发或未知段返 `null` */
export function iCycleSegment(
  src: TbSourceCodes | null | undefined,
  wpCode: string,
  segment?: string,
): TbSegmentAccounts | null {
  const key = segment || iCyclePrimarySegment(wpCode)
  if (!key) return null
  const found = (src?.segments || []).find((s) => s && s.segment === key)
  return found || null
}

/**
 * 段的查询口径（**标准码**集，`trial_balance` 用）。
 *
 * 优先 render 下发；未下发时回退段兜底码。
 * 🔴 段兜底码为空（实证不存在该科目）时返回**空数组**，绝不凭空造前缀。
 */
export function iCycleQueryCodes(
  src: TbSourceCodes | null | undefined,
  wpCode: string,
  segment?: string,
): string[] {
  const codes = nonEmpty(iCycleSegment(src, wpCode, segment)?.standard)
  if (codes.length) return codes
  return [...(iCycleSegmentSpec(wpCode, segment)?.fallback || [])]
}

/**
 * 段的**客户原始码**前缀集（`tb_balance` / `tb_aux_balance` 用）。
 *
 * render 下发 `original` 时用它（已经过 `account_mapping` 反解）；缺失时退回标准码集。
 */
export function iCycleOriginalCodes(
  src: TbSourceCodes | null | undefined,
  wpCode: string,
  segment?: string,
): string[] {
  const codes = nonEmpty(iCycleSegment(src, wpCode, segment)?.original)
  return codes.length ? codes : iCycleQueryCodes(src, wpCode, segment)
}

/** 段的首个科目码（回写 TB / EventBus 载荷 / 请求参数用）；无口径返空串 */
export function iCycleAccountCode(
  src: TbSourceCodes | null | undefined,
  wpCode: string,
  segment?: string,
): string {
  return iCycleQueryCodes(src, wpCode, segment)[0] || ''
}

/**
 * 本项目是否**确实没有**该科目 —— 界面据此提示「本项目无此科目」，勿显示 0。
 *
 * 🔴 三态判据：
 * 1. render **未下发**该段（`null`）→ 未知，返 `false`（不等于「无此科目」）；
 * 2. 下发了但两个码集皆空 → `true`（后端宁缺勿造）；
 * 3. 有码 → `false`。
 */
export function iCycleAccountAbsent(
  src: TbSourceCodes | null | undefined,
  wpCode: string,
  segment?: string,
): boolean {
  const seg = iCycleSegment(src, wpCode, segment)
  if (!seg) return false // render 未下发 → 未知
  return nonEmpty(seg.standard).length === 0 && nonEmpty(seg.original).length === 0
}

/**
 * 某科目码是否属于该段（事件过滤 / 高亮 / 明细归属判定用）。
 *
 * 🔴 严格点号边界：前缀 `1701` 不得误命中 `17010`（不同科目），
 * 但须命中 `1701.01` 这类子科目。
 */
export function iCycleMatchesSegment(
  code: unknown,
  src: TbSourceCodes | null | undefined,
  wpCode: string,
  segment?: string,
): boolean {
  const c = String(code ?? '').trim()
  if (!c) return false
  const targets = [
    ...iCycleQueryCodes(src, wpCode, segment),
    ...iCycleOriginalCodes(src, wpCode, segment),
  ]
  return targets.some((t) => c === t || c.startsWith(`${t}.`))
}

/** 段展示顺序（审定表溯源面板 `slotOrder` 用） */
export function iCycleSegmentOrder(wpCode: string): string[] {
  return (iCycleSpec(wpCode)?.segments || []).map((s) => s.segment)
}

/** 段键 → 中文名（溯源面板 `slotLabels` 兜底；后端下发 label 时优先后端） */
export function iCycleSegmentLabels(wpCode: string): Record<string, string> {
  const out: Record<string, string> = {}
  for (const s of iCycleSpec(wpCode)?.segments || []) out[s.segment] = s.label
  return out
}
