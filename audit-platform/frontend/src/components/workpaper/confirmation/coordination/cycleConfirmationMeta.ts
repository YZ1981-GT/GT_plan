/**
 * cycleConfirmationMeta — 各循环（D0/E0/F0/G0/H0/K0/L0）函证底稿编码与跨表文案
 *
 * 共享 HTML 组件（summary / diff / reliability / alternative master）挂在不同循环时，
 * 须按 wpCode 前缀解析 sheet 名，避免文案写死 D0-*。
 */

// 🔴 L0 的 sheet 定位/展示真源在 L0 专属目录（源模板 9 张可见 tab 名逐字固化 +
//    程序表 tab 名 `函证程序表F0A` 的索引号笔误说明；hidden 的差异检查表不登记）。
//    spec: l0-confirmation-source-alignment R6.1~R6.4
import { L0_CONFIRMATION_SHEETS } from '../l0-confirmation/l0SheetRegistry'
// 🔴 K0 的 sheet 定位/展示真源在 K0 专属目录（源模板 10 张 tab 名逐字固化 + 三条
//    「跨表引用索引号笔误」说明，文案由 `k0LowerZoneSpec.K0_INDEX_TYPO_MAP` 派生）。
//    spec: k0-confirmation-source-alignment R2.2 / R6.1 / R6.2
import { K0_CONFIRMATION_SHEETS } from '../k0-confirmation/k0SheetRegistry'
// 🔴 G0 的 sheet 定位/展示真源在 G0 专属目录（源模板 10 张 tab 名逐字固化 + 三处索引号笔误说明）。
//    反向只有 `import type`（被编译期擦除）→ 无运行时循环依赖。
import { G0_CONFIRMATION_SHEETS } from '../../g0-confirmation/g0SheetRegistry'

export type ConfirmationCycle =
  | 'D0'
  | 'E0'
  | 'F0'
  | 'G0'
  | 'H0'
  | 'K0'
  | 'L0'

/**
 * 单张函证 sheet 的「定位值 / 展示值」分离声明（H10 范式；裁决门 B，2026-08-04 用户裁决）。
 *
 * spec: g0-confirmation-source-alignment，Requirement 6.1~6.4
 */
export interface ConfirmationSheetRef {
  /**
   * 定位真源：源模板真实 tab 名（逐字，含全/半角括号与索引号笔误）。
   * 本循环无此表时为 null。**一切 sheet 请求 / `?sheet=` 深链只许用它。**
   */
  sheetName: string | null
  /** 展示真源：底稿目录索引号（tab 名笔误已按目录裁决修正）。一切 UI 展示只许用它。 */
  indexLabel: string
  /**
   * 索引号笔误说明（tooltip 用；SHALL NOT 静默改写，见 G0 R6.3）。
   *
   * 两种成因都落这里 —— 对用户而言要回答的是同一个问题「我在源模板上看到的索引号
   * 为什么和这里显示的不一样」：
   *   - **tab 名笔误**（G0 / L0）：本表 tab 名尾码与底稿目录不一致，如 L0 的 `函证程序表F0A`；
   *   - **跨表引用笔误**（K0）：本表命名正确，但源模板**别处**引用它时写错了索引号，
   *     如 `K0-1!V6` 写「调节索引（K1-12）」而差异调节表实为 `K0-4`。
   */
  indexTypoNote?: string
}

/** `CycleConfirmationMeta.sheets` 的槽位集合（与既有 `*Code` 字段一一对应） */
export type ConfirmationSheetSlot =
  | 'program'
  | 'summary'
  | 'entityVerify'
  | 'followup'
  | 'diff'
  | 'diffSecurities'
  | 'diffChecklist'
  | 'altPrimary'
  | 'altSecondary'
  | 'reliability'
  | 'fraud'

