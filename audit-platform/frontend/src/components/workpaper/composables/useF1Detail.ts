/**
 * useF1Detail — F1-2 明细表核心逻辑 composable
 *
 * Spec: .kiro/specs/f1-prepayment/
 * Task: 7.1
 *
 * 职责：
 * - 定义 DetailRow 类型（27列完整字段）
 * - rows reactive（从F1-det-rows加载JSON数组）
 * - 行内公式自动计算（H=E+F+G, O=H+N-M, Q=O+P, T=Q+R+S）
 * - subtotalRow computed + verificationRow computed（合计-TB数）
 * - searchQuery + filteredRows computed（模糊搜索）
 * - addRow/removeRow/updateCell
 * - matchRelatedParty（从relatedParties列表包含匹配）
 * - importFromAuxBalance（调后端API批量导入）
 * - onConfirmationCompleted监听（标记isConfirmed='Y'）
 *
 * Requirements: 4.1-4.12, 5.1-5.7, 6.1-6.5, 18.4
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import {
  parseNum,
  calcPriorAudited,
  calcEndBalance,
  calcEndUnadjusted,
  calcEndAudited,
  calcSubtotal,
} from './useF1FormulaEngine'
import { api } from '@/services/apiProxy'
import type { ChecklistResponse } from './useF1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface DetailRow {
  rowId: string
  customerName: string       // A: 对方单位名称
  companyCode: string        // B: 公司代码
  nature: string             // C: 款项性质（下拉）
  relationType: string       // D: 关联方类型（下拉）
  priorUnadjusted: number    // E: 期初未审余额
  priorAdjustment: number    // F: 期初账项调整
  priorReclass: number       // G: 期初重分类调整
  priorAudited: number       // H: =E+F+G（自动）
  agingPrior: { within1: number; y1to2: number; y2to3: number; over3: number }  // I~L
  debit: number              // M: 借方发生
  credit: number             // N: 贷方发生
  endBalance: number         // O: =H+N-M（贷方科目，自动）
  entityReclass: number      // P: 被审计单位重分类调整
  endUnadjusted: number      // Q: =O+P（自动）
  endAje: number             // R: 期末账项调整
  endRje: number             // S: 期末重分类调整
  endAudited: number         // T: =Q+R+S（自动）
  agingAudited: { within1: number; y1to2: number; y2to3: number; over3: number }  // U~X
  isConfirmed: string        // Y: 是否发函
  postPeriodSettlement: number // Z: 期后结转
  remark: string             // AA: 备注
}

export interface UseD3DetailOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
  relatedParties: Ref<string[]>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'F1-det-rows'
const ITEM_ID_TB_AMOUNT = 'F1-adj-trial-balance-amount'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `row-${crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2)}`
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
    customerName: raw.customerName || '',
    companyCode: raw.companyCode || '',
    nature: raw.nature || '',
    relationType: raw.relationType || '非关联方',
    priorUnadjusted: parseNum(raw.priorUnadjusted),
    priorAdjustment: parseNum(raw.priorAdjustment),
    priorReclass: parseNum(raw.priorReclass),
    priorAudited: parseNum(raw.priorAudited),
    agingPrior: {
      within1: parseNum(raw.agingPrior?.within1),
      y1to2: parseNum(raw.agingPrior?.y1to2),
      y2to3: parseNum(raw.agingPrior?.y2to3),
      over3: parseNum(raw.agingPrior?.over3),
    },
    debit: parseNum(raw.debit),
    credit: parseNum(raw.credit),
    endBalance: parseNum(raw.endBalance),
    entityReclass: parseNum(raw.entityReclass),
    endUnadjusted: parseNum(raw.endUnadjusted),
    endAje: parseNum(raw.endAje),
    endRje: parseNum(raw.endRje),
    endAudited: parseNum(raw.endAudited),
    agingAudited: {
      within1: parseNum(raw.agingAudited?.within1),
      y1to2: parseNum(raw.agingAudited?.y1to2),
      y2to3: parseNum(raw.agingAudited?.y2to3),
      over3: parseNum(raw.agingAudited?.over3),
    },
    isConfirmed: raw.isConfirmed || '',
    postPeriodSettlement: parseNum(raw.postPeriodSettlement),
    remark: raw.remark || '',
  }
}

/**
 * 对单行重新计算公式链：
 * H = E + F + G
 * O = H + N - M（贷方科目）
 * Q = O + P
 * T = Q + R + S
 */
