<template>
<div class="f1-adjudication">
  <el-skeleton :loading="!sections.length" :rows="8" animated>
    <template #default>
      <!-- 编制提示 -->
      <details class="guidance-details">
        <summary>📋 编制提示</summary>
        <div class="guidance-content">
          <p>1. 本表汇总预付账款（科目1123）审定情况：一、按性质（货款/工程款/设备款/服务费/其他）；二、按账龄（随项目账龄配置，默认「1年以内(含1年)」…「3年以上」）。</p>
          <p>2. 浅蓝底纹单元格由 F1-2 明细表聚合取数，灰色底纹列为审定数（期初/期末审定）自动计算列。</p>
          <p>3. 账龄超过1年的预付账款须说明未结转原因并与 F1-5 长期检查勾稽一致。</p>
          <p>4. 审定合计应与试算平衡表核对一致，差异须查明并通过 F1-3 调整分录处理。</p>
          <p>5. 「带入调整」：可从集中登记按科目 1123 拉取调整分录，逐笔分配到账龄行的期末账项/重分类调整，带入后审定数自动更新并联动附注。</p>
        </div>
      </details>

      <!-- 审计目标 -->
      <el-alert
        type="info"
        :closable="false"
        title="审计目标：确认预付账款期末余额的准确性与列报恰当性，核实按性质/账龄分类的合理性，并与试算平衡表核对一致。"
        class="objective-alert"
      />

      <!-- 四表库取数溯源 -->
      <F1FourTableSourcePanel
        :tb-source-codes="tbSourceCodes"
        :tb-cross-cycle-codes="tbCrossCycleCodes"
        :trial-balance-amount="trialBalanceAmount"
        :leaf-amount="tbLeafAmount"
      />

      <!-- 工具栏 -->
      <div class="tab-toolbar">
        <div class="toolbar-left"></div>
        <div class="toolbar-right">
          <el-button
            size="small"
            type="primary"
            plain
            :loading="pullingFromTb"
            :disabled="isReadonly"
            @click="onPullNatureFromTB"
          >从四表库带入未审数</el-button>
          <el-button size="small" type="primary" plain :loading="adjPull.loading.value" @click="openBringInAdjustment">
            <el-icon><Download /></el-icon>带入调整
          </el-button>
          <span class="chip-wrap"><GtIndexChip value="wp:F1-2" :context-project-id="projectId" /></span>
          <span class="chip-wrap"><GtIndexChip value="wp:F1-5" :context-project-id="projectId" /></span>
          <el-button v-if="openReviewDialog" size="small" @click="openReview">复核</el-button>
        </div>
      </div>

      <F1SheetAttachments
        :project-id="projectId"
        :wp-id="wpId"
        sheet-code="F1-1"
        label="审定表附件"
      />

      <!-- 交叉验证警告 -->
      <el-alert
        v-if="crossValidationWarning"
        type="warning"
        :title="crossValidationWarning"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
      />

      <!-- F1-3 调整分录勾稽告警 -->
      <el-alert
        v-if="adjustmentReconcile.warning"
        type="warning"
        :title="adjustmentReconcile.warning"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
      >
        <template #default>
          <div>{{ adjustmentReconcile.warning }}</div>
          <span class="chip-wrap" style="margin-top: 4px; display: inline-block">
            <GtIndexChip value="wp:F1-3" :context-project-id="projectId" />
          </span>
        </template>
      </el-alert>

      <!-- 双区块表格 -->
      <div v-for="section in sections" :key="section.sectionKey" class="adj-section">
        <h4 class="section-title">{{ section.sectionLabel }}</h4>
        <el-table
          :data="[...section.rows, section.subtotalRow]"
          size="small"
          border
          stripe
          @cell-contextmenu="onCellContextMenu"
        >
          <el-table-column prop="label" label="项目" width="180" fixed>
            <template #default="{ row }">
              <span :class="{ 'subtotal-label': row.rowKey === 'subtotal' }">{{ row.label }}</span>
            </template>
          </el-table-column>
          <!-- 期初 -->
          <el-table-column label="期初未审" width="110">
            <template #default="{ row }">
              <span :class="cellClass(row)" :title="row.isFromCrossSheet ? '来源：F1-2明细表聚合' : ''">
                {{ fmtAmount(row.priorUnadjusted) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="期初AJE" width="100">
            <template #default="{ row }">{{ fmtAmount(row.priorAje) }}</template>
          </el-table-column>
          <el-table-column label="期初RJE" width="100">
            <template #default="{ row }">{{ fmtAmount(row.priorRje) }}</template>
          </el-table-column>
          <el-table-column label="期初审定" width="110" class-name="auto-calc-col">
            <template #default="{ row }">
              <span class="auto-calc">{{ fmtAmount(row.priorAudited) }}</span>
            </template>
          </el-table-column>
          <!-- 期末 -->
          <el-table-column label="期末未审" width="110">
            <template #default="{ row }">
              <span :class="cellClass(row)" :title="row.isFromCrossSheet ? '来源：F1-2明细表聚合' : ''">
                {{ fmtAmount(row.currentUnadjusted) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="期末AJE" width="100">
            <template #default="{ row }">{{ fmtAmount(row.currentAje) }}</template>
          </el-table-column>
          <el-table-column label="期末RJE" width="100">
            <template #default="{ row }">{{ fmtAmount(row.currentRje) }}</template>
          </el-table-column>
          <el-table-column label="期末审定" width="110" class-name="auto-calc-col">
            <template #default="{ row }">
              <span class="auto-calc">{{ fmtAmount(row.currentAudited) }}</span>
            </template>
          </el-table-column>
          <!-- 变动 -->
          <el-table-column label="变动额" width="110">
            <template #default="{ row }">{{ fmtAmount(row.changeAmount) }}</template>
          </el-table-column>
          <el-table-column label="变动率" width="90">
            <template #default="{ row }">
              <span :class="{ 'rate-exceed': isRateExceeding(row.changeRate) }">
                {{ fmtRate(row.changeRate) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="原因分析" min-width="160">
            <template #default="{ row }">
              <el-input
                v-if="row.isEditable"
                v-model="row.reasonAnalysis"
                size="small"
                :disabled="isReadonly"
                @change="(val: string) => updateCell(row.rowKey, 'reasonAnalysis', val)"
              />
              <span v-else>{{ row.reasonAnalysis }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 试算平衡表核对行 -->
      <div class="tb-check-row">
        <span class="tb-label">与试算平衡表核对（科目1123）：试算平衡表数 {{ fmtAmount(trialBalanceAmount) }}</span>
        <el-tag v-if="trialBalanceDiff !== 0" type="danger" size="small">差异 {{ fmtAmount(trialBalanceDiff) }}</el-tag>
        <el-tag v-else type="success" size="small">核对一致</el-tag>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="confirmAdjudication">
          发布审定数（回写TB）
        </el-button>
      </div>

      <!-- 审计说明区（卡片式） -->
      <el-card class="opinion-card" shadow="never">
        <template #header>
          <div class="opinion-header">
            <span class="opinion-title">审计说明与结论</span>
            <div class="opinion-chips">
              <GtIndexChip value="wp:F1-2" :context-project-id="projectId" />
              <GtIndexChip value="wp:F1-5" :context-project-id="projectId" />
            </div>
          </div>
        </template>

        <div class="opinion-section">
          <div class="opinion-section-header">
            <span class="opinion-section-label">(1) 账龄超过1年的预付账款未结转原因</span>
            <div class="opinion-actions">
              <GtIndexChip value="wp:F1-5" :context-project-id="projectId" />
            </div>
          </div>
          <el-input
            v-model="auditNotes.agingReason"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 8 }"
            :disabled="isReadonly"
            placeholder="说明超过1年未结转的原因..."
          />
        </div>

        <div class="opinion-section">
          <div class="opinion-section-header">
            <span class="opinion-section-label">(2) 重大变动分析</span>
            <div class="opinion-actions">
              <el-button
                size="small"
                type="primary"
                plain
                :disabled="isReadonly || !aiAvailable"
                :loading="aiLoading"
                @click="generateChangeAnalysis"
              >AI 生成分析</el-button>
            </div>
          </div>
          <el-input
            v-model="auditNotes.changeAnalysis"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 8 }"
            :disabled="isReadonly"
            placeholder="分析预付账款重大变动原因..."
          />
        </div>

        <div class="opinion-section">
          <div class="opinion-section-header">
            <span class="opinion-section-label">(3) 审计结论</span>
            <div class="opinion-actions">
              <el-button
                size="small"
                type="primary"
                plain
                :disabled="isReadonly || !aiAvailable"
                :loading="aiLoading"
                @click="generateConclusion"
              >AI 生成结论</el-button>
              <el-button v-if="openReviewDialog" size="small" @click="openReview">复核</el-button>
            </div>
          </div>
          <el-input
            v-model="auditNotes.conclusion"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
            :disabled="isReadonly"
            placeholder="对预付账款审定结果的总结性结论..."
          />
        </div>

        <!-- 编制提示：长期挂账 / 重分类 -->
        <details class="cas14-hint">
          <summary>📋 编制要点提示</summary>
          <div class="hint-content">
            关注账龄超过1年的预付款项：核实是否仍具商业实质、能否形成资产或已具备结转/退款条件；
            性质含工程/设备等且预计超过一年结转的，评估是否应重分类至其他非流动资产。
            性质分类合计须与账龄分类合计勾稽一致，并与试算平衡表核对。
          </div>
        </details>
      </el-card>
    </template>
  </el-skeleton>

  <AdjudicationBringInDialog
    v-model="bringInVisible"
    :matches="adjPull.matches.value"
    :row-options="bringInRowOptions"
    subject-label="1123 预付账款"
    :loading="adjPull.loading.value"
    @apply="onBringInApply"
  />
</div>
</template>

<script setup lang="ts">
/**
 * F1TabAdjudication.vue — F1-1 审定表
 * 双区块(按性质+按账龄) + 变动率高亮 + 跨sheet取数 + 审计说明/结论
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import { isChangeRateExceeding } from '../composables/useF1FormulaEngine'
import { useF1Adjudication } from '../composables/useF1Adjudication'
import { useF1AiGenerate } from '../composables/useF1AiGenerate'
import { useAdjudicationBringIn } from '../composables/useAdjudicationBringIn'
import { useAuditContext } from '@/composables/useAuditContext'
import type { useF1CrossSheet } from '../composables/useF1CrossSheet'
import type { ChecklistResponse } from '../composables/useF1FormData'

// @ts-ignore - GtIndexChip may not have type declarations
import GtIndexChip from '../GtIndexChip.vue'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import F1SheetAttachments from './F1SheetAttachments.vue'
import F1FourTableSourcePanel from './F1FourTableSourcePanel.vue'
import type { F1NaturePrefill } from '../composables/useF1Adjudication'
import type { AgingSegment } from '@/composables/useAgingConfig'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  crossSheet: ReturnType<typeof useF1CrossSheet>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  /** 后端 render 提供的 1123 试算数（只读回退 seed） */
  tbAmountSeed?: number
  /** 科目余额表叶子合计（与 tbAmountSeed 并列，供溯源面板显示两口径差异） */
  tbLeafAmount?: number
  /** 四表库「按性质分类」未审数预填（render adjudication_prefill.nature） */
  naturePrefill?: F1NaturePrefill
  /** render 下发的取数溯源 */
  tbSourceCodes?: unknown
  tbCrossCycleCodes?: unknown
  /** F1 账龄口径单一真源（主入口注入，含表级枚举覆盖） */
  agingSegments?: AgingSegment[]
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>
const wpIdRef = toRef(props, 'wpId') as Ref<string>

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const {
  sections,
  trialBalanceAmount,
  trialBalanceDiff,
  crossValidationWarning,
  adjustmentReconcile,
  auditNotes,
  hasNaturePrefill,
  pullNatureFromTB,
  updateCell,
  publishAdjudicated,
} = useF1Adjudication({
  allResponses: allResponsesRef,
  wpId: wpIdRef,
  projectId: toRef(props, 'projectId') as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  crossSheet: props.crossSheet,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
  tbAmountSeed: computed(() => props.tbAmountSeed ?? 0) as unknown as Ref<number>,
  naturePrefill: computed(() => props.naturePrefill ?? {}) as unknown as Ref<F1NaturePrefill>,
  agingSegments: computed(() => props.agingSegments ?? []) as unknown as Ref<AgingSegment[]>,
})

const pullingFromTb = ref(false)

/**
 * 「从四表库带入未审数」：把 render 下发的性质预填持久化为未审数。
 * 只覆盖预填中出现的性质桶，不清零未出现的桶；四表无数时给中文提示。
 */
async function onPullNatureFromTB() {
  if (props.isReadonly) return
  if (!hasNaturePrefill.value) {
    ElMessage.info('四表库暂无预付款项明细科目数据（需先导入科目余额表并完成科目映射）')
    return
  }
  pullingFromTb.value = true
  try {
    const applied = pullNatureFromTB()
    if (applied > 0) {
      ElMessage.success(`已从四表库带入 ${applied} 个性质分类的未审数（期初/期末）`)
    }
  } finally {
    pullingFromTb.value = false
  }
}

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF1AiGenerate(wpIdRef)

// ─── 从集中登记带入调整（1123 预付账款，资产借方；带入账龄主维度的期末 AJE/RJE） ──────
const bringInRows = computed(() => {
  const aging = sections.value[1]
  if (!aging) return []
  return aging.rows.map((r) => ({ rowKey: r.rowKey, name: r.label, aje: r.currentAje, rje: r.currentRje }))
})
const {
  adjPull,
  visible: bringInVisible,
  rowOptions: bringInRowOptions,
  open: openBringInAdjustment,
  apply: onBringInApply,
} = useAdjudicationBringIn({
  projectId: toRef(props, 'projectId') as any,
  year: useAuditContext().year as any,
  subjectPrefix: '1123',
  direction: 'debit',
  subjectCode: '1123',
  wpCode: 'F1',
  subjectLabel: '预付账款(1123)',
  rows: bringInRows,
  updateCell: (rowKey: string, field: any, value: number) =>
    updateCell(rowKey, field === 'rje' ? 'currentRje' : 'currentAje', value),
  totalAudited: () => sections.value[1]?.subtotalRow.currentAudited ?? 0,
})

// ─── Formatting helpers ─────────────────────────────────────────────────────

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function fmtRate(rate: number | '' | 'N/A'): string {
  if (rate === '' || rate === 'N/A') return String(rate)
  return `${(rate * 100).toFixed(1)}%`
}

function isRateExceeding(rate: number | '' | 'N/A'): boolean {
  return isChangeRateExceeding(rate, 0.3)
}

function cellClass(row: any): Record<string, boolean> {
  return {
    'cross-sheet-cell': row.isFromCrossSheet,
    'subtotal-row': row.rowKey === 'subtotal',
  }
}

function onCellContextMenu(row: any, _col: any, _cell: any, event: MouseEvent) {
  event.preventDefault()
  openReviewDialog?.(`F1-adj-${row.rowKey}`)
}

function openReview() {
  openReviewDialog?.('F1-adj-conclusion')
}

function confirmAdjudication() {
  publishAdjudicated()
  ElMessage.success('已确认审定并发布（回写试算 1123）')
}

async function generateChangeAnalysis() {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'adj-change-analysis',
    auditNotes.value.changeAnalysis,
    { sheet: 'F1-1', trialBalanceDiff: trialBalanceDiff.value },
    'AI 生成 · F1-1 变动分析',
  )
  if (text) auditNotes.value.changeAnalysis = text
}

async function generateConclusion() {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'adj-conclusion',
    auditNotes.value.conclusion,
    { sheet: 'F1-1', trialBalanceDiff: trialBalanceDiff.value },
    'AI 生成 · F1-1 审计结论',
  )
  if (text) auditNotes.value.conclusion = text
}
</script>

<style scoped>
.f1-adjudication { padding: 16px; }
.f1-adjudication :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f1-adjudication :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }

/* 编制提示 */
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }

/* 工具栏 */
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

.adj-section { margin-bottom: 24px; }
.section-title { font-size: 14px; font-weight: 600; margin-bottom: 8px; color: #303133; }
.subtotal-label { font-weight: 700; }
.auto-calc { color: #909399; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.cross-sheet-cell { background: #ecf5ff; padding: 2px 6px; border-radius: 2px; }
.subtotal-row { font-weight: 700; }
.rate-exceed { color: #f56c6c; font-weight: 600; }

/* 核对行 */
.tb-check-row { display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: #f5f7fa; border-radius: 4px; margin: 12px 0; font-size: var(--wp-font-size, 13px); }
.tb-label { color: #909399; }

/* 审计意见卡片 */
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-chips { display: flex; gap: 6px; }
.opinion-section { margin-bottom: 16px; }
.opinion-section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.opinion-section-label { font-size: 14px; font-weight: 500; color: #303133; }
.opinion-actions { display: flex; gap: 6px; align-items: center; }
.cas14-hint { margin-top: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 0; }
.cas14-hint summary { padding: 8px 12px; cursor: pointer; font-size: var(--wp-font-size, 13px); color: #409eff; }
.cas14-hint .hint-content { padding: 8px 12px 12px; font-size: 12px; color: #606266; line-height: 1.6; }
</style>
