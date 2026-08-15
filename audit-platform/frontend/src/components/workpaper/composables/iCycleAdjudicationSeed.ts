/**
 * iCycleAdjudicationSeed — I 类六循环审定表「从四表库带入未审数」的声明与映射（纯函数）。
 *
 * ## 要解决的缺陷
 *
 * 后端 `four_table/i_cycle_prefill.build_adjudication_prefill()` 每次 render 都在算
 * （I1 按 11 类科目名归类 × 三段、I2~I6 按叶子科目逐行），六个 render 策略
 * (`_i1_intangible_assets.py` ~ `_i6_research_development_expense.py`) 都
 * `payload["adjudication_prefill"] = extraction.adjudication_prefill` 下发，
 * 而**前端六个宿主零消费方** —— 实测 `GtI1IntangibleAssets` ~ `GtI6ResearchDevelopmentExpense`
 * 全都不读该键（2026-08-12 `_wip_i_task17.py` 逐点实测）。
 *
 * 这与 H 循环踩过的 **dead output** 完全同型：后端花 DB 查询产出、前端从不消费。
 * 对比 D6 / F1 / F3 / F5 / K1~K13 都已接上消费侧。
 *
 * ## 与 H 循环的关键差异：归类已在后端做完
 *
 * `hCycleAdjudicationSeed.ts` 要写一整套关键词归类规则，因为 H 的后端只产逐叶子明细。
 * **I 的后端已经归类好了**（`_category_key_of()` 按科目名归到 11 类 / `leaf_label()`
 * 取名称后缀），所以本模块**不写归类规则** —— 只做三件事：
 *
 * 1. **段键翻译**：后端段键 ↔ 前端 block 键并不一致
 *    （🔴 I1 后端 `amortization` vs 前端 `I1BlockType='amort'`，不翻译则累计摊销段静默丢失）。
 * 2. **行标签匹配**：后端 `rows[].label` ↔ 前端行的 `projectName`/`category`/`类别`。
 *    用**标签**而非 `rowId` —— `rowId` 由前端生成，后端不可能知道。
 * 3. **三类残余如实上报**，不兜底：
 *    - 段不在载荷里 → `absentSlots`（本项目无此科目，界面如实说明，**不写 0**）
 *    - 后端有行但前端无同名行 → `unclassified`（交审计师显式归入，**不塞进「其他」行**）
 *    - `prefill.unmapped`（后端归类不到 11 类的科目码）一并进 `unclassified`
 *
 * 「哪些格算冲突、怎么幂等」由平台共享件 `shared/adjudicationPrefillPlan` 负责，本模块只产 cells。
 *
 * 本模块**零 Vue 依赖、纯函数**，便于单测与跨文件交叉锁死。
 *
 * spec: .kiro/specs/i-cycle-extraction-formula-and-disclosure-closure/ Task 17
 *       Requirements 9.2, 9.3, 9.4
 */
import type {
  AdjPrefillCell,
  AdjPrefillUnclassified,
} from './shared/adjudicationPrefillPlan'
import {
  I_SEGMENT_AMORTIZATION,
  I_SEGMENT_COST,
  I_SEGMENT_EXPENSE,
  I_SEGMENT_IMPAIRMENT,
  type ICycleWpCode,
} from './iCycleAccountScope'

// ═══════════════════════════════════════════════════════════════════════════
// 后端载荷契约（`html_data.adjudication_prefill`）
// ═══════════════════════════════════════════════════════════════════════════

/** 一个预填行（后端 `build_i1_category_rows` / `build_leaf_project_rows` 的一行） */
export interface IPrefillRow {
  /** I1 = 类别键（`i1_asset_categories` 的 key）；其余 = 叶子科目码 */
  key: string
  /** 中文标签：I1 = 类别名；其余 = 叶子科目名后缀（`长期待摊费用_装修费` → `装修费`） */
  label: string
  /** 该行金额来自哪些客户原始科目码（溯源展示） */
  codes: string[]
  opening: number
  closing: number
  increase: number
  decrease: number
}

/** 一个段（后端按 `ISegmentAccounts.segment` 分段） */
export interface IPrefillSegment {
  segment: string
  label: string
  rows: IPrefillRow[]
  /** 仅 `mode='leaf'` 有；`mode='category'` 不产 totals */
  totals?: Record<string, number>
}

