/**
 * useD7Detail — D7-2 明细表核心逻辑 composable（动态账龄段，2-period）
 *
 * 贷方科目公式链（4步）：
 *   期初审定 = 期初未审 + AJE + RJE
 *   期末余额 = 期初审定 + 贷方发生 - 借方发生（贷方科目：贷增借减）
 *   期末未审 = 期末余额 + 被审计单位重分类调整
 *   期末审定 = 期末未审 + AJE + RJE
 *
 * 账龄：nested keyed（agingPrior / agingAudited，key 由项目账龄配置决定，2-period），
 * 复用 useAgingConfig(subject='D7') + migrateD7FlatToNested + migrateD3F1Keys + remapRowAgingData。
 *
 * Spec: .kiro/specs/d7-contract-liabilities-enhancement/
 * Task: 3
 * Requirements: 2.1, 2.2, 2.3, 8.1-8.4
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import {
  parseNum,
  calcAuditedAmount,
  calcCreditEndBalance,
  calcSubtotal,
} from './useD7FormulaEngine'
import { eventBus } from '@/utils/eventBus'
import { matchRelatedPartyPure } from './useD3Detail'
import {
  parseAuxImportResponse,
  auxImportPrompt,
  AUX_IMPORT_NETWORK_ERROR_PROMPT,
} from './fourTableAuxImportFeedback'
import type { ChecklistResponse } from './useD7FormData'
import { useAgingConfig, type AgingSegment } from '@/composables/useAgingConfig'
import { migrateD7FlatToNested, migrateD3F1Keys, remapRowAgingData, type AgingData } from '@/composables/useAgingMigration'

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
  agingPrior: AgingData        // 期初审定账龄（nested keyed）
  debitAmount: number          // 借方发生
  creditAmount: number         // 贷方发生
  endBalance: number           // 期末余额（自动）
  entityReclass: number        // 被审计单位重分类调整
  endUnadjusted: number        // 期末未审余额（自动）
  endAje: number               // 账项调整
  endRje: number               // 重分类调整
  endAudited: number           // 期末审定数（自动）
  agingAudited: AgingData      // 期末审定账龄（nested keyed）
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
  isReadonly?: Ref<boolean>
  /** 从余额表导入成功后由宿主重载 allResponses（级联审定表/披露刷新，Requirement 4.6）。 */
  onImported?: () => Promise<void> | void
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

/** 安全解析 JSON 数组（使用动态 segments 迁移账龄至当前配置段） */
function safeParseRows(jsonStr: string | null | undefined, segments: AgingSegment[]): DetailRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed.map(raw => normalizeRow(raw, segments)) : []
  } catch {
    return []
  }
}

