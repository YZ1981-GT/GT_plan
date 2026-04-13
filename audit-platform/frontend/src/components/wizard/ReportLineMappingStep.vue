<template>
  <div class="gt-report-line-mapping">
    <h2 class="page-title">报表行次映射</h2>
    <p class="page-desc">将标准科目映射到报表行次，支持AI建议、手动调整和集团参照复制</p>

    <!-- Toolbar -->
    <div class="toolbar">
      <el-button type="primary" :loading="aiSuggesting" @click="handleAiSuggest">
        AI 自动匹配
      </el-button>
      <el-button
        type="success"
        :loading="batchConfirming"
        :disabled="unconfirmedIds.length === 0"
        @click="handleBatchConfirm"
      >
        批量确认 ({{ unconfirmedIds.length }})
      </el-button>
      <el-button type="warning" @click="showReferenceCopy = true">
        一键参照
      </el-button>
      <div class="toolbar-spacer" />
      <el-select
        v-model="filterReportType"
        placeholder="全部报表类型"
        clearable
        style="width: 180px"
        @change="loadMappings"
      >
        <el-option label="资产负债表" value="balance_sheet" />
        <el-option label="利润表" value="income_statement" />
        <el-option label="现金流量表" value="cash_flow" />
      </el-select>
    </div>

    <!-- Mapping table -->
    <el-table
      :data="mappings"
      stripe
      border
      style="width: 100%"
      max-height="600"
      empty-text="暂无映射数据，请先执行AI自动匹配"
    >
      <el-table-column prop="standard_account_code" label="标准科目编码" width="150" />
      <el-table-column label="报表类型" width="130">
        <template #default="{ row }">
          <el-tag :type="reportTypeTag(row.report_type)" size="small">
            {{ reportTypeLabel(row.report_type) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="report_line_code" label="行次编码" width="120" />
      <el-table-column prop="report_line_name" label="报表行次名称" min-width="160" />
      <el-table-column label="置信度" width="100">
        <template #default="{ row }">
          <span v-if="row.confidence_score != null" class="confidence">
            {{ (row.confidence_score * 100).toFixed(0) }}%
          </span>
          <span v-else class="confidence">—</span>
        </template>
      </el-table-column>
      <el-table-column label="映射类型" width="120">
        <template #default="{ row }">
          <el-tag :type="mappingTypeTag(row.mapping_type)" size="small">
            {{ mappingTypeLabel(row.mapping_type) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag v-if="row.is_confirmed" type="success" size="small">已确认</el-tag>
          <el-tag v-else type="warning" size="small">待确认</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="!row.is_confirmed"
            type="primary"
            size="small"
            link
            @click="handleConfirm(row)"
          >
            确认
          </el-button>
          <el-button
            v-if="!row.is_confirmed"
            type="danger"
            size="small"
            link
            @click="handleReject(row)"
          >
            拒绝
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- Reference copy dialog -->
    <el-dialog v-model="showReferenceCopy" title="一键参照复制" width="400px">
      <el-form label-width="100px">
        <el-form-item label="源企业名称">
          <el-input v-model="sourceCompanyCode" placeholder="输入源企业客户名称" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showReferenceCopy = false">取消</el-button>
        <el-button
          type="primary"
          :loading="referenceCopying"
          @click="handleReferenceCopy"
        >
          复制
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

const props = defineProps<{
  projectId: string
}>()

// --- Types ---

interface MappingRow {
  id: string
  project_id: string
  standard_account_code: string
  report_type: string
  report_line_code: string
  report_line_name: string
  report_line_level: number
  parent_line_code: string | null
  mapping_type: string
  is_confirmed: boolean
  confidence_score: number | null
  created_at: string
}

// --- State ---

const mappings = ref<MappingRow[]>([])
const filterReportType = ref<string>('')
const aiSuggesting = ref(false)
const batchConfirming = ref(false)
const showReferenceCopy = ref(false)
const sourceCompanyCode = ref('')
const referenceCopying = ref(false)

// --- Computed ---

const unconfirmedIds = computed(() =>
  mappings.value.filter((m) => !m.is_confirmed).map((m) => m.id),
)

// --- Label helpers ---

function reportTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    balance_sheet: '资产负债表',
    income_statement: '利润表',
    cash_flow: '现金流量表',
  }
  return labels[type] || type
}

function reportTypeTag(type: string): string {
  const tags: Record<string, string> = {
    balance_sheet: '',
    income_statement: 'success',
    cash_flow: 'warning',
  }
  return tags[type] || 'info'
}

function mappingTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    ai_suggested: 'AI建议',
    manual: '手动',
    reference_copied: '参照复制',
  }
  return labels[type] || type
}

