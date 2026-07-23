<!--
  I4SheetImportExport — 统一导入导出下拉（仅后端已支持：I4-2 / I4-6 / I4-7）
-->
<template>
  <span class="i4-ie-wrap">
    <el-dropdown v-if="!disabled" trigger="click" @command="onCommand">
      <el-button size="small" :loading="importing">
        导入导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
      </el-button>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item command="tpl">导出模板</el-dropdown-item>
          <el-dropdown-item command="data">导出数据</el-dropdown-item>
          <el-dropdown-item command="import" divided>导入数据</el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
    <input
      ref="fileInputRef"
      type="file"
      accept=".xlsx,.xls"
      style="display:none"
      @change="onFile"
    />
  </span>
</template>

<script setup lang="ts">
import { ref, toRef } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'
import { useI4ImportExport, type I4ImportableSheet } from '../../composables/useI4ImportExport'

const props = defineProps<{
  sheet: I4ImportableSheet
  wpId: string
  projectId: string
  disabled?: boolean
}>()

const emit = defineEmits<{ (e: 'imported'): void }>()

const fileInputRef = ref<HTMLInputElement | null>(null)
const { exportTemplate, exportData, importData, importing } = useI4ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  onImported: () => emit('imported'),
})

function onCommand(cmd: string) {
  if (cmd === 'tpl') void exportTemplate(props.sheet)
  else if (cmd === 'data') void exportData(props.sheet)
  else if (cmd === 'import') fileInputRef.value?.click()
}

async function onFile(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  await importData(props.sheet, file)
}
</script>
