<template>
  <div class="g11-adjudication" data-testid="g11-adjudication">
    <div class="g11-toolbar">
      <h3 class="g11-title">G11-1 投资收益审定表</h3>
      <div class="g11-actions">
        <el-button size="small" type="primary" plain :loading="adjPull.loading.value" @click="openBringInAdjustment">
          <el-icon><Download /></el-icon>带入调整
        </el-button>
        <el-tooltip :content="fourTableHint" placement="top">
          <el-button
            size="small"
            type="success"
            plain
            :disabled="isReadonly || !hasFourTablePrefill"
            :loading="seeding"
            @click="onPullFromFourTable"
          >
            从四表库带入未审数
          </el-button>
        </el-tooltip>
        <G11ImportExportDropdown :wp-id="wpId" sheet="G11-1" @imported="emit('imported')" />
        <GtReviewTrigger section-id="G11-1-adjudication" />
        <el-button size="small" :loading="adj.aiLoading.value" :disabled="isReadonly" @click="adj.generateAiAnalysis()">🤖 AI</el-button>
      </div>
    </div>

    <GCycleGuideStrip :steps="['G11A 程序', 'G11-1 审定', 'G11-2 明细', 'G11-3 调整', 'G11-4 收益率', '附注披露']" />

    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：确认投资收益的发生真实、金额准确、期间归属恰当，核实权益法/成本法核算及公允价值变动列报正确，为 G11-1 审定表提供审定依据。"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G11-1" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ adj.groupedRows.value.length }} 组</el-tag>
      </div>
    </div>

    <el-alert
      v-if="adj.detailCrossValidation.value"
      type="warning"
      :closable="false"
      class="cross-alert"
    >
      {{ adj.detailCrossValidation.value }}
      <GtIndexChip v-if="jumpToSection" label="G11-2" :prevent-navigate="true" :validate="false" class="warn-chip"
        @click="jumpToSection(resolveG11SheetLabel('G11-2'))" />
    </el-alert>
    <el-alert v-else-if="adj.hasDetailData.value" type="success" :closable="false" class="cross-alert">
      G11-1 与 G11-2 明细汇总一致
    </el-alert>

    <!-- 待归类科目（四表有发生额但科目名对不上 18 行细目 → 交审计师分配，绝不塞「其他」行） -->
    <el-alert
      v-if="unclassifiedLeaves.length"
      type="warning"
      :closable="false"
      class="cross-alert"
    >
      <template #title>
        四表库有 {{ unclassifiedLeaves.length }} 个投资收益子科目无法按科目名归到 18 行细目，请判断归属
        （合计 {{ fmt(unclassifiedTotal) }}）
      </template>
      <ul class="unclassified-list">
        <li v-for="u in unclassifiedLeaves" :key="u.code">
          {{ u.code }} {{ u.name }} — 本期 {{ fmt(u.amount) }}
        </li>
      </ul>
      <div class="unclassified-actions">
        <el-button
          size="small"
          type="warning"
          plain
          :disabled="isReadonly"
          :loading="seeding"
          @click="onFallbackToOther"
        >
          全部归入「{{ G11_FALLBACK_ROW.label }}」行
        </el-button>
        <span class="unclassified-tip">
          源模板 G11-1 第 18 行即「其他」（无「成本法核算的长期股权投资收益」行），
          成本法下的被投资单位分红应列于此；如属其他细目请手工填列。
        </span>
      </div>
    </el-alert>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>科目 6111 投资收益（损益类/贷方），列为本期数与上期数比较，取发生额非余额递推。</p>
        <p>审定数 = 未审数 + 账项调整；|变动率|&gt;20% 时原因分析必填。</p>
        <p>「带入调整」：可从集中登记按科目 6111 拉取调整分录，逐笔分配到各行本期调整，带入后审定数自动更新并联动附注。</p>
      </div>
    </details>

    <div v-for="group in adj.groupedRows.value" :key="group.groupName" class="group-block">
      <div class="group-head" @click="adj.toggleGroup(group.groupName)">
        <span class="group-toggle">{{ group.collapsed ? '▶' : '▼' }}</span>
        <strong>{{ group.groupName }}</strong>
        <span class="group-sub">本期 {{ fmt(group.subtotal.currentAudited) }}</span>
      </div>
      <!-- 四表库取数溯源（口径：本期发生额） -->
      <WpFourTableSourcePanel
        :source-codes="tbSourceCodes"
        gross-label="投资收益"
        fallback-row-code="IS-011"
      />

      <el-table v-show="!group.collapsed" :data="group.rows" border size="small" style="font-size:13px" max-height="420"
        :row-class-name="rowClassName">
        <el-table-column label="项目" prop="label" min-width="200" fixed>
          <template #default="{ row }">
            <GtReviewDot row-prefix="G11-adj" :row-key="row.rowKey" />
            {{ row.label }}
          </template>
        </el-table-column>
        <el-table-column label="本期数" align="center">
          <el-table-column label="未审数" width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.currentUnadjusted" size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'currentUnadjusted', v ?? 0)" />
              <span v-else>{{ fmt(row.currentUnadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="调整" width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.currentAdjustment" size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'currentAdjustment', v ?? 0)" />
              <span v-else>{{ fmt(row.currentAdjustment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定数" width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="审定=未审+调整">{{ fmt(row.currentAudited) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="上期数" align="center">
          <el-table-column label="未审数" width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.priorUnadjusted" size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'priorUnadjusted', v ?? 0)" />
              <span v-else>{{ fmt(row.priorUnadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="调整" width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.priorAdjustment" size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => adj.updateField(row.rowKey, 'priorAdjustment', v ?? 0)" />
              <span v-else>{{ fmt(row.priorAdjustment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定数" width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell">{{ fmt(row.priorAudited) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="变动额" width="96" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.changeAmount) }}</span></template>
        </el-table-column>
        <el-table-column label="变动率" width="80" align="right">
          <template #default="{ row }">
            <span :class="{ 'rate-warn': row.changeRateHighlight }">{{ fmtRate(row.changeRate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="原因分析" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.reasonAnalysis" size="small"
              :class="{ 'reason-required': row.reasonRequired && !row.reasonAnalysis }"
              placeholder="|变动率|>20%时必填"
              @change="(v: string) => adj.updateField(row.rowKey, 'reasonAnalysis', v)" />
            <span v-else>{{ row.reasonAnalysis }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引" width="80">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.indexRef" size="small"
              @change="(v: string) => adj.updateField(row.rowKey, 'indexRef', v)" />
            <GtIndexChip v-else-if="row.indexRef" :value="row.indexRef" />
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-table :data="[adj.totalRow.value]" border size="small" class="total-table" style="font-size:13px">
      <el-table-column label="项目" prop="label" min-width="200" />
      <el-table-column label="本期审定" width="100" align="right">
        <template #default="{ row }"><strong>{{ fmt(row.currentAudited) }}</strong></template>
      </el-table-column>
      <el-table-column label="上期审定" width="100" align="right">
        <template #default="{ row }"><strong>{{ fmt(row.priorAudited) }}</strong></template>
      </el-table-column>
      <el-table-column label="变动额" width="96" align="right">
        <template #default="{ row }">{{ fmt(row.changeAmount) }}</template>
      </el-table-column>
      <el-table-column label="变动率" width="80" align="right">
        <template #default="{ row }"><span :class="{ 'rate-warn': row.changeRateHighlight }">{{ fmtRate(row.changeRate) }}</span></template>
      </el-table-column>
    </el-table>

    <div class="fine-checks" data-testid="g11-fine-checks">
      <el-tag size="small" :type="adj.hasVarianceHighlight.value ? 'danger' : 'success'">G11-CHK-01 试算表勾稽</el-tag>
      <el-tag size="small" :type="adj.detailMismatch.value ? 'warning' : 'success'">G11-CHK-02 明细勾稽</el-tag>
    </div>

    <div class="g11-tb-row">
      <span>试算平衡表数（6111）：</span>
      <el-input-number v-if="!isReadonly" :model-value="adj.trialBalanceAmount.value" size="small" :controls="false"
        style="width:140px" @update:model-value="(v: number) => adj.updateTrialBalance(v ?? 0)" />
      <span v-else>{{ fmt(adj.trialBalanceAmount.value) }}</span>
      <span :class="['variance', { 'is-error': adj.hasVarianceHighlight.value }]">差异：{{ fmt(adj.variance.value) }}</span>
      <el-button size="small" type="primary" :disabled="isReadonly" :loading="publishLoading" @click="onPublish">发布审定数</el-button>
    </div>

    <el-card shadow="never" class="g11-note-card">
      <template #header>审计说明</template>
      <el-input :model-value="adj.auditNote.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly" @update:model-value="adj.updateAuditNote" />
    </el-card>
    <el-card shadow="never" class="g11-note-card">
      <template #header>审计结论</template>
      <el-input :model-value="adj.auditConclusion.value" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }"
        :disabled="isReadonly" @update:model-value="adj.updateAuditConclusion" />
    </el-card>

    <details class="guidance-details guidance-table-block" open>
      <summary>📋 审计程序指引（{{ guidanceRows.length }} 行，只读）</summary>
      <el-table :data="guidanceRows" border size="small" max-height="360" style="font-size:12px;margin-top:8px">
        <el-table-column label="序号" prop="seq" width="56" align="center" />
        <el-table-column label="程序分类" prop="section" width="120" />
        <el-table-column label="审计程序" prop="procedure" min-width="280" show-overflow-tooltip />
        <el-table-column label="索引提示" prop="indexHint" width="88" />
      </el-table>
    </details>

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="6111 投资收益"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, inject, toRef, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import { useG11Adjudication } from '../../composables/useG11Adjudication'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import { useAuditContext } from '@/composables/useAuditContext'
import { dispatchG11OfferDisclosurePull } from '../../composables/g11DisclosureSync'
import {
  G11_ADJUDICATION_ITEMS,
  G11_AUDIT_GUIDANCE_ROWS,
} from '../../composables/g11Constants'
import {
  G11_FALLBACK_ROW,
  G11_SEED_SPEC,
  buildExplicitFallbackCells,
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
import { resolveG11SheetLabel } from '../../composables/g11SheetLabels'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import G11ImportExportDropdown from '../G11ImportExportDropdown.vue'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewDot from '../../GtReviewDot.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GCycleGuideStrip from '../../shared/GCycleGuideStrip.vue'
import WpFourTableSourcePanel from '../../shared/WpFourTableSourcePanel.vue'

const props = defineProps<{
  /** render 下发的本 sheet html_data（含 tb_source_codes） */
  htmlData?: Record<string, any> | null
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()


/**
 * 四表库取数溯源（消费 render 下发的 `tb_source_codes`，消除 dead output）。
 *
 * 科目由后端按**科目名**逐项目解析（`four_table/g_cycle_specs.G11_SPEC`），
 * 取数口径 = 本期发生额。前端单一真源见 `composables/gCycleAccountScope.ts`。
 */
const tbSourceCodes = computed(() => props.htmlData?.tb_source_codes ?? null)
const emit = defineEmits<{ imported: [] }>()

const guidanceRows = G11_AUDIT_GUIDANCE_ROWS

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

const adj = useG11Adjudication({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  debouncedSave: props.debouncedSave,
})

// ─── 从集中登记带入调整（6111 投资收益，损益贷方；带入本期调整，单一调整列） ───
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
  projectId: toRef(props, 'projectId') as any,
  year: useAuditContext().year as any,
  subjectPrefix: '6111',
  direction: 'credit',
  subjectCode: '6111',
  wpCode: 'G11',
  subjectLabel: '投资收益(6111)',
  rows: bringInRows,
  // 单一「调整」列：aje/rje 净额均累加至本期调整（读取实时值做增量累加）
  updateCell: (rowKey: string, _field: any, value: number) => {
    const row = adj.dataRows.value.find((r) => r.rowKey === rowKey)
    const live = row?.currentAdjustment ?? 0
    adj.updateField(rowKey, 'currentAdjustment', Math.round((live + value) * 100) / 100)
  },
  totalAudited: () => adj.totalRow.value.currentAudited,
})

// ─── 从四表库带入未审数（6111 本期发生额，按子科目名归到 18 行细目）─────────
//
// 🔴 口径是**本期发生额贷方单侧**，不是 `debit - credit` —— 含年末结转损益的全年账上
//    借贷两侧恒相等、差额结构性为 0（N4/N5 实证 9 个项目全中）。见后端
//    `g_cycle_specs.G_PL_POSITIVE_SIDE`。
//
// 🔴 归类不命中的叶子**不落「其他」行**：「其他」是源模板真实披露行，把不明投资收益
//    堆进去会让附注失真。未命中一律进上方「待归类」提示条由审计师分配。

const seeding = ref(false)

const fourTablePrefill = computed(() =>
  normalizeGAdjPrefill(props.htmlData?.adjudication_prefill),
)

const seedResult = computed(() => buildGSeedCells(fourTablePrefill.value, {
  ...G11_SEED_SPEC,
  labelOf: (k) => G11_ADJUDICATION_ITEMS.find((d) => d.rowKey === k)?.label ?? k,
}))

const unclassifiedLeaves = computed(() => seedResult.value.unclassified)
const unclassifiedTotal = computed(() =>
  unclassifiedLeaves.value.reduce((s, u) => s + u.amount, 0),
)
const hasFourTablePrefill = computed(() => seedResult.value.cells.length > 0)

const fourTableHint = computed(() =>
  hasFourTablePrefill.value
    ? '把四表库（tb_balance 投资收益叶子科目本期发生额）按子科目名带入对应细目行的本期未审数；已录入的格不覆盖'
    : '四表库暂无可归类的投资收益数据（需先导入余额表；子科目名无法归到 18 行细目时见下方待归类提示）',
)

function readCurrentCell(cell: { rowKey: string; field: string }): number | null {
  const row = adj.dataRows.value.find((r) => r.rowKey === cell.rowKey)
  if (!row) return null
  const v = (row as unknown as Record<string, unknown>)[cell.field]
  return v == null || v === 0 ? null : Number(v)
}

async function onPullFromFourTable(): Promise<void> {
  if (props.isReadonly) return
  const { cells, unclassified, absentSlots } = seedResult.value
  if (!cells.length) {
    ElMessage.info('四表库暂无可归类的投资收益数据可带入')
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
      adj.updateField(w.rowKey, w.field as 'currentUnadjusted', w.amount)
    }
    ElMessage.success(describeAdjPrefillPlan(plan))
  } finally {
    seeding.value = false
  }
}

/**
 * 待归类科目一键归入「其他」行 —— **审计师显式动作**，不是自动兜底。
 *
 * 源模板 `审定表G11-1` R24 逐字「其他」，且 18 行里没有「成本法核算的长期股权投资收益」
 * → 成本法分红的正确落点就是它。但归属仍是判断，故只在审计师点击后写入。
 */
async function onFallbackToOther(): Promise<void> {
  if (props.isReadonly) return
  const pending = unclassifiedLeaves.value
  if (!pending.length) return
  const cells = buildExplicitFallbackCells(pending, G11_FALLBACK_ROW, G11_SEED_SPEC, 'current')
  const plan = planAdjudicationPrefill(cells, readCurrentCell)
  try {
    await ElMessageBox.confirm(
      `将把以下 ${pending.length} 个子科目的本期发生额合计 ${fmt(unclassifiedTotal.value)} `
      + `写入「${G11_FALLBACK_ROW.label}」行的本期未审数：\n`
      + pending.map((u) => `· ${u.code} ${u.name} — ${fmt(u.amount)}`).join('\n')
      + '\n\n若其中有科目实际属于其他细目行，请取消后手工填列。',
      `归入「${G11_FALLBACK_ROW.label}」行`,
      { confirmButtonText: '确认归入', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  seeding.value = true
  try {
    // 显式动作 → 覆盖既有值（审计师已在确认框看到金额）
    for (const w of resolveAdjPrefillWrites(plan, 'overwrite')) {
      adj.updateField(w.rowKey, w.field as 'currentUnadjusted', w.amount)
    }
    ElMessage.success(`已归入「${G11_FALLBACK_ROW.label}」行 ${fmt(unclassifiedTotal.value)}`)
  } finally {
    seeding.value = false
  }
}

const publishLoading = ref(false)

async function onPublish(): Promise<void> {
  if (props.isReadonly) return
  publishLoading.value = true
  try {
    const ok = await adj.validateWithBackend()
    if (!ok) ElMessage.warning('公式校验未通过，请检查审定表与明细表')
    adj.publishAdjudicated()
    await adj.saveAdjudicationToBackend()
    ElMessage.success('审定数已发布')
    dispatchG11OfferDisclosurePull('G11-1')
  } finally {
    publishLoading.value = false
  }
}

function rowClassName({ row }: { row: { changeRateHighlight: boolean; reasonRequired: boolean; reasonAnalysis: string } }): string {
  if (row.changeRateHighlight) return 'g11-row-warn'
  return ''
}

function fmt(v: number | null | undefined): string {
  if (v == null) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(rate: number | null): string {
  if (rate === null) return 'N/A'
  return (rate * 100).toFixed(1) + '%'
}
</script>

<style scoped>
.g11-adjudication { font-size: var(--wp-font-size, 13px); }
.g11-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.g11-title { margin: 0; font-size: 15px; }
.g11-actions { display: flex; gap: 8px; }
.objective-alert { margin-bottom: 8px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.cross-alert { margin-bottom: 8px; }
.unclassified-list { margin: 6px 0 0; padding-left: 18px; line-height: 1.6; font-size: 12px; }
.unclassified-actions { margin-top: 8px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.unclassified-tip { font-size: 12px; color: #909399; line-height: 1.5; }
.guidance-details { margin-bottom: 8px; font-size: 12px; color: #606266; }
.group-block { margin-bottom: 8px; }
.group-head { display: flex; align-items: center; gap: 8px; padding: 6px 10px; background: #f5f7fa; cursor: pointer; border-radius: 4px; }
.group-sub { margin-left: auto; font-size: 12px; color: #909399; }
.formula-cell { border-bottom: 1px dashed #999; cursor: help; }
.rate-warn { color: #e6a23c; font-weight: 600; }
.reason-required :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px #e6a23c inset; }
.g11-tb-row { display: flex; align-items: center; gap: 12px; margin: 12px 0; flex-wrap: wrap; }
.fine-checks { display: flex; gap: 8px; flex-wrap: wrap; margin: 8px 0; }
.variance.is-error { color: #f56c6c; font-weight: 600; }
.g11-note-card { margin-top: 8px; }
.total-table { margin-top: 4px; }
:deep(.g11-row-warn) { background-color: #fdf6ec !important; }
</style>
