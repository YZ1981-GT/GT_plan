<!--
  SaveAsTemplateButton.vue — 「保存为模板」按钮（3 入口共用）
  Validates: Requirements 15.2, 15.3
  Feature: advanced-query-enhancements-p1p2, Task 8.2 / 8.4

  从 SheetCellRangePicker 选区状态序列化完整 config：
  {project_id, year, source, sheet_name, cell_range, filter_text,
   conditions[], selected_columns[], available_columns[],
   page_size, sort_field, sort_order}
-->
<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/services/apiProxy'
import type { CustomQueryTemplateConfig } from '@/types/custom-query-template'

const props = defineProps<{
  /** Function that returns the current query state as a complete config */
  getConfig: () => CustomQueryTemplateConfig | null
  /** Whether the button should be disabled */
  disabled?: boolean
}>()

const emit = defineEmits<{
  (e: 'saved', templateId: string): void
}>()

const saving = ref(false)

async function onSave() {
  const config = props.getConfig()
  if (!config || !config.source) {
    ElMessage.warning('请先选择数据源后再保存')
    return
  }

  try {
    const { value: name } = await ElMessageBox.prompt(
      '为该查询模板命名（项目+源+选区会自动记录）',
      '保存查询模板',
      {
        confirmButtonText: '保存',
        cancelButtonText: '取消',
        inputPattern: /.+/,
        inputErrorMessage: '请输入名称',
      }
    )
    if (!name) return

    saving.value = true

    // Build description from config
    const parts: string[] = []
    if (config.source) parts.push(config.source)
    if (config.sheet_name) parts.push(config.sheet_name)
    if (config.cell_range) parts.push(config.cell_range)
    const description = parts.join(' / ')

    const resp = await api.post('/api/custom-query/templates', {
      name,
      description,
      data_source: config.source,
      config,
      scope: 'private',
    })

    const templateId = resp.data?.id ?? ''
    emit('saved', templateId)

    // Invalidate cache
    sessionStorage.removeItem('gt:cqd:my-templates-cache')

    ElMessage.success(`已保存模板「${name}」`)
  } catch (err: any) {
    if (err === 'cancel' || err?.action === 'cancel') return
    ElMessage.error('保存失败: ' + (err?.response?.data?.detail || err?.message || '未知错误'))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-button
    size="small"
    :loading="saving"
    :disabled="disabled"
    title="保存当前选区/条件为查询模板"
    @click="onSave"
  >
    💾 保存为模板
  </el-button>
</template>
