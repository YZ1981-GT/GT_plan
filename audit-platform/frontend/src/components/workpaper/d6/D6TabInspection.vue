<template>
<div class="d6-tab-inspection">
  <div class="toolbar">
    <el-button size="small" @click="periodIe.exportTemplate">导出模板(本期)</el-button>
    <el-button size="small" @click="periodIe.exportData">导出数据(本期)</el-button>
    <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportPeriodFile">
      <el-button size="small" :loading="periodIe.importing.value">导入(本期)</el-button>
    </el-upload>
    <el-button size="small" @click="postIe.exportTemplate">导出模板(期后)</el-button>
    <el-button size="small" @click="postIe.exportData">导出数据(期后)</el-button>
    <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportPostFile">
      <el-button size="small" :loading="postIe.importing.value">导入(期后)</el-button>
    </el-upload>
  </div>
  <!-- 抽样参数区 -->
  <div class="sampling-params-card">
    <h4 class="card-title">抽样参数</h4>
    <div class="params-grid">
      <div class="param-item">
        <label>测试总体</label>
        <el-input v-model="samplingParams.testPopulation" :disabled="isReadonly" size="small" style="width:160px" />
      </div>
      <div class="param-item">
        <label>特定样本</label>
        <el-input v-model="samplingParams.specificSample" :disabled="isReadonly" size="small" style="width:160px" />
      </div>
      <div class="param-item">
        <label>抽样总体</label>
        <el-input v-model="samplingParams.samplingPopulation" :disabled="isReadonly" size="small" style="width:160px" />
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
        <label>抽样过程</label>
        <el-input v-model="samplingParams.samplingProcess" :disabled="isReadonly" size="small" style="width:180px" />
      </div>
    </div>
    <div class="progress-bar">
      <span>已抽取：{{ sampleCount }} / 目标：{{ samplingParams.targetSampleSize }}</span>
      <el-progress
        :percentage="samplingParams.targetSampleSize > 0 ? Math.min(100, Math.round(sampleCount / samplingParams.targetSampleSize * 100)) : 0"
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
    <el-button v-if="!isReadonly" size="small" style="margin-bottom:8px" @click="addSample(1)">添加样本</el-button>
    <el-table :data="block1Rows" size="small" border max-height="420" style="width:100%">
      <el-table-column label="客户名称" width="120" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.customerName" size="small" @change="(v: string) => updateSampleCell(1, row.rowId, 'customerName', v)" />
          <span v-else>{{ row.customerName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="日期" width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.date" size="small" @change="(v: string) => updateSampleCell(1, row.rowId, 'date', v)" />
          <span v-else>{{ row.date }}</span>
        </template>
      </el-table-column>
      <el-table-column label="凭证号" width="90">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small" @change="(v: string) => updateSampleCell(1, row.rowId, 'voucherNo', v)" />
          <span v-else>{{ row.voucherNo }}</span>
        </template>
      </el-table-column>
      <el-table-column label="业务内容" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.businessContent" size="small" @change="(v: string) => updateSampleCell(1, row.rowId, 'businessContent', v)" />
          <span v-else>{{ row.businessContent }}</span>
        </template>
      </el-table-column>
      <el-table-column label="对方科目" width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.counterAccount" size="small" @change="(v: string) => updateSampleCell(1, row.rowId, 'counterAccount', v)" />
          <span v-else>{{ row.counterAccount }}</span>
        </template>
      </el-table-column>
      <el-table-column label="对方明细" width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.counterDetail" size="small" @change="(v: string) => updateSampleCell(1, row.rowId, 'counterDetail', v)" />
          <span v-else>{{ row.counterDetail }}</span>
        </template>
      </el-table-column>
      <el-table-column label="借方金额" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.debitAmount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateSampleCell(1, row.rowId, 'debitAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方金额" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.creditAmount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateSampleCell(1, row.rowId, 'creditAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="支持性文件" width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.supportDoc" size="small" @change="(v: string) => updateSampleCell(1, row.rowId, 'supportDoc', v)" />
          <span v-else>{{ row.supportDoc }}</span>
        </template>
      </el-table-column>
      <el-table-column label="是否异常" width="80" align="center">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.isAbnormal" size="small" @change="(v: string) => updateSampleCell(1, row.rowId, 'isAbnormal', v)">
            <el-option label="否" value="否" />
            <el-option label="是" value="是" />
          </el-select>
          <span v-else>{{ row.isAbnormal }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.remark" size="small" @change="(v: string) => updateSampleCell(1, row.rowId, 'remark', v)" />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-button type="danger" text size="small" @click="removeSample(1, row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>

  <!-- (2) 期后贴现/背书/调整检查 -->
  <div class="check-block">
    <h4 class="card-title">(2) 期后贴现/背书/调整检查</h4>
    <el-button v-if="!isReadonly" size="small" style="margin-bottom:8px" @click="addSample(2)">添加样本</el-button>
    <el-table :data="block2Rows" size="small" border max-height="420" style="width:100%">
      <el-table-column label="客户名称" width="120" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.customerName" size="small" @change="(v: string) => updateSampleCell(2, row.rowId, 'customerName', v)" />
          <span v-else>{{ row.customerName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="日期" width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.date" size="small" @change="(v: string) => updateSampleCell(2, row.rowId, 'date', v)" />
          <span v-else>{{ row.date }}</span>
        </template>
      </el-table-column>
      <el-table-column label="凭证号" width="90">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small" @change="(v: string) => updateSampleCell(2, row.rowId, 'voucherNo', v)" />
          <span v-else>{{ row.voucherNo }}</span>
        </template>
      </el-table-column>
      <el-table-column label="业务内容" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.businessContent" size="small" @change="(v: string) => updateSampleCell(2, row.rowId, 'businessContent', v)" />
          <span v-else>{{ row.businessContent }}</span>
        </template>
      </el-table-column>
      <el-table-column label="对方科目" width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.counterAccount" size="small" @change="(v: string) => updateSampleCell(2, row.rowId, 'counterAccount', v)" />
          <span v-else>
            {{ row.counterAccount }}
            <GtIndexChip v-if="row.counterAccount && row.counterAccount.includes('主营业务收入')" wp-code="D4" label="→D4" style="margin-left:4px" />
          </span>
        </template>
      </el-table-column>
      <el-table-column label="贷方金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.creditAmount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateSampleCell(2, row.rowId, 'creditAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="支持性文件" width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.supportDoc" size="small" @change="(v: string) => updateSampleCell(2, row.rowId, 'supportDoc', v)" />
          <span v-else>{{ row.supportDoc }}</span>
        </template>
      </el-table-column>
      <el-table-column label="是否异常" width="80" align="center">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.isAbnormal" size="small" @change="(v: string) => updateSampleCell(2, row.rowId, 'isAbnormal', v)">
            <el-option label="否" value="否" />
            <el-option label="是" value="是" />
          </el-select>
          <span v-else>{{ row.isAbnormal }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.remark" size="small" @change="(v: string) => updateSampleCell(2, row.rowId, 'remark', v)" />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-button type="danger" text size="small" @click="removeSample(2, row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
  </template>

  <!-- 检查比例汇总 -->
  <div class="check-block">
    <h4 class="card-title">检查比例汇总</h4>
    <el-table :data="checkRatioSummary" size="small" border>
      <el-table-column prop="direction" label="方向" width="140" />
      <el-table-column label="账面金额" width="150" align="right">
        <template #default="{ row }">
          <span class="cross-sheet-cell" title="来源：D6-2期末审定合计">{{ fmtAmt(row.bookAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="检查金额" width="150" align="right">
        <template #default="{ row }">{{ fmtAmt(row.checkAmount) }}</template>
      </el-table-column>
      <el-table-column label="检查比例" width="120" align="right">
        <template #default="{ row }">{{ fmtPct(row.ratio) }}</template>
      </el-table-column>
    </el-table>
  </div>

  <!-- 审计说明/结论 -->
  <div class="audit-notes-section">
    <h4>审计说明</h4>
    <el-input v-model="auditNotes.explanation" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly" placeholder="检查过程及发现..." />
    <div class="note-actions">
      <el-button size="small" @click="openReview('D6-6-note-explanation')">💬复核</el-button>
    </div>
  </div>
  <div class="audit-notes-section">
    <h4>审计结论</h4>
    <el-input v-model="auditNotes.conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="检查结论..." />
    <div class="note-actions">
      <el-button size="small" @click="openReview('D6-6-note-conclusion')">💬复核</el-button>
    </div>
  </div>
</div>
</template>

<script setup lang="ts">
/**
 * D6TabInspection.vue — 合同资产检查表 D6-6
 */
import { computed, inject, type Ref } from 'vue'
import { useD6Inspection } from '../composables/useD6Inspection'
import { useD6ImportExport } from '../composables/useD6ImportExport'
import { useWorkpaperBrowseMode } from '../composables/useWorkpaperBrowseMode'
import { virtualTextCol, virtualNumCol } from '../composables/virtualColumnHelpers'
import type { VirtualColumn } from '@/composables/useVirtualTable'
import type { ChecklistResponse } from '../composables/useD6FormData'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
function openReview(sectionId: string) { openReviewDialog(sectionId) }
const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
const wpIdRef = computed(() => props.wpId) as unknown as Ref<string>
const periodIe = useD6ImportExport({
  wpId: wpIdRef,
  sheetCode: 'D6-6-period',
  onImported: () => reloadWorkpaperData?.() ?? Promise.resolve(),
})
const postIe = useD6ImportExport({
  wpId: wpIdRef,
  sheetCode: 'D6-6-post',
  onImported: () => reloadWorkpaperData?.() ?? Promise.resolve(),
})

async function onImportPeriodFile(file: File) {
  await periodIe.importData(file)
  return false
}

async function onImportPostFile(file: File) {
  await postIe.importData(file)
  return false
}

const {
  samplingParams, block1Rows, block2Rows,
  addSample, removeSample, updateSampleCell,
  checkRatioSummary, auditNotes,
} = useD6Inspection({
  allResponses: props.allResponses,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
})

const sampleCount = computed(() => block1Rows.value.length + block2Rows.value.length)

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(ratio: number): string {
  if (!ratio) return '-'
  return `${(ratio * 100).toFixed(1)}%`
}

const browseRows = computed(() => [
  ...block1Rows.value.map(r => ({
    section: '(1)本期',
    customerName: r.customerName,
    voucherNo: r.voucherNo,
    amount: (r.debitAmount ?? 0) || (r.creditAmount ?? 0),
  })),
  ...block2Rows.value.map(r => ({
    section: '(2)期后',
    customerName: r.customerName,
    voucherNo: r.voucherNo,
    amount: r.creditAmount ?? 0,
  })),
])

const browseRowCount = computed(() => browseRows.value.length)

const virtualColumns = computed<VirtualColumn[]>(() => [
  virtualTextCol('section', '区块', 80),
  virtualTextCol('customerName', '客户名称', 140),
  virtualTextCol('voucherNo', '凭证号', 100),
  virtualNumCol('amount', '金额', 110, fmtAmt),
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
</script>

<style scoped>
.d6-tab-inspection { padding: 16px; }
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
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
.cross-sheet-cell { background: #ecf5ff; padding: 2px 6px; border-radius: 2px; }
.audit-notes-section { margin-top: 16px; }
.audit-notes-section h4 { font-size: 14px; font-weight: 600; margin-bottom: 8px; }
.note-actions { display: flex; gap: 8px; margin-top: 6px; }
</style>
