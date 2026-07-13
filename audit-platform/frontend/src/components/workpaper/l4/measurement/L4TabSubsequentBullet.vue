<template>
  <div class="l4-tab-subsequent-bullet">
    <!-- ═══ 标题 + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <h3 class="section-title">L4-7A 后续计量（到期一次还本付息）</h3>
        <el-tag type="info" size="small">利息资本化滚入</el-tag>
        <GtIndexChip value="L2" :context-project-id="props.projectId" />
        <GtIndexChip value="L8" :context-project-id="props.projectId" />
      </div>
      <div class="section-header-right">
        <el-button size="small" type="success" :disabled="isReadonly" @click="handlePublishInterest">
          发布利息→L2/L8
        </el-button>
        <el-button size="small" @click="handleAI('subsequent')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>到期一次还本付息：</strong>
        期间不支付利息，利息费用全部资本化滚入摊余成本。
        每期利息费用 = 期初摊余成本 × 实际利率；期末摊余成本 = 期初 + 利息费用（持续增长至到期日还本付息）。
      </div>
    </div>

    <!-- ═══ 债券选择器 ═══ -->
    <div class="bond-selector" v-if="bondParams.length > 1">
      <span class="selector-label">选择债券：</span>
      <el-segmented v-model="activeBondIndex" :options="bondOptions" size="small" />
    </div>

    <!-- ═══ 摊销表 ═══ -->
    <el-table
      :data="activeSchedule"
      border
      size="small"
      style="width: 100%"
      :row-class-name="getRowClassName"
    >
      <el-table-column prop="period" label="期数" width="60" align="center" />

      <el-table-column label="期初摊余成本" min-width="140" align="right">
        <template #default="{ row }">
          <span>{{ fmtAmount(row.beginCost) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="票面利息" min-width="120" align="right">
        <template #header>
          <el-tooltip content="面值 × 票面利率（到期一次还本付息时实际不支付，仅作参考）" placement="top">
            <span class="formula-col-header">票面利息</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="text-muted">{{ fmtAmount(row.couponInterest) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="实际利息费用" min-width="140" align="right">
        <template #header>
          <el-tooltip content="期初摊余成本 × 实际利率" placement="top">
            <span class="formula-col-header">实际利息费用</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-value">{{ fmtAmount(row.interestExpense) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="利息调整摊销" min-width="130" align="right">
        <template #header>
          <el-tooltip content="实际利息 − 票面利息" placement="top">
            <span class="formula-col-header">利息调整摊销</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span>{{ fmtAmount(row.amortization) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="期末摊余成本" min-width="140" align="right">
        <template #header>
          <el-tooltip content="期初 + 利息费用（利息全部资本化）" placement="top">
            <span class="formula-col-header">期末摊余成本</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-value">{{ fmtAmount(row.endCost) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 验证结果 ═══ -->
    <div class="validation-bar" v-if="activeSchedule.length > 0">
      <el-alert
        :title="activeValidation.message"
        :type="activeValidation.isValid ? 'success' : 'warning'"
        :closable="false"
        show-icon
      />
    </div>

    <!-- ═══ 利息费用合计 ═══ -->
    <div class="summary-bar">
      <span>当期利息费用：<strong class="formula-value">{{ fmtAmount(currentPeriodInterest) }}</strong></span>
      <span>累计利息费用：<strong>{{ fmtAmount(totalInterestExpense) }}</strong></span>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="l4-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>到期一次还本付息：期间不付息，利息费用全部资本化</li>
        <li>期末摊余成本 = 期初 + 利息费用（持续递增）</li>
        <li>注意：此分支末期摊余成本含累积利息，远大于面值（正常现象）</li>
        <li>"发布利息→L2/L8"将当期利息费用联动至L2应付利息/L8财务费用</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L4TabSubsequentBullet — L4-7A 后续计量（到期一次还本付息）
 *
 * Requirements: 4.1-4.8
 * - 分支A: 利息资本化，期末=期初+利息费用
 * - 完整摊销表 + 末期验证
 * - publish 'l4:interest-calculated' → L2/L8联动
 */
import { computed, inject, onMounted, ref } from 'vue'
import { MagicStick, Check } from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { useL4FormData } from '../../composables/useL4FormData'
import { useL4Subsequent, type L4BondBranch, type L4SubsequentBondParams } from '../../composables/useL4Subsequent'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<() => void>('openReviewDialog', () => {})
const bondBranch = inject<import('vue').Ref<L4BondBranch>>('bondBranch', ref('bullet'))

// ─── FormData + Composable ───────────────────────────────────────────────────

const formData = useL4FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const bondParams = ref<L4SubsequentBondParams[]>([])

const {
  activeBondIndex,
  activeSchedule,
  activeValidation,
  totalInterestExpense,
  currentPeriodInterest,
  publishInterestCalculated,
  saveSchedule,
  selectBond,
} = useL4Subsequent(formData, ref('bullet') as import('vue').Ref<L4BondBranch>, bondParams)

// ─── 债券选择器选项 ─────────────────────────────────────────────────────────

const bondOptions = computed(() =>
  bondParams.value.map((p, i) => ({ label: p.bondName || `债券${i + 1}`, value: i }))
)

// ─── Handlers ────────────────────────────────────────────────────────────────

function handlePublishInterest() {
  publishInterestCalculated()
}

function getRowClassName({ rowIndex }: { rowIndex: number }) {
  if (rowIndex === activeSchedule.value.length - 1) return 'last-period-row'
  return ''
}

function handleAI(section: string) {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: `l4-subsequent-bullet-${section}`,
      prompt: `请基于应付债券后续计量（到期一次还本付息）"${section}"数据，验证实际利率法摊销合理性`,
      context: { section, wpId: props.wpId },
    }).catch(() => {})
  })
}
function handleReview() { openReviewDialog?.() }

function fmtAmount(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

onMounted(async () => {
  await formData.loadData()
})
</script>

<style scoped>
.l4-tab-subsequent-bullet { padding: 12px; font-size: var(--wp-font-size, 13px); }

.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }

.methodology-context {
  border-left: 4px solid #e6a23c; background: #fdf6ec;
  padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px;
}
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }

.bond-selector { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.selector-label { font-size: var(--wp-font-size, 13px); color: #606266; }

.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.text-muted { color: #909399; }

:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.last-period-row) { background-color: #fef0f0 !important; }

.validation-bar { margin-top: 12px; }

.summary-bar {
  display: flex; gap: 24px; padding: 10px 16px; margin-top: 12px;
  background: #f5f7fa; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266;
}

.l4-details-tip {
  margin-top: 16px; padding: 12px 16px; background: #fafafa;
  border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266;
}
.l4-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l4-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
