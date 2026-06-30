<template>
<div class="d7-voucher-check">
  <!-- 双模式切换 -->
  <div class="mode-toolbar">
    <el-segmented v-model="viewMode" :options="modeOptions" size="small" />
  </div>

  <template v-if="viewMode === 'structured'">
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
            <GtIndexChip v-if="row.counterAccount && row.counterAccount.includes('主营业务收入')" wp-code="D4" label="→D4" style="margin-left:4px" />
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

    <!-- 底部汇总 -->
    <div class="summary-section">
      <span>已检查：<strong>{{ checkedCount }}</strong> 笔</span>
      <span>异常：<strong class="abnormal-count">{{ abnormalCount }}</strong> 笔</span>
      <span>异常率：<strong :class="{ 'abnormal-count': abnormalRate > 0 }">{{ (abnormalRate * 100).toFixed(1) }}%</strong></span>
    </div>

    <!-- 审计说明/结论 -->
    <div class="audit-notes-section">
      <h4>审计说明</h4>
      <el-input v-model="auditNotes.explanation" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly" placeholder="凭证检查发现..." />
      <div class="note-actions">
        <el-button size="small" @click="openReview('D7-7-note-explanation')">💬复核</el-button>
      </div>
    </div>
    <div class="audit-notes-section">
      <h4>审计结论</h4>
      <el-input v-model="auditNotes.conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="凭证检查结论..." />
      <div class="note-actions">
        <el-button size="small" @click="openReview('D7-7-note-conclusion')">💬复核</el-button>
      </div>
    </div>
  </template>

  <div v-else class="oo-mode-placeholder">
    <el-empty description="OnlyOffice 在线编辑模式（待OO服务就绪后启用）" />
  </div>
</div>
</template>

<script setup lang="ts">
/**
 * D7TabVoucherCheck.vue — 凭证检查 D7-7 (~350行)
 * 3区域：抽样参数 + (1)本期增减变动 + (2)期后结转
 * Task: 22.1
 * Requirements: 12.1-12.9, 18.5, 19.4, 20.1, 21.1-21.3
 */
import { ref, computed, inject, type Ref } from 'vue'
import { useD7VoucherCheck } from '../composables/useD7VoucherCheck'
import type { ChecklistResponse } from '../composables/useD7FormData'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet: any
}>()

const viewMode = ref('structured')
const modeOptions = [
  { label: '结构化视图', value: 'structured' },
  { label: '在线编辑', value: 'onlyoffice' },
]

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
function openReview(sectionId: string) { openReviewDialog(sectionId) }

const {
  samplingParams, periodChangeRows, postTransferRows,
  checkedCount, abnormalCount, abnormalRate,
  addSample, removeSample, updateCell, auditNotes,
} = useD7VoucherCheck({
  allResponses: props.allResponses,
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
</script>

<style scoped>
.d7-voucher-check { padding: 16px; }
.mode-toolbar { margin-bottom: 12px; }
.oo-mode-placeholder { padding: 40px 0; }

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

.check-block { margin-bottom: 20px; }
.abnormal-count { color: #f56c6c; }

.summary-section {
  margin-top: 12px;
  padding: 10px 12px;
  background: #fafafa;
  border-radius: 6px;
  display: flex;
  gap: 24px;
  font-size: 13px;
}

.audit-notes-section { margin-top: 16px; }
.audit-notes-section h4 { font-size: 14px; font-weight: 600; margin-bottom: 8px; }
.note-actions { display: flex; gap: 8px; margin-top: 6px; }
</style>
