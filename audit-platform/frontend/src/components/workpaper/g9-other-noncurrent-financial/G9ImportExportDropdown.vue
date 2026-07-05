<template>
  <div class="g9-import-export-dropdown">
    <el-dropdown trigger="click" @command="onCommand">
      <el-button size="small" :loading="ie.importing.value">导入导出 ▾</el-button>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item command="template">导出模板</el-dropdown-item>
          <el-dropdown-item command="export">导出数据</el-dropdown-item>
          <el-dropdown-item command="import">导入数据</el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
    <input ref="fileRef" type="file" accept=".xlsx" hidden @change="onFile" />
  </div>
</template>

<script setup lang="ts">
import { ref, toRef } from 'vue'
import { ElMessage } from 'element-plus'
import { useG9ImportExport, type G9ImportableSheet } from '../composables/useG9ImportExport'

const props = defineProps<{ wpId: string; sheet: G9ImportableSheet }>()
const emit = defineEmits<{ imported: [] }>()

const fileRef = ref<HTMLInputElement | null>(null)
const ie = useG9ImportExport({ wpId: toRef(props, 'wpId') })

async function onCommand(cmd: string) {
  if (cmd === 'template') await ie.exportTemplate(props.sheet)
  else if (cmd === 'export') await ie.exportData(props.sheet)
  else if (cmd === 'import') fileRef.value?.click()
}

async function onFile(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const result = await ie.importData(props.sheet, file)
  if (result) {
    emit('imported')
    ElMessage.success(`已导入 ${result.rowCount} 行`)
  }
}
</script>
