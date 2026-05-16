<!--
  自定义查询弹窗 — 全局多维度数据查询
  支持：报表/试算表/附注/调整分录/工作底稿
  功能：树形指标选择 + 过滤条件 + 结果表格 + 导出/转置/复制
-->
<template>
  <el-dialog v-model="visible" title="🔍 自定义查询" width="90%" top="3vh" append-to-body destroy-on-close class="gt-cq-dialog">
    <div class="gt-cq-container">
      <!-- 左侧：指标树 -->
      <div class="gt-cq-sidebar">
        <div class="gt-cq-sidebar-title">数据源</div>
        <el-tree :data="indicatorTree" :props="{ label: 'label', children: 'children' }" node-key="key"
          highlight-current :expand-on-click-node="false" default-expand-all @node-click="onIndicatorClick">
          <template #default="{ data }">
            <span style="font-size: var(--gt-font-size-xs)">{{ data.icon || '' }} {{ data.label }}</span>
          </template>
        </el-tree>
      </div>
      <!-- 右侧：查询条件 + 结果 -->
      <div class="gt-cq-main">
        <div class="gt-cq-filter-bar">
          <el-select v-model="selectedSource" size="small" style="width:180px" placeholder="数据源" @change="onSourceChange">
            <el-option v-for="s in sourceOptions" :key="s.key" :label="s.label" :value="s.key" />
          </el-select>
          <el-input v-model="filterText" size="small" style="width:200px" placeholder="科目名/行次过滤..." clearable />
          <el-select v-if="selectedSource.startsWith('report')" v-model="filterReportType" size="small" style="width:140px" placeholder="报表类型">
            <el-option label="资产负债表" value="balance_sheet" />
            <el-option label="利润表" value="income_statement" />
            <el-option label="现金流量表" value="cash_flow_statement" />
          </el-select>
          <el-button size="small" type="primary" @click="executeQuery" :loading="loading">▶ 查询</el-button>
          <span style="flex:1" />
          <el-button size="small" @click="transposed = !transposed">{{ transposed ? '↩ 还原' : '↔ 转置' }}</el-button>
          <el-button size="small" @click="copyResult">📋 复制</el-button>
          <el-button size="small" @click="exportResult">📤 导出</el-button>
        </div>
        <!-- 结果表格 -->
        <el-table v-if="!transposed" :data="filteredRows" v-loading="loading" border size="small"
          max-height="calc(100vh - 200px)" style="width:100%" :header-cell-style="{ background: '#f0edf5', fontSize: '12px' }">
          <el-table-column v-for="col in resultColumns" :key="col" :prop="col" :label="columnLabel(col)" min-width="120" show-overflow-tooltip>
            <template #default="{ row }">
              <span :style="{ textAlign: isNumeric(row[col]) ? 'right' : 'left', display: 'block' }">
                {{ formatCell(row[col]) }}
              </span>
            </template>
          </el-table-column>
        </el-table>
        <!-- 转置视图 -->
        <div v-else class="gt-cq-transposed" v-loading="loading">
          <el-table :data="transposedRows" border size="small" max-height="calc(100vh - 200px)" style="width:100%"
            :header-cell-style="{ background: '#f0edf5', whiteSpace: 'nowrap', fontSize: '12px' }">
            <el-table-column prop="_field_label" label="字段" width="140" fixed="left" />
            <el-table-column v-for="(_, ci) in transposedDataCols" :key="ci" :prop="'_v' + ci" :label="'#' + (ci + 1)" min-width="120" show-overflow-tooltip>
              <template #default="{ row }">
                <span style="display:block; text-align:right">{{ row['_v' + ci] }}</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
        <div class="gt-cq-footer">
          <span style="font-size: var(--gt-font-size-xs);color: var(--gt-color-text-tertiary)">{{ resultRows.length }} 行 × {{ resultColumns.length }} 列{{ filterText ? `（过滤后 ${filteredRows.length} 行）` : '' }}</span>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { handleApiError } from '@/utils/errorHandler'
