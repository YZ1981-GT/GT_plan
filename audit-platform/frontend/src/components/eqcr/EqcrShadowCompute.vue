<template>
  <div v-loading="loadingHistory" class="eqcr-tab">
    <!-- 执行区域 -->
    <el-card shadow="never" class="eqcr-tab__section">
      <template #header>
        <span class="eqcr-tab__section-title">影子计算</span>
      </template>

      <el-form :inline="true" class="shadow-compute-form">
        <el-form-item label="计算类型">
          <el-select
            v-model="computationType"
            placeholder="请选择计算类型"
            style="width: 240px"
          >
            <el-option
              v-for="opt in COMPUTATION_TYPE_OPTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            :loading="executing"
            :disabled="!computationType"
            @click="executeCompute"
          >
            执行计算
          </el-button>
        </el-form-item>
      </el-form>

      <!-- 限流提示 -->
      <el-alert
        v-if="rateLimited"
        type="warning"
        show-icon
        :closable="false"
        title="今日计算次数已达上限（20次/天）"
        style="margin-top: 12px"
      />

      <!-- 最新结果展示 -->
      <div v-if="latestResult" class="shadow-compute-result">
        <el-alert
          v-if="latestResult.has_diff"
          type="error"
          show-icon
          :closable="false"
          title="⚠️ 发现差异"
          description="EQCR 独立计算结果与项目组结果不一致，请核实差异原因。"
          style="margin-top: 12px"
        />
        <el-alert
          v-else
          type="success"
          show-icon
          :closable="false"
          title="✅ 一致"
          description="EQCR 独立计算结果与项目组结果一致。"
          style="margin-top: 12px"
        />

        <el-descriptions
          :column="2"
          border
          size="small"
          style="margin-top: 12px"
        >
          <el-descriptions-item label="计算类型">
            {{ computationTypeLabel(latestResult.computation_type) }}
          </el-descriptions-item>
          <el-descriptions-item label="执行时间">
            {{ formatDateTime(latestResult.created_at) }}
          </el-descriptions-item>
        </el-descriptions>

        <el-collapse style="margin-top: 12px">
          <el-collapse-item title="EQCR 独立计算结果">
            <pre class="shadow-compute-json">{{ formatJson(latestResult.result) }}</pre>
          </el-collapse-item>
          <el-collapse-item title="项目组结果快照">
            <pre class="shadow-compute-json">{{ formatJson(latestResult.team_result_snapshot) }}</pre>
          </el-collapse-item>
        </el-collapse>
      </div>
    </el-card>

    <!-- 历史记录表格 -->
    <el-card shadow="never" class="eqcr-tab__section">
      <template #header>
        <div class="eqcr-tab__section-header">
          <span class="eqcr-tab__section-title">历史记录</span>
          <el-tag size="small" type="info" effect="plain">
            共 {{ history.length }} 条
          </el-tag>
        </div>
      </template>

      <el-empty
        v-if="!loadingHistory && history.length === 0"
        description="暂无影子计算记录"
        :image-size="60"
      />

      <el-table
        v-else
        :data="history"
        size="small"
        border
        stripe
        style="width: 100%"
        :row-class-name="rowClassName"
      >
        <el-table-column label="计算类型" min-width="200">
          <template #default="{ row }">
            {{ computationTypeLabel(row.computation_type) }}
          </template>
        </el-table-column>
        <el-table-column label="执行时间" width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="是否有差异" width="130" align="center">
          <template #default="{ row }">
            <el-tag
              v-if="row.has_diff"
              type="danger"
              size="small"
              effect="dark"
            >
              有差异
            </el-tag>
            <el-tag
              v-else
              type="success"
              size="small"
              effect="light"
            >
              一致
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" align="center">
          <template #default="{ row }">
            <el-button
              size="small"
              link
              type="primary"
              @click="toggleDetail(row.id)"
            >
              {{ expandedIds.has(row.id) ? '收起' : '详情' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 展开详情 -->
      <template v-for="row in history" :key="'detail-' + row.id">
        <div v-if="expandedIds.has(row.id)" class="shadow-compute-detail">
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="计算类型">
              {{ computationTypeLabel(row.computation_type) }}
            </el-descriptions-item>
            <el-descriptions-item label="参数">
              <pre class="shadow-compute-json shadow-compute-json--compact">{{ formatJson(row.params) }}</pre>
            </el-descriptions-item>
          </el-descriptions>
          <el-collapse>
            <el-collapse-item title="EQCR 独立计算结果">
              <pre class="shadow-compute-json">{{ formatJson(row.result) }}</pre>
            </el-collapse-item>
            <el-collapse-item title="项目组结果快照">
              <pre class="shadow-compute-json">{{ formatJson(row.team_result_snapshot) }}</pre>
            </el-collapse-item>
          </el-collapse>
        </div>
      </template>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  eqcrApi,
  type ShadowComputeResult,
  type ShadowComputationType,
} from '@/services/eqcrService'

const props = defineProps<{
  projectId: string
}>()

// ─── 常量 ──────────────────────────────────────────────────────────────────

const COMPUTATION_TYPE_OPTIONS: { value: ShadowComputationType; label: string }[] = [
  { value: 'cfs_supplementary', label: '现金流量表补充资料' },
  { value: 'debit_credit_balance', label: '借贷平衡验证' },
  { value: 'tb_vs_report', label: '试算表 vs 报表' },
  { value: 'intercompany_elimination', label: '合并抵消验证' },
]

const COMPUTATION_TYPE_LABELS: Record<string, string> = Object.fromEntries(
  COMPUTATION_TYPE_OPTIONS.map((o) => [o.value, o.label]),
)

// ─── 状态 ──────────────────────────────────────────────────────────────────

const computationType = ref<ShadowComputationType | ''>('')
const executing = ref(false)
const rateLimited = ref(false)
const latestResult = ref<ShadowComputeResult | null>(null)
const loadingHistory = ref(false)
const history = ref<ShadowComputeResult[]>([])
const expandedIds = ref<Set<string>>(new Set())

// ─── 执行计算 ──────────────────────────────────────────────────────────────

async function executeCompute() {
  if (!computationType.value) {
    ElMessage.warning('请先选择计算类型')
    return
  }
  executing.value = true
  rateLimited.value = false
  latestResult.value = null

  try {
    const result = await eqcrApi.executeShadowCompute({
      project_id: props.projectId,
      computation_type: computationType.value,
      params: {},
    })
    latestResult.value = result
    ElMessage.success('影子计算完成')
    // 刷新历史
    await loadHistory()
  } catch (err: any) {
    const status = err?.response?.status
    if (status === 429) {
      rateLimited.value = true
    } else {
      ElMessage.error(err?.response?.data?.detail || '影子计算执行失败')
    }
  } finally {
    executing.value = false
  }
}

// ─── 加载历史 ──────────────────────────────────────────────────────────────

async function loadHistory() {
  loadingHistory.value = true
  try {
    history.value = await eqcrApi.listShadowComputations(props.projectId)
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '加载影子计算历史失败')
    history.value = []
  } finally {
    loadingHistory.value = false
  }
}

