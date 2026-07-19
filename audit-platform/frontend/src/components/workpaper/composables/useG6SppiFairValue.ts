/**
 * useG6SppiFairValue — G6-5 公允价值测试表（对齐 Excel 18列）
 *
 * 改进相对旧实现：
 * 1. 公允价值 = 数量 × 单位公允价值（自动计算，不可手填）
 * 2. 未审/审定公允价值层次分列
 * 3. 差异分解：数量影响 + 价格影响 = 总差异
 * 4. L1/L2/L3 分层必填校验；差异阈值 0.01
 * 5. 合计行 + 审定层次分布
 */
import { ref, computed, watch } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import {
  calcFairValueAmount,
  calcFairValueDiff,
  calcFairValueQtyImpact,
  calcFairValuePriceImpact,
  parseNum,
} from '@/composables/useG6SppiFormulaEngine'

/** 差异高亮阈值（忽略舍入噪声） */
export const G6_FV_DIFF_THRESHOLD = 0.01

export type FairValueLevel = 'L1' | 'L2' | 'L3' | ''

export interface FairValueItem {
  id: string
  seq: number
  investProject: string
  // 期末未审
  unadjQty: number
  unadjPrice: number
  unadjFairValue: number // 公式
  unadjFairValueLevel: FairValueLevel
  // 期末审定
  auditedQty: number
  auditedPrice: number
  auditedFairValue: number // 公式
  auditedFairValueLevel: FairValueLevel
  // 差异分解（公式）
  qtyImpact: number
  priceImpact: number
  difference: number
  diffReason: string
  // 估值方法
  valuationMethod: string
  consistencyWithPrior: string
  // 分层估值证据
  sourceInstitution: string // L1/L2 来源
  inputSource: string // L2 可观察输入值说明
  valuationTechnique: string // L3 估值技术
  unobservableInputs: string // L3 不可观察输入值
  inputValue: string // L3 输入值/估值结果
  valuationFileRef: string
  /** @deprecated 兼容旧单层次字段 */
  fairValueLevel?: FairValueLevel
  /** @deprecated 模板外字段，迁移兼容 */
  faceValue?: number
}

export interface FairValueTestData {
  rows: FairValueItem[]
  conclusion: string
}

export interface FairValueTotals {
  unadjFairValue: number
  auditedFairValue: number
  qtyImpact: number
  priceImpact: number
  difference: number
}

function emptyRow(id: string, seq: number, name = ''): FairValueItem {
  return {
    id,
    seq,
    investProject: name,
    unadjQty: 0,
    unadjPrice: 0,
    unadjFairValue: 0,
    unadjFairValueLevel: '',
    auditedQty: 0,
    auditedPrice: 0,
    auditedFairValue: 0,
    auditedFairValueLevel: '',
    qtyImpact: 0,
    priceImpact: 0,
    difference: 0,
    diffReason: '',
    valuationMethod: '',
    consistencyWithPrior: '',
    sourceInstitution: '',
    inputSource: '',
    valuationTechnique: '',
    unobservableInputs: '',
    inputValue: '',
    valuationFileRef: '',
  }
}

/** 公式链重算 */
export function enrichFairValueRow(row: FairValueItem): FairValueItem {
  const unadjFairValue = calcFairValueAmount(row.unadjQty, row.unadjPrice)
  const auditedFairValue = calcFairValueAmount(row.auditedQty, row.auditedPrice)
  const qtyImpact = calcFairValueQtyImpact(row.auditedQty, row.unadjQty, row.unadjPrice)
  const priceImpact = calcFairValuePriceImpact(row.auditedQty, row.auditedPrice, row.unadjPrice)
  const difference = calcFairValueDiff(auditedFairValue, unadjFairValue)
  return {
    ...row,
    unadjFairValue,
    auditedFairValue,
    qtyImpact,
    priceImpact,
    difference,
  }
}

function migrateLevel(raw: any): { unadj: FairValueLevel; audited: FairValueLevel } {
  const legacy = (raw.fairValueLevel || '') as FairValueLevel
  const unadj = (raw.unadjFairValueLevel || legacy || '') as FairValueLevel
  const audited = (raw.auditedFairValueLevel || legacy || '') as FairValueLevel
  return { unadj, audited }
}