export interface CycleConfirmationMeta {
  cycle: ConfirmationCycle
  /** 汇总表，如 F0-1 */
  summaryCode: string
  /** 差异调节，如 F0-4（E0 无独立差异表 → null） */
  diffCode: string | null
  /** 差异检查表（D0/F0/K0 有 4b；其余可能无） */
  diffChecklistCode: string | null
  /** 差异证券专表（仅 G0 有；展示值取底稿目录索引号 G0-4，其余 null） */
  diffSecuritiesCode: string | null
  /** 替代程序主表（部分循环仅一张；E0 货币资金无替代程序 → null） */
  altPrimaryCode: string | null
  /** 第二张替代（无则 null） */
  altSecondaryCode: string | null
  /** 回函可靠性（E0 无可靠性验证 sheet → null） */
  reliabilityCode: string | null
  /** 舞弊风险 */
  fraudCode: string
  /** 主体核查 */
  entityVerifyCode: string
  /** 跟函 */
  followupCode: string
  /**
   * 逐 sheet 的「定位值 / 展示值」分离声明（R6.1）。**加法式新增，既有 `*Code` 字段一个不删。**
   *
   * - G0 引用 `g0SheetRegistry`（源模板 tab 名真源，含三处索引号笔误说明）
   * - 其余六循环由既有 `*Code` 字段**派生**（`deriveSheetsFromCodes`）—— 它们没有 tab 名
   *   真源，故 `sheetName` 取既有 code 而**不编造中文 tab 名**，`indexLabel` 与 code 相同
   *   → 六枢纽的展示与跳转行为逐字不变（R11.1 零回归支点）。
   */
  sheets: Record<ConfirmationSheetSlot, ConfirmationSheetRef | null>
}

/** 既有编码字段（不含派生出来的 `sheets`），`CYCLE_SHEETS` 的声明形态 */
type CycleConfirmationCodes = Omit<CycleConfirmationMeta, 'cycle' | 'sheets'>

const CYCLE_SHEETS: Record<ConfirmationCycle, CycleConfirmationCodes> = {
  D0: {
    summaryCode: 'D0-1',
    entityVerifyCode: 'D0-2',
    followupCode: 'D0-3',
    diffCode: 'D0-4',
    diffChecklistCode: 'D0-4b',
    diffSecuritiesCode: null,
    altPrimaryCode: 'D0-5',
    altSecondaryCode: 'D0-6',
    reliabilityCode: 'D0-7',
    fraudCode: 'D0-8',
  },
  E0: {
    // E0（货币资金）真实模板：E0-1 汇总 / E0-2 核实单位 / E0-3~6 发函记录(d-form) /
    // E0-7 跟函 / E0-8 舞弊。勿按 D0 序号镜像；无独立差异调节表与回函可靠性表。
    summaryCode: 'E0-1',
    entityVerifyCode: 'E0-2',
    followupCode: 'E0-7',
    diffCode: null, // E0 无独立差异调节表
    diffChecklistCode: null,
    diffSecuritiesCode: null,
    altPrimaryCode: null, // E0 无替代程序 sheet（发函记录 E0-3~6 为 d-form 直接编制，非替代确认）
    altSecondaryCode: null,
    reliabilityCode: null, // 源模板有「邮件传真回函核对记录F1-12」，但为 hidden sheet 且 override 置 skip，故不启用
    fraudCode: 'E0-8',
  },
  F0: {
    summaryCode: 'F0-1',
    entityVerifyCode: 'F0-2',
    followupCode: 'F0-3',
    diffCode: 'F0-4',
    diffChecklistCode: 'F0-4b',
    diffSecuritiesCode: null,
    altPrimaryCode: 'F0-5',
    altSecondaryCode: 'F0-6',
    reliabilityCode: 'F0-7',
    fraudCode: 'F0-8',
  },
  G0: {
    summaryCode: 'G0-1',
    entityVerifyCode: 'G0-2',
    followupCode: 'G0-3',
    // 🔴 展示值 = 底稿目录 F4:F12 索引号（索引号唯一裁决者），不是 tab 名里的索引号：
    //    非证券差异表 tab 写 G0-4 而目录为 G0-5；证券差异表 tab 写 G0-3 而目录为 G0-4。
    //    定位一律走 sheets.diff / sheets.diffSecurities 的 sheetName（真实 tab 名）。
    diffCode: 'G0-5',
    diffChecklistCode: null,
    diffSecuritiesCode: 'G0-4', // 证券差异专表（G0 特有）；旧值 'G0-3S' 是不存在的底稿
    altPrimaryCode: 'G0-6',
    altSecondaryCode: null,
    reliabilityCode: 'G0-7',
    fraudCode: 'G0-8',
  },
  H0: {
    summaryCode: 'H0-1',
    entityVerifyCode: 'H0-2',
    followupCode: 'H0-3',
    diffCode: 'H0-4',
    diffChecklistCode: null,
    diffSecuritiesCode: null,
    altPrimaryCode: 'H0-5',
    altSecondaryCode: null,
    reliabilityCode: 'H0-6',
    fraudCode: 'H0-7',
  },
  K0: {
    summaryCode: 'K0-1',
    entityVerifyCode: 'K0-2',
    followupCode: 'K0-3',
    diffCode: 'K0-4',
    diffChecklistCode: null,
    diffSecuritiesCode: null,
    altPrimaryCode: 'K0-5',
    altSecondaryCode: 'K0-6',
    reliabilityCode: 'K0-7',
    fraudCode: 'K0-8',
  },
  L0: {
    summaryCode: 'L0-1',
    entityVerifyCode: 'L0-2',
    followupCode: 'L0-3',
    diffCode: 'L0-4',
    diffChecklistCode: null,
    diffSecuritiesCode: null,
    altPrimaryCode: 'L0-5',
    altSecondaryCode: null,
    reliabilityCode: 'L0-6',
    fraudCode: 'L0-7',
  },
}

