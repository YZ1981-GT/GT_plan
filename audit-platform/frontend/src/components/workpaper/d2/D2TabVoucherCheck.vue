<script setup lang="ts">
/**
 * D2TabVoucherCheck — 凭证抽查D2-7
 * 抽样参数区 + 凭证明细表(17列) + 进度条 + 底部汇总
 * 集成 GtVoucherSamplingEngine 自动抽凭（Task 11.1）
 */
import { inject, toRef, computed, type Ref } from 'vue'
import { useD2VoucherCheck } from '../composables/useD2VoucherCheck'
import { useD2TabImportExport } from '../composables/useD2TabImportExport'
import { useWorkpaperBrowseMode } from '../composables/useWorkpaperBrowseMode'
import { virtualTextCol, virtualNumCol } from '../composables/virtualColumnHelpers'
import type { VirtualColumn } from '@/composables/useVirtualTable'
import GtIndexChip from '../GtIndexChip.vue'
import GtReviewDot from '../GtReviewDot.vue'
import GtVoucherSamplingEngine from '../voucher-sampling/GtVoucherSamplingEngine.vue'
import type { SampledVoucher, FillMode, Phase } from '../composables/useSamplingAlgorithms'
import type { VoucherSampleRow } from '../composables/useD2VoucherCheck'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  bsDate: string
}>()

const { onExportTemplate, onExportData, onImportFile } = useD2TabImportExport(
  toRef(props, 'wpId') as Ref<string>,
  toRef(props, 'projectId') as Ref<string>,
  'D2-7',
)

const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) => v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

// 复核对话集成 (Task 47.1)
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

function handleCellContextMenu(row: any, column: any, event: MouseEvent): void {
  if (!openReviewDialog) return
  event.preventDefault()
  const field = column?.property || 'unknown'
  const rowKey = row?.seq ?? row?.index ?? 'unknown'
  openReviewDialog(`D2-voucher-${rowKey}-${field}`)
}

function handleContextMenuReview(row: any): void {
  if (!openReviewDialog) return
  openReviewDialog(`D2-voucher-abnormal-${row?.seq ?? 'unknown'}`)
}


const {
  params,
  samples,
  progress,
  abnormalCount,
  abnormalRate,
  addSample,
  removeSample,
  updateCell,
  updateParams,
  autoMarkAllCutoff,
  debounceSave,
} = useD2VoucherCheck({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  bsDate: toRef(props, 'bsDate') as Ref<string>,
})

const browseRows = computed(() =>
  samples.value.map(r => ({
    voucherNo: r.voucherNo,
    voucherDate: r.voucherDate,
    amount: r.amount,
    counterparty: r.counterparty,
    abstract: r.abstract,
  })),
)

const browseRowCount = computed(() => browseRows.value.length)

const virtualColumns = computed<VirtualColumn[]>(() => [
  virtualTextCol('voucherNo', '凭证号', 100),
  virtualTextCol('voucherDate', '凭证日期', 100),
  virtualNumCol('amount', '金额', 110, (v) => displayPrefs.fmtAmount(Number(v) || 0)),
  virtualTextCol('counterparty', '交易对手', 120),
  virtualTextCol('abstract', '摘要', 160),
])

const {
  browseMode,
  useVirtualScroll,
  tableWidth,
  tableHeight,
  toggleBrowseMode,
} = useWorkpaperBrowseMode({
  rows: browseRows,
  virtualColumns,
  tableWidth: 900,
})

// ─── 年度计算（从bsDate提取，如 "2025-12-31" → 2025）─────────────────────────

const year = computed(() => {
  if (props.bsDate && props.bsDate.length >= 4) {
    return parseInt(props.bsDate.slice(0, 4), 10)
  }
  return new Date().getFullYear() - 1
})

// ─── 当前审计阶段（默认年审）────────────────────────────────────────────────

const currentPhase = computed<Phase>(() => 'final')

// ─── 自动抽凭填充处理 (Task 11.1) ───────────────────────────────────────────

