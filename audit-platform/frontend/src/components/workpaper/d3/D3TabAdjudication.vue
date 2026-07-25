<template>
<div class="d3-adjudication">
  <div class="import-export-bar">
    <el-button size="small" type="primary" plain :loading="adjPull.loading.value" @click="openBringInAdjustment">
      <el-icon><Download /></el-icon>带入调整
    </el-button>
    <el-button-group size="small">
      <el-button @click="onExportTemplate">导出模板</el-button>
      <el-button @click="onExportData">导出数据</el-button>
      <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile">
        <el-button :disabled="isReadonly">导入数据</el-button>
      </el-upload>
    </el-button-group>
  </div>
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

      <!-- CAS14 合同负债(2205)分类适当性勾稽 -->
      <el-alert
        v-if="contractLiabilityWarning"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
      >
        <template #title>
          <span>{{ contractLiabilityWarning }}</span>
          <GtIndexChip value="wp:D7" context="收入范围预收应重分类至合同负债(2205)底稿 D7" />
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
              <span :class="cellClass(row)" :title="row.isFromCrossSheet ? '来源：D3-2明细表聚合' : ''">
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
              <span :class="cellClass(row)" :title="row.isFromCrossSheet ? '来源：D3-2明细表聚合' : ''">
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
        <h4 class="section-header-row">
          审计说明
          <GtReviewTrigger section-id="D3-adj-header" />
        </h4>
        <!-- (1) 超1年原因 -->
        <div class="note-block">
          <div class="note-label">
            (1) 账龄超过1年的预收账款未结转原因
            <GtIndexChip target="D3-5" label="→D3-5长期检查" />
            <el-button
              size="small"
              :disabled="isReadonly || !aiAvailable || aiLoading"
              :loading="aiLoading"
              @click="genAgingReason"
            >🤖AI</el-button>
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
            <el-button
              size="small"
              :disabled="isReadonly || !aiAvailable || aiLoading"
              :loading="aiLoading"
              @click="genChangeAnalysis"
            >🤖AI</el-button>
          </div>
          <el-input
            v-model="auditNotes.changeAnalysis"
            type="textarea"
            :rows="3"
            :disabled="isReadonly"
            placeholder="分析预收账款重大变动原因..."
          />
        </div>
        <!-- (3) CAS14提示 -->
        <details class="cas14-hint">
          <summary>📋 CAS14收入准则提示</summary>
          <div class="hint-content">
            根据CAS14《企业会计准则第14号——收入》，预收账款中包含的"合同不成立时已收取的对价"应区分于合同负债。
            需评估是否满足收入确认条件：(a)合同各方已批准并承诺履行各自义务；(b)合同明确了各方权利；
            (c)合同有明确的付款条款；(d)合同具有商业实质；(e)对价很可能收回。
          </div>
        </details>
      </div>

      <!-- 审计结论 -->
      <div class="audit-conclusion-section">
        <h4 class="section-header-row">
          审计结论
          <GtReviewTrigger section-id="D3-adj-conclusion" />
        </h4>
        <el-input
          v-model="auditNotes.conclusion"
          type="textarea"
          :rows="3"
          :disabled="isReadonly"
          placeholder="对预收账款审定结果的总结性结论..."
        />
        <div class="conclusion-actions">
          <el-button
            size="small"
            :disabled="isReadonly || !aiAvailable || aiLoading"
            :loading="aiLoading"
            @click="genConclusion"
          >🤖AI生成结论</el-button>
        </div>
      </div>
    </template>
  </el-skeleton>

  <AdjudicationBringInDialog
    v-model="bringInVisible"
    :matches="adjPull.matches.value"
    :row-options="bringInRowOptions"
    subject-label="2203 预收账款"
    :loading="adjPull.loading.value"
    @apply="onBringInApply"
  />
</div>
</template>

