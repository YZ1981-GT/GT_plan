<template>
  <div class="l4-tab-book-recon-bullet">
    <!-- ═══ 标题 + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">L4-8A 账面核对（到期一次还本付息）</h3>
      </div>
      <div class="section-header-right">
        <el-button size="small" @click="handleAI('bookRecon')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title>审计目标（认定）</template>
      <ol class="ao-list">
        <li><b>计价与分摊：</b>初始/后续计量金额（摊余成本）准确，实际利率法应用正确；</li>
        <li><b>准确性：</b>利息费用计算正确，溢折价摊销金额恰当；</li>
        <li><b>截止：</b>利息费用已记录于正确的会计期间。</li>
      </ol>
    </el-alert>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>账面核对（到期一次还本付息分支）：</strong>
        对比实际账面摊余成本与L4-7A测算值。差异=账面−测算，差异超过阈值(默认1元)红色高亮。
        差异应为0或极小尾差，否则需检查账面记录是否有误。
      </div>
    </div>

    <!-- ═══ 债券选择器 ═══ -->
    <div class="bond-selector" v-if="bookData.length > 1">
      <span class="selector-label">选择债券：</span>
      <el-segmented v-model="activeBondIndex" :options="bondOptions" size="small" />
    </div>

    <!-- ═══ 阈值设置 ═══ -->
    <div class="threshold-row">
      <span>差异阈值：</span>
      <el-input-number v-model="thresholdVal" :min="0.01" :step="0.5" :controls="true" size="small" style="width:120px" @change="setThreshold(thresholdVal)" />
      <span>元</span>
    </div>

    <!-- ═══ 核对表 ═══ -->
    <el-table
      :data="activeReconRows"
      border
      size="small"
      style="width: 100%"
      :row-class-name="reconRowClassName"
    >
      <el-table-column prop="period" label="期数" width="60" align="center" />

      <el-table-column label="账面摊余成本" min-width="140" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.bookAmortizedCost"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(val: number | undefined) => handleUpdateBook($index, val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.bookAmortizedCost) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="测算摊余成本" min-width="140" align="right">
        <template #header>
          <el-tooltip content="来自L4-7A后续计量测算值" placement="top">
            <span class="formula-col-header">测算摊余成本</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-value">{{ fmtAmount(row.calcAmortizedCost) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="差异" min-width="120" align="right">
        <template #header>
          <el-tooltip content="账面 − 测算" placement="top">
            <span class="formula-col-header">差异</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span :class="['formula-value', row.isOverThreshold ? 'text-danger-bold' : '']">
            {{ fmtAmount(row.difference) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="状态" width="80" align="center">
        <template #default="{ row }">
          <el-icon v-if="!row.isOverThreshold" class="text-success"><CircleCheckFilled /></el-icon>
          <el-icon v-else class="text-danger"><WarningFilled /></el-icon>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 汇总 ═══ -->
    <div class="summary-bar">
      <span>总行数：<strong>{{ activeSummary.totalRows }}</strong></span>
      <span>一致：<strong class="text-success">{{ activeSummary.matchedRows }}</strong></span>
      <span>超阈值：<strong :class="activeSummary.overThresholdRows > 0 ? 'text-danger' : ''">{{ activeSummary.overThresholdRows }}</strong></span>
      <span>最大差异：<strong>{{ activeSummary.maxAbsDifference.toFixed(2) }}</strong> 元</span>
    </div>

    <!-- ═══ 核对结论 ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">核对结论</span>
          <el-button size="small" @click="handleAI('conclusion')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="请填写账面核对结论..."
        :disabled="isReadonly"
        @change="saveConclusion"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="l4-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>账面摊余成本来自实际账簿记录（明细账/辅助余额表）</li>
        <li>测算值来自L4-7A后续计量摊销表</li>
        <li>差异超阈值需关注，可能是计提不准确或漏记利息调整</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L4TabBookReconBullet — L4-8A 账面核对（到期一次还本付息分支）
 *
 * Requirements: 5.1-5.6
 * - 与L4-7联动（inject同分支）
 * - 差异=账面-测算，|差异|>阈值红色高亮
 */
import { computed, inject, onMounted, ref } from 'vue'
import { MagicStick, Check, CircleCheckFilled, WarningFilled } from '@element-plus/icons-vue'
import { useL4FormData } from '../../composables/useL4FormData'
import { useL4BookRecon } from '../../composables/useL4BookRecon'
import type { L4BondBranch } from '../../composables/useL4Subsequent'
import type { EIRRow } from '../../composables/useL4EIREngine'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<() => void>('openReviewDialog', () => {})

const formData = useL4FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const schedules = ref<EIRRow[][]>([])
const bookData = ref<Array<{ bondName: string; periodCosts: number[] }>>([])

const {
  threshold,
  activeBondIndex,
  activeReconRows,
  activeSummary,
  setThreshold,
  updateBookCost,
  selectBond,
} = useL4BookRecon(formData, ref('bullet') as import('vue').Ref<L4BondBranch>, schedules, bookData)

const thresholdVal = ref(1.0)

const bondOptions = computed(() =>
  bookData.value.map((b, i) => ({ label: b.bondName || `债券${i + 1}`, value: i }))
)

const conclusion = ref('')
function saveConclusion() {
  formData.debouncedSave('L4-8A-conclusion', { remark: conclusion.value || null })
}

function handleUpdateBook(periodIdx: number, val: number) {
  updateBookCost(activeBondIndex.value, periodIdx, val)
}

function reconRowClassName({ row }: { row: any }) {
  return row.isOverThreshold ? 'over-threshold-row' : ''
}

function handleAI(section: string) {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: `l4-book-recon-bullet-${section}`,
      prompt: `请基于应付债券账面核对（到期一次还本付息）"${section}"数据，给出核对差异分析建议`,
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
.l4-tab-book-recon-bullet { padding: 12px; font-size: var(--wp-font-size, 13px); }

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

.threshold-row { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; font-size: var(--wp-font-size, 13px); color: #606266; }

.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.text-danger { color: #f56c6c; }
.text-danger-bold { color: #f56c6c !important; font-weight: 700; }
.text-success { color: #67c23a; }

:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.over-threshold-row) { background-color: #fef0f0 !important; }

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

.audit-objective { margin-bottom: 12px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.55; font-size: 12px; }
.audit-note-card { margin-top: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
</style>
