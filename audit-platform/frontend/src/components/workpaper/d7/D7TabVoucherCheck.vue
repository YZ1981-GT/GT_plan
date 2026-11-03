<template>
<div class="d7-voucher-check">
  <!-- 抽样方法学（来自抽凭引擎回填，底稿正文可见 → 归档与复核可追溯） -->
  <WpSamplingMethodologyBar :methodology="methodology" />

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表对合同负债（科目2205）本期增减变动及期后结转进行凭证抽查，依据 CAS14 收入准则验证发生额的真实性与截止准确性。</p>
        <p>2. 抽样应结合特定项目（大额/异常）与随机抽样，样本量需覆盖目标；核对凭证与合同、收款记录、履约证据一致。</p>
        <p>3. 期后结转检查关注资产负债表日后合同负债结转至收入的凭证，验证收入确认时点的恰当性（截止测试）。</p>
        <p>4. 异常项目应勾选"异常"并在审计说明中记录，异常率偏高时应扩大样本或追加实质性程序。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        <span class="ao-title">一、审计目标</span>
      </template>
      <template #default>
        <ol class="ao-list">
          <li>资产负债表中记录的合同负债是存在的，且已经记录在恰当的账户中；</li>
          <li>记录的合同负债的金额包括在财务报表中是恰当的，与之相关的计价调整已恰当记录；</li>
          <li>合同负债以恰当的金额包括在财务报表中，与之相关的分摊调整已恰当记录，相关披露已得到恰当计量和描述。</li>
        </ol>
      </template>
    </el-alert>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button v-if="!isReadonly" size="small" type="primary" @click="samplingVisible = true">🎲 抽凭引擎</el-button>
        <el-badge :value="attachedCount" :hidden="attachedCount === 0" type="warning">
          <el-button size="small" :disabled="isReadonly" :loading="importingAttached" title="导入在「账簿查询」右键挂凭到本底稿的序时账凭证" @click="importFromAttached">📎 从序时账挂入导入</el-button>
        </el-badge>
      </div>
      <div class="toolbar-right">
        <el-dropdown v-if="!isReadonly" size="small" trigger="click">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="periodImport.exportTemplate">导出本期模板</el-dropdown-item>
              <el-dropdown-item @click="periodImport.exportData">导出本期数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="periodImport.importing" @change="(f: any) => onPeriodImport(f.raw || f)">
                  <span>导入本期数据</span>
                </el-upload>
              </el-dropdown-item>
              <el-dropdown-item divided @click="postImport.exportTemplate">导出期后模板</el-dropdown-item>
              <el-dropdown-item @click="postImport.exportData">导出期后数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="postImport.importing" @change="(f: any) => onPostImport(f.raw || f)">
                  <span>导入期后数据</span>
                </el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <span class="chip-wrap"><GtIndexChip value="wp:D7-2" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:D4" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ periodChangeRows.length + postTransferRows.length }} 行</el-tag>
      </div>
    </div>

    <!-- 抽样参数区 -->
    <div class="sampling-params-card">
      <h4 class="card-title">抽样参数</h4>
      <div class="params-grid">
        <div class="param-item">
          <label>总体笔数</label>
          <el-input-number v-model="samplingParams.totalPopulation" :controls="false" :disabled="isReadonly" size="small" style="width:120px" />
        </div>
        <div class="param-item">
          <label>特定项目样本</label>
          <el-input-number v-model="samplingParams.specificSamples" :controls="false" :disabled="isReadonly" size="small" style="width:120px" />
        </div>
        <div class="param-item">
          <label>抽样总体笔数</label>
          <el-input-number v-model="samplingParams.samplingPopulation" :controls="false" :disabled="isReadonly" size="small" style="width:120px" />
        </div>
        <div class="param-item">
          <label>目标样本量</label>
          <el-input-number v-model="samplingParams.targetSampleSize" :controls="false" :disabled="isReadonly" size="small" style="width:120px" />
        </div>
        <div class="param-item">
          <label>抽样方法</label>
          <el-input v-model="samplingParams.samplingMethod" :disabled="isReadonly" size="small" style="width:180px" />
        </div>
        <div class="param-item">
          <label>抽样过程说明</label>
          <el-input v-model="samplingParams.samplingProcess" :disabled="isReadonly" size="small" style="width:180px" />
        </div>
      </div>
      <!-- 进度条 -->
      <div class="progress-bar">
        <span>已抽取：{{ checkedCount }} / 目标：{{ samplingParams.targetSampleSize }}</span>
        <el-progress
          :percentage="samplingParams.targetSampleSize > 0 ? Math.min(100, Math.round(checkedCount / samplingParams.targetSampleSize * 100)) : 0"
          :stroke-width="10"
          style="width:200px"
        />
      </div>
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

    <template v-if="!useVirtualScroll || !browseMode">
    <!-- (1) 本期增减变动检查 -->
    <div class="check-block">
      <h4 class="card-title">(1) 本期增减变动检查</h4>
      <el-button v-if="!isReadonly" size="small" style="margin-bottom:8px" @click="addSample('period')">添加样本</el-button>
      <D7VoucherCheckTable :rows="periodChangeRows" block="period" :is-readonly="isReadonly" :project-id="projectId"
        :year="samplingYear" :row-class-name="voucherRowClass" :is-row-locked="isVoucherRowLocked"
        @update="(rowId: string, field: string, v: unknown) => updateCell('period', rowId, field, v)"
        @toggle="(rowId: string, idx: number, v: boolean) => toggleCheck('period', rowId, idx, v)"
        @remove="(rowId: string) => removeSample('period', rowId)" />
    </div>

    <!-- (2) 期后结转检查 -->
    <div class="check-block">
      <h4 class="card-title">(2) 期后结转检查</h4>
      <el-button v-if="!isReadonly" size="small" style="margin-bottom:8px" @click="addSample('post')">添加样本</el-button>
      <D7VoucherCheckTable :rows="postTransferRows" block="post" :is-readonly="isReadonly" :project-id="projectId"
        :year="samplingYear" :row-class-name="voucherRowClass" :is-row-locked="isVoucherRowLocked"
        @update="(rowId: string, field: string, v: unknown) => updateCell('post', rowId, field, v)"
        @toggle="(rowId: string, idx: number, v: boolean) => toggleCheck('post', rowId, idx, v)"
        @remove="(rowId: string) => removeSample('post', rowId)" />
    </div>
    </template>

    <!-- 底部汇总 -->
    <div class="summary-section">
      <span>已检查：<strong>{{ checkedCount }}</strong> 笔</span>
      <span>异常：<strong class="abnormal-count">{{ abnormalCount }}</strong> 笔</span>
      <span>异常率：</span>
      <el-tag v-if="abnormalRate > 0" type="danger" size="small">{{ (abnormalRate * 100).toFixed(1) }}%</el-tag>
      <el-tag v-else type="success" size="small">{{ (abnormalRate * 100).toFixed(1) }}% 无异常</el-tag>
    </div>

    <!-- 审计意见区（卡片式） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明与结论</span>
          <div class="opinion-chips">
            <GtIndexChip value="wp:D7-2" :context-project-id="projectId" />
            <GtIndexChip value="wp:D4" :context-project-id="projectId" />
          </div>
        </div>
      </template>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">1. 审计说明</span>
          <div class="opinion-actions">
            <el-button size="small" @click="openReview('D7-7-note-explanation')">💬</el-button>
          </div>
        </div>
        <el-input
          v-model="auditNotes.explanation"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          :disabled="isReadonly"
          placeholder="凭证检查发现..."
        />
      </div>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">2. 审计结论</span>
          <div class="opinion-actions">
            <el-button size="small" @click="openReview('D7-7-note-conclusion')">💬</el-button>
          </div>
        </div>
        <el-select v-if="!isReadonly" :model-value="undefined" placeholder="选择结论模板..." size="small" style="width: 100%; margin-bottom: 8px" @change="onConclusionTemplateSelect">
          <el-option v-for="tpl in CONCLUSION_TEMPLATES" :key="tpl.value" :label="tpl.label" :value="tpl.label" />
        </el-select>
        <el-input
          v-model="auditNotes.conclusion"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          placeholder="凭证检查结论..."
        />
      </div>
    </el-card>

    <!-- 抽凭引擎弹窗 -->
    <el-dialog v-model="samplingVisible" title="抽凭引擎 — 合同负债(2205)" width="90%" top="5vh" destroy-on-close>
      <GtVoucherSamplingEngine
        v-if="samplingVisible"
        :account-code="samplingAccountCode"
        :workpaper-id="props.wpId"
        :project-id="props.projectId"
        :year="samplingYear"
        @filled="onSampleFilled"
        @undo-request="onUndoRequest"
      />
    </el-dialog>
