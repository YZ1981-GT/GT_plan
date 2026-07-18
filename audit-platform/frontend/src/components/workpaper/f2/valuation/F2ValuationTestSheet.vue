<template>
  <div class="f2-val-sheet">
    <header class="sheet-header">
      <div><h3>{{ title }}</h3><span class="code">{{ sheetCode }}</span></div>
      <div class="stat-row">
        <el-tag v-if="exceedCount > 0" type="danger">超差异 {{ exceedCount }} 笔</el-tag>
        <span class="stat sub">阈值 {{ thresholdRate }}%</span>
      </div>
    </header>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert" :title="`审计目标：${objectiveText}`" />

    <!-- 工具栏（索引联动 + 计数） -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:F2-1" /></span>
        <el-tag size="small" type="info">共 {{ displayRows.length }} 行</el-tag>
      </div>
    </div>

    <!-- 抽样参数区(6字段横排) -->
    <el-form inline size="small" class="sampling-form">
      <el-form-item label="总体金额">
        <el-input v-model="samplingParams.population" :disabled="isReadonly" style="width:120px" />
      </el-form-item>
      <el-form-item label="样本量">
        <el-input-number v-model="samplingParams.sampleSize" :controls="false" :disabled="isReadonly" style="width:80px" />
      </el-form-item>
      <el-form-item label="抽样方法">
        <el-input v-model="samplingParams.method" :disabled="isReadonly" style="width:100px" />
      </el-form-item>
      <el-form-item label="置信水平">
        <el-input v-model="samplingParams.confidence" :disabled="isReadonly" style="width:70px" />
      </el-form-item>
      <el-form-item label="可接受误差">
        <el-input v-model="samplingParams.tolerableError" :disabled="isReadonly" style="width:70px" />
      </el-form-item>
      <el-form-item label="重要性水平">
        <el-input v-model="samplingParams.conclusion" :disabled="isReadonly" style="width:80px" />
      </el-form-item>
    </el-form>

    <!-- 工具栏 -->
    <div class="toolbar">
      <GtVoucherSamplingEngine
        v-if="wpId && projectId && !isReadonly"
        :project-id="projectId"
        :workpaper-id="wpId"
        :account-code="valuationAccountCodes.join(',')"
        :year="new Date().getFullYear()"
        phase="final"
        dialog-mode
        @filled="handleSamplingFilled"
      />
      <el-button size="small" type="primary" :disabled="isReadonly" @click="$emit('addRow')">+ 新增样本</el-button>
      <F2SheetToolbar
        :wp-id="wpId"
        api-prefix="f2-val"
        :sheet="sheetCode"
        :disabled="isReadonly"
        ai-section="valuation-conclusion"
        :existing-content="testConclusion"
        :related-context="{ exceedCount }"
        :ai-title="`AI 生成 · ${title}结论`"
        :review-section="`${sheetCode}-conclusion`"
        @ai-filled="(t: string) => $emit('update:testConclusion', t)"
      />
      <el-segmented v-if="segments.length > 0" v-model="activeSegment" :options="segments" size="small" />
    </div>

    <!-- 动态行检查表(虚拟滚动>50行) -->
    <el-table
      :data="displayRows"
      border
      size="small"
      :max-height="tableMaxHeight"
      :row-class-name="rowClass"
      class="valuation-table"
    >
      <el-table-column prop="seq" label="序号" width="50" fixed align="center" />
      <el-table-column label="凭证号" width="95" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small"
            @change="(v: string) => $emit('updateRow', row.rowId, { voucherNo: v })" />
          <span v-else>{{ row.voucherNo }}</span>
        </template>
      </el-table-column>
      <el-table-column label="品名" width="110" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.itemName" size="small"
            @change="(v: string) => $emit('updateRow', row.rowId, { itemName: v })" />
          <span v-else>{{ row.itemName }}</span>
        </template>
      </el-table-column>

      <!-- 动态列由插槽提供 -->
      <slot name="columns" :segment="activeSegment" :is-readonly="isReadonly" :fmt="fmt" :fmt-rate="fmtRate" :is-exceed="isExceed" />

      <el-table-column label="" width="48" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="$emit('removeRow', row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 合计行+超差异统计 -->
    <div class="totals">
      账面 {{ fmt(totals.bookIssueAmt) }} | 审计 {{ fmt(totals.auditIssueAmt) }} | 差异 {{ fmt(totals.varianceAmt) }}
      <span v-if="exceedCount > 0" class="exceed-stat"> · 超差异 {{ exceedCount }} 笔</span>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <span class="conclusion-header">审计说明</span>
      </template>
      <el-input
        :model-value="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：概述计价方法测试的抽样与重新计算程序、差异分析及核对结果，以及拟调整/未调整事项及其影响。"
        @update:model-value="(v: string) => $emit('update:auditNote', v)"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <span class="conclusion-header">审计结论</span>
      </template>
      <el-input
        :model-value="testConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="填写审计结论：A、计价方法运用正确、一贯，未见异常。B、除上述应调整事项外，其余未见异常。C、由于存在重大未调整事项或审计范围受限，不可确认。"
        @update:model-value="(v: string) => $emit('update:testConclusion', v)"
      />
    </el-card>

    <!-- 编制提示(折叠) -->
    <details class="guidance-details">
      <summary>编制提示</summary>
      <p>{{ guidanceText }}</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * F2ValuationTestSheet.vue — F2-38/39/40 计价测试通用组件
 * config驱动差异：加权平均/先进先出/标准成本
 * 共享：抽样参数区(6字段) + 动态行 + 差异高亮 + 合计 + 导入导出 + 虚拟滚动 + AI + 编制提示
 */
