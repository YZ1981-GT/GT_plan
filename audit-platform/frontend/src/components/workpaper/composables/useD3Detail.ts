/**
 * useD3Detail — D3-2 明细表核心逻辑 composable
 *
 * Spec: .kiro/specs/d3-prepaid-accounts/
 * Task: 7.1, aging-config-enhancement Task 8.1
 *
 * 职责：
 * - 定义 DetailRow 类型（动态账龄段，2-period: agingPrior/agingAudited）
 * - rows reactive（从D3-det-rows加载JSON数组）
 * - 行内公式自动计算（H=E+F+G, O=H+N-M, Q=O+P, T=Q+R+S）
 * - subtotalRow computed + verificationRow computed（合计-TB数）
 * - searchQuery + filteredRows computed（模糊搜索）
 * - addRow/removeRow/updateCell
 * - matchRelatedParty（从relatedParties列表包含匹配）
 * - importFromAuxBalance（调后端API批量导入）
 * - onConfirmationCompleted监听（标记isConfirmed='Y'）
 * - 动态账龄配置集成（useAgingConfig + migrateD3F1Keys + remapRowAgingData）
 *
 * Requirements: 4.1-4.12, 5.1-5.7, 6.1-6.5, 18.4
 * Aging Config Requirements: 5.1, 5.2, 5.3, 5.4
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
} from './useD3FormulaEngine'
import { api } from '@/services/apiProxy'
import {
  parseAuxImportResponse,
  auxImportPrompt,
  AUX_IMPORT_NETWORK_ERROR_PROMPT,
} from './fourTableAuxImportFeedback'
import type { ChecklistResponse } from './useD3FormData'
import { useAgingConfig, type AgingSegment } from '@/composables/useAgingConfig'
import { migrateD3F1Keys, remapRowAgingData, type AgingData } from '@/composables/useAgingMigration'

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
  agingPrior: AgingData      // I~L (动态账龄段，key 由项目配置决定)
  debit: number              // M: 借方发生
  credit: number             // N: 贷方发生
  endBalance: number         // O: =H+N-M（贷方科目，自动）
  entityReclass: number      // P: 被审计单位重分类调整
  endUnadjusted: number      // Q: =O+P（自动）
  endAje: number             // R: 期末账项调整
  endRje: number             // S: 期末重分类调整
  endAudited: number         // T: =Q+R+S（自动）
  agingAudited: AgingData    // U~X (动态账龄段，key 由项目配置决定)
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

const ITEM_ID_ROWS = 'D3-det-rows'
const ITEM_ID_TB_AMOUNT = 'D3-adj-trial-balance-amount'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `row-${crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2)}`
}

/** 安全解析 JSON 数组（使用动态 segments 进行迁移） */
function safeParseRows(jsonStr: string | null | undefined, segments: AgingSegment[]): DetailRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed.map(raw => normalizeRow(raw, segments)) : []
  } catch {
    return []
  }
}

