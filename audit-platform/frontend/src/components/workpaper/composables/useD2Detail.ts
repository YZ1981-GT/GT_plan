/**
 * useD2Detail — 明细表D2-2核心逻辑 composable (39列宽表)
 *
 * Spec: .kiro/specs/d2-accounts-receivable-refactor/
 * Task: 4.1
 *
 * 职责：
 * - DetailRow 类型定义（39列完整字段）
 * - rows reactive（从 D2-detail-rows remark JSON加载）
 * - totalRow computed（SUM全部行各金额列）
 * - searchQuery + filteredRows computed（模糊搜索客户名称）
 * - addRow / removeRow 动态行管理
 * - matchRelatedParty（关联方自动匹配）
 * - 行公式链自动计算（priorAudited/endBalance/currentUnadjusted/currentAudited）
 * - updateCell（编辑→公式重算→关联方匹配→debounce保存）
 * - useVirtualScroll computed（rows.length > 30 启用）
 * - 序列化/反序列化（JSON.stringify rows → D2-detail-rows remark字段）
 *
 * Requirements: 2.1-2.11, 18.4
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  getAuditedAmount,
} from './useD2FormulaEngine'
import type { UseD2BaseOptions } from './useD2Adjudication'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface DetailRow {
  rowId: string
  seq: number                    // 序号
  customerName: string           // 客户名称
  companyCode: string            // 公司代码
  relationType: string           // 关联方类型(非关联方/控股股东/实际控制人/其他关联方)
  // 期初(4列)
  priorUnadjusted: number
  priorAje: number
  priorRje: number
  priorAudited: number           // 自动计算 = priorUnadjusted + priorAje + priorRje
  // 期初审定账龄(6档)
  priorAging1Year: number
  priorAging1to2: number
  priorAging2to3: number
  priorAging3to4: number
  priorAging4to5: number
  priorAgingOver5: number
  // 本期发生
  debitOccurrence: number        // 借方发生
  creditOccurrence: number       // 贷方发生
  endBalance: number             // 期末余额 = 期初审定 + 借方 - 贷方
  reclassification: number       // 被审计单位重分类
  currentUnadjusted: number      // 期末未审 = 期末余额 + 重分类
  // 期末未审账龄(6档)
  currentAging1Year: number
  currentAging1to2: number
  currentAging2to3: number
  currentAging3to4: number
  currentAging4to5: number
  currentAgingOver5: number
  // 调整
  currentAje: number             // 账项调整(Z列)
  currentRje: number             // 重分类调整(AA列)
  currentAudited: number         // 期末审定 = 期末未审 + AJE + RJE
  // 期末审定账龄(6档)
  auditedAging1Year: number
  auditedAging1to2: number
  auditedAging2to3: number
  auditedAging3to4: number
  auditedAging4to5: number
  auditedAgingOver5: number
  // 分类与标记
  creditRiskClassification: string  // 信用风险组合方式(AI列): 单项计提/账龄组合/客户类型组合
  groupName: string              // 组合名称(AJ列)
  isConfirmation: boolean        // 是否函证
  postPayment: number            // 期后回款
  remark: string                 // 备注
}

/** 需要SUM求和的金额字段列表 */
const NUMERIC_FIELDS: (keyof DetailRow)[] = [
  'priorUnadjusted', 'priorAje', 'priorRje', 'priorAudited',
  'priorAging1Year', 'priorAging1to2', 'priorAging2to3',
  'priorAging3to4', 'priorAging4to5', 'priorAgingOver5',
  'debitOccurrence', 'creditOccurrence', 'endBalance',
  'reclassification', 'currentUnadjusted',
  'currentAging1Year', 'currentAging1to2', 'currentAging2to3',
  'currentAging3to4', 'currentAging4to5', 'currentAgingOver5',
  'currentAje', 'currentRje', 'currentAudited',
  'auditedAging1Year', 'auditedAging1to2', 'auditedAging2to3',
  'auditedAging3to4', 'auditedAging4to5', 'auditedAgingOver5',
  'postPayment',
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** 生成简易唯一ID（nanoid替代） */
function generateRowId(): string {
  return `dr-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

/** 创建空行 */
function createEmptyRow(seq: number): DetailRow {
  return {
    rowId: generateRowId(),
    seq,
    customerName: '',
    companyCode: '',
    relationType: '非关联方',
    priorUnadjusted: 0,
    priorAje: 0,
    priorRje: 0,
    priorAudited: 0,
    priorAging1Year: 0,
    priorAging1to2: 0,
    priorAging2to3: 0,
    priorAging3to4: 0,
    priorAging4to5: 0,
    priorAgingOver5: 0,
    debitOccurrence: 0,
    creditOccurrence: 0,
    endBalance: 0,
    reclassification: 0,
    currentUnadjusted: 0,
    currentAging1Year: 0,
    currentAging1to2: 0,
    currentAging2to3: 0,
    currentAging3to4: 0,
    currentAging4to5: 0,
    currentAgingOver5: 0,
    currentAje: 0,
    currentRje: 0,
    currentAudited: 0,
    auditedAging1Year: 0,
    auditedAging1to2: 0,
    auditedAging2to3: 0,
    auditedAging3to4: 0,
    auditedAging4to5: 0,
    auditedAgingOver5: 0,
    creditRiskClassification: '',
    groupName: '',
    isConfirmation: false,
    postPayment: 0,
    remark: '',
  }
}

/**
 * 行公式链自动计算
 * - priorAudited = priorUnadjusted + priorAje + priorRje
 * - endBalance = priorAudited + debitOccurrence - creditOccurrence
 * - currentUnadjusted = endBalance + reclassification
 * - currentAudited = currentUnadjusted + currentAje + currentRje
 */
function recalcRow(row: DetailRow): DetailRow {
  row.priorAudited = getAuditedAmount(
    parseNum(row.priorUnadjusted),
    parseNum(row.priorAje),
    parseNum(row.priorRje)
  )
  row.endBalance = row.priorAudited + parseNum(row.debitOccurrence) - parseNum(row.creditOccurrence)
  row.currentUnadjusted = row.endBalance + parseNum(row.reclassification)
  row.currentAudited = getAuditedAmount(
    row.currentUnadjusted,
    parseNum(row.currentAje),
    parseNum(row.currentRje)
  )
  return row
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD2Detail(options: UseD2BaseOptions & { relatedParties: Ref<string[]> }) {
  const { allResponses, isReadonly, relatedParties } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const rows = ref<DetailRow[]>([])
  const searchQuery = ref<string>('')
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Load from allResponses ────────────────────────────────────────────

  function loadRows(): void {
    const response = allResponses.value.get('D2-detail-rows')
    const jsonStr = response?.remark
    if (!jsonStr) {
      rows.value = []
      return
    }
    try {
      const parsed = JSON.parse(jsonStr)
      if (Array.isArray(parsed)) {
        rows.value = parsed.map((raw: any, idx: number) => {
          const row: DetailRow = {
            rowId: raw.rowId || generateRowId(),
            seq: raw.seq ?? idx + 1,
            customerName: raw.customerName || '',
            companyCode: raw.companyCode || '',
            relationType: raw.relationType || '非关联方',
            priorUnadjusted: parseNum(raw.priorUnadjusted),
            priorAje: parseNum(raw.priorAje),
            priorRje: parseNum(raw.priorRje),
            priorAudited: parseNum(raw.priorAudited),
            priorAging1Year: parseNum(raw.priorAging1Year),
            priorAging1to2: parseNum(raw.priorAging1to2),
            priorAging2to3: parseNum(raw.priorAging2to3),
            priorAging3to4: parseNum(raw.priorAging3to4),
            priorAging4to5: parseNum(raw.priorAging4to5),
            priorAgingOver5: parseNum(raw.priorAgingOver5),
            debitOccurrence: parseNum(raw.debitOccurrence),
            creditOccurrence: parseNum(raw.creditOccurrence),
            endBalance: parseNum(raw.endBalance),
            reclassification: parseNum(raw.reclassification),
            currentUnadjusted: parseNum(raw.currentUnadjusted),
            currentAging1Year: parseNum(raw.currentAging1Year),
            currentAging1to2: parseNum(raw.currentAging1to2),
            currentAging2to3: parseNum(raw.currentAging2to3),
            currentAging3to4: parseNum(raw.currentAging3to4),
            currentAging4to5: parseNum(raw.currentAging4to5),
            currentAgingOver5: parseNum(raw.currentAgingOver5),
            currentAje: parseNum(raw.currentAje),
            currentRje: parseNum(raw.currentRje),
            currentAudited: parseNum(raw.currentAudited),
            auditedAging1Year: parseNum(raw.auditedAging1Year),
            auditedAging1to2: parseNum(raw.auditedAging1to2),
            auditedAging2to3: parseNum(raw.auditedAging2to3),
            auditedAging3to4: parseNum(raw.auditedAging3to4),
            auditedAging4to5: parseNum(raw.auditedAging4to5),
            auditedAgingOver5: parseNum(raw.auditedAgingOver5),
            creditRiskClassification: raw.creditRiskClassification || '',
            groupName: raw.groupName || '',
            isConfirmation: raw.isConfirmation === true || raw.isConfirmation === 'true',
            postPayment: parseNum(raw.postPayment),
            remark: raw.remark || '',
          }
          // Recalc formula fields to ensure consistency
          return recalcRow(row)
        })
      }
    } catch {
      rows.value = []
    }
  }

  // Watch allResponses for D2-detail-rows changes (initial load)
  watch(
    () => allResponses.value.get('D2-detail-rows')?.remark,
    () => {
      // Only reload if rows is empty (initial load) to avoid overwriting user edits
      if (rows.value.length === 0) {
        loadRows()
      }
    },
    { immediate: true }
  )

  // ─── Total Row ─────────────────────────────────────────────────────────

  /**
   * 合计行：SUM所有行各金额列，不可编辑
   */
  const totalRow: ComputedRef<Partial<DetailRow>> = computed(() => {
    const result: Partial<DetailRow> = {
      rowId: '__total__',
      seq: 0,
      customerName: '合计',
      companyCode: '',
      relationType: '',
      creditRiskClassification: '',
      groupName: '',
      isConfirmation: false,
      remark: '',
    }
    for (const field of NUMERIC_FIELDS) {
      (result as any)[field] = rows.value.reduce(
        (sum, row) => sum + parseNum((row as any)[field]),
        0
      )
    }
    return result
  })

  // ─── Search & Filter ───────────────────────────────────────────────────

  /**
   * 按客户名称模糊搜索，大小写不敏感
   */
  const filteredRows: ComputedRef<DetailRow[]> = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    if (!q) return rows.value
    return rows.value.filter(row =>
      row.customerName.toLowerCase().includes(q)
    )
  })

  // ─── Row Management ────────────────────────────────────────────────────

  /**
   * 在合计行上方新增空行，所有金额=0
   */
  function addRow(): void {
    if (isReadonly.value) return
    const newSeq = rows.value.length + 1
    const newRow = createEmptyRow(newSeq)
    rows.value.push(newRow)
    debounceSave()
  }

  /**
   * 删除指定行
   */
  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    rows.value.splice(idx, 1)
    // Resequence
    rows.value.forEach((r, i) => { r.seq = i + 1 })
    debounceSave()
  }

  // ─── Related Party Matching ────────────────────────────────────────────

  /**
   * 从 relatedParties 列表模糊匹配关联方
   * 使用 includes/contains 逻辑（不要求精确匹配）
   *
   * 返回关联方类型：匹配到 → '其他关联方'；未匹配 → '非关联方'
   */
  function matchRelatedParty(name: string): string {
    if (!name || !relatedParties.value || relatedParties.value.length === 0) {
      return '非关联方'
    }
    const lowerName = name.toLowerCase()
    const matched = relatedParties.value.some(party =>
      party.toLowerCase().includes(lowerName) || lowerName.includes(party.toLowerCase())
    )
    return matched ? '其他关联方' : '非关联方'
  }

  // ─── Update Cell ───────────────────────────────────────────────────────

  /**
   * 编辑单元格 → 公式重算 → 触发关联方匹配(如编辑customerName) → debounce保存
   *
   * @param rowId - 行唯一标识
   * @param field - 字段名
   * @param value - 新值
   */
  function updateCell(rowId: string, field: string, value: any): void {
    if (isReadonly.value) return

    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return

    // Update value
    const key = field as keyof DetailRow
    if (key === 'isConfirmation') {
      row.isConfirmation = value === true || value === 'true'
    } else if (NUMERIC_FIELDS.includes(key)) {
      ;(row as any)[key] = parseNum(value)
    } else {
      ;(row as any)[key] = value
    }

    // Recalculate formula chain
    recalcRow(row)

    // If customerName changed, auto-match related party
    if (field === 'customerName' && typeof value === 'string') {
      row.relationType = matchRelatedParty(value)
    }

    // Selection fields (creditRiskClassification, relationType, isConfirmation) → immediate save
    const immediateFields = ['creditRiskClassification', 'relationType', 'isConfirmation']
    if (immediateFields.includes(field)) {
      immediateSave()
    } else {
      debounceSave()
    }
  }

  // ─── Virtual Scroll ────────────────────────────────────────────────────

  /**
   * 当行数超过30行时启用虚拟滚动
   */
  const useVirtualScroll: ComputedRef<boolean> = computed(() => {
    return rows.value.length > 30
  })

  // ─── Serialization & Save ──────────────────────────────────────────────

  /**
   * 序列化行数据为 JSON，存储到 D2-detail-rows remark 字段
   */
  function serializeRows(): string {
    return JSON.stringify(rows.value)
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function immediateSave(): void {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }
    flushSave()
  }

  function flushSave(): void {
    const json = serializeRows()
    // Update allResponses Map
    allResponses.value.set('D2-detail-rows', {
      item_id: 'D2-detail-rows',
      conclusion: null,
      remark: json,
    })
    // Dispatch save event
    dispatchSaveEvent()
  }

  /**
   * 触发保存事件（CustomEvent 'd2:save-items'，由 useD2FormData 监听处理）
   */
  function dispatchSaveEvent(): void {
    try {
      const item = {
        item_id: 'D2-detail-rows',
        conclusion: null,
        remark: serializeRows(),
      }
      window.dispatchEvent(new CustomEvent('d2:save-items', { detail: { items: [item] } }))
    } catch {
      // silent
    }
  }

  // ─── Import from Aux Balance (Task 45.1) ────────────────────────────

  /**
   * 从辅助余额表导入客户明细数据
   * GET /api/projects/{pid}/ledger/aux-balance-detail?account_code=1122&aux_type=customer
   *
   * merge模式：按客户名去重，仅更新 priorUnadjusted/endBalance，不覆盖 AJE/RJE/账龄
   * @returns { imported, updated, added } 摘要
   */
  async function importFromAuxBalance(projectId: string): Promise<{ imported: number; updated: number; added: number }> {
    try {
      const response = await fetch(
        `/api/projects/${projectId}/ledger/aux-balance-detail?account_code=1122&aux_type=customer`
      )
      if (!response.ok) {
        const { ElMessage } = await import('element-plus')
        ElMessage.info('辅助余额表无数据或请求失败')
        return { imported: 0, updated: 0, added: 0 }
      }

      const result = await response.json()
      const data: Array<{ aux_name: string; prior_balance?: number; end_balance?: number }> =
        result.data || result || []

      if (!data.length) {
        const { ElMessage } = await import('element-plus')
        ElMessage.info('辅助余额表中无1122科目客户维度数据')
        return { imported: 0, updated: 0, added: 0 }
      }

      let updated = 0
      let added = 0

      for (const item of data) {
        const customerName = item.aux_name?.trim()
        if (!customerName) continue

        // 按客户名去重查找已有行
        const existing = rows.value.find(
          r => r.customerName.trim().toLowerCase() === customerName.toLowerCase()
        )

        if (existing) {
          // merge: 仅更新 priorUnadjusted/endBalance，不覆盖手工字段
          if (item.prior_balance !== undefined) {
            existing.priorUnadjusted = item.prior_balance
          }
          if (item.end_balance !== undefined) {
            existing.endBalance = item.end_balance
          }
          recalcRow(existing)
          updated++
        } else {
          // 新增行
          const newRow = createEmptyRow(rows.value.length + 1)
          newRow.customerName = customerName
          if (item.prior_balance !== undefined) {
            newRow.priorUnadjusted = item.prior_balance
          }
          if (item.end_balance !== undefined) {
            newRow.endBalance = item.end_balance
          }
          recalcRow(newRow)
          rows.value.push(newRow)
          added++
        }
      }

      const imported = updated + added
      if (imported > 0) {
        debounceSave()
      }

      const { ElMessage } = await import('element-plus')
      ElMessage.success(`从余额表导入完成：更新${updated}行，新增${added}行`)
      return { imported, updated, added }
    } catch {
      const { ElMessage } = await import('element-plus')
      ElMessage.error('从余额表导入失败')
      return { imported: 0, updated: 0, added: 0 }
    }
  }

  // ─── Lifecycle ─────────────────────────────────────────────────────────

  /** EventBus listener for confirmation:completed (Task 44.1) */
  function onConfirmationCompleted(e: Event): void {
    const detail = (e as CustomEvent).detail
    if (!detail || !detail.customerName) return

    const targetName = (detail.customerName as string).toLowerCase()
    let matched = false

    for (const row of rows.value) {
      if (row.customerName && row.customerName.toLowerCase().includes(targetName)) {
        row.isConfirmation = true
        ;(row as any)._confirmationAutoMarked = true
        matched = true
      }
    }

    if (matched) {
      debounceSave()
    }
  }

  // Register EventBus listener
  window.addEventListener('confirmation:completed', onConfirmationCompleted)

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
    window.removeEventListener('confirmation:completed', onConfirmationCompleted)
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 行数据
    rows,
    filteredRows,
    totalRow,

    // 搜索
    searchQuery,

    // 行操作
    addRow,
    removeRow,
    updateCell,

    // 关联方匹配
    matchRelatedParty,

    // 虚拟滚动
    useVirtualScroll,

    // 导入
    importFromAuxBalance,

    // 工具方法（供外部/测试使用）
    loadRows,
    serializeRows,
  }
}

export default useD2Detail
