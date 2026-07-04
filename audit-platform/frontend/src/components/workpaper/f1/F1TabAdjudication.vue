<template>
<div class="f1-adjudication">
  <el-skeleton :loading="!sections.length" :rows="8" animated>
    <template #default>
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
          <el-table-column label="期初审定" width="110">
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
          <el-table-column label="期末审定" width="110">
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

      <!-- 试算平衡表差异 -->
      <div class="tb-diff-row">
        <span>试算平衡表数：{{ fmtAmount(trialBalanceAmount) }}</span>
        <span :class="{ 'diff-red': trialBalanceDiff !== 0 }">
          差异：{{ fmtAmount(trialBalanceDiff) }}
          <template v-if="trialBalanceDiff === 0">✓</template>
          <template v-else>✗</template>
        </span>
      </div>

      <!-- 审计说明区域 -->
      <div class="audit-notes-section">
        <h4>审计说明</h4>
        <!-- (1) 超1年原因 -->
        <div class="note-block">
          <div class="note-label">
            (1) 账龄超过1年的预付账款未结转原因
            <GtIndexChip target="F1-5" label="→F1-5长期检查" />
          </div>
          <el-input
            v-model="auditNotes.agingReason"
            type="textarea"
            :rows="3"
            :disabled="isReadonly"
            placeholder="说明超过1年未结转的原因..."
          />
        </div>
        <!-- (2) 变动分析 -->
        <div class="note-block">
          <div class="note-label">
            (2) 重大变动分析
            <el-button size="small" :disabled="true" title="AI功能暂未开放">🤖AI</el-button>
          </div>
          <el-input
            v-model="auditNotes.changeAnalysis"
            type="textarea"
            :rows="3"
            :disabled="isReadonly"
            placeholder="分析预付账款重大变动原因..."
          />
        </div>
        <!-- (3) CAS14提示 -->
        <details class="cas14-hint">
          <summary>📋 CAS14收入准则提示</summary>
          <div class="hint-content">
            根据CAS14《企业会计准则第14号——收入》，预付账款中包含的"合同不成立时已收取的对价"应区分于合同负债。
            需评估是否满足收入确认条件：(a)合同各方已批准并承诺履行各自义务；(b)合同明确了各方权利；
            (c)合同有明确的付款条款；(d)合同具有商业实质；(e)对价很可能收回。
          </div>
        </details>
      </div>

      <!-- 审计结论 -->
      <div class="audit-conclusion-section">
        <h4>审计结论</h4>
        <el-input
          v-model="auditNotes.conclusion"
          type="textarea"
          :rows="3"
          :disabled="isReadonly"
          placeholder="对预付账款审定结果的总结性结论..."
        />
        <div class="conclusion-actions">
          <el-button size="small" :disabled="true">🤖AI生成结论</el-button>
          <el-button size="small" @click="openReview">💬 复核</el-button>
        </div>
      </div>
    </template>
  </el-skeleton>
</div>
</template>

<script setup lang="ts">
/**
 * F1TabAdjudication.vue — F1-1 审定表
 * 双区块(按性质+按账龄) + 变动率高亮 + 跨sheet取数 + 审计说明/结论
 */
import { computed, inject, type Ref } from 'vue'
import { isChangeRateExceeding } from '../composables/useF1FormulaEngine'
import { useF1Adjudication } from '../composables/useF1Adjudication'
import type { useF1CrossSheet } from '../composables/useF1CrossSheet'
import type { ChecklistResponse } from '../composables/useF1FormData'

// @ts-ignore - GtIndexChip may not have type declarations
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  isReadonly: boolean
  crossSheet: ReturnType<typeof useF1CrossSheet>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const {
  sections,
  trialBalanceAmount,
  trialBalanceDiff,
  crossValidationWarning,
  auditNotes,
  updateCell,
} = useF1Adjudication({
  allResponses: props.allResponses,
  wpId: props.wpId,
  projectId: props.projectId,
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
.adj-section { margin-bottom: 24px; }
.section-title { font-size: 14px; font-weight: 600; margin-bottom: 8px; color: #303133; }
.subtotal-label { font-weight: 700; }
.auto-calc { background: #f5f7fa; padding: 2px 6px; border-radius: 2px; }
.cross-sheet-cell { background: #ecf5ff; padding: 2px 6px; border-radius: 2px; }
.subtotal-row { font-weight: 700; }
.rate-exceed { color: #f56c6c; font-weight: 600; }
.diff-red { color: #f56c6c; font-weight: 600; }
.tb-diff-row { display: flex; gap: 24px; padding: 8px 12px; background: #fafafa; border-radius: 4px; margin: 12px 0; font-size: 13px; }
.audit-notes-section, .audit-conclusion-section { margin-top: 20px; }
.audit-notes-section h4, .audit-conclusion-section h4 { font-size: 14px; margin-bottom: 12px; }
.note-block { margin-bottom: 16px; }
.note-label { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-size: 13px; color: #606266; }
.conclusion-actions { display: flex; gap: 8px; margin-top: 8px; }
.cas14-hint { margin-top: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 0; }
.cas14-hint summary { padding: 8px 12px; cursor: pointer; font-size: 13px; color: #409eff; }
.cas14-hint .hint-content { padding: 8px 12px 12px; font-size: 12px; color: #606266; line-height: 1.6; }
</style>
