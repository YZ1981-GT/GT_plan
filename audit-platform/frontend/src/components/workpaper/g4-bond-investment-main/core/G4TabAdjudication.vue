<template>
  <div class="g4-adjudication" data-testid="g4-adjudication">
    <div class="section-head">
      <h3 class="sheet-title">G4-1 债权投资审定表</h3>
      <div class="head-actions tab-toolbar">
        <el-tooltip :content="fourTableHint" placement="top">
          <el-button
            size="small"
            :disabled="isReadonly || !hasFourTablePrefill"
            :loading="seeding"
            @click="onPullFromFourTable"
          >
            从四表库带入未审数
          </el-button>
        </el-tooltip>
        <el-button size="small" type="primary" plain :loading="adjPull.loading.value" @click="openBringInAdjustment">
          <el-icon><Download /></el-icon>带入调整
        </el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:G4-2" :context-project-id="props.projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G4-3" :context-project-id="props.projectId" /></span>
        <el-button size="small" @click="openReviewDialog('G4-1-adjudication')">💬复核</el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计目标：确认债权投资期末余额真实、准确、完整；审定数与试算平衡表勾稽一致。列结构对齐模板：期初/期末 ×（未审数 | 账项调整 | 审定数）。"
      style="margin-bottom: 12px"
    />

    <el-alert
      v-if="adj.lastWritebackNet.value !== 0"
      type="success"
      :closable="false"
      class="writeback-alert"
      :title="`已自 G4-3 回写期末账项调整 ${fmt(adj.lastWritebackNet.value)}（默认行：原值·按组合计提坏账准备）`"
      style="margin-bottom: 12px"
    />

    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>行结构对齐 Excel：一、原值 → 二、减值准备 → 三、净值；标签为「单项/按组合计提坏账准备」。</li>
        <li>审定＝未审＋账项调整（模板不分列 AJE/RJE）；|变动率|&gt;30% 时原因分析必填。</li>
        <li>净值叶子＝对应原值审定−减值审定；各层「××小计」＝小计−一年内到期的部分。</li>
        <li>G4-3「保存&amp;回写」后，1501/1502 净调整写入原值·按组合计提坏账准备行。</li>
        <li>差异数＝债权投资净值合计期末审定−试算平衡表数，应为 0。</li>
        <li>「带入调整」：可从集中登记按科目 1501 拉取调整分录，逐笔分配到各原值/减值明细行的期末账项调整，带入后审定数自动更新并联动附注。</li>
      </ul>
    </details>

    <!-- 四表库取数溯源（口径：期末余额） -->

    <WpFourTableSourcePanel

      :source-codes="tbSourceCodes"

      gross-label="债权投资"

      provision-label="债权投资减值准备"

      fallback-row-code="BS-021"

    />


    <el-table
      :data="adj.rows.value"
      border
      size="small"
      :row-class-name="rowClassName"
      :max-height="560"
      style="width: 100%"
    >
      <el-table-column label="项目" min-width="220" fixed>
        <template #default="{ row }">
          <span
            :style="{ paddingLeft: `${(row.indent || 0) * 14}px` }"
            :class="{ 'label-strong': row.kind !== 'leaf' }"
          >{{ row.label }}</span>
        </template>
      </el-table-column>

      <el-table-column label="期初数" align="center">
        <el-table-column label="未审数" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly && row.kind !== 'footer'"
              :model-value="row.openingUnadjusted"
              size="small"
              :controls="false"
              style="width: 100%"
              @update:model-value="(v: number) => adj.updateCell(row.rowKey, 'openingUnadjusted', v ?? 0)"
            />
            <span v-else :class="{ 'formula-cell': row.kind !== 'section_header' }">{{ fmt(row.openingUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账项调整" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly && row.kind !== 'footer'"
              :model-value="row.openingAdjustment"
              size="small"
              :controls="false"
              style="width: 100%"
              @update:model-value="(v: number) => adj.updateCell(row.rowKey, 'openingAdjustment', v ?? 0)"
            />
            <span v-else>{{ fmt(row.openingAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="期初审定 = 未审数 + 账项调整">{{ fmt(row.openingAudited) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="期末数" align="center">
        <el-table-column label="未审数" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly"
              :model-value="row.closingUnadjusted"
              size="small"
              :controls="false"
              style="width: 100%"
              @update:model-value="(v: number) => adj.updateCell(row.rowKey, 'closingUnadjusted', v ?? 0)"
            />
            <span v-else class="formula-cell">{{ fmt(row.closingUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账项调整" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly && row.kind !== 'footer'"
              :model-value="row.closingAdjustment"
              size="small"
              :controls="false"
              style="width: 100%"
              @update:model-value="(v: number) => adj.updateCell(row.rowKey, 'closingAdjustment', v ?? 0)"
            />
            <span v-else>{{ fmt(row.closingAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="120" align="right">
          <template #default="{ row }">
            <span
              class="formula-cell"
              :class="{ 'diff-red': row.rowKey === 'footer-variance' && adj.hasVarianceHighlight.value }"
              title="期末审定 = 未审数 + 账项调整"
            >{{ fmt(row.closingAudited) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="本期与上期比较" align="center">
        <el-table-column label="变动额" width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmt(row.changeAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" width="90" align="right">
          <template #default="{ row }">
            <span :class="{ 'rate-orange': row.changeRateHighlight }" class="formula-cell">
              {{ fmtRate(row.changeRate) }}
            </span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="原因分析" min-width="140">
        <template #default="{ row }">
          <el-input
            v-if="row.editable && !isReadonly && row.kind === 'leaf'"
            :model-value="row.reasonAnalysis"
            size="small"
            :class="{ 'reason-required': row.reasonRequired && !row.reasonAnalysis }"
            :placeholder="row.reasonRequired ? '变动率>30%，必填' : ''"
            @change="(v: string) => adj.updateCell(row.rowKey, 'reasonAnalysis', v)"
          />
          <span v-else>{{ row.reasonAnalysis || '' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <G4AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      :note="adj.auditNote.value"
      :conclusion="adj.auditConclusion.value"
      @update:note="(v: string) => { adj.auditNote.value = v }"
      @update:conclusion="(v: string) => { adj.auditConclusion.value = v }"
      note-ai-section="adjudication-note"
      conclusion-ai-section="adjudication-conclusion"
      :related-context="{
        试算表数: adj.trialBalanceAmount.value,
        差异: adj.variance.value,
      }"
      note-placeholder="对债权投资审定表的审计说明..."
      note-hint="覆盖期初/期末审定、净值勾稽及调整事项说明。"
      conclusion-placeholder="审计结论..."
      conclusion-hint="评价科目 1501 审定结果。"
    />

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="1501 债权投资"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * G4TabAdjudication.vue — 对齐 Excel《审定表G4-1》列/行结构（参照 G1-1）
 */
import { ref, computed, toRef, inject, onMounted, watch } from 'vue'
import { Download } from '@element-plus/icons-vue'
import { useG4MainAdjudication } from '../../composables/useG4MainAdjudication'
import type { G4AdjudicationRow } from '../../composables/useG4MainAdjudication'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import { useAuditContext } from '@/composables/useAuditContext'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import {
  G4_SEED_SPEC,
  buildGSeedCells,
  normalizeGAdjPrefill,
} from '../../composables/gCycleAdjudicationSeed'
import {
  describeAdjPrefillConflicts,
  describeAdjPrefillPlan,
  planAdjudicationPrefill,
  planHasWork,
  resolveAdjPrefillWrites,
} from '../../composables/shared/adjudicationPrefillPlan'
import { ElMessage, ElMessageBox } from 'element-plus'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import G4AuditTextCards from '../G4AuditTextCards.vue'
import WpFourTableSourcePanel from '../../shared/WpFourTableSourcePanel.vue'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses?: Map<string, ChecklistResponse>
}>()


/**
 * 四表库取数溯源（消费 render 下发的 `tb_source_codes`，消除 dead output）。
 *
 * 科目由后端按**科目名**逐项目解析（`four_table/g_cycle_specs.G4_SPEC`），
 * 取数口径 = 期末余额。前端单一真源见 `composables/gCycleAccountScope.ts`。
 */
const tbSourceCodes = computed(() => props.htmlData?.tb_source_codes ?? null)
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const allResponses = ref<Map<string, ChecklistResponse>>(new Map())

watch(
  () => props.allResponses,
  (source) => {
    if (!source) return
    allResponses.value = source
  },
  { immediate: true, deep: true },
)

function hydrateFromHtmlData(): void {
  if (props.allResponses && props.allResponses.size > 0) return
  if (!props.htmlData) return
  const data = props.htmlData
  if (data.checklist_responses && typeof data.checklist_responses === 'object') {
    for (const [key, val] of Object.entries(data.checklist_responses)) {
      if (val && typeof val === 'object') {
        allResponses.value.set(key, val as ChecklistResponse)
      } else {
        allResponses.value.set(key, { item_id: key, conclusion: null, remark: String(val ?? '') })
      }
    }
  }
  if (data.responses_snapshot && typeof data.responses_snapshot === 'object') {
    for (const [key, val] of Object.entries(data.responses_snapshot)) {
      if (val && typeof val === 'object') {
        allResponses.value.set(key, val as ChecklistResponse)
      }
    }
  }
  if (Array.isArray(data.responses)) {
    for (const item of data.responses) {
      if (item?.item_id) allResponses.value.set(item.item_id, item)
    }
  }
}

const adj = useG4MainAdjudication({
  wpId: toRef(props, 'wpId') as any,
  projectId: toRef(props, 'projectId') as any,
  allResponses,
  isReadonly: toRef(props, 'isReadonly') as any,
})

// ─── 从集中登记带入调整（1501 债权投资，资产借方；带入期末账项调整，单列合并 AJE/RJE） ───
const bringInRows = computed(() =>
  adj.rows.value
    .filter((r) => r.editable && r.kind === 'leaf')
    .map((r) => ({ rowKey: r.rowKey, name: r.label, aje: r.closingAdjustment, rje: r.closingAdjustment })),
)
const {
  adjPull,
  visible: bringInVisible,
  rowOptions: bringInRowOptions,
  open: openBringInAdjustment,
  apply: onBringInApply,
} = useAdjudicationBringIn({
  projectId: toRef(props, 'projectId') as any,
  year: useAuditContext().year as any,
  subjectPrefix: '1501',
  direction: 'debit',
  subjectCode: '1501',
  wpCode: 'G4',
  subjectLabel: '债权投资(1501)',
  rows: bringInRows,
  updateCell: (rowKey: string, _field: any, value: number) =>
    adj.updateCell(rowKey, 'closingAdjustment', value),
  totalAudited: () => adj.amortizedCostRow.value?.closingAudited ?? 0,
})

onMounted(() => {
  hydrateFromHtmlData()
  adj.fetchTrialBalance()
})

// ─── 从四表库带入未审数（1504 期初+期末，按减值方法默认落「按组合计提」行）──────
//
// G4 的备抵科目 1505 叶子通过 slot='provision' 进入减值准备段行。
// 「单项计提 / 按组合计提」是减值方法的会计判断，四表无信息 → 默认 + 明示。

const seeding = ref(false)

const fourTablePrefill = computed(() =>
  normalizeGAdjPrefill(props.htmlData?.adjudication_prefill),
)

const seedResult = computed(() => buildGSeedCells(fourTablePrefill.value, {
  ...G4_SEED_SPEC,
  labelOf: (k) => adj.rows.value.find((r) => r.rowKey === k)?.label ?? k,
}))

const hasFourTablePrefill = computed(() => seedResult.value.cells.length > 0)

const fourTableHint = computed(() =>
  hasFourTablePrefill.value
    ? '把四表库（tb_balance 债权投资/减值准备叶子科目余额）带入对应行的期初/期末未审数；已录入的格不覆盖'
    : '四表库暂无债权投资科目数据（需先导入余额表）',
)

function readCurrentCell(cell: { rowKey: string; field: string }): number | null {
  const row = adj.rows.value.find((r) => r.rowKey === cell.rowKey)
  if (!row) return null
  const v = (row as unknown as Record<string, unknown>)[cell.field]
  return v == null || v === 0 ? null : Number(v)
}

async function onPullFromFourTable(): Promise<void> {
  if (props.isReadonly) return
  const { cells, unclassified, absentSlots } = seedResult.value
  if (!cells.length) {
    ElMessage.info('四表库暂无债权投资科目数据可带入')
    return
  }
  const plan = planAdjudicationPrefill(cells, readCurrentCell, { unclassified, absentSlots })
  if (!planHasWork(plan)) {
    ElMessage.info(describeAdjPrefillPlan(plan))
    return
  }

  let mode: 'fill-blank' | 'overwrite' = 'fill-blank'
  if (plan.conflicts.length) {
    try {
      const action = await ElMessageBox.confirm(
        `以下 ${plan.conflicts.length} 格已有录入且与四表不一致：\n`
        + `${describeAdjPrefillConflicts(plan)}\n\n`
        + '「覆盖」以四表数据替换；「仅补空值」保留已录入数据、只填空白格。',
        '从四表库带入未审数',
        {
          confirmButtonText: '覆盖',
          cancelButtonText: '仅补空值',
          distinguishCancelAndClose: true,
          type: 'warning',
        },
      )
      if (action === 'confirm') mode = 'overwrite'
    } catch (e) {
      if (e === 'close') return
      mode = 'fill-blank'
    }
  }

  seeding.value = true
  try {
    for (const w of resolveAdjPrefillWrites(plan, mode)) {
      adj.updateCell(w.rowKey, w.field as 'openingUnadjusted' | 'closingUnadjusted', w.amount)
    }
    ElMessage.success(describeAdjPrefillPlan(plan))
  } finally {
    seeding.value = false
  }
}

function rowClassName({ row }: { row: G4AdjudicationRow }): string {
  if (row.kind === 'section_header') return 'row-section'
  if (row.kind === 'subtotal' || row.kind === 'section_net') return 'row-subtotal'
  if (row.kind === 'footer') return 'row-footer'
  return ''
}

function fmt(v: number | null | undefined): string {
  if (v == null) return ''
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function fmtRate(v: number | null | undefined): string {
  if (v == null) return '-'
  return (v * 100).toFixed(2) + '%'
}

const isReadonly = computed(() => props.isReadonly)
const wpId = computed(() => props.wpId)
</script>

<style scoped>
.g4-adjudication { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.chip-wrap { display: inline-flex; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.label-strong { font-weight: 700; }
.rate-orange { color: #e6a23c; font-weight: 600; }
.diff-red { color: #f56c6c; font-weight: 700; }
:deep(.row-section) { background: #ecf5ff !important; }
:deep(.row-subtotal) { background: #f5f7fa !important; font-weight: 700; }
:deep(.row-footer) { background: #fafafa !important; }
:deep(.reason-required .el-input__wrapper) { box-shadow: 0 0 0 1px #e6a23c inset; }
.prep-hint { margin: 0 0 12px; font-size: 12px; color: #606266; }
.prep-hint summary { cursor: pointer; font-weight: 500; color: #303133; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
.writeback-alert { margin-bottom: 12px; }
</style>
