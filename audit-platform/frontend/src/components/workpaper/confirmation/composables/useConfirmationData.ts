/**
 * useConfirmationData — 函证汇总表数据核心 composable
 *
 * 职责：
 * - 从 htmlData 初始化行数据 / 抽样 / 说明 / 结论
 * - CRUD 操作（addRow / deleteRows / updateField）
 * - 科目 Tab 切换与行过滤
 * - 看板指标（按科目大类聚合）
 * - 可确认金额业务规则自动计算
 * - 覆盖率 / 回函率质量指标
 * - buildPayload 构建持久化数据
 *
 * Validates: Tasks 2.1 ~ 2.8
 */
import { ref, computed, watch, shallowRef, type Ref, type ComputedRef } from 'vue'
import type {
  ConfirmationRow,
  DashboardMetrics,
  SamplingData,
  NotesData,
  ConclusionData,
  ConfirmationPayload,
  ConfirmationCoverageMetrics,
} from '../confirmationTypes'
import { isConfirmationInFlight } from '../coordination/emitConfirmationCompleted'

// ─── ID 生成工具（不依赖 uuid 库） ──────────────────────────────────────────

function generateRowId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

// ─── Props 接口 ──────────────────────────────────────────────────────────────

export interface UseConfirmationDataProps {
  /** 响应式数据源（来自底稿的 htmlData） */
  htmlData: () => any
  /** 是否只读 */
  readonly: boolean
  /**
   * 科目审定总额(TB population)，作为函证/确认覆盖率分母。
   * 由后端 render 注入 htmlData.project_context.population_amount，前端只读。
   * 返回 null 或 ≤0 表示不可用 → 覆盖率显示为「不可用」(Skip-on-missing)。
   */
  population?: () => number | null
}

// ─── 返回接口 ────────────────────────────────────────────────────────────────

export interface UseConfirmationDataReturn {
  rows: Ref<ConfirmationRow[]>
  sampling: Ref<SamplingData>
  notes: Ref<NotesData>
  conclusion: Ref<ConclusionData>
  isDirty: Ref<boolean>

  // CRUD
  addRow: () => ConfirmationRow
  deleteRows: (ids: string[]) => void
  updateField: (rowId: string, field: string, value: any) => void

  // Tab 切换
  accountTabs: ComputedRef<string[]>
  activeTab: Ref<string>
  filteredRows: ComputedRef<ConfirmationRow[]>

  // 看板
  dashboardMetrics: ComputedRef<DashboardMetrics[]>

  // 业务规则
  computeConfirmedAmount: (row: ConfirmationRow) => number

  // 覆盖率
  coverageMetrics: ComputedRef<ConfirmationCoverageMetrics>

  // 持久化
  buildPayload: () => ConfirmationPayload
}

// ─── Composable 主体 ─────────────────────────────────────────────────────────

