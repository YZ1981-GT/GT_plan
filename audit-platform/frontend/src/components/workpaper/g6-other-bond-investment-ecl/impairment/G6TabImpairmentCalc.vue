<template>
  <div class="g6-impairment-calc" data-testid="g6-impairment-calc">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计目标：确定其他债权投资减值准备计提是否充分、准确；按账面余额口径重算 ECL，核对审定减值、摊余成本及本年计提/转回。"
      class="objective-alert"
    />

    <div class="methodology-context">
      <p class="methodology-title">编制逻辑（对齐 Excel G6-12）：</p>
      <p>① 账面余额 → ③减值=①×②（Stage1/2）或 max(0,①−现值)（Stage3）→ ④摊余成本=①−③</p>
      <p>⑥ 调整：损失率法 ⑤×②A+①×(②A−②)；Stage3 现值法倒挤目标审定减值−③</p>
      <p>⑦=①+⑤；⑧=③+⑥；⑨=⑦−⑧（审定摊余成本）</p>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="chip-wrap"><GtIndexChip value="wp:G6-12" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G6-3" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G6-11" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ calc.rows.value.length }} 行</el-tag>
      </div>
      <div class="toolbar-right">
        <el-segmented v-model="activeTab" :options="segmentOptions" size="small" />
        <el-select
          v-if="!isReadonly"
          v-model="newRowStage"
          size="small"
          style="width: 110px"
          placeholder="Stage"
        >
          <el-option label="Stage1" value="Stage1" />
          <el-option label="Stage2" value="Stage2" />
          <el-option label="Stage3" value="Stage3" />
        </el-select>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          + 投资项目
        </el-button>
        <G6EclImportExportDropdown
          :wp-id="wpId"
          sheet="G6-12"
          :disabled="isReadonly"
          @imported="emit('imported')"
        />
        <el-button
          size="small"
          :disabled="isReadonly || !aiAvailable"
          :loading="aiLoading"
          @click="handleAiConclusion"
        >🤖 AI</el-button>
        <el-button size="small" @click="openReviewDialog('G6-12-impairment-calc')">💬复核</el-button>
      </div>
    </div>

    <el-table
      :data="displayRows"
      border
      size="small"
      max-height="520"
      highlight-current-row
      row-key="id"
      :row-class-name="rowClassName"
      class="impairment-table"
      @current-change="onCurrentChange"
    >
      <el-table-column label="序号" width="55" align="center" fixed>
        <template #default="{ row }">
          <span v-if="row._isSubtotal" class="subtotal-label">{{ row._groupLabel }}小计</span>
          <span v-else-if="row._isTotal" class="total-label">合计</span>
          <span v-else>{{ row.seq }}</span>
        </template>
      </el-table-column>

      <el-table-column label="投资项目" min-width="130" fixed>
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal" />
          <span v-else>{{ row.investProject }}</span>
        </template>
      </el-table-column>

      <!-- ═══ Tab1: 未审 + 调整 ═══ -->
      <template v-if="activeTab === 'tab1'">
        <el-table-column label="未审数" align="center">
          <el-table-column label="①账面余额" min-width="120" align="right">
            <template #default="{ row }">
              <span v-if="row._isSubtotal || row._isTotal" class="subtotal-num">{{ fmtNum(row.amortizedCost) }}</span>
              <el-input-number
                v-else-if="!isReadonly"
                :model-value="row.amortizedCost"
                size="small"
                :controls="false"
                class="compact-num"
                @change="(v: number | undefined) => updateField(row.id, 'amortizedCost', v ?? 0)"
              />
              <span v-else>{{ fmtNum(row.amortizedCost) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="预计未来现金流量现值" min-width="140" align="right">
            <template #default="{ row }">
              <span v-if="row._isSubtotal || row._isTotal" class="subtotal-num">{{ fmtNum(row.pvFutureCashFlow) }}</span>
              <el-input-number
                v-else-if="!isReadonly"
                :model-value="row.pvFutureCashFlow"
                size="small"
                :controls="false"
                class="compact-num"
                :class="{ 'stage3-hint': row.stage === 'Stage3' }"
                @change="(v: number | undefined) => updateField(row.id, 'pvFutureCashFlow', v ?? 0)"
              />
              <span v-else>{{ fmtNum(row.pvFutureCashFlow) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="②预期信用损失率" min-width="130" align="right">
            <template #default="{ row }">
              <template v-if="row._isSubtotal || row._isTotal">
                <el-tooltip v-if="row._isTotal && calc.totalRecoveryRate.value != null" content="合计参考：Σ现值/Σ账面余额（Excel 合计D列）">
                  <span class="formula-cell">{{ fmtPct(calc.totalRecoveryRate.value) }}</span>
                </el-tooltip>
              </template>
              <template v-else-if="row.stage === 'Stage3' && row.pvFutureCashFlow > 0">
                <el-tooltip content="Stage3 由现值反推：③/①">
                  <span class="formula-cell">{{ fmtPct(row.creditLossRate) }}</span>
                </el-tooltip>
              </template>
              <el-input-number
                v-else-if="!isReadonly"
                :model-value="row.creditLossRate"
                size="small"
                :controls="false"
                :precision="4"
                :step="0.01"
                class="compact-num"
                @change="(v: number | undefined) => updateField(row.id, 'creditLossRate', v ?? 0)"
              />
              <span v-else>{{ fmtPct(row.creditLossRate) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="③减值准备" min-width="110" align="right">
            <template #default="{ row }">
              <el-tooltip
                :content="row.stage === 'Stage3' && row.pvFutureCashFlow > 0 ? '③ = max(0, ① − 现值)' : '③ = ① × ②'"
                placement="top"
              >
                <span class="formula-cell" :class="{ 'subtotal-num': row._isSubtotal || row._isTotal }">
                  {{ fmtNum(row.impairmentProvision) }}
                </span>
              </el-tooltip>
            </template>
          </el-table-column>

          <el-table-column label="④摊余成本" min-width="110" align="right">
            <template #default="{ row }">
              <el-tooltip content="④ = ① − ③" placement="top">
                <span class="formula-cell" :class="{ 'subtotal-num': row._isSubtotal || row._isTotal }">
                  {{ fmtNum(row.bookValue) }}
                </span>
              </el-tooltip>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="审计调整" align="center">
          <el-table-column label="⑤账面余额调整" min-width="120" align="right">
            <template #default="{ row }">
              <span v-if="row._isSubtotal || row._isTotal" class="subtotal-num">{{ fmtNum(row.balanceAdjustment) }}</span>
              <el-input-number
                v-else-if="!isReadonly"
                :model-value="row.balanceAdjustment"
                size="small"
                :controls="false"
                class="compact-num"
                @change="(v: number | undefined) => updateField(row.id, 'balanceAdjustment', v ?? 0)"
              />
              <span v-else>{{ fmtNum(row.balanceAdjustment) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="②A / 审定现值" min-width="130" align="right">
            <template #default="{ row }">
              <template v-if="row._isSubtotal || row._isTotal" />
              <template v-else-if="row.stage === 'Stage3'">
                <el-input-number
                  v-if="!isReadonly"
                  :model-value="calc.effectiveAdjPv(row)"
                  size="small"
                  :controls="false"
                  class="compact-num"
                  placeholder="审定现值"
                  @change="(v: number | undefined) => updateField(row.id, 'adjustedPvFutureCashFlow', v ?? 0)"
                />
                <span v-else>{{ fmtNum(calc.effectiveAdjPv(row)) }}</span>
              </template>
              <template v-else>
                <el-input-number
                  v-if="!isReadonly"
                  :model-value="calc.effectiveAdjRate(row)"
                  size="small"
                  :controls="false"
                  :precision="4"
                  :step="0.01"
                  class="compact-num"
                  @change="(v: number | undefined) => updateField(row.id, 'adjustedCreditLossRate', v ?? 0)"
                />
                <span v-else>{{ fmtPct(calc.effectiveAdjRate(row)) }}</span>
              </template>
            </template>
          </el-table-column>

          <el-table-column label="⑥减值准备调整" min-width="120" align="right">
            <template #default="{ row }">
              <el-tooltip
                :content="row.stage === 'Stage3' && row.pvFutureCashFlow > 0
                  ? '⑥ = 目标审定减值 − ③'
                  : '⑥ = ⑤×②A + ①×(②A−②)'"
                placement="top"
              >
                <span class="formula-cell" :class="{ 'subtotal-num': row._isSubtotal || row._isTotal }">
                  {{ fmtNum(row.impairmentAdjustment) }}
                </span>
              </el-tooltip>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="阶段" width="100" align="center">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <el-select
              v-else-if="!isReadonly"
              :model-value="row.stage"
              size="small"
              style="width: 100%"
              @change="(v: string) => updateField(row.id, 'stage', v)"
            >
              <el-option label="Stage1" value="Stage1" />
              <el-option label="Stage2" value="Stage2" />
              <el-option label="Stage3" value="Stage3" />
            </el-select>
            <el-tag
              v-else
              size="small"
              :type="row.stage === 'Stage3' ? 'danger' : row.stage === 'Stage2' ? 'warning' : 'success'"
            >{{ row.stage }}</el-tag>
          </template>
        </el-table-column>

        <el-table-column label="信用组合方式" min-width="110">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <el-input
              v-else-if="!isReadonly"
              :model-value="row.creditGroupMethod"
              size="small"
              placeholder="单项/组合..."
              @change="(v: string) => updateField(row.id, 'creditGroupMethod', v)"
            />
            <span v-else>{{ row.creditGroupMethod || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="信用组合名称" min-width="110">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <el-input
              v-else-if="!isReadonly"
              :model-value="row.creditGroupName"
              size="small"
              placeholder="组合名..."
              @change="(v: string) => updateField(row.id, 'creditGroupName', v)"
            />
            <span v-else>{{ row.creditGroupName || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="OCI影响" min-width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <el-input-number
              v-else-if="!isReadonly"
              :model-value="row.ociImpact"
              size="small"
              :controls="false"
              class="compact-num"
              @change="(v: number | undefined) => updateField(row.id, 'ociImpact', v ?? 0)"
            />
            <span v-else>{{ fmtNum(row.ociImpact) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="索引" width="90" align="center">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <GtIndexChip
              v-else
              :value="row.indexRef"
              @update="(v: string) => updateField(row.id, 'indexRef', v)"
            />
          </template>
        </el-table-column>
      </template>

      <!-- ═══ Tab2: 审定净值 ═══ -->
      <template v-if="activeTab === 'tab2'">
        <el-table-column label="审计后的债权净值" align="center">
          <el-table-column label="⑦账面余额" min-width="120" align="right">
            <template #default="{ row }">
              <el-tooltip content="⑦ = ① + ⑤" placement="top">
                <span class="formula-cell" :class="{ 'subtotal-num': row._isSubtotal || row._isTotal }">
                  {{ fmtNum(row.adjBalance) }}
                </span>
              </el-tooltip>
            </template>
          </el-table-column>

          <el-table-column label="⑧减值准备" min-width="110" align="right">
            <template #default="{ row }">
              <el-tooltip content="⑧ = ③ + ⑥" placement="top">
                <span class="formula-cell" :class="{ 'subtotal-num': row._isSubtotal || row._isTotal }">
                  {{ fmtNum(row.adjImpairment) }}
                </span>
              </el-tooltip>
            </template>
          </el-table-column>

          <el-table-column label="⑨摊余成本" min-width="110" align="right">
            <template #default="{ row }">
              <el-tooltip content="⑨ = ⑦ − ⑧" placement="top">
                <span class="formula-cell" :class="{ 'subtotal-num': row._isSubtotal || row._isTotal }">
                  {{ fmtNum(row.adjBookValue) }}
                </span>
              </el-tooltip>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="上年减值" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <el-input-number
              v-else-if="!isReadonly"
              :model-value="row.priorImpairment"
              size="small"
              :controls="false"
              class="compact-num"
              @change="(v: number | undefined) => updateField(row.id, 'priorImpairment', v ?? 0)"
            />
            <span v-else>{{ fmtNum(row.priorImpairment) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="本年计提" min-width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <el-tooltip v-else content="max(0, ⑧ − 上年减值)" placement="top">
              <span class="formula-cell">{{ fmtNum(row.currentProvision) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column label="本年转回" min-width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <el-tooltip v-else content="max(0, 上年减值 − ⑧)" placement="top">
              <span class="formula-cell">{{ fmtNum(row.currentReversal) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column label="公允价值(参考)" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <el-input-number
              v-else-if="!isReadonly"
              :model-value="row.adjFairValue || row.fairValue"
              size="small"
              :controls="false"
              class="compact-num"
              @change="(v: number | undefined) => updateField(row.id, 'adjFairValue', v ?? 0)"
            />
            <span v-else>{{ fmtNum(row.adjFairValue || row.fairValue) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="OCI调整" min-width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <el-input-number
              v-else-if="!isReadonly"
              :model-value="row.ociAdjustment"
              size="small"
              :controls="false"
              class="compact-num"
              @change="(v: number | undefined) => updateField(row.id, 'ociAdjustment', v ?? 0)"
            />
            <span v-else>{{ fmtNum(row.ociAdjustment) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="差异说明" min-width="140">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <el-input
              v-else-if="!isReadonly"
              :model-value="row.differenceNote"
              size="small"
              @change="(v: string) => updateField(row.id, 'differenceNote', v)"
            />
            <span v-else>{{ row.differenceNote }}</span>
          </template>
        </el-table-column>
      </template>

      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-popconfirm
            v-if="!row._isSubtotal && !row._isTotal"
            title="确认删除？"
            @confirm="calc.removeRow(row.id)"
          >
            <template #reference>
              <el-icon class="delete-icon"><Delete /></el-icon>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <div class="summary-bar">
      <span class="sum-item">①账面余额 <strong>{{ fmtNum(calc.grandTotal.value.amortizedCost) }}</strong></span>
      <span class="sum-item">③减值 <strong>{{ fmtNum(calc.grandTotal.value.impairmentProvision) }}</strong></span>
      <span class="sum-item">⑧审定减值 <strong>{{ fmtNum(calc.grandTotal.value.adjImpairment) }}</strong></span>
      <span class="sum-item">⑨审定摊余成本 <strong>{{ fmtNum(calc.grandTotal.value.adjBookValue) }}</strong></span>
    </div>

    <el-card class="audit-note-card" shadow="never">
      <template #header>
        <div class="audit-note-header"><span>审计说明</span></div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 4 }"
        placeholder="概述减值测算程序、组合划分、Stage3 现值假设、拟调整/未调整事项及与 G6-3/G6-1 勾稽。"
        @update:model-value="saveAuditNote"
      />
    </el-card>

    <el-card class="conclusion-card" shadow="never">
      <div class="conclusion-header">
        <span class="conclusion-title">审计结论</span>
        <el-button
          size="small"
          type="primary"
          link
          :disabled="isReadonly || !aiAvailable"
          :loading="aiLoading"
          @click="handleAiConclusion"
        >🤖 AI生成</el-button>
      </div>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="A、计提充分准确。B、除下述事项外未见异常。C、存在重大差异须调整。"
        :disabled="isReadonly"
      />
    </el-card>

    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>① 账面余额为计提基数；④/⑨ 摊余成本 = 账面余额 − 减值准备。</li>
        <li>Stage1/2：③=①×②；⑥=⑤×②A+①×(②A−②)。</li>
        <li>Stage3：填预计未来现金流量现值后，③=max(0,①−现值)；⑥按审定现值倒挤。</li>
        <li>本年计提/转回由⑧与上年减值自动轧差，不可手改。</li>
        <li>审定减值合计应与 G6-3 期末坏账、G6-1 减值层勾稽。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G6TabImpairmentCalc.vue — 对齐 Excel《减值准备测算表G6-12》
 */
import { ref, computed, inject, onMounted, watch } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import {
  useG6EclImpairmentCalc,
  createEmptyImpairmentRow,
} from '../../composables/useG6EclImpairmentCalc'
import { useG6EclFormData, type ImpairmentCalcRow } from '../../composables/useG6EclFormData'
import { useG6EclAiGenerate } from '../../composables/useG6EclAiGenerate'
import GtIndexChip from '../../GtIndexChip.vue'
import G6EclImportExportDropdown from '../G6EclImportExportDropdown.vue'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{ imported: [] }>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const calc = useG6EclImpairmentCalc()
const conclusion = ref('')
const activeTab = ref<'tab1' | 'tab2'>('tab1')
const newRowStage = ref<'Stage1' | 'Stage2' | 'Stage3'>('Stage1')

const wpIdRef = computed(() => props.wpId)
const { generateAndConfirm, aiAvailable, loading: aiLoading } = useG6EclAiGenerate(wpIdRef)

const NOTE_KEY = 'G6-12-impairment-calc-audit-note'
const DATA_KEY = 'G6-12-impairment-calc-data'
const auditNote = ref('')
const formData = useG6EclFormData({
  wpId: wpIdRef,
  projectId: computed(() => props.projectId),
})

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  formData.debouncedSave(NOTE_KEY, { conclusion: null, remark: val })
}

const segmentOptions = [
  { label: '未审+调整', value: 'tab1' },
  { label: '审定净值', value: 'tab2' },
]

const isReadonly = computed(() => props.isReadonly)

interface DisplayRow extends ImpairmentCalcRow {
  _isSubtotal?: boolean
  _isTotal?: boolean
  _groupLabel?: string
}

const displayRows = computed<DisplayRow[]>(() => {
  const grouped = calc.groupedRows.value
  const result: DisplayRow[] = []

  function pushGroup(label: string, group: { rows: ImpairmentCalcRow[]; subtotal: Record<string, number> }) {
    if (!group.rows.length) return
    for (const r of group.rows) result.push(r as DisplayRow)
    result.push({
      ...createEmptyImpairmentRow({ id: `__sub-${label}`, seq: 0, investProject: '' }),
      _isSubtotal: true,
      _groupLabel: label,
      ...group.subtotal,
    } as DisplayRow)
  }

  pushGroup('Stage1', grouped.stage1)
  pushGroup('Stage2', grouped.stage2)
  pushGroup('Stage3', grouped.stage3)

  result.push({
    ...createEmptyImpairmentRow({ id: '__total__', seq: 0, investProject: '' }),
    _isTotal: true,
    ...grouped.grandTotal,
  } as DisplayRow)

  return result
})

function onCurrentChange(row: DisplayRow | null) {
  if (!row || row._isSubtotal || row._isTotal) return
  const idx = calc.rows.value.findIndex(r => r.id === row.id)
  if (idx >= 0) calc.selectedRowIndex.value = idx
}

function rowClassName({ row }: { row: DisplayRow }): string {
  if (row._isSubtotal) return 'row-subtotal'
  if (row._isTotal) return 'row-total'
  return ''
}

function updateField(id: string, field: keyof ImpairmentCalcRow, value: any) {
  calc.updateRow(id, field, value ?? (typeof value === 'string' ? '' : 0))
  persistData()
}

async function handleAddRow() {
  await calc.addRow(newRowStage.value)
  persistData()
}

async function handleAiConclusion(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'impairment-conclusion',
    conclusion.value || '',
    {
      rowCount: calc.rows.value.length,
      totals: calc.grandTotal.value,
      stageCounts: {
        s1: calc.groupedRows.value.stage1.rows.length,
        s2: calc.groupedRows.value.stage2.rows.length,
        s3: calc.groupedRows.value.stage3.rows.length,
      },
    },
    'AI 审计结论',
  )
  if (text) {
    conclusion.value = text
    persistData()
  }
}

function fmtNum(v: unknown): string {
  if (v === undefined || v === null || v === '') return '-'
  const n = Number(v)
  if (!Number.isFinite(n)) return '-'
  if (Math.abs(n) < 0.0000001) return '-'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return '-'
  return `${(Number(v) * 100).toFixed(2)}%`
}

function persistData(): void {
  if (props.isReadonly) return
  formData.debouncedSave(DATA_KEY, {
    conclusion: JSON.stringify({
      rows: calc.toJSON(),
      conclusion: conclusion.value,
    }),
  })
}

watch(conclusion, () => persistData())

function initFromData(): void {
  const fromHtml = props.htmlData?.impairmentCalc
  if (fromHtml?.rows) {
    calc.loadRows(fromHtml.rows)
    if (fromHtml.conclusion) conclusion.value = fromHtml.conclusion
    return
  }
  const content = formData.parseContent?.()
  if (content?.impairmentCalc?.rows) {
    calc.loadRows(content.impairmentCalc.rows)
    if (content.impairmentCalc.conclusion) conclusion.value = content.impairmentCalc.conclusion
  }
}

onMounted(async () => {
  await formData.loadAll()
  initFromData()
  const saved = formData.allResponses.value.get(DATA_KEY)
  if (saved?.conclusion) {
    try {
      const parsed = JSON.parse(saved.conclusion)
      if (parsed.rows?.length) calc.loadRows(parsed.rows)
      if (parsed.conclusion) conclusion.value = parsed.conclusion
    } catch { /* ignore */ }
  }
  const n = formData.allResponses.value.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
})

watch(() => props.htmlData, (d) => {
  if (d?.impairmentCalc) initFromData()
})

defineExpose({
  toJSON: () => ({
    rows: calc.toJSON(),
    conclusion: conclusion.value,
  }),
})
</script>

<style scoped>
.g6-impairment-calc { padding: 12px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.methodology-context {
  border-left: 4px solid #e6a23c; background: #fdf6ec;
  padding: 10px 14px; margin-bottom: 12px; border-radius: 0 4px 4px 0;
  font-size: 12px; line-height: 1.7; color: #6b5900;
}
.methodology-title { font-weight: 600; margin: 0 0 4px; }
.methodology-context p { margin: 2px 0; }
.tab-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  gap: 8px; margin-bottom: 10px; flex-wrap: wrap;
}
.toolbar-left, .toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; }
.impairment-table { font-size: var(--wp-font-size, 13px); }
.compact-num { width: 100%; }
.compact-num :deep(.el-input__inner) { text-align: right; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; display: inline-block; min-width: 40px; text-align: right; }
:deep(.row-subtotal) { background-color: #f5f7fa !important; font-weight: 600; }
:deep(.row-total) { background-color: #ecf5ff !important; font-weight: 700; }
.subtotal-label { color: #606266; font-weight: 600; font-size: 12px; }
.total-label { color: #409eff; font-weight: 700; }
.subtotal-num { font-weight: 600; }
:deep(.stage3-hint .el-input__wrapper) { box-shadow: 0 0 0 1px #e6a23c inset; }
.delete-icon { cursor: pointer; color: #909399; }
.delete-icon:hover { color: #f56c6c; }
.summary-bar {
  display: flex; gap: 14px; flex-wrap: wrap; align-items: center;
  margin: 12px 0; padding: 8px 12px;
  background: #fafafa; border: 1px solid #ebeef5; border-radius: 4px;
  font-size: 13px; color: #606266;
}
.sum-item strong { color: #303133; }
.audit-note-card, .conclusion-card { margin-top: 14px; }
.audit-note-header, .conclusion-header {
  display: flex; justify-content: space-between; align-items: center; font-weight: 600;
}
.conclusion-title { font-weight: 600; font-size: 14px; margin-bottom: 8px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; font-weight: 500; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
.prep-hint li { margin-bottom: 4px; }
</style>