</div>
</template>

<script setup lang="ts">
/**
 * D7TabVoucherCheck.vue — 凭证检查 D7-7 (~350行)
 * 3区域：抽样参数 + (1)本期增减变动 + (2)期后结转
 * Task: 22.1
 * Requirements: 12.1-12.9, 18.5, 19.4, 20.1, 21.1-21.3
 */
import { computed, inject, ref, toRef, defineAsyncComponent, onMounted, type Ref } from 'vue'
import { useD7VoucherCheck } from '../composables/useD7VoucherCheck'
import { useD7ImportExport } from '../composables/useD7ImportExport'
import { useWorkpaperBrowseMode } from '../composables/useWorkpaperBrowseMode'
import { virtualTextCol, virtualNumCol } from '../composables/virtualColumnHelpers'
import type { VirtualColumn } from '@/composables/useVirtualTable'
import type { ChecklistResponse } from '../composables/useD7FormData'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'
import D7VoucherCheckTable from './D7VoucherCheckTable.vue'
import WpSamplingMethodologyBar from '../shared/WpSamplingMethodologyBar.vue'
import { useSamplingMethodologyPersist } from '../composables/shared/useSamplingMethodologyPersist'
import type { SamplingMethodologySnapshot } from '../composables/shared/samplingFillTarget'
import type { EngineFilledPayload } from '../composables/shared/voucherCheckFill'

