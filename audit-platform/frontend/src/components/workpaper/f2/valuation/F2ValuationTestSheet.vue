<template>
  <div class="f2-val-sheet">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 选取样本存货品种，按选定计价方法重新计算发出成本，与账面金额比对验证计价方法运用的正确性。</p>
        <p>2. 灰色底纹列为自动计算列（审计金额 / 差异额 / 差异率），由系统按计价公式重算，不可手动编辑。</p>
        <p>3. 差异率超过阈值（{{ thresholdRate }}%）的样本自动标红，须在测试结论中分析差异原因及影响。</p>
        <p>4. {{ guidanceText }}</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：验证被审计单位发出存货计价方法运用的正确性与前后期一贯性，确认存货成本结转准确、无人为调节。"
    />

    <header class="sheet-header">
      <div><h3>{{ title }}</h3><span class="code">{{ sheetCode }}</span></div>
      <div class="stat-row">
        <el-tag v-if="exceedCount > 0" type="danger">超差异 {{ exceedCount }} 笔</el-tag>
        <span class="stat sub">阈值 {{ thresholdRate }}%</span>
      </div>
    </header>

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

    <!-- 抽凭引擎折叠区 -->
    <el-collapse v-if="wpId && projectId && !isReadonly" class="sampling-collapse">
      <el-collapse-item title="⚡ 自动抽凭（存货科目 1401~1411）" name="sampling">
        <GtVoucherSamplingEngine
          account-code="1401,1402,1403,1404,1405,1406,1407,1408,1409,1410,1411"
          phase="final"
          default-method="random"
          :workpaper-id="wpId"
          :project-id="projectId"
          :year="auditYear"
          @filled="handleSamplingFilled"
        />
      </el-collapse-item>
    </el-collapse>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="$emit('addRow')">+ 新增样本</el-button>
        <el-segmented v-if="segments.length > 0" v-model="activeSegment" :options="segments" size="small" />
      </div>
      <div class="toolbar-right">
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
        <span class="chip-wrap"><GtIndexChip value="wp:F2-1" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ displayRows.length }} 行</el-tag>
      </div>
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

    <!-- 测试结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <span class="conclusion-header">测试结论</span>
      </template>
      <el-input
        :model-value="testConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        @update:model-value="(v: string) => $emit('update:testConclusion', v)"
      />
    </el-card>

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
  segments: () => [],
  defaultSegment: '',
})

const emit = defineEmits<{
  addRow: []
  removeRow: [id: string]
  updateRow: [id: string, patch: Partial<ValuationTestRow>]
  samplingFilled: [payload: { samples: SampledVoucher[]; fillMode: FillMode }]
  'update:testConclusion': [text: string]
}>()

const activeSegment = ref(props.defaultSegment || (props.segments.length ? props.segments[0].value : ''))

// 虚拟滚动: >50行启用更大的maxHeight
const tableMaxHeight = computed(() => props.displayRows.length > 50 ? 560 : 420)

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
.f2-val-sheet :deep(.el-table) { --el-table-font-size: 13px; font-size: 13px; }
.f2-val-sheet :deep(.el-table .cell) { font-size: 13px !important; }
/* 编制提示（蓝色） */
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
/* 审计目标 */
.objective-alert { margin-bottom: 12px; }
/* 抽样 */
.sampling-form { margin-bottom: 8px; }
.sampling-collapse { margin-bottom: 8px; }
/* 工具栏 */
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
/* 合计 */
.totals { margin: 10px 0; font-size: 12px; color: #606266; }
.exceed-stat { color: #f56c6c; font-weight: 600; }
/* 计算列灰底 + 公式虚线 */
.valuation-table :deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.valuation-table :deep(.formula) {
  text-decoration: underline dotted #909399;
  cursor: help;
}
/* 结论卡片 */
.conclusion-card { margin-top: 12px; border-radius: 8px; }
.conclusion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.conclusion-header { font-weight: 600; color: #303133; font-size: 14px; }
</style>
