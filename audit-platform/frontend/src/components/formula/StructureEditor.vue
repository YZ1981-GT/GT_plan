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
      <el-button size="small" @click="runFormulas" :loading="calculating">执行公式</el-button>
      <el-button size="small" @click="$emit('export-excel')">导出Excel</el-button>
      <el-button size="small" @click="$emit('export-word')">导出Word</el-button>
      <el-divider direction="vertical" />
      <el-button size="small" text @click="showVersions = true">版本历史</el-button>
      <el-divider direction="vertical" />
      <!-- 可视化维度切换 -->
      <el-checkbox v-model="showFormulas" size="small">显示公式</el-checkbox>
      <el-checkbox v-model="showSources" size="small">显示数据源</el-checkbox>
      <el-checkbox v-model="showStatus" size="small">显示状态</el-checkbox>
    </div>

    <!-- 多维信息面板（选中单元格时显示） -->
    <div class="info-panel" v-if="currentCellInfo && showInfoPanel">
      <div class="info-grid">
        <!-- 基本信息 -->
        <div class="info-card">
          <div class="info-card-title">📍 位置</div>
          <div class="info-card-body">
            <span class="info-label">地址:</span> <code>{{ currentCellInfo.address }}</code>
            <span v-if="currentCellInfo.is_merged" class="info-badge merge">合并 {{ currentCellInfo.merge?.range }}</span>
          </div>
        </div>
        <!-- 公式信息 -->
        <div class="info-card" v-if="currentCellInfo.formula">
          <div class="info-card-title">📐 公式</div>
          <div class="info-card-body">
            <code class="formula-code">{{ currentCellInfo.formula }}</code>
            <el-tag v-if="currentCellInfo.formula_type" size="small" effect="plain">{{ formulaTypeMap[currentCellInfo.formula_type] || currentCellInfo.formula_type }}</el-tag>
          </div>
        </div>
        <!-- 数据源溯源 -->
        <div class="info-card" v-if="currentCellInfo.fetch_rule_id">
          <div class="info-card-title">🔗 数据源</div>
          <div class="info-card-body">
            <span class="info-badge source">取数规则绑定</span>
            <el-button size="small" text type="primary" @click="traceSource">查看来源 →</el-button>
          </div>
        </div>
        <!-- 值信息 -->
        <div class="info-card">
          <div class="info-card-title">💾 值</div>
          <div class="info-card-body">
            <span class="value-display">{{ formatValue(currentCellInfo.value) }}</span>
            <span class="info-label" v-if="pendingEdits.length"> ({{ pendingEdits.length }}项未保存)</span>
          </div>
        </div>
      </div>
      <el-button class="close-panel" size="small" text @click="showInfoPanel = false">收起 ▲</el-button>
    </div>
    <div class="info-toggle" v-else-if="currentCellInfo" @click="showInfoPanel = true">
      <span>{{ currentCellInfo.address }} | {{ currentCellInfo.formula || formatValue(currentCellInfo.value) || '空' }}</span>
      <span class="toggle-hint">展开 ▼</span>
    </div>

    <!-- HTML 表格区域 -->
    <div
      class="table-container"
      :class="{'show-formulas': showFormulas, 'show-sources': showSources, 'show-status': showStatus}"
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
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import FormulaBar from './FormulaBar.vue'
import CellSelector from './CellSelector.vue'
import {
  getExcelHtmlPreview,
  saveExcelHtmlEdits,
  getModuleHtml,
  acquireEditLock,
  releaseEditLock,
  refreshEditLock,
  listFileVersions,
  rollbackFileVersion,
  executeFormulas,
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
const calculating = ref(false)
const showSelector = ref(false)
const showVersions = ref(false)
const showInfoPanel = ref(true)
const showFormulas = ref(false)
const showSources = ref(false)
const showStatus = ref(false)
const versions = ref<any[]>([])
const currentCellInfo = ref<any>(null)
const selectedCell = ref('')
const pendingEdits = ref<any[]>([])
const tableContainer = ref<HTMLElement>()

const formulaTypeMap: Record<string, string> = {
  vertical_sum: '纵向合计',
  horizontal_balance: '横向平衡',
  book_value: '账面价值',
  cross_table: '跨表引用',
}

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
    formula_type: td.dataset.formulaType || null,
    formula_desc: null,
    fetch_rule_id: td.dataset.fetchRule || null,
    merge: td.dataset.mergeRange ? { range: td.dataset.mergeRange } : null,
    is_merged: td.dataset.merged === 'true',
  }

  // 可视化维度：高亮公式依赖的单元格
  if (showFormulas.value && td.dataset.formula) {
    _highlightFormulaDeps(td.dataset.formula)
  }
}

