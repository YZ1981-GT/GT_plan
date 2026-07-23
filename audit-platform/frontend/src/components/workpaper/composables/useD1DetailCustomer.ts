/**
 * useD1DetailCustomer — D1-3 原值明细表(按客户) composable
 *
 * Spec: .kiro/specs/d1-adjudication-table/
 * Task: 5.1
 *
 * 职责：
 * - 管理按客户维度分类的动态行数据
 * - 无固定行（全部动态可增删）
 * - 动态行 CRUD（添加/删除/编辑）
 * - 自动计算公式字段（priorAudited / currentBalance / currentUnadjusted / currentAudited）
 * - 小计行 computed（SUM 所有明细行各金额列；搜索时按筛选行小计）
 * - 搜索过滤（按客户名称模糊匹配，大小写不敏感）
 * - 关联方自动匹配（从 relatedParties 列表中模糊匹配）
 * - 编辑客户名称时自动触发关联方匹配更新 relationType
 * - 审计过程/说明/结论 meta 持久化
 * - 序列化/反序列化（JSON ↔ checklist_responses remark）
 * - Debounce 2s 自动保存
 *
 * Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 8.3, 8.5, 8.7
 *
 * 公式（对齐 Excel D1-3）：
 *   期初审定 = 期初未审 + 期初AJE + 期初RJE
 *   期末余额 = 期初审定 + 本期增加 - 本期减少
 *   期末未审 = 期末余额 + 重分类（被审计单位重分类调整）
 *   期末审定 = 期末未审 + 期末AJE + 期末RJE
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { ChecklistItem, ChecklistResponse } from './useD1FormData'
import {
  parseNum,
  calcAuditedAmount,
  calcSubtotal,
} from './useD1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export type SaveFn = (items: ChecklistItem[]) => Promise<void>

export interface CustomerRow {
  rowId: string
  customerName: string
  companyCode: string
  relationType: string    // '非关联方' | '关联方' | ''
  priorUnadjusted: number
  priorAje: number
  priorRje: number
  priorAudited: number    // = prior + aje + rje (自动计算)
  currentIncrease: number
  currentDecrease: number
  currentBalance: number  // = priorAudited + increase - decrease (自动计算)
  reclassification: number
  currentUnadjusted: number  // = currentBalance + reclassification (自动计算)
  currentAje: number
  currentRje: number
  currentAudited: number  // = currentUnadjusted + aje + rje (自动计算)
  postSettlement: number  // 期后兑付/回款（资产负债表日后票据承兑收款，函证替代程序/存在性证据）
}

export interface UseD1DetailCustomerOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: SaveFn
  isReadonly: Ref<boolean>
  relatedParties: Ref<string[]>  // 项目关联方名单
  bsDate?: Ref<string>           // 资产负债表日（YYYY-MM-DD），用于期后兑付取数窗口
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY = 'D1-cust-rows'
const PROCEDURES_KEY = 'D1-cust-procedures'
const NOTE_KEY = 'D1-cust-note'
const CONCLUSION_KEY = 'D1-cust-conclusion'

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** 重算行内公式字段（对齐 Excel：期末余额为计算列，期末未审 = 期末余额 + 重分类） */
function recalcRow(row: CustomerRow): CustomerRow {
  const priorAudited = calcAuditedAmount(row.priorUnadjusted, row.priorAje, row.priorRje)
  const currentBalance = priorAudited + row.currentIncrease - row.currentDecrease
  const currentUnadjusted = currentBalance + row.reclassification
  const currentAudited = calcAuditedAmount(currentUnadjusted, row.currentAje, row.currentRje)
  return {
    ...row,
    priorAudited,
    currentBalance,
    currentUnadjusted,
    currentAudited,
  }
}

