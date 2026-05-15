<script setup lang="ts">
/**
 * 公式来源穿透展示抽屉
 * 右键菜单"查看来源"→侧面板穿透展示
 */
import { ref, computed } from 'vue'
import { api } from '@/services/apiProxy'

interface ProvenanceEntry {
  source: string
  source_ref: string
  value: number | string | null
  filled_at: string
  formula_type: string
  raw_args: string
  _prev?: ProvenanceEntry
}

const props = defineProps<{
  projectId: string
  wpId: string
}>()

const visible = ref(false)
const loading = ref(false)
const cellRef = ref('')
const sheetName = ref('')
const provenance = ref<ProvenanceEntry | null>(null)

const sourceLabels: Record<string, string> = {
  trial_balance: '试算平衡表',
  workpaper_ref: '其他底稿',
  ledger: '序时账',
  aux_balance: '辅助余额表',
  prior_year: '上年底稿',
  adjustment: '调整分录',
  disclosure_note: '附注',
  formula: '公式计算',
  manual: '手动输入',
  ocr: 'OCR 识别',
}

const sourceIcon: Record<string, string> = {
  trial_balance: '📊',
  workpaper_ref: '📋',
  ledger: '📒',
  aux_balance: '📑',
  prior_year: '📅',
  adjustment: '✏️',
  disclosure_note: '📝',
  formula: '🔢',
  manual: '✍️',
  ocr: '📷',
}

const title = computed(() => `来源追踪: ${sheetName.value}!${cellRef.value}`)

async function open(sheet: string, cell: string) {
  sheetName.value = sheet
  cellRef.value = cell
  visible.value = true
  loading.value = true

  try {
    const data = await api.get(
      `/api/projects/${props.projectId}/workpapers/${props.wpId}/provenance/${sheet}/${cell}`
    )
    provenance.value = data || null
  } catch {
    provenance.value = null
  } finally {
    loading.value = false
  }
}

function close() {
  visible.value = false
  provenance.value = null
}

defineExpose({ open, close })
</script>

<template>
  <el-drawer
    v-model="visible"
    :title="title"
    direction="rtl"
    size="380px"
    :destroy-on-close="true"
  >
    <div v-loading="loading" class="source-drawer-content">
      <template v-if="provenance">
        <!-- 当前来源 -->
        <div class="source-card current">
          <div class="source-header">
            <span class="source-icon">{{ sourceIcon[provenance.source] || '📌' }}</span>
            <span class="source-label">{{ sourceLabels[provenance.source] || provenance.source }}</span>
            <el-tag size="small" type="success">当前</el-tag>
          </div>
          <div class="source-detail">
            <div class="detail-row">
              <span class="detail-label">公式:</span>
              <span class="detail-value mono">={{ provenance.formula_type }}({{ provenance.raw_args }})</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">值:</span>
              <span class="detail-value amount">
                {{ provenance.value != null ? (typeof provenance.value === 'number' ? provenance.value.toLocaleString() : provenance.value) : '—' }}
              </span>
            </div>
            <div v-if="provenance.source_ref" class="detail-row">
              <span class="detail-label">引用:</span>
              <span class="detail-value">{{ provenance.source_ref }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">时间:</span>
              <span class="detail-value time">{{ provenance.filled_at }}</span>
            </div>
          </div>
        </div>

        <!-- 历史来源 -->
        <div v-if="provenance._prev" class="source-card previous">
          <div class="source-header">
            <span class="source-icon">{{ sourceIcon[provenance._prev.source] || '📌' }}</span>
            <span class="source-label">{{ sourceLabels[provenance._prev.source] || provenance._prev.source }}</span>
            <el-tag size="small" type="info">上一次</el-tag>
          </div>
          <div class="source-detail">
            <div class="detail-row">
              <span class="detail-label">值:</span>
              <span class="detail-value amount">
                {{ provenance._prev.value != null ? provenance._prev.value.toLocaleString() : '—' }}
              </span>
            </div>
            <div class="detail-row">
              <span class="detail-label">时间:</span>
              <span class="detail-value time">{{ provenance._prev.filled_at }}</span>
            </div>
          </div>
        </div>
      </template>

      <el-empty v-else-if="!loading" description="暂无来源记录" />
    </div>
  </el-drawer>
</template>

<style scoped>
.source-drawer-content {
  padding: 0 4px;
}

.source-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 12px;
}

.source-card.current {
  border-left: 3px solid var(--el-color-success);
}

.source-card.previous {
  border-left: 3px solid var(--el-border-color);
  opacity: 0.75;
}

.source-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.source-icon { font-size: 16px; }
.source-label { font-weight: 500; font-size: 14px; }

.source-detail {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 13px;
}

.detail-label {
  color: var(--el-text-color-secondary);
  min-width: 40px;
  flex-shrink: 0;
}

.detail-value {
  color: var(--el-text-color-primary);
  word-break: break-all;
}

.detail-value.mono {
  font-family: 'Consolas', monospace;
  font-size: 12px;
}

.detail-value.amount {
  font-family: 'Arial Narrow', sans-serif;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  color: var(--el-color-primary);
}

.detail-value.time {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
</style>
