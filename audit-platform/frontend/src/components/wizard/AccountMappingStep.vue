<template>
  <div class="gt-account-mapping-step">
    <h2 class="step-title">科目映射</h2>
    <p class="step-desc">将客户科目映射到标准审计科目，点击自动匹配后确认结果</p>

    <!-- Toolbar -->
    <div class="toolbar">
      <el-button type="primary" :loading="autoMatching" @click="handleAutoMatch">
        <el-icon style="margin-right: 4px"><Connection /></el-icon>
        自动匹配
      </el-button>
      <el-button
        v-if="unmatchedCount > 0"
        type="warning"
        plain
        @click="showUnmatched = !showUnmatched"
      >
        未匹配 ({{ unmatchedCount }})
      </el-button>
      <div class="toolbar-spacer" />
      <div class="completion-info">
        <span class="rate-label">完成率</span>
        <el-progress
          :percentage="completionRate"
          :stroke-width="18"
          :text-inside="true"
          style="width: 180px"
        />
        <span class="rate-text">{{ mappedCount }}/{{ totalCount }}</span>
      </div>
    </div>

    <!-- Auto-match result summary -->
    <el-alert
      v-if="matchResultMsg"
      :title="matchResultMsg"
      type="success"
      :closable="true"
      show-icon
      style="margin-bottom: 12px"
      @close="matchResultMsg = ''"
    />

    <!-- Warning for unmapped accounts with balance -->
    <el-alert
      v-if="unmappedWithBalance.length > 0"
      title="以下未映射科目存在余额，建议完成映射"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 12px"
    >
      <template #default>
        <div class="unmapped-list">
          <span v-for="item in unmappedWithBalance" :key="item.account_code" class="unmapped-item">
            {{ item.account_code }} {{ item.account_name }}（余额: {{ item.closing_balance }}）
          </span>
        </div>
      </template>
    </el-alert>

    <!-- Mapping result table -->
    <el-table
      :data="tableRows"
      border
      stripe
      size="small"
      max-height="520"
      style="width: 100%"
      :row-style="rowStyle"
    >
      <el-table-column label="客户科目编码" prop="account_code" width="130" sortable>
        <template #default="{ row }">
          <span class="code-cell">{{ row.account_code }}</span>
        </template>
      </el-table-column>
      <el-table-column label="客户科目名称" prop="account_name" min-width="160" show-overflow-tooltip />
      <el-table-column label="" width="50" align="center">
        <template #default>
          <el-icon style="color: #999"><Right /></el-icon>
        </template>
      </el-table-column>
      <el-table-column label="标准科目" min-width="220">
        <template #default="{ row }">
          <el-select
            :model-value="row.standard_account_code"
            filterable
            placeholder="选择标准科目"
            size="small"
            style="width: 100%"
            @change="(val: string) => handleMappingChange(row, val)"
          >
            <el-option
              v-for="std in standardAccounts"
              :key="std.account_code"
              :label="`${std.account_code} ${std.account_name}`"
              :value="std.account_code"
            />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="匹配方式" width="120" align="center">
        <template #default="{ row }">
          <el-tag
            v-if="row.match_method"
            :type="matchTagType(row.match_method)"
            size="small"
          >
            {{ matchMethodLabel(row.match_method) }}
          </el-tag>
          <el-tag v-else-if="row.standard_account_code" type="info" size="small">手动</el-tag>
          <el-tag v-else type="danger" size="small">未匹配</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="置信度" width="80" align="center">
        <template #default="{ row }">
          <span v-if="row.confidence" :style="{ color: confidenceColor(row.confidence) }">
            {{ (row.confidence * 100).toFixed(0) }}%
          </span>
          <span v-else style="color: #ccc">—</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- Unmatched accounts drawer -->
    <el-drawer v-model="showUnmatched" title="未匹配科目" size="420px" direction="rtl">
      <div v-for="row in unmatchedRows" :key="row.account_code" class="unmatched-row">
        <span class="code-cell">{{ row.account_code }}</span>
        <span class="unmatched-name">{{ row.account_name }}</span>
        <el-select
          :model-value="row.standard_account_code"
          filterable
          placeholder="手动选择"
          size="small"
          style="width: 200px; margin-left: auto"
          @change="(val: string) => handleMappingChange(row, val)"
        >
          <el-option
            v-for="std in standardAccounts"
            :key="std.account_code"
            :label="`${std.account_code} ${std.account_name}`"
            :value="std.account_code"
          />
        </el-select>
      </div>
      <div v-if="unmatchedRows.length === 0" class="empty-hint">
        所有科目均已匹配
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Right, Connection } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { useWizardStore } from '@/stores/wizard'