<script setup lang="ts">
/**
 * D3TabAdjudication.vue — D3-1 审定表
 * 双区块(按性质+按账龄) + 变动率高亮 + 跨sheet取数 + 审计说明/结论
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { Download } from '@element-plus/icons-vue'
import { isChangeRateExceeding } from '../composables/useD3FormulaEngine'
import { useD3Adjudication } from '../composables/useD3Adjudication'
import { useD3AiGenerate } from '../composables/useD3AiGenerate'
import { useD3TabImportExport } from '../composables/useD3TabImportExport'
import { useAuditContext } from '@/composables/useAuditContext'
import { useAdjudicationBringIn } from '../composables/useAdjudicationBringIn'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import type { useD3CrossSheet } from '../composables/useD3CrossSheet'
import type { ChecklistResponse } from '../composables/useD3FormData'

// @ts-ignore - GtIndexChip may not have type declarations
import GtIndexChip from '../GtIndexChip.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  crossSheet: ReturnType<typeof useD3CrossSheet>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

// 父级经模板传入的是解包后的普通值（非 ref），此处重新包成 ref 供 composable 使用
const allResponsesRef = toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>
const wpIdRef = toRef(props, 'wpId') as Ref<string>
const projectIdRef = toRef(props, 'projectId') as Ref<string>

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const {
  sections,
  trialBalanceAmount,
  trialBalanceDiff,
  crossValidationWarning,
  contractLiabilityWarning,
  auditNotes,
  updateCell,
} = useD3Adjudication({
  allResponses: allResponsesRef,
  wpId: wpIdRef,
  projectId: projectIdRef,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  crossSheet: props.crossSheet,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})

const { generateAndConfirm, aiAvailable, loading: aiLoading } = useD3AiGenerate(wpIdRef)

const { onExportTemplate, onExportData, onImportFile } = useD3TabImportExport(wpIdRef, 'D3-1')

// ─── 从集中登记带入调整（2203 预收账款，负债贷方；双维度→带入性质主维度，带入期末 AJE/RJE） ─
// D3 为双维度（性质 AND 账龄）表示同一 2203 余额；带入至性质主维度（与手工录入一致），
// 若触发"性质合计≠账龄合计"提示，审计师需在账龄维度同步反映（既有交叉校验保障）。
const bringInRows = computed(() =>
  (sections.value[0]?.rows ?? []).map((r) => ({
    rowKey: r.rowKey,
    name: r.label,
    aje: r.currentAje,
    rje: r.currentRje,
  })),
)
const {
  adjPull,
  visible: bringInVisible,
  rowOptions: bringInRowOptions,
  open: openBringInAdjustment,
  apply: onBringInApply,
} = useAdjudicationBringIn({
  projectId: projectIdRef as any,
  year: useAuditContext().year as any,
  subjectPrefix: '2203',
  direction: 'credit',
  subjectCode: '2203',
  wpCode: 'D3',
  subjectLabel: '预收账款(2203)',
  rows: bringInRows,
  updateCell: (rowKey: string, field: any, value: number) =>
    updateCell(rowKey, field === 'rje' ? 'currentRje' : 'currentAje', value),
  totalAudited: () =>
    sections.value[1]?.subtotalRow?.currentAudited ?? sections.value[0]?.subtotalRow?.currentAudited ?? 0,
})

async function genAgingReason() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('adj-aging-reason', auditNotes.value.agingReason, {
    task: '账龄超过1年的预收账款未结转原因说明',
    crossValidationWarning: crossValidationWarning.value || '',
  }, 'AI · 账龄超1年原因')
  if (text) auditNotes.value.agingReason = text
}

async function genChangeAnalysis() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('adj-change-analysis', auditNotes.value.changeAnalysis, {
    task: '预收账款重大变动分析',
    trialBalanceDiff: trialBalanceDiff.value,
    crossValidationWarning: crossValidationWarning.value || '',
  }, 'AI · 变动分析')
  if (text) auditNotes.value.changeAnalysis = text
}

async function genConclusion() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('adj-conclusion', auditNotes.value.conclusion, {
    task: '预收账款审定审计结论',
    trialBalanceAmount: trialBalanceAmount.value,
    trialBalanceDiff: trialBalanceDiff.value,
  }, 'AI · 审计结论')
  if (text) auditNotes.value.conclusion = text
}

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
  openReviewDialog(`D3-adj-${row.rowKey}`)
}

</script>

<style scoped>
.d3-adjudication { padding: 16px; }
.import-export-bar { display: flex; justify-content: flex-end; margin-bottom: 12px; }
.adj-section { margin-bottom: 24px; }
.section-title { font-size: 14px; font-weight: 600; margin-bottom: 8px; color: #303133; }
.subtotal-label { font-weight: 700; }
.auto-calc { background: #f5f7fa; padding: 2px 6px; border-radius: 2px; }
.cross-sheet-cell { background: #ecf5ff; padding: 2px 6px; border-radius: 2px; }
.subtotal-row { font-weight: 700; }
.rate-exceed { color: #f56c6c; font-weight: 600; }
.diff-red { color: #f56c6c; font-weight: 600; }
.tb-diff-row { display: flex; gap: 24px; padding: 8px 12px; background: #fafafa; border-radius: 4px; margin: 12px 0; font-size: var(--wp-font-size, 13px); }
.audit-notes-section, .audit-conclusion-section { margin-top: 20px; }
.audit-notes-section h4, .audit-conclusion-section h4 { font-size: 14px; margin-bottom: 12px; }
.section-header-row { display: flex; align-items: center; gap: 8px; }
.note-block { margin-bottom: 16px; }
.note-label { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.conclusion-actions { display: flex; gap: 8px; margin-top: 8px; }
.cas14-hint { margin-top: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 0; }
.cas14-hint summary { padding: 8px 12px; cursor: pointer; font-size: var(--wp-font-size, 13px); color: #409eff; }
.cas14-hint .hint-content { padding: 8px 12px 12px; font-size: 12px; color: #606266; line-height: 1.6; }
</style>
