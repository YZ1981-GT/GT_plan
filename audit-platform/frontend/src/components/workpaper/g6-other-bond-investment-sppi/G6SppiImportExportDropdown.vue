<template>
  <div class="g6-sppi-import-export-dropdown">
    <el-dropdown size="small" trigger="click" :disabled="disabled || !wpId" @command="onCommand">
      <el-button size="small" :loading="ie.isImporting.value" :disabled="disabled || !wpId">
        导入导出 ▾
      </el-button>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item command="template">导出模板</el-dropdown-item>
          <el-dropdown-item command="export">导出数据</el-dropdown-item>
          <el-dropdown-item command="import" :disabled="ie.isImporting.value">
            {{ ie.isImporting.value ? '导入中...' : '导入数据' }}
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
    <input ref="fileRef" type="file" accept=".xlsx,.xls" hidden @change="onFile" />
  </div>
</template>

<script setup lang="ts">
/**
 * G6 SPPI 导入导出下拉 — 对齐 G4/G2（导出模板 / 导出数据 / 导入数据）
 * 支持 sheet: G6-5 / G6-6 / G6-9 / G6-10
 */
import { ref, toRef } from 'vue'
import { ElMessage } from 'element-plus'
import { useG6SppiImportExport, type G6SppiImportableSheet } from '../composables/useG6SppiImportExport'

const props = defineProps<{
  wpId: string
  sheet: G6SppiImportableSheet
  disabled?: boolean
}>()

const emit = defineEmits<{ imported: [] }>()

const fileRef = ref<HTMLInputElement | null>(null)
const ie = useG6SppiImportExport({ wpId: toRef(props, 'wpId') })

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