/**
 * 抽凭科目码取自单一真源 `dCycleAccountScope`（D7 合同负债）。
 * 原为模板内字面量；接真源后科目口径与该循环的取数/回写共用同一定义，
 * 避免各处独立硬编码而漂移。本组件无 `tbSourceCodes` prop ⇒ 走兜底码。
 * spec: voucher-sampling-account-scope-and-attach-closure R1.1/R1.2
 */
import {
  pullSamplesForWorkpaper,
  listAttachedVouchers,
} from '../composables/useAttachedVouchers'
import { dSlotQueryCodes, pickDTbSourceCodes } from '../composables/dCycleAccountScope'
import { ElMessage } from 'element-plus'
import { dCycleScope } from '../composables/dCycleAccountScope'

/** 抽凭 account-code（逗号拼接，引擎侧会 split(',')） */
const samplingAccountCode = dCycleScope('D7')?.queryCodes().join(',') ?? ''

const GtVoucherSamplingEngine = defineAsyncComponent(() => import('../voucher-sampling/GtVoucherSamplingEngine.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Map<string, ChecklistResponse>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet: any
  /** 审计年度；项目没填为 null（父级按项目口径取，不按今年兜底） */
  year?: number | null
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
function openReview(sectionId: string) { openReviewDialog(sectionId) }

const wpIdRef = computed(() => props.wpId) as unknown as Ref<string>
const onReload = () => reloadWorkpaperData?.() ?? Promise.resolve()
const periodImport = useD7ImportExport({ wpId: wpIdRef, sheetCode: 'D7-7-period', sheetLabel: '本期变动', onImported: onReload })
const postImport = useD7ImportExport({ wpId: wpIdRef, sheetCode: 'D7-7-post', sheetLabel: '期后结转', onImported: onReload })

async function onPeriodImport(file: File) {
  await periodImport.importData(file)
}
async function onPostImport(file: File) {
  await postImport.importData(file)
}

const {
  samplingParams, periodChangeRows, postTransferRows,
  checkedCount, abnormalCount, abnormalRate,
  addSample, removeSample, updateCell, auditNotes,
  onEngineFilled, onAttachImported, onUndoRequest, voucherRowClass, isVoucherRowLocked, voucherFillReady,
} = useD7VoucherCheck({
  allResponses: allResponsesRef,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: () => props.isReadonly,
  // 挂凭导入按凭证日期分区：晚于资产负债表日进期后结转
  bsDate: () => (props.year ? `${props.year}-12-31` : null),
})
onMounted(() => { void voucherFillReady() })

const CONCLUSION_TEMPLATES = [
  { value: 'no-issue', label: '经抽查，所选样本凭证与合同/收款记录一致，合同负债增减变动真实准确。' },
  { value: 'adjusted', label: '经抽查，发现差异已提请调整，调整后合同负债列报恰当。' },
  { value: 'expand', label: '检查比例不足，建议扩大样本量后重新评估。' },
  { value: 'cutoff-issue', label: '发现收入确认时点不当，期后结转存在截止差异，建议调整。' },
  { value: 'other', label: '其他（请手动编写结论）。' },
]

// ─── 抽凭引擎 ──────────────────────────────────────────────────────
const samplingVisible = ref(false)
const samplingYear = computed<number | null>(() => props.year ?? null)

/**
 * 抽样方法学留痕（R6.3/R6.4）：把 `filled` 载荷里的 methodology 落到固定 item key，
 * 并在抽凭区渲染到底稿正文 —— 复核与归档看的是底稿，不是后台抽凭日志。
 */
const { methodology, persistMethodology } = useSamplingMethodologyPersist({
  wpCode: 'D7',
  allResponses: allResponsesRef,
  persist: (itemId, remark) => props.saveImmediate(itemId, { remark, conclusion: null }),
  isReadonly: computed(() => props.isReadonly),
})

// ─── 从序时账挂入导入（挂凭到底稿联动）─────────────────────────────────────
const attachedCount = ref(0)
const importingAttached = ref(false)
// 科目映射码：优先从上层 provide 注入的 tb_source_codes 取映射后的真实码，未注入时退兜底码
const _injectedTbSrc = inject<Ref<any> | null>('tbSourceCodes', null)
const D7_ACCOUNT_PREFIXES = computed(() => dSlotQueryCodes('D7', _injectedTbSrc?.value ?? null))

async function refreshAttachedCount(): Promise<void> {
  if (!props.projectId || !props.wpId || samplingYear.value == null) return
  try {
    const recs = await listAttachedVouchers(props.projectId, samplingYear.value, props.wpId, true)
    attachedCount.value = recs.length
  } catch { attachedCount.value = 0 }
}
void refreshAttachedCount()

async function importFromAttached(): Promise<void> {
  if (props.isReadonly || samplingYear.value == null) {
    if (samplingYear.value == null) ElMessage.warning('未设置审计年度，无法读取序时账凭证')
    return
  }
  importingAttached.value = true
  try {
    const { samples, misattached } = await pullSamplesForWorkpaper(
      props.projectId, samplingYear.value, props.wpId, D7_ACCOUNT_PREFIXES.value,
    )
    if (samples.length > 0) await onAttachImported(samples)
    if (misattached.length > 0) ElMessage.warning(`${misattached.length} 张凭证不属于本底稿科目范围，已跳过`)
    if (samples.length === 0 && misattached.length === 0) ElMessage.info('暂无挂入本底稿的序时账凭证')
  } finally { importingAttached.value = false }
}

/**
 * 抽凭引擎回填：共享回填函数写进本期增减变动（已在期后结转的分录不重复插入），按分录指纹去重；
 * 对方科目只按后端配对结果（配不上的整张凭证标「多科目」），客户名称取辅助明细账往来单位。
 */
async function onSampleFilled(payload: EngineFilledPayload & { methodology?: SamplingMethodologySnapshot }): Promise<void> {
  // 方法学先落库：即便回填 0 条，「抽过样且方法学如此」也是应留的痕
  void persistMethodology(payload?.methodology)
  if (!(payload?.samples ?? []).length) return
  const out = await onEngineFilled(payload, { tables: ['period'] })
  if (!out.cancelled) samplingVisible.value = false
}

function onConclusionTemplateSelect(val: string) {
  if (val) auditNotes.value.conclusion = val
}

function toggleCheck(block: 'period' | 'post', rowId: string, idx: number, val: boolean) {
  const rows = block === 'period' ? periodChangeRows.value : postTransferRows.value
  const row = rows.find(r => r.rowId === rowId)
  if (!row) return
  const newItems = [...row.checkItems]
  newItems[idx] = val
  updateCell(block, rowId, 'checkItems', newItems)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const browseRows = computed(() => [
  ...periodChangeRows.value.map(r => ({
    section: '本期',
    customerName: r.customerName,
    voucherNo: r.voucherNo,
    debit: r.debitAmount,
    credit: r.creditAmount,
  })),
  ...postTransferRows.value.map(r => ({
    section: '期后',
    customerName: r.customerName,
    voucherNo: r.voucherNo,
    debit: r.debitAmount,
    credit: r.creditAmount,
  })),
])

const browseRowCount = computed(() => browseRows.value.length)

const virtualColumns = computed<VirtualColumn[]>(() => [
  virtualTextCol('section', '区块', 70),
  virtualTextCol('customerName', '客户名称', 130),
  virtualTextCol('voucherNo', '凭证号', 90),
  virtualNumCol('debit', '借方', 100, fmtAmt),
  virtualNumCol('credit', '贷方', 100, fmtAmt),
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
  tableWidth: 960,
})
</script>

<style scoped>
.d7-voucher-check { padding: 12px; }
.d7-voucher-check :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.d7-voucher-check :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}

/* 编制提示 */
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p { margin: 2px 0; }

/* 审计目标 */
.audit-objective { margin-bottom: 14px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-title { font-weight: 600; }
.ao-list { padding-left: 18px; line-height: 1.55; font-size: 12px; margin: 4px 0 0; }

/* 工具栏 */
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

.sampling-params-card {
  padding: 16px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  margin-bottom: 16px;
}
.card-title { font-size: 14px; font-weight: 600; margin: 0 0 12px; color: #303133; }
.params-grid { display: flex; flex-wrap: wrap; gap: 16px; }
.param-item { display: flex; flex-direction: column; gap: 4px; }
.param-item label { font-size: 12px; color: #909399; }
.progress-bar { display: flex; align-items: center; gap: 12px; margin-top: 12px; font-size: var(--wp-font-size, 13px); }
.virtual-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.virtual-hint { flex: 1; min-width: 200px; margin: 0; }
.virtual-table { margin-bottom: 12px; }

.check-block { margin-bottom: 20px; }
.abnormal-count { color: #f56c6c; }

.summary-section {
  margin-top: 12px;
  padding: 10px 12px;
  background: #fafafa;
  border-radius: 6px;
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: var(--wp-font-size, 13px);
}

/* 审计意见卡片 */
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-chips { display: flex; gap: 6px; }
.opinion-section { margin-bottom: 16px; }
.opinion-section:last-child { margin-bottom: 0; }
.opinion-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.opinion-section-label { font-size: 14px; font-weight: 500; color: #303133; }
.opinion-actions { display: flex; gap: 6px; align-items: center; }
</style>
