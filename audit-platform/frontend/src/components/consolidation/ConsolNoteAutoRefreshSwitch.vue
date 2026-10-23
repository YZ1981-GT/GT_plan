<template>
  <!-- 试算表变动后自动按公式刷新合并附注（spec consol-note-header-library-and-node-reaggregate R7.1）。
       开关在后端早已有（GET/PUT .../config/consol-note-gray，只门控 consol_note_formula_refresh_handler），此前页面无入口。 -->
  <el-tooltip :content="tooltip" placement="bottom">
    <span class="gt-note-auto-refresh" data-testid="consol-note-auto-refresh">
      <span class="gt-note-auto-refresh__label">自动刷新</span>
      <el-switch
        size="small"
        :model-value="checked"
        :disabled="disabled"
        :loading="saving"
        :before-change="toggle"
        aria-label="试算表变动后自动刷新合并附注"
      />
    </span>
  </el-tooltip>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getConsolNoteAutoRefresh,
  setConsolNoteAutoRefresh,
  type ConsolNoteAutoRefreshState,
} from '@/services/consolidationApi'
import { handleApiError } from '@/utils/errorHandler'

defineOptions({ name: 'ConsolNoteAutoRefreshSwitch' })

const props = defineProps<{ projectId: string }>()

const state = ref<ConsolNoteAutoRefreshState | null>(null)
const loadError = ref('')
const saving = ref(false)
let loadSeq = 0

const WHAT_IT_DOES = '试算表、调整分录或影响附注的底稿保存后，自动按公式刷新合并附注；从单体附注拉来的数不覆盖、只标「待更新」，需要时点「🔄 重新汇总」'

const checked = computed(() => !!state.value?.effective_enabled)
const disabled = computed(() => !state.value || !!state.value.global_enabled)
const tooltip = computed(() => {
  if (loadError.value) return `自动刷新开关读取失败：${loadError.value}`
  if (!state.value) return '正在读取自动刷新开关…'
  if (state.value.global_enabled) return `全局已开启（所有项目）：${WHAT_IT_DOES}`
  return `开启后，${WHAT_IT_DOES}`
})

function errorReason(err: any): string {
  const detail = err?.response?.data?.detail ?? err?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail.trim()
  if (detail && typeof detail === 'object' && typeof detail.message === 'string') return detail.message
  return err?.response?.status ? `请求失败（${err.response.status}）` : '网络不通'
}

async function load(): Promise<void> {
  const seq = ++loadSeq
  state.value = null
  loadError.value = ''
  if (!props.projectId) return
  try {
    const got = await getConsolNoteAutoRefresh(props.projectId)
    if (seq === loadSeq) state.value = got
  } catch (err: any) {
    if (seq === loadSeq) loadError.value = errorReason(err)
  }
}

/**
 * el-switch 的 before-change：在这里发请求，开关显示只跟后端返回的状态走 —— 成功按响应更新、失败保持原状并提示原因；
 * 恒返回 false，不让 el-switch 自己翻转（显示值由 state 决定）。
 */
async function toggle(): Promise<boolean> {
  if (!state.value || state.value.global_enabled || !props.projectId) return false
  const next = !state.value.project_enabled
  const projectId = props.projectId
  saving.value = true
  try {
    const saved = await setConsolNoteAutoRefresh(projectId, next)
    if (projectId === props.projectId) { // 等待期间换了项目：结果不属于当前页
      state.value = saved
      ElMessage.success(next ? '已开启自动刷新：试算表变动后自动按公式刷新本项目合并附注' : '已关闭自动刷新')
    }
  } catch (err: any) {
    handleApiError(err, '修改自动刷新开关')
  } finally {
    saving.value = false
  }
  return false
}

onMounted(load)
watch(() => props.projectId, load)
</script>

<style scoped>
.gt-note-auto-refresh {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin: 0 4px;
}
.gt-note-auto-refresh__label {
  font-size: 12px;
  color: var(--gt-color-text-secondary, #606266);
}
</style>