/** `html_data.adjudication_prefill` 整体 */
export interface IAdjudicationPrefill {
  /** `category` = I1 三段 × 类别；`leaf` = I2~I6 叶子项目行 */
  mode: 'category' | 'leaf'
  segments: IPrefillSegment[]
  /** 后端归类不到已知类别的科目码（I1 专有；其余恒空数组） */
  unmapped: string[]
}

// ═══════════════════════════════════════════════════════════════════════════
// 段键翻译（🔴 后端段键 ≠ 前端 block 键）
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 后端段键 → 前端 `I1BlockType` 的翻译表。
 *
 * 🔴 **`amortization` → `amort`**：后端 `i1_asset_categories.SEGMENT_AMORTIZATION = 'amortization'`，
 * 而前端 `useI1Adjudication.I1BlockType = 'cost' | 'amort' | 'impairment'`。
 * 不翻译 ⇒ `updateCell('amortization', ...)` 落不到任何 block，**累计摊销段整段静默丢失**
 * （TS 层也拦不住：`block` 参数在运行时只是字符串比较）。
 */
export const I1_SEGMENT_TO_BLOCK: Readonly<Record<string, string>> = {
  [I_SEGMENT_COST]: 'cost',
  [I_SEGMENT_AMORTIZATION]: 'amort',
  [I_SEGMENT_IMPAIRMENT]: 'impairment',
} as const

/** 段键 → 前端 block 键；非 I1 循环无 block 概念，返 `undefined` */
export function iSegmentToBlock(cycle: string, segment: string): string | undefined {
  if (String(cycle || '').toUpperCase() !== 'I1') return undefined
  return I1_SEGMENT_TO_BLOCK[segment]
}

// ═══════════════════════════════════════════════════════════════════════════
// 每循环的列字段声明
// ═══════════════════════════════════════════════════════════════════════════

/** 某段在审定表里对应的列字段 */
export interface ISeedSlot {
  /** 后端段键（逐字对齐 `i_cycle_accounts.SEGMENT_*`） */
  segment: string
  /** 段中文名（`absentSlots` 提示用） */
  segmentLabel: string
  /**
   * 期末（或本期）未审列字段名。
   *
   * 🔴 必须逐字等于该循环行模型的字段名 —— 传不存在的字段 = 静默不写入，
   * `get_diagnostics` / vitest / HEAD-swap 四层都查不出（平台已记铁律）。
   */
  closingField: string
  /** 期末列中文名（冲突清单 / toast 文案用） */
  closingLabel: string
  /** 期初未审列字段名；不声明则不产期初格 */
  openingField?: string
  /** 期初列中文名 */
  openingLabel?: string
}

/** 一个循环的完整声明 */
export interface ISeedSpec {
  cycle: ICycleWpCode
  /** 行标签字段名（后端 label 与该字段比对）：`projectName` / `category` / `类别` */
  labelField: string
  /** 段 → 列字段（顺序 = 审定表展示顺序） */
  slots: readonly ISeedSlot[]
  /**
   * 未命中现有行时的默认落点。
   *
   * 🔴 **恒为空数组**（宁缺勿造）：未命中的行进 `unclassified` 由审计师显式归入，
   * 绝不塞进「其他」行（K2 实测把三行坏账准备全堆进「其他」的根因）。
   * 保留该字段是为了让守卫能**正向断言它确实是空的**，而不是靠「源码里没这个字段」这种弱判据。
   */
  defaults: readonly never[]
}

/**
 * 六循环声明（唯一真源；守卫 `iCycleAdjudicationSeed.spec.ts` 与各 composable 的
 * 行模型字段名交叉锁死）。
 */
