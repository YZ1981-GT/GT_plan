/**
 * useF5CostRollforward — F5-7 主营业务成本倒轧表（灵魂表）
 *
 * 源表编制逻辑（四段倒轧链）：
 *  ① 直接材料成本 ⑹ = ⑴期初材料 + ⑵购入净额 + ⑶其他增加 − ⑷期末材料 − ⑸其他发出
 *  ② 产品生产成本 ⑽ = ⑹ + ⑺直接人工 + ⑻制造费用 + ⑼专用工模具
 *     （「其中：材料费用」为 ⑻ 明细，不参与 ⑽ 合计）
 *  ③ 产成品成本 ⒀ = ⑽ + ⑾在产品期初 − ⑿在产品期末
 *  ④ 主营业务成本 ⒇ = ⒀ + ⒁产成品期初 + ⒂其他增加 − ⒃产成品期末 − ⒄自制自用 − ⒅内部领用 − ⒆其他发出
 *
 * 每行：未审数 / 审计调整 / 审定数(=未审+调整 或 公式轧差) / 上期数
 * 交叉引用：TB(1401/1404/1405)、F2存货、F5-1审定、F5-2月度等
 * HTML 扩展：与 F5-1 审定营业成本校验差异（EventBus）
 */
import { computed, ref, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcAdjustedAmount,
  calcF57DirectMaterial,
  calcF57ProductionCost,
  calcF57FinishedGoodsCost,
  calcF57MainBusinessCOGS,
} from './useF5CosOfFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export interface UseF5CostRollforwardOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
  materiality?: Ref<number>
  adjudicatedCOGS?: Ref<number>
}

export type F57RowType = 'input' | 'formula' | 'detail'
export type F57AmountField = 'unadjusted' | 'aje' | 'prior'

export interface F57RowDef {
  rowKey: string
  seqNo: string
  label: string
  rowType: F57RowType
  /** 计算说明列 / 悬停公式文案 */
  formulaLegend: string
  /** 结构化公式表达式（用于悬停） */
  formulaExpr: string
  dataSource: string
  /** 默认交叉索引（可被用户覆盖） */
  defaultIndexRef: string
  /** TB 自动取数键 */
  tbField?: string
  /** 旧存储字段别名 */
  legacyKeys?: string[]
  isResult?: boolean
}

export interface F57RowView extends F57RowDef {
  unadjusted: number
  aje: number
  audited: number
  prior: number
  indexRef: string
}

interface StoredAmount {
  unadjusted: number
  aje: number
  prior: number
  indexRef?: string
}

const STORAGE_KEY = 'F5-7-cost-rollforward'
const NOTE_KEY = 'F5-7-audit-note'
const CONCLUSION_KEY = 'F5-7-audit-conclusion'
const LEGACY_CONCLUSION_KEY = 'F5-7-conclusion'
const ADJUDICATED_KEY = 'F5-7-adjudicated-cogs'

