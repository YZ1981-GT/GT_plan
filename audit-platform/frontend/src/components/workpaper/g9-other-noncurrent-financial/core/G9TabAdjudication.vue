<template>
  <div class="g9-adjudication" data-testid="g9-adjudication">
    <div class="g9-toolbar tab-toolbar">
      <h3 class="g9-title">G9-1 其他非流动金融资产审定表</h3>
      <div class="g9-actions">
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
        <GtIndexChip value="wp:G9-1" />
        <el-tag size="small" type="info">共 {{ adjRowCount }} 行</el-tag>
        <GtReviewTrigger section-id="G9-1-adjudication" />
        <el-button size="small" :loading="validateLoading" :disabled="isReadonly" data-testid="g9-validate-btn" @click="runValidate">校验公式</el-button>
        <el-button size="small" :loading="adj.aiLoading.value" :disabled="isReadonly" @click="adj.generateAiAnalysis()">🤖 AI</el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      :title="`审计目标：确认${accountLabel}期末余额真实存在、完整、计价准确，混合计量分类与附注列报恰当。`"
    />

    <details class="guidance-details" open>
      <summary>📋 编制提示（对齐 Excel 审定表 G9-1）</summary>
      <div class="guidance-content">
        <p><b>编制思路：</b>未审 → 账项调整(AJE) / 重分类(RJE) → 审定；审定数与试算表、G9-2 明细合计勾稽。</p>
        <p><b>行结构：</b>按 FVTPL / FVOCI / 摊余成本分组；组首行为回写合计，其下按债务/权益/衍生·其他/指定展开（与附注四类一致）。投资成本与累计公允价值变动在 G9-2 明细展开，本表列报账面余额（公允价值）审定过程。</p>
        <p><b>公式：</b>审定数 = 未审 + AJE + RJE；变动额 = 期末审定 − 期初审定；变动率 = 变动额 / 期初审定。</p>
        <p><b>分析要求：</b>|变动率|&gt;20% 时原因分析必填；审计说明中对 |变动率|&gt;30% 的项目重点说明增减原因（对齐模板「审计说明」）。</p>
        <p><b>交易性判定（编制说明）：</b>近期出售或回购、集中管理且存在短期获利模式、衍生工具（财务担保合同及有效套期工具除外）。持有方判断权益工具投资时遵循 CAS 22 / CAS 37。</p>
        <p><b>带入调整：</b>可从集中登记按科目 1519 拉取调整分录，逐笔分配到各分组行的期末账项(AJE)/重分类(RJE)调整，带入后审定数自动更新并联动附注。</p>
      </div>
    </details>

    <el-alert
      v-if="adj.hasTbMissing.value"
      type="info"
      :closable="false"
      class="reason-alert"
      data-testid="g9-adj-tb-missing"
      :title="`试算表未取到 ${accountLabel}（已试 ${aliasHint}）。若本年无此科目可忽略；有余额请检查科目映射后点「刷新TB」`"
    />

    <div
      v-else-if="adj.hasVarianceHighlight.value"
      class="tb-bar tb-warn"
      data-testid="g9-tb-bar"
    >
      试算表 {{ tbBarLabel }}: {{ fmt(adj.trialBalanceAmount.value) }}
      | 差异: {{ fmt(adj.variance.value) }}
      <el-button v-if="!isReadonly" size="small" link @click="refreshTb">刷新TB</el-button>
    </div>
    <div v-else-if="adj.tbFetchStatus.value === 'found'" class="tb-bar tb-ok" data-testid="g9-tb-bar">
      试算表 {{ tbBarLabel }}: {{ fmt(adj.trialBalanceAmount.value) }}
      | 差异: {{ fmt(adj.variance.value) }} ✓
      <el-button v-if="!isReadonly" size="small" link @click="refreshTb">刷新TB</el-button>
    </div>
    <div v-else class="tb-bar" data-testid="g9-tb-bar">
      试算表 {{ tbBarLabel }}: 待刷新
      <el-button v-if="!isReadonly" size="small" link @click="refreshTb">刷新TB</el-button>
    </div>

    <el-alert
      v-if="adj.hasMissingReasons.value"
      type="warning"
      :closable="false"
      class="reason-alert"
      data-testid="g9-adj-reason-warn"
      :title="`有 ${adj.missingReasonCount.value} 行 |变动率|>20%，请填写原因分析`"
    />

    <el-alert
      v-if="adj.hasGroupBreakdownMismatch.value"
      type="warning"
      :closable="false"
      class="reason-alert"
      data-testid="g9-adj-breakdown-warn"
      :title="breakdownWarnTitle"
    />

    <div v-for="group in adj.groupedRows.value" :key="group.groupKey" class="group-block">
      <div class="group-head" @click="adj.toggleGroup(group.groupKey)">
        <span>{{ group.collapsed ? '▶' : '▼' }}</span>
        <strong>{{ group.groupName }}</strong>
        <span class="group-sub">期末审定 {{ fmt(group.subtotal.closingAdjusted) }} · 变动 {{ fmt(group.subtotal.changeAmount) }}</span>
      </div>
      <!-- 四表库取数溯源（口径：期末余额） -->
      <WpFourTableSourcePanel
        :source-codes="tbSourceCodes"
        gross-label="其他非流动金融资产"
        fallback-row-code="BS-026"
      />

      <el-table
        v-show="!group.collapsed"
        :data="[...group.rows, group.subtotal]"
        border size="small"
        style="font-size:13px"
        :max-height="480"
        :row-class-name="({ row }) => rowClassName(row)"
      >
        <el-table-column label="项目" prop="label" min-width="200" fixed>
          <template #default="{ row }">
            <GtReviewDot v-if="!row.rowKey?.endsWith('_subtotal')" row-prefix="G9-adj" :row-key="row.rowKey" />
            <span :class="{ 'is-subtotal': row.rowKey?.endsWith('_subtotal'), 'is-group-total': isGroupTotalKey(row.rowKey) }">{{ row.label }}</span>
          </template>
        </el-table-column>

        <el-table-column label="期初数" align="center">
          <el-table-column label="未审数" width="88" align="right">
            <template #default="{ row }">
              <template v-if="row.rowKey?.endsWith('_subtotal')"><span class="formula-cell">{{ fmt(row.openingUnadjusted) }}</span></template>
              <el-input-number v-else-if="!isReadonly" :model-value="row.openingUnadjusted" size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'openingUnadjusted', v ?? 0)" />
              <span v-else>{{ fmt(row.openingUnadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账项调整" width="80" align="right">
            <template #default="{ row }">
              <template v-if="row.rowKey?.endsWith('_subtotal')"><span class="formula-cell">{{ fmt(row.openingAJE) }}</span></template>
              <el-input-number v-else-if="!isReadonly" :model-value="row.openingAJE" size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'openingAJE', v ?? 0)" />
              <span v-else>{{ fmt(row.openingAJE) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="重分类" width="80" align="right">
            <template #default="{ row }">
              <template v-if="row.rowKey?.endsWith('_subtotal')"><span class="formula-cell">{{ fmt(row.openingRJE) }}</span></template>
              <el-input-number v-else-if="!isReadonly" :model-value="row.openingRJE" size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'openingRJE', v ?? 0)" />
              <span v-else>{{ fmt(row.openingRJE) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定数" width="92" align="right">
            <template #default="{ row }"><span class="formula-cell" title="期初审定 = 未审 + 账项调整 + 重分类">{{ fmt(row.openingAdjusted) }}</span></template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="期末数" align="center">
          <el-table-column label="未审数" width="88" align="right">
            <template #default="{ row }">
              <template v-if="row.rowKey?.endsWith('_subtotal')"><span class="formula-cell">{{ fmt(row.closingUnadjusted) }}</span></template>
              <el-input-number v-else-if="!isReadonly" :model-value="row.closingUnadjusted" size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'closingUnadjusted', v ?? 0)" />
              <span v-else>{{ fmt(row.closingUnadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账项调整" width="80" align="right">
            <template #default="{ row }">
              <template v-if="row.rowKey?.endsWith('_subtotal')"><span class="formula-cell">{{ fmt(row.closingAJE) }}</span></template>
              <el-input-number v-else-if="!isReadonly" :model-value="row.closingAJE" size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'closingAJE', v ?? 0)" />
              <span v-else>{{ fmt(row.closingAJE) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="重分类" width="80" align="right">
            <template #default="{ row }">
              <template v-if="row.rowKey?.endsWith('_subtotal')"><span class="formula-cell">{{ fmt(row.closingRJE) }}</span></template>
              <el-input-number v-else-if="!isReadonly" :model-value="row.closingRJE" size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'closingRJE', v ?? 0)" />
              <span v-else>{{ fmt(row.closingRJE) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定数" width="92" align="right">
            <template #default="{ row }"><span class="formula-cell" title="期末审定 = 未审 + 账项调整 + 重分类">{{ fmt(row.closingAdjusted) }}</span></template>
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

    <div class="total-row">
      <strong>账面余额（公允价值）合计</strong>
      期末审定 {{ fmt(adj.totalRow.value.closingAdjusted) }}
      · 变动额 {{ fmt(adj.totalRow.value.changeAmount) }}
      · 变动率 {{ fmtRate(adj.totalRow.value.changeRate) }}
    </div>

    <div v-if="adj.hasDetailCrossMismatch.value" class="cross-warn" data-testid="g9-detail-cross-warn">
      G9-1 合计 {{ fmt(adj.totalRow.value.closingAdjusted) }} 与 G9-2 明细合计
      {{ fmt(adj.detailTotalClosing.value ?? 0) }} 差异 {{ fmt(adj.detailCrossVariance.value ?? 0) }}
    </div>

    <div class="fine-checks" data-testid="g9-fine-checks">
      <el-tag size="small" :type="chk01Type">G9-CHK-01 试算表勾稽</el-tag>
      <el-tag size="small" :type="adj.hasDetailCrossMismatch.value ? 'warning' : 'success'">G9-CHK-02 明细表勾稽</el-tag>
      <el-tag size="small" :type="adj.hasMissingReasons.value ? 'warning' : 'success'">G9-CHK-03 变动率原因</el-tag>
      <el-tag size="small" :type="adj.hasGroupBreakdownMismatch.value ? 'warning' : 'success'">G9-CHK-04 组内合计=分项</el-tag>
    </div>

    <div class="g9-tb-row">
      <span>试算平衡表数（{{ tbBarLabel }}）：</span>
      <template v-if="adj.hasTbMissing.value">
        <span class="tb-missing">未取到</span>
      </template>
      <template v-else>
        <el-input-number v-if="!isReadonly" :model-value="adj.trialBalanceAmount.value" size="small" :controls="false"
          style="width:140px" @update:model-value="(v: number) => adj.updateTrialBalance(v ?? 0)" />
        <span v-else>{{ fmt(adj.trialBalanceAmount.value) }}</span>
        <span :class="['variance', { 'is-error': adj.hasVarianceHighlight.value }]">差异数：{{ fmt(adj.variance.value) }}</span>
      </template>
      <el-button v-if="!isReadonly" size="small" link @click="refreshTb">刷新TB</el-button>
      <el-button size="small" type="primary" :disabled="isReadonly" data-testid="g9-publish-adj" @click="onPublish">发布审定数</el-button>
    </div>

    <G9AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="noteProxy"
      v-model:conclusion="auditConclusion"
      note-ai-section="adjudication-analysis"
      conclusion-ai-section="adjudication-conclusion"
      note-placeholder="审计说明：(1) 较上年增减变动原因（|变动率|>30% 须重点说明）；(2) 分类计量、与 TB/明细勾稽及拟调整事项。"
      note-hint="覆盖分组审定、TB 勾稽、AJE/RJE 影响及重大波动原因。"
      :related-context="{ 行数: adjRowCount, TB差异: adj.variance.value, 变动额: adj.totalRow.value.changeAmount }"
    />

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="1519 其他非流动金融资产"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, toRef, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtReviewDot from '../../GtReviewDot.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import G9AuditTextCards from '../G9AuditTextCards.vue'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import { useG9Adjudication } from '../../composables/useG9Adjudication'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import { useAuditContext } from '@/composables/useAuditContext'
import { G9_ADJUDICATION_ITEMS, G9_GROUP_LABELS, G9_ACCOUNT_ALIASES } from '../../composables/g9Constants'
import { g9AccountLabel } from '../../composables/g9AccountMatch'
import {
  buildG9SeedCells,
  normalizeGAdjPrefill,
} from '../../composables/gCycleAdjudicationSeed'
import {
  describeAdjPrefillConflicts,
  describeAdjPrefillPlan,
  planAdjudicationPrefill,
  planHasWork,
  resolveAdjPrefillWrites,
} from '../../composables/shared/adjudicationPrefillPlan'
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
 * 科目由后端按**科目名**逐项目解析（`four_table/g_cycle_specs.G9_SPEC`），
 * 取数口径 = 期末余额。前端单一真源见 `composables/gCycleAccountScope.ts`。
 */
const tbSourceCodes = computed(() => props.htmlData?.tb_source_codes ?? null)
const validateLoading = ref(false)

const adj = useG9Adjudication({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
})

// ─── 从集中登记带入调整（1519 其他非流动金融资产，资产借方；带入期末 AJE/RJE） ───
const bringInRows = computed(() =>
  adj.dataRows.value.map((r) => ({ rowKey: r.rowKey, name: r.label, aje: r.closingAJE, rje: r.closingRJE })),
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
  subjectPrefix: '1519',
  direction: 'debit',
  subjectCode: '1519',
  wpCode: 'G9',
  subjectLabel: '其他非流动金融资产(1519)',
  rows: bringInRows,
  updateCell: (rowKey: string, field: any, value: number) =>
    adj.updateField(rowKey, field === 'rje' ? 'closingRJE' : 'closingAJE', value),
  totalAudited: () => adj.totalRow.value.closingAdjusted,
})

const noteProxy = computed({
  get: () => adj.auditNote.value,
  set: (v: string) => adj.updateAuditNote(v),
})

const CONCLUSION_KEY = 'G9-adjudication-audit-conclusion'
const _conclResp = props.allResponses.get(CONCLUSION_KEY)
const auditConclusion = ref(String(_conclResp?.conclusion ?? _conclResp?.remark ?? ''))
watch(auditConclusion, (v) => {
  if (!props.isReadonly) {
    props.debouncedSave(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: v, remark: null })
  }
})

const adjRowCount = computed(() =>
  adj.groupedRows.value.reduce((n, g) => n + g.rows.length, 0),
)

const groupTotalKeys = new Set(
  G9_ADJUDICATION_ITEMS.filter((d) => d.isGroupTotal).map((d) => d.rowKey),
)

// ─── 从四表库带入未审数（1519 期初+期末，按叶子顺序落可编辑行，跳过小计行）──────

const seeding = ref(false)

const fourTablePrefill = computed(() =>
  normalizeGAdjPrefill(props.htmlData?.adjudication_prefill),
)

const seedResult = computed(() => buildG9SeedCells(
  fourTablePrefill.value,
  (k) => adj.dataRows.value.find((r) => r.rowKey === k)?.label ?? k,
))

const hasFourTablePrefill = computed(() => seedResult.value.cells.length > 0)

const fourTableHint = computed(() =>
  hasFourTablePrefill.value
    ? '把四表库（tb_balance 其他非流动金融资产叶子余额）按顺序带入可编辑行的期初/期末未审数；已录入的格不覆盖'
    : '四表库暂无其他非流动金融资产科目数据（需先导入余额表）',
)

function readCurrentCellG9(cell: { rowKey: string; field: string }): number | null {
  const row = adj.dataRows.value.find((r) => r.rowKey === cell.rowKey)
  if (!row) return null
  const v = (row as unknown as Record<string, unknown>)[cell.field]
  return v == null || v === 0 ? null : Number(v)
}

async function onPullFromFourTable(): Promise<void> {
  if (props.isReadonly) return
  const { cells, unclassified, absentSlots } = seedResult.value
  if (!cells.length) {
    ElMessage.info('四表库暂无其他非流动金融资产科目数据可带入')
    return
  }
  const plan = planAdjudicationPrefill(cells, readCurrentCellG9, { unclassified, absentSlots })
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
function isGroupTotalKey(rowKey?: string): boolean {
  return !!rowKey && groupTotalKeys.has(rowKey)
}

const accountLabel = computed(() => g9AccountLabel(adj.tbResolvedCode.value))
const aliasHint = G9_ACCOUNT_ALIASES.join('/')
const tbBarLabel = computed(() =>
  adj.tbResolvedCode.value ? `(${adj.tbResolvedCode.value})` : `(${aliasHint})`,
)

const chk01Type = computed(() => {
  if (adj.hasTbMissing.value) return 'info'
  if (adj.hasVarianceHighlight.value) return 'danger'
  if (adj.tbFetchStatus.value === 'found') return 'success'
  return 'info'
})

const breakdownWarnTitle = computed(() => {
  const parts = adj.groupBreakdownMismatches.value.map((m) => {
    const name = G9_GROUP_LABELS[m.category] ?? m.category
    return `${name}：合计 ${fmt(m.groupTotal)} ≠ 分项 ${fmt(m.detailSum)}（差 ${fmt(m.diff)}）`
  })
  return `组内合计与分项不一致：${parts.join('；')}`
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
    ElMessage.warning('试算表与审定合计存在差异，请核对后再发布')
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

function fmt(n: number): string {
  return Number(n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtRate(r: number | null | undefined): string {
  if (r === null || r === undefined) return '—'
  return `${(r * 100).toFixed(1)}%`
}

function rowClassName(row: { reasonRequired?: boolean; reasonAnalysis?: string; rowKey?: string }): string {
  if (row.rowKey?.endsWith('_subtotal')) return 'row-subtotal'
  if (isGroupTotalKey(row.rowKey)) return 'row-group-total'
  if (row.reasonRequired && !row.reasonAnalysis?.trim()) return 'row-warn'
  return ''
}
</script>

<style scoped>
.g9-adjudication { font-size: var(--wp-font-size, 13px); }
.g9-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.g9-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.g9-title { margin: 0; font-size: 15px; }
.tb-bar { margin-bottom: 10px; padding: 8px; background: #f5f7fa; border-radius: 4px; }
.tb-warn { color: #f56c6c; background: #fef0f0; }
.tb-ok { background: #f0f9eb; }
.tb-missing { color: #909399; font-style: italic; }
.group-head { cursor: pointer; padding: 8px; background: #fafafa; border: 1px solid #ebeef5; margin-top: 8px; display: flex; gap: 8px; align-items: center; }
.group-sub { margin-left: auto; color: #606266; font-size: 12px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; background: #f5f7fa; display: inline-block; width: 100%; }
.audit-objective { margin-bottom: 10px; }
.rate-warn { color: #e6a23c; font-weight: 600; }
.reason-alert { margin-bottom: 8px; }
:deep(.reason-required .el-input__wrapper) { box-shadow: 0 0 0 1px #e6a23c inset; }
:deep(.row-warn) { background: #fdf6ec !important; }
:deep(.row-subtotal) { background: #ecf5ff !important; font-weight: 600; }
:deep(.row-group-total) { background: #f0f9eb !important; font-weight: 600; }
.is-subtotal, .is-group-total { font-weight: 600; }
.total-row { margin-top: 12px; padding: 10px; background: #ecf5ff; font-weight: 600; }
.cross-warn { margin-top: 8px; padding: 8px 12px; background: #fdf6ec; color: #e6a23c; border-radius: 4px; font-size: 12px; }
.guidance-details { margin-bottom: 10px; font-size: 12px; color: #606266; }
.guidance-content p { margin: 4px 0; line-height: 1.5; }
.g9-tb-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin: 10px 0; }
.variance.is-error { color: #f56c6c; font-weight: 600; }
.fine-checks { display: flex; gap: 8px; margin: 10px 0; flex-wrap: wrap; }
</style>
