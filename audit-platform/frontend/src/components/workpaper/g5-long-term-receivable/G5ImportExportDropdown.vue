<template>
  <el-dropdown trigger="click" :disabled="disabled || !wpId" @command="onCommand">
    <el-button size="small" :loading="ie.importing.value" :disabled="disabled || !wpId">导入导出 ▾</el-button>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item command="template">导出模板</el-dropdown-item>
        <el-dropdown-item command="export">导出数据</el-dropdown-item>
        <el-dropdown-item command="import" :disabled="disabled || ie.importing.value">导入数据</el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
  <input ref="fileRef" type="file" accept=".xlsx" hidden @change="onFile" />
</template>

<script setup lang="ts">
import { ref, toRef } from 'vue'
import { useG5ImportExport, type G5ImportableSheet } from '../composables/useG5ImportExport'

const props = withDefaults(defineProps<{
  wpId: string
  sheet: G5ImportableSheet
  disabled?: boolean
}>(), {
  disabled: false,
})
const emit = defineEmits<{ imported: [] }>()

const fileRef = ref<HTMLInputElement | null>(null)
const ie = useG5ImportExport({ wpId: toRef(props, 'wpId') })

async function onCommand(cmd: string) {
  if (props.disabled) return
  if (cmd === 'template') await ie.exportTemplate(props.sheet)
  else if (cmd === 'export') await ie.exportData(props.sheet)
  else if (cmd === 'import') fileRef.value?.click()
}

async function onFile(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || props.disabled) return
  // importData 成功时返回 { rowCount }（不含 rows）；消息由 useWorkpaperImportExport 统一提示
  const result = await ie.importData(props.sheet, file)
  if (result) emit('imported')
}
</script>