function _highlightFormulaDeps(formula: string) {
  // 清除旧高亮
  tableContainer.value?.querySelectorAll('td.gt-dep-highlight').forEach(el => el.classList.remove('gt-dep-highlight'))

  // 解析公式中的单元格引用（简单正则匹配 A1-Z99 格式）
  const refs = formula.match(/[A-Z]{1,2}\d{1,3}/g) || []
  for (const ref of refs) {
    const td = tableContainer.value?.querySelector(`td[data-addr="${ref}"]`)
    if (td) td.classList.add('gt-dep-highlight')
  }
}

function traceSource() {
  ElMessage.info('溯源跳转：查看数据来源（调用 trace-forward API）')
  // TODO: 调用 trace-forward 显示来源弹窗
}

function formatValue(val: any): string {
  if (val === null || val === undefined) return ''
  if (typeof val === 'number') {
    if (val === 0) return '-'
    return val.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
  }
  return String(val)
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

async function runFormulas() {
  if (!props.fileStem) return
  calculating.value = true
  try {
    const result = await executeFormulas(props.projectId, props.fileStem)
    await loadContent()

    // 高亮出错的单元格
    if (result.errors?.length) {
      setTimeout(() => {
        for (const err of result.errors) {
          const td = tableContainer.value?.querySelector(`td[data-cell="${err.cell}"]`) as HTMLElement
          if (td) {
            td.classList.add('gt-formula-error')
            td.title = `公式错误: ${err.error}\n公式: ${err.formula || ''}`
          }
        }
      }, 100) // 等待 v-html 渲染完成
      ElMessage.warning(`执行完成：${result.executed}/${result.total_formulas} 成功，${result.errors.length} 个错误（红色标记）`)
    } else {
      ElMessage.success(`公式执行完成：${result.executed} 个单元格已更新`)
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '公式执行失败')
  } finally {
    calculating.value = false
  }
}

async function loadVersions() {
  if (!props.fileStem) return
  try {
    versions.value = await listFileVersions(props.projectId, props.fileStem)
  } catch { versions.value = [] }
}

async function diffVersion(version: number) {
  ElMessage.info(`对比版本 ${version} 与当前版本（功能开发中）`)
}

async function rollbackVersion(version: number) {
  await ElMessageBox.confirm(`确定回滚到版本 ${version}？当前未保存的编辑将丢失。`, '确认回滚')
  try {
    await rollbackFileVersion(props.projectId, props.fileStem!)
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
    await acquireEditLock(props.projectId, props.fileStem)
    // 定期刷新锁
    lockRefreshTimer = setInterval(async () => {
      try {
        await refreshEditLock(props.projectId, props.fileStem!)
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
    await releaseEditLock(props.projectId, props.fileStem)
  } catch { /* ignore */ }
}

onMounted(async () => {
  await acquireLock()
  await loadContent()
  await loadSelectorData()
  // 注册键盘快捷键
  document.addEventListener('keydown', onKeyDown)
})

onUnmounted(() => {
  releaseLock()
  document.removeEventListener('keydown', onKeyDown)
})

// ═══ 键盘快捷键 ═══

function onKeyDown(e: KeyboardEvent) {
  // Ctrl+S 保存
  if (e.ctrlKey && e.key === 's') {
    e.preventDefault()
    saveEdits()
    return
  }
  // Ctrl+Z 撤销最后一条编辑
  if (e.ctrlKey && e.key === 'z') {
    e.preventDefault()
    if (pendingEdits.value.length) {
      pendingEdits.value.pop()
      ElMessage.info(`撤销一条编辑（剩余 ${pendingEdits.value.length} 条）`)
    }
    return
  }
  // Escape 取消选中
  if (e.key === 'Escape') {
    tableContainer.value?.querySelectorAll('td.gt-selected').forEach(el => el.classList.remove('gt-selected'))
    currentCellInfo.value = null
    selectedCell.value = ''
    return
  }

  // 以下快捷键需要有选中单元格
  if (!selectedCell.value) return
  const [row, col] = selectedCell.value.split(':').map(Number)

  // Tab → 下一列
  if (e.key === 'Tab') {
    e.preventDefault()
    _navigateTo(row, col + (e.shiftKey ? -1 : 1))
    return
  }
  // Enter → 下一行
  if (e.key === 'Enter' && !e.ctrlKey) {
    // 如果当前在 contenteditable 编辑中，不拦截
    const active = document.activeElement
    if (active && active.tagName === 'TD' && (active as HTMLElement).isContentEditable) return
    e.preventDefault()
    _navigateTo(row + 1, col)
    return
  }
  // 方向键导航（仅在非编辑状态）
  const active = document.activeElement
  if (active && active.tagName === 'TD' && (active as HTMLElement).isContentEditable) return
  if (e.key === 'ArrowUp') { e.preventDefault(); _navigateTo(row - 1, col) }
  if (e.key === 'ArrowDown') { e.preventDefault(); _navigateTo(row + 1, col) }
  if (e.key === 'ArrowLeft') { e.preventDefault(); _navigateTo(row, col - 1) }
  if (e.key === 'ArrowRight') { e.preventDefault(); _navigateTo(row, col + 1) }
}

function _navigateTo(row: number, col: number) {
  if (row < 0 || col < 0) return
  const key = `${row}:${col}`
  const td = tableContainer.value?.querySelector(`td[data-cell="${key}"]`) as HTMLElement
  if (td) {
    td.click()  // 触发 onCellClick
    td.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }
}

// ═══ 加载 CellSelector 所需数据 ═══

async function loadSelectorData() {
  try {
    // 加载试算表数据
    const { data: tbData } = await http.get(`/api/projects/${props.projectId}/trial-balance`, { params: { year: 2025 } })
    trialBalanceData.value = Array.isArray(tbData) ? tbData : (tbData?.data || [])
  } catch { trialBalanceData.value = [] }

  try {
    // 加载报表行次数据
    const { data: rptData } = await http.get(`/api/projects/${props.projectId}/reports`, { params: { year: 2025 } })
    reportData.value = Array.isArray(rptData) ? rptData : (rptData?.rows || rptData?.data || [])
  } catch { reportData.value = [] }

  // 附注章节列表（静态）
  noteSections.value = [
    '五、1', '五、2', '五、3', '五、4', '五、5', '五、6', '五、7', '五、8', '五、9', '五、10',
    '五、11', '五、12', '五、13', '五、14', '五、15', '五、16', '五、17', '五、18', '五、19', '五、20',
    '五、21', '五、22', '五、23', '五、24', '五、25', '五、26', '五、27', '五、28', '五、29', '五、30',
    '五、31', '五、32', '五、33', '五、34', '五、35', '五、36', '五、37',
  ]
}
</script>

<style scoped>
.structure-editor { display: flex; flex-direction: column; height: 100%; }
.editor-toolbar { display: flex; align-items: center; gap: 8px; padding: 6px 12px; border-bottom: 1px solid #e8e8e8; background: #fff; flex-wrap: wrap; }
.table-container { flex: 1; overflow: auto; padding: 12px; }
.table-container :deep(td.gt-selected) { outline: 2px solid #4b2d77 !important; background: #faf8ff !important; }
.table-container :deep(td.gt-dep-highlight) { outline: 1px dashed #e6a23c !important; background: #fdf6ec !important; }
.table-container :deep(td.gt-formula-error) { background: #fef0f0 !important; border: 1px solid #f56c6c !important; cursor: help; }

/* 可视化维度：显示公式 */
.table-container.show-formulas :deep(td[data-formula])::after {
  content: attr(data-formula);
  display: block;
  font-size: 9px;
  color: #b7791f;
  font-family: monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
  opacity: 0.8;
}
/* 可视化维度：显示数据源 */
.table-container.show-sources :deep(td[data-fetch-rule])::before {
  content: "🔗";
  position: absolute;
  top: 1px;
  left: 2px;
  font-size: 10px;
}
/* 可视化维度：显示状态（有值=绿色左边框，空=灰色，有公式=橙色） */
.table-container.show-status :deep(td[data-formula]) { border-left: 3px solid #e6a23c !important; }
.table-container.show-status :deep(td[data-fetch-rule]) { border-left: 3px solid #0094b3 !important; }

/* 多维信息面板 */
.info-panel { padding: 8px 12px; background: #f9f7fc; border-bottom: 1px solid #e8e0f0; }
.info-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 8px; }
.info-card { padding: 6px 10px; background: #fff; border-radius: 6px; border: 1px solid #f0ebf8; }
.info-card-title { font-size: 11px; color: #909399; margin-bottom: 3px; }
.info-card-body { font-size: 12px; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.info-label { color: #909399; }
.info-badge { font-size: 10px; padding: 1px 6px; border-radius: 3px; }
.info-badge.merge { background: #f0e6ff; color: #7c3aed; }
.info-badge.source { background: #e0f7fa; color: #0094b3; }
.formula-code { font-size: 11px; background: #fffbf0; padding: 2px 6px; border-radius: 3px; color: #b7791f; }
.value-display { font-weight: 600; color: #303133; font-family: 'Arial Narrow', monospace; }
.close-panel { margin-top: 4px; }

/* 收起状态的信息条 */
.info-toggle { display: flex; justify-content: space-between; align-items: center; padding: 4px 12px; background: #fafafa; border-bottom: 1px solid #eee; font-size: 12px; color: #606266; cursor: pointer; }
.info-toggle:hover { background: #f5f0ff; }
.toggle-hint { color: #c0c4cc; font-size: 11px; }
</style>