// ─── 展开/收起详情 ─────────────────────────────────────────────────────────

function toggleDetail(id: string) {
  if (expandedIds.value.has(id)) {
    expandedIds.value.delete(id)
  } else {
    expandedIds.value.add(id)
  }
  // 触发响应式更新
  expandedIds.value = new Set(expandedIds.value)
}

// ─── 辅助 ──────────────────────────────────────────────────────────────────

function computationTypeLabel(type: string): string {
  return COMPUTATION_TYPE_LABELS[type] || type
}

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return iso
  }
}

function formatJson(obj: any): string {
  if (obj === null || obj === undefined) return '—'
  try {
    return JSON.stringify(obj, null, 2)
  } catch {
    return String(obj)
  }
}

function rowClassName({ row }: { row: ShadowComputeResult }): string {
  return row.has_diff ? 'shadow-compute-row--diff' : ''
}

// ─── 初始化 ────────────────────────────────────────────────────────────────

onMounted(loadHistory)
</script>

<style scoped>
.eqcr-tab {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.eqcr-tab__section {
  border-radius: var(--gt-radius-md, 6px);
}
.eqcr-tab__section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}
.eqcr-tab__section-title {
  font-weight: 600;
  color: var(--gt-color-text, #303133);
  margin-right: 10px;
}

.shadow-compute-form {
  display: flex;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: 8px;
}

.shadow-compute-result {
  margin-top: 8px;
}

.shadow-compute-json {
  background: var(--el-fill-color-lighter, #f5f7fa);
  border-radius: 4px;
  padding: 10px 12px;
  font-size: var(--gt-font-size-xs);
  line-height: 1.5;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
  max-height: 300px;
  overflow-y: auto;
}
.shadow-compute-json--compact {
  max-height: 120px;
}

.shadow-compute-detail {
  margin: 12px 0;
  padding: 12px;
  background: var(--el-fill-color-lighter, #f5f7fa);
  border-radius: 6px;
  border-left: 3px solid var(--el-color-primary, #409eff);
}

:deep(.shadow-compute-row--diff) {
  background-color: var(--el-color-danger-light-9, #fef0f0) !important;
}
</style>
