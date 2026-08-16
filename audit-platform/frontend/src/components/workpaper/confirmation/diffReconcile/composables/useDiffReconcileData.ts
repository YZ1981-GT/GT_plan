/**
 * useDiffReconcileData — D0-4 函证差异调节表数据核心 composable
 *
 * 职责：
 * - 从 htmlData 初始化行数据（_format: diff-reconcile-v1）
 * - CRUD 操作（addRow / deleteRows / updateField / importRows）
 * - 差异自动计算（sent_amount - reply_amount，精确小数，只读不可手填）
 * - 合计 + 按科目分组小计（subjectSummary）
 * - 看板指标（metrics）
 * - 重要性检查（materialityCheck）
 * - buildPayload 构建持久化数据
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type {
  DiffReconcileRow,
  DiffSummaryBySubject,
  DiffReconcileMetrics,
  DiffAnalysisGroup,
  MaterialityConfig,
  DiffAuditNote,
  DiffConclusion,
  DiffReconcilePayload,
} from '../diffReconcileTypes'
import { fetchMaterialityConfig, hasUsablePm } from './fetchMaterialityConfig'

// ─── ID 生成工具 ─────────────────────────────────────────────────────────────

function generateRowId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

// ─── Props 接口 ──────────────────────────────────────────────────────────────

export interface UseDiffReconcileDataProps {
  /** 响应式数据源（来自底稿的 htmlData） */
  htmlData: () => any
  /** 是否只读 */
  readonly: boolean
  /**
   * 项目 ID —— 用于从 B15 自动取实际执行重要性（PM）。
   *
   * 🔴 **可选**：不传时行为与引入前逐字一致（PM 只从底稿载荷读），
   * 这是零回归支点。传了才启用自动取数。
   */
  projectId?: string
  /** 审计年度 —— 与 projectId 配套，缺省时后端取当前年度 */
  year?: string | number
}

// ─── 返回接口 ────────────────────────────────────────────────────────────────

export interface UseDiffReconcileDataReturn {
  rows: Ref<DiffReconcileRow[]>
  auditNote: Ref<DiffAuditNote>
  conclusion: Ref<DiffConclusion>
  materialityConfig: Ref<MaterialityConfig>
  analysisNotes: Ref<Record<string, { note?: string; action?: string }>>
  isDirty: Ref<boolean>

  // CRUD
  addRow: () => DiffReconcileRow
  deleteRows: (ids: string[]) => void
  updateField: (rowId: string, field: string, value: any) => void
  importRows: (newRows: DiffReconcileRow[]) => void

  // 自动计算
  computeDifference: (row: DiffReconcileRow) => number

  // 合计 + 分组
  totals: ComputedRef<{ sent: number; reply: number; difference: number; abs_difference: number }>
  subjectSummary: ComputedRef<DiffSummaryBySubject[]>

  // 看板
  metrics: ComputedRef<DiffReconcileMetrics>

  // 重要性
  isOverMateriality: (row: DiffReconcileRow) => boolean

  // 持久化
  buildPayload: () => DiffReconcilePayload
}

// ─── Composable 主体 ─────────────────────────────────────────────────────────

