/**
 * useD6Detail — D6-2 明细表30列核心逻辑 composable
 *
 * Spec: .kiro/specs/d6-contract-assets/
 * Task: 7.1
 *
 * 职责：
 * - 定义 DetailRow 类型（30列完整字段：序号~期后结转金额）
 * - rows reactive（从D6-2-rows加载JSON数组）
 * - 行内公式自动计算：期初审定(10)=7+8+9; 期末未审(17)=10+15-16(借方!); 期末审定(20)=17+18+19
 * - subtotalByType computed（按合同类型小计：工程施工/质量保证金/其他）
 * - classificationRows computed（附加分类行）
 * - totalRow computed（总合计=SUM所有明细行）
 * - addRow/removeRow/updateCell
 * - importFromAuxBalance（调后端API从tb_aux_balance科目1141按客户/合同维度导入）
 * - searchFilter + filteredRows computed（按合同名称/客户名称模糊搜索）
 *
 * Requirements: 5.1-5.14, 6.1-6.8, 7.1-7.5
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import {
  parseNum,
  calcAuditedAmount,
  calcEndUnadjustedDebit,
  calcEndAudited,
  calcSubtotal,
} from './useD6FormulaEngine'
import { api } from '@/services/apiProxy'
import type { ChecklistResponse } from './useD6FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface DetailRow {
  rowId: string
  seqNo: number                    // 1: 序号
  contractName: string             // 2: 合同名称/项目名称
  contractType: string             // 3: 类型（工程施工/质量保证金/其他）
  customerName: string             // 4: 客户名称
  companyCode: string              // 5: 公司代码
  relatedPartyType: string         // 6: 关联关系
  priorUnadjusted: number          // 7: 期初未审数
  priorAje: number                 // 8: 期初账项调整
  priorRje: number                 // 9: 期初重分类调整
  priorAudited: number             // 10: 期初审定余额 = 7+8+9（自动）
  agePrior1y: number               // 11: 期初账龄-1年以下
  agePrior1to2y: number            // 12: 期初账龄-1~2年
  agePrior2to3y: number            // 13: 期初账龄-2~3年
  agePrior3yAbove: number          // 14: 期初账龄-3年以上
  debitAmount: number              // 15: 借方发生
  creditAmount: number             // 16: 贷方发生
  endUnadjusted: number            // 17: 期末未审余额 = 10+15-16（借方科目！自动）
  endAje: number                   // 18: 账项调整
  endRje: number                   // 19: 重分类调整
  endAudited: number               // 20: 期末审定余额 = 17+18+19（自动）
  ageEnd1y: number                 // 21: 期末账龄-1年以下
  ageEnd1to2y: number              // 22: 期末账龄-1~2年
  ageEnd2to3y: number              // 23: 期末账龄-2~3年
  ageEnd3yAbove: number            // 24: 期末账龄-3年以上
  receivableWithin1y: number       // 25: 1年以内收款权
  receivableAbove1y: number        // 26: 1年以上收款权
  isInConstructionPeriod: string   // 27: 是否在建设期或质保期内（是/否）
  creditRiskGroup: string          // 28: 信用风险组合方式
  isConfirmed: string              // 29: 是否函证
  postPeriodSettlement: number     // 30: 期后结转金额
}

export interface UseD6DetailOptions {
  allResponses: Ref<Map<string, any>>
  saveImmediate: (itemId: string, data: any) => Promise<void>
  debouncedSave: (itemId: string, data: any) => void
  wpId: Ref<string>
  projectId: Ref<string>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'D6-2-rows'

/** 合同类型下拉选项 */
export const CONTRACT_TYPES = ['工程施工', '质量保证金', '其他'] as const

/** 关联关系下拉选项 */
export const RELATED_PARTY_TYPES = [
  '非关联方',
  '实际控制人',
  '控股股东',
  '控股股东附属企业',
  '持有5%以上表决权股份的股东',
  '联营企业',
  '合营企业',
  '董事/监事/高管',
  '其他关联方',
] as const

