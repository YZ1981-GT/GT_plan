<!--
  SeedLoaderPanel.vue — 种子数据加载面板 [template-library-coordination Task 4.5]

  需求 13.1-13.6：
  - "一键加载全部种子" 按钮（admin/partner，调 POST /seed-all）
  - 加载过程进度条
  - 失败时显示原因并继续后续（D15 SAVEPOINT 边界）
  - 加载完成汇总报告（每个种子的成功/跳过/失败条数）
  - 单独加载按钮（每个模块的"重新加载"）
  - 每个种子的最后加载时间和当前记录数

  D7 ADR：admin/partner 才显示加载/重新加载按钮（前端 v-permission + 后端二次校验）
  D8 ADR：数字列统一 .gt-amt
  D13 ADR：JSON 只读源（prefill_formula_mapping / cross_wp_references）不提供"重新加载"，引导文案
  D15 ADR：单个 seed 失败不影响其他（SAVEPOINT），UI 用 partial 状态与 errors 展示
  D16 ADR：所有数字（record_count / expected_count）从 API 动态取，不硬编码
-->
<template>
  <div class="gt-slp" v-loading="statusLoading">
    <!-- 顶部工具栏 -->
    <div class="gt-slp-toolbar">
      <span class="gt-slp-title">种子数据加载</span>
      <span class="gt-slp-summary">
        已加载 <span class="gt-amt">{{ loadedCount }}</span> /
        <span class="gt-amt">{{ seeds.length }}</span> 项
      </span>

      <div class="gt-slp-spacer" />

      <el-button size="small" :disabled="batchLoading" @click="refreshStatus">
        <el-icon style="margin-right: 4px"><Refresh /></el-icon>刷新状态
      </el-button>
      <el-button
        v-if="canEdit"
        size="small"
        type="primary"
        :loading="batchLoading"
        :disabled="seeds.length === 0"
        @click="onLoadAll"
      >
        <el-icon style="margin-right: 4px"><Upload /></el-icon>一键加载全部种子
      </el-button>
    </div>

    <!-- 批量加载进度条 -->
    <div v-if="batchLoading || batchProgress > 0" class="gt-slp-progress">
      <div class="gt-slp-progress-row">
        <span class="gt-slp-progress-label">
          {{ batchLoading ? '正在加载…' : '加载完成' }}
        </span>
        <span class="gt-slp-progress-stat">
          <span class="gt-amt">{{ completedSeedCount }}</span> /
          <span class="gt-amt">{{ totalBatchSeeds }}</span>
        </span>
      </div>
      <el-progress
        :percentage="batchProgress"
        :status="batchLoading ? '' : (batchHasFailed ? 'exception' : 'success')"
        :stroke-width="10"
      />
    </div>

    <!-- 状态表 -->
    <el-table
      :data="seeds"
      size="small"
      :header-cell-style="{ background: '#f0edf5', color: '#303133', fontWeight: '600' }"
      class="gt-slp-table"
      empty-text="暂无种子状态数据"
    >
      <el-table-column prop="seed_name" label="种子" min-width="180">
        <template #default="{ row }">
          <span class="gt-slp-seed-name">{{ seedLabel(row.seed_name) }}</span>
          <el-tag
            v-if="isJsonSource(row.seed_name)"
            size="small"
            type="info"
            effect="plain"
            round
            class="gt-slp-readonly-tag"
          >
            JSON 只读
          </el-tag>
          <div class="gt-slp-seed-key">{{ row.seed_name }}</div>
        </template>
      </el-table-column>

      <el-table-column label="当前记录数" width="120" align="right">
        <template #default="{ row }">
          <span class="gt-amt">{{ row.record_count ?? 0 }}</span>
        </template>
      </el-table-column>

      <el-table-column label="预期记录数" width="120" align="right">
        <template #default="{ row }">
          <span class="gt-amt">{{ row.expected_count ?? '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="状态" width="120" align="center">
        <template #default="{ row }">
          <el-tag
            size="small"
            :type="statusTagType(row.status)"
            effect="light"
          >
            {{ statusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="最后加载时间" min-width="180">
        <template #default="{ row }">
          <span v-if="row.last_loaded_at" class="gt-slp-time">
            {{ formatTime(row.last_loaded_at) }}
          </span>
          <span v-else class="gt-slp-time-empty">从未加载</span>
        </template>
      </el-table-column>

      <el-table-column label="操作" width="140" align="center">
        <template #default="{ row }">
          <el-button
            v-if="canEdit && !isJsonSource(row.seed_name)"
            size="small"
            text
            type="primary"
            :loading="reloadingSeed === row.seed_name"
            :disabled="batchLoading"
            @click="onReloadSingle(row)"
          >
            重新加载
          </el-button>
          <el-tooltip
            v-else-if="isJsonSource(row.seed_name)"
            content="JSON 源只读，请编辑对应 backend/data/*.json 文件后通过一键加载全部种子刷新"
            placement="top"
          >
            <span class="gt-slp-disabled">不支持</span>
          </el-tooltip>
          <span v-else class="gt-slp-disabled">—</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 加载结果汇总（折叠） -->
    <el-collapse
      v-if="lastBatchResults.length > 0"
      v-model="resultsExpanded"
      class="gt-slp-results"
    >
      <el-collapse-item name="results">
        <template #title>
          <span class="gt-slp-results-title">
            <el-icon><InfoFilled /></el-icon>
            加载结果汇总
            <el-tag size="small" type="success" effect="plain" round style="margin-left: 8px">
              成功 <span class="gt-amt">{{ batchSummary.loaded }}</span>
            </el-tag>
            <el-tag
              v-if="batchSummary.failed > 0"
              size="small"
              type="danger"
              effect="plain"
              round
              style="margin-left: 4px"
            >
              失败 <span class="gt-amt">{{ batchSummary.failed }}</span>
            </el-tag>
            <el-tag
              v-if="batchSummary.partial > 0"
              size="small"
              type="warning"
              effect="plain"
              round
              style="margin-left: 4px"
            >
              部分 <span class="gt-amt">{{ batchSummary.partial }}</span>
            </el-tag>
          </span>
        </template>
        <el-table
          :data="lastBatchResults"
          size="small"
          :header-cell-style="{ background: '#f8f6fb', color: '#606266', fontWeight: '600' }"
        >
          <el-table-column label="种子" min-width="200">
            <template #default="{ row }">{{ seedLabel(row.seed_name) }}</template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="statusTagType(row.status)" effect="light">
                {{ statusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="新增" width="80" align="right">
            <template #default="{ row }">
              <span class="gt-amt">{{ row.inserted ?? 0 }}</span>
            </template>
          </el-table-column>
          <el-table-column label="更新" width="80" align="right">
            <template #default="{ row }">
              <span class="gt-amt">{{ row.updated ?? 0 }}</span>
            </template>
          </el-table-column>
          <el-table-column label="记录数" width="100" align="right">
            <template #default="{ row }">
              <span class="gt-amt">{{ row.record_count ?? 0 }}</span>
            </template>
          </el-table-column>
          <el-table-column label="错误" min-width="240">
            <template #default="{ row }">
              <span v-if="!row.errors || row.errors.length === 0" class="gt-slp-no-error">—</span>
              <el-popover
                v-else
                placement="top-start"
                :width="420"
                trigger="hover"
              >
                <template #reference>
                  <el-tag size="small" type="danger" effect="plain">
                    {{ row.errors.length }} 条错误
                  </el-tag>
                </template>
                <div class="gt-slp-error-list">
                  <div
                    v-for="(err, idx) in row.errors.slice(0, 5)"
                    :key="idx"
                    class="gt-slp-error-item"
                  >
                    <code>{{ formatError(err) }}</code>
                  </div>
                  <div v-if="row.errors.length > 5" class="gt-slp-error-more">
                    … 仅展示前 5 条
                  </div>
                </div>
              </el-popover>
              <span v-if="row.error" class="gt-slp-fatal-error">{{ row.error }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, Upload, InfoFilled } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import { templateLibraryMgmt as P_tlm } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import { confirmDangerous } from '@/utils/confirm'
import { useAuthStore } from '@/stores/auth'
import { isJsonSource as _isJsonSource } from '@/composables/useTemplateLibrarySource'

// ─── 类型 ─────────────────────────────────────────────────────────────────

interface SeedInfo {
  seed_name: string
  last_loaded_at: string | null
  record_count: number
  expected_count: number | null
  status: string  // loaded / partial / not_loaded / unknown
}

interface SeedResult {
  seed_name: string
  status: string
  inserted?: number
  updated?: number
  record_count?: number
  errors?: any[]
  error?: string  // SAVEPOINT 失败时的整体错误
}

interface BatchResponse {
  total: number
  loaded: number
  failed: number
  partial: number
  results: SeedResult[]
}

// ─── 权限（D7 ADR）─────────────────────────────────────────────────────────

const authStore = useAuthStore()
const canEdit = computed(() => {
  const role = authStore.user?.role || ''
  return role === 'admin' || role === 'partner'
})

// ─── State ────────────────────────────────────────────────────────────────

const seeds = ref<SeedInfo[]>([])
const statusLoading = ref(false)
const batchLoading = ref(false)
const batchProgress = ref(0)  // 0-100
const totalBatchSeeds = ref(0)
const completedSeedCount = ref(0)
const reloadingSeed = ref<string | null>(null)
const resultsExpanded = ref<string[]>([])
const lastBatchResults = ref<SeedResult[]>([])

const batchSummary = computed(() => {
  const loaded = lastBatchResults.value.filter(r => r.status === 'loaded').length
  const partial = lastBatchResults.value.filter(r => r.status === 'partial').length
  const failed = lastBatchResults.value.filter(r => r.status === 'failed').length
  return { loaded, partial, failed }
})

const batchHasFailed = computed(() => batchSummary.value.failed > 0)

const loadedCount = computed(
  () => seeds.value.filter(s => s.status === 'loaded').length,
)

// ─── 单独加载端点映射（无独立端点 = null） ─────────────────────────────────

const SEED_RELOAD_MAP: Record<string, string | null> = {
  report_config: '/api/report-config/seed',
  gt_wp_coding: '/api/gt-coding/seed',
  wp_template_metadata: '/api/wp-template-metadata/seed',
  audit_report_templates: '/api/audit-report/templates/load-seed',
  accounting_standards: '/api/accounting-standards/seed',
  template_sets: '/api/template-sets/seed',
  // note_templates 无独立 seed 端点，必须通过一键加载触发
  note_templates: null,
  // JSON 只读源（D13 ADR）
  prefill_formula_mapping: null,
  cross_wp_references: null,
}

function isJsonSource(seedName: string): boolean {
  return _isJsonSource(seedName)
}

// ─── 中文标签映射 ─────────────────────────────────────────────────────────

const SEED_LABELS: Record<string, string> = {
  report_config: '报表配置（行次结构 + 公式）',
  gt_wp_coding: '致同编码体系',
  wp_template_metadata: '底稿模板元数据',
  audit_report_templates: '审计报告模板',
  accounting_standards: '会计准则',
  template_sets: '底稿模板集',
  note_templates: '附注模板（国企版 + 上市版）',
  prefill_formula_mapping: '预填充公式映射',
  cross_wp_references: '跨底稿引用规则',
}

function seedLabel(seedName: string): string {
  return SEED_LABELS[seedName] || seedName
}

// ─── 状态显示 ─────────────────────────────────────────────────────────────

function statusTagType(status: string): 'success' | 'warning' | 'danger' | 'info' {
  if (status === 'loaded') return 'success'
  if (status === 'partial') return 'warning'
  if (status === 'not_loaded' || status === 'failed') return 'danger'
  return 'info'
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    loaded: '已加载',
    partial: '部分加载',
    not_loaded: '未加载',
    failed: '失败',
    unknown: '未知',
  }
  return map[status] || status
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso)
    if (isNaN(d.getTime())) return iso
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  } catch {
    return iso
  }
}

function formatError(err: any): string {
  if (!err) return ''
  if (typeof err === 'string') return err
  if (err.error) return err.error
  if (err.message) return err.message
  return JSON.stringify(err)
}

// ─── API 调用 ─────────────────────────────────────────────────────────────

async function refreshStatus() {
  statusLoading.value = true
  try {
    const data = await api.get(P_tlm.seedStatus)
    seeds.value = (data?.seeds || []) as SeedInfo[]
  } catch (e: any) {
    handleApiError(e, '加载种子状态')
    seeds.value = []
  } finally {
    statusLoading.value = false
  }
}

async function onLoadAll() {
  try {
    await confirmDangerous(
      '将依次加载全部种子数据，每个种子在独立 SAVEPOINT 内执行。\n该操作可能耗时数十秒并覆盖现有数据，确认继续？',
      '一键加载全部种子',
    )
  } catch {
    return  // 用户取消
  }

  batchLoading.value = true
  batchProgress.value = 0
  totalBatchSeeds.value = seeds.value.filter(s => !isJsonSource(s.seed_name)).length || 6
  completedSeedCount.value = 0
  lastBatchResults.value = []

  // 模拟前端进度（后端 /seed-all 是单次请求阻塞返回）
  // 真实进度通过完成后展示 results 数组体现，加载期间用平滑动画
  const progressTimer = setInterval(() => {
    if (batchProgress.value < 95) {
      batchProgress.value = Math.min(95, batchProgress.value + Math.random() * 8 + 2)
    }
  }, 500)

  try {
    const data = await api.post<BatchResponse>(P_tlm.seedAll)
    lastBatchResults.value = data?.results || []
    completedSeedCount.value = lastBatchResults.value.length
    batchProgress.value = 100
    resultsExpanded.value = ['results']

    if (data?.failed && data.failed > 0) {
      ElMessage.warning(`加载完成，${data.loaded} 成功 / ${data.failed} 失败 / ${data.partial} 部分`)
    } else {
      ElMessage.success(`全部种子加载成功（共 ${data?.loaded ?? 0} 项）`)
    }
  } catch (e: any) {
    handleApiError(e, '一键加载全部种子')
    batchProgress.value = 0
  } finally {
    clearInterval(progressTimer)
    batchLoading.value = false
    // 重新拉取最新状态
    await refreshStatus()
  }
}

async function onReloadSingle(row: SeedInfo) {
  const endpoint = SEED_RELOAD_MAP[row.seed_name]
  if (!endpoint) {
    ElMessage.warning(`${seedLabel(row.seed_name)} 无独立加载端点，请使用"一键加载全部种子"`)
    return
  }

  try {
    await confirmDangerous(
      `将重新加载「${seedLabel(row.seed_name)}」种子数据，确认继续？`,
      '重新加载种子',
    )
  } catch {
    return
  }

  reloadingSeed.value = row.seed_name
  try {
    await api.post(endpoint)
    ElMessage.success(`${seedLabel(row.seed_name)} 重新加载成功`)
    await refreshStatus()
  } catch (e: any) {
    handleApiError(e, `重新加载 ${seedLabel(row.seed_name)}`)
  } finally {
    reloadingSeed.value = null
  }
}

// ─── 生命周期 ─────────────────────────────────────────────────────────────

onMounted(() => {
  refreshStatus()
})

defineExpose({ refreshStatus })
</script>

<style scoped>
.gt-slp { padding: 4px 0; }

/* D8 ADR：数字列 */
.gt-amt {
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

/* 紧凑工具栏 */
.gt-slp-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: var(--gt-color-bg-white);
  border: 1px solid #ebeef5;
  border-radius: 6px;
  margin-bottom: 12px;
}
.gt-slp-title {
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  color: var(--gt-color-primary);
}
.gt-slp-summary { font-size: var(--gt-font-size-xs); color: var(--gt-color-info); }
.gt-slp-spacer { flex: 1; }

/* 进度条 */
.gt-slp-progress {
  background: var(--gt-color-bg-white);
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 12px 16px;
  margin-bottom: 12px;
}
.gt-slp-progress-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-regular);
}
.gt-slp-progress-label { font-weight: 500; }

/* 表格 */
.gt-slp-table {
  background: var(--gt-color-bg-white);
  border-radius: 6px;
  overflow: hidden;
}
.gt-slp-seed-name { font-weight: 500; }
.gt-slp-seed-key {
  font-family: ui-monospace, Menlo, Consolas, monospace;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-info);
  margin-top: 2px;
}
.gt-slp-readonly-tag { margin-left: 6px; }
.gt-slp-time { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-regular); }
.gt-slp-time-empty { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-placeholder); }
.gt-slp-disabled { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-placeholder); }

/* 结果汇总 */
.gt-slp-results {
  margin-top: 12px;
  background: var(--gt-color-bg-white);
  border: 1px solid #ebeef5;
  border-radius: 6px;
}
.gt-slp-results :deep(.el-collapse-item__header) {
  padding: 0 16px;
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
}
.gt-slp-results-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.gt-slp-error-list {
  max-height: 240px;
  overflow-y: auto;
  font-size: var(--gt-font-size-xs);
}
.gt-slp-error-item {
  margin-bottom: 6px;
  padding: 4px 6px;
  background: var(--gt-bg-danger);
  border-radius: 3px;
  word-break: break-all;
}
.gt-slp-error-item code { font-size: var(--gt-font-size-xs); color: var(--gt-color-coral); }
.gt-slp-error-more { color: var(--gt-color-info); font-size: var(--gt-font-size-xs); padding: 4px 0; }
.gt-slp-no-error { color: var(--gt-color-text-placeholder); }
.gt-slp-fatal-error { color: var(--gt-color-coral); font-size: var(--gt-font-size-xs); }
</style>
