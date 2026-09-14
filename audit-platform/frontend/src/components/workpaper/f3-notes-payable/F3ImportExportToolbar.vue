<script setup lang="ts">
/** F3 各 Tab 导入导出工具栏（比照 D4Tab 内 el-dropdown） */
import { toRef, type Ref } from 'vue'
import { useF3ImportExport, type F3ImportableSheet } from '../composables/useF3ImportExport'

const props = defineProps<{
  wpId: string
  projectId: string
  sheet: F3ImportableSheet
  disabled?: boolean
}>()

const emit = defineEmits<{ (e: 'imported'): void }>()

const { importing, exportTemplate, exportData, importData } = useF3ImportExport({
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