const wizardStore = useWizardStore()

// --- Types ---

interface AccountItem {
  account_code: string
  account_name: string
  direction: string
  level: number
  category: string
}

interface MappingSuggestion {
  original_account_code: string
  original_account_name: string | null
  suggested_standard_code: string
  suggested_standard_name: string | null
  confidence: number
  match_method: string
}

interface MappingRecord {
  id: string
  original_account_code: string
  original_account_name: string | null
  standard_account_code: string
  mapping_type: string
}

interface UnmappedItem {
  account_code: string
  account_name: string | null
  closing_balance: string
}

interface TableRow {
  account_code: string
  account_name: string
  standard_account_code: string
  match_method: string
  confidence: number | null
  mapping_id: string | null
}

// --- State ---

const clientAccounts = ref<AccountItem[]>([])
const standardAccounts = ref<AccountItem[]>([])
const tableRows = ref<TableRow[]>([])

const autoMatching = ref(false)
const showUnmatched = ref(false)
const matchResultMsg = ref('')

const mappedCount = ref(0)
const totalCount = ref(0)
const completionRate = ref(0)
const unmappedWithBalance = ref<UnmappedItem[]>([])

// --- Computed ---

const unmatchedRows = computed(() =>
  tableRows.value.filter((r) => !r.standard_account_code),
)

const unmatchedCount = computed(() => unmatchedRows.value.length)

// --- Methods ---

function matchMethodLabel(method: string): string {
  const labels: Record<string, string> = {
    exact_code: '编码精确',
    prefix: '编码前缀',
    level1_prefix: '一级前缀',
    exact_name: '名称精确',
    base_name: '名称基础',
    fuzzy_name: '模糊匹配',
  }
  return labels[method] || method
}

function matchTagType(method: string): '' | 'success' | 'warning' | 'info' | 'danger' {
  if (method === 'exact_code' || method === 'prefix' || method === 'level1_prefix') return 'success'
  if (method === 'exact_name' || method === 'base_name') return ''
  if (method === 'fuzzy_name') return 'warning'
  return 'info'
}

function confidenceColor(c: number): string {
  if (c >= 0.95) return '#52c41a'
  if (c >= 0.85) return '#fa8c16'
  return '#f5222d'
}

function rowStyle({ row }: { row: TableRow }) {
  if (!row.standard_account_code) return { background: '#fffbe6' }
  return {}
}

/** Rebuild tableRows from clientAccounts + mappings + matchDetails */
function rebuildTable(
  clients: AccountItem[],
  mappings: MappingRecord[],
  details: MappingSuggestion[],
) {
  const mappingMap = new Map<string, MappingRecord>()
  for (const m of mappings) mappingMap.set(m.original_account_code, m)

  const detailMap = new Map<string, MappingSuggestion>()
  for (const d of details) detailMap.set(d.original_account_code, d)

  tableRows.value = clients.map((c) => {
    const mapping = mappingMap.get(c.account_code)
    const detail = detailMap.get(c.account_code)
    return {
      account_code: c.account_code,
      account_name: c.account_name,
      standard_account_code: mapping?.standard_account_code ?? '',
      match_method: detail?.match_method ?? (mapping ? mapping.mapping_type : ''),
      confidence: detail?.confidence ?? null,
      mapping_id: mapping?.id ?? null,
    }
  })
}

async function handleAutoMatch() {
  if (!wizardStore.projectId) return
  autoMatching.value = true
  try {
    const { data } = await http.post(
      `/api/projects/${wizardStore.projectId}/mapping/auto-match`,
    )
    const result = data.data ?? data
    const details: MappingSuggestion[] = result.details || []
    matchResultMsg.value = `自动匹配完成：新增 ${result.saved_count} 条，跳过已映射 ${result.skipped_count} 条，未匹配 ${result.unmatched_count} 条，完成率 ${result.completion_rate}%`

    // Reload mappings, then rebuild table with details
    const mappings = await fetchMappings()
    rebuildTable(clientAccounts.value, mappings, details)
    await loadCompletionRate()

    // Save step
    await wizardStore.saveStep('account_mapping', {
      mapped_count: mappedCount.value,
      total_count: totalCount.value,
      completion_rate: completionRate.value,
    })
  } catch {
    // Error handled by interceptor
  } finally {
    autoMatching.value = false
  }
}

