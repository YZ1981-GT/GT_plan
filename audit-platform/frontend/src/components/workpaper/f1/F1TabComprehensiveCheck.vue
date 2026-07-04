<template>
<div class="d3-comprehensive-check">
  <!-- 抽样参数区 -->
  <div class="sampling-params-card">
    <h4 class="card-title">抽样参数</h4>
    <div class="params-grid">
      <div class="param-item">
        <span class="param-label">测试总体</span>
        <el-input v-model="samplingParams.testPopulation" size="small" :disabled="isReadonly"
          @change="(val: string) => updateSamplingParams('testPopulation', val)" />
      </div>
      <div class="param-item">
        <span class="param-label">特定样本</span>
        <el-input v-model="samplingParams.specificSamples" size="small" :disabled="isReadonly"
          @change="(val: string) => updateSamplingParams('specificSamples', val)" />
      </div>
      <div class="param-item">
        <span class="param-label">抽样总体</span>
        <el-input v-model="samplingParams.samplingPopulation" size="small" :disabled="isReadonly"
          @change="(val: string) => updateSamplingParams('samplingPopulation', val)" />
      </div>
      <div class="param-item">
        <span class="param-label">抽样方法</span>
        <el-input v-model="samplingParams.samplingMethod" size="small" :disabled="isReadonly"
          @change="(val: string) => updateSamplingParams('samplingMethod', val)" />
      </div>
    </div>
    <!-- 进度条 -->
    <div class="sampling-progress">
      <span>抽样进度：{{ samplingParams.currentSampleSize }} / {{ samplingParams.targetSampleSize }}</span>
      <el-progress
        :percentage="progressPct"
        :stroke-width="8"
        :color="progressPct >= 100 ? '#67c23a' : '#409eff'"
        style="flex: 1; margin-left: 12px"
      />
    </div>
  </div>

  <!-- 汇总 + 导入导出 -->
  <div class="summary-bar">
    <el-tag type="info">已检查：{{ totalChecked }}</el-tag>
    <el-tag :type="anomalyCount > 0 ? 'danger' : 'success'">异常：{{ anomalyCount }}</el-tag>
    <el-tag :type="anomalyRate > 10 ? 'danger' : 'info'">异常率：{{ anomalyRate.toFixed(1) }}%</el-tag>
    <GtIndexChip target="voucher-sampling-engine" label="抽凭引擎" />
    <el-button-group size="small" style="margin-left: auto">
      <el-button @click="exportTemplate('F1-7')">导出模板</el-button>
      <el-button @click="exportData('F1-7')">导出数据</el-button>
      <el-upload :show-file-list="false" accept=".xlsx" :disabled="isReadonly || importing" :before-upload="(file: any) => handleImport(file, 'F1-7')">
        <el-button>导入数据</el-button>
      </el-upload>
    </el-button-group>
  </div>

  <!-- (1) 本期增减变动 -->
  <div class="vc-section">
    <div class="section-header">
      <h4>(1) 本期增减变动检查</h4>
      <el-button size="small" :disabled="isReadonly" @click="addSample('current')">+ 添加样本</el-button>
    </div>
    <el-table :data="currentChangeRows" size="small" border stripe :height="currentChangeRows.length > 15 ? '400px' : undefined">
      <el-table-column type="index" label="#" width="40" />
      <el-table-column label="客户名称" width="120">
        <template #default="{ row }">
          <el-input v-model="row.customerName" size="small" :disabled="isReadonly"
            @change="(val: string) => updateCell('current', row.rowId, 'customerName', val)" />
        </template>
      </el-table-column>
      <el-table-column label="日期" width="100">
        <template #default="{ row }">
          <el-input v-model="row.date" size="small" :disabled="isReadonly" placeholder="YYYY-MM-DD"
            @change="(val: string) => updateCell('current', row.rowId, 'date', val)" />
        </template>
      </el-table-column>
      <el-table-column label="凭证号" width="90">
        <template #default="{ row }">
          <el-input v-model="row.voucherNo" size="small" :disabled="isReadonly"
            @change="(val: string) => updateCell('current', row.rowId, 'voucherNo', val)" />
        </template>
      </el-table-column>
      <el-table-column label="业务内容" width="130">
        <template #default="{ row }">
          <el-input v-model="row.businessContent" size="small" :disabled="isReadonly"
            @change="(val: string) => updateCell('current', row.rowId, 'businessContent', val)" />
        </template>
      </el-table-column>
      <el-table-column label="对方科目" width="100">
        <template #default="{ row }">
          <el-input v-model="row.counterAccount" size="small" :disabled="isReadonly"
            @change="(val: string) => updateCell('current', row.rowId, 'counterAccount', val)" />
        </template>
      </el-table-column>
      <el-table-column label="对方明细" width="100">
        <template #default="{ row }">
          <el-input v-model="row.counterDetailAccount" size="small" :disabled="isReadonly"
            @change="(val: string) => updateCell('current', row.rowId, 'counterDetailAccount', val)" />
        </template>
      </el-table-column>
      <el-table-column label="借方" width="100" align="right">
        <template #default="{ row }">
          <el-input v-model.number="row.debitAmount" size="small" :disabled="isReadonly"
            @change="(val: any) => updateCell('current', row.rowId, 'debitAmount', val)" />
        </template>
      </el-table-column>
      <el-table-column label="贷方" width="100" align="right">
        <template #default="{ row }">
          <el-input v-model.number="row.creditAmount" size="small" :disabled="isReadonly"
            @change="(val: any) => updateCell('current', row.rowId, 'creditAmount', val)" />
        </template>
      </el-table-column>
      <el-table-column label="原始凭证" width="100">
        <template #default="{ row }">
          <el-input v-model="row.supportingDoc" size="small" :disabled="isReadonly"
            @change="(val: string) => updateCell('current', row.rowId, 'supportingDoc', val)" />
        </template>
      </el-table-column>
      <el-table-column label="核1" width="40" align="center">
        <template #default="{ row }">
          <el-checkbox v-model="row.checkItems[0]" :disabled="isReadonly"
            @change="(val: any) => updateCell('current', row.rowId, 'checkItems.0', val)" />
        </template>
      </el-table-column>
      <el-table-column label="核2" width="40" align="center">
        <template #default="{ row }">
          <el-checkbox v-model="row.checkItems[1]" :disabled="isReadonly"
            @change="(val: any) => updateCell('current', row.rowId, 'checkItems.1', val)" />
        </template>
      </el-table-column>
      <el-table-column label="核3" width="40" align="center">
        <template #default="{ row }">
          <el-checkbox v-model="row.checkItems[2]" :disabled="isReadonly"
            @change="(val: any) => updateCell('current', row.rowId, 'checkItems.2', val)" />
        </template>
      </el-table-column>
      <el-table-column label="核4" width="40" align="center">
        <template #default="{ row }">
          <el-checkbox v-model="row.checkItems[3]" :disabled="isReadonly"
            @change="(val: any) => updateCell('current', row.rowId, 'checkItems.3', val)" />
        </template>
      </el-table-column>
      <el-table-column label="核5" width="40" align="center">
        <template #default="{ row }">
          <el-checkbox v-model="row.checkItems[4]" :disabled="isReadonly"
            @change="(val: any) => updateCell('current', row.rowId, 'checkItems.4', val)" />
        </template>
      </el-table-column>
      <el-table-column label="索引" width="70">
        <template #default="{ row }">
          <el-input v-model="row.indexRef" size="small" :disabled="isReadonly"
            @change="(val: string) => updateCell('current', row.rowId, 'indexRef', val)" />
        </template>
      </el-table-column>
      <el-table-column label="异常" width="80">
        <template #default="{ row }">
          <el-input v-model="row.isAbnormal" size="small" :disabled="isReadonly"
            :class="{ 'abnormal-cell': row.isAbnormal }"
            @change="(val: string) => updateCell('current', row.rowId, 'isAbnormal', val)" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="50" v-if="!isReadonly">
        <template #default="{ row }">
          <el-popconfirm title="删除？" @confirm="removeSample('current', row.rowId)">
            <template #reference><el-button size="small" type="danger" link>删</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>
  </div>

  <!-- (2) 期后结转检查 -->
  <div class="vc-section">
    <div class="section-header">
      <h4>(2) 期后结转检查</h4>
      <el-button-group size="small">
        <el-button @click="exportTemplate('F1-7-post')">导出模板</el-button>
        <el-button @click="exportData('F1-7-post')">导出数据</el-button>
        <el-upload :show-file-list="false" accept=".xlsx" :disabled="isReadonly || importing" :before-upload="(file: any) => handleImport(file, 'F1-7-post')">
          <el-button>导入数据</el-button>
        </el-upload>
      </el-button-group>
      <el-button size="small" :disabled="isReadonly" @click="addSample('postPeriod')">+ 添加样本</el-button>
    </div>
    <el-table :data="postPeriodRows" size="small" border stripe :height="postPeriodRows.length > 15 ? '400px' : undefined">
      <el-table-column type="index" label="#" width="40" />
      <el-table-column label="客户名称" width="120">
        <template #default="{ row }">
          <el-input v-model="row.customerName" size="small" :disabled="isReadonly"
            @change="(val: string) => updateCell('postPeriod', row.rowId, 'customerName', val)" />
        </template>
      </el-table-column>
      <el-table-column label="日期" width="100">
        <template #default="{ row }">
          <el-input v-model="row.date" size="small" :disabled="isReadonly" placeholder="YYYY-MM-DD"
            @change="(val: string) => updateCell('postPeriod', row.rowId, 'date', val)" />
        </template>
      </el-table-column>
      <el-table-column label="凭证号" width="90">
        <template #default="{ row }">
          <el-input v-model="row.voucherNo" size="small" :disabled="isReadonly"
            @change="(val: string) => updateCell('postPeriod', row.rowId, 'voucherNo', val)" />
        </template>
      </el-table-column>
      <el-table-column label="业务内容" width="130">
        <template #default="{ row }">
          <el-input v-model="row.businessContent" size="small" :disabled="isReadonly"
            @change="(val: string) => updateCell('postPeriod', row.rowId, 'businessContent', val)" />
        </template>
      </el-table-column>
      <el-table-column label="对方科目" width="100">
        <template #default="{ row }">
          <el-input v-model="row.counterAccount" size="small" :disabled="isReadonly"
            @change="(val: string) => updateCell('postPeriod', row.rowId, 'counterAccount', val)" />
        </template>
      </el-table-column>
      <el-table-column label="对方明细" width="100">
        <template #default="{ row }">
          <el-input v-model="row.counterDetailAccount" size="small" :disabled="isReadonly"
            @change="(val: string) => updateCell('postPeriod', row.rowId, 'counterDetailAccount', val)" />
        </template>
      </el-table-column>
      <el-table-column label="贷方" width="100" align="right">
        <template #default="{ row }">
          <el-input v-model.number="row.creditAmount" size="small" :disabled="isReadonly"
            @change="(val: any) => updateCell('postPeriod', row.rowId, 'creditAmount', val)" />
        </template>
      </el-table-column>
      <el-table-column label="原始凭证" width="100">
        <template #default="{ row }">
          <el-input v-model="row.supportingDoc" size="small" :disabled="isReadonly"
            @change="(val: string) => updateCell('postPeriod', row.rowId, 'supportingDoc', val)" />
        </template>
      </el-table-column>
      <el-table-column label="核1" width="40" align="center">
        <template #default="{ row }">
          <el-checkbox v-model="row.checkItems[0]" :disabled="isReadonly"
            @change="(val: any) => updateCell('postPeriod', row.rowId, 'checkItems.0', val)" />
        </template>
      </el-table-column>
      <el-table-column label="核2" width="40" align="center">
        <template #default="{ row }">
          <el-checkbox v-model="row.checkItems[1]" :disabled="isReadonly"
            @change="(val: any) => updateCell('postPeriod', row.rowId, 'checkItems.1', val)" />
        </template>
      </el-table-column>
      <el-table-column label="核3" width="40" align="center">
        <template #default="{ row }">
          <el-checkbox v-model="row.checkItems[2]" :disabled="isReadonly"
            @change="(val: any) => updateCell('postPeriod', row.rowId, 'checkItems.2', val)" />
        </template>
      </el-table-column>
      <el-table-column label="核4" width="40" align="center">
        <template #default="{ row }">
          <el-checkbox v-model="row.checkItems[3]" :disabled="isReadonly"
            @change="(val: any) => updateCell('postPeriod', row.rowId, 'checkItems.3', val)" />
        </template>
      </el-table-column>
      <el-table-column label="核5" width="40" align="center">
        <template #default="{ row }">
          <el-checkbox v-model="row.checkItems[4]" :disabled="isReadonly"
            @change="(val: any) => updateCell('postPeriod', row.rowId, 'checkItems.4', val)" />
        </template>
      </el-table-column>
      <el-table-column label="索引" width="70">
        <template #default="{ row }">
          <el-input v-model="row.indexRef" size="small" :disabled="isReadonly"
            @change="(val: string) => updateCell('postPeriod', row.rowId, 'indexRef', val)" />
        </template>
      </el-table-column>
      <el-table-column label="异常" width="80">
        <template #default="{ row }">
          <el-input v-model="row.isAbnormal" size="small" :disabled="isReadonly"
            :class="{ 'abnormal-cell': row.isAbnormal }"
            @change="(val: string) => updateCell('postPeriod', row.rowId, 'isAbnormal', val)" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="50" v-if="!isReadonly">
        <template #default="{ row }">
          <el-popconfirm title="删除？" @confirm="removeSample('postPeriod', row.rowId)">
            <template #reference><el-button size="small" type="danger" link>删</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>
  </div>

  <!-- F1-2 Z列合计交叉验证 -->
  <el-alert
    v-if="postPeriodCrossValidation"
    :title="postPeriodCrossValidation"
    type="warning"
    :closable="false"
    show-icon
    style="margin: 12px 0"
  />

  <!-- 复核入口 -->
  <div class="review-actions">
    <el-button size="small" @click="openReview">💬 复核</el-button>
  </div>