export function useConfirmationData(props: UseConfirmationDataProps): UseConfirmationDataReturn {
  const rows = ref<ConfirmationRow[]>([])
  const sampling = ref<SamplingData>({})
  const notes = ref<NotesData>({})
  const conclusion = ref<ConclusionData>({})
  const isDirty = ref(false)

  // 内部标记：初始化过程中不触发 dirty
  let _initializing = false

  // ─── Task 2.1: 从 htmlData 初始化 ─────────────────────────────────────────

  function initFromHtmlData(data: any) {
    _initializing = true
    try {
      if (!data || data._format !== 'confirmation-v1') {
        rows.value = []
        sampling.value = {}
        notes.value = {}
        conclusion.value = {}
        return
      }
      rows.value = Array.isArray(data.rows) ? data.rows.map(ensureRowId) : []
      sampling.value = data.sampling ?? {}
      notes.value = data.notes ?? {}
      conclusion.value = data.conclusion ?? {}
      isDirty.value = false
    } finally {
      _initializing = false
    }
  }

  /** 确保每行都有 _row_id */
  function ensureRowId(row: ConfirmationRow): ConfirmationRow {
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

  // ─── Task 2.2: CRUD 操作 ───────────────────────────────────────────────────

  function addRow(): ConfirmationRow {
    // 自动递增序号
    const maxSeq = rows.value.reduce((max, r) => Math.max(max, r.seq ?? 0), 0)
    const newRow: ConfirmationRow = {
      _row_id: generateRowId(),
      seq: maxSeq + 1,
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
    // 更新字段后重算可确认金额（除非用户手动覆盖）
    if (field !== 'confirmed_amount' && field !== '_overridden') {
      if (!row._overridden) {
        row.confirmed_amount = computeConfirmedAmount(row)
        row.difference = computeDifference(row)
      }
    }
    isDirty.value = true
  }

  // ─── Task 2.3: 科目 Tab ───────────────────────────────────────────────────

  const accountTabs = computed<string[]>(() => {
    const types = new Set<string>()
    for (const row of rows.value) {
      if (row.account_type) {
        types.add(row.account_type)
      }
    }
    return [...types].sort()
  })

  /** 当前激活 Tab，空字符串表示"全部" */
  const activeTab = ref<string>('')

  const filteredRows = computed<ConfirmationRow[]>(() => {
    if (!activeTab.value) return rows.value
    return rows.value.filter((r) => r.account_type === activeTab.value)
  })

  // ─── Task 2.5: 可确认金额业务规则 ─────────────────────────────────────────

  /**
   * 计算可确认金额（confirmed_amount）
   *
   * 业务规则：
   * - 相符（matched）→ amount
   * - 不符（unmatched）→ reply_amount
   * - 未回函 + 消极式（no_reply + negative）→ amount（默认确认）
   * - 未回函 + 积极式（no_reply + positive）→ alt_confirmed ?? 0
   * - 用户覆盖（_overridden: true）→ 保持用户值
   */
  function computeConfirmedAmount(row: ConfirmationRow): number {
    // 用户已手动覆盖，保持原值
    if (row._overridden) {
      return row.confirmed_amount ?? 0
    }

    const matchStatus = row.match_status ?? ''
    const method = row.confirmation_method ?? ''
    const amount = row.amount ?? 0
    const replyAmount = row.reply_amount ?? 0
    const altConfirmed = row.alt_confirmed ?? 0

    // 相符 → 账面金额
    if (matchStatus === '相符') {
      return amount
    }

    // 不符 → 回函金额
    if (matchStatus === '不符') {
      return replyAmount
    }

    // 未回函
    if (matchStatus === '未回函') {
      // 消极式未回函 → 默认确认（视同相符）
      if (method === '消极式') {
        return amount
      }
      // 积极式未回函 → 替代程序确认金额
      return altConfirmed
    }

    // 其他情况默认 0
    return 0
  }

  /**
   * 计算差异金额
   * - 相符 → 强制 0
   * - 其他 → amount - reply_amount
   */
  function computeDifference(row: ConfirmationRow): number {
    if (row.match_status === '相符') return 0
    return (row.amount ?? 0) - (row.reply_amount ?? 0)
  }

  // ─── Task 2.4: 看板指标 ───────────────────────────────────────────────────

  const dashboardMetrics = computed<DashboardMetrics[]>(() => {
    const groupMap = new Map<string, DashboardMetrics>()

    for (const row of rows.value) {
      const type = row.account_type || '未分类'
      let group = groupMap.get(type)
      if (!group) {
        group = {
          account_type: type,
          total_count: 0,
          replied_count: 0,
          matched_count: 0,
          total_amount: 0,
          confirmed_amount: 0,
          unconfirmed_amount: 0,
          difference_amount: 0,
        }
        groupMap.set(type, group)
      }

      group.total_count++
      if (row.is_replied) group.replied_count++
      if (row.match_status === '相符') group.matched_count++
      group.total_amount += row.amount ?? 0

      // 可确认金额（实时计算，不依赖存储值）
      const confirmed = row._overridden
        ? (row.confirmed_amount ?? 0)
        : computeConfirmedAmount(row)
      group.confirmed_amount += confirmed
      group.unconfirmed_amount += (row.amount ?? 0) - confirmed
      group.difference_amount += computeDifference(row)
    }

    return [...groupMap.values()]
  })

  // ─── Task 2.8: 覆盖率质量指标 ─────────────────────────────────────────────

  const coverageMetrics = computed<ConfirmationCoverageMetrics>(() => {
    // 已发函笔数：复用在途语义（send_date/is_replied/match_status/confirmation_method 任一）
    const sentRows = rows.value.filter(isConfirmationInFlight)
    const sentCount = sentRows.length
    const repliedCount = rows.value.filter((r) => r.is_replied).length
    // 发函总额 = 已发函行账面金额之和
    const sentAmount = sentRows.reduce((sum, r) => sum + (r.amount ?? 0), 0)
    // 已确认金额（回函确认 + 替代确认）
    const confirmedTotal = rows.value.reduce((sum, r) => {
      const confirmed = r._overridden
        ? (r.confirmed_amount ?? 0)
        : computeConfirmedAmount(r)
      return sum + confirmed
    }, 0)

    // 科目审定总额（population）：作为函证/确认覆盖率分母；缺失或 ≤0 → 覆盖率不可用（Skip-on-missing）
    const population = props.population?.() ?? null
    const popValid = population != null && population > 0

    // 函证覆盖率 = 发函总额 / 科目审定总额；确认覆盖率 = 已确认 / 科目审定总额
    const confirmationCoverage = popValid ? (sentAmount / (population as number)) * 100 : null
    const confirmedCoverage = popValid ? (confirmedTotal / (population as number)) * 100 : null
    // 回函覆盖率 = 已回函笔数 / 已发函笔数（笔数口径，与公式面板一致；防除零）
    const replyCoverage = sentCount > 0 ? (repliedCount / sentCount) * 100 : 0

    // 预警等级：回函不足优先 danger；回函达标但函证覆盖率(population 可用时)不足 → warn；
    // population 缺失时函证覆盖率不参与预警，仅由回函率决定。
    let warnLevel: 'ok' | 'warn' | 'danger' = 'ok'
    if (replyCoverage < 80) {
      warnLevel = 'danger'
    } else if (confirmationCoverage != null && confirmationCoverage < 50) {
      warnLevel = 'warn'
    }

    return {
      confirmation_coverage: confirmationCoverage,
      confirmed_coverage: confirmedCoverage,
      reply_coverage: replyCoverage,
      warn_level: warnLevel,
      population_available: popValid,
    }
  })

  // ─── Task 2.6: buildPayload ────────────────────────────────────────────────

  function buildPayload(): ConfirmationPayload {
    return {
      _format: 'confirmation-v1',
      rows: rows.value.map((row) => ({
        ...row,
        // 确保 confirmed_amount 和 difference 实时计算值同步到 payload
        confirmed_amount: row._overridden
          ? (row.confirmed_amount ?? 0)
          : computeConfirmedAmount(row),
        difference: computeDifference(row),
      })),
      summary_config: {
        account_types: accountTabs.value,
      },
      sampling: sampling.value,
      notes: notes.value,
      conclusion: conclusion.value,
    }
  }

  return {
    rows,
    sampling,
    notes,
    conclusion,
    isDirty,

    addRow,
    deleteRows,
    updateField,

    accountTabs,
    activeTab,
    filteredRows,

    dashboardMetrics,
    computeConfirmedAmount,

    coverageMetrics,

    buildPayload,
  }
}