/** 规范化行：扁平→nested 迁移 + 对齐当前项目账龄段（Task 2 迁移链） */
export function normalizeRow(raw: any, segments: AgingSegment[] = []): DetailRow {
  // 1) 扁平字段 → nested keyed（nested 优先，忽略扁平）；2) 对齐当前段（2-period）
  const migrated = migrateD3F1Keys(migrateD7FlatToNested(raw), segments)
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
    agingPrior: migrated.agingPrior,
    debitAmount: parseNum(raw.debitAmount),
    creditAmount: parseNum(raw.creditAmount),
    endBalance: parseNum(raw.endBalance),
    entityReclass: parseNum(raw.entityReclass),
    endUnadjusted: parseNum(raw.endUnadjusted),
    endAje: parseNum(raw.endAje),
    endRje: parseNum(raw.endRje),
    endAudited: parseNum(raw.endAudited),
    agingAudited: migrated.agingAudited,
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

/** 创建空行（账龄段按当前项目配置动态零初始化） */
export function createEmptyRow(segments: AgingSegment[] = []): DetailRow {
  const emptyAging: AgingData = {}
  for (const seg of segments) emptyAging[seg.key] = 0
  return {
    rowId: generateRowId(),
    contractName: '', companyName: '', companyCode: '',
    relatedPartyType: '', natureType: '',
    priorUnadjusted: 0, priorAje: 0, priorRje: 0, priorAudited: 0,
    agingPrior: { ...emptyAging },
    debitAmount: 0, creditAmount: 0, endBalance: 0,
    entityReclass: 0, endUnadjusted: 0, endAje: 0, endRje: 0, endAudited: 0,
    agingAudited: { ...emptyAging },
    isConfirmed: '', postTransfer: 0,
  }
}

function sumRows(rows: DetailRow[], label: string, segments: AgingSegment[]): DetailRow {
  const agingPriorSub: AgingData = {}
  const agingAuditedSub: AgingData = {}
  for (const seg of segments) {
    agingPriorSub[seg.key] = calcSubtotal(rows.map(r => r.agingPrior?.[seg.key] ?? 0))
    agingAuditedSub[seg.key] = calcSubtotal(rows.map(r => r.agingAudited?.[seg.key] ?? 0))
  }
  return {
    rowId: `__${label}__`,
    contractName: label, companyName: '', companyCode: '',
    relatedPartyType: '', natureType: '',
    priorUnadjusted: calcSubtotal(rows.map(r => r.priorUnadjusted)),
    priorAje: calcSubtotal(rows.map(r => r.priorAje)),
    priorRje: calcSubtotal(rows.map(r => r.priorRje)),
    priorAudited: calcSubtotal(rows.map(r => r.priorAudited)),
    agingPrior: agingPriorSub,
    debitAmount: calcSubtotal(rows.map(r => r.debitAmount)),
    creditAmount: calcSubtotal(rows.map(r => r.creditAmount)),
    endBalance: calcSubtotal(rows.map(r => r.endBalance)),
    entityReclass: calcSubtotal(rows.map(r => r.entityReclass)),
    endUnadjusted: calcSubtotal(rows.map(r => r.endUnadjusted)),
    endAje: calcSubtotal(rows.map(r => r.endAje)),
    endRje: calcSubtotal(rows.map(r => r.endRje)),
    endAudited: calcSubtotal(rows.map(r => r.endAudited)),
    agingAudited: agingAuditedSub,
    isConfirmed: '',
    postTransfer: calcSubtotal(rows.map(r => r.postTransfer)),
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD7Detail(options: UseD7DetailOptions) {
  const { allResponses, debouncedSave, wpId, projectId, onImported } = options
  const relatedParties = options.relatedParties ?? ref<string[]>([])
  const isReadonly = options.isReadonly ?? ref(false)

  // ─── Aging Config Integration (subject='D7', 2-period) ──────────────

  const { segments, bands } = useAgingConfig(projectId, 'D7')

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
    [() => allResponses.value.get(ITEM_ID_ROWS)?.remark, segments],
    ([jsonStr]) => {
      if (!segments.value.length) return  // 等待 segments 加载完成，避免用空段迁移丢数据
      rows.value = safeParseRows(jsonStr as string | undefined, segments.value).map(recalcRow)
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

  const totalRow: ComputedRef<DetailRow> = computed(() => sumRows(rows.value, '合计', segments.value))

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
    if (isReadonly.value) return
    rows.value = [...rows.value, createEmptyRow(segments.value)]
    persistRows()
  }

  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    rows.value = rows.value.filter(r => r.rowId !== rowId)
    persistRows()
  }

  const NUMERIC_EDITABLE_FIELDS = [
    'priorUnadjusted', 'priorAje', 'priorRje',
    'debitAmount', 'creditAmount', 'entityReclass',
    'endAje', 'endRje',
    'postTransfer',
  ]

  function updateCell(rowId: string, field: string, value: any): void {
    if (isReadonly.value) return
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return

    const row = { ...rows.value[idx] }
    if (field.startsWith('agingPrior.')) {
      const subField = field.slice('agingPrior.'.length)
      row.agingPrior = { ...row.agingPrior, [subField]: parseNum(value) }
    } else if (field.startsWith('agingAudited.')) {
      const subField = field.slice('agingAudited.'.length)
      row.agingAudited = { ...row.agingAudited, [subField]: parseNum(value) }
    } else if (NUMERIC_EDITABLE_FIELDS.includes(field)) {
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

  /**
   * 从辅助余额表导入 D7-2（预收款项科目由 BS-047 报表映射解析，兜底 2205）.
   *
   * 🔴 迁移后端（spec four-table-extraction-entry-completion / Task 4）：统一走共享件
   * `aggregate_aux_by_name_ex`（active dataset 过滤 + 单一 aux_type 锁定 + 报表映射前缀 +
   * 账龄留空），**服务端 merge 落库**并返回 reason 码，不再返回 rows[]。前端不再客户端拼行/
   * 客户端 merge（旧实现读 `res.data?.data ?? []`，迁移后恒空 → 静默 0 行 + 与服务端 merge
   * 双写）：成功后由 `onImported` 重载 allResponses，D7-2-rows watch 自动重派生行
   * （Requirement 4.6）；0 行按 reason 码给可辨别提示（Requirement 4.4）。
   */
  async function importFromAuxBalance(): Promise<void> {
    if (!wpId.value) return
    try {
      const http = (await import('@/utils/http')).default
      const res = await http.post(
        `/api/workpapers/${wpId.value}/d7/import-aux-balance`,
        { project_id: projectId.value },
      )
      const outcome = parseAuxImportResponse(res)
      await (onImported?.() ?? Promise.resolve())
      const { level, text } = auxImportPrompt(outcome)
      ElMessage[level]({ message: text })
    } catch {
      const { level, text } = AUX_IMPORT_NETWORK_ERROR_PROMPT
      ElMessage[level]({ message: text })
    }
  }

  // ─── onConfirmationCompleted ─────────────────────────────────────────

  function _handleConfirmationCompleted(payload: any): void {
    if (!payload || payload.wpCode !== 'D7') return
    const customerName = payload.customerName
    if (!customerName) return

    rows.value = rows.value.map(r => {
      if (r.companyName === customerName) {
        return { ...r, isConfirmed: 'Y' }
      }
      return r
    })
    persistRows()
  }

  // Setup listener via eventBus (bridged from window by crossWpEventBridge)
  eventBus.on('confirmation:completed', _handleConfirmationCompleted)

  // ─── aging-config:changed 刷新（保留共有段/新增段零初始化/旧段丢弃） ──

  const _onAgingConfigChanged = (): void => {
    if (!segments.value.length) return
    rows.value = rows.value.map(row =>
      recalcRow(remapRowAgingData(row, segments.value, false) as DetailRow),
    )
    persistRows()
  }
  onMounted(() => {
    window.addEventListener('aging-config:changed', _onAgingConfigChanged)
  })

  onBeforeUnmount(() => {
    eventBus.off('confirmation:completed', _handleConfirmationCompleted)
    window.removeEventListener('aging-config:changed', _onAgingConfigChanged)
  })

  // ─── 期后结转联动 (D7-7 → D7-2) ────────────────────────────────────

  watch(
    () => allResponses.value.get('D7-7-post-rows')?.remark,
    (jsonStr) => {
      if (!jsonStr) return
      let postRows: any[] = []
      try { postRows = JSON.parse(jsonStr) } catch { return }
      if (!Array.isArray(postRows) || postRows.length === 0) return

      const transferMap = new Map<string, number>()
      for (const pr of postRows) {
        const name = pr.customerName || ''
        if (!name) continue
        transferMap.set(name, (transferMap.get(name) || 0) + parseNum(pr.creditAmount))
      }

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
    segments,
    bands,
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
