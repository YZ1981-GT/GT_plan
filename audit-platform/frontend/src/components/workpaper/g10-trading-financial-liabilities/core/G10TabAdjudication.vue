<template>
  <div class="g10-adjudication" data-testid="g10-adjudication">
    <div class="g10-toolbar tab-toolbar">
      <h3 class="g10-title">G10-1 交易性金融负债审定表</h3>
      <div class="g10-actions">
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
        <GtIndexChip value="wp:G10-1" />
        <el-tag size="small" type="info">共 {{ adjRowCount }} 行</el-tag>
        <GtReviewTrigger section-id="G10-1-adjudication" />
        <G10ImportExportDropdown
          :wp-id="wpId"
          sheet="G10-1"
          @imported="emit('imported')"
        />
        <el-button size="small" :loading="validateLoading" :disabled="isReadonly" data-testid="g10-validate-btn" @click="runValidate">校验公式</el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="success"
          plain
          :loading="adj.procedureMarking.value"
          data-testid="g10-adj-mark-procedure"
          @click="onMarkProcedure"
        >
          {{ adj.procedureMarked.value ? '已回填 G10A（可重写）' : '回填 G10A 审定/分析' }}
        </el-button>
        <el-button size="small" :loading="adj.aiLoading.value" :disabled="isReadonly" @click="adj.generateAiAnalysis()">🤖 AI</el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：核实交易性金融负债（2101）期末余额的完整、准确与列报正确，验证(三)账面余额与试算平衡表、G10-2 明细表勾稽一致。"
    />

    <details class="guidance-details" open>
      <summary>📋 编制提示（对齐 Excel 审定表 G10-1）</summary>
      <div class="guidance-content">
        <p><b>编制思路：</b>按「初始金额 → 累计公允价值变动 → 账面余额（公允价值）」三层结构填列；未审 → AJE/RJE → 审定。</p>
        <p><b>勾稽关系：</b>各分项 (三) = (一) + (二)；试算平衡表数与 (三) 账面余额合计比对；G10-2 明细合计应与 (三) 一致。</p>
        <p><b>公式：</b>审定数 = 未审 + AJE + RJE；变动额 = 期末审定 − 期初审定；变动率 = 变动额 / |期初审定|。</p>
        <p><b>分析要求：</b>|变动率|&gt;20% 时原因分析必填；审计说明中对 |变动率|&gt;30% 的项目重点说明增减原因（对齐模板「审计说明」）。</p>
        <p><b>带入调整：</b>可从集中登记按科目 2101 拉取调整分录，逐笔分配到 (三)账面余额各行的期末账项(AJE)/重分类(RJE)调整，带入后审定数自动更新并联动附注。</p>
      </div>
    </details>

    <el-alert
      v-if="adj.hasTbMissing.value"
      type="info"
      :closable="false"
      class="reason-alert"
      data-testid="g10-adj-tb-missing"
      :title="`试算表未取到 ${accountLabel}（已试 ${aliasHint}）。若本年无此科目可忽略；有余额请检查科目映射后点「刷新TB」`"
    />

    <div
      v-else-if="adj.hasVarianceHighlight.value"
      class="tb-bar tb-warn"
      data-testid="g10-tb-bar"
    >
      试算表 {{ tbBarLabel }}: {{ fmt(adj.trialBalanceAmount.value) }}
      | 差异: {{ fmt(adj.variance.value) }}
      <el-button v-if="!isReadonly" size="small" link @click="refreshTb">刷新TB</el-button>
    </div>
    <div v-else-if="adj.tbFetchStatus.value === 'found'" class="tb-bar tb-ok" data-testid="g10-tb-bar">
      试算表 {{ tbBarLabel }}: {{ fmt(adj.trialBalanceAmount.value) }}
      | 差异: {{ fmt(adj.variance.value) }} ✓
      <el-button v-if="!isReadonly" size="small" link @click="refreshTb">刷新TB</el-button>
    </div>
    <div v-else class="tb-bar" data-testid="g10-tb-bar">
      试算表 {{ tbBarLabel }}: 待刷新
      <el-button v-if="!isReadonly" size="small" link @click="refreshTb">刷新TB</el-button>
    </div>

    <el-alert
      v-if="adj.hasMissingReasons.value"
      type="warning"
      :closable="false"
      class="reason-alert"
      data-testid="g10-adj-reason-warn"
      :title="`有 ${adj.missingReasonCount.value} 行 |变动率|>20%，请填写原因分析`"
    />

    <el-alert
      v-if="adj.hasThreePartMismatch.value"
      type="warning"
      :closable="false"
      class="reason-alert"
      data-testid="g10-adj-three-part-warn"
      :title="threePartWarnTitle"
    />

    <div v-for="group in adj.groupedRows.value" :key="group.groupKey" class="group-block">
      <div class="group-head" @click="adj.toggleGroup(group.groupKey)">
        <span class="group-toggle">{{ group.collapsed ? '▶' : '▼' }}</span>
        <strong>{{ group.groupName }}</strong>
        <span class="group-sub">期末审定 {{ fmt(group.subtotal.closingAdjusted) }} · 变动 {{ fmt(group.subtotal.changeAmount) }}</span>
      </div>
      <!-- 四表库取数溯源（口径：期末余额） -->
      <WpFourTableSourcePanel
        :source-codes="tbSourceCodes"
        gross-label="交易性金融负债"
        fallback-row-code="BS-042"
      />

      <el-table
        v-show="!group.collapsed"
        :data="[...group.rows, group.subtotal]"
        border
        size="small"
        style="font-size:13px"
        :max-height="tableMaxHeight"
        :row-class-name="({ row }) => rowClassName(row)"
      >
        <el-table-column label="项目" prop="label" min-width="200" fixed>
          <template #default="{ row }">
            <GtReviewDot v-if="!row.rowKey?.endsWith('_subtotal')" row-prefix="G10-adj" :row-key="row.rowKey" />
            <span :class="{ 'is-subtotal': row.rowKey?.endsWith('_subtotal') }">{{ row.label }}</span>
          </template>
        </el-table-column>

        <el-table-column label="期初数" align="center">
          <el-table-column label="未审数" width="88" align="right">
            <template #default="{ row }">
              <template v-if="row.rowKey?.endsWith('_subtotal')"><span class="formula-cell">{{ fmt(row.openingUnadjusted) }}</span></template>
              <WpAmountInput v-else-if="!isReadonly" :model-value="row.openingUnadjusted" size="small" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'openingUnadjusted', v ?? 0)" />
              <span v-else>{{ fmt(row.openingUnadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="AJE" width="80" align="right">
            <template #default="{ row }">
              <template v-if="row.rowKey?.endsWith('_subtotal')"><span class="formula-cell">{{ fmt(row.openingAJE) }}</span></template>
              <WpAmountInput v-else-if="!isReadonly" :model-value="row.openingAJE" size="small" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'openingAJE', v ?? 0)" />
              <span v-else>{{ fmt(row.openingAJE) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="RJE" width="80" align="right">
            <template #default="{ row }">
              <template v-if="row.rowKey?.endsWith('_subtotal')"><span class="formula-cell">{{ fmt(row.openingRJE) }}</span></template>
              <WpAmountInput v-else-if="!isReadonly" :model-value="row.openingRJE" size="small" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'openingRJE', v ?? 0)" />
              <span v-else>{{ fmt(row.openingRJE) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定数" width="92" align="right">
            <template #default="{ row }"><span class="formula-cell" title="期初审定 = 未审 + AJE + RJE">{{ fmt(row.openingAdjusted) }}</span></template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="期末数" align="center">
          <el-table-column label="未审数" width="88" align="right">
            <template #default="{ row }">
              <template v-if="row.rowKey?.endsWith('_subtotal')"><span class="formula-cell">{{ fmt(row.closingUnadjusted) }}</span></template>
              <WpAmountInput v-else-if="!isReadonly" :model-value="row.closingUnadjusted" size="small" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'closingUnadjusted', v ?? 0)" />
              <span v-else>{{ fmt(row.closingUnadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="AJE" width="80" align="right">
            <template #default="{ row }">
              <template v-if="row.rowKey?.endsWith('_subtotal')"><span class="formula-cell">{{ fmt(row.closingAJE) }}</span></template>
              <WpAmountInput v-else-if="!isReadonly" :model-value="row.closingAJE" size="small" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'closingAJE', v ?? 0)" />
              <span v-else>{{ fmt(row.closingAJE) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="RJE" width="80" align="right">
            <template #default="{ row }">
              <template v-if="row.rowKey?.endsWith('_subtotal')"><span class="formula-cell">{{ fmt(row.closingRJE) }}</span></template>
              <WpAmountInput v-else-if="!isReadonly" :model-value="row.closingRJE" size="small" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'closingRJE', v ?? 0)" />
              <span v-else>{{ fmt(row.closingRJE) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定数" width="92" align="right">
            <template #default="{ row }"><span class="formula-cell" title="期末审定 = 未审 + AJE + RJE">{{ fmt(row.closingAdjusted) }}</span></template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="本期与上期审定数比较" align="center">
          <el-table-column label="变动额" width="88" align="right">
            <template #default="{ row }"><span class="formula-cell">{{ fmt(row.changeAmount) }}</span></template>
          </el-table-column>
          <el-table-column label="变动率" width="72" align="right">
            <template #default="{ row }">
              <span :class="{ 'rate-warn': row.changeRateHighlight }">{{ fmtRate(row.changeRate) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="原因分析" min-width="110">
          <template #default="{ row }">
            <template v-if="row.rowKey?.endsWith('_subtotal')">—</template>
            <el-input v-else-if="!isReadonly" :model-value="row.reasonAnalysis" size="small"
              :class="{ 'reason-required': row.reasonRequired && !row.reasonAnalysis?.trim() }"
              placeholder="|变动率|>20%时必填"
              @update:model-value="(v: string) => adj.updateField(row.rowKey, 'reasonAnalysis', v)" />
            <span v-else>{{ row.reasonAnalysis }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引" width="72">
          <template #default="{ row }">
            <template v-if="row.rowKey?.endsWith('_subtotal')">—</template>
            <el-input v-else-if="!isReadonly" :model-value="row.indexRef" size="small"
              @update:model-value="(v: string) => adj.updateField(row.rowKey, 'indexRef', v)" />
            <GtIndexChip v-else-if="row.indexRef" :value="row.indexRef" />
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="total-row" data-testid="g10-adj-total-row">
      <strong>{{ adj.totalRow.value.label }}</strong>
      期末审定 {{ fmt(adj.totalRow.value.closingAdjusted) }}
      · 变动额 {{ fmt(adj.totalRow.value.changeAmount) }}
      · 变动率 {{ fmtRate(adj.totalRow.value.changeRate) }}
    </div>

    <el-alert
      v-if="adj.hasDetailCrossMismatch.value"
      type="warning"
      :closable="false"
      class="cross-alert"
      data-testid="g10-detail-cross-alert"
    >
      G10-1 账面余额合计 {{ fmt(adj.totalRow.value.closingAdjusted) }} 与 G10-2 明细合计
      {{ fmt(adj.detailTotalClosing.value ?? 0) }} 差异 {{ fmt(adj.detailCrossVariance.value ?? 0) }}
    </el-alert>

    <div class="fine-checks" data-testid="g10-fine-checks">
      <el-tag size="small" :type="chk01Type">G10-CHK-01 试算表勾稽</el-tag>
      <el-tag size="small" :type="adj.hasThreePartMismatch.value ? 'warning' : 'success'">G10-CHK-02 三部分勾稽</el-tag>
      <el-tag size="small" :type="adj.hasDetailCrossMismatch.value ? 'warning' : 'success'">G10-CHK-03 明细表勾稽</el-tag>
      <el-tag size="small" :type="adj.hasMissingReasons.value ? 'warning' : 'success'">G10-CHK-04 变动分析</el-tag>
    </div>

    <div class="g10-tb-row">
      <span>试算平衡表数（{{ tbBarLabel }}）：</span>
      <el-input-number v-if="!isReadonly" :model-value="adj.trialBalanceAmount.value" size="small" :controls="false"
        style="width:140px" @update:model-value="(v: number) => adj.updateTrialBalance(v ?? 0)" />
      <span v-else>{{ fmt(adj.trialBalanceAmount.value) }}</span>
      <span :class="['variance', { 'is-error': adj.hasVarianceHighlight.value }]">差异：{{ fmt(adj.variance.value) }}</span>
      <el-button size="small" type="primary" :disabled="isReadonly" @click="onPublish">发布审定数</el-button>
    </div>

    <G10AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="noteProxy"
      v-model:conclusion="conclusionProxy"
      note-ai-section="adjudication-note"
      conclusion-ai-section="adjudication-conclusion"
      note-placeholder="填写审计说明：可概述审定分析程序、重大变动原因（|变动率|>30% 重点说明）及与试算表/明细表勾稽结果。"
      note-hint="覆盖(三)账面余额审定、三部分勾稽及与 G10-2 明细表勾稽。"
      conclusion-placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在重大未调整事项或审计范围受限，不可确认。"
      :related-context="{ 试算表差异: adj.variance.value, 明细勾稽差异: adj.detailCrossVariance.value, 三部分勾稽: adj.threePartMismatches.value.length }"
    />

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="2101 交易性金融负债"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { computed, ref, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtReviewDot from '../../GtReviewDot.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import G10AuditTextCards from '../G10AuditTextCards.vue'
import G10ImportExportDropdown from '../G10ImportExportDropdown.vue'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import { useG10Adjudication } from '../../composables/useG10Adjudication'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import { useAuditContext } from '@/composables/useAuditContext'
import {
  G10_SEED_SPEC,
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
import {
  confirmNavigateToSheet,
  dispatchProcedureFocus,
} from '../../composables/g8CrossHelpers'
import {
  G10A_ADJUDICATION_PROGRAM_NOS,
  G10A_PROCEDURE_SHEET,
} from '../../composables/g10FvCrossHelpers'
import { G10_ACCOUNT_ALIASES, G10_VIRTUAL_SCROLL_THRESHOLD } from '../../composables/g10Constants'
import { g10AccountLabel } from '../../composables/g10TbResolve'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import WpFourTableSourcePanel from '../../shared/WpFourTableSourcePanel.vue'

const props = defineProps<{
  /** render 下发的本 sheet html_data（含 tb_source_codes） */
  htmlData?: Record<string, any> | null
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()


/**
 * 四表库取数溯源（消费 render 下发的 `tb_source_codes`，消除 dead output）。
 *
 * 科目由后端按**科目名**逐项目解析（`four_table/g_cycle_specs.G10_SPEC`），
 * 取数口径 = 期末余额。前端单一真源见 `composables/gCycleAccountScope.ts`。
 */
const tbSourceCodes = computed(() => props.htmlData?.tb_source_codes ?? null)
const emit = defineEmits<{ imported: [] }>()

const validateLoading = ref(false)

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

const adj = useG10Adjudication({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  allResponses: computed(() => props.allResponses),
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
})

const adjRowCount = computed(() =>
  adj.groupedRows.value.reduce((n, g) => n + g.rows.length, 0),
)

// ─── 从集中登记带入调整（2101 交易性金融负债，负债贷方；带入期末 AJE/RJE） ───
// 仅面向 (三)账面余额组(book_fv)——该组驱动审定合计与 TB 勾稽。
const bringInRows = computed(() =>
  adj.dataRows.value
    .filter((r) => r.group === 'book_fv')
    .map((r) => ({ rowKey: r.rowKey, name: r.label, aje: r.closingAJE, rje: r.closingRJE })),
)
const {
  adjPull,
  visible: bringInVisible,
  rowOptions: bringInRowOptions,
  open: openBringInAdjustment,
  apply: onBringInApply,
} = useAdjudicationBringIn({
  projectId: computed(() => props.projectId) as any,
  year: useAuditContext().year as any,
  subjectPrefix: '2101',
  direction: 'credit',
  subjectCode: '2101',
  wpCode: 'G10',
  subjectLabel: '交易性金融负债(2101)',
  rows: bringInRows,
  updateCell: (rowKey: string, field: any, value: number) =>
    adj.updateField(rowKey, field === 'rje' ? 'closingRJE' : 'closingAJE', value),
  totalAudited: () => adj.totalRow.value.closingAdjusted,
})

const accountLabel = computed(() => g10AccountLabel(adj.tbResolvedCode.value))
const aliasHint = G10_ACCOUNT_ALIASES.join('/')
const tbBarLabel = computed(() =>
  adj.tbResolvedCode.value ? `(${adj.tbResolvedCode.value})` : `(${aliasHint})`,
)

const tableMaxHeight = computed(() =>
  adj.dataRows.value.length >= G10_VIRTUAL_SCROLL_THRESHOLD ? 480 : undefined,
)

const noteProxy = computed({
  get: () => adj.auditNote.value,
  set: (v: string) => adj.updateAuditNote(v),
})

const conclusionProxy = computed({
  get: () => adj.auditConclusion.value,
  set: (v: string) => adj.updateAuditConclusion(v),
})

// ─── 从四表库带入未审数（2101 期初+期末，默认落「（三）账面余额·按组合」行）──────
//
// TB 余额 = 账面余额 = 初始金额 + 累计公允价值变动，四表无法拆分两者。

const seeding = ref(false)

const fourTablePrefill = computed(() =>
  normalizeGAdjPrefill(props.htmlData?.adjudication_prefill),
)

const seedResult = computed(() => buildGSeedCells(fourTablePrefill.value, {
  ...G10_SEED_SPEC,
  labelOf: (k) => adj.dataRows.value.find((r) => r.rowKey === k)?.label ?? k,
}))

const hasFourTablePrefill = computed(() => seedResult.value.cells.length > 0)

const fourTableHint = computed(() =>
  hasFourTablePrefill.value
    ? '把四表库（tb_balance 交易性金融负债叶子余额）带入对应行的期初/期末未审数；已录入的格不覆盖'
    : '四表库暂无交易性金融负债科目数据（需先导入余额表）',
)

function readCurrentCellG10(cell: { rowKey: string; field: string }): number | null {
  const row = adj.dataRows.value.find((r) => r.rowKey === cell.rowKey)
  if (!row) return null
  const v = (row as unknown as Record<string, unknown>)[cell.field]
  return v == null || v === 0 ? null : Number(v)
}

async function onPullFromFourTable(): Promise<void> {
  if (props.isReadonly) return
  const { cells, unclassified, absentSlots } = seedResult.value
  if (!cells.length) {
    ElMessage.info('四表库暂无交易性金融负债科目数据可带入')
    return
  }
  const plan = planAdjudicationPrefill(cells, readCurrentCellG10, { unclassified, absentSlots })
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
      adj.updateField(w.rowKey, w.field as 'openingUnadjusted' | 'closingUnadjusted', w.amount)
    }
    ElMessage.success(describeAdjPrefillPlan(plan))
  } finally {
    seeding.value = false
  }
}

const chk01Type = computed(() => {
  if (adj.hasTbMissing.value) return 'info'
  if (adj.hasVarianceHighlight.value) return 'danger'
  if (adj.tbFetchStatus.value === 'found') return 'success'
  return 'info'
})

const threePartWarnTitle = computed(() => {
  const parts = adj.threePartMismatches.value.slice(0, 3).map((m) => {
    const label = m.field === 'openingAdjusted' ? '期初' : '期末'
    return `${m.suffix} ${label}：(一)+(二)=${fmt(m.expected)} ≠ (三)=${fmt(m.actual)}`
  })
  const more = adj.threePartMismatches.value.length > 3
    ? ` 等共 ${adj.threePartMismatches.value.length} 处`
    : ''
  return `(三)账面余额应等于(一)+(二)：${parts.join('；')}${more}`
})

async function refreshTb() {
  const ok = await adj.loadTrialBalanceFromApi()
  if (!ok && adj.hasTbMissing.value) {
    ElMessage.info(`试算表未找到 ${accountLabel.value}，若本年无此科目可忽略`)
  }
}

function onPublish() {
  if (adj.hasMissingReasons.value) {
    ElMessage.warning('存在 |变动率|>20% 未填原因分析，请先补充或确认无重大波动')
    return
  }
  if (adj.hasVarianceHighlight.value) {
    ElMessage.warning('试算表与(三)账面余额合计存在差异，请核对后再发布')
    return
  }
  if (adj.hasThreePartMismatch.value) {
    ElMessage.warning('(三)与(一)+(二)勾稽不一致，请核对后再发布')
    return
  }
  adj.publishAdjudicated()
  ElMessage.success(`已发布审定数 ${fmt(adj.totalRow.value.closingAdjusted)}`)
}

async function runValidate() {
  validateLoading.value = true
  try {
    const res = await adj.validateFormulasRemote()
    if (res.ok) ElMessage.success('公式校验通过')
    else ElMessage.warning(`发现 ${res.errors.length} 处公式差异`)
  } finally {
    validateLoading.value = false
  }
}

async function onMarkProcedure() {
  const n = await adj.markProcedureComplete()
  if (n < 0) return
  dispatchProcedureFocus({
    programNos: [...G10A_ADJUDICATION_PROGRAM_NOS],
    sheetCode: 'G10A',
    sheetName: G10A_PROCEDURE_SHEET,
  })
  const go = await confirmNavigateToSheet({
    title: '已回填 G10A',
    message: `审定/分析程序（步骤 ${[...G10A_ADJUDICATION_PROGRAM_NOS].join('/')}）已标记完成。是否前往 G10A 程序表查看？`,
    confirmText: '前往 G10A',
  })
  if (go && jumpToSection) {
    jumpToSection('G10A')
    setTimeout(() => {
      dispatchProcedureFocus({
        programNos: [...G10A_ADJUDICATION_PROGRAM_NOS],
        sheetCode: 'G10A',
        sheetName: G10A_PROCEDURE_SHEET,
      })
    }, 400)
  }
}

function fmt(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(rate: number | null): string {
  if (rate == null) return '—'
  return (rate * 100).toFixed(1) + '%'
}

function rowClassName(row: { reasonRequired?: boolean; reasonAnalysis?: string; rowKey?: string }): string {
  if (row.rowKey?.endsWith('_subtotal')) return 'row-subtotal'
  if (row.reasonRequired && !row.reasonAnalysis?.trim()) return 'row-warn'
  return ''
}
</script>

<style scoped>
.g10-adjudication { font-size: var(--wp-font-size, 13px); }
.g10-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.g10-title { margin: 0; font-size: 15px; }
.g10-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.objective-alert { margin-bottom: 10px; }
.guidance-details { margin-bottom: 10px; font-size: 12px; color: #606266; }
.guidance-content p { margin: 4px 0; line-height: 1.5; }
.tb-bar { margin-bottom: 10px; padding: 8px; background: #f5f7fa; border-radius: 4px; font-size: 12px; }
.tb-warn { color: #f56c6c; background: #fef0f0; }
.tb-ok { background: #f0f9eb; }
.reason-alert { margin-bottom: 8px; }
.group-block { margin-bottom: 8px; }
.group-head { display: flex; align-items: center; gap: 8px; padding: 6px 8px; background: #f5f7fa; cursor: pointer; border-radius: 4px; }
.group-toggle { font-size: 11px; color: #909399; }
.group-sub { margin-left: auto; font-size: 12px; color: #606266; }
.formula-cell { border-bottom: 1px dashed #c0c4cc; }
.rate-warn { color: #e6a23c; font-weight: 600; }
.reason-required :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px #e6a23c inset; }
.fine-checks { display: flex; gap: 8px; margin: 10px 0; flex-wrap: wrap; }
.g10-tb-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin: 10px 0; }
.variance.is-error { color: #f56c6c; font-weight: 600; }
.total-row { margin-top: 12px; padding: 10px; background: #ecf5ff; font-weight: 600; }
.cross-alert { margin-top: 8px; }
.is-subtotal { font-weight: 600; }
:deep(.row-warn) { background-color: #fdf6ec !important; }
:deep(.row-subtotal) { background-color: #ecf5ff !important; font-weight: 600; }
</style>
