/**
 * useD2DisclosureNote — D2 应收账款「附注披露」底稿页（结构对齐附注 五、5 / 八、5）
 *
 * 取代旧 `useD2Disclosure`（自造通用 4 版本表，已删除）：
 *  - 本 composable 用独立前缀 `D2-disc-{variant}-`（镜像 D1 的 `D1-disc-{variant}-`）；
 *  - 旧 `D2-disclosure-*` 持久化数据不迁移不删除，改由本文件末尾
 *    `importFromLegacyDisclosure()`「检测 + 一键带入可映射部分」按需读入（见该处说明）。
 *
 * 结构 = 附注模板章节（表名/列头以 `d2NoteSectionMap.ts` 常量为唯一真源）：
 *  ① 按账龄披露（账龄行动态取自项目账龄配置）
 *  ② 按坏账准备计提方法分类披露
 *  ③ 按单项计提坏账准备的应收账款
 *  ④ 组合计提项目（每个组合一张分表）
 *  ⑤ 本期计提、收回或转回的坏账准备情况
 *  ⑥ 转回或收回金额重要的坏账准备
 *  ⑦ 本期实际核销 + 重要核销逐项披露
 *  ⑧ 前五名单位情况
 *  国企另有：采用余额百分比或其他组合方法计提 / 由金融资产转移而终止确认
 *
 * 🔴 取数纪律：只使用已核实存在的跨表键，取不到的一律留手工录入（默认 0/空），
 *    绝不臆造数字，也不新增附注模板没有的列/表。
 *    - D2-2 明细：`D2-detail-rows`（nested keyed 账龄 agingPrior/agingAudited，兼容 legacy 扁平字段）
 *    - D2-1 审定：`D2-adj-{rowKey}-{period}-{unadjusted|aje|rje}`（经 useD2CrossSheet.adjudicationForDisclosure）
 *    - D2-3 坏账：`D2-bd-individual-rows` / `D2-bd-aging-rows` / `D2-bd-customer-rows`
 *    - D2-5 分析：`D2-analysis-top10`
 *    - D2-11 转回核销：`D2-writeoff-reversal-rows` / `D2-writeoff-writeoff-rows`
 */
import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import { parseNum } from './useD2FormulaEngine'
import { useD2CrossSheet } from './useD2CrossSheet'
import type { ChecklistItem, ChecklistResponse } from './useD2FormData'
import { useAgingConfig, PRESET_SEGMENTS, type AgingSegment } from '@/composables/useAgingConfig'
import { D2_NOTE_TEXT_SECTIONS, type D2DisclosureSnapshot, type D2DisclosureVariant } from './d2NoteSectionMap'

// ─── Types ───────────────────────────────────────────────────────────────────

export type D2AgingRowKind = 'segment' | 'within1Subtotal' | 'subtotal' | 'badDebt' | 'total'

export interface D2AgingDisplayRow {
  key: string
  label: string
  kind: D2AgingRowKind
  endAmount: number
  priorAmount: number
  /** 期末值来自跨表自动取数（未被手工覆盖） */
  endAuto: boolean
  priorAuto: boolean
  editable: boolean
  /** 自动取数来源说明（tooltip） */
  autoSource: string
}

export type D2ClassRowKind = 'method' | 'hint' | 'detail' | 'total'

export interface D2ClassDisplayRow {
  key: string
  label: string
  kind: D2ClassRowKind
  endAmount: number
  priorAmount: number
  editable: boolean
  auto: boolean
  autoSource: string
}

/**
 * 国企版 6 列分类宽表行（期末数/期初数各一张）
 * 对齐源模板：类别 | 账面金额 | 比例(%) | 坏账准备 | 预期信用损失率(%) | 账面价值
 */
export interface D2SoeClassWideRow {
  key: string
  label: string
  kind: 'category' | 'subtotal' | 'total'
  /** 账面金额（审定数） */
  bookAmount: number
  /** 比例(%) = 本行账面金额 / 合计账面金额 × 100 */
  ratio: number
  /** 坏账准备 */
  provision: number
  /** 预期信用损失率(%) = 坏账准备 / 账面金额 × 100 */
  lossRate: number
  /** 账面价值 = 账面金额 − 坏账准备 */
  carryingValue: number
  /** 是否可编辑（手工覆盖自动取数） */
  editable: boolean
  /** 数据来源说明 */
  autoSource: string
}

export interface D2IndividualRow {
  rowId: string
  name: string
  endAmount: number
  priorAmount: number
  /** 国企版专有列 */
  provision: number
  aging: string
  lossRate: number
  basis: string
}

export interface D2PortfolioRow {
  key: string
  label: string
  endAmount: number
  priorAmount: number
  /** 国企版：坏账准备（期末） */
  provision: number
}

export interface D2PortfolioGroup {
  groupId: string
  name: string
  rows: D2PortfolioRow[]
}

export interface D2TwoPeriodManualRow {
  rowId: string
  name: string
  endAmount: number
  priorAmount: number
}

export interface D2MovementField {
  key: keyof D2MovementValues
  label: string
  amount: number
  editable: boolean
  auto: boolean
  autoSource: string
}

export interface D2MovementValues {
  priorBalance: number
  provision: number
  reversal: number
  writeOff: number
  transfer: number
  other: number
}

export interface D2MovementCategoryRow {
  key: string
  label: string
  priorAmount: number
  /** 本期计提 */
  provisionAmount: number
  /** 收回或转回 */
  reversalAmount: number
  /** 转销或核销 */
  writeOffAmount: number
  endAmount: number
  auto: boolean
  autoSource: string
  isTotal?: boolean
}

export interface D2ReversalRow {
  rowId: string
  companyName: string
  reversalReason: string
  recoveryMethod: string
  originalBasis: string
  cumulativeProvision: number
  amount: number
}

export interface D2WriteOffRow {
  rowId: string
  companyName: string
  nature: string
  amount: number
  reason: string
  procedure: string
  relatedParty: string
}

export interface D2Top5Row {
  rowId: string
  companyName: string
  arAmount: number
  contractAssetAmount: number
  provision: number
}

export interface D2DerecognizedRow {
  rowId: string
  companyName: string
  amount: number
  gainLoss: number
}

/** (7) 转移应收账款且继续涉入形成的资产、负债 */
export interface D2ContinuedInvolvementRow {
  rowId: string
  /** 项 目 */
  item: string
  /** 资产转移方式 */
  transferMethod: string
  /** 继续涉入形成的资产金额 */
  assetAmount: number
  /** 继续涉入形成的负债金额 */
  liabilityAmount: number
}

export interface UseD2DisclosureNoteOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  variant: D2DisclosureVariant
  /** 组件提供的 debounce 持久化（PUT checklist-responses） */
  save: (items: ChecklistItem[]) => void
  isReadonly: Ref<boolean>
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function genId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
}

function safeParse<T>(json: string | null | undefined, fallback: T): T {
  if (!json) return fallback
  try {
    const parsed = JSON.parse(json)
    return (parsed ?? fallback) as T
  } catch {
    return fallback
  }
}

/** legacy 扁平账龄字段名（迁移前的 D2-detail-rows 兜底，仅默认段有对应字段） */
const LEGACY_AGING_SUFFIX: Record<string, string> = {
  within1: '1Year',
  y1to2: '1to2',
  y2to3: '2to3',
  y3to4: '3to4',
  y4to5: '4to5',
  over5: 'Over5',
}

