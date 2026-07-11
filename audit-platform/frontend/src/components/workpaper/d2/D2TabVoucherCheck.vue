<script setup lang="ts">
/**
 * D2TabVoucherCheck — 凭证抽查D2-7
 * 抽样参数区 + 凭证明细表(17列) + 进度条 + 底部汇总
 * 集成 GtVoucherSamplingEngine 自动抽凭（Task 11.1）
 */
import { inject, ref, toRef, computed, onMounted, type Ref } from 'vue'
import { useD2VoucherCheck } from '../composables/useD2VoucherCheck'
import { useD2TabImportExport } from '../composables/useD2TabImportExport'
import { useD2AiGenerate } from '../composables/useD2AiGenerate'
import { useWorkpaperBrowseMode } from '../composables/useWorkpaperBrowseMode'
import { virtualTextCol, virtualNumCol } from '../composables/virtualColumnHelpers'
import type { VirtualColumn } from '@/composables/useVirtualTable'
import GtIndexChip from '../GtIndexChip.vue'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
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

// ─── 核对结果点选选项 ───────────────────────────────────────────────────────
const YN_OPTIONS = ['是', '否', 'N/A']
const CONFIRM_OPTIONS = ['相符', '不符', '未回函', '未函证']

// ─── 审计说明（inline 存储）─────────────────────────────────────────────────
const NOTE_KEY = 'D2-voucher-note'
const auditNote = ref('')

onMounted(() => {
  auditNote.value = props.allResponses.get(NOTE_KEY)?.remark || ''
})

function saveNote(v: string): void {
  if (props.isReadonly) return
  auditNote.value = v
  const item = { item_id: NOTE_KEY, conclusion: null, remark: v }
  props.allResponses.set(NOTE_KEY, item)
  window.dispatchEvent(new CustomEvent('d2:save-items', { detail: { items: [item] } }))
}

const { aiAvailable, generateAndConfirm } = useD2AiGenerate(toRef(props, 'wpId'))
const aiLoadingNote = ref(false)

async function generateNoteAI(): Promise<void> {
  if (props.isReadonly) return
  aiLoadingNote.value = true
  try {
    const text = await generateAndConfirm('voucher-note', auditNote.value, {
      sheet: 'D2-7',
      checked: samples.value.length,
      abnormalCount: abnormalCount.value,
      abnormalRate: `${(abnormalRate.value * 100).toFixed(1)}%`,
    }, 'AI · 应收账款细节测试说明')
    if (text) saveNote(text)
  } finally { aiLoadingNote.value = false }
}

