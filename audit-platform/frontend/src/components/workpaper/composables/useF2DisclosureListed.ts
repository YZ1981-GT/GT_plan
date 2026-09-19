/**
 * useF2DisclosureListed — F2 附注披露（上市）
 * 对齐源模板「附注披露信息（上市公司）」与 F2ListedSyncSnapshot
 * Spec: .kiro/specs/f2-inventory-main/ Task 15.5
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal, calcNetValue, calcAuditedEnd } from './useF2InvMaiFormulaEngine'
import type { ChecklistResponse } from './useF2FormData'
import { isF2DisclosureApplicable } from './f2NoteSectionMap'
import type { F2ListedS3Mode, F2ListedSyncSnapshot } from './f2DisclosureSyncPayload'
import {
  buildDataResourceRows,
  buildDataResourceSyncRows,
  buildDataResourceTieChecks,
  deriveDataResourceClassRow,
  isDataResourceEmpty,
  setDrCell,
  type DrClassLinkage,
  type DrColKey,
  type DrValueMap,
} from './f2DataResourceInventory'

/**
 * Excel 上市披露分类行（多源科目合并取数）。
 *
 * 🔴 `sourceKeys` 的并集必须覆盖 `f2AccountModel.F2_ROW_KEY_ACCOUNT` 的全部非跌价
 * rowKey，否则该科目的审定数在披露表**没有落点**（合计 ≠ F2-1 审定合计，附注也拿不到）。
 * Sprint 8 前漏了 `dev-costs`(1409) / `dev-products`(1408) / `price-difference`(1412)
 * —— 房地产开发企业与商业零售企业的存货审定数在上市披露里直接丢失。
 * 守卫：`useF2DisclosureListed.spec.ts` 的「sourceKeys 并集 ⊇ 审定表 rowKey 全集」。
 *
 * 行序对齐国企版的语义归属：「开发成本」属在建/在产（紧随在产品）、
 * 「开发产品」属产成品（紧随库存商品）。源模板注（上市 r20）要求
 * 「房地产开发企业应增加"开发成本""开发产品"等种类」。
 *
 * `rowKey` 是**行标识/持久化键**，与取数键是两回事：`work-in-progress` 作为 rowKey
 * 保留（改名会丢既有 `s2Overrides` / `s2QualMap` 数据），但从 `sourceKeys` 里删除
 * —— 审定表 1404 的键是 `semi-finished`，`work-in-progress` 从来取不到数。
 */
export const F2_LISTED_DISCLOSURE_CATEGORIES: ReadonlyArray<{
  rowKey: string
  label: string
  sourceKeys: readonly string[]
}> = [
  { rowKey: 'raw-materials', label: '原材料', sourceKeys: ['raw-materials', 'material-in-transit'] },
  { rowKey: 'work-in-progress', label: '在产品', sourceKeys: ['semi-finished'] },
  { rowKey: 'dev-costs', label: '开发成本', sourceKeys: ['dev-costs'] },
  { rowKey: 'outsourced-processing', label: '委托加工物资', sourceKeys: ['outsourced-processing'] },
  // 1412 商品进销差价是 1406 库存商品的备抵/附加科目，会计上不单列
  { rowKey: 'finished-goods', label: '库存商品', sourceKeys: ['finished-goods', 'price-difference'] },
  { rowKey: 'dev-products', label: '开发产品', sourceKeys: ['dev-products'] },
  { rowKey: 'goods-in-transit', label: '发出商品', sourceKeys: ['goods-in-transit'] },
  { rowKey: 'revolving-materials', label: '周转材料', sourceKeys: ['revolving-materials'] },
  { rowKey: 'contract-performance', label: '合同履约成本', sourceKeys: ['contract-performance'] },
  { rowKey: 'consumable-bio', label: '消耗性生物资产', sourceKeys: ['consumable-bio'] },
  // 数据资源无对应存货科目（1401~1412）→ 从 (8) 数据资源表联动取数，见 loadClassRow
  { rowKey: 'data-resources', label: '数据资源', sourceKeys: [] },
]

const PREFIX = 'F2-note-listed-'
const ITEM_S2_OVERRIDES = `${PREFIX}s2-overrides`
const ITEM_S2_QUAL = `${PREFIX}s2-qual`
const ITEM_S3_END = `${PREFIX}s3-end`
const ITEM_S3_PRIOR = `${PREFIX}s3-prior`
/** (3) 计提方式：'portfolio'（按组合）| 'aging'（按库龄组合）——源模板「或：」二选一 */
const ITEM_S3_MODE = `${PREFIX}s3-mode`
const ITEM_S5 = `${PREFIX}s5-rows`
const ITEM_S6 = `${PREFIX}s6-rows`
const ITEM_S7 = `${PREFIX}s7-rows`
/** (8) 确认为存货的数据资源（三段式 21 行，仅存录入行） */
const ITEM_S8_DR = `${PREFIX}s8-data-resource`
const ITEM_NOTE_CATEGORY = `${PREFIX}note-category`
const ITEM_NOTE_NRV = `${PREFIX}note-nrv`
const ITEM_NOTE_PROVISION = `${PREFIX}note-provision`
const ITEM_NOTE_BORROW = `${PREFIX}note-borrow`
/** (4) 合同履约成本本期摊销说明（源：附注模版「（说明合同履约成本本期摊销金额。）」） */
const ITEM_NOTE_AMORT = `${PREFIX}note-amort`
const ITEM_NOTE_RE = `${PREFIX}note-re`

