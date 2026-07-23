/**
 * useD5Detail — D5-2 明细表核心逻辑 composable
 *
 * Spec: .kiro/specs/d5-receivables-financing/
 * Task: 7.1
 *
 * 职责：
 * - 定义 DetailRow 类型（17列完整字段 A~Q）
 * - rows reactive（从D5-2-rows加载JSON数组）
 * - 行内公式自动计算（F=C+D+E, J=F+H-I, L=J+K, O=L+M+N）
 * - subtotalByCategory computed（应收票据小计/应收账款小计）+ totalRow computed
 * - addRow/removeRow/updateCell
 * - importFromD1（EventBus请求D1出售模式票据）
 * - importFromD2（EventBus请求D2出售模式账款）
 * - importFromAuxBalance（调后端API从tb_aux_balance科目1124导入）
 * - 对"类别"列应用下拉选择（应收票据/应收账款）
 *
 * Requirements: 4.1-4.9, 5.1-5.7
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import {
  parseNum,
  calcAuditedAmount,
  calcEndBalance,
  calcEndUnadjusted,
  calcEndAudited,
  calcSubtotal,
} from './useD5FormulaEngine'
import { api } from '@/services/apiProxy'
import type { ChecklistResponse } from './useD5FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface DetailRow {
  rowId: string
  category: string            // A: 类别（应收票据/应收账款）
  itemName: string            // B: 明细项目
  priorUnadjusted: number     // C: 期初未审
  priorAje: number            // D: 期初AJE
  priorRje: number            // E: 期初RJE
  priorAudited: number        // F: =C+D+E（自动）
  ociImpairment: number       // G: OCI减值准备余额
  periodIncrease: number      // H: 本期增加
  periodDecrease: number      // I: 本期减少
  endBalance: number          // J: =F+H-I（自动）
  entityReclass: number       // K: 被审计单位重分类
  endUnadjusted: number       // L: =J+K（自动）
  endAje: number              // M: 期末账项调整
  endRje: number              // N: 期末重分类调整
  endAudited: number          // O: =L+M+N（自动）
  endOciImpairment: number    // P: 期末OCI减值
  postRealized: number        // R: 期后兑现金额(验证完整性)
  eclStage: string            // S: ECL信用风险阶段(阶段一/阶段二/阶段三)
  remark: string              // Q: 备注
}

export type SaveFn = (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
export type DebouncedSaveFn = (itemId: string, data: Partial<ChecklistResponse>) => void

export interface UseD5DetailOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: SaveFn
  debouncedSave: DebouncedSaveFn
  isReadonly: Ref<boolean>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'D5-2-rows'

/** 类别下拉选项 */
export const CATEGORY_OPTIONS = ['应收票据', '应收账款'] as const

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
    category: raw.category || '',
    itemName: raw.itemName || '',
    priorUnadjusted: parseNum(raw.priorUnadjusted),
    priorAje: parseNum(raw.priorAje),
    priorRje: parseNum(raw.priorRje),
    priorAudited: parseNum(raw.priorAudited),
    ociImpairment: parseNum(raw.ociImpairment),
    periodIncrease: parseNum(raw.periodIncrease),
    periodDecrease: parseNum(raw.periodDecrease),
    endBalance: parseNum(raw.endBalance),
    entityReclass: parseNum(raw.entityReclass),
    endUnadjusted: parseNum(raw.endUnadjusted),
    endAje: parseNum(raw.endAje),
    endRje: parseNum(raw.endRje),
    endAudited: parseNum(raw.endAudited),
    endOciImpairment: parseNum(raw.endOciImpairment),
    postRealized: parseNum(raw.postRealized),
    eclStage: raw.eclStage || '',
    remark: raw.remark || '',
  }
}

/**
 * 对单行重新计算公式链：
 * F = C + D + E（期初审定 = 期初未审 + AJE + RJE）
 * J = F + H - I（期末余额 = 期初审定 + 本期增加 - 本期减少）
 * L = J + K（期末未审余额 = 期末余额 + 重分类）
 * O = L + M + N（期末审定余额 = 期末未审 + 账项调整 + 重分类调整）
 */
export function recalcRow(row: DetailRow): DetailRow {
  const F = calcAuditedAmount(row.priorUnadjusted, row.priorAje, row.priorRje)
  const J = calcEndBalance(F, row.periodIncrease, row.periodDecrease)
  const L = calcEndUnadjusted(J, row.entityReclass)
  const O = calcEndAudited(L, row.endAje, row.endRje)

  return {
    ...row,
    priorAudited: F,
    endBalance: J,
    endUnadjusted: L,
    endAudited: O,
  }
}

