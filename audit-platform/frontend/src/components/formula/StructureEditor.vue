<template>
  <div class="structure-editor">
    <!-- 公式编辑栏 -->
    <FormulaBar
      :visible="true"
      :cell-info="currentCellInfo"
      @update-formula="onUpdateFormula"
      @update-value="onUpdateValue"
      @open-selector="showSelector = true"
    />

    <!-- 工具栏 -->
    <div class="editor-toolbar">
      <el-button-group size="small">
        <el-button @click="insertRow">插入行</el-button>
        <el-button @click="deleteRow">删除行</el-button>
        <el-button @click="insertCol">插入列</el-button>
        <el-button @click="deleteCol">删除列</el-button>
      </el-button-group>
      <el-divider direction="vertical" />
      <el-button size="small" @click="saveEdits" :loading="saving" type="primary">保存</el-button>
      <el-button size="small" @click="$emit('export-excel')">导出Excel</el-button>
      <el-button size="small" @click="$emit('export-word')">导出Word</el-button>
      <el-divider direction="vertical" />
      <el-button size="small" text @click="showVersions = true">版本历史</el-button>
    </div>

    <!-- HTML 表格区域 -->
    <div
      class="table-container"
      ref="tableContainer"
      v-html="htmlContent"
      @click="onCellClick"
      @dblclick="onCellDblClick"
    />

    <!-- 可视选择器弹窗 -->
    <CellSelector
      v-model="showSelector"
      :trial-balance-data="trialBalanceData"
      :report-data="reportData"
      :note-sections="noteSections"
      @confirm="onSelectorConfirm"
    />

    <!-- 版本历史弹窗 -->
    <el-dialog v-model="showVersions" title="版本历史" width="600px" append-to-body>
      <el-table :data="versions" size="small" max-height="400">
        <el-table-column prop="version" label="版本" width="60" />
        <el-table-column prop="edited_at" label="编辑时间" width="180" />
        <el-table-column prop="synced_from" label="来源" width="100" />
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <el-button size="small" text @click="diffVersion(row.version)">对比</el-button>
            <el-button size="small" text type="warning" @click="rollbackVersion(row.version)">回滚</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import FormulaBar from './FormulaBar.vue'
import CellSelector from './CellSelector.vue'
import {
  getExcelHtmlPreview,
  saveExcelHtmlEdits,
  getModuleHtml,
} from '@/services/commonApi'
import http from '@/utils/http'

const props = defineProps<{
  projectId: string
  fileStem?: string
  module?: string
  moduleParams?: Record<string, any>
}>()

const emit = defineEmits<{
  'export-excel': []
  'export-word': []
  'saved': [version: number]
}>()

const htmlContent = ref('')
const saving = ref(false)
const showSelector = ref(false)
const showVersions = ref(false)
const versions = ref<any[]>([])
const currentCellInfo = ref<any>(null)
const selectedCell = ref('')
const pendingEdits = ref<any[]>([])
const tableContainer = ref<HTMLElement>()

// 外部数据（供 CellSelector 使用）
const trialBalanceData = ref<any[]>([])
const reportData = ref<any[]>([])
const noteSections = ref<string[]>([])

// 锁刷新定时器
let lockRefreshTimer: ReturnType<typeof setInterval> | null = null

async function loadContent() {
  try {
    if (props.fileStem) {
      const result = await getExcelHtmlPreview(props.projectId, props.fileStem)
      htmlContent.value = result.html
    } else if (props.module) {
      const result = await getModuleHtml(props.projectId, props.module, {
        ...props.moduleParams,
        editable: true,
      })
      htmlContent.value = result.html
    }
  } catch {
    htmlContent.value = '<p>加载失败</p>'
  }
}

function onCellClick(e: MouseEvent) {
  const td = (e.target as HTMLElement).closest('td[data-cell]') as HTMLElement
  if (!td) return

  // 高亮选中
  tableContainer.value?.querySelectorAll('td.gt-selected').forEach(el => el.classList.remove('gt-selected'))
  td.classList.add('gt-selected')

  selectedCell.value = td.dataset.cell || ''

  // 更新公式栏信息
  currentCellInfo.value = {
    cell: td.dataset.cell,
    address: td.dataset.addr || '',
    value: td.textContent?.replace(/[A-Z]\d+$/g, '').trim(),
    formula: td.dataset.formula || null,
    formula_type: null,
    formula_desc: null,
    fetch_rule_id: td.dataset.fetchRule || null,
    merge: td.dataset.mergeRange ? { range: td.dataset.mergeRange } : null,
    is_merged: td.dataset.merged === 'true',
  }
}

function onCellDblClick(e: MouseEvent) {
  const td = (e.target as HTMLElement).closest('td[data-cell]') as HTMLElement
  if (!td || !td.isContentEditable) return
  // 双击进入编辑模式，浏览器原生 contenteditable 处理
}

function onUpdateFormula(cell: string, formula: string) {
  pendingEdits.value.push({ action: 'set_formula', cell, formula })
  ElMessage.info(`公式已设置: ${cell} = ${formula}`)
}

function onUpdateValue(cell: string, value: string) {
  pendingEdits.value.push({ action: 'edit', cell, value })
}