export interface F2ListedClassRow {
  rowKey: string
  label: string
  endGross: number
  endImpairment: number
  endNet: number
  priorGross: number
  priorImpairment: number
  priorNet: number
}

export interface F2ListedMovementRow {
  rowKey: string
  label: string
  opening: number
  incProvision: number
  incOther: number
  decReversal: number
  decOther: number
  ending: number
  /** 与 (1) 期末跌价准备差额，|diff|<0.01 视为勾稽 */
  tieDiff: number
}

export interface F2ListedQualRow {
  rowKey: string
  label: string
  nrvBasis: string
  reversalReason: string
}

export interface F2ListedPortfolioRow {
  rowId: string
  groupName: string
  balance: number
  impairment: number
  provisionStandard: string
  netValue: number
  balancePct: number
  impairmentPct: number
}

export interface F2ListedDevCostRow {
  rowId: string
  projectName: string
  startDate: string
  expectedCompleteDate: string
  estimatedInvestment: number
  endBalance: number
  priorBalance: number
  endImpairment: number
}

export interface F2ListedDevProductRow {
  rowId: string
  projectName: string
  completeDate: string
  opening: number
  increase: number
  decrease: number
  ending: number
  endImpairment: number
}

export interface F2ListedTurnoverHousingRow {
  rowId: string
  projectName: string
  opening: number
  increase: number
  decrease: number
  ending: number
}

interface S2Override {
  incProvision?: number | null
  incOther?: number
  decReversal?: number | null
  decOther?: number
}

function generateRowId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function safeParseJson<T>(jsonStr: string | null | undefined, fallback: T): T {
  if (!jsonStr) return fallback
  try {
    const parsed = JSON.parse(jsonStr)
    return parsed ?? fallback
  } catch {
    return fallback
  }
}

function itemId(block: 'gross' | 'impairment', rowKey: string, field: string): string {
  return `F2-1-${block}-${rowKey}-${field}`
}

function loadField(map: Map<string, ChecklistResponse>, id: string): number {
  return parseNum(map.get(id)?.conclusion)
}

function sumSources(
  map: Map<string, ChecklistResponse>,
  block: 'gross' | 'impairment',
  sourceKeys: readonly string[],
  field: string,
): number {
  return sourceKeys.reduce((s, key) => s + loadField(map, itemId(block, key, field)), 0)
}

/** 「数据资源」行：无对应存货科目 → 从 (8) 数据资源表联动（R25） */
function linkedClassRow(
  cat: { rowKey: string; label: string },
  dr: DrClassLinkage,
): F2ListedClassRow {
  return {
    rowKey: cat.rowKey,
    label: cat.label,
    endGross: dr.endGross,
    endImpairment: dr.endImpairment,
    endNet: calcNetValue(dr.endGross, dr.endImpairment),
    priorGross: dr.priorGross,
    priorImpairment: dr.priorImpairment,
    priorNet: calcNetValue(dr.priorGross, dr.priorImpairment),
  }
}

function loadClassRow(
  map: Map<string, ChecklistResponse>,
  cat: (typeof F2_LISTED_DISCLOSURE_CATEGORIES)[number],
): F2ListedClassRow {
  const openingG = sumSources(map, 'gross', cat.sourceKeys, 'opening')
  const openingI = sumSources(map, 'impairment', cat.sourceKeys, 'opening')
  const incG = sumSources(map, 'gross', cat.sourceKeys, 'increase')
  const incI = sumSources(map, 'impairment', cat.sourceKeys, 'increase')
  const decG = sumSources(map, 'gross', cat.sourceKeys, 'decrease')
  const decI = sumSources(map, 'impairment', cat.sourceKeys, 'decrease')
  const adjG = sumSources(map, 'gross', cat.sourceKeys, 'adjustment')
  const adjI = sumSources(map, 'impairment', cat.sourceKeys, 'adjustment')

  const priorGross = openingG
  const priorImpairment = openingI
  const priorNet = calcNetValue(priorGross, priorImpairment)
  const endGross = calcAuditedEnd(openingG, incG, decG, adjG)
  const endImpairment = calcAuditedEnd(openingI, incI, decI, adjI)
  const endNet = calcNetValue(endGross, endImpairment)

  return {
    rowKey: cat.rowKey,
    label: cat.label,
    endGross,
    endImpairment,
    endNet,
    priorGross,
    priorImpairment,
    priorNet,
  }
}

function totalClass(rows: F2ListedClassRow[], label = '合计'): F2ListedClassRow {
  return {
    rowKey: '__total__',
    label,
    endGross: calcSubtotal(rows.map((r) => r.endGross)),
    endImpairment: calcSubtotal(rows.map((r) => r.endImpairment)),
    endNet: calcSubtotal(rows.map((r) => r.endNet)),
    priorGross: calcSubtotal(rows.map((r) => r.priorGross)),
    priorImpairment: calcSubtotal(rows.map((r) => r.priorImpairment)),
    priorNet: calcSubtotal(rows.map((r) => r.priorNet)),
  }
}

