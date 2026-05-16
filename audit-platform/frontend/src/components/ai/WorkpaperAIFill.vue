<template>
  <div class="gt-workpaper-ai-fill">
    <div class="panel-header">
      <h3>🤖 AI 底稿填充</h3>
      <div class="fill-controls">
        <select v-model="fillMode" class="mode-select">
          <option value="auto">自动填充</option>
          <option value="semi">半自动填充</option>
        </select>
        <button class="btn-primary" @click="startFill" :disabled="filling">
          {{ filling ? '填充中...' : '🚀 开始AI填充' }}
        </button>
      </div>
    </div>

    <!-- 填充进度 -->
    <div v-if="filling" class="fill-progress">
      <div class="progress-header">
        <span>正在填充：{{ currentWorkpaper || '初始化...' }}</span>
        <span>{{ fillProgress }}%</span>
      </div>
      <div class="progress-bar-wrap">
        <div class="progress-bar" :style="{ width: fillProgress + '%' }"></div>
      </div>
      <div class="progress-steps">
        <span
          v-for="step in fillSteps"
          :key="step.label"
          :class="['step', step.status]"
        >
          {{ step.status === 'done' ? '✅' : step.status === 'active' ? '🔄' : '⏳' }}
          {{ step.label }}
        </span>
      </div>
    </div>

    <!-- 填充结果 -->
    <div v-if="fillResults.length > 0" class="fill-results">
      <div class="results-summary">
        <span class="summary-badge success">✅ 成功 {{ successCount }} 项</span>
        <span class="summary-badge warning">⚠️ 需审核 {{ pendingCount }} 项</span>
        <span class="summary-badge error">❌ 失败 {{ failedCount }} 项</span>
      </div>
      <div
        v-for="result in fillResults"
        :key="result.id"
        class="result-card"
        :class="result.status"
      >
        <div class="result-header">
          <span class="result-label">{{ result.label }}</span>
          <span :class="['status-badge', result.status]">{{ result.statusLabel }}</span>
        </div>
        <div class="result-content">
          <div class="content-before" v-if="result.original !== undefined">
            <span class="content-label">原值：</span>
            <span class="content-value old">{{ result.original }}</span>
          </div>
          <div class="content-after">
            <span class="content-label">AI填入：</span>
            <span class="content-value new">{{ result.value }}</span>
          </div>
        </div>
        <div class="result-meta">
          <span class="confidence" :class="confidenceClass(result.confidence)">
            置信度：{{ result.confidence ? (result.confidence * 100).toFixed(0) + '%' : 'N/A' }}
          </span>
          <span class="data-source" v-if="result.source">📚 来源：{{ result.source }}</span>
        </div>
        <div v-if="result.status === 'pending'" class="result-actions">
          <button class="btn-accept" @click="acceptFill(result)">✅ 采纳</button>
          <button class="btn-reject" @click="rejectFill(result)">❌ 拒绝</button>
          <button class="btn-edit" @click="editFill(result)">✏️ 手动修改</button>
        </div>
        <div v-if="result.editing" class="edit-area">
          <textarea v-model="result.editValue" rows="3" class="edit-textarea"></textarea>
          <div class="edit-actions">
            <button class="btn-save" @click="saveEdit(result)">💾 保存</button>
            <button class="btn-cancel" @click="result.editing = false">取消</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 批量确认 -->
    <div v-if="fillResults.some(r => r.status === 'pending')" class="batch-actions">
      <button class="btn-batch-accept" @click="acceptAllPending">✅ 采纳全部</button>
      <button class="btn-regenerate" @click="regeneratePending">🔄 重新生成</button>
    </div>

    <!-- 无结果提示 -->
    <div v-if="!filling && fillResults.length === 0" class="empty-state">
      <div class="empty-icon">🤖</div>
      <p>点击「开始AI填充」，AI将根据项目数据自动填写底稿字段</p>
      <p class="empty-hint">支持：试算表数据、调整分录、往来账龄分析、截止测试等</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { workpaperFillApi } from '@/api'

const props = defineProps({
  projectId: { type: String, required: true },
  workpaperId: { type: String, default: null }
})