/** 源表固定 21 行定义（含公式悬停与默认交叉引用） */
export const F57_ROW_DEFS: F57RowDef[] = [
  {
    rowKey: 'openingMaterial', seqNo: '⑴', label: '期初原材料余额',
    rowType: 'input',
    formulaLegend: '⑴',
    formulaExpr: '取自总账「原材料」期初余额',
    dataSource: '总账“材料”账户期初余额',
    defaultIndexRef: 'tb:1401',
    tbField: 'openingMaterial',
  },
  {
    rowKey: 'materialPurchaseNet', seqNo: '⑵', label: '加：本期购入材料净额',
    rowType: 'input',
    formulaLegend: '⑵',
    formulaExpr: '材料借方购入 − 退货折让',
    dataSource: '“材料”借方购入额扣退货折让金额',
    defaultIndexRef: 'wp:F2',
    legacyKeys: ['purchase'],
  },
  {
    rowKey: 'materialOtherIncrease', seqNo: '⑶', label: '加：其他增加额',
    rowType: 'input',
    formulaLegend: '⑶',
    formulaExpr: '材料借方其他发生额',
    dataSource: '“材料”借方其他发生额',
    defaultIndexRef: 'wp:F2',
  },
  {
    rowKey: 'closingMaterial', seqNo: '⑷', label: '减：期末原材料余额',
    rowType: 'input',
    formulaLegend: '⑷',
    formulaExpr: '取自总账「原材料」年末余额',
    dataSource: '总账“材料”账户年末余额',
    defaultIndexRef: 'tb:1401',
    tbField: 'closingMaterial',
  },
  {
    rowKey: 'materialOtherIssue', seqNo: '⑸', label: '减：其他原材料发出额',
    rowType: 'input',
    formulaLegend: '⑸',
    formulaExpr: '材料贷方其他发出（非生产领用）',
    dataSource: '“材料”贷方其他发生额',
    defaultIndexRef: 'wp:F2',
    legacyKeys: ['otherIssue1'],
  },
  {
    rowKey: 'directMaterialCost', seqNo: '⑹', label: '直接材料成本',
    rowType: 'formula',
    formulaLegend: '⑹=⑴+⑵+⑶−⑷−⑸',
    formulaExpr: '直接材料成本 = 期初原材料 + 本期购入净额 + 其他增加 − 期末原材料 − 其他发出',
    dataSource: '生产成本明细账',
    defaultIndexRef: '',
    isResult: true,
  },
  {
    rowKey: 'directLabor', seqNo: '⑺', label: '加：直接人工成本',
    rowType: 'input',
    formulaLegend: '⑺',
    formulaExpr: '生产成本明细账直接人工',
    dataSource: '生产成本明细账',
    defaultIndexRef: 'wp:F5-2',
  },
  {
    rowKey: 'manufacturingOverhead', seqNo: '⑻', label: '加：制造费用',
    rowType: 'input',
    formulaLegend: '⑻',
    formulaExpr: '生产成本明细账制造费用',
    dataSource: '生产成本明细账',
    defaultIndexRef: 'wp:F5-2',
    legacyKeys: ['overhead'],
  },
  {
    rowKey: 'overheadMaterialTransfer', seqNo: '', label: '其中：材料费用',
    rowType: 'detail',
    formulaLegend: '⑻明细',
    formulaExpr: '转入制造费用的材料费用（不计入产品生产成本合计，仅作明细披露）',
    dataSource: '“材料”转入“制造费用”借方金额',
    defaultIndexRef: 'wp:F2',
  },
  {
    rowKey: 'specialTooling', seqNo: '⑼', label: '专用工模具',
    rowType: 'input',
    formulaLegend: '⑼',
    formulaExpr: '生产成本明细账专用工模具',
    dataSource: '生产成本明细账',
    defaultIndexRef: 'wp:F5-2',
  },
  {
    rowKey: 'productProductionCost', seqNo: '⑽', label: '产品生产成本',
    rowType: 'formula',
    formulaLegend: '⑽=⑹+⑺+⑻+⑼',
    formulaExpr: '产品生产成本 = 直接材料成本 + 直接人工 + 制造费用 + 专用工模具（不含「其中：材料费用」明细）',
    dataSource: '“生产成本”借方发生额',
    defaultIndexRef: '',
    isResult: true,
  },
  {
    rowKey: 'openingWIP', seqNo: '⑾', label: '加：在产品期初余额',
    rowType: 'input',
    formulaLegend: '⑾',
    formulaExpr: '生产成本/在产品期初余额',
    dataSource: '“生产成本”期初余额',
    defaultIndexRef: 'tb:1404',
    tbField: 'openingWIP',
  },
  {
    rowKey: 'closingWIP', seqNo: '⑿', label: '减：在产品期末余额',
    rowType: 'input',
    formulaLegend: '⑿',
    formulaExpr: '生产成本/在产品期末余额',
    dataSource: '“生产成本”期末余额',
    defaultIndexRef: 'tb:1404',
    tbField: 'closingWIP',
  },
  {
    rowKey: 'finishedGoodsCost', seqNo: '⒀', label: '产成品（库存商品）成本',
    rowType: 'formula',
    formulaLegend: '⒀=⑽+⑾−⑿',
    formulaExpr: '产成品成本 = 产品生产成本 + 在产品期初 − 在产品期末',
    dataSource: '“生产成本”转入“产成品”借方金额',
    defaultIndexRef: 'wp:F2',
    isResult: true,
  },
  {
    rowKey: 'openingFG', seqNo: '⒁', label: '加：产成品期初余额',
    rowType: 'input',
    formulaLegend: '⒁',
    formulaExpr: '产成品/库存商品期初余额',
    dataSource: '“产成品”账户期初余额',
    defaultIndexRef: 'tb:1405',
    tbField: 'openingFG',
  },
  {
    rowKey: 'fgOtherIncrease', seqNo: '⒂', label: '加：其他增加额',
    rowType: 'input',
    formulaLegend: '⒂',
    formulaExpr: '产成品借方其他增加',
    dataSource: '产成品其他增加记录',
    defaultIndexRef: 'wp:F2',
  },
  {
    rowKey: 'closingFG', seqNo: '⒃', label: '减：产成品期末余额',
    rowType: 'input',
    formulaLegend: '⒃',
    formulaExpr: '产成品/库存商品期末余额',
    dataSource: '“产成品”账户期末余额',
    defaultIndexRef: 'tb:1405',
    tbField: 'closingFG',
  },
  {
    rowKey: 'selfUseProductCost', seqNo: '⒄', label: '减：自制自用产品成本',
    rowType: 'input',
    formulaLegend: '⒄',
    formulaExpr: '产成品转入生产成本等自制自用',
    dataSource: '“产成品”转入“生产成本”借方金额',
    defaultIndexRef: 'wp:F2',
  },
  {
    rowKey: 'internalUseProductCost', seqNo: '⒅', label: '减：内部领用产品成本',
    rowType: 'input',
    formulaLegend: '⒅',
    formulaExpr: '内部领用产成品成本',
    dataSource: '内部领用记录',
    defaultIndexRef: 'wp:F2',
  },
  {
    rowKey: 'fgOtherIssue', seqNo: '⒆', label: '减：其他产成品发出额',
    rowType: 'input',
    formulaLegend: '⒆',
    formulaExpr: '产成品折价、盘亏、废损等发出',
    dataSource: '产成品折价、盘亏、废损会计记录',
    defaultIndexRef: 'wp:F2',
    legacyKeys: ['otherIssue2'],
  },
  {
    rowKey: 'mainBusinessCOGS', seqNo: '⒇', label: '主营业务成本',
    rowType: 'formula',
    formulaLegend: '⒇=⒀+⒁+⒂−⒃−⒄−⒅−⒆',
    formulaExpr: '主营业务成本 = 产成品成本 + 产成品期初 + 其他增加 − 产成品期末 − 自制自用 − 内部领用 − 其他发出',
    dataSource: '与 F5-1 主营业务成本审定核对',
    defaultIndexRef: 'wp:F5-1',
    isResult: true,
  },
]

