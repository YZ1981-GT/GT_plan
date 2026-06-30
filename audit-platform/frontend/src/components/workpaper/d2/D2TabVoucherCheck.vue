<script setup lang="ts">
/**
 * D2TabVoucherCheck — 凭证抽查D2-7
 * 抽样参数区 + 凭证明细表(17列) + 进度条 + 底部汇总
 */
import { inject, toRef, type Ref } from 'vue'
import { useD2VoucherCheck } from '../composables/useD2VoucherCheck'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  bsDate: string
}>()

const emit = defineEmits<{
  (e: 'export-template'): void
  (e: 'export-data'): void
  (e: 'import-data'): void
}>()

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

const viewMode = defineModel<'structured' | 'online'>('viewMode', { default: 'structured' })

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
} = useD2VoucherCheck({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  bsDate: toRef(props, 'bsDate') as Ref<string>,
})
</script>

<template>
  <div class="d2-tab-voucher">
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" @click="emit('export-template')">导出模板</el-button>
        <el-button size="small" @click="emit('export-data')">导出数据</el-button>
        <el-button size="small" @click="emit('import-data')">导入数据</el-button>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addSample">添加样本</el-button>
        <el-button size="small" :disabled="isReadonly" @click="autoMarkAllCutoff">自动标记跨期</el-button>
      </div>
      <div class="toolbar-right">
        <el-segmented v-model="viewMode" :options="[
          { label: '结构化视图', value: 'structured' },
          { label: '在线编辑', value: 'online' },
        ]" size="small" />
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

    <!-- 进度条 -->
    <div class="progress-bar">
      <span>抽样进度: {{ progress.current }} / {{ progress.target }}</span>
      <el-progress :percentage="Math.min(progress.ratio * 100, 100)" :stroke-width="8" style="flex:1; margin-left: 12px" />
    </div>

    <!-- 凭证明细表 -->
    <el-table :data="samples" border size="small" :max-height="450" style="width: 100%">
      <el-table-column type="index" label="序号" width="55" />
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
.progress-bar { display: flex; align-items: center; margin-bottom: 12px; font-size: 13px; }
.summary-bar {
  display: flex; gap: 24px; padding: 8px 12px; margin-top: 10px;
  background: #fafafa; border: 1px solid #ebeef5; border-radius: 4px; font-size: 13px;
}
</style>