</div>
</template>

<script setup lang="ts">
/**
 * F1TabComprehensiveCheck.vue — F1-7 综合检查表
 * 抽样参数 + (1)本期增减 + (2)期后结转 + 汇总 + 跨期标记
 */
import { computed, inject, type Ref } from 'vue'
import { useF1VoucherCheck } from '../composables/useF1VoucherCheck'
import { useF1ImportExport, type F1ImportSheet } from '../composables/useWorkpaperImportExport'
import type { ChecklistResponse } from '../composables/useF1FormData'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  isReadonly: boolean
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const {
  samplingParams,
  currentChangeRows,
  postPeriodRows,
  totalChecked,
  anomalyCount,
  anomalyRate,
  addSample,
  removeSample,
  updateCell,
  updateSamplingParams,
} = useF1VoucherCheck({
  allResponses: props.allResponses,
  wpId: props.wpId,
  projectId: props.projectId,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})

const progressPct = computed(() => {
  if (!samplingParams.value.targetSampleSize) return 0
  return Math.min(100, Math.round((samplingParams.value.currentSampleSize / samplingParams.value.targetSampleSize) * 100))
})

// ─── F1-2 Z列合计交叉验证 ───────────────────────────────────────────────────
import { useF1CrossSheet } from '../composables/useF1CrossSheet'
import { parseNum } from '../composables/useF1FormulaEngine'

