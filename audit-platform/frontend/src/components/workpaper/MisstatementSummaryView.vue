<!--
  MisstatementSummaryView — A13 错报汇总 HTML 视图 (增强版)

  功能：
  1. Materiality_Indicator 三色预警 (green/yellow/red) + fraud badge
  2. SSE 监听 a13_summary_updated 事件自动刷新
  3. Prior_Year_Status 分类展示 (上年延续/转回/本年新增/净累计)
  4. 阈值跨越通知 (累计从 < PM 到 ≥ PM 时 el-notification)

  Requirements: 1.7, 2.5, 3.1~3.7, 4.4
-->
<template>
  <div class="misstatement-summary">
    <!-- Materiality_Indicator: 三色预警区 (Task 10.1) -->
    <MaterialityIndicator
      v-if="summaryLoaded"
      :materiality="summaryResult?.materiality"
      :cumulative-total="summaryResult?.cumulative_total ?? 0"
      :fraud-count="summaryResult?.fraud_count ?? 0"
      :project-id="resolvedProjectId"
    />

    <!-- Prior_Year_Status 分类展示 (Task 10.3) -->
    <div v-if="summaryResult && hasPriorYearData" class="misstatement-summary__prior-year">
      <el-descriptions :column="4" border size="small" title="错报分类汇总">
        <el-descriptions-item label="上年延续金额">
          {{ formatAmount(summaryResult.prior_year?.continuing_amount) }} 元
        </el-descriptions-item>
        <el-descriptions-item label="上年转回金额">
          {{ formatAmount(summaryResult.prior_year?.reversed_amount) }} 元
        </el-descriptions-item>
        <el-descriptions-item label="本年新增金额">
          {{ formatAmount(summaryResult.current_year?.new_amount) }} 元
        </el-descriptions-item>
        <el-descriptions-item label="净累计">
          <span class="misstatement-summary__cumulative">
            {{ formatAmount(summaryResult.cumulative_total) }} 元
          </span>
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- 评价区：汇总 vs 重要性 (保留原始逻辑) -->
    <div v-if="evaluation" class="misstatement-summary__eval">
      <el-alert
        :type="evaluation.exceeds_materiality ? 'error' : 'success'"
        :closable="false"
      >
        <template #title>
          错报评价：合计 {{ formatAmount(evaluation.total_amount) }} 元
          {{ evaluation.exceeds_materiality ? '超过' : '未超过' }}
          重要性水平 {{ formatAmount(evaluation.materiality) }} 元
        </template>
        <p>{{ evaluation.suggested_conclusion }}</p>
      </el-alert>
    </div>

    <!-- 无错报时的空状态 -->
    <div v-if="loaded && allRows.length === 0" class="misstatement-summary__empty">
      <el-empty description="本项目暂无未更正错报">
        <template #description>
          <p>当调整分录标记为"管理层不予更正"后，错报将自动汇总到此表。</p>
        </template>
      </el-empty>
    </div>

    <!-- A13-1: 未更正错报汇总表 -->
    <WorkpaperHtmlTable
      v-if="allRows.length > 0"
      title="A13-1 未更正错报汇总表"
      :header="header"
      :columns="columns"
      :rows="allRows"
      scope="misstatement:summary"
      :project-id="resolvedProjectId"
      :year="resolvedYear"
      @field-change="onFieldChange"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElNotification } from 'element-plus'
import { useProjectStore } from '@/stores/project'
import { api } from '@/services/apiProxy'
import { eventBus, type SyncEventPayload } from '@/utils/eventBus'
import WorkpaperHtmlTable, { type ColumnDef, type RowData, type StandardHeader } from './WorkpaperHtmlTable.vue'
import MaterialityIndicator from './MaterialityIndicator.vue'

const props = defineProps<{
  /** 底稿 ID（GtMisstatementWorkpaper / GtWpRenderer 传入） */
  wpId?: string
  /** 可选直传（用于独立渲染场景） */
  projectId?: string
  year?: number
  header?: StandardHeader | null
}>()

const route = useRoute()
const projectStore = useProjectStore()

/** 从路由或 prop 取 projectId */
const resolvedProjectId = computed(
  () => props.projectId || (route.params.projectId as string) || '',
)
/** 从路由或 prop 取 year */
const resolvedYear = computed(
  () => props.year || parseInt(route.query.year as string) || projectStore.year || new Date().getFullYear() - 1,
)

// ─── Types ─────────────────────────────────────────────────────────────────

interface SummaryItem {
  id: string
  adjustment_no: string
  description: string
  account_code: string
  account_name: string
  debit_amount: number | null
  credit_amount: number | null
  passed_reason: string
}

interface Evaluation {
  total_amount: number
  materiality: number
  exceeds_materiality: boolean
  suggested_conclusion: string
}

/** a13-summary-v1 结构 */
interface A13Summary {
  _format?: string
  total_count: number
  total_amount: number
  by_type?: Record<string, { count: number; amount: number }>
  fraud_count: number
  prior_year?: {
    continuing_count?: number
    continuing_amount: number
    reversed_count?: number
    reversed_amount: number
  }
  current_year?: {
    new_count?: number
    new_amount: number
  }
  cumulative_total: number
  materiality?: {
    pm: number | null
    te?: number | null
    sat?: number | null
    ratio: number | null
    status: string
    fraud_flag?: boolean
  }
}

// ─── State ─────────────────────────────────────────────────────────────────

const summaryData = ref<{ prior: SummaryItem[]; current: SummaryItem[] }>({ prior: [], current: [] })
const evaluation = ref<Evaluation | null>(null)
const summaryResult = ref<A13Summary | null>(null)
const summaryLoaded = ref(false)
const loaded = ref(false)
/** 用于阈值跨越检测的上一次累计值 */
let previousCumulative: number | null = null