function generateRowId(): string {
  return `vc-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

/**
 * 将 SampledVoucher 映射为 D2-7 VoucherSampleRow
 * 映射规则：
 *   voucherNo → 凭证号
 *   voucherDate → 日期
 *   debitAmount → 借方金额（取较大者作为金额列）
 *   creditAmount → 贷方金额
 *   summary → 摘要
 *   counterpartAccount → 对方科目（交易对手）
 *   accountCode → 科目编码（科目名称）
 * 标记 source: "自动抽凭"
 */
function mapSampledVoucherToRow(voucher: SampledVoucher, seq: number): VoucherSampleRow {
  const debit = voucher.debitAmount ? parseFloat(voucher.debitAmount) : 0
  const credit = voucher.creditAmount ? parseFloat(voucher.creditAmount) : 0
  const amount = Math.max(debit, credit)

  return {
    rowId: generateRowId(),
    seq,
    voucherNo: voucher.voucherNo || '',
    voucherDate: voucher.voucherDate || '',
    amount,
    counterparty: voucher.counterpartAccount || '',
    abstract: voucher.summary || '',
    accountName: voucher.accountCode || '',
    attachmentCount: 0,
    hasOriginal: '',
    amountConsistent: '',
    dateConsistent: '',
    revenueDate: '',
    isCutoff: false,
    customerConfirm: '',
    agingVerify: '',
    abnormalFlag: '',
    conclusion: '',
    indexRef: '',
    source: '自动抽凭',
  }
}

/**
 * 处理 GtVoucherSamplingEngine @filled 事件
 * 将抽样结果映射到 D2-7 列结构并合并到 samples
 * 同时回写抽样参数区（总体/样本量/方法/覆盖率）
 */
function handleSamplingFilled(payload: { samples: SampledVoucher[]; phase: Phase; fillMode: FillMode }): void {
  const { samples: sampledVouchers, fillMode } = payload
  const mapped = sampledVouchers.map((v, idx) => mapSampledVoucherToRow(v, idx + 1))

  if (fillMode === 'replace') {
    // 替换模式：清空后填充
    samples.value = mapped.map((s, i) => ({ ...s, seq: i + 1 }))
  } else if (fillMode === 'merge') {
    // 合并模式：按凭证号去重
    const existingNos = new Set(samples.value.map(s => s.voucherNo))
    const newSamples = mapped.filter(s => !existingNos.has(s.voucherNo))
    const startSeq = samples.value.length + 1
    newSamples.forEach((s, i) => { s.seq = startSeq + i })
    samples.value.push(...newSamples)
  } else {
    // append 模式（默认）：追加到末尾
    const startSeq = samples.value.length + 1
    mapped.forEach((s, i) => { s.seq = startSeq + i })
    samples.value.push(...mapped)
  }

  // 回写抽样参数区：样本量 = 填充笔数，总体规模从 payload 推算
  updateParams('sampleSize', samples.value.length)
  updateParams('populationSize', params.value.populationSize || samples.value.length)

  // 触发 debounce 2s 自动保存
  debounceSave()
}
</script>

<template>
  <div class="d2-tab-voucher">
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" @click="onExportTemplate">导出模板</el-button>
        <el-button size="small" @click="onExportData">导出数据</el-button>
        <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile">
          <el-button size="small">导入数据</el-button>
        </el-upload>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addSample">添加样本</el-button>
        <el-button size="small" :disabled="isReadonly" @click="autoMarkAllCutoff">自动标记跨期</el-button>
      </div>
    </div>

    <!-- 抽样参数区 -->
    <el-card shadow="never" class="params-card">
      <template #header><span style="font-weight:600">抽样参数</span></template>
      <el-form :model="params" label-width="80px" size="small" inline>
        <el-form-item label="抽样方法">
          <el-select :model-value="params.method" :disabled="isReadonly" @change="(v: string) => updateParams('method', v)">
            <el-option label="随机" value="随机" />
            <el-option label="分层" value="分层" />
            <el-option label="特定项目" value="特定项目" />
          </el-select>
        </el-form-item>
        <el-form-item label="总体规模">
          <el-input-number :model-value="params.populationSize" :disabled="isReadonly" :controls="false" @change="(v: number) => updateParams('populationSize', v)" />
        </el-form-item>
        <el-form-item label="样本量">
          <el-input-number :model-value="params.sampleSize" :disabled="isReadonly" :controls="false" @change="(v: number) => updateParams('sampleSize', v)" />
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 自动抽凭引擎 (Task 11.1) -->
    <el-collapse class="sampling-engine-collapse">
      <el-collapse-item title="自动抽凭" name="auto-sampling">
        <GtVoucherSamplingEngine
          account-code="1122"
          :phase="currentPhase"
          default-method="random"
          :workpaper-id="wpId"
          :project-id="projectId"
          :year="year"
          @filled="handleSamplingFilled"
        />
      </el-collapse-item>
    </el-collapse>

    <!-- 进度条 -->
    <div class="progress-bar">
      <span>抽样进度: {{ progress.current }} / {{ progress.target }}</span>
      <el-progress :percentage="Math.min(progress.ratio * 100, 100)" :stroke-width="8" style="flex:1; margin-left: 12px" />
    </div>

    <div v-if="useVirtualScroll" class="virtual-toolbar">
      <el-alert type="info" :closable="false" class="virtual-hint">
        行数较多（{{ browseRowCount }} 行）· {{ browseMode ? '虚拟滚动速览' : '表格编辑' }}模式
      </el-alert>
      <el-button size="small" @click="toggleBrowseMode">
        {{ browseMode ? '切换表格编辑' : '切换虚拟速览' }}
      </el-button>
    </div>
    <el-table-v2
      v-if="useVirtualScroll && browseMode"
      :columns="virtualColumns"
      :data="browseRows"
      :width="tableWidth"
      :height="tableHeight"
      :row-height="36"
      :header-height="40"
      fixed
      class="virtual-table"
    />

    <!-- 凭证明细表 -->
    <el-table v-if="!useVirtualScroll || !browseMode" :data="samples" border size="small" :max-height="450" style="width: 100%">
      <el-table-column label="序号" width="55">
        <template #default="{ $index, row }">
          {{ $index + 1 }}<GtReviewDot row-prefix="D2-voucher" :row-key="String(row.rowId || row.seq)" />
        </template>
      </el-table-column>
      <el-table-column label="凭证号" width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small" @change="(v: string) => updateCell(row.rowId, 'voucherNo', v)" />
          <span v-else>{{ row.voucherNo }}</span>
        </template>
      </el-table-column>
      <el-table-column label="凭证日期" width="120">
        <template #default="{ row }">
          <el-date-picker v-if="!isReadonly" :model-value="row.voucherDate" type="date" value-format="YYYY-MM-DD" size="small" style="width:100%" @change="(v: string) => updateCell(row.rowId, 'voucherDate', v)" />
          <span v-else>{{ row.voucherDate }}</span>
        </template>
      </el-table-column>
      <el-table-column label="金额" width="110" align="right">
        <template #default="{ row }">{{ displayPrefs.fmtAmount(row.amount) }}</template>
      </el-table-column>
      <el-table-column label="交易对手" width="120">
        <template #default="{ row }">{{ row.counterparty || '-' }}</template>
      </el-table-column>
      <el-table-column label="摘要" min-width="120">
        <template #default="{ row }">{{ row.abstract || '-' }}</template>
      </el-table-column>
      <el-table-column label="收入日期" width="120">
        <template #default="{ row }">
          <el-date-picker v-if="!isReadonly" :model-value="row.revenueDate" type="date" value-format="YYYY-MM-DD" size="small" style="width:100%" @change="(v: string) => updateCell(row.rowId, 'revenueDate', v)" />
          <span v-else>{{ row.revenueDate }}</span>
        </template>
      </el-table-column>
      <el-table-column label="跨期" width="60" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.isCutoff" type="danger" size="small">是</el-tag>
          <span v-else>否</span>
        </template>
      </el-table-column>
      <el-table-column label="异常" width="60" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.abnormalFlag === 'Y'" type="danger" size="small">Y</el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="结论" width="100">
        <template #default="{ row }">{{ row.conclusion || '-' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="60" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button type="danger" link size="small" @click="removeSample(row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部汇总 -->
    <div class="summary-bar">
      <span>已检查: {{ samples.length }}笔</span>
      <span>异常笔数: <b style="color:#f56c6c">{{ abnormalCount }}</b></span>
      <span>异常率: {{ (abnormalRate * 100).toFixed(1) }}%</span>
    </div>
  </div>
</template>

<style scoped>
.d2-tab-voucher { padding: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.toolbar-left { display: flex; gap: 8px; }
.params-card { margin-bottom: 12px; }
.sampling-engine-collapse { margin-bottom: 12px; }
.progress-bar { display: flex; align-items: center; margin-bottom: 12px; font-size: 13px; }
.virtual-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.virtual-hint { flex: 1; min-width: 200px; margin: 0; }
.virtual-table { margin-bottom: 12px; }
.summary-bar {
  display: flex; gap: 24px; padding: 8px 12px; margin-top: 10px;
  background: #fafafa; border: 1px solid #ebeef5; border-radius: 4px; font-size: 13px;
}
</style>
