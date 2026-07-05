/**
 * useD7Detail — D7-2 明细表27列核心逻辑 composable
 *
 * 贷方科目公式链（4步）：
 *   期初审定 = 期初未审 + AJE + RJE
 *   期末余额 = 期初审定 + 贷方发生 - 借方发生（贷方科目：贷增借减）
 *   期末未审 = 期末余额 + 被审计单位重分类调整
 *   期末审定 = 期末未审 + AJE + RJE
 *
 * Spec: .kiro/specs/d7-contract-liabilities/
 * Task: 7.1
 * Requirements: 5.1-5.12, 6.1-6.7, 7.1-7.5, 18.4, 24.1-24.3
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import {
  parseNum,
  calcAuditedAmount,
  calcCreditEndBalance,
  calcSubtotal,
} from './useD7FormulaEngine'
import { matchRelatedPartyPure } from './useD3Detail'
import type { ChecklistResponse } from './useD7FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface DetailRow {
  rowId: string
  contractName: string         // 合同名称/项目名称
  companyName: string          // 单位名称
  companyCode: string          // 公司代码
  relatedPartyType: string     // 关联关系
  natureType: string           // 类型(款项性质)
  priorUnadjusted: number      // 期初未审数
  priorAje: number             // 账项调整
  priorRje: number             // 重分类调整
  priorAudited: number         // 期初审定数（自动）
  priorAging1: number          // 审定账龄-1年以下
  priorAging2: number          // 审定账龄-1~2年
  priorAging3: number          // 审定账龄-2~3年
  priorAging4: number          // 审定账龄-3年以上
  debitAmount: number          // 借方发生
  creditAmount: number         // 贷方发生
  endBalance: number           // 期末余额（自动）
  entityReclass: number        // 被审计单位重分类调整
  endUnadjusted: number        // 期末未审余额（自动）
  endAje: number               // 账项调整
  endRje: number               // 重分类调整
  endAudited: number           // 期末审定数（自动）
  endAging1: number            // 审定账龄-1年以下
  endAging2: number            // 审定账龄-1~2年
  endAging3: number            // 审定账龄-2~3年
  endAging4: number            // 审定账龄-3年以上
  isConfirmed: string          // 是否发函
  postTransfer: number         // 期后结转
}

export interface UseD7DetailOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId: Ref<string>
  projectId: Ref<string>
  relatedParties?: Ref<string[]>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'D7-2-rows'

export const NATURE_TYPES = ['预收货款', '开发项目预收款', '预收工程款', '其他'] as const

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

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `row-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
}

function safeParseRows(jsonStr: string | null | undefined): DetailRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed.map(normalizeRow) : []
  } catch {
    return []
  }
}

function normalizeRow(raw: any): DetailRow {
  return {
    rowId: raw.rowId || generateRowId(),
    contractName: raw.contractName || '',
    companyName: raw.companyName || '',
    companyCode: raw.companyCode || '',
    relatedPartyType: raw.relatedPartyType || '',
    natureType: raw.natureType || '',
    priorUnadjusted: parseNum(raw.priorUnadjusted),
    priorAje: parseNum(raw.priorAje),
    priorRje: parseNum(raw.priorRje),
    priorAudited: parseNum(raw.priorAudited),
    priorAging1: parseNum(raw.priorAging1),
    priorAging2: parseNum(raw.priorAging2),
    priorAging3: parseNum(raw.priorAging3),
    priorAging4: parseNum(raw.priorAging4),
    debitAmount: parseNum(raw.debitAmount),
    creditAmount: parseNum(raw.creditAmount),
    endBalance: parseNum(raw.endBalance),
    entityReclass: parseNum(raw.entityReclass),
    endUnadjusted: parseNum(raw.endUnadjusted),
    endAje: parseNum(raw.endAje),
    endRje: parseNum(raw.endRje),
    endAudited: parseNum(raw.endAudited),
    endAging1: parseNum(raw.endAging1),
    endAging2: parseNum(raw.endAging2),
    endAging3: parseNum(raw.endAging3),
    endAging4: parseNum(raw.endAging4),
    isConfirmed: raw.isConfirmed || '',
    postTransfer: parseNum(raw.postTransfer),
  }
}

/**
 * 贷方科目公式链重算：
 *  priorAudited = priorUnadjusted + priorAje + priorRje
 *  endBalance = priorAudited + creditAmount - debitAmount (贷方科目)
 *  endUnadjusted = endBalance + entityReclass
 *  endAudited = endUnadjusted + endAje + endRje
 */
export function recalcRow(row: DetailRow): DetailRow {
  const priorAudited = calcAuditedAmount(row.priorUnadjusted, row.priorAje, row.priorRje)
  const endBalance = calcCreditEndBalance(priorAudited, row.creditAmount, row.debitAmount)
  const endUnadjusted = endBalance + row.entityReclass
  const endAudited = calcAuditedAmount(endUnadjusted, row.endAje, row.endRje)
  return { ...row, priorAudited, endBalance, endUnadjusted, endAudited }
}