export const I_CYCLE_SEED_SPECS: Readonly<Record<ICycleWpCode, ISeedSpec>> = {
  // I1：三段 × 类别行；行标签 = `category`；`updateCell(block, rowId, field, value)` 四参
  I1: {
    cycle: 'I1',
    labelField: 'category',
    slots: [
      {
        segment: I_SEGMENT_COST,
        segmentLabel: '账面原值',
        closingField: 'unadjusted',
        closingLabel: '期末未审',
      },
      {
        segment: I_SEGMENT_AMORTIZATION,
        segmentLabel: '累计摊销',
        closingField: 'unadjusted',
        closingLabel: '期末未审',
      },
      {
        segment: I_SEGMENT_IMPAIRMENT,
        segmentLabel: '减值准备',
        closingField: 'unadjusted',
        closingLabel: '期末未审',
      },
    ],
    defaults: [],
  },
  // I2：单段；双期（期初/期末未审各一列）；`updateRow(rowId, field, value)`
  I2: {
    cycle: 'I2',
    labelField: 'projectName',
    slots: [
      {
        segment: I_SEGMENT_COST,
        segmentLabel: '开发支出',
        closingField: 'endUnadj',
        closingLabel: '期末未审',
        openingField: 'beginUnadj',
        openingLabel: '期初未审',
      },
    ],
    defaults: [],
  },
  // I3：两段（商誉账面原值 / 商誉减值准备）；🔴 减值段后端兜底为空 ⇒ 常进 absentSlots
  //
  // 🔴 行标签字段是 **`investee`**（商誉按「被投资单位」分行），不是 `projectName`。
  //    `i3AdjudicationModel.normalizeI3AdjudicationRow` 里 `raw?.investee || raw?.projectName`
  //    只是**读取时的兼容别名** —— 归一后的行上只有 `investee`，写 `projectName`
  //    会让全部行标签取到空串、于是每一行都匹配不上、整循环带入静默失效。
  I3: {
    cycle: 'I3',
    labelField: 'investee',
    slots: [
      {
        segment: I_SEGMENT_COST,
        segmentLabel: '商誉账面原值',
        closingField: 'unadjusted',
        closingLabel: '期末未审',
      },
      {
        segment: I_SEGMENT_IMPAIRMENT,
        segmentLabel: '商誉减值准备',
        closingField: 'unadjusted',
        closingLabel: '期末未审',
      },
    ],
    defaults: [],
  },
  I4: {
    cycle: 'I4',
    labelField: 'projectName',
    slots: [
      {
        segment: I_SEGMENT_COST,
        segmentLabel: '长期待摊费用',
        closingField: 'unadjusted',
        closingLabel: '期末未审',
      },
    ],
    defaults: [],
  },
  // I5：🔴 `1911` 全库两张科目表都不存在 ⇒ 该段恒进 absentSlots（正确行为，不写 0）
  I5: {
    cycle: 'I5',
    labelField: 'projectName',
    slots: [
      {
        segment: I_SEGMENT_COST,
        segmentLabel: '其他非流动资产',
        closingField: 'unadjusted',
        closingLabel: '期末未审',
      },
    ],
    defaults: [],
  },
  // I6：损益类取**本期发生额**；行标签与列字段都是中文（该 composable 的行模型如此）
  I6: {
    cycle: 'I6',
    labelField: '类别',
    slots: [
      {
        segment: I_SEGMENT_EXPENSE,
        segmentLabel: '研发费用',
        closingField: '本期未审',
        closingLabel: '本期未审',
      },
    ],
    defaults: [],
  },
} as const

// ═══════════════════════════════════════════════════════════════════════════
// 映射（六循环共用；不含任何循环专属分支）
// ═══════════════════════════════════════════════════════════════════════════

/** 标签归一化：去全部空白（源模板里「项  目」这类双空格很常见） */
export function normalizeSeedLabel(v: unknown): string {
  return String(v ?? '').replace(/\s+/g, '')
}

export interface ICycleSeedResult {
  /** 待写入格（交 `planAdjudicationPrefill` 做 plan） */
  cells: AdjPrefillCell[]
  /** 后端有金额但前端无同名行 → 交审计师显式归入，不兜底 */
  unclassified: AdjPrefillUnclassified[]
  /** 本项目无该段科目 → 界面如实说明，不写 0 */
  absentSlots: Array<{ slotKey: string; label: string }>
  /** 段键翻译后落到的 block（仅 I1 有值），供 `updateCell` 四参调用 */
  blockOf: Record<string, string | undefined>
}

/** 现有审定表行（只需标签与行键两个字段，故用最小结构） */
export interface ISeedExistingRow {
  rowId: string
  /** 该行的标签值（调用方按 `spec.labelField` 取好后传入） */
  label: string
}