/** 从任意函证 sheet 编码解析循环前缀 */
export function resolveConfirmationCycle(wpCode?: string | null): ConfirmationCycle {
  const code = String(wpCode || '').trim().toUpperCase()
  const m = code.match(/^([DEFGHKL])0\b/)
  if (m) return `${m[1]}0` as ConfirmationCycle
  // fallback: 前缀如 "F0-5"
  const prefix = code.split('-')[0]
  if (prefix && /^[DEFGHKL]0$/i.test(prefix)) return prefix.toUpperCase() as ConfirmationCycle
  return 'D0'
}

/**
 * 槽位 → 既有编码字段名（`sheets` 与 `*Code` 的唯一对应表）。
 * `program` 不在此表：既有字段里没有程序表 code，按循环前缀派生 `{cycle}A`。
 */
const SLOT_CODE_FIELD: Readonly<
  Record<Exclude<ConfirmationSheetSlot, 'program'>, keyof CycleConfirmationCodes>
> = Object.freeze({
    summary: 'summaryCode',
    entityVerify: 'entityVerifyCode',
    followup: 'followupCode',
    diff: 'diffCode',
    diffSecurities: 'diffSecuritiesCode',
    diffChecklist: 'diffChecklistCode',
    altPrimary: 'altPrimaryCode',
    altSecondary: 'altSecondaryCode',
    reliability: 'reliabilityCode',
    fraud: 'fraudCode',
  })

/**
 * 由既有 `*Code` 字段派生 `sheets`（D0/E0/F0/H0/K0/L0 走这条路）。
 *
 * 🔴 这些循环**没有 tab 名真源** → `sheetName` 取既有 code（与 `indexLabel` 相同），
 * 绝不编造中文 tab 名。由此 `isSameWorkbookNavTarget()` 对它们恒为 false，
 * 跳转仍走既有 `navigate`（按 wp_code 解析），行为逐字不变。
 *
 * `program`（程序表）在既有字段里没有对应 code，按循环前缀派生 `{cycle}A`（D0A/F0A/…）。
 */
function deriveSheetsFromCodes(
  cycle: ConfirmationCycle,
  codes: CycleConfirmationCodes,
): Record<ConfirmationSheetSlot, ConfirmationSheetRef | null> {
  const programCode = `${cycle}A`
  const out = {
    program: { sheetName: programCode, indexLabel: programCode },
  } as Record<ConfirmationSheetSlot, ConfirmationSheetRef | null>
  for (const slot of Object.keys(SLOT_CODE_FIELD) as Array<
    Exclude<ConfirmationSheetSlot, 'program'>
  >) {
    const raw = codes[SLOT_CODE_FIELD[slot]] as string | null | undefined
    out[slot] = raw ? { sheetName: raw, indexLabel: raw } : null
  }
  return out
}