/** 创建空行（所有数值为 0） */
export function createEmptyRow(): DetailRow {
  return {
    rowId: generateRowId(),
    category: '',
    itemName: '',
    priorUnadjusted: 0,
    priorAje: 0,
    priorRje: 0,
    priorAudited: 0,
    ociImpairment: 0,
    periodIncrease: 0,
    periodDecrease: 0,
    endBalance: 0,
    entityReclass: 0,
    endUnadjusted: 0,
    endAje: 0,
    endRje: 0,
    endAudited: 0,
    endOciImpairment: 0,
    postRealized: 0,
    eclStage: '',
    remark: '',
  }
}

/**
 * 计算一组行的各列合计（用于 subtotal / total）
 */
function sumRows(rows: DetailRow[], label: string): DetailRow {
  return {
    rowId: `__${label}__`,
    category: label,
    itemName: '',
    priorUnadjusted: calcSubtotal(rows.map(r => r.priorUnadjusted)),
    priorAje: calcSubtotal(rows.map(r => r.priorAje)),
    priorRje: calcSubtotal(rows.map(r => r.priorRje)),
    priorAudited: calcSubtotal(rows.map(r => r.priorAudited)),
    ociImpairment: calcSubtotal(rows.map(r => r.ociImpairment)),
    periodIncrease: calcSubtotal(rows.map(r => r.periodIncrease)),
    periodDecrease: calcSubtotal(rows.map(r => r.periodDecrease)),
    endBalance: calcSubtotal(rows.map(r => r.endBalance)),
    entityReclass: calcSubtotal(rows.map(r => r.entityReclass)),
    endUnadjusted: calcSubtotal(rows.map(r => r.endUnadjusted)),
    endAje: calcSubtotal(rows.map(r => r.endAje)),
    endRje: calcSubtotal(rows.map(r => r.endRje)),
    endAudited: calcSubtotal(rows.map(r => r.endAudited)),
    endOciImpairment: calcSubtotal(rows.map(r => r.endOciImpairment)),
    postRealized: calcSubtotal(rows.map(r => r.postRealized)),
    eclStage: '',
    remark: '',
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD5Detail(options: UseD5DetailOptions) {
  const { allResponses, wpId: _wpId, projectId, debouncedSave, isReadonly } = options
  void _wpId // reserved for future use (e.g., import endpoints)

  const eventListeners: Array<{ event: string; handler: (e: Event) => void }> = []

  // ─── Reactive rows ───────────────────────────────────────────────────

  const rows = ref<DetailRow[]>([])

  // Load rows from allResponses
  watch(
    () => allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (jsonStr) => {
      const parsed = safeParseRows(jsonStr)
      // Recalculate formula chain for each row
      rows.value = parsed.map(recalcRow)
    },
    { immediate: true },
  )

  // ─── Persist ─────────────────────────────────────────────────────────

  function persistRows(): void {
    debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
  }

  // ─── subtotalByCategory computed ─────────────────────────────────────

  /**
   * 按类别分组小计：应收票据小计 + 应收账款小计
   */
  const subtotalByCategory: ComputedRef<Record<string, DetailRow>> = computed(() => {
    const result: Record<string, DetailRow> = {}

    for (const cat of CATEGORY_OPTIONS) {
      const catRows = rows.value.filter(r => r.category === cat)
      result[cat] = sumRows(catRows, `${cat}小计`)
    }

    return result
  })

  // ─── totalRow computed ───────────────────────────────────────────────

  /**
   * 总合计行：所有明细行的合计
   */
  const totalRow: ComputedRef<DetailRow> = computed(() => {
    return sumRows(rows.value, '合计')
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

    // Numeric fields (input → recalc)
    const numericFields = [
      'priorUnadjusted', 'priorAje', 'priorRje',
      'ociImpairment', 'periodIncrease', 'periodDecrease',
      'entityReclass', 'endAje', 'endRje',
      'endOciImpairment', 'postRealized',
    ]

    if (numericFields.includes(field)) {
      ;(row as any)[field] = parseNum(value)
    } else {
      // String fields: category, itemName, remark
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

  // ─── importFromD1（从D1导入出售模式票据）─────────────────────────────

  /**
   * 通过EventBus请求D1底稿中业务模式为"出售"的票据数据
   * 导入为类别=应收票据的明细行
   */
  async function importFromD1(): Promise<void> {
    if (isReadonly.value) return

    return new Promise<void>((resolve) => {
      // 监听D1响应事件
      const responseHandler = (e: Event) => {
        const detail = (e as CustomEvent).detail
        window.removeEventListener('d1:export-sold-notes-response', responseHandler)

        if (!detail?.rows || !Array.isArray(detail.rows) || detail.rows.length === 0) {
          ElMessage.info('未找到D1出售模式票据数据')
          resolve()
          return
        }

        // 将D1数据转为D5-2明细行
        const importedRows: DetailRow[] = detail.rows.map((item: any) => {
          const row = normalizeRow({
            rowId: generateRowId(),
            category: '应收票据',
            itemName: item.itemName || item.billName || item.drawer || '',
            priorUnadjusted: item.priorUnadjusted ?? item.faceValue ?? 0,
            periodIncrease: item.periodIncrease ?? 0,
            periodDecrease: item.periodDecrease ?? 0,
          })
          return recalcRow(row)
        })

        rows.value = [...rows.value, ...importedRows]
        persistRows()
        ElMessage.success(`成功从D1导入${importedRows.length}笔应收票据`)
        resolve()
      }

      window.addEventListener('d1:export-sold-notes-response', responseHandler)

      // 发送请求事件
      window.dispatchEvent(new CustomEvent('d1:export-sold-notes-request', {
        detail: { wpCode: 'D5', requestType: 'sold-notes' },
      }))

      // 超时兜底（5秒无响应）
      setTimeout(() => {
        window.removeEventListener('d1:export-sold-notes-response', responseHandler)
        resolve()
      }, 5000)
    })
  }

  // ─── importFromD2（从D2导入出售模式账款）─────────────────────────────

  /**
   * 通过EventBus请求D2底稿中业务模式为"出售"的应收账款数据
   * 导入为类别=应收账款的明细行
   */
  async function importFromD2(): Promise<void> {
    if (isReadonly.value) return

    return new Promise<void>((resolve) => {
      // 监听D2响应事件
      const responseHandler = (e: Event) => {
        const detail = (e as CustomEvent).detail
        window.removeEventListener('d2:export-sold-receivables-response', responseHandler)

        if (!detail?.rows || !Array.isArray(detail.rows) || detail.rows.length === 0) {
          ElMessage.info('未找到D2出售模式应收账款数据')
          resolve()
          return
        }

        // 将D2数据转为D5-2明细行
        const importedRows: DetailRow[] = detail.rows.map((item: any) => {
          const row = normalizeRow({
            rowId: generateRowId(),
            category: '应收账款',
            itemName: item.itemName || item.customerName || '',
            priorUnadjusted: item.priorUnadjusted ?? item.balance ?? 0,
            periodIncrease: item.periodIncrease ?? 0,
            periodDecrease: item.periodDecrease ?? 0,
          })
          return recalcRow(row)
        })

        rows.value = [...rows.value, ...importedRows]
        persistRows()
        ElMessage.success(`成功从D2导入${importedRows.length}笔应收账款`)
        resolve()
      }

      window.addEventListener('d2:export-sold-receivables-response', responseHandler)

      // 发送请求事件
      window.dispatchEvent(new CustomEvent('d2:export-sold-receivables-request', {
        detail: { wpCode: 'D5', requestType: 'sold-receivables' },
      }))

      // 超时兜底（5秒无响应）
      setTimeout(() => {
        window.removeEventListener('d2:export-sold-receivables-response', responseHandler)
        resolve()
      }, 5000)
    })
  }

  // ─── importFromAuxBalance（从余额表导入）──────────────────────────────

  /**
   * 调后端API从tb_aux_balance科目1124按明细维度导入
   */
  async function importFromAuxBalance(): Promise<void> {
    if (isReadonly.value || !projectId.value) return

    try {
      const res = await api.get(
        `/api/projects/${projectId.value}/tb-aux-balance`,
        { params: { account_code: '1124' } },
      )
      const importedData: any[] = Array.isArray(res) ? res : (res?.data ?? res?.rows ?? [])

      if (importedData.length === 0) {
        ElMessage.info('未找到科目1124的辅助余额数据')
        return
      }

      // Merge imported rows into existing (add new items, update existing)
      const existingMap = new Map(rows.value.map(r => [r.itemName, r]))
      let newCount = 0

      for (const imported of importedData) {
        const name = imported.itemName || imported.item_name || imported.aux_name || ''
        if (!name) continue

        if (existingMap.has(name)) {
          // Update existing row with imported data
          const existing = { ...existingMap.get(name)! }
          existing.priorUnadjusted = parseNum(imported.priorUnadjusted ?? imported.prior_unadjusted ?? imported.begin_balance)
          // Recalculate formula chain
          const recalculated = recalcRow(existing)
          existingMap.set(name, recalculated)
        } else {
          // New item row
          const category = imported.category || imported.aux_category || ''
          const newRow = normalizeRow({
            rowId: generateRowId(),
            category: category || '应收票据',
            itemName: name,
            priorUnadjusted: imported.priorUnadjusted ?? imported.prior_unadjusted ?? imported.begin_balance ?? 0,
            periodIncrease: imported.periodIncrease ?? imported.period_increase ?? imported.debit ?? 0,
            periodDecrease: imported.periodDecrease ?? imported.period_decrease ?? imported.credit ?? 0,
          })
          const recalculated = recalcRow(newRow)
          existingMap.set(name, recalculated)
          newCount++
        }
      }

      rows.value = Array.from(existingMap.values())
      persistRows()

      ElMessage.success(`成功导入${importedData.length}行数据，${newCount}个新明细项目`)
    } catch {
      ElMessage.error('从辅助余额表导入失败，请稍后重试')
    }
  }

  // ─── importPostRealizedFromLedger（从次年序时账取期后兑现）──────────

  /**
   * 从次年序时账1124贷方（兑付/贴现/背书=贷方减少）按明细名归集期后兑现金额
   * 仅填入空值行(postRealized===0)，不覆盖已手工填入的数据
   */
  async function importPostRealizedFromLedger(bsDate: string): Promise<void> {
    if (isReadonly.value || !projectId.value) return

    const bsYear = bsDate ? parseInt(bsDate.substring(0, 4)) : new Date().getFullYear()
    const nextYear = bsYear + 1
    const dateFrom = `${nextYear}-01-01`
    const dateTo = `${nextYear}-06-30` // 默认期后窗口6个月

    try {
      const res = await api.get(
        `/api/projects/${projectId.value}/ledger/entries`,
        {
          params: {
            account_code: '1124',
            year: nextYear,
            date_from: dateFrom,
            date_to: dateTo,
          },
        },
      )
      const entries: any[] = Array.isArray(res) ? res : (res?.data ?? res?.items ?? [])

      if (entries.length === 0) {
        ElMessage.info('未找到期后序时账1124贷方数据')
        return
      }

      // 按摘要/对方科目名归集贷方金额(1124贷方=减少=兑现)
      const realizedMap = new Map<string, number>()
      for (const entry of entries) {
        const credit = parseNum(entry.credit_amount ?? entry.credit)
        if (credit <= 0) continue
        const name = entry.summary || entry.counterpart_name || entry.item_name || '未命名'
        realizedMap.set(name, (realizedMap.get(name) || 0) + credit)
      }

      if (realizedMap.size === 0) {
        ElMessage.info('期后无1124贷方发生额(无兑现)')
        return
      }

      // 按名称模糊匹配回填
      let fillCount = 0
      const newRows = rows.value.map(row => {
        if (row.postRealized !== 0) return row // 已有值不覆盖
        // 精确匹配优先,再模糊
        let matched = realizedMap.get(row.itemName)
        if (matched === undefined) {
          // 双向包含
          for (const [name, amount] of realizedMap) {
            if (row.itemName && (name.includes(row.itemName) || row.itemName.includes(name))) {
              matched = amount
              break
            }
          }
        }
        if (matched !== undefined && matched > 0) {
          fillCount++
          return { ...row, postRealized: matched }
        }
        return row
      })

      rows.value = newRows
      persistRows()
      ElMessage.success(`期后兑现取数完成：匹配${fillCount}笔，序时账共${realizedMap.size}个对方`)
    } catch {
      ElMessage.error('从序时账取数失败，请稍后重试')
    }
  }

  // ─── Cleanup EventBus listeners ─────────────────────────────────────

  onBeforeUnmount(() => {
    for (const { event, handler } of eventListeners) {
      window.removeEventListener(event, handler)
    }
  })

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    rows,
    subtotalByCategory,
    totalRow,
    // 操作
    addRow,
    removeRow,
    updateCell,
    // 导入
    importFromD1,
    importFromD2,
    importFromAuxBalance,
    importPostRealizedFromLedger,
  }
}

export default useD5Detail