export function migrateFairValueRow(raw: any, seq: number): FairValueItem {
  const levels = migrateLevel(raw)
  const base = emptyRow(String(raw.id || `fv-${Date.now()}-${seq}`), seq, raw.investProject || '')
  // 若旧数据只存了公允价值而无单价，尽量反推单价
  let unadjQty = parseNum(raw.unadjQty)
  let unadjPrice = parseNum(raw.unadjPrice)
  let auditedQty = parseNum(raw.auditedQty)
  let auditedPrice = parseNum(raw.auditedPrice)
  const legacyUnadjFv = parseNum(raw.unadjFairValue)
  const legacyAuditedFv = parseNum(raw.auditedFairValue)
  if (!unadjPrice && unadjQty && legacyUnadjFv) {
    unadjPrice = Math.round((legacyUnadjFv / unadjQty) * 10000) / 10000
  }
  if (!auditedPrice && auditedQty && legacyAuditedFv) {
    auditedPrice = Math.round((legacyAuditedFv / auditedQty) * 10000) / 10000
  }
  // 旧数据只有 FV 无数量：默认数量=1，单价=FV
  if (!unadjQty && !unadjPrice && legacyUnadjFv) {
    unadjQty = 1
    unadjPrice = legacyUnadjFv
  }
  if (!auditedQty && !auditedPrice && legacyAuditedFv) {
    auditedQty = 1
    auditedPrice = legacyAuditedFv
  }

  return enrichFairValueRow({
    ...base,
    unadjQty,
    unadjPrice,
    unadjFairValueLevel: levels.unadj,
    auditedQty,
    auditedPrice,
    auditedFairValueLevel: levels.audited,
    fairValueLevel: levels.audited || levels.unadj,
    faceValue: raw.faceValue !== undefined ? parseNum(raw.faceValue) : undefined,
    diffReason: String(raw.diffReason || ''),
    valuationMethod: String(raw.valuationMethod || ''),
    consistencyWithPrior: String(raw.consistencyWithPrior || ''),
    sourceInstitution: String(raw.sourceInstitution || ''),
    inputSource: String(raw.inputSource || ''),
    valuationTechnique: String(raw.valuationTechnique || ''),
    unobservableInputs: String(raw.unobservableInputs || ''),
    inputValue: String(raw.inputValue || ''),
    valuationFileRef: String(raw.valuationFileRef || ''),
  })
}

/** 按审定层次做必填校验 */
export function getLevelValidationErrors(row: FairValueItem): string[] {
  const level = row.auditedFairValueLevel || row.fairValueLevel || ''
  const errors: string[] = []
  if (level === 'L1') {
    if (!row.sourceInstitution) errors.push('公允价值来源说明')
  } else if (level === 'L2') {
    if (!row.valuationMethod) errors.push('估值方法')
    if (!row.inputSource) errors.push('可观察输入值来源')
  } else if (level === 'L3') {
    if (!row.valuationMethod) errors.push('估值方法')
    if (!row.valuationTechnique) errors.push('估值技术')
    if (!row.unobservableInputs) errors.push('不可观察输入值')
    if (!row.inputValue) errors.push('输入值/估值结果')
    if (!row.valuationFileRef) errors.push('估值文件索引')
  }
  return errors
}

