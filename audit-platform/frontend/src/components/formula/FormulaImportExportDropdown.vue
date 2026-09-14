<!--
  FormulaImportExportDropdown — 公式模块「导入导出▾」下拉（Req 23.1）

  遵循平台统一规范：el-dropdown 含 导出模板 / 导出数据 / 导入数据 三项，
  复用 useFormulaImportExport composable（http/axios 带 Authorization）。

  - 导出模板：首区块=编报说明 + 示例公式行（Req 23.2）
  - 导出数据：当前页面/模块已有公式（可按 page_key 过滤，Req 23.3）
  - 导入数据：上传 xlsx，逐条 full_resolve 校验，悬空报告并跳过（Req 23.4）

  Spec: .kiro/specs/formula-management-library/  Task: 14.4
  Requirements: 23.1, 23.2, 23.3, 23.4, 23.5
-->
<template>
  <el-dropdown trigger="click" @command="onCommand">
    <el-button size="small" :loading="ie.loading.value || ie.importing.value">
      导入导出 ▾
    </el-button>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item command="template">导出模板</el-dropdown-item>
        <el-dropdown-item command="export">导出数据</el-dropdown-item>
        <el-dropdown-item command="import">导入数据</el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
  <input ref="fileRef" type="file" accept=".xlsx" hidden @change="onFile" />
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  useFormulaImportExport,
  type FormulaImportResult,
} from '@/composables/useFormulaImportExport'

const props = defineProps<{
  /** 可选：限定导入导出到某页面键（scope:key，如 workpaper:D2） */
  pageKey?: string
  /** 可选：项目上下文，供导入时引用解析 */
  projectId?: string
}>()

const emit = defineEmits<{
  imported: [result: FormulaImportResult]
}>()

const fileRef = ref<HTMLInputElement | null>(null)
const ie = useFormulaImportExport()

async function onCommand(cmd: string) {
  if (cmd === 'template') await ie.exportTemplate()
  else if (cmd === 'export') await ie.exportData(props.pageKey)
  else if (cmd === 'import') fileRef.value?.click()
}

async function onFile(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const result = await ie.importData(file, {
    pageKey: props.pageKey,
    projectId: props.projectId,
  })
  if (result) {
    emit('imported', result)
    if (result.skipped_count > 0) {
      const detail = result.skipped
        .slice(0, 5)
        .map((s) => `第${s.row_number}行 ${s.page_key}/${s.target_cell}：${s.reason}`)
        .join('；')
      ElMessage.warning(`已跳过 ${result.skipped_count} 条悬空/无效公式：${detail}`)
    }
  }
}
</script>
