<template>
  <div class="g6-adjudication" data-testid="g6-adjudication">
    <div class="section-head">
      <h3 class="sheet-title">G6-1 其他债权投资审定表</h3>
      <div class="head-actions tab-toolbar">
        <el-button size="small" type="primary" plain :loading="adjPull.loading.value" @click="openBringInAdjustment">
          <el-icon><Download /></el-icon>带入调整
        </el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:G6-1" :context-project-id="props.projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G6-2" :context-project-id="props.projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G6-3" :context-project-id="props.projectId" /></span>
        <el-button size="small" @click="openReviewDialog('G6-1-adjudication')">💬复核</el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计目标：确认其他债权投资(FVOCI-Debt)公允价值与摊余成本审定余额准确完整，减值(ECL)计量恰当，账面价值合计与试算表科目1503勾稽一致。"
      style="margin-bottom: 12px"
    />

    <el-alert
      v-if="classificationSummary"
      :type="classificationAlertType"
      :closable="false"
      show-icon
      style="margin-bottom: 12px"
      :title="classificationBannerTitle"
    >
      <template #default>
        <span>{{ classificationSummary.message }}</span>
        <ul
          v-if="classificationSummary.instruments?.length"
          class="instrument-matrix"
        >
          <li
            v-for="row in classificationSummary.instruments"
            :key="row.instrumentId || row.instrumentName"
          >
            {{ row.instrumentName || row.instrumentId }}：
            SPPI {{ row.sppiOverall === 'pass' ? '通过' : row.sppiOverall === 'fail' ? '未通过' : '未完成' }}
            → {{ row.expectedClassification || '未定' }}
            <template v-if="row.accountConflict">（科目冲突）</template>
          </li>
        </ul>
      </template>
    </el-alert>

    <div class="methodology-context">
      <p class="methodology-title">FVOCI-Debt 计量与本表结构：</p>
      <p>① 一、公允价值 — 报表列示口径（与附注/资产负债表衔接）</p>
      <p>② 二、摊余成本 — 投资成本+利息调整→账面余额；减值按摊余成本口径计提；账面价值=账面余额−减值</p>
      <p>③ 「单项/按组合计提坏账准备」在成本/利息层表示按 ECL 评估方式归类的余额，减值金额仅填在（四）减值准备</p>
      <p>④ 差异数 = 其他债权投资账面价值合计 − 试算平衡表数（应为 0）</p>
    </div>

    <details class="prep-hint">
      <summary>📋 编制提示（如何编制）</summary>
      <ul>
        <li><b>编制顺序</b>：先完成 G6-2 明细与 G6-4 调整（或确认无调整）→ 本表汇总审定 → 再勾稽试算与附注。</li>
        <li><b>取数来源</b>：未审数来自科目余额表/明细汇总；账项调整来自 G6-4 回写（按 150301/302/303/304/305 分流）；明细勾稽看 G6-2，减值看 G6-3/G6-12。</li>
        <li><b>三层结构</b>：①公允价值（报表列示）②摊余成本（成本+利息调整→账面余额；减值在（四））③账面价值=账面余额−减值。</li>
        <li>审定＝未审＋账项调整；|变动率|&gt;30% 时「原因分析」必填。</li>
        <li>账面余额叶子＝成本审定＋利息调整审定；账面价值叶子＝账面余额审定−减值审定（自动计算，勿手改公式列）。</li>
        <li>一年内到期：成本一年内＋利息一年内；账面价值一年内到期＝账面一年内−减值一年内；与 G6-2 到期分类一致。</li>
        <li>差异数（账面价值合计 − 试算 1503）应为 0；非零时先查 G6-4 是否已回写、G6-2/G6-3 是否已同步。</li>
        <li>分类结论关注顶部 G6-7/G6-8 回写摘要；非 FVOCI-Debt 预期分类时须在说明中评价影响。</li>
        <li>「带入调整」：可从集中登记按科目 1503 拉取调整分录，逐笔分配到各成本/利息调整/减值明细行的期末账项调整，带入后审定数自动更新并联动附注。</li>
      </ul>
    </details>

    <el-table
      :data="adj.rows.value"
      border
      size="small"
      :row-class-name="rowClassName"
      :max-height="620"
      style="width: 100%"
    >
      <el-table-column label="项目" min-width="260" fixed>
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
            <span v-else :class="{ 'formula-cell': isFormulaRow(row) }">{{ fmt(row.openingUnadjusted) }}</span>
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
            v-if="row.editable && !isReadonly && (row.kind === 'leaf' || row.kind === 'one_year_deduct')"
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

    <!-- 审计说明：公允价值变动率摘要（对齐 Excel R64） -->
    <div class="fv-summary">
      <span>其他债权投资公允价值本期较上期变动：</span>
      <strong :class="{ 'rate-orange': isFvRateWarning }">{{ fmtRate(adj.fvChangeRate.value) }}</strong>
      <span v-if="isFvRateWarning" class="fv-hint">（超过 30%，请在审计说明中分析原因）</span>
    </div>

    <G6AuditTextCards
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
        公允价值合计变动率: adj.fvChangeRate.value,
      }"
      note-placeholder="对其他债权投资审定表的审计说明…"
      note-hint="覆盖公允价值/摊余成本审定、一年内到期重分类、减值与试算勾稽；变动率>30%须说明原因。"
      conclusion-placeholder="审计结论…"
      conclusion-hint="按 A/B/C 口径评价科目 1503 审定结果。"
    />

    <details class="guidance-details">
      <summary>编制说明【非打印内容】— 列报与准则口径</summary>
      <div class="guidance-content">
        <p>1. 「其他债权投资」项目，反映资产负债表日企业分类为以公允价值计量且其变动计入其他综合收益的长期债权投资的期末账面价值。</p>
        <p>2. 自资产负债表日起一年内到期的长期债权投资的期末账面价值，在「一年内到期的非流动资产」项目反映。</p>
        <p>3. 企业购入的以公允价值计量且其变动计入其他综合收益的一年内到期的债权投资的期末账面价值，在「其他流动资产」项目反映。</p>
        <p>4. 操作路径提示：G6-2 提供明细与一年内到期拆分；G6-3/G6-12 提供减值；G6-4「保存并回写」后刷新本表账项调整列；附注表从本表审定带入。</p>
      </div>
    </details>

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="1503 其他债权投资"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * G6TabAdjudication.vue — 对齐 Excel《审定表G6-1》列/行结构
 *
 * 相对源模板的改进：
 * - 去掉组合下无名空行；账面余额/账面价值及对应一年内到期公式自动勾稽
 * - 澄清「单项/组合」在成本层为 ECL 归类标签，减值仅填（四）
 * - 变动率阈值 30%；试算差异嵌在表内（与 G4 一致）
 */
