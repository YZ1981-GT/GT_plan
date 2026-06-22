/**
 * useFollowupData — D0-3 跟函数据核心 composable
 *
 * 职责：
 * - 从 htmlData 初始化行数据（confirmation-followup-v1 格式）
 * - CRUD 操作（addRow / deleteRows / updateField / importRows）
 * - 进度指标（signed / control_pass / control_fail / anomaly 统计）
 * - 控制结论自动派生（3项控制检查 → pass/fail/incomplete）
 * - buildPayload 构建持久化数据
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type { FollowupRow, FollowupProgressMetrics, FollowupPayload } from '../followupTypes'

// ─── ID 生成工具 ─────────────────────────────────────────────────────────────

function generateRowId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

// ─── Props 接口 ──────────────────────────────────────────────────────────────

export interface UseFollowupDataProps {
  /** 响应式数据源（来自底稿的 htmlData） */
  htmlData: () => any
  /** 是否只读 */
  readonly: boolean
}

// ─── 返回接口 ────────────────────────────────────────────────────────────────

export interface UseFollowupDataReturn {
  rows: Ref<FollowupRow[]>
  isDirty: Ref<boolean>

  // CRUD
  addRow: () => FollowupRow
  deleteRows: (ids: string[]) => void
  updateField: (rowId: string, field: string, value: any) => void
  importRows: (newRows: Partial<FollowupRow>[]) => void

  // 进度指标
  progressMetrics: ComputedRef<FollowupProgressMetrics>

  // 控制结论派生
  deriveControlConclusion: (row: FollowupRow) => 'pass' | 'fail' | 'incomplete'

  // 持久化
  buildPayload: () => FollowupPayload
}

// ─── 控制结论派生逻辑 ─────────────────────────────────────────────────────────

/**
 * 三项控制检查全部为 'yes' → pass
 * 任一为 'no' → fail
 * 其余 → incomplete
 */
export function deriveControlConclusion(row: FollowupRow): 'pass' | 'fail' | 'incomplete' {
  const controls = [row.control_process, row.control_identity, row.control_normal_flow]

  if (controls.some((c) => c === 'no')) return 'fail'
  if (controls.every((c) => c === 'yes')) return 'pass'
  return 'incomplete'
}

// ─── Composable 主体 ─────────────────────────────────────────────────────────

export function useFollowupData(props: UseFollowupDataProps): UseFollowupDataReturn {
  const rows = ref<FollowupRow[]>([])
  const isDirty = ref(false)

  // ─── 初始化 ─────────────────────────────────────────────────────────────────

  function initFromHtmlData(data: any) {
    if (!data || data._format !== 'confirmation-followup-v1') {
      rows.value = []
      return
    }
    rows.value = Array.isArray(data.rows) ? data.rows.map(ensureRowId) : []
    isDirty.value = false
  }

  function ensureRowId(row: FollowupRow): FollowupRow {
    if (!row._row_id) {
      return { ...row, _row_id: generateRowId() }
    }
    return row
  }

  // 初始加载
  initFromHtmlData(props.htmlData())

  // 监听 htmlData 变化并重新初始化
  watch(
    () => props.htmlData(),
    (newData) => {
      initFromHtmlData(newData)
    },
    { deep: true }
  )

  // ─── CRUD 操作 ──────────────────────────────────────────────────────────────

  function addRow(): FollowupRow {
    const maxSeq = rows.value.reduce((max, r) => Math.max(max, r.seq ?? 0), 0)
    const newRow: FollowupRow = {
      _row_id: generateRowId(),
      seq: maxSeq + 1,
      scenario: 'immediate',
      sign_status: 'unsigned',
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

    // 自动派生 control_conclusion
    if (field === 'control_process' || field === 'control_identity' || field === 'control_normal_flow') {
      row.control_conclusion = deriveControlConclusion(row)
    }

    isDirty.value = true
  }

  function importRows(newRows: Partial<FollowupRow>[]) {
    const maxSeq = rows.value.reduce((max, r) => Math.max(max, r.seq ?? 0), 0)
    newRows.forEach((data, idx) => {
      const row: FollowupRow = {
        ...data,
        _row_id: generateRowId(),
        seq: maxSeq + idx + 1,
        _source: data._source ?? 'import',
      }
      // 自动派生 control_conclusion
      row.control_conclusion = deriveControlConclusion(row)
      rows.value.push(row)
    })
    isDirty.value = true
  }

  // ─── 进度指标 ───────────────────────────────────────────────────────────────

  const progressMetrics = computed<FollowupProgressMetrics>(() => {
    const total = rows.value.length
    const signed = rows.value.filter((r) => r.sign_status === 'signed').length
    const controlPass = rows.value.filter((r) => r.control_conclusion === 'pass').length
    const controlFail = rows.value.filter((r) => r.control_conclusion === 'fail').length
    // 异常: control 有 'no' 的行
    const anomaly = rows.value.filter((r) =>
      r.control_process === 'no' ||
      r.control_identity === 'no' ||
      r.control_normal_flow === 'no'
    ).length

    return {
      total_count: total,
      signed_count: signed,
      control_pass_count: controlPass,
      control_fail_count: controlFail,
      anomaly_count: anomaly,
      sign_rate: total > 0 ? (signed / total) * 100 : 0,
      control_pass_rate: total > 0 ? (controlPass / total) * 100 : 0,
    }
  })

  // ─── 持久化 ─────────────────────────────────────────────────────────────────

  function buildPayload(): FollowupPayload {
    return {
      _format: 'confirmation-followup-v1',
      rows: rows.value,
      progress_summary: progressMetrics.value,
    }
  }

  return {
    rows,
    isDirty,
    addRow,
    deleteRows,
    updateField,
    importRows,
    progressMetrics,
    deriveControlConclusion,
    buildPayload,
  }
}
