<script setup lang="ts">
/**
 * D2TabAdjudication — 审定表 D2-1（完整三层结构）
 * 一、应收账款原值 | 二、坏账准备 | 三、净值 | 账龄组合附表
 * 参照 xlsx 审定表D2-1 + D4TabAdjudication 精美化
 */
import { computed, inject, ref, toRef, watch, type Ref } from 'vue'
import { useD2Adjudication, type AdjudicationRow } from '../composables/useD2Adjudication'
import { useD2CrossSheet } from '../composables/useD2CrossSheet'
import { useD2AiGenerate } from '../composables/useD2AiGenerate'
import { useD2TabImportExport } from '../composables/useD2TabImportExport'
import { getChangeRate } from '../composables/useD2FormulaEngine'
import GtIndexChip from '../GtIndexChip.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)
const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

const displayPrefs = inject<{ fmtAmount: (v: number) => string; amountClass?: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) => v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
  amountClass: () => '',
})

const baseOpts = {
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
}

const {
  adjudicationRows,
  totalRow,
  trialBalanceDiff,
  updateCell,
  isChangeRateWarning,
  sumifStatus,
  detailCrossValidation,
  eclCrossValidation,
} = useD2Adjudication(baseOpts)

const crossSheet = useD2CrossSheet({ allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>> })

const { generateAndConfirm, aiAvailable } = useD2AiGenerate(toRef(props, 'wpId'))

const { onExportTemplate, onExportData, onImportFile } = useD2TabImportExport(
  toRef(props, 'wpId') as Ref<string>,
  toRef(props, 'projectId') as Ref<string>,
  'D2-1',
)

const auditNote = ref('')
const auditConclusion = ref('')

function loadAuditTexts(): void {
  auditNote.value = props.allResponses.get('D2-adj-audit-note')?.remark || ''
  auditConclusion.value = props.allResponses.get('D2-adj-audit-conclusion')?.remark || ''
}

watch(() => props.allResponses, loadAuditTexts, { immediate: true, deep: true })

function saveAuditField(field: 'note' | 'conclusion', value: string): void {
  const id = field === 'note' ? 'D2-adj-audit-note' : 'D2-adj-audit-conclusion'
  props.allResponses.set(id, { item_id: id, conclusion: null, remark: value })
  window.dispatchEvent(new CustomEvent('d2:save-items', {
    detail: { items: [{ item_id: id, conclusion: null, remark: value }] },
  }))
}

const loading = computed(() => sumifStatus.value === 'computing')

interface SectionRow {
  rowKey: string
  label: string
  priorAudited: number
  currentAudited: number
  change: number
  changeRate: number | ''
  isFromCrossSheet?: boolean
  isEditable?: boolean
}

function mapGrossRows(): SectionRow[] {
  return adjudicationRows.value.map(r => ({
    rowKey: r.rowKey,
    label: r.label,
    priorAudited: r.priorAudited,
    currentAudited: r.currentAudited,
    change: r.change,
    changeRate: r.changeRate,
    isFromCrossSheet: r.isFromSumif,
    isEditable: r.isEditable,
  }))
}

const provisionRows = computed<SectionRow[]>(() => {
  const bd = crossSheet.badDebtByCategory.value
  const items = [
    { rowKey: 'individual', label: '单项计提坏账准备', data: bd.individual },
    { rowKey: 'aging', label: '账龄组合坏账准备', data: bd.aging },
    { rowKey: 'customer-type', label: '客户类型组合坏账准备', data: bd.customerType },
  ]
  const rows = items.map(({ rowKey, label, data }) => {
    const change = data.current - data.prior
    return {
      rowKey,
      label,
      priorAudited: data.prior,
      currentAudited: data.current,
      change,
      changeRate: getChangeRate(data.prior, data.current),
      isFromCrossSheet: true,
      isEditable: false,
    }
  })
  const prior = rows.reduce((s, r) => s + r.priorAudited, 0)
  const current = rows.reduce((s, r) => s + r.currentAudited, 0)
  rows.push({
    rowKey: 'total',
    label: '小计',
    priorAudited: prior,
    currentAudited: current,
    change: current - prior,
    changeRate: getChangeRate(prior, current),
    isEditable: false,
  })
  return rows
})

