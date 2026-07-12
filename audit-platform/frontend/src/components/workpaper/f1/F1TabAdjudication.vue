<template>
<div class="f1-adjudication">
  <el-skeleton :loading="!sections.length" :rows="8" animated>
    <template #default>
      <!-- 编制提示 -->
      <details class="guidance-details">
        <summary>📋 编制提示</summary>
        <div class="guidance-content">
          <p>1. 本表汇总预付账款（科目1123）审定情况，按款项性质与账龄两个区块分别归集。</p>
          <p>2. 浅蓝底纹单元格由 F1-2 明细表聚合取数，灰色底纹列为审定数（期初/期末审定）自动计算列。</p>
          <p>3. 账龄超过1年的预付账款须说明未结转原因并与 F1-5 长期检查勾稽一致。</p>
          <p>4. 审定合计应与试算平衡表核对一致，差异须查明并通过 F1-3 调整分录处理。</p>
        </div>
      </details>

      <!-- 审计目标 -->
      <el-alert
        type="info"
        :closable="false"
        title="审计目标：确认预付账款期末余额的准确性与列报恰当性，核实按性质/账龄分类的合理性，并与试算平衡表核对一致。"
        class="objective-alert"
      />

      <!-- 工具栏 -->
      <div class="tab-toolbar">
        <div class="toolbar-left"></div>
        <div class="toolbar-right">
          <span class="chip-wrap"><GtIndexChip value="wp:F1-2" :context-project-id="projectId" /></span>
          <span class="chip-wrap"><GtIndexChip value="wp:F1-5" :context-project-id="projectId" /></span>
        </div>
      </div>

      <!-- 交叉验证警告 -->
      <el-alert
        v-if="crossValidationWarning"
        type="warning"
        :title="crossValidationWarning"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
      />

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
              <el-button size="small" @click="openReview">💬</el-button>
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

        <!-- CAS14 方法论提示 -->
        <details class="cas14-hint">
          <summary>📋 CAS14收入准则提示</summary>
          <div class="hint-content">
            根据CAS14《企业会计准则第14号——收入》，预付账款中包含的"合同不成立时已收取的对价"应区分于合同负债。
            需评估是否满足收入确认条件：(a)合同各方已批准并承诺履行各自义务；(b)合同明确了各方权利；
            (c)合同有明确的付款条款；(d)合同具有商业实质；(e)对价很可能收回。
          </div>
        </details>
      </el-card>
    </template>
  </el-skeleton>
</div>
</template>

<script setup lang="ts">
/**
 * F1TabAdjudication.vue — F1-1 审定表
 * 双区块(按性质+按账龄) + 变动率高亮 + 跨sheet取数 + 审计说明/结论
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { isChangeRateExceeding } from '../composables/useF1FormulaEngine'
import { useF1Adjudication } from '../composables/useF1Adjudication'
import type { useF1CrossSheet } from '../composables/useF1CrossSheet'
import type { ChecklistResponse } from '../composables/useF1FormData'

// @ts-ignore - GtIndexChip may not have type declarations
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  crossSheet: ReturnType<typeof useF1CrossSheet>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const {
  sections,
  trialBalanceAmount,
  trialBalanceDiff,
  crossValidationWarning,
  auditNotes,
  updateCell,
} = useF1Adjudication({
  allResponses: allResponsesRef,
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  crossSheet: props.crossSheet,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
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
  openReviewDialog(`F1-adj-${row.rowKey}`)
}

function openReview() {
  openReviewDialog('F1-adj-conclusion')
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
