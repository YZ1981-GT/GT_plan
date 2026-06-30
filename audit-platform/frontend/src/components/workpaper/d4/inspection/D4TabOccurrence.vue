<script setup lang="ts">
/**
 * D4TabOccurrence — D4-14 发生检查
 *
 * 抽样参数区 + 凭证明细表 + 异常率统计
 * Requirements: 10.5-10.8, 19.6
 */
import { inject, toRef, computed, type Ref } from 'vue'
import { useD4Inspection, type SamplingParams, type VoucherCheckRow } from '../../composables/useD4Inspection'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const { occurrenceSampling, occurrenceRows, computeAnomalyRate, addSample, removeSample } = useD4Inspection({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const anomalyRate = computed(() => computeAnomalyRate(occurrenceRows.value))
const samplingProgress = computed(() => {
  const target = occurrenceSampling.value.targetSampleSize
  if (target === 0) return 0
  return Math.round((occurrenceRows.value.length / target) * 100)
})
</script>

<template>
  <div class="d4-tab-occurrence">
    <!-- Sampling Params -->
    <el-card shadow="never" class="mb-4">
      <template #header><span class="text-sm font-medium">抽样参数</span></template>
      <el-descriptions :column="3" size="small" border>
        <el-descriptions-item label="测试总体">{{ occurrenceSampling.testPopulation || '-' }}</el-descriptions-item>
        <el-descriptions-item label="特定项目">{{ occurrenceSampling.specificSamples || '-' }}</el-descriptions-item>
        <el-descriptions-item label="抽样总体">{{ occurrenceSampling.samplingPopulation || '-' }}</el-descriptions-item>
        <el-descriptions-item label="抽样方法">{{ occurrenceSampling.samplingMethod || '-' }}</el-descriptions-item>
        <el-descriptions-item label="目标样本量">{{ occurrenceSampling.targetSampleSize }}</el-descriptions-item>
        <el-descriptions-item label="已检查">
          {{ occurrenceRows.length }} / {{ occurrenceSampling.targetSampleSize }}
          <el-progress :percentage="samplingProgress" :stroke-width="6" style="width:80px;display:inline-flex;margin-left:8px;" />
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- Anomaly indicator -->
    <div class="mb-3 flex items-center gap-4">
      <span class="text-sm text-gray-600">异常率：</span>
      <el-tag :type="anomalyRate > 5 ? 'danger' : anomalyRate > 0 ? 'warning' : 'success'" size="small">
        {{ anomalyRate.toFixed(1) }}%
      </el-tag>
      <div class="ml-auto">
        <el-button type="primary" size="small" :disabled="isReadonly" @click="addSample('D4-14')">
          + 添加凭证
        </el-button>
      </div>
    </div>

    <!-- Table -->
    <el-table :data="occurrenceRows" border stripe max-height="400">
      <el-table-column prop="voucherNo" label="凭证号" width="100" />
      <el-table-column prop="voucherDate" label="日期" width="100" />
      <el-table-column prop="customerName" label="客户" min-width="120" />
      <el-table-column label="金额" width="120" align="right">
        <template #default="{ row }">{{ row.amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 }) }}</template>
      </el-table-column>
      <el-table-column label="合同" width="60" align="center">
        <template #default="{ row }"><span>{{ row.hasContract || '-' }}</span></template>
      </el-table-column>
      <el-table-column label="发货" width="60" align="center">
        <template #default="{ row }"><span>{{ row.hasDelivery || '-' }}</span></template>
      </el-table-column>
      <el-table-column label="发票" width="60" align="center">
        <template #default="{ row }"><span>{{ row.hasInvoice || '-' }}</span></template>
      </el-table-column>
      <el-table-column label="异常" width="60" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.isAnomalous" type="danger" size="small">!</el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="70" align="center" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button type="danger" size="small" text @click="removeSample('D4-14', row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计说明 -->
    <div class="mt-4">
      <div class="flex items-center justify-between mb-1">
        <label class="text-sm font-medium text-gray-600">审计说明/结论</label>
        <div class="flex gap-2">
          <el-button size="small" disabled>🤖 AI辅助</el-button>
          <el-button v-if="openReviewDialog" size="small" text @click="openReviewDialog('D4-14-note')">💬</el-button>
        </div>
      </div>
      <el-input type="textarea" :rows="3" :disabled="isReadonly" placeholder="请输入发生检查结论..." />
    </div>
  </div>
</template>

<style scoped>
.d4-tab-occurrence { padding: 16px; }
.mt-4 { margin-top: 16px; }
.mb-4 { margin-bottom: 16px; }
.mb-3 { margin-bottom: 12px; }
.mb-1 { margin-bottom: 4px; }
.ml-auto { margin-left: auto; }
</style>