export function recalcRowFormulas(row: DetailRow): DetailRow {
  const H = calcPriorAudited(row.priorUnadjusted, row.priorAdjustment, row.priorReclass)
  const O = calcEndBalance(H, row.credit, row.debit)
  const Q = calcEndUnadjusted(O, row.entityReclass)
  const T = calcEndAudited(Q, row.endAje, row.endRje)

  return {
    ...row,
    priorAudited: H,
    endBalance: O,
    endUnadjusted: Q,
    endAudited: T,
  }
}

/** 创建空行（所有数值为 0） */
export function createEmptyRow(): DetailRow {
  return {
    rowId: generateRowId(),
    customerName: '',
    companyCode: '',
    nature: '',
    relationType: '非关联方',
    priorUnadjusted: 0,
    priorAdjustment: 0,
    priorReclass: 0,
    priorAudited: 0,
    agingPrior: { within1: 0, y1to2: 0, y2to3: 0, over3: 0 },
    debit: 0,
    credit: 0,
    endBalance: 0,
    entityReclass: 0,
    endUnadjusted: 0,
    endAje: 0,
    endRje: 0,
    endAudited: 0,
    agingAudited: { within1: 0, y1to2: 0, y2to3: 0, over3: 0 },
    isConfirmed: '',
    postPeriodSettlement: 0,
    remark: '',
  }
}

/**
 * 关联方匹配逻辑（纯函数，方便测试）
 *
 * 检查 customerName 是否包含 relatedParties 列表中任一项（或反向包含）。
 * 匹配则返回该关联方名称（作为关联关系标识），否则返回'非关联方'。
 */
export function matchRelatedPartyPure(customerName: string, relatedParties: string[]): string {
  if (!customerName) return '非关联方'
  const nameLower = customerName.toLowerCase()
  for (const party of relatedParties) {
    if (!party) continue
    const partyLower = party.toLowerCase()
    if (nameLower.includes(partyLower) || partyLower.includes(nameLower)) {
      return party
    }
  }
  return '非关联方'
}

/**
 * 搜索过滤逻辑（纯函数，方便测试）
 *
 * 按 customerName 大小写不敏感模糊搜索。
 * 空查询串返回所有行。
 */
export function filterRowsBySearch(rows: DetailRow[], query: string): DetailRow[] {
  if (!query) return rows
  const q = query.toLowerCase()
  return rows.filter(row => row.customerName.toLowerCase().includes(q))
}

/**
 * 函证完成事件处理逻辑（纯函数，方便测试）
 *
 * 匹配 customerName 的行标记 isConfirmed='Y'，不匹配行保持不变。
 */