import { ref, computed, toRef, inject, watch } from 'vue'
import { Download } from '@element-plus/icons-vue'
import { useG6MainAdjudication } from '../../composables/useG6MainAdjudication'
import type { G6AdjudicationRow } from '../../composables/useG6MainAdjudication'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import { useAuditContext } from '@/composables/useAuditContext'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import { G6_CHANGE_RATE_THRESHOLD } from '../../composables/g6AdjudicationItems'
import {
  G6_CLASSIFICATION_SUMMARY_KEY,
  parseG6ClassificationSummary,
} from '../../composables/g6CrossHelpers'
import GtIndexChip from '../../GtIndexChip.vue'
import G6AuditTextCards from '../G6AuditTextCards.vue'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses?: Map<string, ChecklistResponse>
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const isReadonly = computed(() => props.isReadonly)

const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
watch(
  () => props.allResponses,
  (source) => {
    if (!source) return
    allResponses.value = source
  },
  { immediate: true, deep: true },
)

const adj = useG6MainAdjudication({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses,
  isReadonly,
  htmlData: toRef(props, 'htmlData'),
})

// ─── 从集中登记带入调整（1503 其他债权投资，资产借方；带入期末账项调整，单列合并 AJE/RJE） ───
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
  subjectPrefix: '1503',
  direction: 'debit',
  subjectCode: '1503',
  wpCode: 'G6',
  subjectLabel: '其他债权投资(1503)',
  rows: bringInRows,
  updateCell: (rowKey: string, _field: any, value: number) =>
    adj.updateCell(rowKey, 'closingAdjustment', value),
  totalAudited: () => adj.carryingNetRow.value?.closingAudited ?? 0,
})