// ─── Columns ───────────────────────────────────────────────────────────────

const columns: ColumnDef[] = [
  { key: 'seq', label: '序号', type: 'text', width: 50 },
  { key: 'section', label: '区间', type: 'text', width: 80 },
  { key: 'adjustment_no', label: '编号', type: 'text', width: 80 },
  { key: 'description', label: '内容说明', type: 'text', minWidth: 200 },
  { key: 'account_name', label: '科目', type: 'text', width: 120 },
  { key: 'debit_amount', label: '借方金额', type: 'computed', width: 110, align: 'right' },
  { key: 'credit_amount', label: '贷方金额', type: 'computed', width: 110, align: 'right' },
  { key: 'passed_reason', label: '管理层不予更正原因', type: 'editable', minWidth: 180 },
]

const allRows = computed<RowData[]>(() => {
  const rows: RowData[] = []
  let seq = 1
  for (const item of summaryData.value.current) {
    rows.push({ _key: item.id, seq, section: '本期', ...item })
    seq++
  }
  for (const item of summaryData.value.prior) {
    rows.push({ _key: item.id, seq, section: '以前期间', ...item })
    seq++
  }
  return rows
})

/** 是否有上年分类数据 */
const hasPriorYearData = computed(() => {
  if (!summaryResult.value) return false
  const { prior_year, current_year } = summaryResult.value
  return !!(prior_year || current_year)
})

// ─── Helpers ───────────────────────────────────────────────────────────────

function formatAmount(val: number | null | undefined): string {
  if (val == null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2 })
}

// ─── 阈值跨越检测 (Task 10.4) ────────────────────────────────────────────

/**
 * 检测累计未更正错报是否从 < PM 跨越到 ≥ PM
 * 仅在 old < PM 且 new ≥ PM 时触发通知
 */
function checkThresholdCrossing(newCumulative: number, pm: number | null | undefined) {
  if (!pm || pm <= 0) return
  if (previousCumulative === null) {
    // 首次加载不触发通知
    previousCumulative = newCumulative
    return
  }
  if (previousCumulative < pm && newCumulative >= pm) {
    ElNotification({
      title: '重要性阈值警告',
      message: `累计未更正错报(${formatAmount(newCumulative)}元)已达到或超过重要性水平(${formatAmount(pm)}元)，请关注审计意见影响。`,
      type: 'warning',
      duration: 8000,
    })
  }
  previousCumulative = newCumulative
}

// ─── 数据加载 ──────────────────────────────────────────────────────────────

async function loadData() {
  if (!resolvedProjectId.value) return
  try {
    const [summary, eval_] = await Promise.all([
      api.get<typeof summaryData.value>(
        `/api/workpapers/${resolvedProjectId.value}/${resolvedYear.value}/misstatement-summary`,
      ),
      api.get<Evaluation>(
        `/api/workpapers/${resolvedProjectId.value}/${resolvedYear.value}/misstatement-evaluation`,
      ),
    ])
    summaryData.value = summary
    evaluation.value = eval_
  } catch {
    // 降级：无数据时保持空态
  } finally {
    loaded.value = true
  }
}

/** 加载 a13-summary-v1 聚合结果 */
async function loadSummaryResult() {
  if (!resolvedProjectId.value) return
  try {
    const result = await api.get<A13Summary>(
      `/api/workpapers/${resolvedProjectId.value}/${resolvedYear.value}/misstatement-evaluation`,
    )
    // 检测阈值跨越
    if (result && result.cumulative_total !== undefined) {
      checkThresholdCrossing(result.cumulative_total, result.materiality?.pm)
    }
    summaryResult.value = result
  } catch {
    // 降级：使用 evaluation 数据
  } finally {
    summaryLoaded.value = true
  }
}

function onFieldChange(payload: { itemKey: string; field: string; value: any }) {
  if (payload.field === 'passed_reason') {
    void api.post(
      `/api/workpapers/${resolvedProjectId.value}/${resolvedYear.value}/misstatement-communication`,
      {
        adjustment_id: payload.itemKey,
        communication_date: new Date().toISOString(),
        reason: payload.value,
      },
    )
  }
}

// ─── SSE 监听自动刷新 (Task 10.2) ────────────────────────────────────────

function onSSEEvent(payload: SyncEventPayload) {
  // 监听 a13_summary_updated 事件
  const eventType = payload.event_type as string
  if (eventType === 'a13_summary_updated' || eventType === 'workpaper.saved') {
    // 仅处理当前项目的事件
    if (payload.project_id && payload.project_id !== resolvedProjectId.value) return
    // 自动刷新数据
    void loadData()
    void loadSummaryResult()
  }
}

/** SSE 断开降级: tab 切换时主动 fetch 最新 summary */
function onVisibilityChange() {
  if (document.visibilityState === 'visible') {
    // tab 恢复可见时主动 fetch
    void loadData()
    void loadSummaryResult()
  }
}

// ─── Lifecycle ─────────────────────────────────────────────────────────────

onMounted(() => {
  loadData()
  loadSummaryResult()
  // 订阅 SSE 事件
  eventBus.on('sse:sync-event', onSSEEvent)
  // 订阅 visibility change 作为 SSE 断开降级
  document.addEventListener('visibilitychange', onVisibilityChange)
})

onUnmounted(() => {
  eventBus.off('sse:sync-event', onSSEEvent)
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
</script>

<style scoped>
.misstatement-summary__eval {
  margin-bottom: 12px;
}
.misstatement-summary__empty {
  padding: 40px 0;
  text-align: center;
  color: #909399;
}
.misstatement-summary__prior-year {
  margin-bottom: 16px;
}
.misstatement-summary__cumulative {
  font-weight: 600;
  color: var(--el-color-primary);
}
</style>