/** 比例：分母为 0 时返回 0，避免 #DIV/0! */
export function safeRatio(part: number, total: number): number {
  if (!total || !Number.isFinite(total) || !Number.isFinite(part)) return 0
  return part / total
}

function emptyS3Row(): F2ListedPortfolioRow {
  return {
    rowId: generateRowId('s3'),
    groupName: '',
    balance: 0,
    impairment: 0,
    provisionStandard: '',
    netValue: 0,
    balancePct: 0,
    impairmentPct: 0,
  }
}

function emptyS5Row(): F2ListedDevCostRow {
  return {
    rowId: generateRowId('s5'),
    projectName: '',
    startDate: '',
    expectedCompleteDate: '',
    estimatedInvestment: 0,
    endBalance: 0,
    priorBalance: 0,
    endImpairment: 0,
  }
}

function emptyS6Row(): F2ListedDevProductRow {
  return {
    rowId: generateRowId('s6'),
    projectName: '',
    completeDate: '',
    opening: 0,
    increase: 0,
    decrease: 0,
    ending: 0,
    endImpairment: 0,
  }
}

function emptyS7Row(): F2ListedTurnoverHousingRow {
  return {
    rowId: generateRowId('s7'),
    projectName: '',
    opening: 0,
    increase: 0,
    decrease: 0,
    ending: 0,
  }
}

/**
 * 补算 (3) 按组合计提的派生列。
 *
 * 源模板口径（附注披露信息（上市公司）R52/R54）：
 * - `C52 = B52/B54` → 账面余额「比例(%)」= 本组合账面余额 ÷ 合计账面余额（占比）
 * - `F52 = D52/B52` → 存货跌价准备「比例(%)」= 本组合跌价准备 ÷ **本组合账面余额**（计提比例）
 *
 * 注意两列分母不同：占比的分母是合计，计提比例的分母是本行账面余额。
 */
function enrichS3(rows: F2ListedPortfolioRow[]): F2ListedPortfolioRow[] {
  const balTotal = calcSubtotal(rows.map((r) => r.balance))
  return rows.map((r) => {
    const netValue = calcNetValue(r.balance, r.impairment)
    return {
      ...r,
      netValue,
      balancePct: safeRatio(r.balance, balTotal),
      impairmentPct: safeRatio(r.impairment, r.balance),
    }
  })
}

function isF2InventoryAccount(code: string): boolean {
  const n = parseInt(code, 10)
  return (n >= 1401 && n <= 1412) || n === 1421 || n === 1461 || n === 1471
}

