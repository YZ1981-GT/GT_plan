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

    <!-- A13-1: 未更正错报汇总表 -->
    <WorkpaperHtmlTable
      title="A13-1 未更正错报汇总表"
      :header="header"
      :columns="columns"
      :rows="allRows"
      scope="misstatement:summary"
      :project-id="projectId"
      :year="year"
      @field-change="onFieldChange"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api } from '@/services/apiProxy'
import WorkpaperHtmlTable, { type ColumnDef, type RowData, type StandardHeader } from './WorkpaperHtmlTable.vue'

const props = defineProps<{
  projectId: string
  year: number
  header?: StandardHeader | null
}>()

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
      `/api/workpapers/${props.projectId}/${props.year}/misstatement-communication`,
      {
        adjustment_id: payload.itemKey,
        communication_date: new Date().toISOString(),
        reason: payload.value,
      },
    )
  }
}

async function loadData() {
  try {
    const [summary, eval_] = await Promise.all([
      api.get<typeof summaryData.value>(
        `/api/workpapers/${props.projectId}/${props.year}/misstatement-summary`,
      ),
      api.get<Evaluation>(
        `/api/workpapers/${props.projectId}/${props.year}/misstatement-evaluation`,
      ),
    ])
    summaryData.value = summary
    evaluation.value = eval_
  } catch {
    // 降级
  }
}

onMounted(loadData)
</script>

<style scoped>
.misstatement-summary__eval {
  margin-bottom: 12px;
}
</style>