/** 生成动态行 ID */
function generateRowId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return `dynamic-${crypto.randomUUID()}`
  }
  // Fallback for environments without crypto.randomUUID
  return `dynamic-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

/** 创建空白客户行 */
function createEmptyRow(): CustomerRow {
  return recalcRow({
    rowId: generateRowId(),
    customerName: '',
    companyCode: '',
    relationType: '',
    priorUnadjusted: 0,
    priorAje: 0,
    priorRje: 0,
    priorAudited: 0,
    currentIncrease: 0,
    currentDecrease: 0,
    currentBalance: 0,
    reclassification: 0,
    currentUnadjusted: 0,
    currentAje: 0,
    currentRje: 0,
    currentAudited: 0,
    postSettlement: 0,
  })
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD1DetailCustomer(options: UseD1DetailCustomerOptions) {
  const { allResponses, projectId, saveImmediate, isReadonly, relatedParties, bsDate } = options

  // ─── State ───────────────────────────────────────────────────────────────

  const rows = ref<CustomerRow[]>([])
  const searchQuery = ref<string>('')
  const auditProcedures = ref('')
  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── Related Party Matching ──────────────────────────────────────────────

  /**
   * 模糊匹配关联方：检查 name 是否存在于 relatedParties 列表中（大小写不敏感）
   * 返回 '关联方' 或 '非关联方'
   */
  function matchRelatedParty(name: string): string {
    if (!name || name.trim() === '') return ''
    const lowerName = name.toLowerCase()
    const parties = relatedParties.value
    for (const party of parties) {
      if (party.toLowerCase().includes(lowerName) || lowerName.includes(party.toLowerCase())) {
        return '关联方'
      }
    }
    return '非关联方'
  }

  // ─── Deserialization (Load from allResponses) ────────────────────────────

  function loadFromResponses(): void {
    const response = allResponses.value.get(STORAGE_KEY)
    const raw = response?.remark
    if (!raw) {
      // No stored data, start with empty array
      rows.value = []
      return
    }
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed) || parsed.length === 0) {
        rows.value = []
        return
      }
      // Parse and ensure all numeric fields are proper numbers
      const loadedRows: CustomerRow[] = parsed.map((r: any) => recalcRow({
        rowId: r.rowId || generateRowId(),
        customerName: r.customerName || '',
        companyCode: r.companyCode || '',
        relationType: r.relationType || '',
        priorUnadjusted: parseNum(r.priorUnadjusted),
        priorAje: parseNum(r.priorAje),
        priorRje: parseNum(r.priorRje),
        priorAudited: 0, // will be recalculated
        currentIncrease: parseNum(r.currentIncrease),
        currentDecrease: parseNum(r.currentDecrease),
        currentBalance: parseNum(r.currentBalance),
        reclassification: parseNum(r.reclassification),
        currentUnadjusted: 0, // will be recalculated
        currentAje: parseNum(r.currentAje),
        currentRje: parseNum(r.currentRje),
        currentAudited: 0, // will be recalculated
        postSettlement: parseNum(r.postSettlement),
      }))

      rows.value = loadedRows
    } catch {
      // JSON parse failed, fall back to empty
      rows.value = []
    }
  }

  function loadMetaFromResponses(): void {
    auditProcedures.value = allResponses.value.get(PROCEDURES_KEY)?.remark || ''
    auditNote.value = allResponses.value.get(NOTE_KEY)?.remark || ''
    auditConclusion.value = allResponses.value.get(CONCLUSION_KEY)?.remark || ''
  }

  // Initial load
  loadFromResponses()
  loadMetaFromResponses()

  // Watch allResponses for external changes (e.g., from other tabs or OO sync)
  watch(
    () => allResponses.value.get(STORAGE_KEY)?.remark,
    (newRemark, oldRemark) => {
      if (newRemark !== oldRemark && newRemark !== serializeRows()) {
        loadFromResponses()
      }
    },
  )

  watch(
    () => [
      allResponses.value.get(PROCEDURES_KEY)?.remark,
      allResponses.value.get(NOTE_KEY)?.remark,
      allResponses.value.get(CONCLUSION_KEY)?.remark,
    ],
    () => {
      loadMetaFromResponses()
    },
  )

  // ─── Serialization ───────────────────────────────────────────────────────

  function serializeRows(): string {
    // 可编辑字段 + 期末余额快照（供导入导出；加载时仍会按公式重算）
    const data = rows.value.map(r => ({
      rowId: r.rowId,
      customerName: r.customerName,
      companyCode: r.companyCode,
      relationType: r.relationType,
      priorUnadjusted: r.priorUnadjusted,
      priorAje: r.priorAje,
      priorRje: r.priorRje,
      currentIncrease: r.currentIncrease,
      currentDecrease: r.currentDecrease,
      currentBalance: r.currentBalance,
      reclassification: r.reclassification,
      currentAje: r.currentAje,
      currentRje: r.currentRje,
      postSettlement: r.postSettlement,
    }))
    return JSON.stringify(data)
  }

  // ─── Debounce Save ───────────────────────────────────────────────────────

  let saveTimer: ReturnType<typeof setTimeout> | null = null
  let metaSaveTimer: ReturnType<typeof setTimeout> | null = null

  function scheduleSave(): void {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveTimer = null
      persistRows()
    }, 2000)
  }

  function scheduleMetaSave(): void {
    if (metaSaveTimer) clearTimeout(metaSaveTimer)
    metaSaveTimer = setTimeout(() => {
      metaSaveTimer = null
      persistMeta()
    }, 2000)
  }

  function persistRows(): void {
    const serialized = serializeRows()
    const item: ChecklistItem = {
      item_id: STORAGE_KEY,
      conclusion: null,
      remark: serialized,
    }
    allResponses.value.set(STORAGE_KEY, item)
    saveImmediate([item])
  }

  function persistMeta(): void {
    const items: ChecklistItem[] = [
      { item_id: PROCEDURES_KEY, conclusion: null, remark: auditProcedures.value || null },
      { item_id: NOTE_KEY, conclusion: null, remark: auditNote.value || null },
      { item_id: CONCLUSION_KEY, conclusion: null, remark: auditConclusion.value || null },
    ]
    for (const item of items) {
      allResponses.value.set(item.item_id, item)
    }
    saveImmediate(items)
  }

  function persistToResponses(): void {
    persistRows()
  }

  // ─── Filtered Rows (computed, search by customerName) ────────────────────

  const filteredRows: ComputedRef<CustomerRow[]> = computed(() => {
    const query = searchQuery.value.trim().toLowerCase()
    if (!query) return rows.value
    return rows.value.filter(r =>
      r.customerName.toLowerCase().includes(query)
    )
  })

  // ─── Subtotal Row (computed；搜索时按筛选行小计，避免合计与可见行不一致) ─

  function buildSubtotal(source: CustomerRow[], label: string): CustomerRow {
    return {
      rowId: 'subtotal',
      customerName: label,
      companyCode: '',
      relationType: '',
      priorUnadjusted: calcSubtotal(source.map(r => r.priorUnadjusted)),
      priorAje: calcSubtotal(source.map(r => r.priorAje)),
      priorRje: calcSubtotal(source.map(r => r.priorRje)),
      priorAudited: calcSubtotal(source.map(r => r.priorAudited)),
      currentIncrease: calcSubtotal(source.map(r => r.currentIncrease)),
      currentDecrease: calcSubtotal(source.map(r => r.currentDecrease)),
      currentBalance: calcSubtotal(source.map(r => r.currentBalance)),
      reclassification: calcSubtotal(source.map(r => r.reclassification)),
      currentUnadjusted: calcSubtotal(source.map(r => r.currentUnadjusted)),
      currentAje: calcSubtotal(source.map(r => r.currentAje)),
      currentRje: calcSubtotal(source.map(r => r.currentRje)),
      currentAudited: calcSubtotal(source.map(r => r.currentAudited)),
      postSettlement: calcSubtotal(source.map(r => r.postSettlement)),
    }
  }

  const subtotalRow: ComputedRef<CustomerRow> = computed(() => {
    const query = searchQuery.value.trim()
    if (query) {
      return buildSubtotal(filteredRows.value, `小计（筛选 ${filteredRows.value.length} 行）`)
    }
    return buildSubtotal(rows.value, '小计')
  })

  // ─── Row CRUD ────────────────────────────────────────────────────────────

  /** 新增空行（所有行均为动态可删除） */
  function addRow(): void {
    if (isReadonly.value) return
    const newRow = createEmptyRow()
    rows.value = [...rows.value, newRow]
    scheduleSave()
  }

  /** 删除行 */
  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    const target = rows.value.find(r => r.rowId === rowId)
    if (!target) return
    rows.value = rows.value.filter(r => r.rowId !== rowId)
    scheduleSave()
  }

  /** 编辑单元格 → 公式重算 → 关联方匹配 → debounce 保存 */
  function updateCell(rowId: string, field: string, value: number | string): void {
    if (isReadonly.value) return
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return

    const row = { ...rows.value[idx] }

    // String fields
    if (field === 'customerName') {
      row.customerName = String(value)
      // Auto-trigger related party matching when customerName changes
      row.relationType = matchRelatedParty(row.customerName)
    } else if (field === 'companyCode') {
      row.companyCode = String(value)
    } else if (field === 'relationType') {
      row.relationType = String(value)
    } else {
      // Numeric fields（期末余额为计算列，不可编辑）
      const numericFields: Array<keyof CustomerRow> = [
        'priorUnadjusted', 'priorAje', 'priorRje',
        'currentIncrease', 'currentDecrease',
        'reclassification',
        'currentAje', 'currentRje',
        'postSettlement',
      ]
      if (numericFields.includes(field as keyof CustomerRow)) {
        ;(row as any)[field] = parseNum(value)
      }
    }

    // Recalculate computed fields
    const recalculated = recalcRow(row)

    // Update the rows array immutably
    const newRows = [...rows.value]
    newRows[idx] = recalculated
    rows.value = newRows

    scheduleSave()
  }

  // ─── 期后兑付一键取数（P1-6）─────────────────────────────────────────────

  /** 归一化名称（去空白/全角空格，小写）供分录摘要模糊匹配 */
  function normalizeName(s: string): string {
    return String(s ?? '').replace(/[\s\u3000]+/g, '').toLowerCase()
  }

  /**
   * 从序时账取期后兑付/回款（资产负债表日后科目 1121 贷方发生额），按客户归集填入 postSettlement。
   *
   * 数据源：GET /projects/{pid}/ledger/entries/1121?year={bsYear+1}&date_from&date_to（贷方=票据减少=承兑收款）
   * 归集：按客户名规范化匹配分录摘要/对方科目/辅助核算名；仅精确包含才计入。
   * 交互：预览"匹配 N 户合计 X / 未匹配 M 笔 Y"→确认后填入 postSettlement（覆盖同客户原值）。
   *
   * 期后兑付是应收票据存在性与可回收性的关键证据（票据到期承兑）。
   * @param monthsAfter 取数窗口月数（默认 6，覆盖典型审计报告日）
   */
  async function importPostSettlementFromLedger(monthsAfter = 6): Promise<{ matched: number; filledAmount: number; unmatchedCount: number; unmatchedAmount: number }> {
    const empty = { matched: 0, filledAmount: 0, unmatchedCount: 0, unmatchedAmount: 0 }
    if (isReadonly.value) return empty
    if (rows.value.length === 0) {
      ElMessage.info('请先录入或导入客户明细后再取期后兑付')
      return empty
    }
    const pid = projectId?.value
    if (!pid) {
      ElMessage.warning('缺少项目信息，无法取数')
      return empty
    }
    const bs = (bsDate?.value || '').trim()
    if (!/^\d{4}-\d{2}-\d{2}$/.test(bs)) {
      ElMessage.warning('资产负债表日无效，无法确定期后兑付窗口')
      return empty
    }
    const start = new Date(`${bs}T00:00:00`)
    start.setDate(start.getDate() + 1)
    const end = new Date(start)
    end.setMonth(end.getMonth() + monthsAfter)
    const fmt = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    const dateFrom = fmt(start)
    const dateTo = fmt(end)
    const postYear = start.getFullYear()

    try {
      const token = sessionStorage.getItem('token') || ''
      const url = `/api/projects/${pid}/ledger/entries/1121?year=${postYear}`
        + `&date_from=${encodeURIComponent(dateFrom)}&date_to=${encodeURIComponent(dateTo)}&limit=1000`
      const resp = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      if (!resp.ok) {
        ElMessage.info(`期后（${postYear}年）序时账无数据或未导入`)
        return empty
      }
      const result = await resp.json()
      const payload = result?.data ?? result
      const items: any[] = Array.isArray(payload) ? payload
        : Array.isArray(payload?.items) ? payload.items
        : Array.isArray(payload?.ledger?.items) ? payload.ledger.items
        : []
      if (items.length === 0) {
        ElMessage.info(`期后（${dateFrom} 至 ${dateTo}）无 1121 兑付分录`)
        return empty
      }

      const rowSums = new Map<string, number>()
      let unmatchedCount = 0
      let unmatchedAmount = 0
      for (const it of items) {
        const credit = Number(it.credit_amount) || 0
        if (credit <= 0) continue // 只取贷方（票据减少=承兑收款）
        const text = normalizeName(`${it.summary ?? ''} ${it.counterpart_account ?? ''} ${it.aux_name ?? ''}`)
        let hitId: string | null = null
        for (const row of rows.value) {
          const name = normalizeName(row.customerName)
          if (name.length >= 2 && text.includes(name)) { hitId = row.rowId; break }
        }
        if (hitId) {
          rowSums.set(hitId, (rowSums.get(hitId) || 0) + credit)
        } else {
          unmatchedCount++
          unmatchedAmount += credit
        }
      }

      const matched = rowSums.size
      const filledAmount = Array.from(rowSums.values()).reduce((s, v) => s + v, 0)
      if (matched === 0 && unmatchedCount === 0) {
        ElMessage.info('期后窗口内无兑付分录')
        return empty
      }

      const fmtAmt = (v: number) => v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
      try {
        await ElMessageBox.confirm(
          `期后窗口 ${dateFrom} 至 ${dateTo}（${postYear}年）：\n`
          + `可归集 ${matched} 户，合计兑付 ${fmtAmt(filledAmount)} 元；\n`
          + `未匹配 ${unmatchedCount} 笔，合计 ${fmtAmt(unmatchedAmount)} 元（需手工分配）。\n`
          + `确认后将按客户填入"期后兑付"列（覆盖同客户原值），是否继续？`,
          '期后兑付取数确认',
          { confirmButtonText: '填入', cancelButtonText: '取消', type: 'warning' },
        )
      } catch {
        return empty // 用户取消
      }

      const newRows = rows.value.map(r => {
        const amt = rowSums.get(r.rowId)
        return amt !== undefined ? { ...r, postSettlement: amt } : r
      })
      rows.value = newRows
      if (matched > 0) scheduleSave()

      ElMessage.success(`期后兑付取数完成：填入 ${matched} 户，合计 ${fmtAmt(filledAmount)} 元`)
      return { matched, filledAmount, unmatchedCount, unmatchedAmount }
    } catch {
      ElMessage.error('期后兑付取数失败')
      return empty
    }
  }

  // ─── Audit meta save ─────────────────────────────────────────────────────

  function saveAuditProcedures(text: string): void {
    if (isReadonly.value) return
    auditProcedures.value = text
    scheduleMetaSave()
  }

  function saveAuditNote(text: string): void {
    if (isReadonly.value) return
    auditNote.value = text
    scheduleMetaSave()
  }

  function saveAuditConclusion(text: string): void {
    if (isReadonly.value) return
    auditConclusion.value = text
    scheduleMetaSave()
  }

  // ─── Cleanup ─────────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (saveTimer) {
      clearTimeout(saveTimer)
      persistRows()
    }
    if (metaSaveTimer) {
      clearTimeout(metaSaveTimer)
      persistMeta()
    }
  })

  // ─── Return ──────────────────────────────────────────────────────────────

  return {
    rows,
    filteredRows,
    subtotalRow,
    searchQuery,
    auditProcedures,
    auditNote,
    auditConclusion,
    addRow,
    removeRow,
    updateCell,
    matchRelatedParty,
    importPostSettlementFromLedger,
    saveAuditProcedures,
    saveAuditNote,
    saveAuditConclusion,
  }
}
