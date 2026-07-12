<template>
  <el-dropdown trigger="click" size="small" @command="handleCommand">
    <el-button size="small" :disabled="loading">
      导入导出 ▾
    </el-button>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
        <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
        <el-dropdown-item command="import-data">
          <el-upload
            ref="uploadRef"
            :show-file-list="false"
            accept=".xlsx,.xls"
            :auto-upload="false"
            :disabled="loading"
            @change="onFileChange"
          >
            <span>导入数据</span>
          </el-upload>
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup lang="ts">
/**
 * WpImportExport — 底稿导入导出 dropdown（Wp_Kit）
 *
 * 标准三项：导出模板 / 导出数据 / 导入数据
 * 复用 useXImportExport 范式（后端三端点 + http axios + blob 下载 + FormData 上传）
 *
 * Props:
 *   - wpId: 底稿 ID
 *   - endpoints: 自定义端点路径（可选，默认 /api/workpapers/{wpId}/export-template 等）
 *
 * Emits:
 *   - imported: 导入成功后触发（父组件 reload）
 *   - error: 操作失败时触发
 *
 * Feature: platform-global-hardening
 * Task: 6.4
 * Requirements: 4.4
 */
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

// ─── Props & Emits ───────────────────────────────────────────────────────────

export interface WpImportExportEndpoints {
  exportTemplate?: string
  exportData?: string
  importData?: string
}

const props = defineProps<{
  wpId: string
  endpoints?: WpImportExportEndpoints
}>()

const emit = defineEmits<{
  imported: []
  error: [msg: string]
}>()

// ─── State ───────────────────────────────────────────────────────────────────

const loading = ref(false)

// ─── Computed Endpoints ──────────────────────────────────────────────────────

const resolvedEndpoints = computed(() => ({
  exportTemplate: props.endpoints?.exportTemplate
    ?? `/api/workpapers/${props.wpId}/export-template`,
  exportData: props.endpoints?.exportData
    ?? `/api/workpapers/${props.wpId}/export-data`,
  importData: props.endpoints?.importData
    ?? `/api/workpapers/${props.wpId}/import-data`,
}))

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 从 Content-Disposition 解析文件名（支持 RFC5987 中文名）
 */
function parseFilename(contentDisposition: string | null, fallback: string): string {
  if (!contentDisposition) return fallback

  // 优先 filename*=UTF-8''xxx（RFC5987）
  const rfc5987Match = contentDisposition.match(/filename\*=UTF-8''(.+?)(?:;|$)/i)
  if (rfc5987Match) {
    try {
      return decodeURIComponent(rfc5987Match[1])
    } catch {
      // 解码失败用 fallback
    }
  }

  // 兜底 filename="xxx"
  const plainMatch = contentDisposition.match(/filename="?(.+?)"?(?:;|$)/)
  if (plainMatch) return plainMatch[1]

  return fallback
}

/**
 * 下载 Blob 为文件
 */
function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

// ─── Actions ─────────────────────────────────────────────────────────────────

async function exportTemplate(): Promise<void> {
  if (!props.wpId) return
  loading.value = true
  try {
    const response = await http.get(resolvedEndpoints.value.exportTemplate, {
      responseType: 'blob',
    })
    const blob = new Blob([response.data], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    const contentDisposition = response.headers?.['content-disposition'] ?? null
    const filename = parseFilename(contentDisposition, '导出模板.xlsx')
    downloadBlob(blob, filename)
    ElMessage.success('模板已导出')
  } catch (err: any) {
    const msg = err?.response?.data?.message || err.message || '导出模板失败'
    ElMessage.error(msg)
    emit('error', msg)
  } finally {
    loading.value = false
  }
}

async function exportData(): Promise<void> {
  if (!props.wpId) return
  loading.value = true
  try {
    const response = await http.get(resolvedEndpoints.value.exportData, {
      responseType: 'blob',
    })
    const blob = new Blob([response.data], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    const contentDisposition = response.headers?.['content-disposition'] ?? null
    const filename = parseFilename(contentDisposition, '导出数据.xlsx')
    downloadBlob(blob, filename)
    ElMessage.success('数据已导出')
  } catch (err: any) {
    const msg = err?.response?.data?.message || err.message || '导出数据失败'
    ElMessage.error(msg)
    emit('error', msg)
  } finally {
    loading.value = false
  }
}

async function importData(file: File): Promise<void> {
  if (!props.wpId) return
  loading.value = true
  try {
    const formData = new FormData()
    formData.append('file', file)
    const response = await http.post(resolvedEndpoints.value.importData, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    const data: any = response.data?.data ?? response.data
    const rowCount = data?.imported_count ?? data?.rowCount ?? 0
    let msg = `成功导入 ${rowCount} 行数据`
    if (data?.warning) msg += `（${data.warning}）`
    ElMessage.success(msg)
    emit('imported')
  } catch (err: any) {
    const errMsg = err?.response?.data?.detail
      || err?.response?.data?.message
      || err.message
      || '导入数据失败'
    const msg = Array.isArray(errMsg) ? errMsg.join(', ') : String(errMsg)
    ElMessage.error(msg)
    emit('error', msg)
  } finally {
    loading.value = false
  }
}

// ─── Command Handler ─────────────────────────────────────────────────────────

function handleCommand(command: string): void {
  if (command === 'export-template') {
    exportTemplate()
  } else if (command === 'export-data') {
    exportData()
  }
  // import-data 由 el-upload @change 触发，不走 command
}

function onFileChange(f: { raw?: File } | File): void {
  const file = f instanceof File ? f : (f.raw ?? null)
  if (!file) return
  importData(file)
}
</script>

<style scoped>
/* 导入项内 upload 不需额外间距 */
:deep(.el-upload) {
  display: inline;
}
</style>