/** 循环声明；未知 wp_code 返 `undefined` */
export function iCycleSeedSpec(wpCode: string): ISeedSpec | undefined {
  return I_CYCLE_SEED_SPECS[String(wpCode || '').toUpperCase() as ICycleWpCode]
}

/**
 * 把后端载荷映射成待写入格。
 *
 * @param prefill render 下发的 `html_data.adjudication_prefill`（未下发传 `null`）
 * @param wpCode I1~I6
 * @param existing 审定表现有行（标签已按 `spec.labelField` 取出）
 *
 * 语义要点：
 * - `prefill` 为 `null`（后端全空未下发该键）→ 全部段进 `absentSlots`，`cells` 为空。
 *   这**不是**「金额为 0」，界面须如实说明。
 * - 某段不在 `segments` 里 → 该段进 `absentSlots`（后端宁缺勿造）。
 * - 某行标签在前端找不到同名行 → 进 `unclassified`（不兜底、不新建行）。
 * - `prefill.unmapped` 的科目码一并进 `unclassified`（后端归类不到已知类别）。
 */
export function buildICycleSeedCells(
  prefill: IAdjudicationPrefill | null | undefined,
  wpCode: string,
  existing: readonly ISeedExistingRow[],
): ICycleSeedResult {
  const spec = iCycleSeedSpec(wpCode)
  const out: ICycleSeedResult = {
    cells: [],
    unclassified: [],
    absentSlots: [],
    blockOf: {},
  }
  if (!spec) return out

  const byLabel = new Map<string, ISeedExistingRow>()
  for (const row of existing || []) {
    const key = normalizeSeedLabel(row.label)
    if (key && !byLabel.has(key)) byLabel.set(key, row)
  }

  const segments = prefill?.segments || []
  for (const slot of spec.slots) {
    out.blockOf[slot.segment] = iSegmentToBlock(spec.cycle, slot.segment)
    const seg = segments.find((s) => s && s.segment === slot.segment)
    if (!seg || !(seg.rows || []).length) {
      // 段缺失或无行 ⇒ 本项目无此科目（不写 0）
      out.absentSlots.push({ slotKey: slot.segment, label: slot.segmentLabel })
      continue
    }
    for (const row of seg.rows) {
      const hit = byLabel.get(normalizeSeedLabel(row.label))
      if (!hit) {
        out.unclassified.push({
          code: (row.codes || [])[0] || row.key || '',
          name: `${slot.segmentLabel}·${row.label}`,
          amount: Number(row.closing) || 0,
          opening: Number(row.opening) || 0,
        })
        continue
      }
      out.cells.push({
        rowKey: hit.rowId,
        field: slot.closingField,
        amount: Number(row.closing) || 0,
        label: row.label,
        periodLabel: `${slot.segmentLabel}·${slot.closingLabel}`,
        sourceCodes: [...(row.codes || [])],
      })
      if (slot.openingField) {
        out.cells.push({
          rowKey: hit.rowId,
          field: slot.openingField,
          amount: Number(row.opening) || 0,
          label: row.label,
          periodLabel: `${slot.segmentLabel}·${slot.openingLabel || '期初未审'}`,
          sourceCodes: [...(row.codes || [])],
        })
      }
    }
  }

  // 后端归类不到已知类别的科目码（I1 专有）
  for (const code of prefill?.unmapped || []) {
    const c = String(code || '').trim()
    if (!c) continue
    out.unclassified.push({ code: c, name: `未归类科目 ${c}`, amount: 0, opening: 0 })
  }
  return out
}

/** 从 render 载荷里取 `adjudication_prefill`（形态校验，非对象一律返 `null`） */
export function extractICyclePrefill(
  htmlData?: Record<string, unknown> | null,
): IAdjudicationPrefill | null {
  const raw = (htmlData as any)?.adjudication_prefill ?? (htmlData as any)?.adjudicationPrefill
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const mode = (raw as any).mode
  if (mode !== 'category' && mode !== 'leaf') return null
  return {
    mode,
    segments: Array.isArray((raw as any).segments) ? (raw as any).segments : [],
    unmapped: Array.isArray((raw as any).unmapped) ? (raw as any).unmapped : [],
  }
}