const TB_FIELDS = [
  'openingMaterial', 'closingMaterial',
  'openingWIP', 'closingWIP',
  'openingFG', 'closingFG',
] as const

const EDITABLE_LEGACY = [
  'purchase', 'directLabor', 'overhead', 'otherIssue1', 'otherIssue2',
  'materialPurchaseNet', 'materialOtherIncrease', 'materialOtherIssue',
  'manufacturingOverhead', 'specialTooling', 'overheadMaterialTransfer',
  'fgOtherIncrease', 'selfUseProductCost', 'internalUseProductCost', 'fgOtherIssue',
] as const

function emptyAmount(): StoredAmount {
  return { unadjusted: 0, aje: 0, prior: 0, indexRef: '' }
}

function migrateStored(raw: unknown): Record<string, StoredAmount> {
  const out: Record<string, StoredAmount> = {}
  for (const def of F57_ROW_DEFS) {
    if (def.rowType === 'formula') continue
    out[def.rowKey] = emptyAmount()
  }
  if (!raw || typeof raw !== 'object') return out
  const obj = raw as Record<string, any>

  // 新格式：{ rows: { rowKey: { unadjusted, aje, prior, indexRef } } }
  if (obj.rows && typeof obj.rows === 'object') {
    for (const def of F57_ROW_DEFS) {
      if (def.rowType === 'formula') continue
      const r = obj.rows[def.rowKey]
      if (!r) continue
      out[def.rowKey] = {
        unadjusted: parseNum(r.unadjusted ?? r.E),
        aje: parseNum(r.aje ?? r.F),
        prior: parseNum(r.prior ?? r.H),
        indexRef: String(r.indexRef ?? ''),
      }
    }
    return out
  }

  // 旧扁平单金额：字段 → unadjusted
  const legacyMap: Record<string, string> = {
    purchase: 'materialPurchaseNet',
    otherIssue1: 'materialOtherIssue',
    overhead: 'manufacturingOverhead',
    otherIssue2: 'fgOtherIssue',
  }
  for (const [k, v] of Object.entries(obj)) {
    if (typeof v === 'object' && v !== null && ('unadjusted' in v || 'aje' in v)) {
      const key = legacyMap[k] ?? k
      if (out[key]) {
        out[key] = {
          unadjusted: parseNum((v as any).unadjusted),
          aje: parseNum((v as any).aje),
          prior: parseNum((v as any).prior),
          indexRef: String((v as any).indexRef ?? ''),
        }
      }
      continue
    }
    const key = legacyMap[k] ?? k
    if (out[key] && typeof v !== 'object') {
      out[key].unadjusted = parseNum(v)
    }
  }
  return out
}