function mappingTypeTag(type: string): string {
  const tags: Record<string, string> = {
    ai_suggested: 'info',
    manual: '',
    reference_copied: 'warning',
  }
  return tags[type] || 'info'
}

// --- Data loading ---

async function loadMappings() {
  if (!props.projectId) return
  try {
    const params: Record<string, string> = {}
    if (filterReportType.value) {
      params.report_type = filterReportType.value
    }
    const { data } = await http.get(
      `/api/projects/${props.projectId}/report-line-mapping`,
      { params },
    )
    mappings.value = data.data ?? data
  } catch {
    // Error handled by interceptor
  }
}

// --- Actions ---

async function handleAiSuggest() {
  if (!props.projectId) return
  aiSuggesting.value = true
  try {
    const { data } = await http.post(
      `/api/projects/${props.projectId}/report-line-mapping/ai-suggest`,
    )
    const suggestions = data.data ?? data
    ElMessage.success(`AI匹配完成，生成 ${suggestions.length} 条建议`)
    await loadMappings()
  } catch {
    // Error handled by interceptor
  } finally {
    aiSuggesting.value = false
  }
}

async function handleConfirm(row: MappingRow) {
  try {
    await http.put(
      `/api/projects/${props.projectId}/report-line-mapping/${row.id}/confirm`,
    )
    row.is_confirmed = true
    ElMessage.success('已确认')
  } catch {
    // Error handled by interceptor
  }
}

async function handleReject(row: MappingRow) {
  // Soft-delete the rejected mapping (mark as deleted on frontend)
  const idx = mappings.value.findIndex((m) => m.id === row.id)
  if (idx >= 0) {
    mappings.value.splice(idx, 1)
  }
  ElMessage.info('已移除该建议')
}

async function handleBatchConfirm() {
  if (!props.projectId || unconfirmedIds.value.length === 0) return
  batchConfirming.value = true
  try {
    const { data } = await http.post(
      `/api/projects/${props.projectId}/report-line-mapping/batch-confirm`,
      { mapping_ids: unconfirmedIds.value },
    )
    const result = data.data ?? data
    ElMessage.success(`已批量确认 ${result.confirmed_count} 条映射`)
    await loadMappings()
  } catch {
    // Error handled by interceptor
  } finally {
    batchConfirming.value = false
  }
}

async function handleReferenceCopy() {
  if (!props.projectId || !sourceCompanyCode.value) {
    ElMessage.warning('请输入源企业名称')
    return
  }
  referenceCopying.value = true
  try {
    const { data } = await http.post(
      `/api/projects/${props.projectId}/report-line-mapping/reference-copy`,
      { source_company_code: sourceCompanyCode.value },
    )
    const result = data.data ?? data
    ElMessage.success(`已复制 ${result.copied_count} 条映射`)
    if (result.unmatched_accounts?.length > 0) {
      ElMessage.warning(`${result.unmatched_accounts.length} 个科目未匹配: ${result.unmatched_accounts.join(', ')}`)
    }
    showReferenceCopy.value = false
    await loadMappings()
  } catch {
    // Error handled by interceptor
  } finally {
    referenceCopying.value = false
  }
}

onMounted(() => {
  loadMappings()
})
</script>

<style scoped>
.gt-report-line-mapping {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

.page-title {
  color: var(--gt-color-primary);
  margin-bottom: var(--gt-space-1);
  font-size: 20px;
}

.page-desc {
  color: #999;
  margin-bottom: var(--gt-space-4);
  font-size: 14px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: var(--gt-space-4);
  padding: 12px 16px;
  background: #fafafa;
  border-radius: var(--gt-radius-md);
}

.toolbar-spacer {
  flex: 1;
}

.confidence {
  font-family: monospace;
  font-weight: 600;
  color: var(--gt-color-primary);
}
</style>
