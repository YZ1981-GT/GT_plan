/**
 * useReliabilityData — D0-7 回函可靠性验证数据核心 composable
 *
 * 职责：
 * - 从 htmlData 初始化行数据（_format: reliability-v1）
 * - CRUD 操作（addRow / deleteRows / updateField / importRows）
 * - 条件列逻辑：寄回原件=是 → 验证字段清空/灰掉
 * - 看板指标（metrics）
 * - D0-1 带入：回函方式=传真/电子邮件行，按 confirm_index 去重
 * - buildPayload 构建持久化数据
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type {
  ReliabilityRow,
  ReliabilityMetrics,
  ReliabilityAuditNote,
  ReliabilityConclusion,
  ReliabilityPayload,
} from '../reliabilityTypes'

// ─── ID 生成工具 ─────────────────────────────────────────────────────────────

function generateRowId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

// ─── Props 接口 ──────────────────────────────────────────────────────────────

export interface UseReliabilityDataProps {
  /** 响应式数据源（来自底稿的 htmlData） */
  htmlData: () => any
  /** 是否只读 */
  readonly: boolean
}

// ─── 返回接口 ────────────────────────────────────────────────────────────────

export interface UseReliabilityDataReturn {
  rows: Ref<ReliabilityRow[]>
  auditNote: Ref<ReliabilityAuditNote>
  conclusion: Ref<ReliabilityConclusion>
  isDirty: Ref<boolean>

  // CRUD
  addRow: () => ReliabilityRow
  deleteRows: (ids: string[]) => void
  updateField: (rowId: string, field: string, value: any) => void
  importRows: (newRows: ReliabilityRow[]) => void

  // 条件列判断
  isVerificationDisabled: (row: ReliabilityRow) => boolean

  // 看板
  metrics: ComputedRef<ReliabilityMetrics>

  // 质量红线
  getRowQualityStatus: (row: ReliabilityRow) => 'ok' | 'warning' | 'danger'

  // 持久化
  buildPayload: () => ReliabilityPayload
}

// ─── Composable 主体 ─────────────────────────────────────────────────────────