async function handleMappingChange(row: TableRow, stdCode: string) {
  if (!wizardStore.projectId || !stdCode) return
  try {
    let record: MappingRecord
    if (row.mapping_id) {
      // Update existing
      const { data } = await http.put(
        `/api/projects/${wizardStore.projectId}/mapping/${row.mapping_id}`,
        { standard_account_code: stdCode },
      )
      record = data.data ?? data
    } else {
      // Create new
      const { data } = await http.post(
        `/api/projects/${wizardStore.projectId}/mapping`,
        {
          original_account_code: row.account_code,
          original_account_name: row.account_name,
          standard_account_code: stdCode,
          mapping_type: 'manual',
        },
      )
      record = data.data ?? data
    }
    // Update row in-place (no full reload, no flicker)
    row.standard_account_code = record.standard_account_code
    row.mapping_id = record.id
    row.match_method = ''
    row.confidence = null
    ElMessage.success(`${row.account_code} 映射已更新`)
    await loadCompletionRate()
  } catch {
    // Error handled by interceptor
  }
}

// --- Data loading ---

async function fetchMappings(): Promise<MappingRecord[]> {
  if (!wizardStore.projectId) return []
  const { data } = await http.get(
    `/api/projects/${wizardStore.projectId}/mapping`,
  )
  return data.data ?? data
}

async function loadClientAccounts() {
  if (!wizardStore.projectId) return
  try {
    const { data } = await http.get(
      `/api/projects/${wizardStore.projectId}/account-chart/client`,
    )
    const tree = data.data ?? data
    const flat: AccountItem[] = []
    for (const nodes of Object.values(tree) as AccountItem[][]) {
      flattenTree(nodes, flat)
    }
    clientAccounts.value = flat.sort((a, b) => a.account_code.localeCompare(b.account_code))
  } catch {
    // Silently fail
  }
}

function flattenTree(nodes: any[], result: AccountItem[]) {
  for (const n of nodes) {
    result.push({
      account_code: n.account_code,
      account_name: n.account_name,
      direction: n.direction,
      level: n.level,
      category: n.category,
    })
    if (n.children) flattenTree(n.children, result)
  }
}

async function loadStandardAccounts() {
  if (!wizardStore.projectId) return
  try {
    const { data } = await http.get(
      `/api/projects/${wizardStore.projectId}/account-chart/standard`,
    )
    standardAccounts.value = data.data ?? data
  } catch {
    // Silently fail
  }
}

async function loadCompletionRate() {
  if (!wizardStore.projectId) return
  try {
    const { data } = await http.get(
      `/api/projects/${wizardStore.projectId}/mapping/completion-rate`,
    )
    const rate = data.data ?? data
    mappedCount.value = rate.mapped_count
    totalCount.value = rate.total_count
    completionRate.value = rate.completion_rate
    unmappedWithBalance.value = rate.unmapped_with_balance || []
  } catch {
    // Silently fail
  }
}

onMounted(async () => {
  await Promise.all([
    loadClientAccounts(),
    loadStandardAccounts(),
  ])
  // Load mappings and build table after clients are ready
  const mappings = await fetchMappings()
  rebuildTable(clientAccounts.value, mappings, [])
  await loadCompletionRate()
})
</script>

<style scoped>
.gt-account-mapping-step {
  max-width: 1100px;
  margin: 0 auto;
}

.step-title {
  color: var(--gt-color-primary);
  margin-bottom: var(--gt-space-1);
  font-size: 20px;
}

.step-desc {
  color: #999;
  margin-bottom: var(--gt-space-4);
  font-size: 14px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border-radius: var(--gt-radius-md);
}

.toolbar-spacer {
  flex: 1;
}

.completion-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.rate-label {
  font-size: 13px;
  color: #666;
  white-space: nowrap;
}

.rate-text {
  font-size: 13px;
  color: #999;
  white-space: nowrap;
}

.unmapped-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.unmapped-item {
  font-size: 13px;
  background: #fff3e0;
  padding: 2px 8px;
  border-radius: 4px;
}

.code-cell {
  font-family: monospace;
  color: var(--gt-color-primary);
}

.unmatched-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid #f0f0f0;
  font-size: 13px;
}

.unmatched-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.empty-hint {
  text-align: center;
  color: #ccc;
  padding: 40px 16px;
  font-size: 14px;
}
</style>