/** 信用风险组合方式下拉选项 */
export const CREDIT_RISK_GROUPS = [
  '单项计提',
  '业务类型组合',
  '客户类型组合',
] as const

/** 是否在建设期/质保期下拉 */
export const CONSTRUCTION_PERIOD_OPTIONS = ['是', '否'] as const

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `row-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
}

/** 安全解析 JSON 数组 */
function safeParseRows(jsonStr: string | null | undefined): DetailRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed.map(normalizeRow) : []
  } catch {
    return []
  }
}

/** 规范化行数据，确保所有字段存在且类型正确 */
function normalizeRow(raw: any): DetailRow {
  return {
    rowId: raw.rowId || generateRowId(),
    seqNo: parseNum(raw.seqNo),
    contractName: raw.contractName || '',
    contractType: raw.contractType || '',
    customerName: raw.customerName || '',
    companyCode: raw.companyCode || '',
    relatedPartyType: raw.relatedPartyType || '',
    priorUnadjusted: parseNum(raw.priorUnadjusted),
    priorAje: parseNum(raw.priorAje),
    priorRje: parseNum(raw.priorRje),
    priorAudited: parseNum(raw.priorAudited),
    agePrior1y: parseNum(raw.agePrior1y),
    agePrior1to2y: parseNum(raw.agePrior1to2y),
    agePrior2to3y: parseNum(raw.agePrior2to3y),
    agePrior3yAbove: parseNum(raw.agePrior3yAbove),
    debitAmount: parseNum(raw.debitAmount),
    creditAmount: parseNum(raw.creditAmount),
    endUnadjusted: parseNum(raw.endUnadjusted),
    endAje: parseNum(raw.endAje),
    endRje: parseNum(raw.endRje),
    endAudited: parseNum(raw.endAudited),
    ageEnd1y: parseNum(raw.ageEnd1y),
    ageEnd1to2y: parseNum(raw.ageEnd1to2y),
    ageEnd2to3y: parseNum(raw.ageEnd2to3y),
    ageEnd3yAbove: parseNum(raw.ageEnd3yAbove),
    receivableWithin1y: parseNum(raw.receivableWithin1y),
    receivableAbove1y: parseNum(raw.receivableAbove1y),
    isInConstructionPeriod: raw.isInConstructionPeriod || '',
    creditRiskGroup: raw.creditRiskGroup || '',
    isConfirmed: raw.isConfirmed || '',
    postPeriodSettlement: parseNum(raw.postPeriodSettlement),
  }
}

/**
 * 对单行重新计算公式链（借方科目）：
 * col10 = col7 + col8 + col9（期初审定 = 期初未审 + AJE + RJE）
 * col17 = col10 + col15 - col16（期末未审 = 期初审定 + 借方发生 - 贷方发生）← 借方科目！
 * col20 = col17 + col18 + col19（期末审定 = 期末未审 + 账项调整 + 重分类调整）
 */
export function recalcRow(row: DetailRow): DetailRow {
  const priorAudited = calcAuditedAmount(row.priorUnadjusted, row.priorAje, row.priorRje)
  const endUnadjusted = calcEndUnadjustedDebit(priorAudited, row.debitAmount, row.creditAmount)
  const endAudited = calcEndAudited(endUnadjusted, row.endAje, row.endRje)

  return {
    ...row,
    priorAudited,
    endUnadjusted,
    endAudited,
  }
}

/** 创建空行（所有数值为 0） */
export function createEmptyRow(seqNo: number): DetailRow {
  return {
    rowId: generateRowId(),
    seqNo,
    contractName: '',
    contractType: '',
    customerName: '',
    companyCode: '',
    relatedPartyType: '',
    priorUnadjusted: 0,
    priorAje: 0,
    priorRje: 0,
    priorAudited: 0,
    agePrior1y: 0,
    agePrior1to2y: 0,
    agePrior2to3y: 0,
    agePrior3yAbove: 0,
    debitAmount: 0,
    creditAmount: 0,
    endUnadjusted: 0,
    endAje: 0,
    endRje: 0,
    endAudited: 0,
    ageEnd1y: 0,
    ageEnd1to2y: 0,
    ageEnd2to3y: 0,
    ageEnd3yAbove: 0,
    receivableWithin1y: 0,
    receivableAbove1y: 0,
    isInConstructionPeriod: '',
    creditRiskGroup: '',
    isConfirmed: '',
    postPeriodSettlement: 0,
  }
}

/**
 * 计算一组行的各数值列合计（用于 subtotal / total）
 */
function sumRows(rows: DetailRow[], label: string): DetailRow {
  return {
    rowId: `__${label}__`,
    seqNo: 0,
    contractName: label,
    contractType: label,
    customerName: '',
    companyCode: '',
    relatedPartyType: '',
    priorUnadjusted: calcSubtotal(rows.map(r => r.priorUnadjusted)),
    priorAje: calcSubtotal(rows.map(r => r.priorAje)),
    priorRje: calcSubtotal(rows.map(r => r.priorRje)),
    priorAudited: calcSubtotal(rows.map(r => r.priorAudited)),
    agePrior1y: calcSubtotal(rows.map(r => r.agePrior1y)),
    agePrior1to2y: calcSubtotal(rows.map(r => r.agePrior1to2y)),
    agePrior2to3y: calcSubtotal(rows.map(r => r.agePrior2to3y)),
    agePrior3yAbove: calcSubtotal(rows.map(r => r.agePrior3yAbove)),
    debitAmount: calcSubtotal(rows.map(r => r.debitAmount)),
    creditAmount: calcSubtotal(rows.map(r => r.creditAmount)),
    endUnadjusted: calcSubtotal(rows.map(r => r.endUnadjusted)),
    endAje: calcSubtotal(rows.map(r => r.endAje)),
    endRje: calcSubtotal(rows.map(r => r.endRje)),
    endAudited: calcSubtotal(rows.map(r => r.endAudited)),
    ageEnd1y: calcSubtotal(rows.map(r => r.ageEnd1y)),
    ageEnd1to2y: calcSubtotal(rows.map(r => r.ageEnd1to2y)),
    ageEnd2to3y: calcSubtotal(rows.map(r => r.ageEnd2to3y)),
    ageEnd3yAbove: calcSubtotal(rows.map(r => r.ageEnd3yAbove)),
    receivableWithin1y: calcSubtotal(rows.map(r => r.receivableWithin1y)),
    receivableAbove1y: calcSubtotal(rows.map(r => r.receivableAbove1y)),
    isInConstructionPeriod: '',
    creditRiskGroup: '',
    isConfirmed: '',
    postPeriodSettlement: calcSubtotal(rows.map(r => r.postPeriodSettlement)),
  }
}

// ─── Classification Rows ─────────────────────────────────────────────────────

export interface ClassificationRow {
  label: string
  priorAudited: number
  endAudited: number
}

/**
 * 按关联方类型分类：合并范围内关联方/合并范围外关联方/非关联方
 * 按信用风险组合分类：单项计提/业务类型组合/客户类型组合
 */
function buildClassificationRows(rows: DetailRow[]): ClassificationRow[] {
  // 关联方分类
  const inScope = rows.filter(r =>
    r.relatedPartyType !== '' && r.relatedPartyType !== '非关联方',
  )
  const outScope: DetailRow[] = [] // 合并范围外关联方未单独标识，预留
  const nonRelated = rows.filter(r =>
    r.relatedPartyType === '非关联方' || r.relatedPartyType === '',
  )

  // 信用风险组合分类
  const singleProvision = rows.filter(r => r.creditRiskGroup === '单项计提')
  const bizTypeGroup = rows.filter(r => r.creditRiskGroup === '业务类型组合')
  const custTypeGroup = rows.filter(r => r.creditRiskGroup === '客户类型组合')

  return [
    {
      label: '合并范围内关联方',
      priorAudited: calcSubtotal(inScope.map(r => r.priorAudited)),
      endAudited: calcSubtotal(inScope.map(r => r.endAudited)),
    },
    {
      label: '合并范围外关联方',
      priorAudited: calcSubtotal(outScope.map(r => r.priorAudited)),
      endAudited: calcSubtotal(outScope.map(r => r.endAudited)),
    },
    {
      label: '非关联方',
      priorAudited: calcSubtotal(nonRelated.map(r => r.priorAudited)),
      endAudited: calcSubtotal(nonRelated.map(r => r.endAudited)),
    },
    {
      label: '单项计提',
      priorAudited: calcSubtotal(singleProvision.map(r => r.priorAudited)),
      endAudited: calcSubtotal(singleProvision.map(r => r.endAudited)),
    },
    {
      label: '业务类型组合',
      priorAudited: calcSubtotal(bizTypeGroup.map(r => r.priorAudited)),
      endAudited: calcSubtotal(bizTypeGroup.map(r => r.endAudited)),
    },
    {
      label: '客户类型组合',
      priorAudited: calcSubtotal(custTypeGroup.map(r => r.priorAudited)),
      endAudited: calcSubtotal(custTypeGroup.map(r => r.endAudited)),
    },
  ]
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD6Detail(options: UseD6DetailOptions) {
  const { allResponses, debouncedSave, wpId, projectId } = options

  // ─── Reactive rows ───────────────────────────────────────────────────

  const rows = ref<DetailRow[]>([])

  // Load rows from allResponses (D6-2-rows remark field stores JSON array)
  watch(
    () => allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (jsonStr) => {
      const parsed = safeParseRows(jsonStr)
      // Recalculate formula chain for each row
      rows.value = parsed.map(recalcRow)
    },
    { immediate: true },
  )

  // ─── Search/filter ───────────────────────────────────────────────────

  const searchFilter = ref('')

  /** 按合同名称/客户名称模糊搜索 */
  const filteredRows: ComputedRef<DetailRow[]> = computed(() => {
    const keyword = searchFilter.value.trim().toLowerCase()
    if (!keyword) return rows.value
    return rows.value.filter(r =>
      r.contractName.toLowerCase().includes(keyword) ||
      r.customerName.toLowerCase().includes(keyword),
    )
  })

  // ─── Persist ─────────────────────────────────────────────────────────

  function persistRows(): void {
    debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
  }

  // ─── subtotalByType computed ─────────────────────────────────────────

  /**
   * 按合同类型分组小计：工程施工 / 质量保证金 / 其他
   */
  const subtotalByType: ComputedRef<Record<string, DetailRow>> = computed(() => {
    const result: Record<string, DetailRow> = {}

    for (const cType of CONTRACT_TYPES) {
      const typeRows = rows.value.filter(r => r.contractType === cType)
      result[cType] = sumRows(typeRows, `${cType}小计`)
    }

    return result
  })

  // ─── classificationRows computed ─────────────────────────────────────

  /**
   * 附加分类行：
   * - 合并范围内关联方/合并范围外关联方/非关联方
   * - 单项计提/业务类型组合/客户类型组合
   */
  const classificationRows: ComputedRef<ClassificationRow[]> = computed(() => {
    return buildClassificationRows(rows.value)
  })

  // ─── totalRow computed ───────────────────────────────────────────────

  /**
   * 总合计行：所有明细行的各数值列SUM
   */
  const totalRow: ComputedRef<DetailRow> = computed(() => {
    return sumRows(rows.value, '合计')
  })

  // ─── addRow ──────────────────────────────────────────────────────────

  function addRow(): void {
    const nextSeqNo = rows.value.length > 0
      ? Math.max(...rows.value.map(r => r.seqNo)) + 1
      : 1
    const newRow = createEmptyRow(nextSeqNo)
    rows.value = [...rows.value, newRow]
    persistRows()
  }

  /**
   * 以完整数据新增一行（供弹窗依次录入使用）。
   * 自动分配序号、执行公式链重算并持久化。
   */
  function addRowWithData(data: Partial<DetailRow>): void {
    const nextSeqNo = rows.value.length > 0
      ? Math.max(...rows.value.map(r => r.seqNo)) + 1
      : 1
    const base = createEmptyRow(nextSeqNo)
    const merged = normalizeRow({ ...base, ...data, rowId: base.rowId, seqNo: nextSeqNo })
    rows.value = [...rows.value, recalcRow(merged)]
    persistRows()
  }

  /**
   * 以完整数据更新一行（供弹窗编辑使用）。保留 rowId/seqNo，重算公式链后持久化。
   */
  function updateRowWithData(rowId: string, data: Partial<DetailRow>): void {
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    const original = rows.value[idx]
    const merged = normalizeRow({ ...original, ...data, rowId: original.rowId, seqNo: original.seqNo })
    const newRows = [...rows.value]
    newRows[idx] = recalcRow(merged)
    rows.value = newRows
    persistRows()
  }

  // ─── removeRow ───────────────────────────────────────────────────────

  function removeRow(rowId: string): void {
    rows.value = rows.value.filter(r => r.rowId !== rowId)
    // Re-sequence
    rows.value.forEach((r, idx) => { r.seqNo = idx + 1 })
    persistRows()
  }

  // ─── updateCell ──────────────────────────────────────────────────────

  /** 可编辑的数值字段列表（公式自动计算列不在此列表中） */
  const NUMERIC_EDITABLE_FIELDS = [
    'priorUnadjusted', 'priorAje', 'priorRje',
    'agePrior1y', 'agePrior1to2y', 'agePrior2to3y', 'agePrior3yAbove',
    'debitAmount', 'creditAmount',
    'endAje', 'endRje',
    'ageEnd1y', 'ageEnd1to2y', 'ageEnd2to3y', 'ageEnd3yAbove',
    'receivableWithin1y', 'receivableAbove1y',
    'postPeriodSettlement',
  ]

  function updateCell(rowId: string, field: string, value: any): void {
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return

    const row = { ...rows.value[idx] }

    if (NUMERIC_EDITABLE_FIELDS.includes(field)) {
      ;(row as any)[field] = parseNum(value)
    } else {
      // String fields: contractName, contractType, customerName, companyCode,
      // relatedPartyType, isInConstructionPeriod, creditRiskGroup, isConfirmed
      ;(row as any)[field] = value
    }

    // Recalculate formula chain
    const recalculated = recalcRow(row)

    // Update rows array
    const newRows = [...rows.value]
    newRows[idx] = recalculated
    rows.value = newRows

    persistRows()
  }

  // ─── importFromAuxBalance ────────────────────────────────────────────

  /**
   * 调后端 POST /api/workpapers/{wpId}/d6/import-aux-balance
   * 从 tb_aux_balance 科目1141 按客户/合同维度导入明细行
   *
   * 合同资产科目为 1141；`report_config` 报表行 BS-011 四准则一致。
   * 原 `1402` 是在途物资（存货类），属误用。
   */
  async function importFromAuxBalance(): Promise<void> {
    if (!wpId.value) return

    try {
      const res = await api.post(
        `/api/workpapers/${wpId.value}/d6/import-aux-balance`,
        { project_id: projectId.value },
      )
      const importedData: any[] = Array.isArray(res) ? res : (res?.data ?? res?.rows ?? [])

      if (importedData.length === 0) {
        ElMessage.info('未找到科目1141的辅助余额数据')
        return
      }

      // 转换为 DetailRow 并 merge
      const existingMap = new Map(rows.value.map(r => [`${r.contractName}||${r.customerName}`, r]))
      let newCount = 0
      let nextSeqNo = rows.value.length > 0
        ? Math.max(...rows.value.map(r => r.seqNo)) + 1
        : 1

      for (const item of importedData) {
        const contractName = item.contractName || item.contract_name || item.aux_name || ''
        const customerName = item.customerName || item.customer_name || ''
        const key = `${contractName}||${customerName}`

        if (existingMap.has(key)) {
          // Update existing row
          const existing = { ...existingMap.get(key)! }
          existing.priorUnadjusted = parseNum(item.priorUnadjusted ?? item.prior_unadjusted ?? item.begin_balance)
          existing.debitAmount = parseNum(item.debitAmount ?? item.debit_amount ?? item.debit ?? 0)
          existing.creditAmount = parseNum(item.creditAmount ?? item.credit_amount ?? item.credit ?? 0)
          existingMap.set(key, recalcRow(existing))
        } else {
          // New row
          const newRow = normalizeRow({
            rowId: generateRowId(),
            seqNo: nextSeqNo++,
            contractName,
            customerName,
            contractType: item.contractType || item.contract_type || '',
            companyCode: item.companyCode || item.company_code || '',
            relatedPartyType: item.relatedPartyType || item.related_party_type || '',
            priorUnadjusted: item.priorUnadjusted ?? item.prior_unadjusted ?? item.begin_balance ?? 0,
            debitAmount: item.debitAmount ?? item.debit_amount ?? item.debit ?? 0,
            creditAmount: item.creditAmount ?? item.credit_amount ?? item.credit ?? 0,
          })
          existingMap.set(key, recalcRow(newRow))
          newCount++
        }
      }

      rows.value = Array.from(existingMap.values())
      persistRows()
      ElMessage.success(`成功导入${importedData.length}行数据，新增${newCount}个明细项目`)
    } catch {
      ElMessage.error('从辅助余额表导入失败，请稍后重试')
    }
  }

  /**
   * 从次年序时账导入期后结转金额
   * (1141贷方=合同资产转为应收，按客户名归集)
   */
  async function importPostSettlementFromLedger(bsDate?: string): Promise<void> {
    if (!wpId.value || !projectId.value) return

    const year = bsDate ? parseInt(bsDate.slice(0, 4)) : new Date().getFullYear() - 1
    const nextYear = year + 1
    const dateFrom = `${nextYear}-01-01`
    const dateTo = `${nextYear}-06-30`

    try {
      const res = await api.get(
        `/api/workpapers/${wpId.value}/ledger/entries`,
        { params: { account_code: '1141', year: nextYear, date_from: dateFrom, date_to: dateTo, direction: 'credit' } },
      )
      const entries: any[] = Array.isArray(res) ? res : (res?.data ?? res?.entries ?? [])

      if (entries.length === 0) {
        ElMessage.info('未找到科目1141的期后贷方发生数据')
        return
      }

      // 按客户名归集贷方金额
      const grouped = new Map<string, number>()
      for (const entry of entries) {
        const name = entry.counterpart_name || entry.customer_name || entry.aux_name || ''
        if (!name) continue
        grouped.set(name, (grouped.get(name) || 0) + parseNum(entry.credit_amount || entry.amount || 0))
      }

      // 匹配D6-2明细行回填(仅填空值)
      let filled = 0
      const normalizedGrouped = new Map<string, number>()
      for (const [k, v] of grouped) {
        normalizedGrouped.set(k.trim().toLowerCase(), v)
      }

      rows.value = rows.value.map(row => {
        if (row.postPeriodSettlement > 0) return row // 已有值不覆盖
        const matchKey = (row.customerName || row.contractName || '').trim().toLowerCase()
        const amount = normalizedGrouped.get(matchKey)
        if (amount && amount > 0) {
          filled++
          return { ...row, postPeriodSettlement: amount }
        }
        return row
      })

      if (filled > 0) {
        persistRows()
        ElMessage.success(`期后结转金额已填入${filled}行（${dateFrom}至${dateTo}，科目1141贷方）`)
      } else {
        ElMessage.warning(`序时账有${grouped.size}个客户的期后数据，但未匹配到D6-2明细行（按客户名称/合同名称匹配）`)
      }
    } catch {
      ElMessage.error('从序时账获取期后结转数据失败')
    }
  }

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    rows,
    subtotalByType,
    classificationRows,
    totalRow,
    addRow,
    addRowWithData,
    updateRowWithData,
    removeRow,
    updateCell,
    importFromAuxBalance,
    importPostSettlementFromLedger,
    searchFilter,
    filteredRows,
  }
}

export default useD6Detail