import { ref, computed } from 'vue'
import { isVarianceExceeding } from '../../composables/useF2ValuationTestFormulas'
import type { ValuationTestRow } from '../../composables/useF2ValuationTestFormulas'
import type { SampledVoucher, FillMode } from '../../composables/useSamplingAlgorithms'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'

export interface SegmentOption {
  label: string
  value: string
}

const props = withDefaults(defineProps<{
  // 配置
  title: string
  sheetCode: string
  thresholdRate: number
  guidanceText?: string
  objectiveText?: string
  auditNote?: string
  segments?: SegmentOption[]
  defaultSegment?: string
  // 数据
  displayRows: ValuationTestRow[]
  totals: { bookIssueAmt: number; auditIssueAmt: number; varianceAmt: number }
  exceedCount: number
  samplingParams: { population: string; sampleSize: number; method: string; confidence: string; tolerableError: string; conclusion: string }
  testConclusion: string
  // 环境
  wpId?: string
  projectId?: string
  auditYear?: number
  isReadonly: boolean
}>(), {
  guidanceText: '请根据抽样结果逐项核对存货计价方法的正确性，关注差异率超过阈值的样本。',
  objectiveText: '选取样本存货品种，重新计算发出/结存成本，验证企业存货计价方法运用的正确性与一贯性，防止计价错误导致成本与存货错报。',
  auditNote: '',
  segments: () => [],
  defaultSegment: '',
})

const emit = defineEmits<{
  addRow: []
  removeRow: [id: string]
  updateRow: [id: string, patch: Partial<ValuationTestRow>]
  samplingFilled: [payload: { samples: SampledVoucher[]; fillMode: FillMode }]
  'update:testConclusion': [text: string]
  'update:auditNote': [text: string]
}>()

const activeSegment = ref(props.defaultSegment || (props.segments.length ? props.segments[0].value : ''))

// 虚拟滚动: >50行启用更大的maxHeight
const tableMaxHeight = computed(() => props.displayRows.length > 50 ? 560 : 420)

// 存货计价测试科目范围（保留原 account-code 值 1401~1411，不新增硬编码）
const valuationAccountCodes = '1401,1402,1403,1404,1405,1406,1407,1408,1409,1410,1411'.split(',')

function handleSamplingFilled(payload: { samples: SampledVoucher[]; fillMode: FillMode }) {
  emit('samplingFilled', payload)
}

function fmt(v: number): string {
  return v === 0 ? '—' : v.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

function fmtRate(r: number | '' | 'N/A'): string {
  if (r === '' || r === 'N/A') return '—'
  return `${(typeof r === 'number' ? r * 100 : 0).toFixed(2)}%`
}

function isExceed(row: { varianceRate: number | '' | 'N/A' }): boolean {
  return isVarianceExceeding(row.varianceRate, props.thresholdRate)
}

function rowClass({ row }: { row: { varianceRate: number | '' | 'N/A' } }): string {
  return isExceed(row) ? 'error-row' : ''
}

defineExpose({ fmt, fmtRate, isExceed, activeSegment })
</script>

<style scoped src="./f2ValSheetStyles.css"></style>
<style scoped>
.sampling-form { margin-bottom: 8px; }
.totals { margin: 10px 0; font-size: 12px; color: #606266; }
.exceed-stat { color: #f56c6c; font-weight: 600; }
.valuation-table :deep(.formula) {
  text-decoration: underline dotted #909399;
  cursor: help;
}
.conclusion-card { margin-top: 12px; }
.conclusion-card :deep(.el-card__header) { padding: 8px 12px; font-size: var(--wp-font-size, 13px); }
.conclusion-header { font-weight: 600; color: #606266; }
.guidance-details { margin-top: 12px; font-size: 12px; color: #909399; }
.guidance-details summary { cursor: pointer; font-weight: 500; }
.guidance-details p { margin: 6px 0 0 12px; line-height: 1.6; }
</style>
