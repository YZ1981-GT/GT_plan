<template>
  <div class="g8-adjudication" data-testid="g8-adjudication">
    <div class="g8-toolbar">
      <div class="title-block">
        <h3 class="g8-title">G8-1 其他权益工具投资审定表</h3>
        <p class="sheet-sub">科目 1503 · 审定 = 未审 + 账项调整 · 与 TB / G8-2 / G8-3 / G8-4 勾稽</p>
      </div>
      <div class="g8-actions">
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
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          plain
          data-testid="g8-sync-from-detail"
          @click="onSyncFromDetail"
        >
          从 G8-2 带入未审
        </el-button>
        <GtReviewTrigger section-id="G8-1-adjudication" />
        <el-button size="small" :loading="validateLoading" :disabled="isReadonly" data-testid="g8-validate-btn" @click="runValidate">
          校验公式
        </el-button>
      </div>
    </div>

    <details class="guidance-details" open>
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表汇总科目 1503 其他权益工具投资（FVOCI）期初/期末审定；审定数 = 未审数 + 账项调整。</p>
        <p>2. 编制顺序：G8-2 明细取账面 →「从 G8-2 带入未审」→ G8-3 调整回写期末调整（默认写入「{{ adj.writebackRowKey }}」行）→ 刷新 TB 勾稽 → 核对 G8-4 公允合计。</p>
        <p>3. |变动率|&gt;20% 时原因分析必填；试算表差异、明细/公允勾稽异常须追查后再发布审定数。</p>
        <p>4. 公允价值变动计入 OCI，不经损益；处置时累计 OCI 可转留存收益。</p>
        <p>5.「带入调整」：可从集中登记按科目 1503 拉取调整分录，逐笔分配到各行期末调整，带入后审定数自动更新并联动附注。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计目标：核实其他权益工具投资（1503）期末余额的存在与计价，验证 FVOCI/OCI 分类恰当，确认审定数与试算表、明细表及公允测试勾稽一致。"
      class="objective-alert"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="chip-wrap"><GtIndexChip value="wp:G8-2" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G8-3" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G8-4" :context-project-id="projectId" /></span>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G8-1" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rowCount }} 行</el-tag>
      </div>
    </div>

    <el-alert
      v-if="adj.hasMissingReasons.value"
      type="warning"
      :closable="false"
      show-icon
      class="reason-alert"
      data-testid="g8-adj-reason-warn"
      :title="`有 ${adj.missingReasonCount.value} 行 |变动率|>20%，请填写原因分析`"
    />

    <div v-for="group in adj.groupedRows.value" :key="group.groupKey" class="group-block">
      <div class="group-head" @click="adj.toggleGroup()">
        <span class="group-toggle">{{ group.collapsed ? '▶' : '▼' }}</span>
        <strong>{{ group.groupName }}</strong>
        <span class="group-sub">期末 {{ fmt(group.subtotal.closingAdjusted) }}</span>
      </div>
      <!-- 四表库取数溯源（口径：期末余额） -->
      <WpFourTableSourcePanel
        :source-codes="tbSourceCodes"
        gross-label="其他权益工具投资"
        fallback-row-code="BS-025"
      />

      <el-table
        v-show="!group.collapsed"
        :data="group.rows"
        border
        size="small"
        style="font-size:13px"
        :max-height="480"
        :row-class-name="rowClassName"
      >
        <el-table-column label="项目" prop="label" min-width="180" fixed>
          <template #default="{ row }">
            <GtReviewDot row-prefix="G8-adj" :row-key="row.rowKey" />
            {{ row.label }}
          </template>
        </el-table-column>
        <el-table-column label="期初" align="center">
          <el-table-column label="未审" width="92" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.openingUnadjusted" size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'openingUnadjusted', v ?? 0)" />
              <span v-else>{{ fmt(row.openingUnadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="调整" width="88" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.openingAdjustment" size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'openingAdjustment', v ?? 0)" />
              <span v-else>{{ fmt(row.openingAdjustment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定" width="92" align="right">
            <template #default="{ row }"><span class="formula-cell" title="未审+调整">{{ fmt(row.openingAdjusted) }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期末" align="center">
          <el-table-column label="未审" width="92" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.closingUnadjusted" size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'closingUnadjusted', v ?? 0)" />
              <span v-else>{{ fmt(row.closingUnadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="调整" width="88" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.closingAdjustment" size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'closingAdjustment', v ?? 0)" />
              <span v-else>{{ fmt(row.closingAdjustment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定" width="92" align="right">
            <template #default="{ row }"><span class="formula-cell" title="未审+调整">{{ fmt(row.closingAdjusted) }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="变动额" width="92" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.changeAmount) }}</span></template>
        </el-table-column>
        <el-table-column label="变动率" width="76" align="right">
          <template #default="{ row }">
            <span :class="{ 'rate-warn': row.changeRateHighlight }">{{ fmtRate(row.changeRate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="原因分析" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.reasonAnalysis" size="small"
              :class="{ 'reason-required': row.reasonRequired && !row.reasonAnalysis }"
              placeholder="|变动率|>20%时必填"
              @change="(v: string) => adj.updateField(row.rowKey, 'reasonAnalysis', v)" />
            <span v-else>{{ row.reasonAnalysis }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引" width="72">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.indexRef" size="small"
              @change="(v: string) => adj.updateField(row.rowKey, 'indexRef', v)" />
            <GtIndexChip v-else-if="row.indexRef" :value="row.indexRef" />
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-table :data="[adj.totalRow.value]" border size="small" class="total-table" style="font-size:13px">
      <el-table-column label="项目" prop="label" min-width="180" />
      <el-table-column label="期初审定" width="100" align="right">
        <template #default="{ row }"><strong>{{ fmt(row.openingAdjusted) }}</strong></template>
      </el-table-column>
      <el-table-column label="期末审定" width="100" align="right">
        <template #default="{ row }"><strong>{{ fmt(row.closingAdjusted) }}</strong></template>
      </el-table-column>
      <el-table-column label="变动额" width="92" align="right">
        <template #default="{ row }">{{ fmt(row.changeAmount) }}</template>
      </el-table-column>
      <el-table-column label="变动率" width="76" align="right">
        <template #default="{ row }"><span :class="{ 'rate-warn': row.changeRateHighlight }">{{ fmtRate(row.changeRate) }}</span></template>
      </el-table-column>
    </el-table>

    <el-alert
      v-if="adj.hasDetailCrossMismatch.value"
      type="warning"
      :closable="false"
      show-icon
      class="cross-alert"
      data-testid="g8-detail-cross-alert"
    >
      <template #title>
        <span>
          G8-1 合计 {{ fmt(adj.totalRow.value.closingAdjusted) }} 与 G8-2 明细合计
          {{ fmt(adj.detailTotalClosing.value ?? 0) }} 差异 {{ fmt(adj.detailCrossVariance.value ?? 0) }}
        </span>
        <el-button size="small" link type="primary" @click="goSheet('G8-2')">前往 G8-2</el-button>
      </template>
    </el-alert>

    <el-alert
      v-if="adj.hasFvCrossMismatch.value"
      type="warning"
      :closable="false"
      show-icon
      class="cross-alert"
      data-testid="g8-fv-cross-alert"
    >
      <template #title>
        <span>
          G8-1 合计 {{ fmt(adj.totalRow.value.closingAdjusted) }} 与 G8-4 审定公允价值合计
          {{ fmt(adj.fvAuditedTotal.value ?? 0) }} 差异 {{ fmt(adj.fvCrossVariance.value ?? 0) }}
        </span>
        <el-button size="small" link type="primary" @click="goSheet('G8-4')">前往 G8-4</el-button>
      </template>
    </el-alert>

    <div class="fine-checks" data-testid="g8-fine-checks">
      <el-tag size="small" :type="adj.hasVarianceHighlight.value ? 'danger' : 'success'">G8-CHK-01 试算表勾稽</el-tag>
      <el-tag size="small" :type="adj.hasDetailCrossMismatch.value ? 'warning' : 'success'">G8-CHK-02 明细表勾稽</el-tag>
      <el-tag size="small" :type="adj.hasFvCrossMismatch.value ? 'warning' : 'success'">G8-CHK-05 公允测试勾稽</el-tag>
      <el-tag size="small" :type="adj.hasMissingReasons.value ? 'warning' : 'success'">G8-CHK-03 变动率原因</el-tag>
    </div>

    <div class="tb-info-bar" :class="{ ok: !adj.hasVarianceHighlight.value, bad: adj.hasVarianceHighlight.value }" data-testid="g8-tb-bar">
      <span class="tb-label">试算平衡表数（1503）</span>
      <el-input-number
        v-if="!isReadonly"
        :model-value="adj.trialBalanceAmount.value"
        size="small"
        :controls="false"
        style="width:140px"
        @update:model-value="(v: number) => adj.updateTrialBalance(v ?? 0)"
      />
      <span v-else>{{ fmt(adj.trialBalanceAmount.value) }}</span>
      <span class="tb-var">差异 {{ fmt(adj.variance.value) }} {{ adj.hasVarianceHighlight.value ? '✗' : '✓' }}</span>
      <el-button v-if="!isReadonly" size="small" link @click="adj.loadTrialBalanceFromApi()">刷新TB</el-button>
      <el-button size="small" type="primary" :disabled="isReadonly" data-testid="g8-publish-adj" @click="onPublish">
        发布审定数
      </el-button>
      <el-button size="small" link type="primary" @click="goSheet('G8-3')">查看 G8-3 调整</el-button>
    </div>

    <G8AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="noteProxy"
      v-model:conclusion="conclusionProxy"
      note-ai-section="adjudication-note"
      conclusion-ai-section="adjudication-conclusion"
      note-placeholder="填写审计说明：（1）程序测试情况与结果；（2）与 TB/G8-2/G8-4 勾稽；（3）G8-3 调整及未调整事项影响。"
      note-hint="覆盖期初/期末审定、OCI 分类及跨表勾稽。"
      conclusion-placeholder="填写审计结论：A、审定数准确、FVOCI 分类恰当，与试算表及明细勾稽一致。B、除已调整事项外未见异常。C、存在重大未调整差异或范围受限，不可确认。"
      conclusion-hint="可先选 A/B/C 口径，再按需补充说明。"
      :related-context="{
        期末审定: adj.totalRow.value.closingAdjusted,
        试算表差异: adj.variance.value,
        明细勾稽差异: adj.detailCrossVariance.value,
        公允勾稽差异: adj.fvCrossVariance.value,
        缺失原因行数: adj.missingReasonCount.value,
      }"
    />

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="1503 其他权益工具投资"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * G8TabAdjudication.vue — G8-1 审定表
 * 勾稽：TB / G8-2 明细 / G8-3 调整回写 / G8-4 公允合计
 */
import { computed, inject, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtReviewDot from '../../GtReviewDot.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import G8AuditTextCards from '../G8AuditTextCards.vue'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import { useG8Adjudication } from '../../composables/useG8Adjudication'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import { useAuditContext } from '@/composables/useAuditContext'
import { jumpToG8Sheet } from '../../composables/g8CrossHelpers'
import {
  buildG8FvSeedCells,
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
 * 科目由后端按**科目名**逐项目解析（`four_table/g_cycle_specs.G8_SPEC`），
 * 取数口径 = 期末余额。前端单一真源见 `composables/gCycleAccountScope.ts`。
 */
const tbSourceCodes = computed(() => props.htmlData?.tb_source_codes ?? null)
const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)
const validateLoading = ref(false)

const adj = useG8Adjudication({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  allResponses: computed(() => props.allResponses),
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
})

// ─── 从集中登记带入调整（1503 其他权益工具投资，资产借方；带入期末调整，单一调整列） ───
const bringInRows = computed(() =>
  adj.dataRows.value.map((r) => ({ rowKey: r.rowKey, name: r.label, aje: 0, rje: 0 })),
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
  subjectPrefix: '1503',
  direction: 'debit',
  subjectCode: '1503',
  wpCode: 'G8',
  subjectLabel: '其他权益工具投资(1503)',
  rows: bringInRows,
  // 单一「调整」列：aje/rje 净额均累加至期末调整（读取实时值做增量累加）
  updateCell: (rowKey: string, _field: any, value: number) => {
    const row = adj.dataRows.value.find((r) => r.rowKey === rowKey)
    const live = row?.closingAdjustment ?? 0
    adj.updateField(rowKey, 'closingAdjustment', Math.round((live + value) * 100) / 100)
  },
  totalAudited: () => adj.totalRow.value.closingAdjusted,
})

const noteProxy = computed({
  get: () => adj.auditNote.value,
  set: (v: string) => adj.updateAuditNote(v),
})

const conclusionProxy = computed({
  get: () => adj.auditConclusion.value,
  set: (v: string) => adj.updateAuditConclusion(v),
})

const rowCount = computed(() =>
  adj.groupedRows.value.reduce((n, g) => n + (g.rows?.length ?? 0), 0),
)

// ─── 从四表库带入未审数（1507 期初+期末，按叶子顺序落 10 个占位行，同 G6 范式）──────

const seeding = ref(false)

const fourTablePrefill = computed(() =>
  normalizeGAdjPrefill(props.htmlData?.adjudication_prefill),
)

const seedResult = computed(() => buildG8FvSeedCells(
  fourTablePrefill.value,
  (k) => adj.dataRows.value.find((r) => r.rowKey === k)?.label ?? k,
))

const hasFourTablePrefill = computed(() => seedResult.value.cells.length > 0)

const fourTableHint = computed(() =>
  hasFourTablePrefill.value
    ? '把四表库（tb_balance 其他权益工具投资叶子余额）按顺序带入占位行的期初/期末未审数；已录入的格不覆盖'
    : '四表库暂无其他权益工具投资科目数据（需先导入余额表）',
)

function readCurrentCellG8(cell: { rowKey: string; field: string }): number | null {
  const row = adj.dataRows.value.find((r) => r.rowKey === cell.rowKey)
  if (!row) return null
  const v = (row as unknown as Record<string, unknown>)[cell.field]
  return v == null || v === 0 ? null : Number(v)
}

async function onPullFromFourTable(): Promise<void> {
  if (props.isReadonly) return
  const { cells, unclassified, absentSlots } = seedResult.value
  if (!cells.length) {
    ElMessage.info('四表库暂无其他权益工具投资科目数据可带入')
    return
  }
  const plan = planAdjudicationPrefill(cells, readCurrentCellG8, { unclassified, absentSlots })
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

function fmt(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(rate: number | null): string {
  if (rate == null) return '—'
  return (rate * 100).toFixed(1) + '%'
}

function rowClassName({ row }: { row: { reasonRequired?: boolean; reasonAnalysis?: string } }) {
  if (row.reasonRequired && !row.reasonAnalysis) return 'row-warn'
  return ''
}

function goSheet(code: string) {
  jumpToG8Sheet(code, jumpToSection)
}

function onSyncFromDetail() {
  const res = adj.syncUnadjustedFromDetail()
  if (!res.count) {
    ElMessage.warning('G8-2 暂无明细，请先编制明细表')
    return
  }
  ElMessage.success(
    `已从 G8-2（${res.count} 行）带入未审：期初 ${fmt(res.opening)} / 期末 ${fmt(res.closing)}（保留账项调整）`,
  )
}

function onPublish() {
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
</script>

<style scoped>
.g8-adjudication { font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 10px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.tab-toolbar .toolbar-left,
.tab-toolbar .toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.tab-toolbar .chip-wrap { display: inline-flex; align-items: center; }
.g8-toolbar { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.title-block .g8-title { margin: 0; font-size: 15px; }
.sheet-sub { margin: 4px 0 0; font-size: 12px; color: #909399; }
.g8-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.guidance-details {
  margin-bottom: 10px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 12px; color: #606266; line-height: 1.65; }
.guidance-content p { margin: 2px 0; }
.reason-alert { margin-bottom: 8px; }
.group-block { margin-bottom: 8px; }
.group-head { display: flex; align-items: center; gap: 8px; padding: 6px 8px; background: #f5f7fa; cursor: pointer; border-radius: 4px; }
.group-toggle { font-size: 11px; color: #909399; }
.group-sub { margin-left: auto; font-size: 12px; color: #606266; }
.formula-cell { border-bottom: 1px dashed #c0c4cc; cursor: help; }
.rate-warn { color: #e6a23c; font-weight: 600; }
.reason-required :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px #e6a23c inset; }
.tb-info-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin: 10px 0;
  padding: 8px 12px;
  border-radius: 4px;
  background: #f0f9eb;
  font-size: 12px;
}
.tb-info-bar.bad { background: #fef0f0; }
.tb-label { font-weight: 600; }
.tb-var { font-weight: 600; }
.tb-info-bar.bad .tb-var { color: #f56c6c; }
.tb-info-bar.ok .tb-var { color: #67c23a; }
.total-table { margin-top: 8px; }
.cross-alert { margin: 8px 0; }
.fine-checks { display: flex; gap: 8px; margin: 10px 0; flex-wrap: wrap; }
:deep(.row-warn) { background-color: #fdf6ec !important; }
</style>
