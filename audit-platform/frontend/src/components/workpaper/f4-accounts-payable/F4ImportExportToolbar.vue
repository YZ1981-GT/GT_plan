<script setup lang="ts">
import { toRef, type Ref } from 'vue'
import { useF4ImportExport, type F4ImportableSheet } from '../composables/useF4ImportExport'

const props = defineProps<{
  wpId: string
  projectId: string
  sheet: F4ImportableSheet
  disabled?: boolean
}>()

const emit = defineEmits<{ (event: 'imported'): void }>()

const { importing, exportTemplate, exportData, importData } = useF4ImportExport({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  onImported: () => emit('imported'),
})

function handleUpload(file: File): boolean {
  void importData(props.sheet, file)
  return false
}
</script>

<template>
  <el-dropdown size="small" trigger="click" :disabled="disabled || importing">
    <el-button size="small" :loading="importing">导入导出 ▾</el-button>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item @click="exportTemplate(sheet)">导出模板</el-dropdown-item>
        <el-dropdown-item @click="exportData(sheet)">导出数据</el-dropdown-item>
        <el-dropdown-item>
          <el-upload :show-file-list="false" accept=".xlsx,.xls" :before-upload="handleUpload">
            <span>导入数据</span>
          </el-upload>
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>