function amt(stored: Record<string, StoredAmount>, key: string, field: keyof StoredAmount): number {
  if (field === 'indexRef') return 0
  return parseNum(stored[key]?.[field as 'unadjusted' | 'aje' | 'prior'])
}

function rollCol(
  stored: Record<string, StoredAmount>,
  field: 'unadjusted' | 'aje' | 'prior',
  fn: (...args: number[]) => number,
  keys: string[],
): number {
  return fn(...keys.map((k) => amt(stored, k, field)))
}

export function useF5CostRollforward(options: UseF5CostRollforwardOptions) {
  const { allResponses, isReadonly, materiality, adjudicatedCOGS } = options
  const readonly = isReadonly ?? ref(false)
  const materialityRef = materiality ?? ref(0)
  const extAdjudicated = adjudicatedCOGS ?? ref(0)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  let lastPersisted = ''

  const storedRows = ref<Record<string, StoredAmount>>(migrateStored(null))
  const auditNote = ref('')
  const auditConclusion = ref('')

  function rawJson(): string | null | undefined {
    return allResponses.value.get(STORAGE_KEY)?.remark
  }

  function load(): void {
    try {
      const raw = rawJson()
      storedRows.value = migrateStored(raw ? JSON.parse(raw) : null)
    } catch {
      storedRows.value = migrateStored(null)
    }
  }

  watch(() => rawJson(), (raw) => {
    if (raw && raw === lastPersisted) return
    load()
  }, { immediate: true })

  watch(
    () => [
      allResponses.value.get(NOTE_KEY)?.remark,
      allResponses.value.get(CONCLUSION_KEY)?.remark
        ?? allResponses.value.get(LEGACY_CONCLUSION_KEY)?.remark,
    ],
    ([note, conclusion]) => {
      auditNote.value = typeof note === 'string' ? note : ''
      auditConclusion.value = typeof conclusion === 'string' ? conclusion : ''
    },
    { immediate: true },
  )

  function computeAmountSet(field: 'unadjusted' | 'aje' | 'prior') {
    const dm = rollCol(storedRows.value, field, calcF57DirectMaterial, [
      'openingMaterial', 'materialPurchaseNet', 'materialOtherIncrease', 'closingMaterial', 'materialOtherIssue',
    ])
    const pc = calcF57ProductionCost(
      dm,
      amt(storedRows.value, 'directLabor', field),
      amt(storedRows.value, 'manufacturingOverhead', field),
      amt(storedRows.value, 'specialTooling', field),
    )
    const fg = calcF57FinishedGoodsCost(
      pc,
      amt(storedRows.value, 'openingWIP', field),
      amt(storedRows.value, 'closingWIP', field),
    )
    const cogs = calcF57MainBusinessCOGS(
      fg,
      amt(storedRows.value, 'openingFG', field),
      amt(storedRows.value, 'fgOtherIncrease', field),
      amt(storedRows.value, 'closingFG', field),
      amt(storedRows.value, 'selfUseProductCost', field),
      amt(storedRows.value, 'internalUseProductCost', field),
      amt(storedRows.value, 'fgOtherIssue', field),
    )
    return { dm, pc, fg, cogs }
  }

  const rows: ComputedRef<F57RowView[]> = computed(() => {
    const u = computeAmountSet('unadjusted')
    const a = computeAmountSet('aje')
    const p = computeAmountSet('prior')
    const formulaMap: Record<string, { unadjusted: number; aje: number; prior: number }> = {
      directMaterialCost: { unadjusted: u.dm, aje: a.dm, prior: p.dm },
      productProductionCost: { unadjusted: u.pc, aje: a.pc, prior: p.pc },
      finishedGoodsCost: { unadjusted: u.fg, aje: a.fg, prior: p.fg },
      mainBusinessCOGS: { unadjusted: u.cogs, aje: a.cogs, prior: p.cogs },
    }

    return F57_ROW_DEFS.map((def) => {
      if (def.rowType === 'formula') {
        const f = formulaMap[def.rowKey]
        const unadjusted = f.unadjusted
        const aje = f.aje
        // 审定列：对公式行按各输入行审定轧差（= 未审轧差 + 调整轧差），与源表 G=SUM(G) 一致
        const audited = unadjusted + aje
        return {
          ...def,
          unadjusted,
          aje,
          audited,
          prior: f.prior,
          indexRef: def.defaultIndexRef,
        }
      }
      const s = storedRows.value[def.rowKey] ?? emptyAmount()
      const unadjusted = parseNum(s.unadjusted)
      const ajeVal = parseNum(s.aje)
      return {
        ...def,
        unadjusted,
        aje: ajeVal,
        audited: calcAdjustedAmount(unadjusted, ajeVal, 0),
        prior: parseNum(s.prior),
        indexRef: (s.indexRef && String(s.indexRef)) || def.defaultIndexRef,
      }
    })
  })

  const mainCogsRow = computed(() => rows.value.find((r) => r.rowKey === 'mainBusinessCOGS')!)

  /** 兼容旧 API：data 聚合视图（取未审数口径，与历史测试一致） */
  const data = computed(() => {
    const byKey = Object.fromEntries(rows.value.map((r) => [r.rowKey, r]))
    const localAdjudicated = parseNum(allResponses.value.get(ADJUDICATED_KEY)?.remark)
    const adjudicated = extAdjudicated.value || localAdjudicated
    const cogs = byKey.mainBusinessCOGS?.unadjusted ?? 0
    return {
      openingMaterial: byKey.openingMaterial?.unadjusted ?? 0,
      purchase: byKey.materialPurchaseNet?.unadjusted ?? 0,
      closingMaterial: byKey.closingMaterial?.unadjusted ?? 0,
      otherIssue1: byKey.materialOtherIssue?.unadjusted ?? 0,
      materialInput: byKey.directMaterialCost?.unadjusted ?? 0,
      directLabor: byKey.directLabor?.unadjusted ?? 0,
      overhead: byKey.manufacturingOverhead?.unadjusted ?? 0,
      totalProductionCost: byKey.productProductionCost?.unadjusted ?? 0,
      openingWIP: byKey.openingWIP?.unadjusted ?? 0,
      closingWIP: byKey.closingWIP?.unadjusted ?? 0,
      finishedGoodsCost: byKey.finishedGoodsCost?.unadjusted ?? 0,
      openingFG: byKey.openingFG?.unadjusted ?? 0,
      closingFG: byKey.closingFG?.unadjusted ?? 0,
      otherIssue2: byKey.fgOtherIssue?.unadjusted ?? 0,
      cogs,
      adjudicatedCOGS: adjudicated,
      rollforwardVariance: adjudicated - (byKey.mainBusinessCOGS?.audited ?? cogs),
      /** 审定口径倒轧主营业务成本（校验区优先用） */
      cogsAudited: byKey.mainBusinessCOGS?.audited ?? cogs,
    }
  })

  const varianceExceedsMateriality = computed(() => {
    const m = materialityRef.value
    const v = Math.abs(data.value.rollforwardVariance)
    if (m <= 0) return v > 0.01
    return v > m
  })

  function persist(): void {
    const payload = { rows: storedRows.value, version: 2 }
    const json = JSON.stringify(payload)
    lastPersisted = json
    allResponses.value.set(STORAGE_KEY, { item_id: STORAGE_KEY, conclusion: null, remark: json })
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 1200)
  }

  function flushSave(): void {
    const items = [
      allResponses.value.get(STORAGE_KEY),
      allResponses.value.get(NOTE_KEY),
      allResponses.value.get(CONCLUSION_KEY),
      allResponses.value.get(ADJUDICATED_KEY),
    ].filter(Boolean)
    if (items.length) {
      window.dispatchEvent(new CustomEvent('f5:save-items', { detail: { items } }))
    }
  }

  function resolveRowKey(field: string): string | null {
    if (storedRows.value[field]) return field
    const legacy: Record<string, string> = {
      purchase: 'materialPurchaseNet',
      otherIssue1: 'materialOtherIssue',
      overhead: 'manufacturingOverhead',
      otherIssue2: 'fgOtherIssue',
    }
    return legacy[field] ?? null
  }

  function isEditable(field: string): boolean {
    const key = resolveRowKey(field) ?? field
    if ((TB_FIELDS as readonly string[]).includes(key)) return false
    const def = F57_ROW_DEFS.find((d) => d.rowKey === key)
    return def?.rowType === 'input' || def?.rowType === 'detail'
      || (EDITABLE_LEGACY as readonly string[]).includes(field)
  }

  function isTbField(field: string): boolean {
    const key = resolveRowKey(field) ?? field
    return (TB_FIELDS as readonly string[]).includes(key)
  }

  function updateAmount(rowKey: string, field: F57AmountField, value: number | string): void {
    if (readonly.value) return
    const def = F57_ROW_DEFS.find((d) => d.rowKey === rowKey)
    if (!def || def.rowType === 'formula') return
    if (!storedRows.value[rowKey]) storedRows.value[rowKey] = emptyAmount()
    storedRows.value[rowKey][field] = parseNum(value)
    persist()
  }

  function updateIndexRef(rowKey: string, indexRef: string): void {
    if (readonly.value) return
    const def = F57_ROW_DEFS.find((d) => d.rowKey === rowKey)
    if (!def || def.rowType === 'formula') return
    if (!storedRows.value[rowKey]) storedRows.value[rowKey] = emptyAmount()
    storedRows.value[rowKey].indexRef = String(indexRef ?? '')
    persist()
  }

  /** 旧 API：按扁平字段更新未审数 */
  function updateField(field: string, value: number | string): void {
    if (readonly.value) return
    const key = resolveRowKey(field)
    if (!key) return
    if (!isEditable(field) && !isTbField(field)) return
    updateAmount(key, 'unadjusted', value)
  }

  function setTbValues(values: Partial<Record<(typeof TB_FIELDS)[number], number>>): void {
    for (const [k, v] of Object.entries(values)) {
      if (!(TB_FIELDS as readonly string[]).includes(k)) continue
      if (!storedRows.value[k]) storedRows.value[k] = emptyAmount()
      storedRows.value[k].unadjusted = parseNum(v)
    }
    persist()
  }

  function setAdjudicatedCOGS(amount: number): void {
    allResponses.value.set(ADJUDICATED_KEY, {
      item_id: ADJUDICATED_KEY,
      conclusion: null,
      remark: String(parseNum(amount)),
    })
    debounceSave()
  }

  function saveAuditNote(value: string): void {
    if (readonly.value) return
    auditNote.value = value
    allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: value })
    debounceSave()
  }

  function saveAuditConclusion(value: string): void {
    if (readonly.value) return
    auditConclusion.value = value
    allResponses.value.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: value })
    debounceSave()
  }

  /** 兼容旧 v-model auditConclusion */
  const auditConclusionCompat = computed<string>({
    get: () => auditConclusion.value,
    set: (val) => { saveAuditConclusion(val) },
  })

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  return {
    rows,
    mainCogsRow,
    data,
    varianceExceedsMateriality,
    auditNote,
    auditConclusion: auditConclusionCompat,
    isEditable,
    isTbField,
    updateField,
    updateAmount,
    updateIndexRef,
    setTbValues,
    setAdjudicatedCOGS,
    saveAuditNote,
    saveAuditConclusion,
    editableFields: EDITABLE_LEGACY,
    tbFields: TB_FIELDS,
    rowDefs: F57_ROW_DEFS,
  }
}

export default useF5CostRollforward