const crossSheet = useF1CrossSheet({ allResponses: props.allResponses })

/** F1-2 Z列（期后结转）合计 vs F1-7 (2)期后结转贷方合计 交叉验证 */
const postPeriodCrossValidation = computed(() => {
  const d37Total = crossSheet.postPeriodSettlementSync.value.total
  if (d37Total === 0) return ''

  // 从 F1-2 明细行聚合 Z列合计
  const detResp = props.allResponses.value.get('F1-det-rows')
  let d32ZTotal = 0
  if (detResp?.remark) {
    try {
      const rows = JSON.parse(detResp.remark) as Array<{ postPeriodSettlement?: number }>
      d32ZTotal = rows.reduce((sum, r) => sum + parseNum(r.postPeriodSettlement), 0)
    } catch { /* ignore */ }
  }

  const diff = Math.abs(d32ZTotal - d37Total)
  if (diff < 0.01) return ''
  return `F1-2期后结转（Z列）合计 ${d32ZTotal.toLocaleString()} 元 ≠ F1-7期后结转贷方合计 ${d37Total.toLocaleString()} 元，差额 ${diff.toLocaleString()} 元`
})

function openReview() {
  openReviewDialog('F1-vc-review')
}

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
const { exportTemplate, exportData, importData, importing } = useF1ImportExport({ wpId: props.wpId })

async function handleImport(file: File, sheet: F1ImportSheet): Promise<boolean> {
  const result = await importData(sheet, file)
  if (result) await reloadWorkpaperData?.()
  return false
}
</script>

<style scoped>
.d3-comprehensive-check { padding: 16px; }
.sampling-params-card { padding: 16px; background: #fff; border: 1px solid #ebeef5; border-radius: 6px; margin-bottom: 16px; }
.card-title { font-size: 14px; font-weight: 600; margin-bottom: 12px; }
.params-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px; }
.param-item { display: flex; align-items: center; gap: 8px; }
.param-label { font-size: 12px; color: #909399; white-space: nowrap; min-width: 60px; }
.sampling-progress { display: flex; align-items: center; font-size: 12px; color: #606266; }
.summary-bar { display: flex; gap: 12px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.vc-section { margin-bottom: 20px; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.section-header h4 { font-size: 14px; font-weight: 600; }
.abnormal-cell :deep(.el-input__inner) { color: #f56c6c; font-weight: 600; }
.review-actions { margin-top: 12px; }
</style>