export function applyConfirmationCompleted(rows: DetailRow[], customerName: string): DetailRow[] {
  if (!customerName) return rows
  const nameLower = customerName.toLowerCase()
  return rows.map(row => {
    if (row.customerName.toLowerCase() === nameLower) {
      return { ...row, isConfirmed: 'Y' }
    }
    return row
  })
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useF1Detail(options: UseD3DetailOptions) {
  const { allResponses, wpId, projectId, debouncedSave, isReadonly, relatedParties } = options

  const eventListeners: Array<{ event: string; handler: (e: Event) => void }> = []

  // ─── Reactive rows ───────────────────────────────────────────────────

  const rows = ref<DetailRow[]>([])
  const searchQuery = ref<string>('')

  // Load rows from allResponses
  watch(
    () => allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (jsonStr) => {
      const parsed = safeParseRows(jsonStr)
      // Recalculate formula chain for each row
      rows.value = parsed.map(recalcRowFormulas)
    },
    { immediate: true },
  )

  // ─── Persist ─────────────────────────────────────────────────────────

  function persistRows(): void {
    // Strip computed fields before saving (they are recalculated on load)
    const toSave = rows.value.map(row => ({
      ...row,
      // Keep computed fields in storage for crossSheet consumers
    }))
    debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(toSave) })
  }

  // ─── filteredRows computed ───────────────────────────────────────────

  const filteredRows: ComputedRef<DetailRow[]> = computed(() => {
    return filterRowsBySearch(rows.value, searchQuery.value)
  })

  // ─── subtotalRow computed ────────────────────────────────────────────

  const subtotalRow: ComputedRef<DetailRow> = computed(() => {
    const allRows = rows.value
    return {
      rowId: '__subtotal__',
      customerName: '合计',
      companyCode: '',
      nature: '',
      relationType: '',
      priorUnadjusted: calcSubtotal(allRows.map(r => r.priorUnadjusted)),
      priorAdjustment: calcSubtotal(allRows.map(r => r.priorAdjustment)),
      priorReclass: calcSubtotal(allRows.map(r => r.priorReclass)),
      priorAudited: calcSubtotal(allRows.map(r => r.priorAudited)),
      agingPrior: {
        within1: calcSubtotal(allRows.map(r => r.agingPrior.within1)),
        y1to2: calcSubtotal(allRows.map(r => r.agingPrior.y1to2)),
        y2to3: calcSubtotal(allRows.map(r => r.agingPrior.y2to3)),
        over3: calcSubtotal(allRows.map(r => r.agingPrior.over3)),
      },
      debit: calcSubtotal(allRows.map(r => r.debit)),
      credit: calcSubtotal(allRows.map(r => r.credit)),
      endBalance: calcSubtotal(allRows.map(r => r.endBalance)),
      entityReclass: calcSubtotal(allRows.map(r => r.entityReclass)),
      endUnadjusted: calcSubtotal(allRows.map(r => r.endUnadjusted)),
      endAje: calcSubtotal(allRows.map(r => r.endAje)),
      endRje: calcSubtotal(allRows.map(r => r.endRje)),
      endAudited: calcSubtotal(allRows.map(r => r.endAudited)),
      agingAudited: {
        within1: calcSubtotal(allRows.map(r => r.agingAudited.within1)),
        y1to2: calcSubtotal(allRows.map(r => r.agingAudited.y1to2)),
        y2to3: calcSubtotal(allRows.map(r => r.agingAudited.y2to3)),
        over3: calcSubtotal(allRows.map(r => r.agingAudited.over3)),
      },
      isConfirmed: '',
      postPeriodSettlement: calcSubtotal(allRows.map(r => r.postPeriodSettlement)),
      remark: '',
    }
  })

  // ─── verificationRow computed（合计 - TB数）────────────────────────────

  const verificationRow: ComputedRef<DetailRow> = computed(() => {
    const tbAmount = parseNum(allResponses.value.get(ITEM_ID_TB_AMOUNT)?.remark)
    const sub = subtotalRow.value
    return {
      rowId: '__verification__',
      customerName: '核对行（合计-TB数）',
      companyCode: '',
      nature: '',
      relationType: '',
      priorUnadjusted: sub.priorUnadjusted - tbAmount,
      priorAdjustment: sub.priorAdjustment,
      priorReclass: sub.priorReclass,
      priorAudited: sub.priorAudited - tbAmount,
      agingPrior: sub.agingPrior,
      debit: sub.debit,
      credit: sub.credit,
      endBalance: sub.endBalance - tbAmount,
      entityReclass: sub.entityReclass,
      endUnadjusted: sub.endUnadjusted - tbAmount,
      endAje: sub.endAje,
      endRje: sub.endRje,
      endAudited: sub.endAudited - tbAmount,
      agingAudited: sub.agingAudited,
      isConfirmed: '',
      postPeriodSettlement: sub.postPeriodSettlement,
      remark: '',
    }
  })

  // ─── addRow ──────────────────────────────────────────────────────────

  function addRow(): void {
    if (isReadonly.value) return
    const newRow = createEmptyRow()
    rows.value = [...rows.value, newRow]
    persistRows()
  }

  // ─── removeRow ───────────────────────────────────────────────────────

  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    rows.value = rows.value.filter(r => r.rowId !== rowId)
    persistRows()
  }

  // ─── updateCell ──────────────────────────────────────────────────────

  function updateCell(rowId: string, field: string, value: any): void {
    if (isReadonly.value) return

    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return

    const row = { ...rows.value[idx] }

    // Handle nested aging fields
    if (field.startsWith('agingPrior.')) {
      const subField = field.replace('agingPrior.', '') as keyof DetailRow['agingPrior']
      row.agingPrior = { ...row.agingPrior, [subField]: parseNum(value) }
    } else if (field.startsWith('agingAudited.')) {
      const subField = field.replace('agingAudited.', '') as keyof DetailRow['agingAudited']
      row.agingAudited = { ...row.agingAudited, [subField]: parseNum(value) }
    } else if (['priorUnadjusted', 'priorAdjustment', 'priorReclass', 'debit', 'credit', 'entityReclass', 'endAje', 'endRje', 'postPeriodSettlement'].includes(field)) {
      ;(row as any)[field] = parseNum(value)
    } else {
      ;(row as any)[field] = value
    }

    // Recalculate formula chain
    const recalculated = recalcRowFormulas(row)

    // Update rows array
    const newRows = [...rows.value]
    newRows[idx] = recalculated
    rows.value = newRows

    persistRows()
  }

  // ─── matchRelatedParty ───────────────────────────────────────────────

  function matchRelatedParty(name: string): string {
    return matchRelatedPartyPure(name, relatedParties.value)
  }

  // ─── importFromAuxBalance ────────────────────────────────────────────

  async function importFromAuxBalance(): Promise<void> {
    if (!wpId.value) return
    try {
      const res = await api.post(
        `/api/workpapers/${wpId.value}/f1/import-aux-balance`,
        { project_id: projectId.value },
      )
      const importedRows: any[] = Array.isArray(res) ? res : (res?.data ?? res?.rows ?? [])

      if (importedRows.length === 0) {
        ElMessage.info('未找到科目1123的辅助余额数据')
        return
      }

      // Merge imported rows into existing (add new customers, update existing)
      const existingMap = new Map(rows.value.map(r => [r.customerName, r]))
      let newCount = 0

      for (const imported of importedRows) {
        const name = imported.customerName || imported.customer_name || ''
        if (!name) continue

        if (existingMap.has(name)) {
          // Update existing row with imported data
          const existing = existingMap.get(name)!
          existing.priorUnadjusted = parseNum(imported.priorUnadjusted ?? imported.prior_unadjusted)
          existing.credit = parseNum(imported.credit)
          existing.debit = parseNum(imported.debit)
          // Recalculate formula chain
          const recalculated = recalcRowFormulas(existing)
          existingMap.set(name, recalculated)
        } else {
          // New customer row
          const newRow = normalizeRow({
            rowId: generateRowId(),
            customerName: name,
            companyCode: imported.companyCode || imported.company_code || '',
            priorUnadjusted: imported.priorUnadjusted ?? imported.prior_unadjusted ?? 0,
            credit: imported.credit ?? 0,
            debit: imported.debit ?? 0,
          })
          const recalculated = recalcRowFormulas(newRow)
          existingMap.set(name, recalculated)
          newCount++
        }
      }

      rows.value = Array.from(existingMap.values())
      persistRows()

      ElMessage.success(`成功导入${importedRows.length}行数据，${newCount}个新客户`)
    } catch {
      ElMessage.error('从辅助余额表导入失败，请稍后重试')
    }
  }

  // ─── onConfirmationCompleted ─────────────────────────────────────────

  function onConfirmationCompleted(payload: { customerName: string }): void {
    if (!payload.customerName) return
    rows.value = applyConfirmationCompleted(rows.value, payload.customerName)
    persistRows()
  }

  // ─── EventBus Registration ───────────────────────────────────────────

  const confirmationHandler = (e: Event) => {
    const detail = (e as CustomEvent).detail
    if (detail?.customerName) {
      onConfirmationCompleted(detail)
    }
  }
  window.addEventListener('confirmation:completed', confirmationHandler)
  eventListeners.push({ event: 'confirmation:completed', handler: confirmationHandler })

  onBeforeUnmount(() => {
    for (const { event, handler } of eventListeners) {
      window.removeEventListener(event, handler)
    }
  })

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    rows,
    filteredRows,
    subtotalRow,
    verificationRow,
    searchQuery,
    // 操作
    addRow,
    removeRow,
    updateCell,
    matchRelatedParty,
    importFromAuxBalance,
    // EventBus
    onConfirmationCompleted,
  }
}

export default useF1Detail