export function createEmptyRow(): DetailRow {
  return {
    rowId: generateRowId(),
    contractName: '', companyName: '', companyCode: '',
    relatedPartyType: '', natureType: '',
    priorUnadjusted: 0, priorAje: 0, priorRje: 0, priorAudited: 0,
    priorAging1: 0, priorAging2: 0, priorAging3: 0, priorAging4: 0,
    debitAmount: 0, creditAmount: 0, endBalance: 0,
    entityReclass: 0, endUnadjusted: 0, endAje: 0, endRje: 0, endAudited: 0,
    endAging1: 0, endAging2: 0, endAging3: 0, endAging4: 0,
    isConfirmed: '', postTransfer: 0,
  }
}

function sumRows(rows: DetailRow[], label: string): DetailRow {
  return {
    rowId: `__${label}__`,
    contractName: label, companyName: '', companyCode: '',
    relatedPartyType: '', natureType: '',
    priorUnadjusted: calcSubtotal(rows.map(r => r.priorUnadjusted)),
    priorAje: calcSubtotal(rows.map(r => r.priorAje)),
    priorRje: calcSubtotal(rows.map(r => r.priorRje)),
    priorAudited: calcSubtotal(rows.map(r => r.priorAudited)),
    priorAging1: calcSubtotal(rows.map(r => r.priorAging1)),
    priorAging2: calcSubtotal(rows.map(r => r.priorAging2)),
    priorAging3: calcSubtotal(rows.map(r => r.priorAging3)),
    priorAging4: calcSubtotal(rows.map(r => r.priorAging4)),
    debitAmount: calcSubtotal(rows.map(r => r.debitAmount)),
    creditAmount: calcSubtotal(rows.map(r => r.creditAmount)),
    endBalance: calcSubtotal(rows.map(r => r.endBalance)),
    entityReclass: calcSubtotal(rows.map(r => r.entityReclass)),
    endUnadjusted: calcSubtotal(rows.map(r => r.endUnadjusted)),
    endAje: calcSubtotal(rows.map(r => r.endAje)),
    endRje: calcSubtotal(rows.map(r => r.endRje)),
    endAudited: calcSubtotal(rows.map(r => r.endAudited)),
    endAging1: calcSubtotal(rows.map(r => r.endAging1)),
    endAging2: calcSubtotal(rows.map(r => r.endAging2)),
    endAging3: calcSubtotal(rows.map(r => r.endAging3)),
    endAging4: calcSubtotal(rows.map(r => r.endAging4)),
    isConfirmed: '',
    postTransfer: calcSubtotal(rows.map(r => r.postTransfer)),
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD7Detail(options: UseD7DetailOptions) {
  const { allResponses, debouncedSave, wpId, projectId } = options
  const relatedParties = options.relatedParties ?? ref<string[]>([])

  function resolveRelatedPartyType(companyName: string): string {
    const matched = matchRelatedPartyPure(companyName, relatedParties.value)
    if (matched === '非关联方') return '非关联方'
    if ((RELATED_PARTY_TYPES as readonly string[]).includes(matched)) return matched
    return '其他关联方'
  }

  function matchRelatedParty(name: string): string {
    return resolveRelatedPartyType(name)
  }

  // ─── Reactive rows ───────────────────────────────────────────────────

  const rows = ref<DetailRow[]>([])

  watch(
    () => allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (jsonStr) => {
      rows.value = safeParseRows(jsonStr).map(recalcRow)
    },
    { immediate: true },
  )

  // ─── Search ──────────────────────────────────────────────────────────

  const searchFilter = ref('')

  const filteredRows: ComputedRef<DetailRow[]> = computed(() => {
    const keyword = searchFilter.value.trim().toLowerCase()
    if (!keyword) return rows.value
    return rows.value.filter(r =>
      r.companyName.toLowerCase().includes(keyword) ||
      r.contractName.toLowerCase().includes(keyword),
    )
  })

  // ─── Persist ─────────────────────────────────────────────────────────

  function persistRows(): void {
    debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
  }

  // ─── totalRow ────────────────────────────────────────────────────────

  const totalRow: ComputedRef<DetailRow> = computed(() => sumRows(rows.value, '合计'))

  // ─── verificationRow (核对行 = 合计 - TB数) ─────────────────────────

  const verificationRow: ComputedRef<DetailRow> = computed(() => {
    const total = totalRow.value
    const tbPrior = parseNum(allResponses.value.get('D7-2-tb-priorAudited')?.remark)
    const tbCurrent = parseNum(allResponses.value.get('D7-2-tb-currentAudited')?.remark)
    return {
      ...total,
      rowId: '__verification__',
      contractName: '核对差异',
      priorAudited: total.priorAudited - tbPrior,
      endAudited: total.endAudited - tbCurrent,
    }
  })

  // ─── addRow / removeRow / updateCell ─────────────────────────────────

  function addRow(): void {
    rows.value = [...rows.value, createEmptyRow()]
    persistRows()
  }

  function removeRow(rowId: string): void {
    rows.value = rows.value.filter(r => r.rowId !== rowId)
    persistRows()
  }

  const NUMERIC_EDITABLE_FIELDS = [
    'priorUnadjusted', 'priorAje', 'priorRje',
    'priorAging1', 'priorAging2', 'priorAging3', 'priorAging4',
    'debitAmount', 'creditAmount', 'entityReclass',
    'endAje', 'endRje',
    'endAging1', 'endAging2', 'endAging3', 'endAging4',
    'postTransfer',
  ]

  function updateCell(rowId: string, field: string, value: any): void {
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return

    const row = { ...rows.value[idx] }
    if (NUMERIC_EDITABLE_FIELDS.includes(field)) {
      ;(row as any)[field] = parseNum(value)
    } else {
      ;(row as any)[field] = value
    }

    if (field === 'companyName') {
      row.relatedPartyType = resolveRelatedPartyType(String(value ?? ''))
    }

    const newRows = [...rows.value]
    newRows[idx] = recalcRow(row)
    rows.value = newRows
    persistRows()
  }

  // ─── importFromAuxBalance ────────────────────────────────────────────

  async function importFromAuxBalance(): Promise<void> {
    if (!wpId.value) return
    try {
      const http = (await import('@/utils/http')).default
      const res = await http.post(
        `/api/workpapers/${wpId.value}/d7/import-aux-balance`,
        { project_id: projectId.value },
      )
      const importedData: any[] = Array.isArray(res.data) ? res.data : (res.data?.data ?? [])

      if (importedData.length === 0) {
        ElMessage.info('未找到科目2205的辅助余额数据')
        return
      }

      const existingMap = new Map(rows.value.map(r => [`${r.contractName}||${r.companyName}`, r]))
      let newCount = 0

      for (const item of importedData) {
        const contractName = item.contractName || item.contract_name || item.aux_name || ''
        const companyName = item.companyName || item.company_name || ''
        const key = `${contractName}||${companyName}`

        if (!existingMap.has(key)) {
          const newRow = recalcRow(normalizeRow({
            rowId: generateRowId(),
            contractName,
            companyName,
            companyCode: item.companyCode || item.company_code || '',
            priorUnadjusted: item.priorUnadjusted ?? item.prior_unadjusted ?? item.begin_balance ?? 0,
            debitAmount: item.debitAmount ?? item.debit_amount ?? 0,
            creditAmount: item.creditAmount ?? item.credit_amount ?? 0,
            relatedPartyType: resolveRelatedPartyType(companyName),
          }))
          existingMap.set(key, newRow)
          newCount++
        }
      }

      rows.value = Array.from(existingMap.values())
      persistRows()
      ElMessage.success(`成功导入${importedData.length}行数据，新增${newCount}个客户`)
    } catch {
      ElMessage.error('从辅助余额表导入失败，请稍后重试')
    }
  }

  // ─── 关联方自动匹配 ──────────────────────────────────────────────────

  // 编辑单位名称时通过 relatedParties 列表模糊匹配关联关系

  // ─── onConfirmationCompleted ─────────────────────────────────────────

  function _handleConfirmationCompleted(event: Event): void {
    const detail = (event as CustomEvent).detail
    if (!detail || detail.wpCode !== 'D7') return
    const customerName = detail.customerName
    if (!customerName) return

    rows.value = rows.value.map(r => {
      if (r.companyName === customerName) {
        return { ...r, isConfirmed: 'Y' }
      }
      return r
    })
    persistRows()
  }

  // Setup listener
  if (typeof window !== 'undefined') {
    window.addEventListener('confirmation:completed', _handleConfirmationCompleted)
  }

  // ─── 期后结转联动 (D7-7 → D7-2) ────────────────────────────────────

  // Computed from D7-7-post-rows: match by customer name
  watch(
    () => allResponses.value.get('D7-7-post-rows')?.remark,
    (jsonStr) => {
      if (!jsonStr) return
      let postRows: any[] = []
      try { postRows = JSON.parse(jsonStr) } catch { return }
      if (!Array.isArray(postRows) || postRows.length === 0) return

      // Aggregate post transfer credits by customer name
      const transferMap = new Map<string, number>()
      for (const pr of postRows) {
        const name = pr.customerName || ''
        if (!name) continue
        transferMap.set(name, (transferMap.get(name) || 0) + parseNum(pr.creditAmount))
      }

      // Update rows
      let changed = false
      rows.value = rows.value.map(r => {
        const transfer = transferMap.get(r.companyName) ?? 0
        if (r.postTransfer !== transfer) {
          changed = true
          return { ...r, postTransfer: transfer }
        }
        return r
      })
      if (changed) persistRows()
    },
    { immediate: true },
  )

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    rows,
    totalRow,
    verificationRow,
    addRow,
    removeRow,
    updateCell,
    importFromAuxBalance,
    searchFilter,
    filteredRows,
    matchRelatedParty,
  }
}

export default useD7Detail