const netRows = computed<SectionRow[]>(() => {
  const gross = mapGrossRows().filter(r => r.rowKey !== 'total')
  const prov = provisionRows.value.filter(r => r.rowKey !== 'total')
  const rows: SectionRow[] = gross.map((g, i) => {
    const p = prov[i] || { priorAudited: 0, currentAudited: 0 }
    const prior = g.priorAudited - p.priorAudited
    const current = g.currentAudited - p.currentAudited
    return {
      rowKey: g.rowKey,
      label: g.label.replace('应收账款-', '净值-'),
      priorAudited: prior,
      currentAudited: current,
      change: current - prior,
      changeRate: getChangeRate(prior, current),
      isEditable: false,
    }
  })
  const prior = rows.reduce((s, r) => s + r.priorAudited, 0)
  const current = rows.reduce((s, r) => s + r.currentAudited, 0)
  rows.push({
    rowKey: 'total',
    label: '合计',
    priorAudited: prior,
    currentAudited: current,
    change: current - prior,
    changeRate: getChangeRate(prior, current),
    isEditable: false,
  })
  return rows
})

const AGING_LABELS = [
  { key: 'within1Year', label: '一年以内' },
  { key: 'y1to2', label: '一到二年' },
  { key: 'y2to3', label: '二到三年' },
  { key: 'y3to4', label: '三到四年' },
  { key: 'y4to5', label: '四到五年' },
  { key: 'over5', label: '五年以上' },
] as const

const agingTableRows = computed(() => {
  const a = crossSheet.agingFromDetail.value.audited
  return AGING_LABELS.map(({ key, label }) => ({
    label,
    amount: a[key],
  }))
})

const agingTotal = computed(() => agingTableRows.value.reduce((s, r) => s + r.amount, 0))

function fmtRate(rate: number | ''): string {
  if (rate === '') return '-'
  return (rate * 100).toFixed(1) + '%'
}

function getCellClass(row: SectionRow | AdjudicationRow, field: string): string {
  const classes: string[] = []
  if ('isFromCrossSheet' in row && row.isFromCrossSheet && field === 'currentAudited') {
    classes.push('sumif-cell')
  }
  if ('isFromSumif' in row && row.isFromSumif && field === 'currentAudited') {
    classes.push('sumif-cell')
  }
  if (field === 'changeRate' && isChangeRateWarning(row.changeRate as number | '')) {
    classes.push('rate-warning')
  }
  return classes.join(' ')
}

async function onAiNote(section: 'adj-note' | 'adj-conclusion'): Promise<void> {
  const existing = section === 'adj-note' ? auditNote.value : auditConclusion.value
  const title = section === 'adj-note' ? 'AI 生成审计说明' : 'AI 生成审计结论'
  const content = await generateAndConfirm(section, existing, {
    grossTotal: totalRow.value.currentAudited,
    changeRate: totalRow.value.changeRate,
    badDebtTotal: crossSheet.badDebtTotal.value.current,
  }, title)
  if (section === 'adj-note') {
    auditNote.value = content
    saveAuditField('note', content)
  } else {
    auditConclusion.value = content
    saveAuditField('conclusion', content)
  }
}
</script>

