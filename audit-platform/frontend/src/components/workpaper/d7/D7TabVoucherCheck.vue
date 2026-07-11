<template>
<div class="d7-voucher-check">
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
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：通过凭证抽查验证合同负债本期发生额及期后结转的真实性、准确性与截止恰当性，识别异常交易及收入确认时点风险。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
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
      <el-table :data="periodChangeRows" size="small" border max-height="400">
        <el-table-column label="客户名称" width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.customerName" size="small" @change="(v: string) => updateCell('period', row.rowId, 'customerName', v)" />
            <span v-else>{{ row.customerName }}</span>
          </template>
        </el-table-column>
        <el-table-column label="日期" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.date" size="small" @change="(v: string) => updateCell('period', row.rowId, 'date', v)" />
            <span v-else>{{ row.date }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证号" width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small" @change="(v: string) => updateCell('period', row.rowId, 'voucherNo', v)" />
            <span v-else>{{ row.voucherNo }}</span>
          </template>
        </el-table-column>
        <el-table-column label="业务内容" width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.businessContent" size="small" @change="(v: string) => updateCell('period', row.rowId, 'businessContent', v)" />
            <span v-else>{{ row.businessContent }}</span>
          </template>
        </el-table-column>
        <el-table-column label="对方科目" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.counterAccount" size="small" @change="(v: string) => updateCell('period', row.rowId, 'counterAccount', v)" />
            <span v-else>{{ row.counterAccount }}</span>
          </template>
        </el-table-column>
        <el-table-column label="借方金额" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.debitAmount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell('period', row.rowId, 'debitAmount', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.debitAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="贷方金额" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.creditAmount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell('period', row.rowId, 'creditAmount', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核对" width="70" align="center">
          <template #default="{ row }">
            <el-checkbox :model-value="row.checkItems[0]" :disabled="isReadonly" @change="(v: boolean) => toggleCheck('period', row.rowId, 0, v)" />
          </template>
        </el-table-column>
        <el-table-column label="异常" width="60" align="center">
          <template #default="{ row }">
            <el-checkbox :model-value="row.isAbnormal" :disabled="isReadonly" @change="(v: boolean) => updateCell('period', row.rowId, 'isAbnormal', v)" />
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50" align="center">
          <template #default="{ row }">
            <el-button type="danger" text size="small" @click="removeSample('period', row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- (2) 期后结转检查 -->
    <div class="check-block">
      <h4 class="card-title">(2) 期后结转检查</h4>
      <el-button v-if="!isReadonly" size="small" style="margin-bottom:8px" @click="addSample('post')">添加样本</el-button>
      <el-table :data="postTransferRows" size="small" border max-height="400">
        <el-table-column label="客户名称" width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.customerName" size="small" @change="(v: string) => updateCell('post', row.rowId, 'customerName', v)" />
            <span v-else>{{ row.customerName }}</span>
          </template>
        </el-table-column>
        <el-table-column label="日期" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.date" size="small" @change="(v: string) => updateCell('post', row.rowId, 'date', v)" />
            <span v-else>{{ row.date }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证号" width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small" @change="(v: string) => updateCell('post', row.rowId, 'voucherNo', v)" />
            <span v-else>{{ row.voucherNo }}</span>
          </template>
        </el-table-column>
        <el-table-column label="对方科目" width="130">
          <template #default="{ row }">
            <span>{{ row.counterAccount }}</span>
            <GtIndexChip v-if="row.counterAccount && row.counterAccount.includes('主营业务收入')" value="wp:D4" :context-project-id="projectId" style="margin-left:4px" />
          </template>
        </el-table-column>
        <el-table-column label="贷方金额" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.creditAmount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell('post', row.rowId, 'creditAmount', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核对" width="70" align="center">
          <template #default="{ row }">
            <el-checkbox :model-value="row.checkItems[0]" :disabled="isReadonly" @change="(v: boolean) => toggleCheck('post', row.rowId, 0, v)" />
          </template>
        </el-table-column>
        <el-table-column label="异常" width="60" align="center">
          <template #default="{ row }">
            <el-checkbox :model-value="row.isAbnormal" :disabled="isReadonly" @change="(v: boolean) => updateCell('post', row.rowId, 'isAbnormal', v)" />
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50" align="center">
          <template #default="{ row }">
            <el-button type="danger" text size="small" @click="removeSample('post', row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
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
        <el-input
          v-model="auditNotes.conclusion"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          placeholder="凭证检查结论..."
        />
      </div>
    </el-card>
</div>
</template>

<script setup lang="ts">
/**
 * D7TabVoucherCheck.vue — 凭证检查 D7-7 (~350行)
 * 3区域：抽样参数 + (1)本期增减变动 + (2)期后结转
 * Task: 22.1
 * Requirements: 12.1-12.9, 18.5, 19.4, 20.1, 21.1-21.3
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { useD7VoucherCheck } from '../composables/useD7VoucherCheck'
import { useD7ImportExport } from '../composables/useD7ImportExport'
import { useWorkpaperBrowseMode } from '../composables/useWorkpaperBrowseMode'
import { virtualTextCol, virtualNumCol } from '../composables/virtualColumnHelpers'
import type { VirtualColumn } from '@/composables/useVirtualTable'
import type { ChecklistResponse } from '../composables/useD7FormData'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Map<string, ChecklistResponse>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet: any
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
} = useD7VoucherCheck({
  allResponses: allResponsesRef,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
})

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
  --el-table-font-size: 13px;
  font-size: 13px;
}
.d7-voucher-check :deep(.el-table .cell) {
  font-size: 13px !important;
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
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }

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
.progress-bar { display: flex; align-items: center; gap: 12px; margin-top: 12px; font-size: 13px; }
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
  font-size: 13px;
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