const fillMode = ref('semi')
const filling = ref(false)
const fillProgress = ref(0)
const fillResults = ref([])
const currentWorkpaper = ref('')
const fillSteps = ref([])

const successCount = computed(() => fillResults.value.filter(r => r.status === 'accepted').length)
const pendingCount = computed(() => fillResults.value.filter(r => r.status === 'pending').length)
const failedCount = computed(() => fillResults.value.filter(r => r.status === 'rejected').length)

async function startFill() {
  filling.value = true
  fillResults.value = []
  fillProgress.value = 5
  currentWorkpaper.value = '准备数据...'
  fillSteps.value = [
    { label: '数据采集', status: 'active' },
    { label: 'AI分析', status: 'pending' },
    { label: '填充底稿', status: 'pending' },
  ]

  try {
    const res = await workpaperFillApi.startFill({
      project_id: props.projectId,
      workpaper_id: props.workpaperId,
      mode: fillMode.value
    }, (p) => { fillProgress.value = p })

    fillResults.value = res.data || []
    fillProgress.value = 100
    fillSteps.value = fillSteps.value.map(s => ({ ...s, status: 'done' }))
  } catch (e) {
    console.error(e)
  } finally {
    filling.value = false
  }
}

async function acceptFill(result) {
  await workpaperFillApi.confirmFill(result.id, { accepted: true, value: result.value })
  result.status = 'accepted'
  result.statusLabel = '已采纳'
}

async function rejectFill(result) {
  await workpaperFillApi.confirmFill(result.id, { accepted: false })
  result.status = 'rejected'
  result.statusLabel = '已拒绝'
}

function editFill(result) {
  result.editValue = result.value
  result.editing = true
}

async function saveEdit(result) {
  await workpaperFillApi.confirmFill(result.id, { accepted: true, value: result.editValue })
  result.value = result.editValue
  result.status = 'accepted'
  result.statusLabel = '已采纳（手动修改）'
  result.editing = false
}

async function acceptAllPending() {
  const pending = fillResults.value.filter(r => r.status === 'pending')
  for (const p of pending) {
    await acceptFill(p)
  }
}

async function regeneratePending() {
  // 重新生成pending项目
  const pending = fillResults.value.filter(r => r.status === 'pending')
  try {
    const res = await workpaperFillApi.regenerate({
      project_id: props.projectId,
      workpaper_id: props.workpaperId,
      item_ids: pending.map(p => p.id)
    })
    // 更新结果
    for (const item of res.data || []) {
      const idx = fillResults.value.findIndex(r => r.id === item.id)
      if (idx >= 0) fillResults.value[idx] = item
    }
  } catch (e) {
    console.error(e)
  }
}

function confidenceClass(c) {
  if (!c) return ''
  if (c < 0.7) return 'low'
  if (c < 0.85) return 'medium'
  return 'high'
}
</script>

<style scoped>
.gt-workpaper-ai-fill { padding: 16px; }
.panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.panel-header h3 { margin: 0; font-size: var(--gt-font-size-md); }
.fill-controls { display: flex; gap: 8px; align-items: center; }

