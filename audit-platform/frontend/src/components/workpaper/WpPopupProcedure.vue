<script setup lang="ts">
/**
 * WpPopupProcedure — A1-17 对应数据程序表
 *
 * 3 个程序步骤卡片：
 * - 是否适用（下拉 Y/N）
 * - 执行说明（输入框）
 * - 完成状态标记
 * 数据保存到 checklist_responses（item_id: A1-17-001~003）
 * 自动保存 debounce 2s
 */
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

const props = defineProps<{
  wpCode: string
  wpId?: string
  projectId?: string
}>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
}>()

// 3 procedure steps for A1-17
const STEPS = [
  {
    id: 'A1-17-001',
    seq: 1,
    content: '如果以前针对上期财务报表发了保留意见、无法表示意见或否定意见，且导致非无保留意见的事项仍未解决，对本期财务报表发表非无保留意见。在审计报告的导致非无保留意见的事项段如果未解决事项对本期数据的影响或可能的影响是重大的，在导致非无保留意见事项段中同时提及本期数据和对应数据。',
  },
  {
    id: 'A1-17-002',
    seq: 2,
    content: '如果已经获取上期财务报表存在重大错报的审计证据，而以前对该财务报表发表了无保留意见，且对应数据未经适当重述或恰当披露，就包括在财务报表中的对应数据，在审计报告中对本期财务报表发表保留意见或否定意见。',
  },
  {
    id: 'A1-17-003',
    seq: 3,
    content: '如果上期财务报表未经审计，在审计报告的其他事项段中说明对应数据未经审计。',
  },
]

interface StepState {
  applicable: string | null  // 'Y' or 'N' or null
  remark: string
}

const stepStates = ref<Record<string, StepState>>({})
const loading = ref(false)
const saveTimer = ref<ReturnType<typeof setTimeout> | null>(null)

// Initialize states
function initStates() {
  for (const step of STEPS) {
    if (!stepStates.value[step.id]) {
      stepStates.value[step.id] = { applicable: null, remark: '' }
    }
  }
}

// Load existing data
async function loadData() {
  if (!props.wpId) return
  loading.value = true
  try {
    const res = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const responses = Array.isArray(res) ? res : (res?.data ?? [])
    for (const r of responses) {
      if (r.item_id?.startsWith('A1-17-')) {
        stepStates.value[r.item_id] = {
          applicable: r.conclusion,
          remark: r.remark || '',
        }
      }
    }
  } catch { /* ignore load errors */ }
  finally { loading.value = false }
}

// Save with debounce
function scheduleSave() {
  if (saveTimer.value) clearTimeout(saveTimer.value)
  saveTimer.value = setTimeout(doSave, 2000)
}

async function doSave() {
  if (!props.wpId || !props.projectId) return
  const items = STEPS.map(step => ({
    item_id: step.id,
    conclusion: stepStates.value[step.id]?.applicable || null,
    remark: stepStates.value[step.id]?.remark || null,
    wp_ref: null,
  }))
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId,
      items,
    })
    emit('save')
    // Check if all completed
    const allDone = STEPS.every(s => stepStates.value[s.id]?.applicable)
    if (allDone) emit('completed')
  } catch (err: any) {
    const msg = err?.message || ''
    if (msg !== 'canceled' && err?.code !== 'ERR_CANCELED') {
      ElMessage.error('保存失败')
    }
  }
}

function updateApplicable(id: string, val: string) {
  stepStates.value[id].applicable = val || null
  scheduleSave()
}

function updateRemark(id: string, val: string) {
  stepStates.value[id].remark = val
  scheduleSave()
}

onMounted(() => {
  initStates()
  loadData()
})

onBeforeUnmount(() => {
  // Flush pending save on unmount
  if (saveTimer.value) {
    clearTimeout(saveTimer.value)
    doSave()
  }
})
</script>

<template>
  <div class="wp-popup-procedure" v-loading="loading">
    <div
      v-for="step in STEPS"
      :key="step.id"
      class="procedure-step"
      :class="{ 'is-done': stepStates[step.id]?.applicable }"
    >
      <div class="step-header">
        <span class="step-seq">{{ step.seq }}</span>
        <span class="step-status" v-if="stepStates[step.id]?.applicable">✓</span>
      </div>
      <div class="step-content">{{ step.content }}</div>
      <div class="step-controls">
        <div class="step-field">
          <span class="step-label">是否适用：</span>
          <el-select
            :model-value="stepStates[step.id]?.applicable || ''"
            size="small"
            placeholder="请选择"
            style="width: 100px"
            @change="(val: string) => updateApplicable(step.id, val)"
          >
            <el-option label="是" value="Y" />
            <el-option label="否" value="N" />
          </el-select>
        </div>
        <div class="step-field step-field--remark">
          <span class="step-label">执行说明：</span>
          <el-input
            :model-value="stepStates[step.id]?.remark || ''"
            size="small"
            placeholder="填写执行情况说明"
            style="flex: 1"
            @input="(val: string) => updateRemark(step.id, val)"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wp-popup-procedure {
  padding: 8px 0;
}

.procedure-step {
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 14px 16px;
  margin-bottom: 12px;
  transition: border-color 0.2s, background-color 0.2s;
}

.procedure-step:last-child {
  margin-bottom: 0;
}

.procedure-step.is-done {
  border-color: #d8b8ee;
  background-color: #f4f0fa;
}

.step-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.step-seq {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background-color: #4b2d77;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}

.procedure-step.is-done .step-seq {
  background-color: #4b2d77;
}

.step-status {
  color: #4b2d77;
  font-weight: 700;
  font-size: 14px;
}

.step-content {
  font-size: var(--wp-font-size, 13px);
  line-height: 1.6;
  color: #303133;
  margin-bottom: 10px;
}

.step-controls {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.step-field {
  display: flex;
  align-items: center;
  gap: 4px;
}

.step-field--remark {
  flex: 1;
  min-width: 200px;
}

.step-label {
  font-size: 12px;
  color: #606266;
  white-space: nowrap;
}
</style>
