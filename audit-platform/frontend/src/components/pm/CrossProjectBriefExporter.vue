<template>
  <div class="cross-brief-exporter">
    <div class="exporter-header">
      <span class="exporter-title">📄 跨项目合并简报</span>
      <div class="exporter-actions">
        <el-switch
          v-model="useAi"
          active-text="AI 总结"
          inactive-text=""
          size="small"
          class="ai-switch"
        />
        <el-button
          type="primary"
          size="small"
          :disabled="selectedIds.length === 0 || exporting"
          :loading="exporting"
          @click="startExport"
        >
          导出合并简报（{{ selectedIds.length }}）
        </el-button>
      </div>
    </div>

    <div class="exporter-select">
      <el-checkbox
        v-model="selectAll"
        :indeterminate="isIndeterminate"
        @change="handleSelectAll"
        class="select-all-checkbox"
      >
        全选
      </el-checkbox>
      <el-checkbox-group v-model="selectedIds" class="project-checkbox-group">
        <el-checkbox
          v-for="proj in projects"
          :key="proj.id"
          :value="proj.id"
          class="project-checkbox-item"
        >
          {{ proj.name }}
        </el-checkbox>
      </el-checkbox-group>
    </div>

    <!-- 导出进度 -->
    <div v-if="exporting" class="exporter-progress">
      <el-progress
        :percentage="progressPercent"
        :status="progressStatus"
        :stroke-width="6"
      />
      <span class="progress-text">{{ progressText }}</span>
    </div>

    <!-- 导出失败提示 -->
    <div v-if="exportError" class="exporter-error">
      <el-alert :title="exportError" type="error" show-icon :closable="true" @close="exportError = ''" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onBeforeUnmount } from 'vue'
import { api } from '@/services/apiProxy'
import { ElMessage } from 'element-plus'

export interface BriefProject {
  id: string
  name: string
}

const props = defineProps<{
  projects: BriefProject[]
}>()

// ── 选择状态 ──
const selectedIds = ref<string[]>([])
const selectAll = ref(false)
const isIndeterminate = ref(false)

function handleSelectAll(val: boolean | string | number) {
  const checked = !!val
  selectedIds.value = checked ? props.projects.map(p => p.id) : []
  isIndeterminate.value = false
}

// 监听 checkbox group 变化更新全选状态
import { watch } from 'vue'
watch(selectedIds, (val) => {
  const total = props.projects.length
  selectAll.value = val.length === total && total > 0
  isIndeterminate.value = val.length > 0 && val.length < total
})

// ── 导出状态 ──
const useAi = ref(false)
const exporting = ref(false)
const exportError = ref('')
const progressTotal = ref(0)
const progressDone = ref(0)
let pollTimer: ReturnType<typeof setInterval> | null = null

const progressPercent = computed(() => {
  if (progressTotal.value === 0) return 0
  return Math.round((progressDone.value / progressTotal.value) * 100)
})

const progressStatus = computed(() => {
  if (exportError.value) return 'exception'
  if (progressPercent.value >= 100) return 'success'
  return undefined
})

const progressText = computed(() => {
  if (progressTotal.value === 0) return '正在提交任务...'
  return `${progressDone.value} / ${progressTotal.value} 个项目已处理`
})

// ── 导出逻辑 ──
async function startExport() {
  if (selectedIds.value.length === 0) return

  exporting.value = true
  exportError.value = ''
  progressTotal.value = 0
  progressDone.value = 0

  try {
    // 提交批量简报任务
    const resp = await api.post('/api/projects/briefs/batch', {
      project_ids: selectedIds.value,
      use_ai: useAi.value,
    })

    const jobId = resp?.export_job_id
    if (!jobId) {
      throw new Error('未返回任务 ID')
    }

    // 开始轮询
    startPolling(jobId)
  } catch (err: any) {
    const msg = err?.detail?.message || err?.message || '提交导出任务失败'
    exportError.value = msg
    exporting.value = false
  }
}

function startPolling(jobId: string) {
  pollTimer = setInterval(async () => {
    try {
      const status = await api.get(`/api/projects/briefs/batch/${jobId}`)

      progressTotal.value = status.progress_total || 0
      progressDone.value = status.progress_done || 0

      if (status.status === 'succeeded') {
        stopPolling()
        exporting.value = false
        ElMessage.success('合并简报生成完成')

        // 触发下载
        if (status.download_url) {
          await api.download(status.download_url, `合并简报_${new Date().toISOString().slice(0, 10)}.md`)
        } else if (status.data) {
          // 直接返回数据时，生成文件下载
          downloadMarkdown(status.data)
        }
      } else if (status.status === 'failed') {
        stopPolling()
        exporting.value = false
        exportError.value = status.error_message || '简报生成失败'
      }
    } catch (err: any) {
      stopPolling()
      exporting.value = false
      exportError.value = '轮询任务状态失败'
    }
  }, 2000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function downloadMarkdown(content: string) {
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `合并简报_${new Date().toISOString().slice(0, 10)}.md`
  link.click()
  URL.revokeObjectURL(link.href)
}

onBeforeUnmount(() => {
  stopPolling()
})
</script>

<style scoped>
.cross-brief-exporter {
  background: #fff;
  border: 1px solid var(--gt-color-border-light, #ebeef5);
  border-radius: var(--gt-radius-md, 8px);
  padding: 16px;
}

.exporter-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.exporter-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--gt-color-text, #303133);
}

.exporter-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.ai-switch {
  margin-right: 4px;
}

.exporter-select {
  margin-bottom: 12px;
}

.select-all-checkbox {
  margin-bottom: 8px;
  display: block;
}

.project-checkbox-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
}

.project-checkbox-item {
  margin-right: 0;
}

.exporter-progress {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.progress-text {
  font-size: 12px;
  color: var(--gt-color-text-secondary, #909399);
}

.exporter-error {
  margin-top: 12px;
}
</style>
