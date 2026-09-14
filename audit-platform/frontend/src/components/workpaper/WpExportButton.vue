<template>
  <el-button
    :type="buttonType"
    :size="size"
    :loading="loading"
    :icon="Download"
    @click="handleExport"
  >
    {{ label }}
  </el-button>
</template>

<script setup lang="ts">
/**
 * WpExportButton — 底稿导出按钮组件
 *
 * 底稿列表页/编辑页添加"导出"按钮。
 * 使用 downloadFile（axios blob + Bearer header），禁止 window.open。
 * 文件名从 Content-Disposition 解析。
 *
 * Requirements: 1.1
 */
import { Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useWpExportImport } from '@/composables/useWpExportImport'

const props = withDefaults(defineProps<{
  projectId: string
  wpId: string
  label?: string
  buttonType?: '' | 'primary' | 'success' | 'warning' | 'danger' | 'info'
  size?: '' | 'small' | 'default' | 'large'
}>(), {
  label: '导出',
  buttonType: 'primary',
  size: 'default',
})

const emit = defineEmits<{
  (e: 'exported'): void
  (e: 'error', err: Error): void
}>()

const { exportWithMetadata, loading } = useWpExportImport()

async function handleExport() {
  try {
    await exportWithMetadata(props.projectId, props.wpId)
    ElMessage.success('导出成功')
    emit('exported')
  } catch (err: any) {
    ElMessage.error(err?.message || '导出失败')
    emit('error', err)
  }
}
</script>
