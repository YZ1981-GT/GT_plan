<template>
  <div class="l8-tab-non-fin-interest">
    <!-- ═══ 标题 + 操作栏 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">L8-4 非金融机构利息支出测算</h3>
        <el-tag type="warning" size="small">税务扣除</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          <el-icon><Plus /></el-icon> 新增借款
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
        <el-button size="small" @click="handleAI('nonFinInterest')">
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
        <strong>审计目标：</strong>测算非金融机构借款利息的可税前扣除限额，识别超标利息并提示纳税调增，核查税务口径的准确性。
      </template>
    </el-alert>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>企业所得税法实施条例第38条：</strong>
        非金融企业向非金融企业借款的利息支出，超过按照金融企业同期同类贷款利率计算的部分不得税前扣除。
        可扣除利息 = 本金 × 同期金融机构基准利率 × 天数/360（税务口径）；
        超标利息 = 实际支付利息 − 可扣除利息（需纳税调增）。
      </div>
    </div>

    <!-- ═══ 超标利息警告 ═══ -->
    <el-alert
      v-if="hasAnyExcess"
      type="warning"
      :closable="false"
      show-icon
      class="excess-alert"
    >
      <template #title>
        存在超标利息 {{ fmtAmount(totalExcessInterest) }} 元，需做纳税调增处理
      </template>
    </el-alert>

    <!-- ═══ 测算表主体 ═══ -->
    <el-table :data="computedRows" border size="small" style="width: 100%" highlight-current-row>
      <el-table-column type="index" label="#" width="50" align="center" fixed />

      <el-table-column label="贷款单位" min-width="150" fixed>
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" :model-value="row.lender" size="small" @change="(val: string) => handleUpdate($index, 'lender', val)" />
          <span v-else>{{ row.lender || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="借款日" width="130">
        <template #default="{ row, $index }">
          <el-date-picker
            v-if="!isReadonly"
            :model-value="row.startDate"
            type="date"
            value-format="YYYY-MM-DD"
            size="small"
            style="width: 100%"
            @change="(val: string) => handleUpdate($index, 'startDate', val)"
          />
          <span v-else>{{ row.startDate || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="还款日" width="130">
        <template #default="{ row, $index }">
          <el-date-picker
            v-if="!isReadonly"
            :model-value="row.endDate"
            type="date"
            value-format="YYYY-MM-DD"
            size="small"
            style="width: 100%"
            @change="(val: string) => handleUpdate($index, 'endDate', val)"
          />
          <span v-else>{{ row.endDate || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="约定年利率" width="110" align="right">
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" :model-value="row.annualRate * 100" :controls="false" :precision="2" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'annualRate', (val ?? 0) / 100)">
            <template #suffix>%</template>
          </el-input-number>
          <span v-else>{{ row.annualRate ? (row.annualRate * 100).toFixed(2) + '%' : '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="基准利率" width="110" align="right">
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" :model-value="row.benchmarkRate * 100" :controls="false" :precision="2" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'benchmarkRate', (val ?? 0) / 100)" />
          <span v-else>{{ row.benchmarkRate ? (row.benchmarkRate * 100).toFixed(2) + '%' : '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="借款本金" width="130" align="right">
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" :model-value="row.principal" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'principal', val ?? 0)" />
          <span v-else>{{ fmtAmount(row.principal) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="计息天数" width="90" align="right">
        <template #header>
          <el-tooltip content="公式: 还款日-借款日（整年365不加1，非整年+1天）" placement="top">
            <span class="formula-col-header">计息天数</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-value">{{ row.interestDays || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="应计利息" width="130" align="right">
        <template #header>
          <el-tooltip content="公式: 年利率×本金/365×天数（actual/365制）" placement="top">
            <span class="formula-col-header">应计利息</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-value">{{ fmtAmount(row.accruedInterest) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="可扣除利息" width="130" align="right">
        <template #header>
          <el-tooltip content="公式: 本金×基准利率×天数/360（税务口径）" placement="top">
            <span class="formula-col-header">可扣除利息</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-value">{{ fmtAmount(row.deductibleInterest) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="超标利息" width="130" align="right">
        <template #header>
          <el-tooltip content="公式: 应计利息 − 可扣除利息（>0需纳税调增）" placement="top">
            <span class="formula-col-header">超标利息</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-value" :class="{ 'excess-highlight': row.isExcess }">
            {{ fmtAmount(row.excessInterest) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="合同索引" width="100">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" :model-value="row.contractRef" size="small" @change="(val: string) => handleUpdate($index, 'contractRef', val)" />
          <span v-else>{{ row.contractRef || '—' }}</span>
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

    <!-- ═══ 汇总栏 ═══ -->
    <div class="summary-bar">
      <span>应计利息合计：<strong class="formula-value">{{ fmtAmount(totalAccruedInterest) }}</strong></span>
      <span>可扣除合计：<strong>{{ fmtAmount(totalDeductibleInterest) }}</strong></span>
      <span class="excess-summary" :class="{ 'has-excess': hasAnyExcess }">
        超标合计：<strong>{{ fmtAmount(totalExcessInterest) }}</strong>
      </span>
    </div>

    <!-- ═══ 差异比对区 ═══ -->
    <el-card shadow="never" class="diff-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">差异 = 测算合计 − 账面合计</span>
          <el-button size="small" @click="handleAI('diff')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <div class="diff-content">
        <div class="diff-row">
          <span>账面利息合计：</span>
          <el-input-number
            v-if="!isReadonly"
            :model-value="bookedInterestTotal"
            :controls="false"
            size="small"
            style="width: 200px"
            @change="(val: number | undefined) => setBookedTotal(val ?? 0)"
          />
          <span v-else>{{ fmtAmount(bookedInterestTotal) }}</span>
        </div>
        <div class="diff-row">
          <span>差异：</span>
          <strong :class="{ 'negative-value': diffVsBooked < 0, 'positive-diff': diffVsBooked > 0 }">
            {{ fmtAmount(diffVsBooked) }}
          </strong>
          <el-tag v-if="Math.abs(diffVsBooked) > 0" :type="Math.abs(diffVsBooked) > 10000 ? 'danger' : 'warning'" size="small">
            {{ diffVsBooked > 0 ? '测算>账面' : '账面>测算' }}
          </el-tag>
        </div>
      </div>
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="l8-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>非金融机构借款：指向非银行/非信托等非金融机构（如股东/关联方/自然人）的借款</li>
        <li>计息天数：IF((还款日-借款日)=365, 365, 还款日-借款日+1)（含头含尾）</li>
        <li>应计利息=年利率×本金/365×天数（actual/365制，实际支付）</li>
        <li>可扣除利息=本金×同期金融机构基准利率×天数/360（税务口径，360天制!）</li>
        <li>超标利息=应计利息−可扣除利息（>0需企业所得税纳税调增）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L8TabNonFinInterest — L8-4 非金融机构利息支出测算表
 *
 * Requirements: 5.1-5.4
 * - 动态行（ElMessageBox.prompt输入贷款单位名称）
 * - 公式列：计息天数/应计利息/可扣除利息/超标利息
 * - 超标利息>0 橙色高亮（税务调整提示）
 * - 差异 = 测算合计 − 账面合计
 * - 导入导出三级
 */
import { computed, inject, onMounted, ref } from 'vue'
import { Plus, MagicStick, Check } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useL8FormData } from '../../composables/useL8FormData'
import {
  useL8NonFinInterest,
  type L8NonFinInterestRow,
} from '../../composables/useL8NonFinInterest'
import { useL8ImportExport } from '../../composables/useL8ImportExport'

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

const nfiRows = ref<L8NonFinInterestRow[]>([])

const {
  computedRows,
  totalAccruedInterest,
  totalDeductibleInterest,
  totalExcessInterest,
  diffVsBooked,
  hasAnyExcess,
  bookedInterestTotal,
  addRow,
  removeRow,
  updateRow,
  setBookedTotal,
} = useL8NonFinInterest(formData, nfiRows)

const { exportTemplate, exportData, importData } = useL8ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleAddRow() { addRow() }
function handleRemoveRow(index: number) { removeRow(index) }
function handleUpdate(index: number, field: keyof L8NonFinInterestRow, value: any) { updateRow(index, field, value) }

function handleImportExport(command: string) {
  switch (command) {
    case 'exportTemplate': exportTemplate('L8-4'); break
    case 'exportData': exportData('L8-4'); break
    case 'importData': {
      const input = document.createElement('input')
      input.type = 'file'
      input.accept = '.xlsx,.xls'
      input.onchange = async (e: Event) => {
        const file = (e.target as HTMLInputElement).files?.[0]
        if (file) {
          const result = await importData(file, 'L8-4')
          if (result) {
            await formData.loadData()
            ElMessage.success(`导入完成，共 ${result.rowCount} 行`)
          }
        }
      }
      input.click()
      break
    }
  }
}

function handleAI(_section: string) { /* AI辅助待集成 */ }
function handleReview() { openReviewDialog?.('L8-4-nonFinInterest', '非金融利息测算') }

// ─── Format ──────────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  _restoreRows()
})

function _restoreRows() {
  const fullData = formData.allResponses.value.get('L8-4-full-data')
  if (fullData?.remark) {
    try {
      const parsed = JSON.parse(fullData.remark)
      if (Array.isArray(parsed) && parsed.length > 0) nfiRows.value = parsed
    } catch { /* keep empty */ }
  }
  // 恢复账面合计
  const booked = formData.allResponses.value.get('L8-4-bookedTotal')
  if (booked?.remark) bookedInterestTotal.value = Number(booked.remark) || 0
}
</script>

<style scoped>
.l8-tab-non-fin-interest { padding: 12px; font-size: 13px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: 13px; color: #6b5900; line-height: 1.6; }
.excess-alert { margin-bottom: 12px; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.excess-highlight { color: #e6a23c !important; font-weight: 700; background: #fef0e6; padding: 2px 4px; border-radius: 3px; }
.negative-value { color: #f56c6c; }
.positive-diff { color: #e6a23c; }
:deep(.el-table) { font-size: 13px; }
.summary-bar { display: flex; gap: 24px; padding: 10px 16px; margin-top: 12px; background: #f5f7fa; border-radius: 6px; font-size: 13px; color: #606266; flex-wrap: wrap; }
.excess-summary.has-excess { color: #e6a23c; font-weight: 600; }
.diff-card { margin-top: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
.diff-content { display: flex; flex-direction: column; gap: 12px; }
.diff-row { display: flex; align-items: center; gap: 12px; }
.l8-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266; }
.l8-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l8-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