function agingValue(raw: Record<string, any>, period: 'agingPrior' | 'agingAudited', segKey: string): number {
  const nested = raw?.[period]
  if (nested && typeof nested === 'object' && nested[segKey] !== undefined) {
    return parseNum(nested[segKey])
  }
  const suffix = LEGACY_AGING_SUFFIX[segKey]
  if (!suffix) return 0
  const flatKey = period === 'agingPrior' ? `priorAging${suffix}` : `auditedAging${suffix}`
  return parseNum(raw?.[flatKey])
}

const SUM = (list: number[]): number => list.reduce((s, v) => s + parseNum(v), 0)

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD2DisclosureNote(options: UseD2DisclosureNoteOptions) {
  const { allResponses, projectId, variant, save, isReadonly } = options
  const prefix = `D2-disc-${variant}-`
  const isSoe = variant === 'soe'

  const crossSheet = useD2CrossSheet({ allResponses })
  const { segments: configSegments } = useAgingConfig(projectId, 'D2')

  /**
   * 账龄段（枚举账龄：3年段 / 5年段 / 自定义）：项目账龄配置为唯一真源；
   * 配置未加载完成时回退 5 年段预设——与 useAgingConfig 对 D2 的默认预设一致，
   * 避免首帧用 3 年段渲染、配置到达后段数跳变。
   */
  const agingSegments: ComputedRef<AgingSegment[]> = computed(() => {
    const list = configSegments.value
    if (Array.isArray(list) && list.length > 0) return list
    return PRESET_SEGMENTS.FIVE_YEAR
  })

  // ─── 持久化读写 ────────────────────────────────────────────────────────────

  function readRaw(key: string): string | null {
    return allResponses.value.get(prefix + key)?.remark ?? null
  }

  function persist(key: string, remark: string): void {
    if (isReadonly.value) return
    const itemId = prefix + key
    const item: ChecklistItem = { item_id: itemId, conclusion: null, remark }
    allResponses.value.set(itemId, item)
    save([item])
  }

  function persistJson(key: string, value: unknown): void {
    persist(key, JSON.stringify(value))
  }

  // ─── 手工覆盖值（自动取数可被审计师覆盖）────────────────────────────────────
  // 结构：{ [cellKey]: number }，cellKey 形如 `aging:end:within1`
  const overrides = ref<Record<string, number>>({})
  const individualRows = ref<D2IndividualRow[]>([])
  const portfolios = ref<D2PortfolioGroup[]>([])
  const otherPortfolioRows = ref<D2TwoPeriodManualRow[]>([])
  const reversalRows = ref<D2ReversalRow[]>([])
  const writeOffRows = ref<D2WriteOffRow[]>([])
  const top5Rows = ref<D2Top5Row[]>([])
  const derecognizedRows = ref<D2DerecognizedRow[]>([])
  const continuedInvolvementRows = ref<D2ContinuedInvolvementRow[]>([])
  const sectionNotes = ref<Record<string, string>>({})

  let hydrated = false

  function hydrate(): void {
    overrides.value = safeParse<Record<string, number>>(readRaw('overrides'), {})
    individualRows.value = safeParse<D2IndividualRow[]>(readRaw('individual-rows'), []).map((r) => ({
      rowId: r.rowId || genId('ind'),
      name: String(r.name ?? ''),
      endAmount: parseNum(r.endAmount),
      priorAmount: parseNum(r.priorAmount),
      provision: parseNum(r.provision),
      aging: String(r.aging ?? ''),
      lossRate: parseNum(r.lossRate),
      basis: String(r.basis ?? ''),
    }))
    portfolios.value = safeParse<D2PortfolioGroup[]>(readRaw('portfolios'), []).map((g) => ({
      groupId: g.groupId || genId('pf'),
      name: String(g.name ?? ''),
      rows: Array.isArray(g.rows)
        ? g.rows.map((r) => ({
            key: String(r.key ?? ''),
            label: String(r.label ?? ''),
            endAmount: parseNum(r.endAmount),
            priorAmount: parseNum(r.priorAmount),
            provision: parseNum((r as any).provision),
          }))
        : [],
    }))
    otherPortfolioRows.value = safeParse<D2TwoPeriodManualRow[]>(readRaw('other-portfolio-rows'), []).map((r) => ({
      rowId: r.rowId || genId('op'),
      name: String(r.name ?? ''),
      endAmount: parseNum(r.endAmount),
      priorAmount: parseNum(r.priorAmount),
    }))
    reversalRows.value = safeParse<D2ReversalRow[]>(readRaw('reversal-rows'), []).map((r) => ({
      rowId: r.rowId || genId('rv'),
      companyName: String(r.companyName ?? ''),
      reversalReason: String(r.reversalReason ?? ''),
      recoveryMethod: String(r.recoveryMethod ?? ''),
      originalBasis: String(r.originalBasis ?? ''),
      cumulativeProvision: parseNum(r.cumulativeProvision),
      amount: parseNum(r.amount),
    }))
    writeOffRows.value = safeParse<D2WriteOffRow[]>(readRaw('writeoff-rows'), []).map((r) => ({
      rowId: r.rowId || genId('wo'),
      companyName: String(r.companyName ?? ''),
      nature: String(r.nature ?? ''),
      amount: parseNum(r.amount),
      reason: String(r.reason ?? ''),
      procedure: String(r.procedure ?? ''),
      relatedParty: String(r.relatedParty ?? ''),
    }))
    top5Rows.value = safeParse<D2Top5Row[]>(readRaw('top5-rows'), []).map((r) => ({
      rowId: r.rowId || genId('t5'),
      companyName: String(r.companyName ?? ''),
      arAmount: parseNum(r.arAmount),
      contractAssetAmount: parseNum(r.contractAssetAmount),
      provision: parseNum(r.provision),
    }))
    derecognizedRows.value = safeParse<D2DerecognizedRow[]>(readRaw('derecognized-rows'), []).map((r) => ({
      rowId: r.rowId || genId('dr'),
      companyName: String(r.companyName ?? ''),
      amount: parseNum(r.amount),
      gainLoss: parseNum(r.gainLoss),
    }))
    continuedInvolvementRows.value = safeParse<D2ContinuedInvolvementRow[]>(readRaw('continued-involvement-rows'), []).map((r) => ({
      rowId: r.rowId || genId('ci'),
      item: String(r.item ?? ''),
      transferMethod: String(r.transferMethod ?? ''),
      assetAmount: parseNum(r.assetAmount),
      liabilityAmount: parseNum(r.liabilityAmount),
    }))
    const notes: Record<string, string> = {}
    for (const { key } of D2_NOTE_TEXT_SECTIONS) {
      const raw = readRaw(`note-${key}`)
      if (raw) notes[key] = raw
    }
    sectionNotes.value = notes
    hydrated = true
  }

  hydrate()
  /**
   * allResponses 异步加载完成后二次 hydrate（首次 setup 时 Map 可能为空）。
   * 🔴 只在「本地尚无任何数据」时回灌，避免 size 变化（每次 persist 新键都会变）
   *    把审计师正在编辑的行/覆盖值重置回持久化快照。
   */
  function localIsEmpty(): boolean {
    return (
      Object.keys(overrides.value).length === 0 &&
      individualRows.value.length === 0 &&
      portfolios.value.length === 0 &&
      otherPortfolioRows.value.length === 0 &&
      reversalRows.value.length === 0 &&
      writeOffRows.value.length === 0 &&
      top5Rows.value.length === 0 &&
      derecognizedRows.value.length === 0 &&
      Object.keys(sectionNotes.value).length === 0
    )
  }
  watch(
    () => allResponses.value.size,
    () => {
      if (!hydrated || localIsEmpty()) hydrate()
    },
  )

  // ─── 自动取数：D2-2 明细账龄 ───────────────────────────────────────────────

  const detailAging = computed<{ end: Record<string, number>; prior: Record<string, number>; hasData: boolean }>(() => {
    const rows = safeParse<Record<string, any>[]>(allResponses.value.get('D2-detail-rows')?.remark, [])
    const end: Record<string, number> = {}
    const prior: Record<string, number> = {}
    for (const seg of agingSegments.value) {
      end[seg.key] = 0
      prior[seg.key] = 0
    }
    for (const raw of Array.isArray(rows) ? rows : []) {
      for (const seg of agingSegments.value) {
        end[seg.key] += agingValue(raw, 'agingAudited', seg.key)
        prior[seg.key] += agingValue(raw, 'agingPrior', seg.key)
      }
    }
    const hasData = Object.values(end).some((v) => v !== 0) || Object.values(prior).some((v) => v !== 0)
    return { end, prior, hasData }
  })

  /** D2-3 坏账准备三分类固定行汇总（期初审定 / 期末审定 / 各变动列） */
  const badDebtSummary = computed(() => {
    const keys = ['D2-bd-individual-rows', 'D2-bd-aging-rows', 'D2-bd-customer-rows']
    const acc = {
      priorAudited: 0,
      currentAudited: 0,
      provision: 0,
      reversal: 0,
      writeOff: 0,
      otherIncrease: 0,
      otherDecrease: 0,
    }
    for (const key of keys) {
      const rows = safeParse<Record<string, any>[]>(allResponses.value.get(key)?.remark, [])
      const fixed = (Array.isArray(rows) ? rows : []).find((r) => r?.isFixed)
      if (!fixed) continue
      acc.priorAudited += parseNum(fixed.priorAudited)
      acc.currentAudited += parseNum(fixed.currentAudited)
      acc.provision += parseNum(fixed.currentProvision)
      acc.reversal += parseNum(fixed.currentReversal)
      acc.writeOff += parseNum(fixed.currentWriteOff)
      acc.otherIncrease += parseNum(fixed.currentOtherIncrease)
      acc.otherDecrease += parseNum(fixed.currentOtherDecrease)
    }
    return acc
  })

  // ─── ① 按账龄披露 ──────────────────────────────────────────────────────────

  function cellValue(cellKey: string, autoValue: number): { amount: number; auto: boolean } {
    const manual = overrides.value[cellKey]
    if (manual !== undefined && manual !== null) return { amount: parseNum(manual), auto: false }
    return { amount: autoValue, auto: true }
  }

  const agingRows: ComputedRef<D2AgingDisplayRow[]> = computed(() => {
    const segs = agingSegments.value
    const auto = detailAging.value
    const rows: D2AgingDisplayRow[] = []

    for (const seg of segs) {
      const end = cellValue(`aging:end:${seg.key}`, auto.end[seg.key] ?? 0)
      const prior = cellValue(`aging:prior:${seg.key}`, auto.prior[seg.key] ?? 0)
      rows.push({
        key: seg.key,
        label: seg.label,
        kind: 'segment',
        endAmount: end.amount,
        priorAmount: prior.amount,
        endAuto: end.auto,
        priorAuto: prior.auto,
        editable: true,
        autoSource: '取自 D2-2 明细表账龄（期末审定 / 期初审定）',
      })
    }

    const within1Keys = segs.filter((s) => s.dayFrom < 366).map((s) => s.key)
    const within1End = SUM(rows.filter((r) => within1Keys.includes(r.key)).map((r) => r.endAmount))
    const within1Prior = SUM(rows.filter((r) => within1Keys.includes(r.key)).map((r) => r.priorAmount))
    rows.push({
      key: '__within1_subtotal',
      label: '1年以内小计',
      kind: 'within1Subtotal',
      endAmount: within1End,
      priorAmount: within1Prior,
      endAuto: true,
      priorAuto: true,
      editable: false,
      autoSource: '= 1年以内各账龄段之和',
    })

    const segEnd = SUM(rows.filter((r) => r.kind === 'segment').map((r) => r.endAmount))
    const segPrior = SUM(rows.filter((r) => r.kind === 'segment').map((r) => r.priorAmount))
    rows.push({
      key: '__subtotal',
      label: '小计',
      kind: 'subtotal',
      endAmount: segEnd,
      priorAmount: segPrior,
      endAuto: true,
      priorAuto: true,
      editable: false,
      autoSource: '= 各账龄段之和',
    })

    const bdEnd = cellValue('aging:end:__badDebt', badDebtSummary.value.currentAudited)
    const bdPrior = cellValue('aging:prior:__badDebt', badDebtSummary.value.priorAudited)
    rows.push({
      key: '__badDebt',
      label: '减：坏账准备',
      kind: 'badDebt',
      endAmount: bdEnd.amount,
      priorAmount: bdPrior.amount,
      endAuto: bdEnd.auto,
      priorAuto: bdPrior.auto,
      editable: true,
      autoSource: '取自 D2-3 坏账准备明细表（各分类小计合计）',
    })

    rows.push({
      key: '__total',
      label: '合计',
      kind: 'total',
      endAmount: segEnd - bdEnd.amount,
      priorAmount: segPrior - bdPrior.amount,
      endAuto: true,
      priorAuto: true,
      editable: false,
      autoSource: '= 小计 − 坏账准备',
    })

    return rows
  })

  // ─── ② 按坏账准备计提方法分类披露 ──────────────────────────────────────────

  const classRows: ComputedRef<D2ClassDisplayRow[]> = computed(() => {
    const adj = crossSheet.adjudicationForDisclosure.value
    const rows: D2ClassDisplayRow[] = []

    const indEnd = cellValue('class:end:individual', adj.individual.current)
    const indPrior = cellValue('class:prior:individual', adj.individual.prior)
    rows.push({
      key: 'individual',
      label: '按单项计提坏账准备',
      kind: 'method',
      endAmount: indEnd.amount,
      priorAmount: indPrior.amount,
      editable: true,
      auto: indEnd.auto && indPrior.auto,
      autoSource: '取自 D2-1 审定表（单项计提，期末/期初审定数）',
    })
    rows.push({
      key: 'individual-hint',
      label: '其中：',
      kind: 'hint',
      endAmount: 0,
      priorAmount: 0,
      editable: false,
      auto: false,
      autoSource: '',
    })
    for (const r of individualRows.value) {
      rows.push({
        key: `ind-${r.rowId}`,
        label: r.name || '（未命名）',
        kind: 'detail',
        endAmount: r.endAmount,
        priorAmount: r.priorAmount,
        editable: false,
        auto: false,
        autoSource: '取自本页「按单项计提坏账准备的应收账款」明细',
      })
    }

    const autoPortfolio = adj.aging.current + adj.customerType.current
    const autoPortfolioPrior = adj.aging.prior + adj.customerType.prior
    const pfEnd = cellValue('class:end:portfolio', autoPortfolio)
    const pfPrior = cellValue('class:prior:portfolio', autoPortfolioPrior)
    rows.push({
      key: 'portfolio',
      label: '按组合计提坏账准备',
      kind: 'method',
      endAmount: pfEnd.amount,
      priorAmount: pfPrior.amount,
      editable: true,
      auto: pfEnd.auto && pfPrior.auto,
      autoSource: '取自 D2-1 审定表（账龄组合 + 客户类型组合，期末/期初审定数）',
    })
    rows.push({
      key: 'portfolio-hint',
      label: '其中：',
      kind: 'hint',
      endAmount: 0,
      priorAmount: 0,
      editable: false,
      auto: false,
      autoSource: '',
    })
    for (const g of portfolios.value) {
      rows.push({
        key: `pf-${g.groupId}`,
        label: g.name || '（未命名组合）',
        kind: 'detail',
        endAmount: SUM(g.rows.map((r) => r.endAmount)),
        priorAmount: SUM(g.rows.map((r) => r.priorAmount)),
        editable: false,
        auto: false,
        autoSource: '= 本页对应组合分表各账龄段之和',
      })
    }

    rows.push({
      key: '__total',
      label: '合计',
      kind: 'total',
      endAmount: indEnd.amount + pfEnd.amount,
      priorAmount: indPrior.amount + pfPrior.amount,
      editable: false,
      auto: true,
      autoSource: '= 按单项计提 + 按组合计提',
    })

    return rows
  })

  // ─── ②-SOE 国企 6 列分类宽表（期末数/期初数各一张）───────────────────────
  // 源模板：类别 | 账面金额 | 比例(%) | 坏账准备 | 预期信用损失率(%) | 账面价值

  function buildSoeClassWideRows(period: 'current' | 'prior'): D2SoeClassWideRow[] {
    const adj = crossSheet.adjudicationForDisclosure.value
    const bd = crossSheet.badDebtByCategory.value

    const categories: Array<{ key: string; label: string }> = [
      { key: 'individual', label: '按单项计提坏账准备' },
      { key: 'aging', label: '按账龄组合计提坏账准备' },
      { key: 'customerType', label: '按客户类型组合计提坏账准备' },
    ]

    const rows: D2SoeClassWideRow[] = []
    let totalBook = 0
    let totalProvision = 0

    for (const cat of categories) {
      const adjCat = adj[cat.key as keyof typeof adj] as { prior: number; current: number }
      const bdCat = bd[cat.key as keyof typeof bd] as { prior: number; current: number }

      const book = cellValue(`soeClass:${period}:${cat.key}:book`, period === 'current' ? adjCat.current : adjCat.prior).amount
      const prov = cellValue(`soeClass:${period}:${cat.key}:prov`, period === 'current' ? bdCat.current : bdCat.prior).amount

      totalBook += book
      totalProvision += prov

      rows.push({
        key: cat.key,
        label: cat.label,
        kind: 'category',
        bookAmount: book,
        ratio: 0, // 后填
        provision: prov,
        lossRate: book !== 0 ? (prov / book) * 100 : 0,
        carryingValue: book - prov,
        editable: true,
        autoSource: `取自 D2-1 审定表（${cat.label}，${period === 'current' ? '期末' : '期初'}审定数）+ D2-3 坏账准备`,
      })

      // 「其中：」子行——单项计提展开每个债务人，组合计提展开每个组合名
      if (cat.key === 'individual' && individualRows.value.length > 0) {
        for (const r of individualRows.value) {
          const subBook = period === 'current' ? r.endAmount : r.priorAmount
          const subProv = period === 'current' ? r.provision : 0
          rows.push({
            key: `ind-${r.rowId}`,
            label: `  其中：${r.name || '（未命名）'}`,
            kind: 'subtotal',
            bookAmount: subBook,
            ratio: 0,
            provision: subProv,
            lossRate: subBook !== 0 ? (subProv / subBook) * 100 : 0,
            carryingValue: subBook - subProv,
            editable: false,
            autoSource: '取自本页「按单项计提坏账准备的应收账款」明细',
          })
        }
      }
      if ((cat.key === 'aging' || cat.key === 'customerType') && portfolios.value.length > 0) {
        // 按组合计提行后展开各组合分表名称及汇总金额
        for (const g of portfolios.value) {
          const pfBook = SUM(g.rows.map((r) => period === 'current' ? r.endAmount : r.priorAmount))
          rows.push({
            key: `pf-${g.groupId}`,
            label: `  其中：${g.name || '（未命名组合）'}`,
            kind: 'subtotal',
            bookAmount: pfBook,
            ratio: 0,
            provision: 0, // 组合分表未单独存坏账准备
            lossRate: 0,
            carryingValue: pfBook,
            editable: false,
            autoSource: '= 对应组合分表各账龄段之和',
          })
        }
        // 只在第一个组合类别行（aging）后展开，避免 customerType 重复
        if (cat.key === 'customerType') {
          // customerType 无独立组合分表子行
        }
      }
    }

    // 回填比例（只对 category 行填比例，subtotal 行按其 bookAmount/totalBook 填）
    for (const r of rows) {
      if (r.kind === 'total') continue
      r.ratio = totalBook !== 0 ? (r.bookAmount / totalBook) * 100 : 0
    }

    rows.push({
      key: '__total',
      label: '合计',
      kind: 'total',
      bookAmount: totalBook,
      ratio: 100,
      provision: totalProvision,
      lossRate: totalBook !== 0 ? (totalProvision / totalBook) * 100 : 0,
      carryingValue: totalBook - totalProvision,
      editable: false,
      autoSource: '= 各类别之和',
    })

    return rows
  }

  /** 国企版分类宽表——期末数 */
  const soeClassEndRows: ComputedRef<D2SoeClassWideRow[]> = computed(() => buildSoeClassWideRows('current'))
  /** 国企版分类宽表——期初数 */
  const soeClassPriorRows: ComputedRef<D2SoeClassWideRow[]> = computed(() => buildSoeClassWideRows('prior'))

  // ─── ⑤ 坏账准备变动（上市纵向 7 行）───────────────────────────────────────

  const MOVEMENT_LABELS: Array<{ key: keyof D2MovementValues; label: string; autoSource: string }> = [
    { key: 'priorBalance', label: '期初余额', autoSource: '取自 D2-3 坏账准备明细表（期初审定合计）' },
    { key: 'provision', label: '本期计提', autoSource: '取自 D2-3（本期计提合计）' },
    { key: 'reversal', label: '本期收回或转回', autoSource: '取自 D2-3（本期转回合计）' },
    { key: 'writeOff', label: '本期核销', autoSource: '取自 D2-3（本期核销合计）' },
    { key: 'transfer', label: '本期转销', autoSource: '' },
    { key: 'other', label: '其他', autoSource: '取自 D2-3（其他增加 − 其他减少）' },
  ]

  const movementFields: ComputedRef<D2MovementField[]> = computed(() => {
    const bd = badDebtSummary.value
    const autoMap: Record<keyof D2MovementValues, number> = {
      priorBalance: bd.priorAudited,
      provision: bd.provision,
      reversal: bd.reversal,
      writeOff: bd.writeOff,
      transfer: 0,
      other: bd.otherIncrease - bd.otherDecrease,
    }
    return MOVEMENT_LABELS.map(({ key, label, autoSource }) => {
      const cell = cellValue(`movement:${key}`, autoMap[key])
      return {
        key,
        label,
        amount: cell.amount,
        editable: true,
        auto: cell.auto && Boolean(autoSource),
        autoSource,
      }
    })
  })

  const movementValues: ComputedRef<D2MovementValues> = computed(() => {
    const out = {} as D2MovementValues
    for (const f of movementFields.value) out[f.key] = f.amount
    return out
  })

  /** 期末余额 = 期初 + 计提 − 转回 − 核销 − 转销 + 其他 */
  const movementEndBalance: ComputedRef<number> = computed(() => {
    const m = movementValues.value
    return m.priorBalance + m.provision - m.reversal - m.writeOff - m.transfer + m.other
  })

  // ─── ⑤(国企) 按类别的坏账准备变动 ─────────────────────────────────────────

  const movementByCategory: ComputedRef<D2MovementCategoryRow[]> = computed(() => {
    // 从 D2-3 各分类坏账准备明细表取逐列变动（isFixed 合计行）
    const catKeys: Array<{ key: 'individual' | 'aging' | 'customerType'; label: string; jsonKey: string }> = [
      { key: 'individual', label: '按单项计提坏账准备', jsonKey: 'D2-bd-individual-rows' },
      { key: 'aging', label: '按账龄组合计提坏账准备', jsonKey: 'D2-bd-aging-rows' },
      { key: 'customerType', label: '按客户类型组合计提坏账准备', jsonKey: 'D2-bd-customer-rows' },
    ]

    const rows: D2MovementCategoryRow[] = catKeys.map(({ key, label, jsonKey }) => {
      const catRows = safeParse<Record<string, any>[]>(allResponses.value.get(jsonKey)?.remark, [])
      const fixed = (Array.isArray(catRows) ? catRows : []).find((r) => r?.isFixed)

      const prior = parseNum(fixed?.priorAudited)
      const prov = parseNum(fixed?.currentProvision)
      const rev = parseNum(fixed?.currentReversal)
      const wo = parseNum(fixed?.currentWriteOff)
      const end = parseNum(fixed?.currentAudited)

      return {
        key,
        label,
        priorAmount: cellValue(`movementCat:prior:${key}`, prior).amount,
        provisionAmount: cellValue(`movementCat:provision:${key}`, prov).amount,
        reversalAmount: cellValue(`movementCat:reversal:${key}`, rev).amount,
        writeOffAmount: cellValue(`movementCat:writeoff:${key}`, wo).amount,
        endAmount: cellValue(`movementCat:end:${key}`, end).amount,
        auto: true,
        autoSource: '取自 D2-3 坏账准备明细表（对应分类小计的逐列变动数）',
      }
    })
    rows.push({
      key: '__total',
      label: '合计',
      priorAmount: SUM(rows.map((r) => r.priorAmount)),
      provisionAmount: SUM(rows.map((r) => r.provisionAmount)),
      reversalAmount: SUM(rows.map((r) => r.reversalAmount)),
      writeOffAmount: SUM(rows.map((r) => r.writeOffAmount)),
      endAmount: SUM(rows.map((r) => r.endAmount)),
      auto: true,
      autoSource: '= 各类别之和',
      isTotal: true,
    })
    return rows
  })

  // ─── ⑦ 核销金额（单一金额）────────────────────────────────────────────────

  const writeOffAmountCell = computed(() => cellValue('writeoff:amount', badDebtSummary.value.writeOff))

  // ─── 编辑 API ─────────────────────────────────────────────────────────────

  function setOverride(cellKey: string, value: number | null): void {
    if (isReadonly.value) return
    const next = { ...overrides.value }
    if (value === null) delete next[cellKey]
    else next[cellKey] = parseNum(value)
    overrides.value = next
    persistJson('overrides', next)
  }

  function resetOverride(cellKey: string): void {
    setOverride(cellKey, null)
  }

  // 单项计提明细
  function addIndividualRow(): void {
    if (isReadonly.value) return
    individualRows.value = [
      ...individualRows.value,
      { rowId: genId('ind'), name: '', endAmount: 0, priorAmount: 0, provision: 0, aging: '', lossRate: 0, basis: '' },
    ]
    persistJson('individual-rows', individualRows.value)
  }
  function removeIndividualRow(rowId: string): void {
    if (isReadonly.value) return
    individualRows.value = individualRows.value.filter((r) => r.rowId !== rowId)
    persistJson('individual-rows', individualRows.value)
  }
  function updateIndividualRow(rowId: string, field: keyof D2IndividualRow, value: string | number): void {
    if (isReadonly.value) return
    individualRows.value = individualRows.value.map((r) => {
      if (r.rowId !== rowId) return r
      const isText = field === 'name' || field === 'aging' || field === 'basis'
      return { ...r, [field]: isText ? String(value ?? '') : parseNum(value) }
    })
    persistJson('individual-rows', individualRows.value)
  }

  /** 从 D2-3「按单项计提」子行带入（名称 + 期末/期初坏账准备），仅填充空白行不覆盖已录入 */
  function importIndividualFromBadDebt(): number {
    if (isReadonly.value) return 0
    const rows = safeParse<Record<string, any>[]>(allResponses.value.get('D2-bd-individual-rows')?.remark, [])
    const subRows = (Array.isArray(rows) ? rows : []).filter((r) => r?.isSubRow && String(r.label ?? '').trim())
    if (subRows.length === 0) return 0
    const existing = new Set(individualRows.value.map((r) => r.name.trim()).filter(Boolean))
    const added: D2IndividualRow[] = []
    for (const raw of subRows) {
      const name = String(raw.label).trim()
      if (existing.has(name)) continue
      added.push({
        rowId: genId('ind'),
        name,
        endAmount: 0,
        priorAmount: 0,
        provision: parseNum(raw.currentAudited),
        aging: '',
        lossRate: 0,
        basis: '',
      })
      existing.add(name)
    }
    if (added.length === 0) return 0
    individualRows.value = [...individualRows.value, ...added]
    persistJson('individual-rows', individualRows.value)
    return added.length
  }

  // 组合计提分表
  function buildPortfolioRows(): D2PortfolioRow[] {
    return agingSegments.value.map((seg) => ({ key: seg.key, label: seg.label, endAmount: 0, priorAmount: 0, provision: 0 }))
  }
  function addPortfolio(name: string): void {
    if (isReadonly.value) return
    portfolios.value = [...portfolios.value, { groupId: genId('pf'), name: name.trim(), rows: buildPortfolioRows() }]
    persistJson('portfolios', portfolios.value)
  }
  function renamePortfolio(groupId: string, name: string): void {
    if (isReadonly.value) return
    portfolios.value = portfolios.value.map((g) => (g.groupId === groupId ? { ...g, name: String(name ?? '').trim() } : g))
    persistJson('portfolios', portfolios.value)
  }
  function removePortfolio(groupId: string): void {
    if (isReadonly.value) return
    portfolios.value = portfolios.value.filter((g) => g.groupId !== groupId)
    persistJson('portfolios', portfolios.value)
  }
  function updatePortfolioCell(groupId: string, rowKey: string, field: 'endAmount' | 'priorAmount' | 'provision', value: number): void {
    if (isReadonly.value) return
    portfolios.value = portfolios.value.map((g) => {
      if (g.groupId !== groupId) return g
      return { ...g, rows: g.rows.map((r) => (r.key === rowKey ? { ...r, [field]: parseNum(value) } : r)) }
    })
    persistJson('portfolios', portfolios.value)
  }
  /** 账龄配置变化后，为已有组合补齐新增账龄段（保留同 key 金额，移除已废弃段） */
  watch(agingSegments, (segs) => {
    if (portfolios.value.length === 0 || segs.length === 0) return
    let changed = false
    const next = portfolios.value.map((g) => {
      const rows = segs.map((seg) => {
        const old = g.rows.find((r) => r.key === seg.key)
        if (!old) {
          changed = true
          return { key: seg.key, label: seg.label, endAmount: 0, priorAmount: 0, provision: 0 }
        }
        if (old.label !== seg.label) changed = true
        return { ...old, label: seg.label }
      })
      if (rows.length !== g.rows.length) changed = true
      return { ...g, rows }
    })
    if (changed) {
      portfolios.value = next
      persistJson('portfolios', next)
    }
  })

  // 国企：其他组合方法
  function addOtherPortfolioRow(): void {
    if (isReadonly.value) return
    otherPortfolioRows.value = [...otherPortfolioRows.value, { rowId: genId('op'), name: '', endAmount: 0, priorAmount: 0 }]
    persistJson('other-portfolio-rows', otherPortfolioRows.value)
  }
  function removeOtherPortfolioRow(rowId: string): void {
    if (isReadonly.value) return
    otherPortfolioRows.value = otherPortfolioRows.value.filter((r) => r.rowId !== rowId)
    persistJson('other-portfolio-rows', otherPortfolioRows.value)
  }
  function updateOtherPortfolioRow(rowId: string, field: keyof D2TwoPeriodManualRow, value: string | number): void {
    if (isReadonly.value) return
    otherPortfolioRows.value = otherPortfolioRows.value.map((r) =>
      r.rowId === rowId ? { ...r, [field]: field === 'name' ? String(value ?? '') : parseNum(value) } : r,
    )
    persistJson('other-portfolio-rows', otherPortfolioRows.value)
  }

  // ⑥ 转回或收回
  function addReversalRow(): void {
    if (isReadonly.value) return
    reversalRows.value = [
      ...reversalRows.value,
      { rowId: genId('rv'), companyName: '', reversalReason: '', recoveryMethod: '', originalBasis: '', cumulativeProvision: 0, amount: 0 },
    ]
    persistJson('reversal-rows', reversalRows.value)
  }
  function removeReversalRow(rowId: string): void {
    if (isReadonly.value) return
    reversalRows.value = reversalRows.value.filter((r) => r.rowId !== rowId)
    persistJson('reversal-rows', reversalRows.value)
  }
  function updateReversalRow(rowId: string, field: keyof D2ReversalRow, value: string | number): void {
    if (isReadonly.value) return
    reversalRows.value = reversalRows.value.map((r) => {
      if (r.rowId !== rowId) return r
      const isNum = field === 'amount' || field === 'cumulativeProvision'
      return { ...r, [field]: isNum ? parseNum(value) : String(value ?? '') }
    })
    persistJson('reversal-rows', reversalRows.value)
  }
  /** 从 D2-11 转回明细带入（单位名称/转回原因/金额；收回方式与原依据无数据源需手工） */
  function importReversalFromWriteoffCheck(): number {
    if (isReadonly.value) return 0
    const rows = safeParse<Record<string, any>[]>(allResponses.value.get('D2-writeoff-reversal-rows')?.remark, [])
    const source = (Array.isArray(rows) ? rows : []).filter((r) => String(r?.debtorName ?? '').trim() || parseNum(r?.amount))
    if (source.length === 0) return 0
    const existing = new Set(reversalRows.value.map((r) => r.companyName.trim()).filter(Boolean))
    const added: D2ReversalRow[] = []
    for (const raw of source) {
      const name = String(raw.debtorName ?? '').trim()
      if (name && existing.has(name)) continue
      added.push({
        rowId: genId('rv'),
        companyName: name,
        reversalReason: String(raw.reason ?? ''),
        recoveryMethod: '',
        originalBasis: '',
        cumulativeProvision: 0,
        amount: parseNum(raw.amount),
      })
      if (name) existing.add(name)
    }
    if (added.length === 0) return 0
    reversalRows.value = [...reversalRows.value, ...added]
    persistJson('reversal-rows', reversalRows.value)
    return added.length
  }

  // ⑦ 核销
  function setWriteOffAmount(value: number | null): void {
    setOverride('writeoff:amount', value)
  }
  function addWriteOffRow(): void {
    if (isReadonly.value) return
    writeOffRows.value = [
      ...writeOffRows.value,
      { rowId: genId('wo'), companyName: '', nature: '', amount: 0, reason: '', procedure: '', relatedParty: '' },
    ]
    persistJson('writeoff-rows', writeOffRows.value)
  }
  function removeWriteOffRow(rowId: string): void {
    if (isReadonly.value) return
    writeOffRows.value = writeOffRows.value.filter((r) => r.rowId !== rowId)
    persistJson('writeoff-rows', writeOffRows.value)
  }
  function updateWriteOffRow(rowId: string, field: keyof D2WriteOffRow, value: string | number): void {
    if (isReadonly.value) return
    writeOffRows.value = writeOffRows.value.map((r) =>
      r.rowId === rowId ? { ...r, [field]: field === 'amount' ? parseNum(value) : String(value ?? '') } : r,
    )
    persistJson('writeoff-rows', writeOffRows.value)
  }
  /** 从 D2-11 核销明细带入（单位名称/核销金额/核销原因；性质、程序、关联交易需手工） */
  function importWriteOffFromWriteoffCheck(): number {
    if (isReadonly.value) return 0
    const rows = safeParse<Record<string, any>[]>(allResponses.value.get('D2-writeoff-writeoff-rows')?.remark, [])
    const source = (Array.isArray(rows) ? rows : []).filter((r) => String(r?.debtorName ?? '').trim() || parseNum(r?.amount))
    if (source.length === 0) return 0
    const existing = new Set(writeOffRows.value.map((r) => r.companyName.trim()).filter(Boolean))
    const added: D2WriteOffRow[] = []
    for (const raw of source) {
      const name = String(raw.debtorName ?? '').trim()
      if (name && existing.has(name)) continue
      added.push({
        rowId: genId('wo'),
        companyName: name,
        nature: '',
        amount: parseNum(raw.amount),
        reason: String(raw.reason ?? ''),
        procedure: '',
        relatedParty: '',
      })
      if (name) existing.add(name)
    }
    if (added.length === 0) return 0
    writeOffRows.value = [...writeOffRows.value, ...added]
    persistJson('writeoff-rows', writeOffRows.value)
    return added.length
  }

  // ⑧ 前五名
  const top5Total = computed(() => crossSheet.adjudicationForDisclosure.value.total.current)

  function top5Ratio(row: D2Top5Row): number {
    const base = top5Total.value
    if (!base) return 0
    return ((row.arAmount + row.contractAssetAmount) / base) * 100
  }

  function addTop5Row(): void {
    if (isReadonly.value) return
    top5Rows.value = [
      ...top5Rows.value,
      { rowId: genId('t5'), companyName: '', arAmount: 0, contractAssetAmount: 0, provision: 0 },
    ]
    persistJson('top5-rows', top5Rows.value)
  }
  function removeTop5Row(rowId: string): void {
    if (isReadonly.value) return
    top5Rows.value = top5Rows.value.filter((r) => r.rowId !== rowId)
    persistJson('top5-rows', top5Rows.value)
  }
  function updateTop5Row(rowId: string, field: keyof D2Top5Row, value: string | number): void {
    if (isReadonly.value) return
    top5Rows.value = top5Rows.value.map((r) =>
      r.rowId === rowId ? { ...r, [field]: field === 'companyName' ? String(value ?? '') : parseNum(value) } : r,
    )
    persistJson('top5-rows', top5Rows.value)
  }
  /** 从 D2-5 分析表「期末前十名」带入前 5 名（单位名称 + 期末余额；合同资产与减值准备需手工） */
  function importTop5FromAnalysis(): number {
    if (isReadonly.value) return 0
    const rows = safeParse<Record<string, any>[]>(allResponses.value.get('D2-analysis-top10')?.remark, [])
    const source = (Array.isArray(rows) ? rows : [])
      .filter((r) => String(r?.customerName ?? '').trim())
      .sort((a, b) => parseNum(b?.endBalance) - parseNum(a?.endBalance))
      .slice(0, 5)
    if (source.length === 0) return 0
    const existing = new Set(top5Rows.value.map((r) => r.companyName.trim()).filter(Boolean))
    const added: D2Top5Row[] = []
    for (const raw of source) {
      const name = String(raw.customerName).trim()
      if (existing.has(name)) continue
      added.push({
        rowId: genId('t5'),
        companyName: name,
        arAmount: parseNum(raw.endBalance),
        contractAssetAmount: 0,
        provision: 0,
      })
      existing.add(name)
    }
    if (added.length === 0) return 0
    top5Rows.value = [...top5Rows.value, ...added]
    persistJson('top5-rows', top5Rows.value)
    return added.length
  }

  // ⑨ 国企：终止确认
  function addDerecognizedRow(): void {
    if (isReadonly.value) return
    derecognizedRows.value = [...derecognizedRows.value, { rowId: genId('dr'), companyName: '', amount: 0, gainLoss: 0 }]
    persistJson('derecognized-rows', derecognizedRows.value)
  }
  function removeDerecognizedRow(rowId: string): void {
    if (isReadonly.value) return
    derecognizedRows.value = derecognizedRows.value.filter((r) => r.rowId !== rowId)
    persistJson('derecognized-rows', derecognizedRows.value)
  }
  function updateDerecognizedRow(rowId: string, field: keyof D2DerecognizedRow, value: string | number): void {
    if (isReadonly.value) return
    derecognizedRows.value = derecognizedRows.value.map((r) =>
      r.rowId === rowId ? { ...r, [field]: field === 'companyName' ? String(value ?? '') : parseNum(value) } : r,
    )
    persistJson('derecognized-rows', derecognizedRows.value)
  }

  // ─── ⑦ 继续涉入 ───────────────────────────────────────────────────────────
  function addContinuedInvolvementRow(): void {
    if (isReadonly.value) return
    continuedInvolvementRows.value = [...continuedInvolvementRows.value, { rowId: genId('ci'), item: '', transferMethod: '', assetAmount: 0, liabilityAmount: 0 }]
    persistJson('continued-involvement-rows', continuedInvolvementRows.value)
  }
  function removeContinuedInvolvementRow(rowId: string): void {
    if (isReadonly.value) return
    continuedInvolvementRows.value = continuedInvolvementRows.value.filter((r) => r.rowId !== rowId)
    persistJson('continued-involvement-rows', continuedInvolvementRows.value)
  }
  function updateContinuedInvolvementRow(rowId: string, field: keyof D2ContinuedInvolvementRow, value: string | number): void {
    if (isReadonly.value) return
    continuedInvolvementRows.value = continuedInvolvementRows.value.map((r) =>
      r.rowId === rowId ? { ...r, [field]: (field === 'item' || field === 'transferMethod') ? String(value ?? '') : parseNum(value) } : r,
    )
    persistJson('continued-involvement-rows', continuedInvolvementRows.value)
  }

  // ─── 旧版披露数据（D2-disclosure-*）兼容带入 ───────────────────────────────
  //  - top5 区块 → 前五名（单位名称/期末余额/坏账准备）
  //  - aging-detail 区块 → 账龄段期末覆盖值（按段标签匹配，匹配不上的丢弃不臆造）
  // 分类/款项性质区块行是自由文本行，无法映射到模板固定分类，一律不迁移（提示审计师自行核对）。

  const LEGACY_VERSIONS = ['listed-d2-1', 'soe-d2-1', 'listed-aging', 'soe-aging'] as const

  interface LegacyRow { label?: string; amount?: unknown; badDebt?: unknown }

  function readLegacySections(): Record<string, LegacyRow[]> {
    const merged: Record<string, LegacyRow[]> = {}
    for (const v of LEGACY_VERSIONS) {
      const raw = allResponses.value.get(`D2-disclosure-${v}`)?.remark
      if (!raw) continue
      let parsed: unknown
      try {
        parsed = JSON.parse(raw)
      } catch {
        continue
      }
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) continue
      for (const [sectionId, rows] of Object.entries(parsed as Record<string, unknown>)) {
        if (!Array.isArray(rows) || rows.length === 0) continue
        const meaningful = (rows as LegacyRow[]).filter(
          (r) => String(r?.label ?? '').trim() || parseNum(r?.amount) || parseNum(r?.badDebt),
        )
        if (meaningful.length === 0) continue
        merged[sectionId] = [...(merged[sectionId] ?? []), ...meaningful]
      }
    }
    return merged
  }

  /** 归一化账龄标签用于匹配旧数据（「一年以内」↔「1年以内」、到/至、全角括号差异） */
  function normalizeAgingLabel(label: string): string {
    return String(label ?? '')
      .replace(/[（）()\s]/g, '')
      .replace(/[一二三四五六七八九十]/g, (ch) => String('一二三四五六七八九十'.indexOf(ch) + 1))
      .replace(/[到至]/g, '-')
      .replace(/年以上/g, '年+')
  }

  /** 旧版披露数据概览（供 UI 提示，非零才提示） */
  const legacyDisclosureInfo: ComputedRef<{ top5: number; aging: number; unmapped: string[] }> = computed(() => {
    const sections = readLegacySections()
    const unmapped: string[] = []
    for (const key of Object.keys(sections)) {
      if (key !== 'top5' && key !== 'aging-detail') unmapped.push(key)
    }
    return {
      top5: sections['top5']?.length ?? 0,
      aging: sections['aging-detail']?.length ?? 0,
      unmapped,
    }
  })

  /**
   * 一键带入旧版披露数据的可映射部分。仅补空：
   * 前五名按单位名称去重后追加；账龄期末仅在该段尚无手工覆盖值时写入覆盖值。
   * 返回 { top5, aging } 实际带入条数。
   */
  function importFromLegacyDisclosure(): { top5: number; aging: number } {
    if (isReadonly.value) return { top5: 0, aging: 0 }
    const sections = readLegacySections()
    let top5Added = 0
    let agingAdded = 0

    const legacyTop5 = sections['top5'] ?? []
    if (legacyTop5.length > 0) {
      const existing = new Set(top5Rows.value.map((r) => r.companyName.trim()).filter(Boolean))
      const added: D2Top5Row[] = []
      for (const raw of legacyTop5) {
        const name = String(raw?.label ?? '').trim()
        if (!name || existing.has(name)) continue
        added.push({
          rowId: genId('t5'),
          companyName: name,
          arAmount: parseNum(raw?.amount),
          contractAssetAmount: 0,
          provision: parseNum(raw?.badDebt),
        })
        existing.add(name)
      }
      if (added.length > 0) {
        top5Rows.value = [...top5Rows.value, ...added]
        persistJson('top5-rows', top5Rows.value)
        top5Added = added.length
      }
    }

    const legacyAging = sections['aging-detail'] ?? []
    if (legacyAging.length > 0) {
      const next = { ...overrides.value }
      for (const seg of agingSegments.value) {
        const cellKey = `aging:end:${seg.key}`
        if (next[cellKey] !== undefined && next[cellKey] !== null) continue // 已有手工覆盖，不动
        const target = normalizeAgingLabel(seg.label)
        const hit = legacyAging.find((r) => {
          const label = normalizeAgingLabel(String(r?.label ?? ''))
          return Boolean(label) && (label.includes(target) || target.includes(label))
        })
        if (!hit) continue
        const amount = parseNum(hit.amount)
        if (!amount) continue
        next[cellKey] = amount
        agingAdded += 1
      }
      if (agingAdded > 0) {
        overrides.value = next
        persistJson('overrides', next)
      }
    }

    return { top5: top5Added, aging: agingAdded }
  }

  // 说明文本
  function setNote(key: string, value: string): void {
    if (isReadonly.value) return
    sectionNotes.value = { ...sectionNotes.value, [key]: value }
    persist(`note-${key}`, value)
  }

  // ─── 不一致告警（披露合计 vs D2-1 审定表 / D2-3 坏账表）────────────────────

  const inconsistencyWarnings: ComputedRef<string[]> = computed(() => {
    const out: string[] = []
    const adjTotal = crossSheet.adjudicationForDisclosure.value.total.current
    const bdTotal = badDebtSummary.value.currentAudited
    const fmt = (v: number) => v.toFixed(2)

    const agingSubtotal = agingRows.value.find((r) => r.kind === 'subtotal')?.endAmount ?? 0
    if (adjTotal !== 0 && Math.abs(agingSubtotal - adjTotal) > 0.01) {
      out.push(`按账龄披露小计(${fmt(agingSubtotal)}) 与 D2-1 审定表期末审定合计(${fmt(adjTotal)}) 不一致`)
    }

    const classTotal = classRows.value.find((r) => r.kind === 'total')?.endAmount ?? 0
    if (adjTotal !== 0 && Math.abs(classTotal - adjTotal) > 0.01) {
      out.push(`按计提方法分类合计(${fmt(classTotal)}) 与 D2-1 审定表期末审定合计(${fmt(adjTotal)}) 不一致`)
    }

    const disclosedBadDebt = agingRows.value.find((r) => r.kind === 'badDebt')?.endAmount ?? 0
    if (bdTotal !== 0 && Math.abs(disclosedBadDebt - bdTotal) > 0.01) {
      out.push(`披露坏账准备(${fmt(disclosedBadDebt)}) 与 D2-3 坏账准备表期末审定合计(${fmt(bdTotal)}) 不一致`)
    }

    const mvEnd = isSoe
      ? (movementByCategory.value.find((r) => r.isTotal)?.endAmount ?? 0)
      : movementEndBalance.value
    if (bdTotal !== 0 && Math.abs(mvEnd - bdTotal) > 0.01) {
      out.push(`坏账准备变动表期末余额(${fmt(mvEnd)}) 与 D2-3 坏账准备表期末审定合计(${fmt(bdTotal)}) 不一致`)
    }

    return out
  })

  // ─── 同步快照（喂 buildD2SyncPayload）───────────────────────────────────────

  function buildSnapshot(): D2DisclosureSnapshot {
    const m = movementValues.value
    return {
      agingRows: agingRows.value.map((r) => ({
        label: r.label,
        endAmount: r.endAmount,
        priorAmount: r.priorAmount,
        isTotal: r.kind === 'total',
      })),
      classRows: classRows.value.map((r) => ({
        label: r.label,
        endAmount: r.endAmount,
        priorAmount: r.priorAmount,
        isTotal: r.kind === 'total',
      })),
      soeClassEndRows: isSoe
        ? soeClassEndRows.value.map((r) => ({
            label: r.label,
            bookAmount: r.bookAmount,
            ratio: r.ratio,
            provision: r.provision,
            lossRate: r.lossRate,
            carryingValue: r.carryingValue,
            isTotal: r.kind === 'total',
          }))
        : undefined,
      soeClassPriorRows: isSoe
        ? soeClassPriorRows.value.map((r) => ({
            label: r.label,
            bookAmount: r.bookAmount,
            ratio: r.ratio,
            provision: r.provision,
            lossRate: r.lossRate,
            carryingValue: r.carryingValue,
            isTotal: r.kind === 'total',
          }))
        : undefined,
      individualRows: individualRows.value.map((r) => ({
        name: r.name,
        endAmount: r.endAmount,
        priorAmount: r.priorAmount,
        provision: r.provision,
        aging: r.aging,
        lossRate: r.lossRate,
        basis: r.basis,
      })),
      portfolios: portfolios.value.map((g) => ({
        name: g.name,
        groupId: g.groupId,
        rows: g.rows.map((r) => ({ label: r.label, endAmount: r.endAmount, priorAmount: r.priorAmount })),
      })),
      otherPortfolioRows: otherPortfolioRows.value.map((r) => ({
        label: r.name,
        endAmount: r.endAmount,
        priorAmount: r.priorAmount,
      })),
      movement: {
        priorBalance: m.priorBalance,
        provision: m.provision,
        reversal: m.reversal,
        writeOff: m.writeOff,
        transfer: m.transfer,
        other: m.other,
        endBalance: movementEndBalance.value,
      },
      movementByCategory: movementByCategory.value.map((r) => ({
        label: r.label,
        priorAmount: r.priorAmount,
        provisionAmount: r.provisionAmount,
        reversalAmount: r.reversalAmount,
        writeOffAmount: r.writeOffAmount,
        endAmount: r.endAmount,
        isTotal: r.isTotal,
      })),
      reversalRows: reversalRows.value.map((r) => ({
        companyName: r.companyName,
        reversalReason: r.reversalReason,
        recoveryMethod: r.recoveryMethod,
        originalBasis: r.originalBasis,
        cumulativeProvision: r.cumulativeProvision,
        amount: r.amount,
      })),
      writeOffAmount: writeOffAmountCell.value.amount,
      writeOffRows: writeOffRows.value.map((r) => ({
        companyName: r.companyName,
        nature: r.nature,
        amount: r.amount,
        reason: r.reason,
        procedure: r.procedure,
        relatedParty: r.relatedParty,
      })),
      top5Rows: top5Rows.value.map((r) => ({
        companyName: r.companyName,
        arAmount: r.arAmount,
        contractAssetAmount: r.contractAssetAmount,
        ratio: top5Ratio(r),
        provision: r.provision,
      })),
      derecognizedRows: derecognizedRows.value.map((r) => ({
        companyName: r.companyName,
        amount: r.amount,
        gainLoss: r.gainLoss,
      })),
      notes: { ...sectionNotes.value },
    }
  }

  return {
    variant,
    isSoe,
    agingSegments,
    // ① 账龄
    agingRows,
    detailAgingHasData: computed(() => detailAging.value.hasData),
    // ② 分类
    classRows,
    soeClassEndRows,
    soeClassPriorRows,
    // ③ 单项
    individualRows,
    addIndividualRow,
    removeIndividualRow,
    updateIndividualRow,
    importIndividualFromBadDebt,
    // ④ 组合
    portfolios,
    addPortfolio,
    renamePortfolio,
    removePortfolio,
    updatePortfolioCell,
    otherPortfolioRows,
    addOtherPortfolioRow,
    removeOtherPortfolioRow,
    updateOtherPortfolioRow,
    // ⑤ 变动
    movementFields,
    movementValues,
    movementEndBalance,
    movementByCategory,
    // ⑥ 转回
    reversalRows,
    addReversalRow,
    removeReversalRow,
    updateReversalRow,
    importReversalFromWriteoffCheck,
    // ⑦ 核销
    writeOffAmountCell,
    setWriteOffAmount,
    writeOffRows,
    addWriteOffRow,
    removeWriteOffRow,
    updateWriteOffRow,
    importWriteOffFromWriteoffCheck,
    // ⑧ 前五名
    top5Rows,
    top5Total,
    top5Ratio,
    addTop5Row,
    removeTop5Row,
    updateTop5Row,
    importTop5FromAnalysis,
    // ⑨ 终止确认（国企）
    derecognizedRows,
    addDerecognizedRow,
    removeDerecognizedRow,
    updateDerecognizedRow,
    // ⑦ 继续涉入
    continuedInvolvementRows,
    addContinuedInvolvementRow,
    removeContinuedInvolvementRow,
    updateContinuedInvolvementRow,
    // 说明 / 覆盖 / 告警 / 同步
    sectionNotes,
    setNote,
    setOverride,
    resetOverride,
    inconsistencyWarnings,
    buildSnapshot,
    badDebtSummary,
    // 旧版披露数据兼容
    legacyDisclosureInfo,
    importFromLegacyDisclosure,
    /**
     * 强制从 allResponses 重新读取（Excel 导入直接写库后调用）。
     * 与 watch 里的自动 hydrate 不同：此处不受 localIsEmpty 守卫限制。
     */
    rehydrate: hydrate,
  }
}

export default useD2DisclosureNote
