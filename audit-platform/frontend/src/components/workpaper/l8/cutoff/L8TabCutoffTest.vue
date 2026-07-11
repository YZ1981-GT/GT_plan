<template>
  <div class="l8-tab-cutoff-test">
    <!-- ═══ 标题 + 操作栏 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">L8-5 截止性测试</h3>
        <el-tag type="danger" size="small">序时账±{{ cutoffDays }}天</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" type="success" :disabled="isReadonly || !reportDate" :loading="isExtracting" @click="handleAutoExtract">
          <el-icon><Download /></el-icon> 自动提取
        </el-button>
        <el-button size="small" :disabled="isReadonly" @click="handleAddRow">
          <el-icon><Plus /></el-icon> 新增行
        </el-button>
        <el-dropdown :disabled="isReadonly" @command="handleImportExport" trigger="click">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item command="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item command="importData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="handleAI('cutoff')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 审计目标 ═══ -->
    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
      <template #title>
        <strong>审计目标：</strong>核查报告日前后财务费用的期间归属正确性，识别跨期入账，确认费用截止无重大错报。
      </template>
    </el-alert>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>截止测试（损益类关键程序）：</strong>
        以报告日为基准，提取前后±N天的序时账分录，核查是否存在跨期入账的费用。
        跨期判定：应归属期间 ≠ 实际入账期间。跨期条目红色高亮，需进一步核实是否构成错报。
        集成 useCutoffAutoSampling 自动提取 + GtVoucherSamplingEngine 行级抽凭。
      </div>
    </div>

    <!-- ═══ 参数设置栏 ═══ -->
    <div class="param-bar">
      <div class="param-item">
        <span class="param-label">报告截止日：</span>
        <el-date-picker
          v-model="reportDate"
          type="date"
          value-format="YYYY-MM-DD"
          size="small"
          placeholder="选择截止日"
          :disabled="isReadonly"
          style="width: 160px"
        />
      </div>
      <div class="param-item">
        <span class="param-label">窗口天数：±</span>
        <el-input-number
          v-model="cutoffDays"
          :min="1"
          :max="30"
          size="small"
          style="width: 100px"
          :disabled="isReadonly"
        />
        <span class="param-label">天</span>
      </div>
    </div>

    <!-- ═══ 区段切换（期前/期后） ═══ -->
    <el-segmented v-model="activeSection" :options="sectionOptions" size="default" class="segment-switcher" />

    <!-- ═══ 跨期统计汇总 ═══ -->
    <div class="cutoff-summary">
      <el-statistic title="总测试笔数" :value="currentSummary.totalCount" />
      <el-statistic title="跨期笔数" :value="currentSummary.crossCount">
        <template #suffix>
          <el-tag v-if="currentSummary.crossCount > 0" type="danger" size="small">跨期</el-tag>
        </template>
      </el-statistic>
      <el-statistic title="跨期金额" :value="currentSummary.crossAmountTotal" :precision="2" />
      <el-statistic title="跨期率" :value="currentSummary.crossRate" :precision="1" suffix="%" />
    </div>

    <!-- ═══ 截止测试表 ═══ -->
    <el-table
      :data="currentRows"
      border
      size="small"
      style="width: 100%"
      :row-class-name="getCutoffRowClass"
      highlight-current-row
    >
      <el-table-column type="index" label="#" width="50" align="center" fixed />

      <el-table-column label="凭证日期" width="120">
        <template #default="{ row, $index }">
          <el-date-picker v-if="!isReadonly" :model-value="row.voucherDate" type="date" value-format="YYYY-MM-DD" size="small" style="width:100%" @change="(val: string) => handleRowUpdate($index, 'voucherDate', val)" />
          <span v-else>{{ row.voucherDate || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="凭证编号" width="100">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small" @change="(val: string) => handleRowUpdate($index, 'voucherNo', val)" />
          <span v-else>{{ row.voucherNo || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="摘要/内容" min-width="180">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" :model-value="row.voucherContent" size="small" @change="(val: string) => handleRowUpdate($index, 'voucherContent', val)" />
          <span v-else>{{ row.voucherContent || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="对方科目" width="130">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" :model-value="row.counterAccount" size="small" @change="(val: string) => handleRowUpdate($index, 'counterAccount', val)" />
          <span v-else>{{ row.counterAccount || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="金额" width="120" align="right">
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" :model-value="row.voucherAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleRowUpdate($index, 'voucherAmount', val ?? 0)" />
          <span v-else>{{ fmtAmount(row.voucherAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="应归属期间" width="120">
        <template #default="{ row, $index }">
          <el-date-picker v-if="!isReadonly" :model-value="row.attributionPeriod" type="month" value-format="YYYY-MM" size="small" style="width:100%" @change="(val: string) => handleRowUpdate($index, 'attributionPeriod', val)" />
          <span v-else>{{ row.attributionPeriod || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="入账期间" width="120">
        <template #default="{ row, $index }">
          <el-date-picker v-if="!isReadonly" :model-value="row.bookingPeriod" type="month" value-format="YYYY-MM" size="small" style="width:100%" @change="(val: string) => handleRowUpdate($index, 'bookingPeriod', val)" />
          <span v-else>{{ row.bookingPeriod || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="跨期" width="70" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.isCrossPeriod" type="danger" size="small">跨期</el-tag>
          <span v-else class="pass-mark">✓</span>
        </template>
      </el-table-column>

      <el-table-column label="跨期金额" width="110" align="right">
        <template #default="{ row }">
          <span :class="{ 'cross-period-amount': row.crossPeriodAmount > 0 }">
            {{ row.crossPeriodAmount > 0 ? fmtAmount(row.crossPeriodAmount) : '—' }}
          </span>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="操作" width="70" align="center" fixed="right">
        <template #default="{ $index }">
          <el-popconfirm title="确认删除？" @confirm="handleRemoveRow($index)">
            <template #reference>
              <el-button type="danger" text size="small">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 审计说明（el-card包裹） ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">截止测试结论</span>
          <el-button size="small" @click="handleAI('conclusion')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="cutoffConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="对截止测试发现的跨期事项进行总结说明..."
        :disabled="isReadonly"
        @change="saveCutoffConclusion"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="l8-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>截止测试是损益类科目关键审计程序，检查期末前后费用的归属期间正确性</li>
        <li>默认窗口±5天（可调整），自动提取调用序时账API</li>
        <li>跨期判定：应归属期间 ≠ 实际入账期间（红色高亮）</li>
        <li>期前测试：报告日之前N天内入账、但应归属本期的费用</li>
        <li>期后测试：报告日之后N天内入账、但应归属上期的费用</li>
        <li>支持行级抽凭（集成GtVoucherSamplingEngine）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L8TabCutoffTest — L8-5 截止性测试（序时账±天数自动提取）
 *
 * Requirements: 6.1-6.5
 * - 双区段（期前/期后）el-segmented切换
 * - 跨期条目红色高亮
 * - 自动提取按钮（调cutoff-extract API）
 * - 行级抽凭（GtVoucherSamplingEngine集成）
 * - 导入导出三级
 */
import { computed, inject, onMounted, ref } from 'vue'
import { Plus, MagicStick, Check, Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useL8FormData } from '../../composables/useL8FormData'
import {
  useL8CutoffTest,
  type L8CutoffTestRow,
  type L8CutoffSection,
} from '../../composables/useL8CutoffTest'
import { useL8ImportExport } from '../../composables/useL8ImportExport'
import { api } from '@/services/apiProxy'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── FormData + Composables ──────────────────────────────────────────────────

const formData = useL8FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const prePeriodRows = ref<L8CutoffTestRow[]>([])
const postPeriodRows = ref<L8CutoffTestRow[]>([])

const {
  activeSection,
  reportDate,
  cutoffDays,
  switchSection,
  computedPreRows,
  computedPostRows,
  preSummary,
  postSummary,
  overallSummary,
  autoExtractFromLedger,
  addRow: composableAddRow,
  removeRow: composableRemoveRow,
  updateRow: composableUpdateRow,
} = useL8CutoffTest(formData, prePeriodRows, postPeriodRows)

const { exportTemplate, exportData, importData } = useL8ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── State ───────────────────────────────────────────────────────────────────

const isExtracting = ref(false)
const cutoffConclusion = ref('')

// ─── Computed ────────────────────────────────────────────────────────────────

const sectionOptions = [
  { label: '期前测试', value: 'pre-period' },
  { label: '期后测试', value: 'post-period' },
]

const currentRows = computed(() => {
  return activeSection.value === 'pre-period' ? computedPreRows.value : computedPostRows.value
})

const currentSummary = computed(() => {
  return activeSection.value === 'pre-period' ? preSummary.value : postSummary.value
})

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleAddRow() { composableAddRow(activeSection.value) }
function handleRemoveRow(index: number) { composableRemoveRow(activeSection.value, index) }
function handleRowUpdate(index: number, field: keyof L8CutoffTestRow, value: any) {
  composableUpdateRow(activeSection.value, index, field, value)
}

async function handleAutoExtract() {
  if (!reportDate.value) {
    ElMessage.warning('请先设置报告截止日')
    return
  }
  isExtracting.value = true
  try {
    // 调用截止测试自动提取API
    const data = await api.get(
      `/api/l8-financial-expenses/${props.wpId}/cutoff-extract`,
      { params: { report_date: reportDate.value, days: cutoffDays.value } },
    )
    const ledgerEntries = Array.isArray(data) ? data : (data?.data ?? [])
    // 分配到当前区段
    autoExtractFromLedger(ledgerEntries, activeSection.value)
    ElMessage.success(`已提取 ${currentRows.value.length} 条记录`)
  } catch {
    ElMessage.error('自动提取失败，请检查序时账数据')
  } finally {
    isExtracting.value = false
  }
}

function getCutoffRowClass({ row }: { row: any; rowIndex: number }): string {
  return row.isCrossPeriod ? 'cross-period-row' : ''
}

function handleImportExport(command: string) {
  switch (command) {
    case 'exportTemplate': exportTemplate('L8-5'); break
    case 'exportData': exportData('L8-5'); break
    case 'importData': {
      const input = document.createElement('input')
      input.type = 'file'
      input.accept = '.xlsx,.xls'
      input.onchange = async (e: Event) => {
        const file = (e.target as HTMLInputElement).files?.[0]
        if (file) {
          const result = await importData(file, 'L8-5')
          if (result) ElMessage.success(`导入完成，共 ${result.rowCount} 行`)
        }
      }
      input.click()
      break
    }
  }
}

function handleAI(_section: string) { /* AI辅助待集成 */ }
function handleReview() { openReviewDialog?.('L8-5-cutoff', '截止测试') }

function saveCutoffConclusion() {
  formData.debouncedSave('L8-5-conclusion', { remark: cutoffConclusion.value || null })
}

// ─── Format ──────────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  _restoreData()
})

function _restoreData() {
  const rd = formData.allResponses.value.get('L8-5-reportDate')
  if (rd?.remark) reportDate.value = rd.remark
  const conc = formData.allResponses.value.get('L8-5-conclusion')
  if (conc?.remark) cutoffConclusion.value = conc.remark
}
</script>

<style scoped>
.l8-tab-cutoff-test { padding: 12px; font-size: 13px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: 13px; color: #6b5900; line-height: 1.6; }
.param-bar { display: flex; align-items: center; gap: 24px; margin-bottom: 12px; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; flex-wrap: wrap; }
.param-item { display: flex; align-items: center; gap: 6px; }
.param-label { font-size: 13px; color: #606266; }
.segment-switcher { margin-bottom: 12px; }
.cutoff-summary { display: flex; gap: 32px; margin-bottom: 16px; padding: 12px 16px; background: #fafafa; border-radius: 6px; flex-wrap: wrap; }
:deep(.el-statistic) { text-align: center; }
:deep(.el-statistic__head) { font-size: 12px; color: #909399; }
:deep(.el-statistic__content) { font-size: 18px; font-weight: 600; }
:deep(.el-table) { font-size: 13px; }
:deep(.cross-period-row) { background: #fef0f0 !important; }
:deep(.cross-period-row td) { color: #f56c6c; }
.pass-mark { color: #67c23a; font-weight: 600; }
.cross-period-amount { color: #f56c6c; font-weight: 600; }
.audit-note-card { margin-top: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
.l8-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266; }
.l8-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l8-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