/** 规范化行数据，确保所有字段存在且类型正确（使用动态 segments） */
function normalizeRow(raw: any, segments: AgingSegment[]): DetailRow {
  // 使用 migrateD3F1Keys 对齐 aging key 到当前项目配置
  const migrated = migrateD3F1Keys(raw, segments)

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
    agingPrior: migrated.agingPrior,
    debit: parseNum(raw.debit),
    credit: parseNum(raw.credit),
    endBalance: parseNum(raw.endBalance),
    entityReclass: parseNum(raw.entityReclass),
    endUnadjusted: parseNum(raw.endUnadjusted),
    endAje: parseNum(raw.endAje),
    endRje: parseNum(raw.endRje),
    endAudited: parseNum(raw.endAudited),
    agingAudited: migrated.agingAudited,
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

/** 创建空行（账龄段基于当前项目配置动态初始化为 0） */
export function createEmptyRow(segments: AgingSegment[] = []): DetailRow {
  const emptyAging: AgingData = {}
  for (const seg of segments) {
    emptyAging[seg.key] = 0
  }
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
    agingPrior: { ...emptyAging },
    debit: 0,
    credit: 0,
    endBalance: 0,
    entityReclass: 0,
    endUnadjusted: 0,
    endAje: 0,
    endRje: 0,
    endAudited: 0,
    agingAudited: { ...emptyAging },
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

export function useD3Detail(options: UseD3DetailOptions) {
  const { allResponses, wpId, projectId, debouncedSave, isReadonly, relatedParties } = options

  const eventListeners: Array<{ event: string; handler: (e: Event) => void }> = []

  // ─── Aging Config Integration (subject='D3', 2-period) ──────────────

  const { segments, bands } = useAgingConfig(projectId, 'D3')

  // ─── Reactive rows ───────────────────────────────────────────────────

  const rows = ref<DetailRow[]>([])
  const searchQuery = ref<string>('')

  // Load rows from allResponses (with migration via migrateD3F1Keys)
  watch(
    [() => allResponses.value.get(ITEM_ID_ROWS)?.remark, segments],
    ([jsonStr]) => {
      if (!segments.value.length) return  // 等待 segments 加载完成
      const parsed = safeParseRows(jsonStr as string | undefined, segments.value)
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
    // 动态合计 aging 数据
    const agingPriorSub: AgingData = {}
    const agingAuditedSub: AgingData = {}
    for (const seg of segments.value) {
      agingPriorSub[seg.key] = calcSubtotal(allRows.map(r => r.agingPrior?.[seg.key] ?? 0))
      agingAuditedSub[seg.key] = calcSubtotal(allRows.map(r => r.agingAudited?.[seg.key] ?? 0))
    }

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
      agingPrior: agingPriorSub,
      debit: calcSubtotal(allRows.map(r => r.debit)),
      credit: calcSubtotal(allRows.map(r => r.credit)),
      endBalance: calcSubtotal(allRows.map(r => r.endBalance)),
      entityReclass: calcSubtotal(allRows.map(r => r.entityReclass)),
      endUnadjusted: calcSubtotal(allRows.map(r => r.endUnadjusted)),
      endAje: calcSubtotal(allRows.map(r => r.endAje)),
      endRje: calcSubtotal(allRows.map(r => r.endRje)),
      endAudited: calcSubtotal(allRows.map(r => r.endAudited)),
      agingAudited: agingAuditedSub,
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
    const newRow = createEmptyRow(segments.value)
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

    // Handle nested aging fields (dynamic keys)
    if (field.startsWith('agingPrior.')) {
      const subField = field.replace('agingPrior.', '')
      row.agingPrior = { ...row.agingPrior, [subField]: parseNum(value) }
    } else if (field.startsWith('agingAudited.')) {
      const subField = field.replace('agingAudited.', '')
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

  /**
   * 从辅助余额表导入 D3-2（预收账款科目由 BS-046 报表映射解析，兜底 2203）.
   *
   * 🔴 D3-2 明细表的**实际入口**是 `useD3ImportExport.importFromAuxBalance`（经
   * `useD3TabImportExport.onImportFromAuxBalance` → 宿主 reloadWorkpaperData 级联刷新）。
   * 迁移后端（spec four-table-extraction-entry-completion / Task 4）已改服务端 merge 落库 +
   * reason 码，不再返回 rows[]，故此处不再客户端拼行/客户端 merge（旧实现读
   * `res?.data ?? res?.rows` 会与服务端 merge 双写且恒空）。仅消费端点、按 reason 码给
   * 可辨别提示（Requirement 4.4）；行刷新由宿主 reload 后 D3-2-rows watch 驱动。
   */
  async function importFromAuxBalance(): Promise<void> {
    if (!wpId.value) return
    try {
      const res = await api.post(
        `/api/workpapers/${wpId.value}/d3/import-aux-balance`,
        { project_id: projectId.value },
      )
      const outcome = parseAuxImportResponse(res)
      const { level, text } = auxImportPrompt(outcome)
      ElMessage[level]({ message: text })
    } catch {
      const { level, text } = AUX_IMPORT_NETWORK_ERROR_PROMPT
      ElMessage[level]({ message: text })
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

  // ─── Aging Config Changed EventBus ──────────────────────────────────

  const agingConfigHandler = () => {
    // 配置变更时：对每行调用 remapRowAgingData 保留已有段/零初始化新增段
    if (!segments.value.length) return
    rows.value = rows.value.map(row =>
      remapRowAgingData(row, segments.value, false) as DetailRow,
    )
    persistRows()
  }
  window.addEventListener('aging-config:changed', agingConfigHandler)
  eventListeners.push({ event: 'aging-config:changed', handler: agingConfigHandler })

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
    // 账龄配置
    segments,
    bands,
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

export default useD3Detail
