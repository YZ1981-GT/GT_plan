<template>
  <el-dialog
    v-model="visible"
    title="导出"
    width="560px"
    :close-on-click-modal="false"
    @close="onClose"
  >
    <!-- 导出模式选择 -->
    <div class="gt-export-modes">
      <el-radio-group v-model="exportMode" size="large">
        <el-radio-button value="excel">仅报表 Excel</el-radio-button>
        <el-radio-button value="word">仅附注 Word</el-radio-button>
        <el-radio-button value="package">完整导出包</el-radio-button>
      </el-radio-group>
    </div>

    <!-- 完整导出包选项 -->
    <div v-if="exportMode === 'package'" class="gt-export-options">
      <el-checkbox v-model="includeAuditReport">包含审计报告</el-checkbox>
      <el-checkbox v-model="includeWorkpapers">包含审定表</el-checkbox>
    </div>

    <!-- 一致性检查结果 -->
    <div class="gt-export-checks">
      <div class="gt-export-checks__header">
        <span>一致性检查</span>
        <el-button size="small" text :loading="checkLoading" @click="runChecks">
          🔄 重新检查
        </el-button>
      </div>
      <div v-if="checkLoading" class="gt-export-checks__loading">
        <el-skeleton :rows="3" animated />
      </div>
      <div v-else-if="checks.length > 0" class="gt-export-checks__list">
        <div
          v-for="check in checks"
          :key="check.check_name"
          class="gt-export-check-item"
          :class="{
            'gt-export-check-item--pass': check.passed,
            'gt-export-check-item--fail-blocking': !check.passed && check.severity === 'blocking',
            'gt-export-check-item--fail-warning': !check.passed && check.severity === 'warning',
          }"
        >
          <span class="gt-export-check-item__icon">
            {{ check.passed ? '✅' : (check.severity === 'blocking' ? '❌' : '⚠️') }}
          </span>
          <span class="gt-export-check-item__name">{{ check.check_name }}</span>
          <span class="gt-export-check-item__details">{{ check.details }}</span>
        </div>
      </div>
    </div>

    <!-- 强制导出（admin/partner 可见） -->
    <div v-if="hasBlockingFailures && canForceExport" class="gt-export-force">
      <el-checkbox v-model="forceExport">
        强制导出（跳过阻断项检查）
      </el-checkbox>
    </div>

    <!-- 导出进度 -->
    <div v-if="exporting" class="gt-export-progress">
      <el-progress :percentage="exportProgress" :status="exportProgress >= 100 ? 'success' : undefined" />
      <span class="gt-export-progress__text">{{ exportProgressText }}</span>
    </div>

    <template #footer>
      <el-button @click="onClose">取消</el-button>
      <el-button
        type="primary"
        :loading="exporting"
        :disabled="hasBlockingFailures && !forceExport"
        @click="onExport"
      >
        {{ exporting ? '导出中...' : '开始导出' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * ExportDialog — 导出对话框
 *
 * 3 种导出模式：仅报表 Excel / 仅附注 Word / 完整导出包
 * 导出前显示一致性检查结果（绿/红/黄）
 * blocking 项禁用导出按钮
 * "强制导出"复选框（admin/partner 可见）
 *
 * Requirements: 12.1-12.7
 */
import { ref, computed, watch } from 'vue'
import { api } from '@/services/apiProxy'
import { chainWorkflow } from '@/services/apiPaths'
import { ElMessage } from 'element-plus'
import { handleApiError } from '@/utils/errorHandler'
import http from '@/utils/http'
import { useAuthStore } from '@/stores/auth'

const props = defineProps<{
  projectId: string
  year: number
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const visible = ref(true)
const authStore = useAuthStore()

// Export mode
const exportMode = ref<'excel' | 'word' | 'package'>('package')
const includeAuditReport = ref(false)
const includeWorkpapers = ref(false)
const forceExport = ref(false)

// Consistency checks
const checkLoading = ref(false)
const checks = ref<Array<{
  check_name: string
  passed: boolean
  details: string
  severity: string
}>>([])

const hasBlockingFailures = computed(() =>
  checks.value.some(c => !c.passed && c.severity === 'blocking')
)

const canForceExport = computed(() => {
  const role = authStore.user?.role
  return role === 'admin' || role === 'partner'
})

// Export progress
const exporting = ref(false)
const exportProgress = ref(0)
const exportProgressText = ref('')

// Run consistency checks on open
async function runChecks() {
  if (!props.projectId || !props.year) return
  checkLoading.value = true
  try {
    const data: any = await api.get(
      `/api/projects/${props.projectId}/workflow/consistency-check`,
      { params: { year: props.year } }
    )
    checks.value = data?.checks || []
  } catch (err) {
    handleApiError(err, '一致性检查')
  } finally {
    checkLoading.value = false
  }
}

// Export
async function onExport() {
  if (!props.projectId || !props.year) return
  exporting.value = true
  exportProgress.value = 10
  exportProgressText.value = '准备导出...'

  try {
    let url = ''
    let body: any = {}

    if (exportMode.value === 'excel') {
      url = `/api/projects/${props.projectId}/reports/export-excel`
      body = { year: props.year, mode: 'audited' }
    } else if (exportMode.value === 'word') {
      url = `/api/projects/${props.projectId}/notes/export-word`
      body = { year: props.year }
    } else {
      url = `/api/projects/${props.projectId}/workflow/export-package`
      body = {
        year: props.year,
        include_audit_report: includeAuditReport.value,
        include_workpapers: includeWorkpapers.value,
        force_export: forceExport.value,
      }
    }

    exportProgress.value = 30
    exportProgressText.value = '正在生成文件...'

    const response = await http.post(url, body, { responseType: 'blob' })

    exportProgress.value = 80
    exportProgressText.value = '下载中...'

    // Auto-download
    const blob = new Blob([response.data])
    const contentDisposition = response.headers['content-disposition'] || ''
    const filenameMatch = contentDisposition.match(/filename="?([^";\n]+)"?/)
    const filename = filenameMatch
      ? decodeURIComponent(filenameMatch[1])
      : `export_${props.year}.${exportMode.value === 'excel' ? 'xlsx' : exportMode.value === 'word' ? 'docx' : 'zip'}`

    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = filename
    link.click()
    URL.revokeObjectURL(link.href)

    exportProgress.value = 100
    exportProgressText.value = '导出完成'
    ElMessage.success('导出成功')

    setTimeout(() => onClose(), 1500)
  } catch (err: any) {
    exportProgress.value = 0
    exportProgressText.value = ''
    if (err?.response?.status === 400) {
      const detail = err?.response?.data
      if (detail?.checks) {
        ElMessage.error('一致性检查未通过，请修复后重试')
      } else {
        handleApiError(err, '导出')
      }
    } else {
      handleApiError(err, '导出')
    }
  } finally {
    exporting.value = false
  }
}

function onClose() {
  visible.value = false
  emit('close')
}

// Run checks on mount
watch(() => props.projectId, () => runChecks(), { immediate: true })
</script>

<style scoped>
.gt-export-modes {
  margin-bottom: 16px;
  text-align: center;
}

.gt-export-options {
  margin-bottom: 16px;
  padding: 12px;
  background: #f8f7fc;
  border-radius: 6px;
  display: flex;
  gap: 16px;
}

.gt-export-checks {
  margin-bottom: 16px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 12px;
}

.gt-export-checks__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-weight: 600;
  font-size: 13px;
}

.gt-export-checks__list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.gt-export-check-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 4px;
  font-size: 13px;
}

.gt-export-check-item--pass {
  background: #f0f9eb;
}

.gt-export-check-item--fail-blocking {
  background: #fef0f0;
}

.gt-export-check-item--fail-warning {
  background: #fdf6ec;
}

.gt-export-check-item__icon {
  flex-shrink: 0;
}

.gt-export-check-item__name {
  font-weight: 500;
  min-width: 80px;
}

.gt-export-check-item__details {
  color: #909399;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gt-export-force {
  margin-bottom: 16px;
  padding: 8px 12px;
  background: #fef0f0;
  border-radius: 4px;
  border: 1px solid #fde2e2;
}

.gt-export-progress {
  margin-top: 12px;
}

.gt-export-progress__text {
  display: block;
  text-align: center;
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
</style>
