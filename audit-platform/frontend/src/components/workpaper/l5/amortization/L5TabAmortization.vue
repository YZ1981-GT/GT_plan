<template>
  <div class="l5-tab-amortization">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">L5-5 未确认融资费用摊销测算表</h3>
        <el-tag type="danger" size="small">核心·实际利率法</el-tag>
        <GtIndexChip value="L8" :context-project-id="props.projectId" />
      </div>
      <div class="section-header-right">
        <el-button size="small" type="success" :disabled="isReadonly" @click="handlePublishToL8">
          发布摊销→L8
        </el-button>
        <el-button size="small" @click="handleAI('amortization')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 审计目标 ═══ -->
    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
      <template #title>
        <strong>审计目标：</strong>复核未确认融资费用实际利率法摊销测算的准确性，验证末期余额趋近于零，本期摊销正确计入财务费用（联动 L8）。
      </template>
    </el-alert>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>实际利率法摊销（核心）：</strong>
        每期摊销额 = 期初摊余成本 × 实际利率(EIR)；期末摊余成本 = 期初 − 摊销额 + 本期偿还调整。
        全部期数摊销合计 = 初始未确认融资费用总额。最后一期末余额应≈0（允许±1元尾差）。
        本期摊销计入财务费用（联动L8）。
      </div>
    </div>

    <!-- ═══ 款项筛选器 ═══ -->
    <div class="item-selector" v-if="filterOptions.length > 2">
      <span class="selector-label">按款项筛选：</span>
      <el-segmented v-model="selectedFilterKey" :options="filterOptionList" size="small" />
    </div>

    <!-- ═══ 摊销测算主参数区 ═══ -->
    <div class="params-area" v-if="currentItem">
      <el-descriptions :column="4" border size="small">
        <el-descriptions-item label="款项名称">{{ currentItem.payableName }}</el-descriptions-item>
        <el-descriptions-item label="初始摊余成本">{{ fmtAmount(currentItem.initialCost) }}</el-descriptions-item>
        <el-descriptions-item label="实际利率(EIR)">{{ (currentItem.effectiveRate * 100).toFixed(4) }}%</el-descriptions-item>
        <el-descriptions-item label="总期数">{{ currentItem.periods }} 期</el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- ═══ 摊销表 ═══ -->
    <el-table
      :data="currentSchedule"
      border
      size="small"
      style="width: 100%; margin-top: 12px"
      :row-class-name="getRowClassName"
    >
      <el-table-column prop="period" label="期数" width="60" align="center" />
      <el-table-column label="期初摊余成本" min-width="140" align="right">
        <template #default="{ row }">
          <span>{{ fmtAmount(row.beginCost) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="摊销额" min-width="140" align="right">
        <template #header>
          <el-tooltip content="期初摊余成本 × 实际利率" placement="top">
            <span class="formula-col-header">摊销额</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-value">{{ fmtAmount(row.amortization) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期偿还" min-width="120" align="right">
        <template #default="{ row }">
          <span>{{ fmtAmount(row.repayment) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末摊余成本" min-width="140" align="right">
        <template #header>
          <el-tooltip content="期初 − 摊销额（+ 偿还调整）" placement="top">
            <span class="formula-col-header">期末摊余成本</span>
          </el-tooltip>
        </template>
        <template #default="{ row, $index }">
          <span :class="[
            'formula-value',
            $index === currentSchedule.length - 1 && Math.abs(row.endCost) > 1 ? 'text-danger' : ''
          ]">
            {{ fmtAmount(row.endCost) }}
          </span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 验证结果区 ═══ -->
    <div class="validation-area" v-if="validationResults.length > 0">
      <h4 class="sub-title">验证结果</h4>
      <div class="validation-grid">
        <div
          v-for="v in validationResults"
          :key="v.payableName"
          :class="['validation-item', v.isValid ? 'valid' : 'invalid']"
        >
          <el-icon><CircleCheck v-if="v.isValid" /><CircleClose v-else /></el-icon>
          <span class="validation-label">{{ v.payableName }}</span>
          <span class="validation-diff" v-if="!v.isValid">尾差: {{ v.tailDiff.toFixed(2) }}</span>
        </div>
      </div>
    </div>

    <!-- ═══ 合计区 ═══ -->
    <div class="summary-bar">
      <span>本期摊销合计：<strong class="text-primary">{{ fmtAmount(periodAmortizationTotal) }}</strong>（→L8财务费用）</span>
      <span>摊销总额：<strong>{{ fmtAmount(totalAmortizationSum) }}</strong></span>
      <span>
        全部验证：
        <el-tag :type="allValid ? 'success' : 'danger'" size="small">
          {{ allValid ? '✓ 通过' : '✗ 存在尾差' }}
        </el-tag>
      </span>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="l5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>实际利率法：每期摊销=期初摊余成本×EIR</li>
        <li>最后一期末余额应≈0（允许±1元尾差）</li>
        <li>全部期数摊销合计应=初始未确认融资费用</li>
        <li>本期摊销计入财务费用，通过"发布摊销→L8"联动</li>
        <li>EIR=0时摊销=0，需黄色提示</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L5TabAmortization — L5-5 未确认融资费用摊销测算表（核心！）
 * Requirements: 4.1-4.7
 * 实际利率法摊销 + 按款项筛选 + 末期验证 + L8联动publish
 */
import { computed, inject, onMounted, ref } from 'vue'
import { MagicStick, Check, CircleCheck, CircleClose } from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { useL5FormData } from '../../composables/useL5FormData'
import {
  useL5Amortization,
  type L5AmortizationItem,
} from '../../composables/useL5Amortization'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<() => void>('openReviewDialog', () => {})

// ─── FormData + Composable ──────────────────────────────────────────────────

const formData = useL5FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const amortizationItems = ref<L5AmortizationItem[]>([])

const {
  selectedItemKey,
  filterOptions,
  selectItem,
  scheduleMap,
  currentSchedule,
  validationResults,
  allValid,
  periodAmortizationTotal,
  totalAmortizationSum,
  publishAmortization,
  saveUnamortizedTotal,
} = useL5Amortization(formData, amortizationItems)

// ─── 筛选器 ──────────────────────────────────────────────────────────────────

const selectedFilterKey = computed({
  get: () => selectedItemKey.value || '',
  set: (val: string) => selectItem(val || null),
})

const filterOptionList = computed(() =>
  filterOptions.value.map(o => ({ label: o.label, value: o.key }))
)

/** 当前选中的款项数据 */
const currentItem = computed(() => {
  if (!selectedItemKey.value) return amortizationItems.value[0] || null
  return amortizationItems.value.find(i => i.key === selectedItemKey.value) || null
})

// ─── Handlers ────────────────────────────────────────────────────────────────

function handlePublishToL8() {
  publishAmortization()
  saveUnamortizedTotal()
}

function handleAI(_section: string) {}
function handleReview() { openReviewDialog?.() }

/** 标记当前期行 + 末期尾差红色 */
function getRowClassName({ row, rowIndex }: { row: any; rowIndex: number }): string {
  if (currentItem.value && row.period === currentItem.value.currentPeriod) {
    return 'current-period-row'
  }
  if (rowIndex === currentSchedule.value.length - 1 && Math.abs(row.endCost) > 1) {
    return 'invalid-row'
  }
  return ''
}

function fmtAmount(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

onMounted(async () => {
  await formData.loadData()
})
</script>

<style scoped>
.l5-tab-amortization { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }
.item-selector { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.selector-label { font-size: var(--wp-font-size, 13px); color: #606266; white-space: nowrap; }
.params-area { margin-bottom: 12px; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.text-danger { color: #f56c6c !important; }
.text-primary { color: #409eff; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.current-period-row) { background: #ecf5ff !important; }
:deep(.invalid-row) { background: #fef0f0 !important; }
.validation-area { margin-top: 16px; }
.sub-title { margin: 0 0 8px; font-size: 14px; font-weight: 600; color: #303133; }
.validation-grid { display: flex; flex-wrap: wrap; gap: 12px; }
.validation-item { display: flex; align-items: center; gap: 6px; padding: 6px 12px; border-radius: 6px; font-size: var(--wp-font-size, 13px); }
.validation-item.valid { background: #f0f9eb; color: #67c23a; }
.validation-item.invalid { background: #fef0f0; color: #f56c6c; }
.validation-label { font-weight: 500; }
.validation-diff { font-size: 12px; color: #909399; }
.summary-bar { display: flex; gap: 24px; padding: 10px 16px; margin-top: 12px; background: #f5f7fa; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.l5-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.l5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