import { api } from '@/services/apiProxy'
import { fmtAmount } from '@/utils/formatters'

const props = defineProps<{ modelValue: boolean; projectId: string; year: number }>()
const emit = defineEmits<{ 'update:modelValue': [val: boolean] }>()
const visible = computed({ get: () => props.modelValue, set: (v) => emit('update:modelValue', v) })

const loading = ref(false)
const transposed = ref(false)
const filterText = ref('')
const selectedSource = ref('report_balance_sheet')
const filterReportType = ref('balance_sheet')
const resultRows = ref<any[]>([])
const resultColumns = ref<string[]>([])
const indicatorTree = ref<any[]>([])

const sourceOptions = [
  { key: 'report_balance_sheet', label: '📊 资产负债表' },
  { key: 'report_income_statement', label: '📊 利润表' },
  { key: 'report_cash_flow_statement', label: '📊 现金流量表' },
  { key: 'tb_detail', label: '📋 科目明细' },
  { key: 'tb_summary', label: '📋 试算平衡表' },
  { key: 'disclosure_note', label: '📝 附注数据' },
  { key: 'adj_aje', label: '📐 审计调整(AJE)' },
  { key: 'adj_rcl', label: '📐 重分类(RCL)' },
  { key: 'ws_info', label: '📑 基本信息表' },
  { key: 'ws_elimination', label: '📑 抵消分录' },
]

const filteredRows = computed(() => {
  if (!filterText.value) return resultRows.value
  const kw = filterText.value.toLowerCase()
  return resultRows.value.filter(r => Object.values(r).some(v => String(v).toLowerCase().includes(kw)))
})

// 转置视图数据：每个原始列变成一行，每个原始行变成一列
const transposedDataCols = computed(() => filteredRows.value.slice(0, 50))
const transposedRows = computed(() => {
  const rows = transposedDataCols.value
  return resultColumns.value.map(col => {
    const entry: Record<string, any> = { _field_label: columnLabel(col) }
    rows.forEach((row, ci) => { entry['_v' + ci] = formatCell(row[col]) })
    return entry
  })
})

const COLUMN_LABELS: Record<string, string> = {
  row_code: '行次', row_name: '项目', current_period_amount: '本期金额', prior_period_amount: '上期金额',
  account_code: '科目编码', account_name: '科目名称', opening_balance: '期初余额', closing_balance: '期末余额',
  debit_amount: '借方发生额', credit_amount: '贷方发生额', unadjusted: '未审数', audited: '审定数',
  aje_dr: 'AJE借', aje_cr: 'AJE贷', rcl_dr: 'RCL借', rcl_cr: 'RCL贷',
  entry_number: '分录号', description: '说明', status: '状态', section_id: '章节ID',
  company_name: '企业名称', company_code: '企业代码', holding_type: '持股类型',
  direction: '借贷', subject: '科目', amount: '金额', desc: '说明',
  summary: '审定汇总', equity_dr: '权益抵消借', equity_cr: '权益抵消贷',
  indent: '层级', is_total: '合计行', non_common_ratio: '持股比例',
  headers: '表头', row_count: '行数',
}
function columnLabel(col: string) { return COLUMN_LABELS[col] || col }
function isNumeric(v: any) { return v != null && !isNaN(Number(v)) }
function formatCell(v: any) {
  if (v == null) return '-'
  if (Array.isArray(v)) return v.join(', ')
  if (typeof v === 'boolean') return v ? '是' : '否'
  const s = String(v)
  // 不格式化长字符串（如信用代码、编码等）
  if (s.length > 12 || /[a-zA-Z\u4e00-\u9fff]/.test(s)) return s
  const n = Number(v)
  if (!isNaN(n) && s.trim() !== '') return fmtAmount(n)
  return s
}

function onIndicatorClick(data: any) {
  if (data.key && !data.children?.length) {
    selectedSource.value = data.key
    if (data.key.startsWith('report_')) filterReportType.value = data.key.replace('report_', '')
  }
}

