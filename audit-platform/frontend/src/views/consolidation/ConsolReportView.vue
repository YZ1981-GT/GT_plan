<template>
  <div class="gt-consol-report-view">
    <!-- 顶部工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <!-- 报表类型切换 -->
        <el-radio-group v-model="reportType" size="default" @change="onReportTypeChange">
          <el-radio-button value="balance_sheet">资产负债表</el-radio-button>
          <el-radio-button value="income_statement">利润表</el-radio-button>
          <el-radio-button value="cash_flow">现金流量表</el-radio-button>
        </el-radio-group>

        <!-- 期间选择 -->
        <el-date-picker
          v-model="period"
          type="month"
          format="YYYY-MM"
          value-format="YYYY-MM"
          placeholder="选择期间"
          style="width: 140px"
          @change="loadReport"
        />
      </div>

      <div class="toolbar-right">
        <!-- 视图切换 -->
        <el-radio-group v-model="viewMode" size="default">
          <el-radio-button value="preview">预览</el-radio-button>
          <el-radio-button value="edit">编辑</el-radio-button>
          <el-radio-button value="print">打印</el-radio-button>
        </el-radio-group>

        <!-- 导出按钮 -->
        <el-dropdown @command="onExport" trigger="click">
          <el-button type="primary" plain>
            <el-icon><Download /></el-icon> 导出
            <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="excel">
                <el-icon><Document /></el-icon> 下载 Excel
              </el-dropdown-item>
              <el-dropdown-item command="pdf">
                <el-icon><Reading /></el-icon> 下载 PDF
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>

        <!-- 操作按钮 -->
        <el-button :loading="loading" @click="onRefresh" plain>
          <el-icon><Refresh /></el-icon> 刷新
        </el-button>
        <el-button type="primary" @click="onSubmitReview" :disabled="viewMode !== 'edit'">
          <el-icon><Select /></el-icon> 提交复核
        </el-button>
      </div>
    </div>

    <!-- 报表内容区域 -->
    <div class="report-content" v-loading="loading">
      <!-- 标准三表 -->
      <el-card class="report-card" shadow="never" v-if="reportData">
        <!-- 报表标题 -->
        <div class="report-header">
          <h2 class="report-title">{{ reportTitle }}</h2>
          <p class="report-period">期间：{{ period }}</p>
        </div>

        <!-- 标准报表表格 -->
        <el-table
          :data="reportRows"
          border
          stripe
          size="small"
          :max-height="tableMaxHeight"
          :header-cell-style="headerCellStyle"
          class="report-table"
          :class="{ 'edit-mode': viewMode === 'edit' }"
        >
          <el-table-column prop="line_no" label="行次" width="60" align="center" />
          <el-table-column prop="account_code" label="科目编码" width="100" />
          <el-table-column prop="account_name" label="科目名称" min-width="200" fixed />

          <!-- 底稿视图列 -->
          <template v-if="viewMode === 'edit'">
            <el-table-column label="调整前金额" align="right" width="140">
              <template #default="{ row }">
                <el-input-number
                  v-if="isEditable(row)"
                  v-model="row.before_amount"
                  :precision="2"
                  size="small"
                  controls-position="right"
                  @change="onCellChange(row)"
                />
                <span v-else class="amount">{{ formatNum(row.before_amount) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="调整分录" align="right" width="140">
              <template #default="{ row }">
                <span class="amount adjustment">{{ formatNum(row.adjustment) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="调整后金额" align="right" width="140">
              <template #default="{ row }">
                <span class="amount">{{ formatNum(row.after_amount) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="合并金额" align="right" width="140">
              <template #default="{ row }">
                <el-input-number
                  v-if="isEditable(row)"
                  v-model="row.consol_amount"
                  :precision="2"
                  size="small"
                  controls-position="right"
                  @change="onCellChange(row)"
                />
                <span v-else class="amount bold">{{ formatNum(row.consol_amount) }}</span>
              </template>
            </el-table-column>
          </template>

          <!-- 预览/打印视图列 -->
          <template v-else>
            <el-table-column label="合并金额" align="right" width="160">
              <template #default="{ row }">
                <span
                  class="amount bold"
                  :class="getAmountClass(row.consol_amount)"
                >{{ formatNum(row.consol_amount) }}</span>
              </template>
            </el-table-column>
          </template>
        </el-table>

        <!-- 新增行次展示（资产负债表特有） -->
        <template v-if="reportType === 'balance_sheet' && extraRows.length">
          <div class="extra-section">
            <h4 class="section-title">新增行次</h4>
            <el-table
              :data="extraRows"
              border
              stripe
              size="small"
              :header-cell-style="headerCellStyle"
              class="extra-table"
            >
              <el-table-column prop="account_name" label="项目" min-width="260" />
              <el-table-column label="行次" width="60" align="center">
                <template #default="{ row }">
                  {{ row.line_no || '—' }}
                </template>
              </el-table-column>
              <el-table-column label="合并金额" align="right" width="160">
                <template #default="{ row }">
                  <span class="amount">{{ formatNum(row.consol_amount) }}</span>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </template>

        <!-- 利润表新增行次 -->
        <template v-if="reportType === 'income_statement' && incomeExtraRows.length">
          <div class="extra-section">
            <h4 class="section-title">新增行次</h4>
            <el-table
              :data="incomeExtraRows"
              border
              stripe
              size="small"
              :header-cell-style="headerCellStyle"
              class="extra-table"
            >
              <el-table-column prop="account_name" label="项目" min-width="260" />
              <el-table-column label="行次" width="60" align="center">
                <template #default="{ row }">
                  {{ row.line_no || '—' }}
                </template>
              </el-table-column>
              <el-table-column label="合并金额" align="right" width="160">
                <template #default="{ row }">
                  <span class="amount">{{ formatNum(row.consol_amount) }}</span>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </template>

        <!-- 同比分析区 -->
        <div class="yoy-analysis" v-if="yoyData.length">
          <el-card class="yoy-card" shadow="never">
            <template #header>
              <div class="yoy-header">
                <span class="yoy-title">同比分析</span>
                <span class="yoy-period">对比期间：{{ priorPeriod }}</span>
              </div>
            </template>
            <el-table
              :data="yoyData"
              border
              stripe
              size="small"
              max-height="240"
              :header-cell-style="headerCellStyle"
            >
              <el-table-column prop="account_name" label="科目" min-width="200" />
              <el-table-column label="本年合并数" align="right" width="140">
                <template #default="{ row }">
                  <span class="amount">{{ formatNum(row.current_amount) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="上年合并数" align="right" width="140">
                <template #default="{ row }">
                  <span class="amount">{{ formatNum(row.prior_amount) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="同比增减" align="right" width="140">
                <template #default="{ row }">
                  <span
                    class="amount"
                    :class="getChangeClass(row.change)"
                  >
                    {{ formatSignedNum(row.change) }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="增减%" align="right" width="100">
                <template #default="{ row }">
                  <span
                    class="amount"
                    :class="getChangeClass(row.change_pct)"
                  >
                    {{ row.change_pct ? row.change_pct + '%' : '—' }}
                  </span>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </div>

        <!-- 打印模式下显示页脚 -->
        <div class="report-footer" v-if="viewMode === 'print'">
          <p>编制人：__________ 复核人：__________ 批准人：__________</p>
          <p>编制日期：{{ new Date().toLocaleDateString('zh-CN') }}</p>
        </div>
      </el-card>

      <!-- 无数据提示 -->
      <el-empty v-else-if="!loading" description="暂无报表数据" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Download, ArrowDown, Document, Reading, Select } from '@element-plus/icons-vue'
import {
  getConsolReport,
  saveConsolReport,
  downloadConsolReportExcel,
  downloadConsolReportPDF,
  getYoYAnalysis,
  type ConsolReportData,
  type ConsolReportRow,
  type ReportType,
  type YoYAnalysis,
} from '@/services/consolidationApi'

// ─── Props & Emits ────────────────────────────────────────────────────────────
const props = defineProps<{
  projectId: string
  period?: string
}>()

const emit = defineEmits<{
  'data-loaded': [data: ConsolReportData]
}>()

// ─── State ────────────────────────────────────────────────────────────────────
const loading = ref(false)
const exporting = ref(false)
const reportType = ref<ReportType>('balance_sheet')
const period = ref(props.period || new Date().toISOString().slice(0, 7))
const viewMode = ref<'preview' | 'edit' | 'print'>('preview')
const reportData = ref<ConsolReportData | null>(null)
const yoyData = ref<YoYAnalysis[]>([])
const editedRows = ref<Map<string, Partial<ConsolReportRow>>>(new Map())

const tableMaxHeight = ref(600)

// ─── Computed ─────────────────────────────────────────────────────────────────
const reportTitle = computed(() => {
  const titles: Record<ReportType, string> = {
    balance_sheet: '合并资产负债表',
    income_statement: '合并利润表',
    cash_flow: '合并现金流量表',
  }
  return titles[reportType.value]
})

const priorPeriod = computed(() => {
  const [year, month] = period.value.split('-').map(Number)
  const prior = month === 1 ? 12 : month - 1
  const priorYear = month === 1 ? year - 1 : year
  return `${priorYear}-${String(prior).padStart(2, '0')}`
})

// 过滤出标准报表行（排除新增行次）
const reportRows = computed(() => {
  if (!reportData.value) return []
  return reportData.value.rows.filter(r => !isExtraRow(r))
})

// 资产负债表新增行次
const extraRows = computed(() => {
  if (!reportData.value || reportType.value !== 'balance_sheet') return []
  return reportData.value.rows.filter(r =>
    ['商誉', '少数股东权益', '少数股东权益合计', '少数股东损益'].includes(r.account_name)
  )
})

// 利润表新增行次
const incomeExtraRows = computed(() => {
  if (!reportData.value || reportType.value !== 'income_statement') return []
  return reportData.value.rows.filter(r =>
    ['少数股东损益', '归属于母公司净利润'].includes(r.account_name)
  )
})

// ─── Methods ───────────────────────────────────────────────────────────────────
const headerCellStyle = computed(() => ({
  background: 'var(--gt-color-primary)',
  color: '#fff',
  fontWeight: '600',
  fontSize: '13px',
}))

function formatNum(val: string | number | undefined): string {
  if (val === undefined || val === null || val === '') return '—'
  const num = typeof val === 'string' ? parseFloat(val) : val
  if (isNaN(num)) return '—'
  return num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatSignedNum(val: string | number | undefined): string {
  if (val === undefined || val === null || val === '') return '—'
  const num = typeof val === 'string' ? parseFloat(val) : val
  if (isNaN(num)) return '—'
  const sign = num >= 0 ? '+' : ''
  return sign + num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function getAmountClass(val: string | number | undefined): string {
  if (val === undefined || val === null || val === '') return ''
  const num = typeof val === 'string' ? parseFloat(val) : val
  if (isNaN(num)) return ''
  return num < 0 ? 'credit' : 'debit'
}

function getChangeClass(val: string | number | undefined): string {
  if (val === undefined || val === null || val === '') return ''
  const num = typeof val === 'string' ? parseFloat(val) : val
  if (isNaN(num)) return ''
  if (num > 0) return 'positive'
  if (num < 0) return 'negative'
  return ''
}

function isExtraRow(row: ConsolReportRow): boolean {
  return ['商誉', '少数股东权益', '少数股东权益合计', '少数股东损益', '归属于母公司净利润'].includes(row.account_name)
}

function isEditable(_row: ConsolReportRow): boolean {
  return viewMode.value === 'edit'
}

function onCellChange(row: ConsolReportRow) {
  const key = row.line_no
  if (!editedRows.value.has(key)) {
    editedRows.value.set(key, {})
  }
  const edits = editedRows.value.get(key)!
  edits.before_amount = row.before_amount
  edits.consol_amount = row.consol_amount
}

// ─── Data Loading ─────────────────────────────────────────────────────────────
async function loadReport() {
  loading.value = true
  try {
    reportData.value = await getConsolReport(props.projectId, reportType.value, period.value)
    yoyData.value = await getYoYAnalysis(props.projectId, reportType.value, period.value)
    editedRows.value.clear()
    emit('data-loaded', reportData.value)
  } catch (e: any) {
    ElMessage.error(e?.message || '加载合并报表失败')
  } finally {
    loading.value = false
  }
}

async function onRefresh() {
  await loadReport()
  ElMessage.success('刷新成功')
}

async function onReportTypeChange() {
  await loadReport()
}

async function onSubmitReview() {
  try {
    await ElMessageBox.confirm('确认提交复核？提交后将锁定报表编辑。', '提交复核', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await saveConsolReport(props.projectId, reportType.value, period.value, {
      ...reportData.value!,
      rows: reportRows.value,
    } as any)
    ElMessage.success('提交复核成功')
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e?.message || '提交复核失败')
    }
  }
}

async function onExport(command: 'excel' | 'pdf') {
  exporting.value = true
  try {
    let url: string
    if (command === 'excel') {
      url = await downloadConsolReportExcel(props.projectId, reportType.value, period.value)
      ElMessage.success('Excel 导出任务已提交')
    } else {
      url = await downloadConsolReportPDF(props.projectId, reportType.value, period.value)
      ElMessage.success('PDF 导出任务已提交')
    }
    if (url) {
      const a = document.createElement('a')
      a.href = url
      a.download = ''
      a.click()
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '导出失败')
  } finally {
    exporting.value = false
  }
}

// ─── Lifecycle ─────────────────────────────────────────────────────────────────
onMounted(() => {
  loadReport()
})

watch(() => props.projectId, () => {
  if (props.projectId) loadReport()
})

watch(() => props.period, (val) => {
  if (val) {
    period.value = val
    loadReport()
  }
})
</script>

<style scoped>
.gt-consol-report-view {
  display: flex;
  flex-direction: column;
  gap: var(--gt-space-4, 12px);
  padding: var(--gt-space-4, 12px);
  height: 100%;
  box-sizing: border-box;
}

/* 工具栏 */
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--gt-space-3, 8px);
  padding: var(--gt-space-3, 8px) var(--gt-space-4, 12px);
  background: var(--gt-color-primary-light, #A06DFF);
  border-radius: var(--gt-radius-md, 8px);
  box-shadow: var(--gt-shadow-sm, 0 1px 3px rgba(75,45,119,0.075));
}

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: var(--gt-space-3, 8px);
  flex-wrap: wrap;
}

/* 报表内容 */
.report-content {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.report-card {
  border-radius: var(--gt-radius-md, 8px);
  overflow: hidden;
}

/* 报表头部 */
.report-header {
  text-align: center;
  margin-bottom: var(--gt-space-6, 20px);
  padding-bottom: var(--gt-space-4, 12px);
  border-bottom: 2px solid var(--gt-color-primary, #4b2d77);
}

.report-title {
  margin: 0 0 var(--gt-space-2, 4px);
  font-size: 18px;
  font-weight: 600;
  color: var(--gt-color-primary, #4b2d77);
}

.report-period {
  margin: 0;
  font-size: 13px;
  color: #666;
}

/* 报表表格 */
.report-table {
  font-size: 13px;
}

.report-table :deep(.el-table__header th) {
  background: var(--gt-color-primary, #4b2d77) !important;
  color: #fff;
  font-weight: 600;
}

.amount {
  font-family: 'Helvetica Neue', Arial, sans-serif;
  font-size: 13px;
}

.amount.bold {
  font-weight: 700;
}

.amount.debit {
  color: #333;
}

.amount.credit {
  color: var(--gt-color-coral, #FF5149);
}

.amount.adjustment {
  color: var(--gt-color-teal, #0094B3);
}

.amount.positive {
  color: var(--gt-color-success, #28A745);
}

.amount.negative {
  color: var(--gt-color-coral, #FF5149);
}

/* 编辑模式 */
.report-table.edit-mode :deep(.el-table__body tr:hover > td) {
  background-color: #f5f0ff;
}

/* 新增行次区域 */
.extra-section {
  margin-top: var(--gt-space-6, 20px);
  padding-top: var(--gt-space-4, 12px);
  border-top: 1px dashed #ddd;
}

.section-title {
  margin: 0 0 var(--gt-space-3, 8px);
  font-size: 14px;
  font-weight: 600;
  color: var(--gt-color-primary, #4b2d77);
}

.extra-table {
  font-size: 13px;
}

/* 同比分析 */
.yoy-analysis {
  margin-top: var(--gt-space-6, 20px);
  padding-top: var(--gt-space-4, 12px);
  border-top: 1px dashed #ddd;
}

.yoy-card {
  border-radius: var(--gt-radius-md, 8px);
}

.yoy-card :deep(.el-card__header) {
  background: var(--gt-color-primary, #4b2d77);
  color: #fff;
  padding: 8px 12px;
}

.yoy-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.yoy-title {
  font-weight: 600;
  font-size: 14px;
}

.yoy-period {
  font-size: 12px;
  opacity: 0.85;
}

/* 报表页脚 */
.report-footer {
  margin-top: var(--gt-space-8, 28px);
  padding-top: var(--gt-space-4, 12px);
  border-top: 1px solid #ddd;
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  color: #666;
}

.report-footer p {
  margin: var(--gt-space-1, 2px) 0;
}
</style>
