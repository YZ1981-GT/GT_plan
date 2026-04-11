<template>
  <div class="account-mapping-step">
    <h2 class="step-title">科目映射</h2>
    <p class="step-desc">将客户科目映射到标准审计科目，支持自动匹配和手动调整</p>

    <!-- Toolbar -->
    <div class="toolbar">
      <el-button type="primary" :loading="autoSuggesting" @click="handleAutoSuggest">
        自动匹配
      </el-button>
      <el-button
        type="success"
        :loading="batchConfirming"
        :disabled="suggestions.length === 0 && pendingMappings.length === 0"
        @click="handleBatchConfirm"
      >
        批量确认
      </el-button>
      <div class="toolbar-spacer" />
      <div class="completion-info">
        <span class="rate-label">完成率</span>
        <el-progress
          :percentage="completionRate"
          :stroke-width="18"
          :text-inside="true"
          style="width: 200px"
        />
        <span class="rate-text">{{ mappedCount }}/{{ totalCount }}</span>
      </div>
    </div>

    <!-- Warning for unmapped accounts with balance -->
    <el-alert
      v-if="unmappedWithBalance.length > 0"
      title="以下未映射科目存在余额，需完成映射后才能进入下一步"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 16px"
    >
      <template #default>
        <div class="unmapped-list">
          <span v-for="item in unmappedWithBalance" :key="item.account_code" class="unmapped-item">
            {{ item.account_code }} {{ item.account_name }}（余额: {{ item.closing_balance }}）
          </span>
        </div>
      </template>
    </el-alert>

    <!-- Three-column layout -->
    <div class="mapping-layout">
      <!-- Left: Client accounts -->
      <div class="column column-left">
        <div class="column-header">客户科目</div>
        <div class="account-list">
          <div
            v-for="account in clientAccounts"
            :key="account.account_code"
            class="account-item"
            :class="{
              selected: selectedClientCode === account.account_code,
              mapped: isMapped(account.account_code),
              unmatched: !isMapped(account.account_code) && !hasSuggestion(account.account_code),
            }"
            @click="selectClient(account)"
          >
            <span class="item-code">{{ account.account_code }}</span>
            <span class="item-name">{{ account.account_name }}</span>
            <el-tag v-if="isMapped(account.account_code)" size="small" type="success">已映射</el-tag>
            <el-tag v-else-if="hasSuggestion(account.account_code)" size="small" type="warning">建议</el-tag>
          </div>
          <div v-if="clientAccounts.length === 0" class="empty-hint">
            请先在上一步导入客户科目表
          </div>
        </div>
      </div>

      <!-- Center: Mapping status -->
      <div class="column column-center">
        <div class="column-header">映射状态</div>
        <div class="mapping-detail" v-if="selectedClientCode">
          <div class="detail-label">当前选中</div>
          <div class="detail-value">{{ selectedClientCode }} {{ selectedClientName }}</div>

          <template v-if="currentMappingStdCode">
            <div class="detail-label" style="margin-top: 12px">已映射到</div>
            <div class="detail-value mapped-target">
              {{ currentMappingStdCode }}
              <el-icon><Right /></el-icon>
            </div>
          </template>

          <template v-else-if="currentSuggestion">
            <div class="detail-label" style="margin-top: 12px">建议映射</div>
            <div class="detail-value suggestion-target">
              {{ currentSuggestion.suggested_standard_code }}
              {{ currentSuggestion.suggested_standard_name }}
            </div>
            <div class="detail-meta">
              匹配方式: {{ matchMethodLabel(currentSuggestion.match_method) }}
              · 置信度: {{ (currentSuggestion.confidence * 100).toFixed(0) }}%
            </div>
          </template>

          <template v-else>
            <div class="detail-label" style="margin-top: 12px">状态</div>
            <div class="detail-value unmatched-hint">未匹配，请从右侧选择标准科目</div>
          </template>

          <!-- Manual mapping dropdown -->
          <div class="manual-mapping" style="margin-top: 16px">
            <div class="detail-label">手动选择标准科目</div>
            <el-select
              v-model="manualStdCode"
              filterable
              placeholder="搜索标准科目编码或名称"
              style="width: 100%"
              @change="handleManualMapping"
            >
              <el-option
                v-for="std in standardAccounts"
                :key="std.account_code"
                :label="`${std.account_code} ${std.account_name}`"
                :value="std.account_code"
              />
            </el-select>
          </div>
        </div>
        <div v-else class="empty-hint">
          点击左侧客户科目查看映射详情
        </div>
      </div>

      <!-- Right: Standard accounts -->
      <div class="column column-right">
        <div class="column-header">标准科目</div>
        <div class="account-list">
          <div
            v-for="account in standardAccounts"
            :key="account.account_code"
            class="account-item"
            :class="{ highlighted: account.account_code === currentMappingStdCode }"
            @click="handleStdClick(account)"
          >
            <span class="item-code">{{ account.account_code }}</span>
            <span class="item-name">{{ account.account_name }}</span>
          </div>
          <div v-if="standardAccounts.length === 0" class="empty-hint">
            标准科目表未加载
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Right } from '@element-plus/icons-vue'
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