function resolveCycleSheets(
  cycle: ConfirmationCycle,
  codes: CycleConfirmationCodes,
): Record<ConfirmationSheetSlot, ConfirmationSheetRef | null> {
  // G0 / K0 / L0 有源模板 tab 名真源（逐字固化）→ 用注册表；其余四循环派生。
  //
  // 🔴 L0 接注册表会把它的跨表跳转从「按 wp_code」切到「同工作簿 `?sheet=` 深链」，
  //    这是 spec l0-confirmation-source-alignment R6.1 的裁决，且有库侧实证支撑：
  //    `wp_index` 里 L0 只有整册 `L0` 与遗留单 sheet `L0-1`~`L0-5`，**没有 L0-6/L0-7**
  //    → 按 wp_code 跳这两张表本来就落空；遗留单 sheet wp_code 的 render 又返
  //    `html_data=null`（同 G0/H0）⇒ `?sheet=` 是唯一可达路径。
  //
  // 🔴 K0 同款（2026-08-07 `wp_index` 实测）：只有整册 `K0` 与遗留 `K0-1`~`K0-5`，
  //    **没有 K0-6/K0-7/K0-8**（= altSecondary / reliability / fraud 三槽）
  //    ⇒ 接注册表既让这三张表可达，又给三条「跨表引用索引号笔误」提供 tooltip 落点。
  //    详见 `k0-confirmation/k0SheetRegistry.ts` 文件头。
  if (cycle === 'G0') return G0_CONFIRMATION_SHEETS
  if (cycle === 'K0') return K0_CONFIRMATION_SHEETS
  if (cycle === 'L0') return L0_CONFIRMATION_SHEETS
  return deriveSheetsFromCodes(cycle, codes)
}

export function getCycleConfirmationMeta(wpCode?: string | null): CycleConfirmationMeta {
  const cycle = resolveConfirmationCycle(wpCode)
  const codes = CYCLE_SHEETS[cycle]
  return { cycle, ...codes, sheets: resolveCycleSheets(cycle, codes) }
}

/** 替代程序标签（主表/次表拼接；无替代程序 sheet 时返回 null，如 E0） */
export function altProcedureLabel(m: CycleConfirmationMeta): string | null {
  if (!m.altPrimaryCode) return null
  return m.altSecondaryCode
    ? `${m.altPrimaryCode}/${m.altSecondaryCode}`
    : m.altPrimaryCode
}

/** 汇总表 CrossRef 规则文案（挂在 confirmation-summary；null sheet 自动跳过） */
export function buildCrossRefRules(wpCode?: string | null) {
  const m = getCycleConfirmationMeta(wpCode)
  const altLabel = altProcedureLabel(m)
  const rules: Array<{ field: string; target: string; rule: string }> = [
    { field: '函证金额', target: 'TB 试算表', rule: '应与科目审定余额(audited_amount)核对一致' },
  ]
  if (m.diffCode) {
    rules.push({ field: '差异金额', target: `${m.diffCode} 差异调节`, rule: `不符项跳转到 ${m.diffCode} 差异调节表编制` })
  }
  if (m.diffSecuritiesCode) {
    rules.push({ field: '证券差异', target: `${m.diffSecuritiesCode} 证券差异专表`, rule: `证券类不符项跳转到 ${m.diffSecuritiesCode} 编制` })
  }
  if (altLabel) {
    rules.push({ field: '替代确认', target: altLabel, rule: `未回函项跳转到替代程序底稿（${altLabel}）确认` })
  }
  if (m.reliabilityCode) {
    rules.push({ field: '回函可靠性', target: m.reliabilityCode, rule: `电子回函需跳转 ${m.reliabilityCode} 验证可靠性` })
  }
  rules.push({ field: '舞弊风险', target: `${m.fraudCode}/B50`, rule: `异常迹象需记录到 ${m.fraudCode} 并汇总至 B50 风险评估` })
  return rules
}

