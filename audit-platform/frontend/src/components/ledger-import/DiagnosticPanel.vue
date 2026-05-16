<template>
  <div class="diagnostic-panel">
    <el-collapse v-model="expandedPanels">
      <!-- 识别决策树 -->
      <el-collapse-item title="识别决策树" name="evidence">
        <div v-if="diagnostics?.detection_evidence" class="evidence-tree">
          <div
            v-for="(value, key) in diagnostics.detection_evidence"
            :key="String(key)"
            class="evidence-row"
          >
            <el-icon :class="value ? 'hit' : 'miss'">
              <component :is="value ? CircleCheck : CircleClose" />
            </el-icon>
            <span class="evidence-key">{{ formatEvidenceKey(String(key)) }}</span>
            <span class="evidence-value">{{ formatEvidenceValue(value) }}</span>
          </div>
        </div>
        <el-empty v-else description="暂无识别决策数据" :image-size="60" />
      </el-collapse-item>

      <!-- 适配器信息 -->
      <el-collapse-item title="适配器信息" name="adapter">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="适配器 ID">
            {{ diagnostics?.adapter_used || '未命中' }}
          </el-descriptions-item>
          <el-descriptions-item label="匹配度">
            {{ diagnostics?.adapter_score ? `${(diagnostics.adapter_score * 100).toFixed(0)}%` : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="引擎版本">
            {{ diagnostics?.engine_version || 'v2' }}
          </el-descriptions-item>
          <el-descriptions-item label="处理耗时">
            {{ diagnostics?.duration_ms ? `${diagnostics.duration_ms}ms` : '-' }}
          </el-descriptions-item>
        </el-descriptions>
      </el-collapse-item>

      <!-- 错误详情 -->
      <el-collapse-item title="错误详情" name="errors">
        <div v-if="diagnostics?.errors?.length" class="error-list-compact">
          <div v-for="(err, idx) in diagnostics.errors" :key="idx" class="error-compact">
            <el-tag
              :type="err.severity === 'fatal' ? 'danger' : err.severity === 'blocking' ? 'warning' : 'info'"
              size="small"
              class="code-link"
              @click="goToRule(err.code)"
            >
              {{ err.code }}
            </el-tag>
            <span>{{ err.message }}</span>
            <!-- 8.14: 查看明细按钮（drill_down） -->
            <el-button
              v-if="err.location?.drill_down"
              link
              type="primary"
              size="small"
              @click="onDrillDown(err)"
            >
              查看明细 ({{ err.location.drill_down.expected_count || '?' }}行)
            </el-button>
          </div>
        </div>
        <el-empty v-else description="无错误" :image-size="60" />
      </el-collapse-item>

      <!-- 进度历史 -->
      <el-collapse-item title="进度历史" name="history">
        <el-timeline v-if="diagnostics?.progress_history?.length">
          <el-timeline-item
            v-for="(item, idx) in diagnostics.progress_history"
            :key="idx"
            :timestamp="item.timestamp"
            placement="top"
          >
            <span class="history-phase">{{ item.phase }}</span>
            <span v-if="item.message" class="history-message">— {{ item.message }}</span>
          </el-timeline-item>
        </el-timeline>
        <el-empty v-else description="暂无进度记录" :image-size="60" />
      </el-collapse-item>
    </el-collapse>

    <!-- 加载状态 -->
    <div v-if="loading" class="loading-overlay">
      <el-icon class="is-loading"><Loading /></el-icon>
      <span>加载诊断数据...</span>
    </div>

    <!-- 8.14: LedgerPenetration 抽屉（通过 iframe 或路由跳转） -->
    <el-drawer
      v-model="drillDrawerVisible"
      title="明细穿透"
      size="80%"
      direction="rtl"
      destroy-on-close
    >
      <div class="drill-down-content">
        <p class="drill-info">
          正在查看科目明细凭证，筛选条件：
        </p>
        <el-descriptions :column="2" border size="small" v-if="drillDownFilter">
          <el-descriptions-item
            v-for="(val, key) in drillDownFilter"
            :key="String(key)"
            :label="String(key)"
          >
            {{ val }}
          </el-descriptions-item>
        </el-descriptions>
        <el-button
          type="primary"
          style="margin-top: 16px"
          @click="openPenetrationPage"
        >
          在新页面打开穿透视图
        </el-button>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { CircleCheck, CircleClose, Loading } from '@element-plus/icons-vue'

const router = useRouter()

// ─── Props ──────────────────────────────────────────────────────────────────

const props = defineProps<{
  jobId: string
  projectId: string
}>()

// ─── Types ──────────────────────────────────────────────────────────────────

interface DrillDown {
  target?: string
  filter?: Record<string, any>
  sample_ids?: string[]
  expected_count?: number
}

interface DiagnosticError {
  code: string
  severity: string
  message: string
  location?: {
    drill_down?: DrillDown
    [key: string]: any
  }
}

interface DiagnosticData {
  detection_evidence: Record<string, unknown> | null
  adapter_used: string | null
  adapter_score: number | null
  engine_version: string | null
  duration_ms: number | null
  errors: DiagnosticError[]
  progress_history: Array<{ phase: string; timestamp: string; message?: string }>
  // 后端实际返回的字段
  result_summary?: {
    findings?: DiagnosticError[]
    blocking_findings?: DiagnosticError[]
    [key: string]: any
  } | null
  current_phase?: string | null
  status?: string
}

// ─── State ──────────────────────────────────────────────────────────────────

const expandedPanels = ref<string[]>(['evidence'])
const diagnostics = ref<DiagnosticData | null>(null)
const loading = ref(false)

// ─── Drill Down (8.14) ──────────────────────────────────────────────────────

const drillDrawerVisible = ref(false)
const drillDownFilter = ref<Record<string, any> | null>(null)

function onDrillDown(err: DiagnosticError) {
  if (!err.location?.drill_down?.filter) return
  drillDownFilter.value = err.location.drill_down.filter
  drillDrawerVisible.value = true
}

function goToRule(code: string) {
  const route = router.resolve({ path: '/ledger-import/validation-rules', hash: `#${code}` })
  window.open(route.href, '_blank')
}

function openPenetrationPage() {
  const query: Record<string, string> = {}
  if (drillDownFilter.value) {
    Object.entries(drillDownFilter.value).forEach(([k, v]) => {
      if (v != null) query[k] = String(v)
    })
  }
  router.push({ path: `/projects/${props.projectId}/ledger`, query })
  drillDrawerVisible.value = false
}

// ─── Methods ────────────────────────────────────────────────────────────────

function formatEvidenceKey(key: string): string {
  // 将 snake_case 转为可读文本
  const map: Record<string, string> = {
    level1_sheetname: 'Level 1 — Sheet 名匹配',
    level2_headers: 'Level 2 — 表头特征匹配',
    level3_content: 'Level 3 — 内容样本识别',
    adapter_match: '适配器匹配',
    key_columns_found: '关键列识别',
    recommended_columns_found: '次关键列识别',
  }
  return map[key] || key.replace(/_/g, ' ')
}

function formatEvidenceValue(value: unknown): string {
  if (typeof value === 'boolean') return value ? '✓ 命中' : '✗ 未命中'
  if (Array.isArray(value)) return value.join(', ')
  if (typeof value === 'object' && value !== null) return JSON.stringify(value, null, 2)
  return String(value)
}

async function fetchDiagnostics() {
  loading.value = true
  try {
    const { api } = await import('@/services/apiProxy')
    const res = await api.get(
      `/api/projects/${props.projectId}/ledger-import/jobs/${props.jobId}/diagnostics`
    ) as any
    // 后端返回 result_summary.findings / blocking_findings，前端统一到 errors 数组
    const summary = res?.result_summary || {}
    const findings: DiagnosticError[] = [
      ...(summary.blocking_findings || []),
      ...(summary.findings || []),
    ]
    diagnostics.value = {
      detection_evidence: res?.detection_result?.detection_evidence || res?.options?.detection_evidence || null,
      adapter_used: res?.adapter_used || null,
      adapter_score: res?.options?.adapter_score || null,
      engine_version: res?.options?.engine_version || 'v2',
      duration_ms: summary.duration_ms || null,
      errors: findings,
      progress_history: summary.progress_history || [],
      result_summary: summary,
      current_phase: res?.current_phase,
      status: res?.status,
    }
  } catch (err) {
    console.error('获取诊断数据失败', err)
  } finally {
    loading.value = false
  }
}

// ─── Lifecycle ──────────────────────────────────────────────────────────────

onMounted(() => {
  fetchDiagnostics()
})
</script>

<style scoped>
.diagnostic-panel {
  position: relative;
}

.evidence-tree {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.evidence-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border-radius: 4px;
  background: var(--el-fill-color-lighter);
}

.evidence-row .hit {
  color: var(--el-color-success);
}

.evidence-row .miss {
  color: var(--el-color-danger);
}

.evidence-key {
  font-size: var(--gt-font-size-sm);
  min-width: 180px;
}

.evidence-value {
  font-size: var(--gt-font-size-xs);
  color: var(--el-text-color-secondary);
  word-break: break-all;
}

.error-list-compact {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.error-compact {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--gt-font-size-sm);
}

.error-compact .code-link {
  cursor: pointer;
  transition: opacity 0.2s;
}

.error-compact .code-link:hover {
  opacity: 0.7;
  text-decoration: underline;
}

.history-phase {
  font-weight: 500;
}

.history-message {
  color: var(--el-text-color-secondary);
  font-size: var(--gt-font-size-xs);
}

.loading-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: rgba(255, 255, 255, 0.8);
  font-size: var(--gt-font-size-sm);
}

.drill-down-content {
  padding: 16px;
}

.drill-info {
  margin: 0 0 12px;
  font-size: var(--gt-font-size-sm);
  color: var(--el-text-color-secondary);
}
</style>
