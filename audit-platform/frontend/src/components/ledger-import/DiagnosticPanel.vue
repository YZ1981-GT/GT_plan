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
            <el-tag :type="err.severity === 'fatal' ? 'danger' : err.severity === 'blocking' ? 'warning' : 'info'" size="small">
              {{ err.code }}
            </el-tag>
            <span>{{ err.message }}</span>
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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { CircleCheck, CircleClose, Loading } from '@element-plus/icons-vue'

// ─── Props ──────────────────────────────────────────────────────────────────

const props = defineProps<{
  jobId: string
  projectId: string
}>()

// ─── Types ──────────────────────────────────────────────────────────────────

interface DiagnosticData {
  detection_evidence: Record<string, unknown> | null
  adapter_used: string | null
  adapter_score: number | null
  engine_version: string | null
  duration_ms: number | null
  errors: Array<{ code: string; severity: string; message: string }>
  progress_history: Array<{ phase: string; timestamp: string; message?: string }>
}

// ─── State ──────────────────────────────────────────────────────────────────

const expandedPanels = ref<string[]>(['evidence'])
const diagnostics = ref<DiagnosticData | null>(null)
const loading = ref(false)

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
    )
    diagnostics.value = res as DiagnosticData
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
  font-size: 13px;
  min-width: 180px;
}

.evidence-value {
  font-size: 12px;
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
  font-size: 13px;
}

.history-phase {
  font-weight: 500;
}

.history-message {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.loading-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: rgba(255, 255, 255, 0.8);
  font-size: 14px;
}
</style>