.mode-select { padding: 5px 10px; border: 1px solid #ddd; border-radius: 6px; font-size: var(--gt-font-size-xs); }
.btn-primary { padding: 6px 16px; background: var(--gt-color-primary); color: var(--gt-color-text-inverse); border: none; border-radius: 6px; cursor: pointer; font-size: var(--gt-font-size-sm); }
.btn-primary:disabled { background: var(--gt-color-border); cursor: not-allowed; }

.fill-progress { margin-bottom: 16px; }
.progress-header { display: flex; justify-content: space-between; font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary); margin-bottom: 6px; }
.progress-bar-wrap { height: 8px; background: var(--gt-color-border-lighter); border-radius: 4px; overflow: hidden; }
.progress-bar { height: 100%; background: linear-gradient(90deg, #4b2d77, #7c3aed); transition: width 0.4s; }
.progress-steps { display: flex; gap: 8px; margin-top: 8px; }
.step { font-size: var(--gt-font-size-xs); padding: 2px 8px; border-radius: 4px; }
.step.done { color: var(--gt-color-success); }
.step.active { color: #4b2d77; background: rgba(75,45,119,0.1); }
.step.pending { color: var(--gt-color-text-tertiary); }

.results-summary { display: flex; gap: 8px; margin-bottom: 12px; }
.summary-badge { padding: 3px 10px; border-radius: 4px; font-size: var(--gt-font-size-xs); font-weight: 600; }
.summary-badge.success { background: var(--gt-bg-success); color: var(--gt-color-success); }
.summary-badge.warning { background: var(--gt-color-wheat-light); color: var(--gt-color-wheat); }
.summary-badge.error { background: var(--gt-bg-danger); color: var(--gt-color-coral); }

.result-card { border: 1px solid #eee; border-radius: 8px; padding: 12px; margin-bottom: 8px; }
.result-card.pending { border-color: #faad14; background: var(--gt-color-wheat-light); }
.result-card.accepted { border-color: #52c41a; background: var(--gt-bg-success); }
.result-card.rejected { border-color: #ff4d4f; background: var(--gt-bg-danger); opacity: 0.7; }

.result-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.result-label { font-weight: 600; font-size: var(--gt-font-size-sm); }
.status-badge { font-size: var(--gt-font-size-xs); padding: 2px 6px; border-radius: 4px; }
.status-badge.pending { background: var(--gt-color-wheat-light); color: var(--gt-color-wheat); }
.status-badge.accepted { background: var(--gt-bg-success); color: var(--gt-color-success); }
.status-badge.rejected { background: var(--gt-bg-danger); color: var(--gt-color-coral); }

.result-content { display: flex; gap: 16px; margin-bottom: 6px; }
.content-label { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); }
.content-value { font-size: var(--gt-font-size-sm); font-weight: 500; }
.content-value.old { text-decoration: line-through; color: var(--gt-color-text-tertiary); }
.content-value.new { color: var(--gt-color-primary); }

.result-meta { display: flex; gap: 12px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-bottom: 8px; }
.confidence.low { color: var(--gt-color-coral); }
.confidence.medium { color: var(--gt-color-wheat); }
.confidence.high { color: var(--gt-color-success); }

.result-actions { display: flex; gap: 6px; }
.btn-accept, .btn-reject, .btn-edit {
  padding: 3px 10px;
  border-radius: 4px;
  border: none;
  cursor: pointer;
  font-size: var(--gt-font-size-xs);
}
.btn-accept { background: var(--gt-color-success); color: var(--gt-color-text-inverse); }
.btn-reject { background: var(--gt-color-bg); color: var(--gt-color-text-secondary); }
.btn-edit { background: var(--gt-color-bg-white); border: 1px solid #ddd; }

.edit-area { margin-top: 8px; }
.edit-textarea { width: 100%; padding: 6px 8px; border: 1px solid #4b2d77; border-radius: 6px; font-size: var(--gt-font-size-sm); resize: vertical; }
.edit-actions { display: flex; gap: 6px; margin-top: 6px; justify-content: flex-end; }
.btn-save, .btn-cancel { padding: 3px 10px; border-radius: 4px; cursor: pointer; font-size: var(--gt-font-size-xs); }
.btn-save { background: var(--gt-color-primary); color: var(--gt-color-text-inverse); border: none; }
.btn-cancel { background: var(--gt-color-bg); color: var(--gt-color-text-secondary); border: 1px solid #ddd; }

.batch-actions { display: flex; gap: 8px; margin-top: 12px; }
.btn-batch-accept { padding: 6px 16px; background: var(--gt-color-success); color: var(--gt-color-text-inverse); border: none; border-radius: 6px; cursor: pointer; font-size: var(--gt-font-size-xs); }
.btn-regenerate { padding: 6px 16px; background: var(--gt-color-bg-white); color: var(--gt-color-primary); border: 1px solid #4b2d77; border-radius: 6px; cursor: pointer; font-size: var(--gt-font-size-xs); }

.empty-state { text-align: center; padding: 40px 20px; color: var(--gt-color-text-secondary); }
.empty-icon { font-size: 40px /* allow-px: special */; margin-bottom: 12px; }
.empty-hint { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-top: 8px; }
</style>