// --- State ---

const clientAccounts = ref<AccountItem[]>([])
const standardAccounts = ref<AccountItem[]>([])
const suggestions = ref<MappingSuggestion[]>([])
const mappings = ref<MappingRecord[]>([])
const pendingMappings = ref<MappingSuggestion[]>([])

const selectedClientCode = ref<string | null>(null)
const selectedClientName = ref<string>('')
const manualStdCode = ref<string>('')

const autoSuggesting = ref(false)
const batchConfirming = ref(false)

const mappedCount = ref(0)
const totalCount = ref(0)
const completionRate = ref(0)
const unmappedWithBalance = ref<UnmappedItem[]>([])

// --- Computed ---

const mappedCodes = computed(() => new Set(mappings.value.map((m) => m.original_account_code)))
const suggestionMap = computed(() => {
  const map = new Map<string, MappingSuggestion>()
  for (const s of suggestions.value) {
    map.set(s.original_account_code, s)
  }
  return map
})

const currentMappingStdCode = computed(() => {
  if (!selectedClientCode.value) return null
  const m = mappings.value.find((m) => m.original_account_code === selectedClientCode.value)
  return m?.standard_account_code ?? null
})

const currentSuggestion = computed(() => {
  if (!selectedClientCode.value) return null
  return suggestionMap.value.get(selectedClientCode.value) ?? null
})

// --- Methods ---

function isMapped(code: string): boolean {
  return mappedCodes.value.has(code)
}

function hasSuggestion(code: string): boolean {
  return suggestionMap.value.has(code)
}

function matchMethodLabel(method: string): string {
  const labels: Record<string, string> = {
    prefix: '编码前缀匹配',
    exact_name: '名称精确匹配',
    fuzzy_name: '名称模糊匹配',
  }
  return labels[method] || method
}

function selectClient(account: AccountItem) {
  selectedClientCode.value = account.account_code
  selectedClientName.value = account.account_name
  // Pre-fill manual dropdown with current mapping or suggestion
  const existing = mappings.value.find((m) => m.original_account_code === account.account_code)
  if (existing) {
    manualStdCode.value = existing.standard_account_code
  } else {
    const sug = suggestionMap.value.get(account.account_code)
    manualStdCode.value = sug?.suggested_standard_code ?? ''
  }
}

function handleStdClick(account: AccountItem) {
  if (!selectedClientCode.value) {
    ElMessage.info('请先选择左侧的客户科目')
    return
  }
  manualStdCode.value = account.account_code
  handleManualMapping(account.account_code)
}

async function handleManualMapping(stdCode: string) {
  if (!wizardStore.projectId || !selectedClientCode.value || !stdCode) return

  try {
    const { data } = await http.post(
      `/api/projects/${wizardStore.projectId}/mapping`,
      {
        original_account_code: selectedClientCode.value,
        original_account_name: selectedClientName.value,
        standard_account_code: stdCode,
        mapping_type: 'manual',
      },
    )
    const record = data.data ?? data
    // Update local mappings
    const idx = mappings.value.findIndex(
      (m) => m.original_account_code === selectedClientCode.value,
    )
    if (idx >= 0) {
      mappings.value[idx] = record
    } else {
      mappings.value.push(record)
    }
    ElMessage.success('映射已保存')
    await loadCompletionRate()
  } catch {
    // Error handled by interceptor
  }
}