export function useG6SppiFairValue() {
  const rows = ref<FairValueItem[]>([])
  const activeTab = ref<'tab1' | 'tab2'>('tab1')
  const selectedRowIndex = ref(0)
  const conclusion = ref('')

  function recalcRow(row: FairValueItem): void {
    const enriched = enrichFairValueRow(row)
    Object.assign(row, enriched)
  }

  watch(rows, (newRows) => {
    for (const row of newRows) recalcRow(row)
  }, { deep: true })

  function hasDifference(row: FairValueItem): boolean {
    return Math.abs(parseNum(row.difference)) > G6_FV_DIFF_THRESHOLD
  }

  function getDiffCellStyle(row: FairValueItem): Record<string, string> {
    if (hasDifference(row)) {
      return { backgroundColor: '#fef2f2', color: '#dc2626', fontWeight: '600' }
    }
    return {}
  }

  function isLevel3(row: FairValueItem): boolean {
    return (row.auditedFairValueLevel || row.fairValueLevel) === 'L3'
  }

  /** @deprecated 兼容旧测试名：按审定层次校验 */
  function getL3ValidationErrors(row: FairValueItem): string[] {
    return getLevelValidationErrors(row)
  }

  function hasL3Errors(row: FairValueItem): boolean {
    return getLevelValidationErrors(row).length > 0
  }

  const l3ValidationSummary = computed(() => {
    const issues: Array<{ row: FairValueItem; errors: string[] }> = []
    for (const row of rows.value) {
      const errors = getLevelValidationErrors(row)
      if (errors.length > 0) issues.push({ row, errors })
    }
    return issues
  })

  const totals = computed<FairValueTotals>(() => {
    let unadjFairValue = 0
    let auditedFairValue = 0
    let qtyImpact = 0
    let priceImpact = 0
    let difference = 0
    for (const r of rows.value) {
      unadjFairValue += parseNum(r.unadjFairValue)
      auditedFairValue += parseNum(r.auditedFairValue)
      qtyImpact += parseNum(r.qtyImpact)
      priceImpact += parseNum(r.priceImpact)
      difference += parseNum(r.difference)
    }
    return {
      unadjFairValue: Math.round(unadjFairValue * 100) / 100,
      auditedFairValue: Math.round(auditedFairValue * 100) / 100,
      qtyImpact: Math.round(qtyImpact * 100) / 100,
      priceImpact: Math.round(priceImpact * 100) / 100,
      difference: Math.round(difference * 100) / 100,
    }
  })

  async function addRow(): Promise<void> {
    try {
      const { value } = await ElMessageBox.prompt(
        '请输入投资项目名称',
        '新增公允价值测试行',
        {
          confirmButtonText: '确认',
          cancelButtonText: '取消',
          inputPattern: /\S+/,
          inputErrorMessage: '投资项目名称不能为空',
          inputPlaceholder: '例如：XX公司债券',
        },
      )
      if (!value?.trim()) return
      const newRow = enrichFairValueRow(
        emptyRow(`fv-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`, rows.value.length + 1, value.trim()),
      )
      rows.value.push(newRow)
      selectedRowIndex.value = rows.value.length - 1
      ElMessage.success(`已新增"${value.trim()}"`)
    } catch {
      /* cancel */
    }
  }

  async function removeRow(id: string): Promise<void> {
    const row = rows.value.find(r => r.id === id)
    if (!row) return
    try {
      await ElMessageBox.confirm(
        `确认删除"${row.investProject}"？`,
        '删除确认',
        { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' },
      )
      rows.value = rows.value.filter(r => r.id !== id)
      rows.value.forEach((r, i) => { r.seq = i + 1 })
      if (selectedRowIndex.value >= rows.value.length) {
        selectedRowIndex.value = Math.max(0, rows.value.length - 1)
      }
      ElMessage.success(`已删除"${row.investProject}"`)
    } catch {
      /* cancel */
    }
  }

  /** 可编辑字段（公允价值公式列不可写） */
  const FORMULA_FIELDS = new Set([
    'unadjFairValue', 'auditedFairValue', 'qtyImpact', 'priceImpact', 'difference',
  ])

  function updateRow(id: string, field: keyof FairValueItem, value: any): void {
    if (FORMULA_FIELDS.has(field)) return
    const row = rows.value.find(r => r.id === id)
    if (!row) return
    ;(row as any)[field] = value
    // 兼容：改审定层次时同步 fairValueLevel
    if (field === 'auditedFairValueLevel') {
      row.fairValueLevel = value as FairValueLevel
    }
    recalcRow(row)
  }

  function loadData(data: FairValueTestData | null): void {
    if (!data?.rows?.length) {
      rows.value = []
      conclusion.value = data?.conclusion || ''
      return
    }
    rows.value = data.rows.map((r, i) => migrateFairValueRow(r, i + 1))
    conclusion.value = data.conclusion || ''
  }

  function toJSON(): FairValueTestData {
    return {
      rows: rows.value.map(r => ({ ...r })),
      conclusion: conclusion.value,
    }
  }

  const levelSummary = computed(() => {
    const summary = { L1: 0, L2: 0, L3: 0, unset: 0 }
    for (const row of rows.value) {
      const lv = row.auditedFairValueLevel || row.fairValueLevel || ''
      if (lv === 'L1') summary.L1++
      else if (lv === 'L2') summary.L2++
      else if (lv === 'L3') summary.L3++
      else summary.unset++
    }
    return summary
  })

  const diffCount = computed(() => rows.value.filter(hasDifference).length)

  /** 差异行缺原因提示 */
  const missingDiffReasonCount = computed(() =>
    rows.value.filter(r => hasDifference(r) && !String(r.diffReason || '').trim()).length,
  )

  return {
    rows,
    activeTab,
    selectedRowIndex,
    conclusion,
    l3ValidationSummary,
    levelSummary,
    diffCount,
    missingDiffReasonCount,
    totals,
    recalcRow,
    hasDifference,
    getDiffCellStyle,
    isLevel3,
    getL3ValidationErrors,
    getLevelValidationErrors,
    hasL3Errors,
    addRow,
    removeRow,
    updateRow,
    loadData,
    toJSON,
  }
}

export default useG6SppiFairValue
