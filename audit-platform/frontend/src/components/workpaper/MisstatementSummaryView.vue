<!--
  MisstatementSummaryView — A13 错报汇总 HTML 视图

  从后端获取 passed 调整分录自动生成的错报清单，
  使用 WorkpaperHtmlTable 渲染，支持索引跳转和用户补充原因。

  Requirements: 1.1, 1.4, 2.3
-->
<template>
  <div class="misstatement-summary">
    <!-- 评价区：汇总 vs 重要性 -->
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
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useProjectStore } from '@/stores/project'
import { api } from '@/services/apiProxy'
import WorkpaperHtmlTable, { type ColumnDef, type RowData, type StandardHeader } from './WorkpaperHtmlTable.vue'

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

const summaryData = ref<{ prior: SummaryItem[]; current: SummaryItem[] }>({ prior: [], current: [] })
const evaluation = ref<Evaluation | null>(null)
const loaded = ref(false)

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

function formatAmount(val: number | null | undefined): string {
  if (val == null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2 })
}

function onFieldChange(payload: { itemKey: string; field: string; value: any }) {
  // 回写 passed_reason 到 adjustment
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

onMounted(loadData)
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
</style>