const GUIDANCE_TEXTS = [
  '细节测试：对抽取的应收账款交易核对原始单据（销售合同、发货单、验收单、发票、回款记录），验证发生额的真实性、准确性与截止。',
  '核对要点：金额一致（凭证↔单据）、日期一致（入账↔业务实质）、客户函证相符、账龄核实，任一异常应标记并追查。',
  '异常处理：标记异常的样本应查明原因、评估错报性质与金额，必要时扩大样本或提出调整。',
  '样本量与方法应与 B50 风险评估及重要性水平匹配，特定项目（大额/关联方/异常）应单独关注。',
]

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
    <div class="tab-header">
      <h4>应收账款检查表（细节测试）D2-7</h4>
      <GtReviewTrigger section-id="D2-voucher-header" />
    </div>

    <el-alert type="info" :closable="false" show-icon title="审计目标" class="audit-objective">
      <template #default>
        <p>通过抽样核对原始单据，验证应收账款发生额的真实性、准确性、截止与计价，识别异常交易。</p>
      </template>
    </el-alert>

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

    <!-- 凭证明细表（宽表：凭证基础信息固定左侧，核对结果横向滚动） -->
    <el-table v-if="!useVirtualScroll || !browseMode" :data="samples" border size="small" :max-height="480" style="width: 100%">
      <!-- 凭证基础信息 -->
      <el-table-column label="凭证基础信息" header-align="center">
        <el-table-column label="序号" width="55" fixed="left">
          <template #default="{ $index, row }">
            {{ $index + 1 }}<GtReviewDot row-prefix="D2-voucher" :row-key="String(row.rowId || row.seq)" />
          </template>
        </el-table-column>
        <el-table-column label="凭证号" width="110" fixed="left">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small" placeholder="凭证号" @change="(v: string) => updateCell(row.rowId, 'voucherNo', v)" />
            <span v-else>{{ row.voucherNo }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证日期" width="130">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" :model-value="row.voucherDate" type="date" value-format="YYYY-MM-DD" size="small" style="width:100%" @change="(v: string) => updateCell(row.rowId, 'voucherDate', v)" />
            <span v-else>{{ row.voucherDate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.amount" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'amount', v || 0)" />
            <span v-else>{{ displayPrefs.fmtAmount(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="交易对手" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.counterparty" size="small" placeholder="交易对手" @change="(v: string) => updateCell(row.rowId, 'counterparty', v)" />
            <span v-else>{{ row.counterparty || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="摘要" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.abstract" size="small" placeholder="摘要" @change="(v: string) => updateCell(row.rowId, 'abstract', v)" />
            <span v-else>{{ row.abstract || '-' }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 核对结果 -->
      <el-table-column label="核对结果" header-align="center">
        <el-table-column label="原始单据" width="100" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.hasOriginal" size="small" clearable placeholder="选择" style="width:100%" @change="(v: string) => updateCell(row.rowId, 'hasOriginal', v || '')">
              <el-option v-for="o in YN_OPTIONS" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.hasOriginal || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="金额一致" width="100" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.amountConsistent" size="small" clearable placeholder="选择" style="width:100%" @change="(v: string) => updateCell(row.rowId, 'amountConsistent', v || '')">
              <el-option v-for="o in YN_OPTIONS" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.amountConsistent || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="日期一致" width="100" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.dateConsistent" size="small" clearable placeholder="选择" style="width:100%" @change="(v: string) => updateCell(row.rowId, 'dateConsistent', v || '')">
              <el-option v-for="o in YN_OPTIONS" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.dateConsistent || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="收入日期" width="130">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" :model-value="row.revenueDate" type="date" value-format="YYYY-MM-DD" size="small" style="width:100%" @change="(v: string) => updateCell(row.rowId, 'revenueDate', v)" />
            <span v-else>{{ row.revenueDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="跨期" width="60" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.isCutoff" type="danger" size="small">是</el-tag>
            <span v-else>否</span>
          </template>
        </el-table-column>
        <el-table-column label="客户函证" width="110" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.customerConfirm" size="small" clearable placeholder="选择" style="width:100%" @change="(v: string) => updateCell(row.rowId, 'customerConfirm', v || '')">
              <el-option v-for="o in CONFIRM_OPTIONS" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.customerConfirm || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账龄核实" width="100" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.agingVerify" size="small" clearable placeholder="选择" style="width:100%" @change="(v: string) => updateCell(row.rowId, 'agingVerify', v || '')">
              <el-option v-for="o in YN_OPTIONS" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.agingVerify || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="异常" width="90" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.abnormalFlag" size="small" clearable placeholder="选择" style="width:100%" @change="(v: string) => updateCell(row.rowId, 'abnormalFlag', v || '')">
              <el-option label="正常" value="" />
              <el-option label="异常" value="Y" />
            </el-select>
            <el-tag v-else-if="row.abnormalFlag === 'Y'" type="danger" size="small">异常</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 结论 -->
      <el-table-column label="结论" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.conclusion" size="small" placeholder="结论" @change="(v: string) => updateCell(row.rowId, 'conclusion', v)" />
          <span v-else>{{ row.conclusion || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="索引号" width="140">
        <template #default="{ row }">
          <div class="index-cell">
            <el-input v-if="!isReadonly" :model-value="row.indexRef" size="small" placeholder="索引号" @change="(v: string) => updateCell(row.rowId, 'indexRef', v)" />
            <GtIndexChip v-if="row.indexRef" :value="row.indexRef" :context-project-id="projectId" />
          </div>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="" width="50" fixed="right">
        <template #default="{ row }">
          <el-popconfirm title="确定删除该行？" confirm-button-text="删除" cancel-button-text="取消" @confirm="removeSample(row.rowId)">
            <template #reference><el-button type="danger" link size="small">✕</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
      <template #empty>暂无抽样凭证，点击"添加样本"或使用"自动抽凭"</template>
    </el-table>

    <!-- 底部汇总 -->
    <div class="summary-bar">
      <span>已检查: {{ samples.length }}笔</span>
      <span>异常笔数: <b style="color:#f56c6c">{{ abnormalCount }}</b></span>
      <span>异常率: {{ (abnormalRate * 100).toFixed(1) }}%</span>
    </div>

    <!-- 审计说明 -->
    <div class="section-subtitle">
      审计说明
      <GtReviewTrigger section-id="D2-voucher-note" />
      <el-tooltip :content="aiAvailable ? 'AI 辅助生成' : 'AI 服务暂不可用'" placement="top">
        <el-button size="small" text type="primary" :loading="aiLoadingNote" :disabled="isReadonly || !aiAvailable" @click="generateNoteAI">🤖 AI 生成</el-button>
      </el-tooltip>
    </div>
    <el-input type="textarea" :autosize="{ minRows: 5 }" :model-value="auditNote" placeholder="记录细节测试的样本选取、核对结果、异常处理及总体结论..." :disabled="isReadonly" @change="saveNote" />

    <details class="guidance-fold">
      <summary>📋 编制提示</summary>
      <p v-for="(t, i) in GUIDANCE_TEXTS" :key="'g-' + i">{{ t }}</p>
    </details>
  </div>
</template>

<style scoped>
.d2-tab-voucher { padding: 12px; }
.tab-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.tab-header h4 { margin: 0; font-size: 15px; }
.audit-objective { margin-bottom: 12px; }
.audit-objective p { margin: 0; font-size: 13px; line-height: 1.6; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.toolbar-left { display: flex; gap: 8px; }
.index-cell { display: flex; align-items: center; gap: 6px; }
.index-cell .el-input { flex: 1; }
.section-subtitle { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 600; color: #303133; margin: 16px 0 10px; }
.guidance-fold { margin: 16px 0; border-left: 3px solid #409eff; background: #ecf5ff; padding: 10px 14px; border-radius: 0 4px 4px 0; font-size: 13px; color: #606266; }
.guidance-fold summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-fold p { margin: 6px 0; line-height: 1.6; }
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