function onSelectorConfirm(rule: any) {
  if (!selectedCell.value) {
    ElMessage.warning('请先选择目标单元格')
    return
  }
  // 将选择结果转为公式
  const sources = rule.sources || []
  let formula = '='
  if (sources.length === 1) {
    formula += _sourceToFormula(sources[0])
  } else if (rule.transform === 'sum') {
    formula += sources.map(_sourceToFormula).join(' + ')
  } else if (rule.transform === 'diff' && sources.length >= 2) {
    formula += `${_sourceToFormula(sources[0])} - ${_sourceToFormula(sources[1])}`
  }

  pendingEdits.value.push({ action: 'set_formula', cell: selectedCell.value, formula, description: rule.description })
  ElMessage.success(`取数规则已绑定到 ${currentCellInfo.value?.address || selectedCell.value}`)
}

function _sourceToFormula(source: any): string {
  if (source.type === 'trial_balance') return `TB(${source.account_code}, ${source.field})`
  if (source.type === 'report') return `RPT(${source.row_code}, ${source.field})`
  if (source.type === 'note') return `NOTE(${source.section}, ${source.row}, ${source.col})`
  if (source.type === 'workpaper') return `WP(${source.wp_code}, ${source.data_key})`
  if (source.type === 'aux_balance') return `AUX(${source.account_code}, ${source.aux_code}, ${source.field})`
  return '0'
}

function insertRow() {
  if (!selectedCell.value) { ElMessage.warning('请先选择单元格'); return }
  const row = parseInt(selectedCell.value.split(':')[0])
  pendingEdits.value.push({ action: 'insert_row', at: row })
  ElMessage.info(`在第 ${row + 1} 行前插入空行`)
}

function deleteRow() {
  if (!selectedCell.value) { ElMessage.warning('请先选择单元格'); return }
  const row = parseInt(selectedCell.value.split(':')[0])
  pendingEdits.value.push({ action: 'delete_row', at: row })
  ElMessage.info(`删除第 ${row + 1} 行`)
}

function insertCol() {
  if (!selectedCell.value) { ElMessage.warning('请先选择单元格'); return }
  const col = parseInt(selectedCell.value.split(':')[1])
  pendingEdits.value.push({ action: 'insert_col', at: col })
  ElMessage.info(`在第 ${col + 1} 列前插入空列`)
}

function deleteCol() {
  if (!selectedCell.value) { ElMessage.warning('请先选择单元格'); return }
  const col = parseInt(selectedCell.value.split(':')[1])
  pendingEdits.value.push({ action: 'delete_col', at: col })
  ElMessage.info(`删除第 ${col + 1} 列`)
}

async function saveEdits() {
  if (!props.fileStem || !pendingEdits.value.length) {
    ElMessage.info('无待保存的编辑')
    return
  }
  saving.value = true
  try {
    const result = await saveExcelHtmlEdits(props.projectId, props.fileStem, pendingEdits.value)
    pendingEdits.value = []
    emit('saved', result.version)
    await loadContent()
    ElMessage.success(`已保存 v${result.version}`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function loadVersions() {
  if (!props.fileStem) return
  try {
    const { data } = await http.get(`/api/projects/${props.projectId}/excel-html/versions/${props.fileStem}`)
    versions.value = Array.isArray(data) ? data : []
  } catch { versions.value = [] }
}

async function diffVersion(version: number) {
  ElMessage.info(`对比版本 ${version} 与当前版本（功能开发中）`)
}

async function rollbackVersion(version: number) {
  await ElMessageBox.confirm(`确定回滚到版本 ${version}？当前未保存的编辑将丢失。`, '确认回滚')
  try {
    await http.post(`/api/projects/${props.projectId}/excel-html/versions/${props.fileStem}/rollback/${version}`)
    ElMessage.success(`已回滚到版本 ${version}`)
    await loadContent()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '回滚失败')
  }
}

// 编辑锁
async function acquireLock() {
  if (!props.fileStem) return
  try {
    await http.post(`/api/projects/${props.projectId}/excel-html/lock/${props.fileStem}`)
    // 定期刷新锁
    lockRefreshTimer = setInterval(async () => {
      try {
        await http.put(`/api/projects/${props.projectId}/excel-html/lock/${props.fileStem}/refresh`)
      } catch { /* 锁过期 */ }
    }, 4 * 60 * 1000) // 4分钟刷新一次
  } catch (e: any) {
    if (e?.response?.status === 423) {
      ElMessage.warning('文件正在被其他用户编辑，进入只读模式')
    }
  }
}

async function releaseLock() {
  if (!props.fileStem) return
  if (lockRefreshTimer) { clearInterval(lockRefreshTimer); lockRefreshTimer = null }
  try {
    await http.delete(`/api/projects/${props.projectId}/excel-html/lock/${props.fileStem}`)
  } catch { /* ignore */ }
}

onMounted(async () => {
  await acquireLock()
  await loadContent()
})

onUnmounted(() => {
  releaseLock()
})
</script>

<style scoped>
.structure-editor { display: flex; flex-direction: column; height: 100%; }
.editor-toolbar { display: flex; align-items: center; gap: 8px; padding: 6px 12px; border-bottom: 1px solid #e8e8e8; background: #fff; }
.table-container { flex: 1; overflow: auto; padding: 12px; }
.table-container :deep(td.gt-selected) { outline: 2px solid #4b2d77 !important; background: #faf8ff !important; }
</style>