<template>
  <div class="d2-tab-adjudication">
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button-group size="small">
          <el-button @click="onExportTemplate">导出模板</el-button>
          <el-button @click="onExportData">导出数据</el-button>
          <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile">
            <el-button :disabled="isReadonly">导入数据</el-button>
          </el-upload>
        </el-button-group>
      </div>
    </div>

    <el-alert v-if="detailCrossValidation" type="warning" :closable="false" class="cross-alert">
      {{ detailCrossValidation }}
      <GtIndexChip v-if="jumpToSection" label="D2-2" class="warn-chip" @click="jumpToSection('明细表D2-2')" />
    </el-alert>
    <el-alert v-if="eclCrossValidation" type="warning" :closable="false" class="cross-alert">
      {{ eclCrossValidation }}
      <GtIndexChip v-if="jumpToSection" label="D2-9" class="warn-chip" @click="jumpToSection('应收坏账准备测算D2-9')" />
    </el-alert>

    <el-alert v-if="!trialBalanceDiff.isZero" type="error" :closable="false" class="tb-alert">
      试算平衡表差异：{{ displayPrefs.fmtAmount(trialBalanceDiff.amount) }}（科目1122）
    </el-alert>

    <el-skeleton :loading="loading" :rows="8" animated>
      <template #default>
        <!-- 一、应收账款原值 -->
        <div class="section-block section-gross">
          <div class="section-title">一、应收账款原值</div>
          <el-table :data="adjudicationRows" border stripe size="small">
            <el-table-column prop="label" label="项目" width="160" fixed />
            <el-table-column label="期初" align="center">
              <el-table-column label="未审" width="95" align="right">
                <template #default="{ row }">{{ displayPrefs.fmtAmount(row.priorUnadjusted) }}</template>
              </el-table-column>
              <el-table-column label="AJE" width="85" align="right">
                <template #default="{ row }">{{ displayPrefs.fmtAmount(row.priorAje) }}</template>
              </el-table-column>
              <el-table-column label="RJE" width="85" align="right">
                <template #default="{ row }">{{ displayPrefs.fmtAmount(row.priorRje) }}</template>
              </el-table-column>
              <el-table-column label="审定" width="95" align="right">
                <template #default="{ row }">{{ displayPrefs.fmtAmount(row.priorAudited) }}</template>
              </el-table-column>
            </el-table-column>
            <el-table-column label="期末" align="center">
              <el-table-column label="未审" width="95" align="right">
                <template #default="{ row }">
                  <el-tooltip v-if="row.isFromSumif" content="取自D2-2 SUMIF">
                    <span class="sumif-cell">{{ displayPrefs.fmtAmount(row.currentUnadjusted) }}</span>
                  </el-tooltip>
                  <span v-else>{{ displayPrefs.fmtAmount(row.currentUnadjusted) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="AJE" width="85" align="right">
                <template #default="{ row }">{{ displayPrefs.fmtAmount(row.currentAje) }}</template>
              </el-table-column>
              <el-table-column label="RJE" width="85" align="right">
                <template #default="{ row }">{{ displayPrefs.fmtAmount(row.currentRje) }}</template>
              </el-table-column>
              <el-table-column label="审定" width="95" align="right">
                <template #default="{ row }">
                  <span :class="getCellClass(row, 'currentAudited')">{{ displayPrefs.fmtAmount(row.currentAudited) }}</span>
                </template>
              </el-table-column>
            </el-table-column>
            <el-table-column label="变动额" width="100" align="right">
              <template #default="{ row }">{{ displayPrefs.fmtAmount(row.change) }}</template>
            </el-table-column>
            <el-table-column label="变动率" width="90" align="right">
              <template #default="{ row }">
                <span :class="getCellClass(row, 'changeRate')">{{ fmtRate(row.changeRate) }}</span>
                <GtIndexChip
                  v-if="isChangeRateWarning(row.changeRate) && jumpToSection"
                  label="D2-5"
                  @click="jumpToSection('应收账款分析表D2-5')"
                />
              </template>
            </el-table-column>
            <el-table-column label="原因分析" min-width="140">
              <template #default="{ row }">
                <el-input
                  v-if="row.isEditable && !isReadonly"
                  :model-value="row.reasonAnalysis"
                  size="small"
                  @change="(v: string) => updateCell(row.rowKey, 'reason', v)"
                />
                <span v-else>{{ row.reasonAnalysis || '-' }}</span>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <!-- 二、坏账准备 -->
        <div class="section-block section-provision">
          <div class="section-title">二、应收账款坏账准备</div>
          <el-table :data="provisionRows" border stripe size="small">
            <el-table-column prop="label" label="项目" width="200" />
            <el-table-column label="期初审定" width="120" align="right">
              <template #default="{ row }">
                <span :class="getCellClass(row, 'currentAudited')">{{ displayPrefs.fmtAmount(row.priorAudited) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="期末审定" width="120" align="right">
              <template #default="{ row }">
                <el-tooltip content="取自D2-3坏账准备明细表">
                  <span class="sumif-cell">{{ displayPrefs.fmtAmount(row.currentAudited) }}</span>
                </el-tooltip>
              </template>
            </el-table-column>
            <el-table-column label="变动额" width="110" align="right">
              <template #default="{ row }">{{ displayPrefs.fmtAmount(row.change) }}</template>
            </el-table-column>
            <el-table-column label="变动率" width="90" align="right">
              <template #default="{ row }">
                <span :class="getCellClass(row, 'changeRate')">{{ fmtRate(row.changeRate) }}</span>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <!-- 三、净值 -->
        <div class="section-block section-net">
          <div class="section-title">三、应收账款净值</div>
          <el-table :data="netRows" border stripe size="small">
            <el-table-column prop="label" label="项目" width="200" />
            <el-table-column label="期初审定" width="120" align="right">
              <template #default="{ row }">{{ displayPrefs.fmtAmount(row.priorAudited) }}</template>
            </el-table-column>
            <el-table-column label="期末审定" width="120" align="right">
              <template #default="{ row }">
                <span class="audited-cell">{{ displayPrefs.fmtAmount(row.currentAudited) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="变动额" width="110" align="right">
              <template #default="{ row }">{{ displayPrefs.fmtAmount(row.change) }}</template>
            </el-table-column>
            <el-table-column label="变动率" width="90" align="right">
              <template #default="{ row }">{{ fmtRate(row.changeRate) }}</template>
            </el-table-column>
          </el-table>
        </div>

        <!-- 账龄组合原值附表 -->
        <div class="section-block section-aging">
          <div class="section-title">（一）账龄组合原值（取自 D2-2 审定账龄汇总）</div>
          <el-table :data="agingTableRows" border size="small" style="max-width: 480px">
            <el-table-column prop="label" label="账龄段" width="140" />
            <el-table-column label="期末审定余额" align="right">
              <template #default="{ row }">
                <span class="sumif-cell">{{ displayPrefs.fmtAmount(row.amount) }}</span>
              </template>
            </el-table-column>
          </el-table>
          <div class="aging-total">小计：{{ displayPrefs.fmtAmount(agingTotal) }}</div>
        </div>

        <!-- 试算平衡 -->
        <div class="tb-row">
          <span>试算平衡表数（1122）：{{ displayPrefs.fmtAmount(parseFloat(String(allResponses.get('D2-adj-tb-amount')?.remark || '0')) || 0) }}</span>
          <span :class="{ 'rate-warning': !trialBalanceDiff.isZero }">
            差异：{{ displayPrefs.fmtAmount(trialBalanceDiff.amount) }}
          </span>
        </div>
      </template>
    </el-skeleton>

    <!-- 审计说明 / 结论 -->
    <div class="audit-footer">
      <el-row :gutter="16">
        <el-col :span="12">
          <div class="audit-block">
            <div class="audit-block-header">
              <span>1. 审计说明</span>
              <el-button v-if="aiAvailable && !isReadonly" size="small" text type="primary" @click="onAiNote('adj-note')">🤖 AI生成</el-button>
              <GtReviewTrigger section-id="D2-adj-audit-note" />
            </div>
            <el-input
              v-model="auditNote"
              type="textarea"
              :rows="4"
              :disabled="isReadonly"
              placeholder="说明应收账款变动原因..."
              @change="saveAuditField('note', auditNote)"
            />
          </div>
        </el-col>
        <el-col :span="12">
          <div class="audit-block">
            <div class="audit-block-header">
              <span>2. 审计结论</span>
              <el-button v-if="aiAvailable && !isReadonly" size="small" text type="primary" @click="onAiNote('adj-conclusion')">🤖 AI生成</el-button>
              <GtReviewTrigger section-id="D2-adj-audit-conclusion" />
            </div>
            <el-input
              v-model="auditConclusion"
              type="textarea"
              :rows="4"
              :disabled="isReadonly"
              placeholder="审计结论..."
              @change="saveAuditField('conclusion', auditConclusion)"
            />
          </div>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<style scoped>
.d2-tab-adjudication { padding: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; margin-bottom: 12px; }
.toolbar-left { display: flex; gap: 8px; }
.tb-alert { margin-bottom: 12px; }
.cross-alert { margin-bottom: 12px; }
.warn-chip { margin-left: 8px; vertical-align: middle; }
.section-block { margin-bottom: 20px; border-radius: 6px; padding: 12px; }
.section-gross { background: #f0f9eb; border-left: 4px solid #67c23a; }
.section-provision { background: #fdf6ec; border-left: 4px solid #e6a23c; }
.section-net { background: #ecf5ff; border-left: 4px solid #409eff; }
.section-aging { background: #f5f7fa; border-left: 4px solid #909399; }
.section-title { font-weight: 600; font-size: 14px; margin-bottom: 8px; color: #303133; }
.sumif-cell { background: #e6f7ff; padding: 2px 6px; border-radius: 2px; }
.rate-warning { color: #f56c6c; font-weight: 600; }
.audited-cell { font-weight: 600; }
.aging-total { margin-top: 8px; font-size: 13px; font-weight: 600; text-align: right; padding-right: 12px; }
.tb-row { display: flex; gap: 24px; padding: 10px 12px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 4px; font-size: 13px; margin-bottom: 16px; }
.audit-footer { margin-top: 16px; }
.audit-block-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-weight: 600; font-size: 13px; }
</style>
