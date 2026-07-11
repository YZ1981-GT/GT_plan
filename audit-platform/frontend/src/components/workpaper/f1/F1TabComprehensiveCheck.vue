<template>
<div class="d3-comprehensive-check">
  <!-- 编制提示 -->
  <details class="guidance-details">
    <summary>📋 编制提示</summary>
    <div class="guidance-content">
      <p>1. 本表对预付账款（科目1123）本期增减变动与期后结转进行抽样检查，验证真实性与截止恰当性。</p>
      <p>2. 抽样应结合重要性与风险确定样本量，大额、长账龄、关联方预付款应作为特定样本必选。</p>
      <p>3. 逐笔核对凭证、合同、原始单据，异常项在"异常"列标注并回写审计说明。</p>
      <p>4. 期后结转贷方合计应与 F1-2 期后结转（Z列）勾稽一致，差异须查明原因。</p>
    </div>
  </details>

  <!-- 审计目标 -->
  <el-alert
    type="info"
    :closable="false"
    title="审计目标：验证预付账款本期增减变动的真实性与准确性，检查期后结转情况，评估长期挂账款项的可收回性与截止恰当性。"
    class="objective-alert"
  />

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
  <div class="tab-toolbar">
    <div class="toolbar-left">
      <el-tag type="info">已检查：{{ totalChecked }}</el-tag>
      <el-tag :type="anomalyCount > 0 ? 'danger' : 'success'">异常：{{ anomalyCount }}</el-tag>
      <el-tag :type="anomalyRate > 10 ? 'danger' : 'info'">异常率：{{ anomalyRate.toFixed(1) }}%</el-tag>
      <el-tag size="small" type="warning" effect="plain">抽凭引擎</el-tag>
    </div>
    <div class="toolbar-right">
      <el-dropdown size="small" trigger="click" :disabled="isReadonly">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="exportTemplate('F1-7')">导出模板</el-dropdown-item>
            <el-dropdown-item @click="exportData('F1-7')">导出数据</el-dropdown-item>
            <el-dropdown-item>
              <el-upload :show-file-list="false" accept=".xlsx" :disabled="isReadonly || importing"
                :before-upload="(file: any) => handleImport(file, 'F1-7')">
                <span>导入数据</span>
              </el-upload>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
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
      <div class="section-header-actions">
        <el-dropdown size="small" trigger="click" :disabled="isReadonly">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="exportTemplate('F1-7-post')">导出模板</el-dropdown-item>
              <el-dropdown-item @click="exportData('F1-7-post')">导出数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload :show-file-list="false" accept=".xlsx" :disabled="isReadonly || importing"
                  :before-upload="(file: any) => handleImport(file, 'F1-7-post')">
                  <span>导入数据</span>
                </el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" :disabled="isReadonly" @click="addSample('postPeriod')">+ 添加样本</el-button>
      </div>
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
import { computed, inject, toRef, type Ref } from 'vue'
import { useF1VoucherCheck } from '../composables/useF1ComprehensiveCheck'
import { useF1ImportExport, type F1ImportSheet } from '../composables/useWorkpaperImportExport'
import type { ChecklistResponse } from '../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

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
  allResponses: allResponsesRef,
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
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

const crossSheet = useF1CrossSheet({ allResponses: allResponsesRef })

/** F1-2 Z列（期后结转）合计 vs F1-7 (2)期后结转贷方合计 交叉验证 */
const postPeriodCrossValidation = computed(() => {
  const d37Total = crossSheet.postPeriodSettlementSync.value.total
  if (d37Total === 0) return ''

  // 从 F1-2 明细行聚合 Z列合计
  const detResp = allResponsesRef.value.get('F1-det-rows')
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
const { exportTemplate, exportData, importData, importing } = useF1ImportExport({ wpId: toRef(props, 'wpId') as Ref<string> })

async function handleImport(file: File, sheet: F1ImportSheet): Promise<boolean> {
  const result = await importData(sheet, file)
  if (result) await reloadWorkpaperData?.()
  return false
}
</script>

<style scoped>
.d3-comprehensive-check { padding: 16px; }
.d3-comprehensive-check :deep(.el-table) { --el-table-font-size: 13px; font-size: 13px; }
.d3-comprehensive-check :deep(.el-table .cell) { font-size: 13px !important; }

/* 编制提示 */
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }

/* 工具栏 */
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }

.sampling-params-card { padding: 16px; background: #fff; border: 1px solid #ebeef5; border-radius: 6px; margin-bottom: 16px; }
.card-title { font-size: 14px; font-weight: 600; margin-bottom: 12px; }
.params-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px; }
.param-item { display: flex; align-items: center; gap: 8px; }
.param-label { font-size: 12px; color: #909399; white-space: nowrap; min-width: 60px; }
.sampling-progress { display: flex; align-items: center; font-size: 12px; color: #606266; }
.vc-section { margin-bottom: 20px; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; gap: 8px; }
.section-header h4 { font-size: 14px; font-weight: 600; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }
.abnormal-cell :deep(.el-input__inner) { color: #f56c6c; font-weight: 600; }
.review-actions { margin-top: 12px; }
</style>
