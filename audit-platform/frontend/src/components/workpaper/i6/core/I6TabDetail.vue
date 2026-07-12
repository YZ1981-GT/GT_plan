<template>
  <div class="i6-tab-detail">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p><strong>I6-2 研发费用明细表 — 月度12列横向矩阵：</strong></p>
      <p>固定列(项目名称/研发项目编号) + 1月~12月 + 合计列。异常月份(±30%均值)红色标记。</p>
      <p>顶部ECharts折线图(可折叠)显示月度趋势。动态行(新增研发项目)需先弹窗输入名称。</p>
    </div>

    <!-- ECharts月度趋势图(可折叠) -->
    <details class="chart-details" open>
      <summary>月度趋势图</summary>
      <div ref="chartRef" class="trend-chart"></div>
    </details>

    <!-- 操作栏 -->
    <div class="toolbar-row">
      <span class="row-count">共 {{ rows.length }} 个研发项目</span>
      <div class="toolbar-right">
        <el-button v-if="!isReadonly" type="primary" size="small" @click="handleAddRow">+ 新增项目</el-button>
        <el-dropdown v-if="!isReadonly" trigger="click">
          <el-button size="small">导入导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon></el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExport('template')">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExport('data')">导出数据</el-dropdown-item>
              <el-dropdown-item @click="handleImport">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" type="primary" text @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI
        </el-button>
        <el-button size="small" type="default" text @click="handleReview">复核</el-button>
      </div>
    </div>

    <!-- 月度明细表(固定前2列 + 12月横滚 + 合计) -->
    <el-table :data="rows" border size="small" class="detail-table" max-height="520" scrollbar-always-on :row-class-name="getRowClassName">
      <!-- 固定列: 项目名称 -->
      <el-table-column prop="name" label="研发项目" min-width="140" fixed>
        <template #default="{ row }">
          <span :class="{ 'subtotal-text': row.isSubtotal }">{{ row.name }}</span>
          <el-button v-if="row.isEditable && !isReadonly" size="small" type="danger" text class="row-del" @click="handleRemoveRow(row.rowId)">✕</el-button>
        </template>
      </el-table-column>
      <!-- 固定列: 编号 -->
      <el-table-column prop="code" label="编号" width="80" fixed>
        <template #default="{ row }">
          <el-input v-if="row.isEditable && !isReadonly" v-model="row.code" size="small" @change="onFieldChange" />
          <span v-else>{{ row.code || '-' }}</span>
        </template>
      </el-table-column>
      <!-- 12月份列 -->
      <el-table-column v-for="m in 12" :key="m" :label="`${m}月`" min-width="95" align="right">
        <template #default="{ row }">
          <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.months[m-1]" size="small" :controls="false" @change="onMonthChange(row)" />
          <span v-else :class="{ 'anomaly-cell': isAnomalyMonth(row, m-1) }">{{ fmtAmount(row.months[m-1]) }}</span>
        </template>
      </el-table-column>
      <!-- 合计(公式列) -->
      <el-table-column label="合计" min-width="110" align="right">
        <template #header>
          <el-tooltip content="合计 = SUM(1月~12月)" placement="top">
            <span class="formula-col-header">合计</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-tooltip content="= SUM(1月~12月)" placement="top">
            <span class="formula-value">{{ fmtAmount(row.total) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="操作" width="55" align="center" fixed="right">
        <template #default="{ row }">
          <el-button v-if="row.isEditable" type="danger" link size="small" @click="handleRemoveRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 合计行摘要 -->
    <div class="subtotals-bar">
      <span class="subtotal-label">年度合计：</span>
      <span v-for="m in 12" :key="m" class="subtotal-item">{{ m }}月: {{ fmtAmount(monthlyTotals[m-1]) }}</span>
      <span class="subtotal-item subtotal-total">全年: {{ fmtAmount(grandTotal) }}</span>
    </div>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>固定前2列(项目名称/编号)+12月横滚+合计列，44行×65列</li>
        <li>合计=SUM(1月~12月)，自动计算</li>
        <li>异常月份(偏离均值±30%)红色标记</li>
        <li>新增研发项目需先输入项目名称</li>
        <li>年度合计联动审定表I6-1</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I6TabDetail.vue — I6-2 研发费用明细表（月度12列横向矩阵）
 *
 * 固定列(项目/编号) + 12月份列 + 合计列
 * - 异常月份(±30%均值)红色标记
 * - ECharts折线图(顶部可折叠)
 * - 动态行(新增研发项目) ElMessageBox.prompt输入名称
 * - 导入导出 el-dropdown
 *
 * Spec: .kiro/specs/i6-research-development-expense/
 * Task: 4.3
 */
import { ref, computed, watch, onMounted, inject, nextTick } from 'vue'
import { ArrowDown, MagicStick } from '@element-plus/icons-vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{ 'save': [itemId: string, value: any] }>()
const openReviewDialog = inject<(section?: string) => void>('openReviewDialog', () => {})

// ─── Types ───────────────────────────────────────────────────────────────────
interface DetailRow {
  rowId: string
  name: string
  code: string
  months: number[]  // 12 elements
  total: number
  isSubtotal: boolean
  isEditable: boolean
}

// ─── State ───────────────────────────────────────────────────────────────────
const ITEM_ID = 'I6-2-rows'
const rows = ref<DetailRow[]>([])
const chartRef = ref<HTMLElement>()

const monthlyTotals = computed(() => {
  const totals = new Array(12).fill(0)
  for (const row of rows.value.filter((r) => r.isEditable)) {
    for (let i = 0; i < 12; i++) totals[i] += row.months[i] || 0
  }
  return totals
})

const grandTotal = computed(() => monthlyTotals.value.reduce((s, v) => s + v, 0))

// ─── Load / Save ─────────────────────────────────────────────────────────────
function _load(): void {
  const item = props.allResponses.get(ITEM_ID)
  const raw = item?.remark ?? (typeof item === 'string' ? item : null)
  if (raw) {
    try { const parsed = JSON.parse(raw); if (Array.isArray(parsed)) { rows.value = parsed; _recalc(); return } } catch { /* */ }
  }
  rows.value = [
    _makeRow('人工费', 'RD-01'), _makeRow('材料费', 'RD-02'),
    _makeRow('折旧费', 'RD-03'), _makeRow('无形资产摊销', 'RD-04'),
    _makeRow('设计费', 'RD-05'), _makeRow('装备调试费', 'RD-06'),
    _makeRow('委外研发费', 'RD-07'), _makeRow('其他', 'RD-08'),
  ]
  _recalc()
}

function _makeRow(name: string, code: string): DetailRow {
  return { rowId: `row-${Math.random().toString(36).slice(2, 10)}`, name, code, months: new Array(12).fill(0), total: 0, isSubtotal: false, isEditable: true }
}

function _recalc(): void {
  for (const row of rows.value) { row.total = row.months.reduce((s, v) => s + (v || 0), 0) }
}

function _persist(): void { emit('save', ITEM_ID, JSON.stringify(rows.value)) }

watch(() => props.allResponses, () => _load(), { immediate: true })

function onMonthChange(row: DetailRow): void { row.total = row.months.reduce((s, v) => s + (v || 0), 0); _persist() }
function onFieldChange(): void { _persist() }

// ─── Anomaly detection ───────────────────────────────────────────────────────
function isAnomalyMonth(row: DetailRow, monthIdx: number): boolean {
  const val = row.months[monthIdx] || 0
  const nonZero = row.months.filter((v) => v !== 0)
  if (nonZero.length < 3) return false
  const avg = nonZero.reduce((s, v) => s + v, 0) / nonZero.length
  if (avg === 0) return false
  return Math.abs(val - avg) / Math.abs(avg) > 0.3
}

function getRowClassName({ row }: { row: DetailRow }): string {
  return row.isSubtotal ? 'row-subtotal' : ''
}

// ─── Dynamic rows ────────────────────────────────────────────────────────────
async function handleAddRow(): Promise<void> {
  try {
    const { value: name } = await ElMessageBox.prompt('请输入研发项目名称', '新增研发项目', {
      confirmButtonText: '确定', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '名称不能为空',
    })
    if (!name) return
    rows.value.push(_makeRow(name.trim(), `RD-${String(rows.value.length + 1).padStart(2, '0')}`))
    _persist()
  } catch { /* cancelled */ }
}

function handleRemoveRow(rowId: string): void {
  const idx = rows.value.findIndex((r) => r.rowId === rowId)
  if (idx >= 0) { rows.value.splice(idx, 1); _persist() }
}

// ─── Import/Export ───────────────────────────────────────────────────────────
async function handleExport(type: 'template' | 'data'): Promise<void> {
  try {
    const endpoint = type === 'template' ? 'export-template' : 'export-data'
    const res = await http.get(`/api/workpapers/${props.wpId}/i6/${endpoint}`, { params: { sheet: 'I6-2' }, responseType: 'blob' })
    const blob = res.data instanceof Blob ? res.data : new Blob([res.data])
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url; a.download = `I6-2_明细表${type === 'template' ? '模板' : '数据'}.xlsx`; a.click()
    URL.revokeObjectURL(url)
  } catch { ElMessage.error(`导出${type === 'template' ? '模板' : '数据'}失败`) }
}

async function handleImport(): Promise<void> {
  const input = document.createElement('input'); input.type = 'file'; input.accept = '.xlsx,.xls,.csv'
  input.onchange = async (e: Event) => {
    const file = (e.target as HTMLInputElement).files?.[0]; if (!file) return
    const formData = new FormData(); formData.append('file', file)
    try {
      const res = await http.post(`/api/workpapers/${props.wpId}/i6/import-data`, formData, { params: { sheet: 'I6-2' }, headers: { 'Content-Type': 'multipart/form-data' } })
      const data = res.data?.data ?? res.data
      if (Array.isArray(data?.rows)) { rows.value = data.rows; _recalc(); _persist() }
      ElMessage.success('导入成功')
    } catch { ElMessage.error('导入失败') }
  }
  input.click()
}

// ─── AI / Review ─────────────────────────────────────────────────────────────
async function handleAiGenerate(): Promise<void> {
  try { await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, { section: 'detail', prompt: 'I6研发费用明细表月度分析', context: { wpCode: 'I6-2', rowCount: rows.value.length } }) } catch { /* */ }
}
function handleReview(): void { openReviewDialog('I6-2 明细表') }

// ─── Chart (lazy init) ───────────────────────────────────────────────────────
onMounted(async () => {
  await nextTick()
  if (!chartRef.value) return
  try {
    const echarts = await import('echarts')
    const chart = echarts.init(chartRef.value)
    watch(monthlyTotals, (totals) => {
      chart.setOption({
        tooltip: { trigger: 'axis' },
        xAxis: { type: 'category', data: ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'] },
        yAxis: { type: 'value', name: '金额(元)' },
        series: [{ type: 'line', data: totals, smooth: true, areaStyle: { opacity: 0.15 } }],
        grid: { left: 60, right: 20, top: 30, bottom: 30 },
      })
    }, { immediate: true })
  } catch { /* echarts not available */ }
})

function fmtAmount(v: number | null | undefined): string {
  if (v == null || Math.abs(v) < 0.005) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i6-tab-detail { padding: 16px; font-size: var(--wp-font-size, 13px); }
.methodology-context { border-left: 4px solid #d97706; background: #fffbeb; padding: 12px 16px; margin-bottom: 16px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.8; }
.methodology-context p { margin: 0; }
.methodology-context strong { color: #78350f; }
.chart-details { margin-bottom: 16px; }
.chart-details summary { cursor: pointer; font-weight: 500; font-size: var(--wp-font-size, 13px); color: var(--el-text-color-regular); }
.trend-chart { width: 100%; height: 220px; margin-top: 8px; }
.toolbar-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.toolbar-right { display: flex; align-items: center; gap: 8px; }
.row-count { font-size: 12px; color: var(--el-text-color-secondary); }
.detail-table { font-size: var(--wp-font-size, 13px); }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; padding-bottom: 2px; }
.formula-value { border-bottom: 1px dashed #c0c4cc; cursor: help; padding-bottom: 1px; color: #303133; font-weight: 500; }
.subtotal-text { font-weight: 600; }
.row-del { margin-left: 4px; font-size: 11px; padding: 2px 4px; }
.anomaly-cell { color: #dc2626; font-weight: 600; background: #fef2f2; padding: 1px 4px; border-radius: 2px; }
.detail-table :deep(.row-subtotal td) { font-weight: 600; background: #f0f9ff !important; }
.subtotals-bar { display: flex; align-items: center; gap: 10px; padding: 10px 12px; margin-top: 12px; background: #f0f9ff; border-radius: 6px; font-size: 12px; flex-wrap: wrap; }
.subtotal-label { font-weight: 600; color: #303133; }
.subtotal-item { color: #606266; }
.subtotal-total { font-weight: 600; color: var(--el-color-primary); }
.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
