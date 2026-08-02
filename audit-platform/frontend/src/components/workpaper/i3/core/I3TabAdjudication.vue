<!--
  I3TabAdjudication.vue — I3-1 商誉审定表

  对齐致同 Excel：未审 → 账项调整 → 审定；自 I3-2 带入；与 TB/明细勾稽
-->
<template>
  <div class="i3-adjudication">
    <div class="section-header">
      <span class="section-title">I3-1 商誉审定表</span>
      <div class="section-actions">
        <el-button size="small" type="default" text @click="handleReview">复核</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>审计目标</template>
      确认商誉(1711)期末余额真实、完整、计价准确；商誉不摊销，本期变动仅来自新并购（增加）与减值（减少）；
      审定数＝未审数＋AJE＋RJE，与试算平衡表勾稽一致（CAS8、CAS20）。
    </el-alert>

    <div class="methodology-context">
      <p>
        <b>编制逻辑（对齐 Excel I3-1）：</b>
        明细取数(I3-2) → 未审数(期初/增/减/期末) → 账项调整(I3-3) → 审定数；
        期末＝期初＋新并购−减值（不摊销）；净额＝原值−累计减值。检查比例类除零显示 N/A。
        减值迹象与 CGU 深度程序见 I3-6~I3-8。
      </p>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-right">
        <GtIndexChip value="wp:I3-1" :context-project-id="projectId" />
        <el-tag size="small" type="info">{{ rows.length }} 个单位</el-tag>
        <el-tag size="small" type="success">审定 {{ fmtAmount(subtotals.audited) }}</el-tag>
        <el-tag size="small" :type="Math.abs(tbDiff) > 0.01 ? 'danger' : 'success'">
          {{ Math.abs(tbDiff) > 0.01 ? `TB差异 ${fmtAmount(tbDiff)}` : '✓ TB一致' }}
        </el-tag>
        <el-tag v-if="crossCheck.hasWarning" size="small" type="warning">与明细勾稽差异</el-tag>
        <el-button size="small" @click="navigateTo('I3-2')">I3-2 →</el-button>
        <el-button size="small" @click="navigateTo('I3-3')">I3-3 →</el-button>
      </div>
    </div>

    <WpFourTableSourcePanel
      :source-codes="tbSourceCodes"
      :gross-label="sourceConfig.grossLabel"
      :provision-label="sourceConfig.provisionLabel"
      :fallback-row-code="sourceConfig.fallbackRowCode"
      :hints="sourceConfig.hints"
    />

    <el-alert
      v-for="w in newAcquisitionWarnings"
      :key="'acq-' + w.rowId"
      type="warning"
      :title="w.message"
      show-icon
      :closable="false"
      class="adj-warning"
    />
    <el-alert
      v-for="w in impairmentReversalWarnings"
      :key="'rev-' + w.rowId"
      type="error"
      :title="w.message"
      show-icon
      :closable="false"
      class="adj-warning"
    />
    <el-alert
      v-for="w in endVsNetWarnings"
      :key="'net-' + w.rowId"
      type="warning"
      :title="w.message"
      show-icon
      :closable="false"
      class="adj-warning"
    />
    <el-alert
      v-if="crossCheck.hasWarning"
      type="warning"
      :closable="false"
      show-icon
      class="adj-warning"
      :title="`与 I3-2 勾稽：原值差 ${fmtAmount(crossCheck.originalDiff)} / 净值差 ${fmtAmount(crossCheck.netDiff)} / 本期减值差 ${fmtAmount(crossCheck.impairmentDiff)} / 期末≠净额 ${fmtAmount(crossCheck.endVsNetDiff)}`"
    />

    <el-alert
      v-if="hasAjeApprox"
      type="warning"
      :closable="false"
      show-icon
      class="adj-warning"
      title="系统近似分摊：部分 AJE/RJE 按未审占比分摊自 I3-3，请按被投资单位人工复核后改数（改后自动清除「近似」标记）"
    />
    <el-alert
      v-if="unspecifiedAdjCount > 0"
      type="warning"
      :closable="false"
      show-icon
      class="adj-warning"
      :title="`I3-3 有 ${unspecifiedAdjCount} 笔商誉分录未填被投资单位，同步时将比例分摊。请先在 I3-3 补全后再点「从 I3-3 同步调整」。`"
    />

    <el-card shadow="never" class="layer-card">
      <template #header>
        <span class="block-title">原值 / 减值准备 / 净值（只读汇总，对齐 Excel 三层）</span>
      </template>
      <el-table :data="layerRows" border size="small" class="layer-table">
        <el-table-column prop="layer" label="项目类别" min-width="100" />
        <el-table-column prop="begin" label="期初" min-width="100" align="right">
          <template #default="{ row }">{{ fmtAmount(row.begin) }}</template>
        </el-table-column>
        <el-table-column prop="increase" label="本期增加" min-width="100" align="right">
          <template #default="{ row }">{{ fmtAmount(row.increase) }}</template>
        </el-table-column>
        <el-table-column prop="decrease" label="本期减少" min-width="100" align="right">
          <template #default="{ row }">{{ fmtAmount(row.decrease) }}</template>
        </el-table-column>
        <el-table-column prop="end" label="期末" min-width="100" align="right">
          <template #default="{ row }">{{ fmtAmount(row.end) }}</template>
        </el-table-column>
        <el-table-column prop="audited" label="审定" min-width="100" align="right">
          <template #default="{ row }">{{ fmtAmount(row.audited) }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <div class="action-bar">
      <el-button size="small" type="primary" plain :loading="adjPull.loading.value" @click="openBringInAdjustment">
        <el-icon><Download /></el-icon>带入调整
      </el-button>
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleSeedI32">从 I3-2 带入</el-button>
      <el-button size="small" plain :disabled="isReadonly" @click="handleSyncI33">从 I3-3 同步调整</el-button>
      <el-button size="small" plain :disabled="isReadonly" @click="handleSyncI36">从 I3-6 同步减值</el-button>
      <el-button size="small" plain :disabled="isReadonly" @click="handleApplyTb">TB写入未审</el-button>
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="addRow">+ 新增</el-button>
      <I3SheetImportExport
        v-if="!isReadonly"
        sheet="I3-1"
        :wp-id="wpId"
        :project-id="projectId"
      />
      <el-button size="small" type="success" :disabled="isReadonly" @click="handleSave">保存并回写</el-button>
    </div>

    <div class="table-section">
      <el-table
        :data="rows"
        border
        size="small"
        :row-class-name="getRowClassName"
        class="adjudication-table"
        show-summary
        :summary-method="getSummaryMethod"
        max-height="520"
      >
        <el-table-column prop="investee" label="被投资单位 / 项目" min-width="140" fixed>
          <template #default="{ row }">
            <span>{{ row.investee }}</span>
            <el-tag v-if="row.fromDetail" size="small" type="info" class="src-tag">I3-2</el-tag>
            <el-tag v-if="row.ajeApprox" size="small" type="warning" class="src-tag">近似</el-tag>
            <el-button
              v-if="row.isEditable !== false && !isReadonly"
              size="small"
              type="danger"
              text
              class="row-delete-btn"
              @click="removeRow(row.rowId)"
            >删</el-button>
          </template>
        </el-table-column>

        <el-table-column label="滚动变动（对齐未审期初/增/减/期末）" align="center">
          <el-table-column prop="beginBalance" label="期初" min-width="100" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="row.isEditable !== false && !isReadonly"
                :model-value="row.beginBalance"
                size="small"
                :disabled="isReadonly"
                class="amt-input"
                @change="(v: number) => onCellChange(row.rowId, 'beginBalance', v)"
              />
              <span v-else>{{ fmtAmount(row.beginBalance) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="newAcquisition" label="本期增加" min-width="110" align="right">
            <template #header>
              <el-tooltip content="仅新并购；正常年份多为 0" placement="top"><span class="hint-h">本期增加</span></el-tooltip>
            </template>
            <template #default="{ row }">
              <WpAmountInput
                v-if="row.isEditable !== false && !isReadonly"
                :model-value="row.newAcquisition"
                size="small"
                :disabled="isReadonly"
                :class="{ 'cell-warning': row.newAcquisition !== 0 }"
                class="amt-input"
                @change="(v: number) => onCellChange(row.rowId, 'newAcquisition', v)"
              />
              <span v-else :class="{ 'cell-warning-text': row.newAcquisition !== 0 }">{{ fmtAmount(row.newAcquisition) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="impairment" label="本期减少" min-width="110" align="right">
            <template #header>
              <el-tooltip content="仅减值，不可转回（≥0）" placement="top"><span class="hint-h">本期减少</span></el-tooltip>
            </template>
            <template #default="{ row }">
              <WpAmountInput
                v-if="row.isEditable !== false && !isReadonly"
                :model-value="row.impairment"
                size="small"
                :disabled="isReadonly"
                class="amt-input"
                @change="(v: number) => onCellChange(row.rowId, 'impairment', v)"
              />
              <span v-else>{{ fmtAmount(row.impairment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末" min-width="100" align="right">
            <template #header>
              <el-tooltip content="期末 = 期初 + 增加 − 减少（不摊销）" placement="top">
                <span class="formula-col-header">期末</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span class="formula-value">{{ fmtAmount(row.endBalance) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="未审 / 账项调整 / 审定" align="center">
          <el-table-column prop="unadjusted" label="未审数" min-width="100" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="row.isEditable !== false && !isReadonly"
                :model-value="row.unadjusted"
                size="small"
                :disabled="isReadonly"
                class="amt-input"
                @change="(v: number) => onCellChange(row.rowId, 'unadjusted', v)"
              />
              <span v-else>{{ fmtAmount(row.unadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="aje" label="AJE" min-width="90" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="row.isEditable !== false && !isReadonly"
                :model-value="row.aje"
                size="small"
                :disabled="isReadonly"
                class="amt-input"
                @change="(v: number) => onCellChange(row.rowId, 'aje', v)"
              />
              <span v-else>{{ fmtAmount(row.aje) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="rje" label="RJE" min-width="90" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="row.isEditable !== false && !isReadonly"
                :model-value="row.rje"
                size="small"
                :disabled="isReadonly"
                class="amt-input"
                @change="(v: number) => onCellChange(row.rowId, 'rje', v)"
              />
              <span v-else>{{ fmtAmount(row.rje) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定数" min-width="100" align="right">
            <template #header>
              <el-tooltip content="审定 = 未审 + AJE + RJE" placement="top">
                <span class="formula-col-header">审定数</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span class="formula-value">{{ fmtAmount(row.audited) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="原值 / 减值准备 / 净额" align="center">
          <el-table-column prop="initialRecognition" label="原值" min-width="100" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="row.isEditable !== false && !isReadonly"
                :model-value="row.initialRecognition"
                size="small"
                :disabled="isReadonly"
                class="amt-input"
                @change="(v: number) => onCellChange(row.rowId, 'initialRecognition', v)"
              />
              <span v-else>{{ fmtAmount(row.initialRecognition) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="accImpairment" label="累计减值" min-width="100" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="row.isEditable !== false && !isReadonly"
                :model-value="row.accImpairment"
                size="small"
                :disabled="isReadonly"
                class="amt-input"
                @change="(v: number) => onCellChange(row.rowId, 'accImpairment', v)"
              />
              <span v-else>{{ fmtAmount(row.accImpairment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="净额" min-width="100" align="right">
            <template #header>
              <el-tooltip content="净额 = 原值 − 累计减值（应≈期末）" placement="top">
                <span class="formula-col-header">净额</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span
                class="formula-value"
                :class="{ 'cell-warning-text': Math.abs(row.endBalance - row.netValue) > 0.01 }"
              >{{ fmtAmount(row.netValue) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
      </el-table>
    </div>

    <div class="tb-section">
      <div class="block-header"><span class="block-title">TB 取数与差异（Excel「差异」行）</span></div>
      <el-table :data="differenceRows" border size="small" class="adjudication-table tb-table">
        <el-table-column prop="label" label="科目" min-width="140" />
        <el-table-column prop="tbAmount" label="TB未审数" min-width="120" align="right">
          <template #default="{ row }">{{ fmtAmount(row.tbAmount) }}</template>
        </el-table-column>
        <el-table-column prop="audited" label="审定表审定数" min-width="120" align="right">
          <template #default="{ row }">{{ fmtAmount(row.audited) }}</template>
        </el-table-column>
        <el-table-column prop="difference" label="差异" min-width="120" align="right">
          <template #default="{ row }">
            <span :class="{ 'difference-warning': Math.abs(row.difference) > 0.01 }">{{ fmtAmount(row.difference) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="cross-ref-bar">
      <span class="cross-ref-label">跨底稿：</span>
      <GtIndexChip value="I3-2" @click="navigateTo('I3-2')" />
      <GtIndexChip value="I3-3" @click="navigateTo('I3-3')" />
      <GtIndexChip value="I3-4" @click="navigateTo('I3-4')" />
      <GtIndexChip value="I3-6" @click="navigateTo('I3-6')" />
    </div>

    <el-card class="audit-note-card" shadow="never">
      <template #header><span>一、审计说明</span></template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 12 }"
        placeholder="记录重大事项、内控了解、舞弊风险评估、调整说明及与 I3-3 索引关系…"
        :disabled="isReadonly"
        @blur="onNoteBlur"
      />
    </el-card>

    <el-card class="audit-note-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>二、审计结论</span>
          <el-button v-if="!isReadonly" size="small" text type="primary" @click="handleFillDraft">生成草稿</el-button>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="商誉期末列报是否恰当；减值是否充分；与 TB/明细勾稽结论…"
        :disabled="isReadonly"
        @blur="onConclusionBlur"
      />
      <el-select
        v-if="!isReadonly"
        v-model="quickConclusion"
        placeholder="快捷结论（可选）"
        clearable
        class="conclusion-select"
        @change="onQuickConclusion"
      >
        <el-option value="商誉期末余额列报恰当，减值准备计提充分" label="商誉期末余额列报恰当，减值准备计提充分" />
        <el-option value="商誉减值测试结论合理，无需追加减值" label="商誉减值测试结论合理，无需追加减值" />
        <el-option value="经审计调整后，商誉列报恰当" label="经审计调整后，商誉列报恰当" />
        <el-option value="需进一步关注" label="需进一步关注" />
      </el-select>
    </el-card>

    <details class="edit-tips">
      <summary>编制提示（对齐 Excel I3-1）</summary>
      <ol>
        <li>优先「从 I3-2 带入」生成被投资单位行；Excel 中审定表金额主要引用明细表。</li>
        <li>账项调整从 I3-3 同步（仅 1711）；本期减值可从 I3-6 同步或沿用明细本期减值。</li>
        <li>期末＝期初＋增加−减少；净额＝原值−累计减值；二者应一致。差异行与 TB 须为 0。</li>
        <li>商誉不摊销、减值不可转回；保存后回写 TB 1711 并通知附注。</li>
        <li>「带入调整」：从集中登记按科目 1711 拉取调整分录，逐笔分配到各被投资单位的 AJE/RJE，带入后审定数自动更新并联动附注。</li>
      </ol>
    </details>

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="1711 商誉"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef, inject } from 'vue'
import { ElMessage } from 'element-plus'
import {
  useI3Adjudication,
  type I3AdjudicationRow,
} from '../../composables/useI3Adjudication'
import { useI3CrossSheet } from '../../composables/useI3CrossSheet'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import { useAuditContext } from '@/composables/useAuditContext'
import { Download } from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import I3SheetImportExport from '../shared/I3SheetImportExport.vue'
import WpFourTableSourcePanel from '../../shared/WpFourTableSourcePanel.vue'
import { getICycleSourceConfig, extractTbSourceCodes } from '../../composables/useICycleFourTableSource'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  tbData: { unadjusted1711: number; audited1711: number }
  isReadonly: boolean
  year?: number
  htmlData?: Record<string, unknown> | null
}>()

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
  'save': [itemId: string, value: any]
}>()

const openReviewDialog = inject<(section?: string) => void>('openReviewDialog', () => {})
const isReadonly = computed(() => Boolean(props.isReadonly))

const sourceConfig = getICycleSourceConfig('I3')
const tbSourceCodes = computed(() => extractTbSourceCodes(props.htmlData))
const projectId = computed(() => props.projectId)
const asOfYear = computed(() => props.year || new Date().getFullYear())
const quickConclusion = ref('')

const {
  rows,
  auditNote,
  auditConclusion,
  subtotals,
  warnings,
  crossCheck,
  tbDiff,
  differenceRows,
  addRow,
  removeRow,
  updateCell,
  applyTbData,
  seedFromI32,
  syncFromI33,
  syncImpairmentFromI36,
  fillConclusionDraft,
  saveAdjudication,
  saveNote,
  saveConclusion,
  layerSummary,
  hasAjeApprox,
} = useI3Adjudication(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  toRef(props, 'allResponses'),
  {
    tbUnadjusted1711: computed(() => props.tbData?.unadjusted1711 ?? 0),
    tbAudited1711: computed(() => props.tbData?.audited1711 ?? 0),
    asOfYear,
    onSave: (itemId: string, value: any) => emit('save', itemId, value),
  },
)

// ─── 从集中登记带入调整（1711 商誉，资产借方；带入 AJE/RJE） ───
const bringInRows = computed(() =>
  rows.value.map((r) => ({ rowKey: r.rowId, name: r.investee, aje: r.aje, rje: r.rje })),
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
  subjectPrefix: '1711',
  direction: 'debit',
  subjectCode: '1711',
  wpCode: 'I3',
  subjectLabel: '商誉(1711)',
  rows: bringInRows,
  updateCell: (rowKey: string, field: any, value: number) => updateCell(rowKey, field, value),
  totalAudited: () => subtotals.value.audited,
})

const layerRows = computed(() => {
  const L = layerSummary.value
  return [
    { layer: '原始金额', ...L.original },
    { layer: '减值准备', ...L.impairment },
    { layer: '净值', ...L.net },
  ]
})

const newAcquisitionWarnings = computed(() => warnings.value.filter((w) => w.type === 'newAcquisition'))
const impairmentReversalWarnings = computed(() => warnings.value.filter((w) => w.type === 'impairmentReversal'))
const endVsNetWarnings = computed(() => warnings.value.filter((w) => w.type === 'endVsNet'))

const injectedCross = inject<ReturnType<typeof useI3CrossSheet> | null>('i3CrossSheet', null)
const localCross = injectedCross || useI3CrossSheet(toRef(props, 'allResponses') as any)
const unspecifiedAdjCount = computed(() => {
  const by = localCross.adjustmentSync.value.byInvestee['未指定']
  if (!by) return 0
  const hasAmt = Math.abs(by.costAje) > 0.01 || Math.abs(by.impAje) > 0.01 || Math.abs(by.net) > 0.01
  // 粗计：有未指定汇总则提示至少 1；精确条数从 I3-3 再扫
  const raw = props.allResponses.get('I3-3-rows')
  let rows: any[] = []
  try {
    const remark = typeof raw === 'string' ? raw : raw?.remark
    const p = typeof remark === 'string' ? JSON.parse(remark) : remark
    rows = Array.isArray(p) ? p : []
  } catch { rows = [] }
  let n = 0
  for (const r of rows) {
    const code = String(r.accountCode || '')
    const name = String(r.accountName || '')
    if (!(code.startsWith('1711') || name.includes('商誉'))) continue
    if (!String(r.investee || '').trim()) n++
  }
  return n || (hasAmt ? 1 : 0)
})

const wpId = computed(() => props.wpId)

function getSummaryMethod({ columns }: { columns: any[] }) {
  const sums: string[] = []
  const sub = subtotals.value
  columns.forEach((col, idx) => {
    if (idx === 0) { sums[idx] = '合计'; return }
    const prop = col.property as keyof I3AdjudicationRow | undefined
    if (prop && (sub as any)[prop] != null) {
      sums[idx] = fmtAmount((sub as any)[prop])
      return
    }
    const label = String(col.label || '')
    if (label === '期末') { sums[idx] = fmtAmount(sub.endBalance); return }
    if (label === '审定数') { sums[idx] = fmtAmount(sub.audited); return }
    if (label === '净额') { sums[idx] = fmtAmount(sub.netValue); return }
    sums[idx] = ''
  })
  return sums
}

function getRowClassName({ row }: { row: I3AdjudicationRow }): string {
  const classes: string[] = []
  if (row.newAcquisition !== 0) classes.push('row-has-warning')
  if (row.impairment < 0) classes.push('row-has-error')
  if (Math.abs(row.endBalance - row.netValue) > 0.01) classes.push('row-has-warning')
  return classes.join(' ')
}

function onCellChange(rowId: string, field: keyof I3AdjudicationRow, value: number): void {
  updateCell(rowId, field, value)
}

function onNoteBlur(): void {
  saveNote(auditNote.value)
}

function onConclusionBlur(): void {
  saveConclusion(auditConclusion.value)
}

function onQuickConclusion(val: string): void {
  if (!val) return
  auditConclusion.value = val
  saveConclusion(val)
}

function handleFillDraft(): void {
  fillConclusionDraft()
  saveConclusion(auditConclusion.value)
  ElMessage.success('已生成审计结论草稿')
}

function handleSeedI32(): void {
  const r = seedFromI32()
  if (r.ok) ElMessage.success(r.message)
  else ElMessage.warning(r.message)
}

function handleSyncI33(): void {
  const r = syncFromI33()
  if (r.ok) ElMessage.success(r.message)
  else ElMessage.warning(r.message)
}

function handleSyncI36(): void {
  const r = syncImpairmentFromI36()
  if (r.ok) ElMessage.success(r.message)
  else ElMessage.warning(r.message)
}

function handleApplyTb(): void {
  const tb = props.tbData?.unadjusted1711 ?? 0
  if (!(tb > 0) && rows.value.length === 0) {
    ElMessage.warning('TB 未审数为 0 且无审定行')
    return
  }
  if (!rows.value.length) {
    ElMessage.warning('请先从 I3-2 带入或新增行')
    return
  }
  applyTbData(tb)
  ElMessage.success(`已将 TB 未审 ${fmtAmount(tb)} 写入未审数`)
}

async function handleSave(): Promise<void> {
  const r = await saveAdjudication()
  if (!r.ok) {
    ElMessage.error(`保存被阻断：${r.message}`)
    return
  }
  ElMessage.success(r.message.includes('已保存') ? r.message : `${r.message}；已尝试回写 TB`)
}

function handleReview(): void {
  openReviewDialog('I3-1 审定表')
}

function navigateTo(wpCode: string): void {
  emit('navigate-sheet', wpCode)
}

function fmtAmount(value: number | null | undefined): string {
  if (value == null) return '—'
  if (Math.abs(value) < 0.005) return '—'
  return value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i3-adjudication { font-size: var(--wp-font-size, 13px); padding: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { font-size: 15px; font-weight: 600; color: #1f2937; }
.section-actions { display: flex; gap: 4px; }
.objective-alert { margin-bottom: 12px; }
.methodology-context {
  border-left: 4px solid #d97706; background: #fffbeb; padding: 10px 14px;
  margin-bottom: 12px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.65;
}
.methodology-context p { margin: 0; }
.tab-toolbar { display: flex; justify-content: flex-end; margin-bottom: 10px; }
.toolbar-right { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.adj-warning { margin-bottom: 8px; }
.action-bar { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.layer-card { margin-bottom: 12px; }
.layer-table { font-size: 12px; }
.table-section { margin-bottom: 16px; }
.adjudication-table { font-size: var(--wp-font-size, 13px); }
.adjudication-table :deep(.el-table__footer td) {
  font-weight: 600; background: #f0f9ff; position: sticky; bottom: 0;
}
.formula-col-header, .hint-h {
  border-bottom: 1px dashed #909399; cursor: help; padding-bottom: 2px;
}
.formula-value {
  border-bottom: 1px dashed #c0c4cc; cursor: help; font-weight: 500;
}
.amt-input { width: 100%; }
.cell-warning :deep(.el-input__inner) { background: #fffbeb !important; }
.cell-warning-text { color: #d97706; font-weight: 500; }
.adjudication-table :deep(.row-has-warning td) { background: #fffbeb !important; }
.adjudication-table :deep(.row-has-error td) { background: #fef2f2 !important; }
.row-delete-btn { margin-left: 4px; }
.src-tag { margin-left: 4px; }
.tb-section { margin: 16px 0; }
.block-header { font-weight: 600; margin-bottom: 8px; }
.difference-warning { color: #dc2626; font-weight: 600; }
.cross-ref-bar {
  display: flex; align-items: center; gap: 8px; padding: 8px 0 16px; flex-wrap: wrap;
}
.cross-ref-label { color: #606266; font-size: 12px; }
.audit-note-card { margin-bottom: 12px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.conclusion-select { width: 100%; margin-top: 8px; }
.edit-tips { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ol { padding-left: 18px; margin-top: 8px; line-height: 1.8; }
</style>