function onSourceChange() {
  if (selectedSource.value.startsWith('report_')) filterReportType.value = selectedSource.value.replace('report_', '')
}

async function executeQuery() {
  if (!props.projectId) { ElMessage.warning('请先选择项目'); return }
  loading.value = true
  try {
    const source = selectedSource.value
    const filters: Record<string, any> = {}
    if (source.startsWith('report_')) filters.report_type = filterReportType.value
    if (source === 'adj_aje') filters.adjustment_type = 'AJE'
    if (source === 'adj_rcl') filters.adjustment_type = 'RCL'
    if (source.startsWith('ws_')) filters.sheet_key = source.replace('ws_', '')
    if (filterText.value && (source === 'tb_detail')) filters.account_name = filterText.value

    const data = await api.post('/api/custom-query/execute', {
      project_id: props.projectId, year: props.year, source, filters,
    }, { validateStatus: (s: number) => s < 600 })
    const result = data
    resultRows.value = result?.rows || []
    resultColumns.value = result?.columns || (resultRows.value.length ? Object.keys(resultRows.value[0]) : [])
    if (!resultRows.value.length) ElMessage.info('查询无结果')
  } catch (err: any) {
    handleApiError(err, '查询失败')
  } finally { loading.value = false }
}

function copyResult() {
  if (!resultRows.value.length) { ElMessage.warning('无数据'); return }
  const headers = resultColumns.value.map(c => columnLabel(c))
  const dataRows = filteredRows.value.map(r => resultColumns.value.map(c => r[c] ?? ''))
  const text = [headers.join('\t'), ...dataRows.map(r => r.join('\t'))].join('\n')
  const html = `<table border="1"><tr>${headers.map(h => `<th>${h}</th>`).join('')}</tr>${dataRows.map(r => `<tr>${r.map(c => `<td>${c}</td>`).join('')}</tr>`).join('')}</table>`
  try {
    navigator.clipboard.write([new ClipboardItem({ 'text/html': new Blob([html], { type: 'text/html' }), 'text/plain': new Blob([text], { type: 'text/plain' }) })])
    ElMessage.success(`已复制 ${filteredRows.value.length} 行`)
  } catch { navigator.clipboard?.writeText(text); ElMessage.success('已复制为文本') }
}

async function exportResult() {
  if (!resultRows.value.length) { ElMessage.warning('无数据'); return }
  const XLSX = await import('xlsx')
  const wb = XLSX.utils.book_new()
  const headers = resultColumns.value.map(c => columnLabel(c))
  const dataRows = filteredRows.value.map(r => resultColumns.value.map(c => r[c] ?? ''))
  const ws = XLSX.utils.aoa_to_sheet([headers, ...dataRows])
  ws['!cols'] = headers.map(() => ({ wch: 16 }))
  XLSX.utils.book_append_sheet(wb, ws, '查询结果')
  XLSX.writeFile(wb, `自定义查询_${selectedSource.value}_${props.year}.xlsx`)
  ElMessage.success('已导出')
}

// 加载指标树
async function loadIndicators() {
  try {
    const data = await api.get('/api/custom-query/indicators')
    indicatorTree.value = Array.isArray(data) ? data : (data ?? [])
  } catch { indicatorTree.value = sourceOptions.map(s => ({ key: s.key, label: s.label })) }
}
loadIndicators()
</script>

<style scoped>
.gt-cq-container { display: flex; gap: 12px; height: calc(100vh - 140px); }
.gt-cq-sidebar { width: 200px; flex-shrink: 0; border-right: 1px solid var(--gt-color-border-purple); padding-right: 8px; overflow-y: auto; }
.gt-cq-sidebar-title { font-size: var(--gt-font-size-sm); font-weight: 600; color: var(--gt-color-primary); margin-bottom: 8px; }
.gt-cq-main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.gt-cq-filter-bar { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.gt-cq-footer { padding: 6px 0; }
.gt-cq-transposed { overflow: auto; flex: 1; }
</style>