export function useDiffReconcileData(props: UseDiffReconcileDataProps): UseDiffReconcileDataReturn {
  const rows = ref<DiffReconcileRow[]>([])
  const auditNote = ref<DiffAuditNote>({})
  const conclusion = ref<DiffConclusion>({})
  const materialityConfig = ref<MaterialityConfig>({})
  const analysisNotes = ref<Record<string, { note?: string; action?: string }>>({})
  const isDirty = ref(false)

  let _initializing = false

  // ─── PM 自动取数状态（声明必须早于 initFromHtmlData 首次调用） ──────────────
  //
  // 🔴 TDZ：`initFromHtmlData()` 在下方立即被调用，它内部会读 `_autoConfig`。
  // `let` 不像 `function` 那样提升，若把这两个声明留在文件后半段，
  // 首次调用就会抛 `ReferenceError: Cannot access '_autoConfig' before initialization`
  // —— 而 `get_diagnostics` / vitest 都查不出，只有浏览器挂载才暴露
  // （与 E1TabDisclosure 那次 setup 期 TDZ 同族）。
  let _autoFetched = false

  /**
   * B15 取到的配置缓存（`{performance_materiality, is_overridden:false, source:'auto'}`）。
   *
   * 必须缓存 —— `initFromHtmlData` 由 `watch(htmlData, {deep:true})` 反复触发，
   * 每次都把 `materialityConfig` 重置为载荷值。只在取数那一刻赋值的话，
   * 底稿保存/上游刷新后 auto 值会被静默冲掉（表现为「阈值时有时无」）。
   */
  let _autoConfig: MaterialityConfig | null = null

  // ─── 从 htmlData 初始化 ────────────────────────────────────────────────────

  function initFromHtmlData(data: any) {
    _initializing = true
    try {
      if (!data || data._format !== 'diff-reconcile-v1') {
        rows.value = []
        auditNote.value = {}
        conclusion.value = {}
        materialityConfig.value = {}
        analysisNotes.value = {}
        // 非本格式载荷也要保留 B15 阈值 —— 它是项目级事实，与底稿格式无关
        applyAutoMateriality()
        return
      }
      rows.value = Array.isArray(data.rows) ? data.rows.map(ensureRowId) : []
      auditNote.value = data.audit_note ?? {}
      conclusion.value = data.conclusion ?? {}
      materialityConfig.value = data.materiality_config ?? {}
      analysisNotes.value = data.analysis_notes ?? {}
      isDirty.value = false
      // 🔴 载荷无 PM 时回落 B15 auto 值（本函数由 deep watch 反复触发，
      // 不在这里重新套用会让 auto 值被静默冲掉）
      applyAutoMateriality()
    } finally {
      _initializing = false
    }
  }

  function ensureRowId(row: DiffReconcileRow): DiffReconcileRow {
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
    { deep: true }
  )

  // ─── PM 自动取数（B15 重要性水平底稿） ─────────────────────────────────────
  //
  // 🔴 UI 文案早已写明「默认从 B15 重要性水平底稿自动获取」，而改造前
  // `materialityConfig` **只从底稿自身载荷读**、从不调 `/materiality` 端点
  // → 新建底稿的 PM 恒为空 → `isOverMateriality` 恒 false →
  // 「推送 N 笔超重要性差异至 A13」按钮永久禁用、行标红永不触发，
  // 且 `MaterialityConfig.source === 'auto'` 这个 tag 分支不可达（死分支）。
  //
  // 手工优先：仅当底稿无 PM 且用户未手动覆盖时才套用自动值。
  // （`_autoFetched` / `_autoConfig` 因 TDZ 已前移到 composable 顶部声明）

  /** 把 auto 配置套进 state —— 手工优先，已有有效 PM 时空操作 */
  function applyAutoMateriality(): void {
    if (_autoConfig == null) return
    const cur = materialityConfig.value
    // 手工覆盖优先；载荷已有有效 PM 也不动（判据与 isOverMateriality 同口径）
    if (cur.is_overridden || hasUsablePm(cur)) return
    materialityConfig.value = { ...cur, ..._autoConfig }
  }

  async function loadAutoMateriality(): Promise<void> {
    if (_autoFetched || !props.projectId) return
    _autoFetched = true

    _autoConfig = await fetchMaterialityConfig(props.projectId, props.year)
    // 二次判定在 await 之后 —— 期间用户可能已手填，手工永远优先
    applyAutoMateriality()
  }

  void loadAutoMateriality()

  // ─── 差异自动计算（精确小数） ──────────────────────────────────────────────

  function computeDifference(row: DiffReconcileRow): number {
    const sent = row.sent_amount ?? 0
    const reply = row.reply_amount ?? 0
    // 精确小数：乘 100 整数运算后除回（避免浮点漂移）
    return Math.round((sent - reply) * 100) / 100
  }

  // ─── CRUD ──────────────────────────────────────────────────────────────────

  function addRow(): DiffReconcileRow {
    const maxSeq = rows.value.reduce((max, r) => Math.max(max, r.seq ?? 0), 0)
    const newRow: DiffReconcileRow = {
      _row_id: generateRowId(),
      seq: maxSeq + 1,
      difference: 0,
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
    // 金额字段变更时重算差异
    if (field === 'sent_amount' || field === 'reply_amount') {
      row.difference = computeDifference(row)
    }
    isDirty.value = true
  }

  function importRows(newRows: DiffReconcileRow[]) {
    // 按 confirm_index 去重：已有相同索引号的不重复导入
    const existingIndexes = new Set(
      rows.value.map((r) => r.confirm_index).filter(Boolean)
    )
    const deduped = newRows.filter(
      (r) => !r.confirm_index || !existingIndexes.has(r.confirm_index)
    )
    const maxSeq = rows.value.reduce((max, r) => Math.max(max, r.seq ?? 0), 0)
    deduped.forEach((r, i) => {
      r._row_id = generateRowId()
      r.seq = maxSeq + i + 1
      r.difference = computeDifference(r)
      r._source = r._source || 'auto'
    })
    rows.value.push(...deduped)
    isDirty.value = true
  }

  // ─── 合计 ──────────────────────────────────────────────────────────────────

  const totals = computed(() => {
    let sent = 0
    let reply = 0
    let difference = 0
    let abs_difference = 0
    for (const row of rows.value) {
      sent += row.sent_amount ?? 0
      reply += row.reply_amount ?? 0
      const diff = computeDifference(row)
      difference += diff
      abs_difference += Math.abs(diff)
    }
    return {
      sent: Math.round(sent * 100) / 100,
      reply: Math.round(reply * 100) / 100,
      difference: Math.round(difference * 100) / 100,
      abs_difference: Math.round(abs_difference * 100) / 100,
    }
  })

  // ─── 按科目分组小计 ───────────────────────────────────────────────────────

  const subjectSummary = computed<DiffSummaryBySubject[]>(() => {
    const map = new Map<string, DiffSummaryBySubject>()
    for (const row of rows.value) {
      const subj = row.subject || '未分类'
      let group = map.get(subj)
      if (!group) {
        group = {
          subject: subj,
          count: 0,
          sent_total: 0,
          reply_total: 0,
          difference_total: 0,
          difference_abs_total: 0,
          analyzed_count: 0,
          adjustment_count: 0,
        }
        map.set(subj, group)
      }
      group.count++
      group.sent_total += row.sent_amount ?? 0
      group.reply_total += row.reply_amount ?? 0
      const diff = computeDifference(row)
      group.difference_total += diff
      group.difference_abs_total += Math.abs(diff)
      if (row.diff_type) group.analyzed_count++
      if (row.needs_adjustment) group.adjustment_count++
    }
    return [...map.values()].map((g) => ({
      ...g,
      sent_total: Math.round(g.sent_total * 100) / 100,
      reply_total: Math.round(g.reply_total * 100) / 100,
      difference_total: Math.round(g.difference_total * 100) / 100,
      difference_abs_total: Math.round(g.difference_abs_total * 100) / 100,
    }))
  })

  // ─── 重要性检查 ───────────────────────────────────────────────────────────

  function isOverMateriality(row: DiffReconcileRow): boolean {
    const pm = materialityConfig.value.performance_materiality
    if (pm == null || pm <= 0) return false // 无配置不误报
    const diff = Math.abs(computeDifference(row))
    return diff >= pm
  }

  // ─── 看板指标 ──────────────────────────────────────────────────────────────

  const metrics = computed<DiffReconcileMetrics>(() => {
    const total = rows.value.length
    const analyzed = rows.value.filter((r) => !!r.diff_type).length
    const adjRows = rows.value.filter((r) => r.needs_adjustment)
    const adjAmount = adjRows.reduce((s, r) => s + Math.abs(computeDifference(r)), 0)
    const overMat = rows.value.filter((r) => isOverMateriality(r)).length

    // 类型分布
    const typeMap = new Map<string, { count: number; net: number; abs: number }>()
    for (const row of rows.value) {
      const t = row.diff_type || '未分类'
      let g = typeMap.get(t)
      if (!g) { g = { count: 0, net: 0, abs: 0 }; typeMap.set(t, g) }
      g.count++
      const diff = computeDifference(row)
      g.net += diff
      g.abs += Math.abs(diff)
    }
    const totalAbs = totals.value.abs_difference || 1
    const distribution: DiffAnalysisGroup[] = [...typeMap.entries()].map(([dt, g]) => ({
      diff_type: dt,
      count: g.count,
      net_amount: Math.round(g.net * 100) / 100,
      abs_amount: Math.round(g.abs * 100) / 100,
      percentage: Math.round((g.abs / totalAbs) * 10000) / 100,
      note: analysisNotes.value[dt]?.note,
      action: analysisNotes.value[dt]?.action,
    }))

    return {
      total_count: total,
      difference_net_total: totals.value.difference,
      difference_abs_total: totals.value.abs_difference,
      analyzed_rate: total > 0 ? Math.round((analyzed / total) * 10000) / 100 : 0,
      adjustment_count: adjRows.length,
      adjustment_amount: Math.round(adjAmount * 100) / 100,
      over_materiality_count: overMat,
      type_distribution: distribution,
    }
  })

  // ─── buildPayload ──────────────────────────────────────────────────────────

  function buildPayload(): DiffReconcilePayload {
    return {
      _format: 'diff-reconcile-v1',
      rows: rows.value.map((row) => ({
        ...row,
        difference: computeDifference(row),
      })),
      analysis_notes: analysisNotes.value,
      audit_note: auditNote.value,
      conclusion: conclusion.value,
      materiality_config: materialityConfig.value,
    }
  }

  return {
    rows,
    auditNote,
    conclusion,
    materialityConfig,
    analysisNotes,
    isDirty,

    addRow,
    deleteRows,
    updateField,
    importRows,

    computeDifference,

    totals,
    subjectSummary,

    metrics,
    isOverMateriality,

    buildPayload,
  }
}