/** 跨表导航项（`sheetName` 为定位值、`label` 为展示值、`tooltip` 含笔误说明） */
export interface CrossWorkpaperNavDef {
  /** 跨工作簿跳转用的底稿编码（= 展示索引号；组合替代程序为 `X0-5/X0-6` 形态） */
  wpCode: string
  /** 展示值（底稿目录索引号） */
  label: string
  /** 悬停提示；有 `indexTypoNote` 时追加源模板笔误说明 */
  tooltip: string
  /**
   * 同工作簿定位值（源模板真实 tab 名）。为 null 表示本槽没有 tab 名真源
   * （六枢纽的派生值与 `wpCode` 相同、组合替代程序无单一 sheet）→ 回退按 `wpCode` 跳转。
   */
  sheetName: string | null
}

/**
 * 判「该导航目标是否在同一工作簿内」。
 *
 * 判据 = 该槽有**真实 tab 名真源**且与展示编码不同。
 *
 * 🔴 已接注册表（sheetName 是中文 tab 名 ⇒ 恒 true ⇒ 走 `?sheet=` 深链）：
 *    **G0 / L0 / K0** —— 三者都是单 `wp_code` 多 sheet 工作簿，且 `wp_index` 里缺后几张
 *    单 sheet 记录，按 wp_code 跳本就落空（各自 registry 文件头有库侧实证）。
 * 🔴 仍走派生（sheetName === wpCode ⇒ 恒 false ⇒ 既有 `navigate` 按 wp_code 解析）：
 *    **D0 / E0 / F0 / H0** —— 行为逐字不变（G0 spec R11.1 的零回归支点）。
 *
 * 改写记录：本注释原写「D0/E0/F0/H0/K0/L0 … 恒为 false」，该表述在
 * `l0-confirmation-source-alignment`（L0 接注册表）与
 * `k0-confirmation-source-alignment` Task 12（K0 接注册表）后失效，已按实际收敛。
 */
export function isSameWorkbookNavTarget(def: CrossWorkpaperNavDef): boolean {
  return !!def.sheetName && def.sheetName !== def.wpCode
}

/** CrossWorkpaperNav 导航项（按循环；槽位本身不存在（meta 为 null）时才跳过，不生成跳错的入口） */
export function buildCrossWorkpaperNavDefs(wpCode?: string | null): CrossWorkpaperNavDef[] {
  const m = getCycleConfirmationMeta(wpCode)
  const altLabel = altProcedureLabel(m)
  const sheetNameOf = (slot: ConfirmationSheetSlot): string | null =>
    m.sheets[slot]?.sheetName ?? null
  const tooltipOf = (slot: ConfirmationSheetSlot, base: string): string => {
    const note = m.sheets[slot]?.indexTypoNote
    return note ? `${base}（${note}）` : base
  }
  const item = (
    slot: ConfirmationSheetSlot,
    code: string,
    base: string,
  ): CrossWorkpaperNavDef => ({
    wpCode: code,
    label: code,
    tooltip: tooltipOf(slot, base),
    sheetName: sheetNameOf(slot),
  })

  const items: CrossWorkpaperNavDef[] = [
    item('entityVerify', m.entityVerifyCode, '核实被函证单位'),
    item('summary', m.summaryCode, '函证汇总表'),
    item('followup', m.followupCode, '跟函过程控制'),
  ]
  if (m.reliabilityCode) {
    items.push(item('reliability', m.reliabilityCode, '回函可靠性验证'))
  }
  if (m.diffCode) {
    items.push(item('diff', m.diffCode, '差异调节表'))
  }
  if (m.diffSecuritiesCode) {
    items.push(item('diffSecurities', m.diffSecuritiesCode, '证券差异专表'))
  }
  if (m.diffChecklistCode) {
    items.push(item('diffChecklist', m.diffChecklistCode, '差异检查表'))
  }
  if (altLabel) {
    // 组合替代程序（D0-5/D0-6 等）没有单一 sheet → sheetName 取 null，回退按 wpCode 跳转
    items.push({
      wpCode: altLabel,
      label: altLabel,
      tooltip: tooltipOf('altPrimary', '替代程序'),
      sheetName: m.altSecondaryCode ? null : sheetNameOf('altPrimary'),
    })
  }
  items.push(item('fraud', m.fraudCode, '舞弊风险评价'))
  return items
}

/** 示例索引号（导入模板说明） */
export function exampleConfirmIndex(wpCode?: string | null): string {
  const cycle = resolveConfirmationCycle(wpCode)
  return `${cycle}-001`
}
