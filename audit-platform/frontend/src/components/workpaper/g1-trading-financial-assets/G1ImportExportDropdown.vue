<template>
  <div class="g1-import-export-dropdown">
    <el-dropdown size="small" trigger="click" :disabled="disabled || !wpId" @command="onCommand">
      <el-button size="small" :loading="ie.importing.value" :disabled="disabled || !wpId">
        导入导出 ▾
      </el-button>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item command="template">导出模板</el-dropdown-item>
          <el-dropdown-item command="export">导出数据</el-dropdown-item>
          <el-dropdown-item command="import" :disabled="ie.importing.value">
            {{ ie.importing.value ? '导入中...' : '导入数据' }}
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
    <input ref="fileRef" type="file" accept=".xlsx,.xls" hidden @change="onFile" />
  </div>
</template>

<script setup lang="ts">
/**
 * G1 导入导出下拉 — 对齐 D4-8（导出模板 / 导出数据 / 导入数据）
 */
import { ref, toRef } from 'vue'
import { ElMessage } from 'element-plus'
import { useG1ImportExport, type G1ImportableSheet } from '../../composables/useG1ImportExport'

const props = defineProps<{
  wpId: string
  sheet: G1ImportableSheet
  disabled?: boolean
}>()

const emit = defineEmits<{ imported: [] }>()

const fileRef = ref<HTMLInputElement | null>(null)
const ie = useG1ImportExport({ wpId: toRef(props, 'wpId') })

async function onCommand(cmd: string) {
  if (!props.wpId) {
    ElMessage.warning('底稿未就绪')
    return
  }
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
  if (result) emit('imported')
}
</script>
