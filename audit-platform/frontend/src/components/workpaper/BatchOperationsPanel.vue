<script setup lang="ts">
/**
 * 批量操作 UI — 选中+操作按钮+进度条+结果摘要弹窗
 * Sprint 10 Task 10.10
 */
import { ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'

interface WorkpaperItem {
  id: string
  wp_code: string
  wp_name: string
}

const props = defineProps<{ projectId: string; workpapers: WorkpaperItem[] }>()

const selectedIds = ref<string[]>([])
const operating = ref(false)
const progressPercent = ref(0)
const resultVisible = ref(false)
const resultData = ref<{ total: number; success: number; failed: number; details: any[] }>({
  total: 0, success: 0, failed: 0, details: []
})

const hasSelection = computed(() => selectedIds.value.length > 0)

async function batchPrefill() {
  if (!hasSelection.value) return
  operating.value = true
  progressPercent.value = 0
  try {
    const data = await api.post(`/api/projects/${props.projectId}/workpapers/batch-prefill`, {
      wp_ids: selectedIds.value,
    })
    const res = data as any
    resultData.value = { total: res.total, success: res.success, failed: res.failed, details: res.results }
    resultVisible.value = true
  } catch {
    ElMessage.error('批量预填充失败')
  } finally {
    operating.value = false
    progressPercent.value = 100
  }
}

async function batchExport() {
  if (!hasSelection.value) return
  operating.value = true
  try {
    // Trigger download
    const url = `/api/projects/${props.projectId}/workpapers/batch-export`
    ElMessage.info('正在生成导出文件...')
    // In real implementation, use blob download
  } catch {
    ElMessage.error('批量导出失败')
  } finally {
    operating.value = false
  }
}

async function batchSubmit() {
  if (!hasSelection.value) return
  try {
    await ElMessageBox.confirm(`确认提交 ${selectedIds.value.length} 个底稿进行复核？`, '批量提交')
  } catch { return }

  operating.value = true
  try {
    const data = await api.post(`/api/projects/${props.projectId}/workpapers/batch-submit`, {
      wp_ids: selectedIds.value,
    })
    const res = data as any
    resultData.value = { total: res.total, success: res.submitted, failed: res.skipped, details: res.skipped_reasons }
    resultVisible.value = true
  } catch {
    ElMessage.error('批量提交失败')
  } finally {
    operating.value = false
  }
}
</script>

<template>
  <div class="batch-operations-panel">
    <div class="toolbar">
      <el-button size="small" :disabled="!hasSelection || operating" @click="batchPrefill">
        批量预填充
      </el-button>
      <el-button size="small" :disabled="!hasSelection || operating" @click="batchExport">
        批量导出 PDF
      </el-button>
      <el-button size="small" type="primary" :disabled="!hasSelection || operating" @click="batchSubmit">
        批量提交复核
      </el-button>
      <span v-if="hasSelection" class="selection-count">已选 {{ selectedIds.length }} 项</span>
    </div>
    <el-progress v-if="operating" :percentage="progressPercent" :stroke-width="4" style="margin-top: 8px;" />

    <!-- 结果摘要弹窗 -->
    <el-dialog v-model="resultVisible" title="操作结果" width="400px">
      <div class="result-summary">
        <p>总计：{{ resultData.total }}</p>
        <p style="color: #67c23a;">成功：{{ resultData.success }}</p>
        <p v-if="resultData.failed > 0" style="color: #f56c6c;">失败/跳过：{{ resultData.failed }}</p>
      </div>
      <div v-if="resultData.details.length > 0" class="result-details">
        <div v-for="(d, i) in resultData.details" :key="i" class="detail-item">
          {{ d.wp_id || d.reason }}
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.batch-operations-panel { padding: 8px 0; }
.toolbar { display: flex; align-items: center; gap: 8px; }
.selection-count { font-size: 12px; color: #909399; margin-left: 8px; }
.result-summary p { margin: 4px 0; }
.result-details { margin-top: 12px; max-height: 200px; overflow-y: auto; }
.detail-item { font-size: 12px; padding: 2px 0; color: #606266; }
</style>