const classificationSummary = computed(() =>
  parseG6ClassificationSummary(allResponses.value.get(G6_CLASSIFICATION_SUMMARY_KEY)),
)

const classificationAlertType = computed(() => {
  if (classificationSummary.value?.accountConflict || classificationSummary.value?.level === 'warning') {
    return 'warning'
  }
  if (classificationSummary.value?.level === 'ok') return 'success'
  return 'info'
})

const classificationBannerTitle = computed(() => {
  const s = classificationSummary.value
  if (!s) return ''
  const cls = s.expectedClassification || '未定'
  const conflict = s.accountConflict ? ' · 与「其他债权投资」科目定位可能冲突' : ''
  return `G6-7×G6-8 分类摘要：${cls}${conflict}`
})

const isFvRateWarning = computed(() => {
  const r = adj.fvChangeRate.value
  return r != null && Math.abs(r) > G6_CHANGE_RATE_THRESHOLD
})

function isFormulaRow(row: G6AdjudicationRow): boolean {
  return (
    row.kind === 'subtotal' ||
    row.kind === 'section_net' ||
    row.kind === 'footer' ||
    (row.kind === 'leaf' && (row.section === 'book' || row.section === 'carrying')) ||
    (row.kind === 'one_year_deduct' && (row.section === 'book' || row.section === 'carrying'))
  )
}

function rowClassName({ row }: { row: G6AdjudicationRow }): string {
  if (row.kind === 'section_header') return 'row-section'
  if (row.kind === 'subsection_header') return 'row-subsection'
  if (row.kind === 'subtotal' || row.kind === 'section_net') return 'row-subtotal'
  if (row.kind === 'footer') return 'row-footer'
  return ''
}

function fmt(v: number | null | undefined): string {
  if (v == null) return ''
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function fmtRate(v: number | null | undefined): string {
  if (v == null) return '-'
  return (v * 100).toFixed(2) + '%'
}
</script>

<style scoped>
.g6-adjudication { padding: 12px; font-size: var(--wp-font-size, 13px); }

.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 12px 16px;
  margin-bottom: 12px;
  border-radius: 0 4px 4px 0;
  font-size: 12px;
  line-height: 1.8;
  color: #92400e;
}
.methodology-title { font-weight: 600; margin: 0 0 4px 0; color: #78350f; }
.methodology-context p { margin: 2px 0; }
.instrument-matrix {
  margin: 8px 0 0;
  padding-left: 18px;
  font-size: 12px;
  line-height: 1.6;
}

.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; }

.prep-hint {
  margin-bottom: 12px; padding: 8px 12px;
  background: #fafafa; border: 1px solid #ebeef5; border-radius: 4px;
  font-size: 12px; color: #606266;
}
.prep-hint summary { cursor: pointer; font-weight: 500; color: #303133; }
.prep-hint ul { margin: 6px 0 0; padding-left: 18px; }
.prep-hint li { margin: 2px 0; }

.label-strong { font-weight: 700; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.rate-orange { color: #e6a23c; font-weight: 600; }
.diff-red { color: #f56c6c; font-weight: 700; }

:deep(.reason-required .el-input__wrapper) {
  box-shadow: 0 0 0 1px #e6a23c inset;
}
:deep(.row-section) { background: #ecf5ff !important; font-weight: 700; }
:deep(.row-subsection) { background: #f5f7fa !important; font-weight: 600; }
:deep(.row-subtotal) { background: #f0f9eb !important; font-weight: 700; }
:deep(.row-footer) { background: #fdf6ec !important; font-weight: 600; }

.fv-summary {
  margin: 14px 0 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
}
.fv-hint { color: #e6a23c; font-size: 12px; }

.guidance-details {
  margin-top: 12px; padding: 8px 12px;
  background: #fafafa; border: 1px solid #ebeef5;
  border-radius: 4px; font-size: 12px; color: #606266;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #303133; }
.guidance-content p { margin: 4px 0; }
</style>
