<template>
  <div class="g5-adjudication" data-testid="g5-adjudication">
    <div class="section-head">
      <h3 class="sheet-title">G5-1 长期应收款审定表</h3>
      <div class="head-actions tab-toolbar">
        <el-button size="small" type="primary" plain :loading="adjPull.loading.value" @click="openBringInAdjustment">
          <el-icon><Download /></el-icon>带入调整
        </el-button>
        <GtIndexChip value="wp:G5-1" />
        <G5ImportExportDropdown
          :wp-id="props.wpId"
          sheet="G5-1"
          :disabled="!!props.readonly"
          @imported="onImported"
        />
        <el-button size="small" :disabled="!!props.readonly" :loading="syncing" @click="onSyncSupporting">
          从 G5-2/G5-3 汇总未审
        </el-button>
        <el-button size="small" :disabled="!!props.readonly" :loading="tbLoading" @click="onFetchTb">
          取试算 1531
        </el-button>
        <el-tag size="small" :type="Math.abs(adjudication.variance.value) > 0.01 ? 'danger' : 'success'">
          差异 {{ fmtAmount(adjudication.variance.value) }}
        </el-tag>
        <el-tag size="small" type="info">
          TB 1531 {{ fmtAmount(adjudication.tbValues.value.closing) }}
        </el-tag>
        <GtReviewTrigger section-id="g5-1-adjudication" />
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      审计目标：核实长期应收款余额、坏账准备及净额的存在、完整与准确；确认单项/组合划分恰当；扣除一年内到期后与试算 1531 勾稽，为报表列报及附注提供审定依据。
    </el-alert>

    <div v-if="Math.abs(adjudication.variance.value) > 0.01" class="variance-alert">
      <el-alert type="error" :closable="false">
        试算表差异：{{ fmtAmount(adjudication.variance.value) }}（净额审定 − 试算平衡表数），请分析或补调整。
      </el-alert>
    </div>

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>结构对齐致同模板：（一）余额 →（二）坏账准备 →（三）净额＝一年以上余额−一年以上坏账。</li>
        <li>余额/坏账按「单项计提 / 业务类型组合 / 客户类型组合」展开；小计自动汇总；「减：1年内到期」后得报表列示数。</li>
        <li>审定＝未审数＋账项调整＋重分类调整；变动额/变动率自动算；|变动率|&gt;{{ Math.round(G5_CHANGE_RATE_THRESHOLD * 100) }}% 时原因分析必填。</li>
        <li>「从 G5-2/G5-3 汇总未审」：原值按业务类型归集；一年内优先用 G5-2「1年内到期」勾选；坏账按单项/组合细分归集。</li>
        <li>G5-4「确认调整」后，净 AJE/RJE 回写至「业务类型组合」期末调整列；审定净额自动回写试算 1531。</li>
        <li>可「取试算 1531」拉取核对参考；导入导出按行键 round-trip。</li>
        <li>「带入调整」：可从集中登记按科目 1531 拉取调整分录，逐笔分配到各余额/坏账明细行的期末账项/重分类调整，带入后审定净额自动更新并联动附注。</li>
      </ul>
    </details>

    <el-table
      :data="adjudication.rows.value"
      :height="560"
      border
      stripe
      size="small"
      style="width: 100%; font-size: 13px"
      :row-class-name="rowClassName"
    >
      <el-table-column label="项目" min-width="260" fixed>
        <template #default="{ row }">
          <span
            :style="{ paddingLeft: `${(row.indent || 0) * 14}px` }"
            :class="{
              'label-strong': row.kind !== 'leaf' && row.kind !== 'deduction',
              'label-combo': row.kind === 'group_header' || row.methodKey?.startsWith('collective'),
            }"
          >
            {{ row.label }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="期初数" align="center">
        <el-table-column label="未审数" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !props.readonly && row.kind !== 'tb_amount'"
              :model-value="row.openingUnadjusted"
              size="small"
              :controls="false"
              @update:model-value="(v: number) => adjudication.updateField(row.rowKey, 'openingUnadjusted', v ?? 0)"
            />
            <span v-else :class="{ 'formula-cell': !row.editable }">{{ fmtAmount(row.openingUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账项调整" min-width="90" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !props.readonly && row.kind !== 'tb_amount'"
              :model-value="row.openingAJE"
              size="small"
              :controls="false"
              @update:model-value="(v: number) => adjudication.updateField(row.rowKey, 'openingAJE', v ?? 0)"
            />
            <span v-else :class="{ 'formula-cell': !row.editable }">{{ fmtAmount(row.openingAJE) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="重分类调整" min-width="90" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !props.readonly && row.kind !== 'tb_amount'"
              :model-value="row.openingRJE"
              size="small"
              :controls="false"
              @update:model-value="(v: number) => adjudication.updateField(row.rowKey, 'openingRJE', v ?? 0)"
            />
            <span v-else :class="{ 'formula-cell': !row.editable }">{{ fmtAmount(row.openingRJE) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="未审+账项调整+重分类调整">{{ fmtAmount(row.openingAdjusted) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="期末数" align="center">
        <el-table-column label="未审数" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !props.readonly"
              :model-value="row.closingUnadjusted"
              size="small"
              :controls="false"
              @update:model-value="(v: number) => adjudication.updateField(row.rowKey, 'closingUnadjusted', v ?? 0)"
            />
            <span v-else :class="{ 'formula-cell': !row.editable }">{{ fmtAmount(row.closingUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账项调整" min-width="90" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !props.readonly && row.kind !== 'tb_amount'"
              :model-value="row.closingAJE"
              size="small"
              :controls="false"
              @update:model-value="(v: number) => adjudication.updateField(row.rowKey, 'closingAJE', v ?? 0)"
            />
            <span v-else :class="{ 'formula-cell': !row.editable }">{{ fmtAmount(row.closingAJE) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="重分类调整" min-width="90" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !props.readonly && row.kind !== 'tb_amount'"
              :model-value="row.closingRJE"
              size="small"
              :controls="false"
              @update:model-value="(v: number) => adjudication.updateField(row.rowKey, 'closingRJE', v ?? 0)"
            />
            <span v-else :class="{ 'formula-cell': !row.editable }">{{ fmtAmount(row.closingRJE) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="100" align="right">
          <template #default="{ row }">
            <span
              class="formula-cell"
              :class="{ 'diff-warn': row.rowKey === 'tb-diff' && Math.abs(row.closingAdjusted) > 0.01 }"
              title="未审+账项调整+重分类调整"
            >{{ fmtAmount(row.closingAdjusted) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="本期与上期审定数比较" align="center">
        <el-table-column label="变动额" min-width="90" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="期末审定−期初审定">{{ fmtAmount(row.changeAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" min-width="80" align="right">
          <template #default="{ row }">
            <span
              :class="{ 'rate-warning': adjudication.needsReason(row) }"
              class="formula-cell"
              title="(期末−期初)/期初"
            >
              {{ row.changeRate !== null ? (row.changeRate * 100).toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="原因分析" min-width="140">
        <template #default="{ row }">
          <el-input
            v-if="adjudication.needsReason(row) || (row.editable && row.kind === 'leaf')"
            :model-value="row.reasonAnalysis"
            size="small"
            :placeholder="adjudication.needsReason(row) ? '必填（变动率>30%）' : ''"
            :disabled="props.readonly"
            @update:model-value="(v: string) => adjudication.updateField(row.rowKey, 'reasonAnalysis', v)"
          />
          <span v-else>{{ row.reasonAnalysis || '-' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <G5AuditTextCards
      :wp-id="props.wpId"
      :is-readonly="!!props.readonly"
      :note="auditNote"
      :conclusion="auditConclusion"
      note-ai-section="adjudication-note"
      conclusion-ai-section="adjudication-conclusion"
      note-placeholder="填写审计说明：（1）变动比例超过30%的原因分析；（2）其他情况说明。"
      note-hint="覆盖期初/期末审定、一年内到期扣除、净值与试算勾稽及重大变动原因。"
      :related-context="{ 试算表差异: adjudication.variance.value }"
      @update:note="saveAuditNote"
      @update:conclusion="saveAuditConclusion"
    />

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="1531 长期应收款"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import {
  useG5Adjudication,
  G5_CHANGE_RATE_THRESHOLD,
  type G5AdjudicationRow,
} from '../../composables/useG5Adjudication'
import { useAuditContext } from '@/composables/useAuditContext'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import { useInjectedG5FormData } from '../../composables/useG5LonRecFormData'
import {
  aggregateGrossFromG52,
  aggregateProvisionFromG53,
  parseRowsRemark,
} from '../../composables/g5CrossHelpers'
import { G5_ITEM_IDS } from '../../composables/g5StorageContract'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import G5AuditTextCards from '../G5AuditTextCards.vue'
import G5ImportExportDropdown from '../G5ImportExportDropdown.vue'

const props = defineProps<{
  htmlData?: any
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const g5Notes = useInjectedG5FormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })
const readonlyRef = computed(() => !!props.readonly)
const htmlDataRef = toRef(props, 'htmlData')
const syncing = ref(false)
const tbLoading = ref(false)
const emit = defineEmits<{ imported: [] }>()

const adjudication = useG5Adjudication({
  wpId: props.wpId,
  projectId: props.projectId,
  htmlData: htmlDataRef,
  isReadonly: readonlyRef,
  allResponses: g5Notes.allResponses,
  debouncedSave: g5Notes.debouncedSave,
})

// ─── 从集中登记带入调整（1531 长期应收款，资产借方；带入期末 AJE/RJE） ────────────
const bringInRows = computed(() =>
  adjudication.rows.value
    .filter((r) => r.editable && r.kind === 'leaf')
    .map((r) => ({ rowKey: r.rowKey, name: r.label, aje: r.closingAJE, rje: r.closingRJE })),
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
  subjectPrefix: '1531',
  direction: 'debit',
  subjectCode: '1531',
  wpCode: 'G5',
  subjectLabel: '长期应收款(1531)',
  rows: bringInRows,
  updateCell: (rowKey: string, field: any, value: number) =>
    adjudication.updateField(rowKey, field === 'rje' ? 'closingRJE' : 'closingAJE', value),
  totalAudited: () => adjudication.adjudicatedAmount.value,
})

const auditNote = ref('')
const auditConclusion = ref('')
const G5_NOTE_KEY = 'G5-1-audit-note'
const G5_CONCLUSION_KEY = 'G5-1-audit-conclusion'

function saveAuditNote(val: string): void {
  if (props.readonly) return
  auditNote.value = val
  void g5Notes.saveImmediate(G5_NOTE_KEY, { conclusion: null, remark: val })
}
function saveAuditConclusion(val: string): void {
  if (props.readonly) return
  auditConclusion.value = val
  void g5Notes.saveImmediate(G5_CONCLUSION_KEY, { conclusion: null, remark: val })
}

async function onFetchTb(): Promise<void> {
  if (props.readonly) return
  tbLoading.value = true
  try {
    const amt = await adjudication.fetchTrialBalance(props.projectId)
    if (amt == null) ElMessage.warning('未取到试算 1531，请确认项目已导入试算')
    else ElMessage.success(`已取试算 1531：${amt.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`)
  } finally {
    tbLoading.value = false
  }
}

async function onSyncSupporting(): Promise<void> {
  if (props.readonly) return
  syncing.value = true
  try {
    await g5Notes.loadAll()
    const detailList = parseRowsRemark(g5Notes.allResponses.value.get(G5_ITEM_IDS.G5_2_ROWS))
    const badList = parseRowsRemark(g5Notes.allResponses.value.get(G5_ITEM_IDS.G5_3_ROWS))

    if (!detailList.length && !badList.length) {
      ElMessage.warning('未找到 G5-2 / G5-3 数据，请先编制明细与坏账表')
      return
    }

    const gross = aggregateGrossFromG52(detailList)
    const provision = aggregateProvisionFromG53(badList, gross.oneYearDebtors)

    adjudication.applyFromDetailTotals({
      individualGross: gross.individualClosing,
      businessGross: gross.businessClosing,
      customerGross: gross.customerClosing,
      individualProvision: provision.individualClosing,
      businessProvision: provision.businessClosing,
      customerProvision: provision.customerClosing,
      oneYearGross: gross.oneYearClosing,
      oneYearProvision: provision.oneYearClosing,
    })
    if (adjudication.tbValues.value.closing) {
      adjudication.updateField('tb-amount', 'closingUnadjusted', adjudication.tbValues.value.closing)
      adjudication.updateField('tb-amount', 'openingUnadjusted', adjudication.tbValues.value.opening)
    }
    ElMessage.success(
      `已汇总：明细 ${detailList.length} 行 / 坏账 ${badList.length} 行` +
      (gross.oneYearClosing ? `；一年内 ${gross.oneYearClosing.toLocaleString('zh-CN')}` : ''),
    )
    if (provision.unmatchedOneYearDebtors?.length) {
      const sample = provision.unmatchedOneYearDebtors.slice(0, 3).join('、')
      const more = provision.unmatchedOneYearDebtors.length > 3
        ? ` 等 ${provision.unmatchedOneYearDebtors.length} 户`
        : ''
      ElMessage.warning(
        `一年内到期债务人在 G5-3 未匹配：${sample}${more}（请核对债务人名称是否一致）`,
      )
    }
  } finally {
    syncing.value = false
  }
}

async function onImported(): Promise<void> {
  try { await g5Notes.loadAll() } catch { /* ignore */ }
  adjudication.hydrateFromStore()
  emit('imported')
}

onMounted(async () => {
  try { await g5Notes.loadAll() } catch { /* ignore */ }
  adjudication.hydrateFromStore()
  const n = g5Notes.allResponses.value.get(G5_NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = g5Notes.allResponses.value.get(G5_CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

function fmtAmount(v: number | null | undefined): string {
  if (v === null || v === undefined) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function rowClassName({ row }: { row: G5AdjudicationRow }) {
  if (row.kind === 'section_header' || row.kind === 'net_row') return 'row-section'
  if (row.kind === 'section_subtotal' || row.kind === 'reportable') return 'row-total'
  if (row.kind === 'tb_diff' && Math.abs(row.closingAdjusted) > 0.01) return 'row-diff'
  if (row.kind === 'tb_amount' || row.kind === 'tb_diff') return 'row-tb'
  if (adjudication.needsReason(row) && !row.reasonAnalysis) return 'row-warning'
  if (row.kind === 'group_header') return 'row-group'
  return ''
}
</script>

<style scoped>
.g5-adjudication { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.variance-alert { margin-bottom: 8px; }
.audit-objective { margin-bottom: 8px; }
.prep-hint { margin: 0 0 10px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; font-weight: 500; }
.prep-hint ul { margin: 6px 0 0; padding-left: 18px; line-height: 1.8; }
.formula-cell {
  border-bottom: 1px dashed #999;
  cursor: help;
}
.rate-warning {
  color: #e6a23c;
  font-weight: 600;
}
.diff-warn { color: #f56c6c; font-weight: 600; }
.label-strong { font-weight: 600; }
.label-combo { color: #c45656; }
:deep(.row-warning) { background-color: #fdf6ec !important; }
:deep(.row-total) { background-color: #f0f9eb !important; font-weight: 600; }
:deep(.row-section) { background-color: #ecf5ff !important; font-weight: 600; }
:deep(.row-group) { background-color: #fafafa !important; color: #c45656; }
:deep(.row-tb) { background-color: #f4f4f5 !important; }
:deep(.row-diff) { background-color: #fef0f0 !important; }
:deep(.el-input-number) { width: 100%; }
:deep(.el-input-number .el-input__inner) { text-align: right; }
</style>