export function useReliabilityData(props: UseReliabilityDataProps): UseReliabilityDataReturn {
  const rows = ref<ReliabilityRow[]>([])
  const auditNote = ref<ReliabilityAuditNote>({})
  const conclusion = ref<ReliabilityConclusion>({})
  const isDirty = ref(false)

  // ─── 从 htmlData 初始化 ────────────────────────────────────────────────────

  function initFromHtmlData(data: any) {
    // 仅接受本表 canonical 格式（见 reliabilityTypes.ReliabilityPayload._format）；
    // 其它格式（如其它 sheet 的 old-format）拒绝，避免误载入非本表数据。
    if (!data || data._format !== 'reliability-v1') {
      rows.value = []
      auditNote.value = {}
      conclusion.value = {}
      return
    }
    rows.value = Array.isArray(data.rows) ? data.rows.map(ensureRowId) : []
    auditNote.value = data.audit_note ?? {}
    conclusion.value = data.conclusion ?? {}
    isDirty.value = false
  }

  function ensureRowId(row: ReliabilityRow): ReliabilityRow {
    if (!row._row_id) {
      return { ...row, _row_id: generateRowId() }
    }
    return row
  }

  // 初始加载
  initFromHtmlData(props.htmlData())

  // 监听 htmlData 变化
  watch(
    () => props.htmlData(),
    (newData) => { initFromHtmlData(newData) },
    { deep: true },
  )

  // ─── 条件列逻辑 ───────────────────────────────────────────────────────────

  /**
   * 寄回原件=是 → 验证列禁用（已收回原件无需验证）
   */
  function isVerificationDisabled(row: ReliabilityRow): boolean {
    return row.original_returned === '是'
  }

  /**
   * 当寄回原件从"否"切到"是"时，清空验证字段值
   */
  function clearVerificationFields(row: ReliabilityRow): void {
    row.identity_verified = undefined
    row.identity_method = undefined
    row.email_verified = undefined
    row.email_domain = undefined
    row.phone_called = undefined
    row.phone_source = undefined
    row.reliability_note = undefined
  }

  // ─── CRUD ──────────────────────────────────────────────────────────────────

  function addRow(): ReliabilityRow {
    const maxSeq = rows.value.reduce((max, r) => Math.max(max, r.seq ?? 0), 0)
    const newRow: ReliabilityRow = {
      _row_id: generateRowId(),
      seq: maxSeq + 1,
      original_returned: '否',
      _source: 'manual',
    }
    rows.value.push(newRow)
    isDirty.value = true
    return newRow
  }

  function deleteRows(ids: string[]) {
    if (!ids.length) return
    const idSet = new Set(ids)
    rows.value = rows.value.filter((r) => !idSet.has(r._row_id!))
    isDirty.value = true
  }

  function updateField(rowId: string, field: string, value: any) {
    const row = rows.value.find((r) => r._row_id === rowId)
    if (!row) return
    ;(row as any)[field] = value

    // 条件列联动：寄回原件切到"是"时清空验证字段
    if (field === 'original_returned' && value === '是') {
      clearVerificationFields(row)
    }

    isDirty.value = true
  }

  function importRows(newRows: ReliabilityRow[]) {
    // 按 confirm_index 去重：已有相同索引号的不重复导入
    const existingIndexes = new Set(
      rows.value.map((r) => r.confirm_index).filter(Boolean),
    )
    const deduped = newRows.filter(
      (r) => !r.confirm_index || !existingIndexes.has(r.confirm_index),
    )
    const maxSeq = rows.value.reduce((max, r) => Math.max(max, r.seq ?? 0), 0)
    deduped.forEach((r, i) => {
      r._row_id = generateRowId()
      r.seq = maxSeq + i + 1
      r._source = r._source || 'auto'
      // 默认寄回原件=否（电子回函需验证）
      if (!r.original_returned) r.original_returned = '否'
    })
    rows.value.push(...deduped)
    isDirty.value = true
  }

  // ─── 质量红线 ─────────────────────────────────────────────────────────────

  /**
   * 行质量状态：
   * - 寄回原件=是：直接 ok（免验证）
   * - 结论=不可靠：danger（红）
   * - 结论空/验证未完成：warning（橙）
   * - 其余：ok
   */
  function getRowQualityStatus(row: ReliabilityRow): 'ok' | 'warning' | 'danger' {
    if (isVerificationDisabled(row)) return 'ok'
    if (row.conclusion_status === '不可靠') return 'danger'
    if (!row.conclusion_status) return 'warning'
    return 'ok'
  }

  // ─── 看板指标 ──────────────────────────────────────────────────────────────

  const metrics = computed<ReliabilityMetrics>(() => {
    const total = rows.value.length
    const originalReturned = rows.value.filter((r) => r.original_returned === '是').length
    const verified = rows.value.filter((r) => !!r.conclusion_status).length
    const reliable = rows.value.filter((r) => r.conclusion_status === '可靠').length
    const partial = rows.value.filter((r) => r.conclusion_status === '部分可靠需补充').length
    const unreliable = rows.value.filter((r) => r.conclusion_status === '不可靠').length

    return {
      total_count: total,
      verified_count: verified,
      verified_rate: total > 0 ? Math.round((verified / total) * 10000) / 100 : 0,
      reliable_count: reliable,
      partial_count: partial,
      unreliable_count: unreliable,
      original_returned_count: originalReturned,
    }
  })

  // ─── buildPayload ──────────────────────────────────────────────────────────

  function buildPayload(): ReliabilityPayload {
    return {
      _format: 'reliability-v1',
      rows: rows.value.map((row) => {
        // 寄回原件=是的行不持久化验证字段（防止脏数据残留）
        if (isVerificationDisabled(row)) {
          const { identity_verified, identity_method, email_verified, email_domain, phone_called, phone_source, reliability_note, ...rest } = row
          return rest
        }
        return { ...row }
      }),
      audit_note: auditNote.value,
      conclusion: conclusion.value,
    }
  }

  return {
    rows,
    auditNote,
    conclusion,
    isDirty,

    addRow,
    deleteRows,
    updateField,
    importRows,

    isVerificationDisabled,

    metrics,
    getRowQualityStatus,

    buildPayload,
  }
}