export function useF2DisclosureListed(options: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly: Ref<boolean>
  applicableStandards: Ref<string[]>
}) {
  const { allResponses, isReadonly, applicableStandards } = options
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const eventListeners: Array<{ event: string; handler: (e: Event) => void }> = []
  const adjudicatedRefreshKey = ref(0)
  const dataUpdatedVisible = ref(false)
  let dataUpdatedTimer: ReturnType<typeof setTimeout> | null = null

  const isApplicable: ComputedRef<boolean> = computed(() =>
    isF2DisclosureApplicable('listed', applicableStandards.value),
  )

  // ─── (8) 数据资源持久化值 ─────────────
  // 🔴 声明必须早于 `section1Rows`：分类表「数据资源」行从本表联动取数，
  // 而 computed 可能在 setup 期间（s2 的 immediate watch）就被求值，
  // 若 `drValues` 还在 TDZ 会直接 ReferenceError。
  const drValues = ref<DrValueMap>({})

  watch(
    () => allResponses.value.get(ITEM_S8_DR)?.remark,
    (json) => { drValues.value = safeParseJson<DrValueMap>(json, {}) },
    { immediate: true },
  )

  /** 数据资源表 → 分类表「数据资源」行（R25） */
  const drClassLinkage: ComputedRef<DrClassLinkage> = computed(() =>
    deriveDataResourceClassRow(drValues.value),
  )

  // ─── (1) 存货分类：跨 sheet 自 F2-1；数据资源行自 (8) 联动 ─────────────
  const section1Rows: ComputedRef<F2ListedClassRow[]> = computed(() => {
    void adjudicatedRefreshKey.value
    const map = allResponses.value
    const dr = drClassLinkage.value
    return F2_LISTED_DISCLOSURE_CATEGORIES.map((cat) =>
      cat.rowKey === 'data-resources' ? linkedClassRow(cat, dr) : loadClassRow(map, cat),
    )
  })

  const section1Total: ComputedRef<F2ListedClassRow> = computed(() =>
    totalClass(section1Rows.value),
  )

  // ─── (2) 跌价准备变动 + 定性说明 ─────────────
  const s2Overrides = ref<Record<string, S2Override>>({})
  const s2QualMap = ref<Record<string, { nrvBasis: string; reversalReason: string }>>({})

  watch(
    () => allResponses.value.get(ITEM_S2_OVERRIDES)?.remark,
    (json) => { s2Overrides.value = safeParseJson(json, {}) },
    { immediate: true },
  )
  watch(
    () => allResponses.value.get(ITEM_S2_QUAL)?.remark,
    (json) => { s2QualMap.value = safeParseJson(json, {}) },
    { immediate: true },
  )

  const section2Rows: ComputedRef<F2ListedMovementRow[]> = computed(() => {
    void adjudicatedRefreshKey.value
    const map = allResponses.value
    const classByKey = new Map(section1Rows.value.map((r) => [r.rowKey, r]))
    return F2_LISTED_DISCLOSURE_CATEGORIES.map((cat) => {
      const opening = sumSources(map, 'impairment', cat.sourceKeys, 'opening')
      const autoInc = sumSources(map, 'impairment', cat.sourceKeys, 'increase')
      const autoDec = sumSources(map, 'impairment', cat.sourceKeys, 'decrease')
      const ov = s2Overrides.value[cat.rowKey] || {}
      const incProvision = ov.incProvision != null ? parseNum(ov.incProvision) : autoInc
      const incOther = parseNum(ov.incOther)
      const decReversal = ov.decReversal != null ? parseNum(ov.decReversal) : autoDec
      const decOther = parseNum(ov.decOther)
      const ending = opening + incProvision + incOther - decReversal - decOther
      const classEndI = classByKey.get(cat.rowKey)?.endImpairment ?? 0
      return {
        rowKey: cat.rowKey,
        label: cat.label,
        opening,
        incProvision,
        incOther,
        decReversal,
        decOther,
        ending,
        tieDiff: ending - classEndI,
      }
    })
  })

  const section2Total: ComputedRef<F2ListedMovementRow> = computed(() => {
    const rows = section2Rows.value
    const opening = calcSubtotal(rows.map((r) => r.opening))
    const incProvision = calcSubtotal(rows.map((r) => r.incProvision))
    const incOther = calcSubtotal(rows.map((r) => r.incOther))
    const decReversal = calcSubtotal(rows.map((r) => r.decReversal))
    const decOther = calcSubtotal(rows.map((r) => r.decOther))
    const ending = opening + incProvision + incOther - decReversal - decOther
    return {
      rowKey: '__total__',
      label: '合计',
      opening,
      incProvision,
      incOther,
      decReversal,
      decOther,
      ending,
      tieDiff: ending - section1Total.value.endImpairment,
    }
  })

  const section2QualRows: ComputedRef<F2ListedQualRow[]> = computed(() =>
    F2_LISTED_DISCLOSURE_CATEGORIES.map((cat) => {
      const q = s2QualMap.value[cat.rowKey] || { nrvBasis: '', reversalReason: '' }
      return {
        rowKey: cat.rowKey,
        label: cat.label,
        nrvBasis: q.nrvBasis || '',
        reversalReason: q.reversalReason || '',
      }
    }),
  )

  // ─── (3) 按组合计提 ─────────────
  const s3EndRaw = ref<F2ListedPortfolioRow[]>([])
  const s3PriorRaw = ref<F2ListedPortfolioRow[]>([])

  watch(
    () => allResponses.value.get(ITEM_S3_END)?.remark,
    (json) => {
      const rows = safeParseJson<F2ListedPortfolioRow[]>(json, [])
      s3EndRaw.value = rows.length ? rows : [emptyS3Row(), emptyS3Row()]
    },
    { immediate: true },
  )
  watch(
    () => allResponses.value.get(ITEM_S3_PRIOR)?.remark,
    (json) => {
      const rows = safeParseJson<F2ListedPortfolioRow[]>(json, [])
      s3PriorRaw.value = rows.length ? rows : [emptyS3Row(), emptyS3Row()]
    },
    { immediate: true },
  )

  /**
   * (3) 计提方式。源模板 R47~R61「按组合计提」与其后「或：…各库龄组合…」是**互斥两组**，
   * 列结构完全相同 → 共用一套行 state（`s3EndRaw` / `s3PriorRaw`），只切换推送表名与行语义，
   * 避免第二套 state 造成双真源。
   */
  const s3Mode = ref<F2ListedS3Mode>('portfolio')
  watch(
    () => allResponses.value.get(ITEM_S3_MODE)?.remark,
    (v) => { s3Mode.value = v === 'aging' ? 'aging' : 'portfolio' },
    { immediate: true },
  )

  const s3EndRows = computed(() => enrichS3(s3EndRaw.value))
  const s3PriorRows = computed(() => enrichS3(s3PriorRaw.value))

  /** 合计行：balancePct 恒 1（源模板 C54=1）；impairmentPct = D54/B54（合计计提比例） */
  function s3Total(rows: F2ListedPortfolioRow[]): F2ListedPortfolioRow {
    const balance = calcSubtotal(rows.map((r) => r.balance))
    const impairment = calcSubtotal(rows.map((r) => r.impairment))
    return {
      rowId: '__total__',
      groupName: '合计',
      balance,
      impairment,
      provisionStandard: '',
      netValue: calcNetValue(balance, impairment),
      balancePct: balance ? 1 : 0,
      impairmentPct: safeRatio(impairment, balance),
    }
  }

  const s3EndTotal = computed(() => s3Total(s3EndRows.value))
  const s3PriorTotal = computed(() => s3Total(s3PriorRows.value))

  // ─── (5)(6)(7) 房企附表 ─────────────
  const s5Rows = ref<F2ListedDevCostRow[]>([])
  const s6Rows = ref<F2ListedDevProductRow[]>([])
  const s7Rows = ref<F2ListedTurnoverHousingRow[]>([])

  watch(
    () => allResponses.value.get(ITEM_S5)?.remark,
    (json) => {
      const rows = safeParseJson<F2ListedDevCostRow[]>(json, [])
      s5Rows.value = rows.length ? rows : [emptyS5Row(), emptyS5Row(), emptyS5Row()]
    },
    { immediate: true },
  )
  watch(
    () => allResponses.value.get(ITEM_S6)?.remark,
    (json) => {
      const rows = safeParseJson<F2ListedDevProductRow[]>(json, [])
      s6Rows.value = rows.length ? rows.map((r) => ({
        ...r,
        ending: calcAuditedEnd(parseNum(r.opening), parseNum(r.increase), parseNum(r.decrease), 0),
        completeDate: r.completeDate === '1900-1-0' ? '' : (r.completeDate || ''),
      })) : [emptyS6Row(), emptyS6Row(), emptyS6Row()]
    },
    { immediate: true },
  )
  watch(
    () => allResponses.value.get(ITEM_S7)?.remark,
    (json) => {
      const rows = safeParseJson<F2ListedTurnoverHousingRow[]>(json, [])
      s7Rows.value = rows.length ? rows.map((r) => ({
        ...r,
        ending: calcAuditedEnd(parseNum(r.opening), parseNum(r.increase), parseNum(r.decrease), 0),
      })) : [emptyS7Row(), emptyS7Row(), emptyS7Row()]
    },
    { immediate: true },
  )

  const s5Total = computed(() => ({
    rowId: '__total__',
    projectName: '合计',
    startDate: '',
    expectedCompleteDate: '',
    estimatedInvestment: calcSubtotal(s5Rows.value.map((r) => r.estimatedInvestment)),
    endBalance: calcSubtotal(s5Rows.value.map((r) => r.endBalance)),
    priorBalance: calcSubtotal(s5Rows.value.map((r) => r.priorBalance)),
    endImpairment: calcSubtotal(s5Rows.value.map((r) => r.endImpairment)),
  } satisfies F2ListedDevCostRow))

  const s6Total = computed(() => ({
    rowId: '__total__',
    projectName: '合计',
    completeDate: '',
    opening: calcSubtotal(s6Rows.value.map((r) => r.opening)),
    increase: calcSubtotal(s6Rows.value.map((r) => r.increase)),
    decrease: calcSubtotal(s6Rows.value.map((r) => r.decrease)),
    ending: calcSubtotal(s6Rows.value.map((r) => r.ending)),
    endImpairment: calcSubtotal(s6Rows.value.map((r) => r.endImpairment)),
  } satisfies F2ListedDevProductRow))

  const s7Total = computed(() => ({
    rowId: '__total__',
    projectName: '合计',
    opening: calcSubtotal(s7Rows.value.map((r) => r.opening)),
    increase: calcSubtotal(s7Rows.value.map((r) => r.increase)),
    decrease: calcSubtotal(s7Rows.value.map((r) => r.decrease)),
    ending: calcSubtotal(s7Rows.value.map((r) => r.ending)),
  } satisfies F2ListedTurnoverHousingRow))

  // ─── (8) 确认为存货的数据资源（`drValues` 与 watch 已提前到 (1) 之前声明）─────────────
  const drRows = computed(() => buildDataResourceRows(drValues.value, 'listed'))
  const drIsEmpty = computed(() => isDataResourceEmpty(drValues.value))

  /** 与 (1) 分类表「数据资源」行的交叉勾稽（F9-12/12a/13/13a） */
  const drTieChecks = computed(() => {
    const cls = section1Rows.value.find((r) => r.rowKey === 'data-resources')
    return buildDataResourceTieChecks(
      drValues.value,
      cls
        ? {
            endGross: cls.endGross,
            endImpairment: cls.endImpairment,
            priorGross: cls.priorGross,
            priorImpairment: cls.priorImpairment,
          }
        : null,
      'listed',
    )
  })

  const drTieFailures = computed(() => drTieChecks.value.filter((c) => !c.ok))

  // ─── 附注文字 ─────────────
  const noteCategory = ref('')
  const noteNrv = ref('')
  const noteProvision = ref('')
  const s4BorrowText = ref('')
  const s4AmortText = ref('')
  const noteRe = ref('')

  watch(() => allResponses.value.get(ITEM_NOTE_CATEGORY)?.remark, (v) => { noteCategory.value = v || '' }, { immediate: true })
  watch(() => allResponses.value.get(ITEM_NOTE_NRV)?.remark, (v) => { noteNrv.value = v || '' }, { immediate: true })
  watch(() => allResponses.value.get(ITEM_NOTE_PROVISION)?.remark, (v) => { noteProvision.value = v || '' }, { immediate: true })
  watch(() => allResponses.value.get(ITEM_NOTE_BORROW)?.remark, (v) => { s4BorrowText.value = v || '' }, { immediate: true })
  watch(() => allResponses.value.get(ITEM_NOTE_AMORT)?.remark, (v) => { s4AmortText.value = v || '' }, { immediate: true })
  watch(() => allResponses.value.get(ITEM_NOTE_RE)?.remark, (v) => { noteRe.value = v || '' }, { immediate: true })

  // ─── 持久化 ─────────────
  function setItem(itemIdKey: string, remark: string): void {
    allResponses.value.set(itemIdKey, { item_id: itemIdKey, conclusion: null, remark })
  }

  function flushSave(): void {
    const keys = [
      ITEM_S2_OVERRIDES, ITEM_S2_QUAL, ITEM_S3_END, ITEM_S3_PRIOR, ITEM_S3_MODE,
      ITEM_S5, ITEM_S6, ITEM_S7, ITEM_S8_DR,
      ITEM_NOTE_CATEGORY, ITEM_NOTE_NRV, ITEM_NOTE_PROVISION,
      ITEM_NOTE_BORROW, ITEM_NOTE_AMORT, ITEM_NOTE_RE,
    ]
    const items = keys.map((k) => allResponses.value.get(k)).filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items } }))
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function persistNote(itemIdKey: string, val: string, section: string): void {
    setItem(itemIdKey, val)
    debounceSave()
    try {
      window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
        // 存货 listed → 五、9（note_template_variant_matrix）
        detail: { wpCode: 'F2', accountCode: '1405', section, sectionIds: ['五、9'], text: val },
      }))
    } catch { /* silent */ }
  }

  watch(noteCategory, (v) => persistNote(ITEM_NOTE_CATEGORY, v, 'listed-note-category'))
  watch(noteNrv, (v) => persistNote(ITEM_NOTE_NRV, v, 'listed-note-nrv'))
  watch(noteProvision, (v) => persistNote(ITEM_NOTE_PROVISION, v, 'listed-note-provision'))
  watch(s4BorrowText, (v) => persistNote(ITEM_NOTE_BORROW, v, 'listed-note-borrow'))
  watch(s4AmortText, (v) => persistNote(ITEM_NOTE_AMORT, v, 'listed-note-amort'))
  watch(noteRe, (v) => persistNote(ITEM_NOTE_RE, v, 'listed-note-re'))

  const adjudicatedHandler = (e: Event) => {
    const d = (e as CustomEvent).detail
    if (d?.wpCode !== 'F2') return
    const codes: string[] = d?.accountCodes ?? []
    if (codes.length === 0 || codes.some(isF2InventoryAccount)) {
      adjudicatedRefreshKey.value += 1
      dataUpdatedVisible.value = true
      if (dataUpdatedTimer) clearTimeout(dataUpdatedTimer)
      dataUpdatedTimer = setTimeout(() => { dataUpdatedVisible.value = false }, 3000)
    }
  }
  window.addEventListener('substantive:adjudicated', adjudicatedHandler)
  eventListeners.push({ event: 'substantive:adjudicated', handler: adjudicatedHandler })

  // ─── 编辑 API ─────────────
  function updateS2Field(rowKey: string, field: keyof S2Override, value: number): void {
    if (isReadonly.value) return
    const next = { ...(s2Overrides.value[rowKey] || {}), [field]: parseNum(value) }
    s2Overrides.value = { ...s2Overrides.value, [rowKey]: next }
    setItem(ITEM_S2_OVERRIDES, JSON.stringify(s2Overrides.value))
    debounceSave()
  }

  function updateQualField(rowKey: string, field: 'nrvBasis' | 'reversalReason', value: string): void {
    if (isReadonly.value) return
    const prev = s2QualMap.value[rowKey] || { nrvBasis: '', reversalReason: '' }
    s2QualMap.value = { ...s2QualMap.value, [rowKey]: { ...prev, [field]: value } }
    setItem(ITEM_S2_QUAL, JSON.stringify(s2QualMap.value))
    debounceSave()
  }

  function updateS3Row(
    which: 'end' | 'prior',
    rowId: string,
    field: keyof F2ListedPortfolioRow,
    value: string | number,
  ): void {
    if (isReadonly.value) return
    const raw = which === 'end' ? s3EndRaw : s3PriorRaw
    const itemKey = which === 'end' ? ITEM_S3_END : ITEM_S3_PRIOR
    const idx = raw.value.findIndex((r) => r.rowId === rowId)
    if (idx < 0) return
    const row = { ...raw.value[idx] }
    if (field === 'groupName' || field === 'provisionStandard') (row as any)[field] = String(value ?? '')
    else if (field === 'balance' || field === 'impairment') {
      (row as any)[field] = parseNum(value)
      row.netValue = calcNetValue(row.balance, row.impairment)
    }
    raw.value.splice(idx, 1, row)
    setItem(itemKey, JSON.stringify(raw.value))
    debounceSave()
  }

  /** 库龄组合骨架（源模板未列具体档位，给最常见两档作提示，可改名/增删） */
  const S3_AGING_SEED_LABELS = ['1年以内', '1至2年'] as const

  /**
   * 切换 (3) 计提方式。切到「按库龄组合」且组合名全空时，用库龄段预填骨架
   * （只填名字，金额不动；已有名字一律不覆盖）。
   */
  function setS3Mode(mode: F2ListedS3Mode): void {
    if (isReadonly.value || s3Mode.value === mode) return
    s3Mode.value = mode
    setItem(ITEM_S3_MODE, mode)
    if (mode === 'aging') {
      for (const [raw, itemKey] of [
        [s3EndRaw, ITEM_S3_END],
        [s3PriorRaw, ITEM_S3_PRIOR],
      ] as const) {
        if (raw.value.some((r) => r.groupName.trim())) continue
        raw.value = raw.value.map((r, i) => (
          i < S3_AGING_SEED_LABELS.length ? { ...r, groupName: S3_AGING_SEED_LABELS[i] } : r
        ))
        setItem(itemKey, JSON.stringify(raw.value))
      }
    }
    debounceSave()
  }

  function addS3Row(which: 'end' | 'prior'): void {
    if (isReadonly.value) return
    const raw = which === 'end' ? s3EndRaw : s3PriorRaw
    const itemKey = which === 'end' ? ITEM_S3_END : ITEM_S3_PRIOR
    raw.value = [...raw.value, emptyS3Row()]
    setItem(itemKey, JSON.stringify(raw.value))
    debounceSave()
  }

  function removeS3Row(which: 'end' | 'prior', rowId: string): void {
    if (isReadonly.value) return
    const raw = which === 'end' ? s3EndRaw : s3PriorRaw
    const itemKey = which === 'end' ? ITEM_S3_END : ITEM_S3_PRIOR
    if (raw.value.length <= 1) {
      raw.value = [emptyS3Row()]
    } else {
      raw.value = raw.value.filter((r) => r.rowId !== rowId)
    }
    setItem(itemKey, JSON.stringify(raw.value))
    debounceSave()
  }

  function updateS5(rowId: string, field: keyof F2ListedDevCostRow, value: string | number): void {
    if (isReadonly.value) return
    const idx = s5Rows.value.findIndex((r) => r.rowId === rowId)
    if (idx < 0) return
    const row = { ...s5Rows.value[idx] }
    if (field === 'projectName' || field === 'startDate' || field === 'expectedCompleteDate') {
      let v = String(value ?? '')
      if (v === '1900-1-0') v = ''
      ;(row as any)[field] = v
    } else {
      (row as any)[field] = parseNum(value)
    }
    s5Rows.value.splice(idx, 1, row)
    setItem(ITEM_S5, JSON.stringify(s5Rows.value))
    debounceSave()
  }

  function updateS6(rowId: string, field: keyof F2ListedDevProductRow, value: string | number): void {
    if (isReadonly.value) return
    const idx = s6Rows.value.findIndex((r) => r.rowId === rowId)
    if (idx < 0) return
    const row = { ...s6Rows.value[idx] }
    if (field === 'projectName' || field === 'completeDate') {
      let v = String(value ?? '')
      if (v === '1900-1-0') v = ''
      ;(row as any)[field] = v
    } else {
      (row as any)[field] = parseNum(value)
    }
    row.ending = calcAuditedEnd(row.opening, row.increase, row.decrease, 0)
    s6Rows.value.splice(idx, 1, row)
    setItem(ITEM_S6, JSON.stringify(s6Rows.value))
    debounceSave()
  }

  function updateS7(rowId: string, field: keyof F2ListedTurnoverHousingRow, value: string | number): void {
    if (isReadonly.value) return
    const idx = s7Rows.value.findIndex((r) => r.rowId === rowId)
    if (idx < 0) return
    const row = { ...s7Rows.value[idx] }
    if (field === 'projectName') row.projectName = String(value ?? '')
    else (row as any)[field] = parseNum(value)
    row.ending = calcAuditedEnd(row.opening, row.increase, row.decrease, 0)
    s7Rows.value.splice(idx, 1, row)
    setItem(ITEM_S7, JSON.stringify(s7Rows.value))
    debounceSave()
  }

  function addS5(): void {
    if (isReadonly.value) return
    s5Rows.value = [...s5Rows.value, emptyS5Row()]
    setItem(ITEM_S5, JSON.stringify(s5Rows.value))
    debounceSave()
  }
  function addS6(): void {
    if (isReadonly.value) return
    s6Rows.value = [...s6Rows.value, emptyS6Row()]
    setItem(ITEM_S6, JSON.stringify(s6Rows.value))
    debounceSave()
  }
  function addS7(): void {
    if (isReadonly.value) return
    s7Rows.value = [...s7Rows.value, emptyS7Row()]
    setItem(ITEM_S7, JSON.stringify(s7Rows.value))
    debounceSave()
  }

  function removeS5(rowId: string): void {
    if (isReadonly.value) return
    s5Rows.value = s5Rows.value.length <= 1 ? [emptyS5Row()] : s5Rows.value.filter((r) => r.rowId !== rowId)
    setItem(ITEM_S5, JSON.stringify(s5Rows.value))
    debounceSave()
  }
  function removeS6(rowId: string): void {
    if (isReadonly.value) return
    s6Rows.value = s6Rows.value.length <= 1 ? [emptyS6Row()] : s6Rows.value.filter((r) => r.rowId !== rowId)
    setItem(ITEM_S6, JSON.stringify(s6Rows.value))
    debounceSave()
  }
  function removeS7(rowId: string): void {
    if (isReadonly.value) return
    s7Rows.value = s7Rows.value.length <= 1 ? [emptyS7Row()] : s7Rows.value.filter((r) => r.rowId !== rowId)
    setItem(ITEM_S7, JSON.stringify(s7Rows.value))
    debounceSave()
  }

  /** (8) 数据资源：仅录入行可写（派生行/段标题行由 setDrCell 拦截） */
  function updateDrCell(rowKey: string, col: DrColKey, value: number | string | null): void {
    if (isReadonly.value) return
    const next = setDrCell(drValues.value, rowKey, col, value)
    if (next === drValues.value) return
    drValues.value = next
    setItem(ITEM_S8_DR, JSON.stringify(next))
    debounceSave()
  }

  function getSyncSnapshot(): F2ListedSyncSnapshot {
    return {
      section1Rows: section1Rows.value.map(({ rowKey, label, endGross, endImpairment, endNet, priorGross, priorImpairment, priorNet }) => ({
        rowKey, label, endGross, endImpairment, endNet, priorGross, priorImpairment, priorNet,
      })),
      section1Total: {
        label: section1Total.value.label,
        endGross: section1Total.value.endGross,
        endImpairment: section1Total.value.endImpairment,
        endNet: section1Total.value.endNet,
        priorGross: section1Total.value.priorGross,
        priorImpairment: section1Total.value.priorImpairment,
        priorNet: section1Total.value.priorNet,
      },
      section2Rows: section2Rows.value.map(({ rowKey, label, opening, incProvision, incOther, decReversal, decOther, ending }) => ({
        rowKey, label, opening, incProvision, incOther, decReversal, decOther, ending,
      })),
      section2Total: {
        label: section2Total.value.label,
        opening: section2Total.value.opening,
        incProvision: section2Total.value.incProvision,
        incOther: section2Total.value.incOther,
        decReversal: section2Total.value.decReversal,
        decOther: section2Total.value.decOther,
        ending: section2Total.value.ending,
      },
      section2QualRows: section2QualRows.value.map(({ rowKey, label, nrvBasis, reversalReason }) => ({
        rowKey, label, nrvBasis, reversalReason,
      })),
      s3EndRows: s3EndRows.value.map((r) => ({
        groupName: r.groupName,
        balance: r.balance,
        balancePct: r.balancePct,
        impairment: r.impairment,
        provisionStandard: r.provisionStandard,
        impairmentPct: r.impairmentPct,
        netValue: r.netValue,
      })),
      s3PriorRows: s3PriorRows.value.map((r) => ({
        groupName: r.groupName,
        balance: r.balance,
        balancePct: r.balancePct,
        impairment: r.impairment,
        provisionStandard: r.provisionStandard,
        impairmentPct: r.impairmentPct,
        netValue: r.netValue,
      })),
      s4BorrowText: s4BorrowText.value,
      s4AmortText: s4AmortText.value,
      s5Rows: s5Rows.value.map((r) => ({
        projectName: r.projectName,
        startDate: r.startDate,
        expectedCompleteDate: r.expectedCompleteDate,
        estimatedInvestment: r.estimatedInvestment,
        endBalance: r.endBalance,
        priorBalance: r.priorBalance,
        endImpairment: r.endImpairment,
      })),
      s6Rows: s6Rows.value.map((r) => ({
        projectName: r.projectName,
        completeDate: r.completeDate,
        opening: r.opening,
        increase: r.increase,
        decrease: r.decrease,
        ending: r.ending,
        endImpairment: r.endImpairment,
      })),
      s7Rows: s7Rows.value.map((r) => ({
        projectName: r.projectName,
        opening: r.opening,
        increase: r.increase,
        decrease: r.decrease,
        ending: r.ending,
      })),
      s8DataResourceRows: buildDataResourceSyncRows(drRows.value),
      s3Mode: s3Mode.value,
      noteCategory: noteCategory.value,
      noteNrv: noteNrv.value,
      noteProvision: noteProvision.value,
      noteRe: noteRe.value,
    }
  }

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); flushSave() }
    if (dataUpdatedTimer) clearTimeout(dataUpdatedTimer)
    for (const { event, handler } of eventListeners) window.removeEventListener(event, handler)
  })

  return {
    isApplicable,
    section1Rows,
    section1Total,
    section2Rows,
    section2Total,
    section2QualRows,
    s3EndRows,
    s3EndTotal,
    s3PriorRows,
    s3PriorTotal,
    s3Mode,
    setS3Mode,
    s5Rows,
    s5Total,
    s6Rows,
    s6Total,
    s7Rows,
    s7Total,
    drRows,
    drIsEmpty,
    drTieChecks,
    drTieFailures,
    noteCategory,
    noteNrv,
    noteProvision,
    s4BorrowText,
    s4AmortText,
    noteRe,
    dataUpdatedVisible,
    updateS2Field,
    updateQualField,
    updateS3Row,
    addS3Row,
    removeS3Row,
    updateS5,
    updateS6,
    updateS7,
    addS5,
    addS6,
    addS7,
    removeS5,
    removeS6,
    removeS7,
    updateDrCell,
    getSyncSnapshot,
  }
}

export default useF2DisclosureListed