async function handleAutoSuggest() {
  if (!wizardStore.projectId) return
  autoSuggesting.value = true
  try {
    const { data } = await http.post(
      `/api/projects/${wizardStore.projectId}/mapping/auto-suggest`,
    )
    suggestions.value = data.data ?? data
    // Build pending mappings from suggestions that aren't already mapped
    pendingMappings.value = suggestions.value.filter(
      (s) => !isMapped(s.original_account_code),
    )
    ElMessage.success(`自动匹配完成，找到 ${suggestions.value.length} 个建议`)
  } catch {
    // Error handled by interceptor
  } finally {
    autoSuggesting.value = false
  }
}

async function handleBatchConfirm() {
  if (!wizardStore.projectId) return

  // Combine suggestions and pending into batch
  const toConfirm = suggestions.value
    .filter((s) => !isMapped(s.original_account_code))
    .map((s) => ({
      original_account_code: s.original_account_code,
      original_account_name: s.original_account_name,
      standard_account_code: s.suggested_standard_code,
      mapping_type: s.confidence >= 0.95 ? 'auto_exact' : 'auto_fuzzy',
    }))

  if (toConfirm.length === 0) {
    ElMessage.info('没有待确认的映射建议')
    return
  }

  batchConfirming.value = true
  try {
    const { data } = await http.post(
      `/api/projects/${wizardStore.projectId}/mapping/batch-confirm`,
      toConfirm,
    )
    const result = data.data ?? data
    ElMessage.success(`已确认 ${result.confirmed_count} 条映射，完成率 ${result.completion_rate}%`)

    // Reload data
    await loadMappings()
    await loadCompletionRate()
    pendingMappings.value = []

    // Save step data
    await wizardStore.saveStep('account_mapping', {
      mapped_count: mappedCount.value,
      total_count: totalCount.value,
      completion_rate: completionRate.value,
    })
  } catch {
    // Error handled by interceptor
  } finally {
    batchConfirming.value = false
  }
}

// --- Data loading ---

async function loadClientAccounts() {
  if (!wizardStore.projectId) return
  try {
    const { data } = await http.get(
      `/api/projects/${wizardStore.projectId}/account-chart/client`,
    )
    const tree = data.data ?? data
    // Flatten tree into list
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
    const accounts = data.data ?? data
    standardAccounts.value = accounts
  } catch {
    // Silently fail
  }
}

async function loadMappings() {
  if (!wizardStore.projectId) return
  try {
    const { data } = await http.get(
      `/api/projects/${wizardStore.projectId}/mapping`,
    )
    mappings.value = data.data ?? data
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
    loadMappings(),
    loadCompletionRate(),
  ])
})
</script>

<style scoped>
.account-mapping-step {
  max-width: 1200px;
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
  margin-bottom: var(--gt-space-4);
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

/* Three-column layout */
.mapping-layout {
  display: grid;
  grid-template-columns: 1fr 300px 1fr;
  gap: 16px;
  min-height: 500px;
}

.column {
  border: 1px solid #e8e8e8;
  border-radius: var(--gt-radius-md);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.column-header {
  padding: 10px 16px;
  font-weight: 600;
  font-size: 14px;
  color: var(--gt-color-primary);
  background: #f5f0fa;
  border-bottom: 1px solid #e8e8e8;
}

.column-center .column-header {
  background: #f0f5ff;
}

.account-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.account-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  transition: background 0.15s;
}

.account-item:hover {
  background: #f5f5f5;
}

.account-item.selected {
  background: #e8e0f0;
}

.account-item.mapped {
  background: #f0faf0;
}

.account-item.unmatched {
  background: #fffbe6;
}

.account-item.highlighted {
  background: #e6f7ff;
  border: 1px solid #91d5ff;
}

.item-code {
  font-family: monospace;
  color: var(--gt-color-primary);
  min-width: 50px;
}

.item-name {
  flex: 1;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Center column detail */
.mapping-detail {
  padding: 16px;
}

.detail-label {
  font-size: 12px;
  color: #999;
  margin-bottom: 4px;
}

.detail-value {
  font-size: 14px;
  color: #333;
  font-weight: 500;
}

.mapped-target {
  color: #52c41a;
  display: flex;
  align-items: center;
  gap: 4px;
}

.suggestion-target {
  color: #fa8c16;
}

.unmatched-hint {
  color: #faad14;
  font-weight: normal;
}

.detail-meta {
  font-size: 12px;
  color: #999;
  margin-top: 4px;
}

.manual-mapping {
  border-top: 1px solid #f0f0f0;
  padding-top: 12px;
}

.empty-hint {
  text-align: center;
  color: #ccc;
  padding: 40px 16px;
  font-size: 14px;
}
</style>
