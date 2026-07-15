<script setup lang="ts">
/**
 * E1TabCashTxnAnalysis.vue — E1-26 现金交易分析表（IPO/舞弊应对）
 * 对齐源模板：（一）月度总体 （二）合理性 （三）金额分布 （四）客户/供应商概要 + 说明/结论
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import E1IpoSheetChrome from './E1IpoSheetChrome.vue'
import {
  useE1CashTxnAnalysis,
  formatPct,
  type MonthAmountRow,
  type StratumRow,
} from '../composables/useE1CashTxnAnalysis'
import { useE1AiGenerate } from '../composables/useE1AiGenerate'
import { useE1ImportExport } from '../composables/useE1ImportExport'
import type { UseE1BaseOptions } from '../composables/useE1Adjudication'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveImmediate: (items: any[]) => Promise<void>
  debouncedSave: (items: any[]) => Promise<void>
  isReadonly: boolean
  sheetName?: string
  bsDate?: string
}>()

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()
const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
const { generateText, isGenerating } = useE1AiGenerate(toRef(props, 'wpId') as Ref<string>)

const options: UseE1BaseOptions = {
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
}

const {
  pack,
  auditNote,
  auditConclusion,
  isLoading,
  isApplicable,
  salesView,
  purchaseView,
  salesShare,
  purchaseShare,
  salesAvgPerTxn,
  purchaseAvgPerTxn,
  highCashShare,
  load,
  patchPack,
  setApplicable,
  saveNote,
  saveConclusion,
} = useE1CashTxnAnalysis(options)

const sheetCode = computed(() => 'E1-26')
const { exportTemplate, exportData, importData, isImporting } = useE1ImportExport({
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  sheet: sheetCode as unknown as Ref<string>,
})

const TIPS = [
  '结合相关收入确认及成本核算的原则与依据，是否存在体外循环或虚构业务情形；',
  '在业务流程层面内部控制底稿中完成了解与现金交易相关的内部控制，并测试其有效性；',
  '关注公司实际控制人及发行人董监高等关联方是否与客户或供应商存在资金往来。',
]

function fmtAmt(v: number): string {
  return displayPrefs.fmtAmount(Number(v) || 0)
}

function updateMonth(
  side: 'sales' | 'purchase',
  month: number,
  field: keyof MonthAmountRow,
  value: number,
): void {
  patchPack(p => {
    const rows = side === 'sales' ? p.salesMonths : p.purchaseMonths
    const row = rows.find(r => r.month === month)
    if (!row) return
    ;(row as any)[field] = Number(value) || 0
  })
}

function updateOverall(side: 'sales' | 'purchase', field: 'taxInclusiveBase' | 'remark', value: number | string): void {
  patchPack(p => {
    const o = side === 'sales' ? p.salesOverall : p.purchaseOverall
    if (field === 'taxInclusiveBase') o.taxInclusiveBase = Number(value) || 0
    else o.remark = String(value ?? '')
  })
}

function updateDist(
  side: 'sales' | 'purchase',
  field: 'totalAmount' | 'txnCount' | 'remark',
  value: number | string,
): void {
  patchPack(p => {
    const d = side === 'sales' ? p.salesDist : p.purchaseDist
    if (field === 'remark') d.remark = String(value ?? '')
    else d[field] = Number(value) || 0
  })
}

function updateStratum(
  side: 'sales' | 'purchase',
  id: string,
  field: keyof StratumRow,
  value: string | number,
): void {
  patchPack(p => {
    const d = side === 'sales' ? p.salesDist : p.purchaseDist
    const row = d.strata.find(s => s.id === id)
    if (!row) return
    if (field === 'label') row.label = String(value)
    else if (field === 'current' || field === 'prior') row[field] = Number(value) || 0
  })
}

function addStratum(side: 'sales' | 'purchase'): void {
  patchPack(p => {
    const d = side === 'sales' ? p.salesDist : p.purchaseDist
    d.strata.push({
      id: `st-${Date.now()}-${Math.random().toString(36).slice(2, 5)}`,
      label: '…万元',
      current: 0,
      prior: 0,
    })
  })
}

function removeStratum(side: 'sales' | 'purchase', id: string): void {
  patchPack(p => {
    const d = side === 'sales' ? p.salesDist : p.purchaseDist
    if (d.strata.length <= 1) return
    d.strata = d.strata.filter(s => s.id !== id)
  })
}

function updateProfile(
  side: 'sales' | 'purchase',
  key: string,
  field: 'value' | 'remark',
  value: string | number,
): void {
  patchPack(p => {
    const list = side === 'sales' ? p.salesProfile : p.purchaseProfile
    const row = list.find(r => r.key === key)
    if (!row) return
    if (field === 'remark') row.remark = String(value ?? '')
    else row.value = value
  })
}

function setReasonableness(val: string): void {
  patchPack(p => { p.reasonablenessNote = val ?? '' })
}

function setOverallRemark(val: string): void {
  patchPack(p => { p.overallRemark = val ?? '' })
}

function onNoteInput(v: string): void {
  if (props.isReadonly) return
  auditNote.value = v ?? ''
}

function onConclusionInput(v: string): void {
  if (props.isReadonly) return
  auditConclusion.value = v ?? ''
}

function aiContext(): Record<string, unknown> {
  return {
    底稿: 'E1-26 现金交易分析',
    现金销售合计本期: salesView.value.totalCurrent,
    现金销售合计上期: salesView.value.totalPrior,
    现金销售占收入比重: salesShare.value,
    现金采购合计本期: purchaseView.value.totalCurrent,
    现金采购合计上期: purchaseView.value.totalPrior,
    现金采购占支出比重: purchaseShare.value,
    高现金占比信号: highCashShare.value,
    合理性分析: pack.value.reasonablenessNote,
    销售分布: pack.value.salesDist,
    采购分布: pack.value.purchaseDist,
    销售概要: pack.value.salesProfile,
    采购概要: pack.value.purchaseProfile,
  }
}

async function generateAi(target: 'reason' | 'note' | 'conclusion'): Promise<void> {
  if (props.isReadonly) return
  const map = {
    reason: {
      section: 'e1-26-reasonableness',
      prompt: '请根据现金销售/采购月度规模、占收入或支出比重、金额分布与客户供应商概要，草拟「现金交易合理性分析」。说明现金交易原因、行业结算惯例、比例是否合理、是否匹配业务性质。不要虚构未提供事实，不要写正式审计结论。',
      existing: pack.value.reasonablenessNote,
      title: 'AI 生成合理性分析',
    },
    note: {
      section: 'e1-26-audit-note',
      prompt: '请生成审计说明：写总体规模与占比、合理性判断要点、大额/分层/仅现客户或供应商的关注，以及关联方提示。不要写正式结论。',
      existing: auditNote.value,
      title: 'AI 生成审计说明',
    },
    conclusion: {
      section: 'e1-26-audit-conclusion',
      prompt: '请生成审计结论，优先采用三档表述之一：A 模式匹配未见体外循环/虚构业务迹象；B 除下列异常外未见异常（列出异常）；C 发现舞弊迹象已扩大测试。不要虚构。',
      existing: auditConclusion.value,
      title: 'AI 生成审计结论',
    },
  } as const
  const cfg = map[target]
  const text = await generateText({
    section: cfg.section,
    prompt: cfg.prompt,
    context: aiContext(),
    existingContent: cfg.existing,
    confirmTitle: cfg.title,
  })
  if (!text) return
  if (target === 'reason') setReasonableness(text)
  else if (target === 'note') {
    auditNote.value = text
    saveNote(text)
  } else {
    auditConclusion.value = text
    saveConclusion(text)
  }
}

async function handleImport(file: File): Promise<boolean> {
  const res = await importData(file)
  if (res.success) {
    ElMessage.success(res.message || '导入成功')
    await reloadWorkpaperData?.()
    load()
  } else {
    ElMessage.warning(res.message || '导入失败')
  }
  return false
}
</script>

<template>
  <E1IpoSheetChrome
    class="e1-tab-cash-txn"
    title="现金交易分析 (E1-26)"
    :is-applicable="isApplicable"
    :is-readonly="isReadonly"
    :is-loading="isLoading"
    :project-id="projectId"
    :index-chips="['wp:E1-27', 'wp:E1-28', 'wp:E1-32']"
    :is-importing="isImporting"
    @update:applicable="setApplicable"
    @export-template="exportTemplate"
    @export-data="exportData"
    @import="handleImport"
  >
    <template #guidance>
      <details class="guidance-details">
        <summary>📋 编制提示</summary>
        <div class="guidance-content">
          <p>1. 本表用于 IPO/上市/新三板/重组或对货币资金存舞弊疑虑时，分析现金交易模式与结构。</p>
          <p>2. 先填（一）月度现金销售/采购，再计算占比；比重偏高必须写透（二）合理性。</p>
          <p>3. （三）分层按发行人情况自定金额档；（四）关注仅现客户/供应商与前50集中度。</p>
          <p>4. 与收入确认、流程内控、关联方资金往来交叉印证；必要时衔接 E1-27～E1-32。</p>
        </div>
      </details>
    </template>

    <template #goal>
      <el-alert
        type="info"
        :closable="false"
        class="mb8"
        title="审计目标：1.资产负债表中记录的货币资金是存在的，且已记录于恰当的账户；2.货币资金以恰当的金额包括在财务报表中，相关计价或分摊调整及披露已恰当计量和描述。"
      />
    </template>

    <template #status>
      <el-tag v-if="isApplicable && highCashShare" size="small" type="danger">现金占比偏高（≥30%）</el-tag>
    </template>

        <!-- （一）月度总体 -->
        <el-card shadow="never" class="section-card">
          <template #header>
            <span class="section-title">（一）现金销售收款、采购付款的总体情况</span>
          </template>
          <div class="dual-grid">
            <div>
              <div class="side-title">现金销售收款的总体情况</div>
              <el-table :data="salesView.rows" border size="small" max-height="420">
                <el-table-column prop="month" label="月份" width="60" align="center" />
                <el-table-column label="本期金额" min-width="110">
                  <template #default="{ row }">
                    <el-input-number
                      :model-value="row.current"
                      :disabled="isReadonly"
                      :controls="false"
                      size="small"
                      style="width: 100%"
                      @update:model-value="(v: number | undefined) => updateMonth('sales', row.month, 'current', Number(v) || 0)"
                    />
                  </template>
                </el-table-column>
                <el-table-column label="上期金额" min-width="110">
                  <template #default="{ row }">
                    <el-input-number
                      :model-value="row.prior"
                      :disabled="isReadonly"
                      :controls="false"
                      size="small"
                      style="width: 100%"
                      @update:model-value="(v: number | undefined) => updateMonth('sales', row.month, 'prior', Number(v) || 0)"
                    />
                  </template>
                </el-table-column>
                <el-table-column label="上上期" min-width="100">
                  <template #default="{ row }">
                    <el-input-number
                      :model-value="row.prior2"
                      :disabled="isReadonly"
                      :controls="false"
                      size="small"
                      style="width: 100%"
                      @update:model-value="(v: number | undefined) => updateMonth('sales', row.month, 'prior2', Number(v) || 0)"
                    />
                  </template>
                </el-table-column>
                <el-table-column label="本期变动" width="90" align="right">
                  <template #default="{ row }">{{ formatPct(row.change) }}</template>
                </el-table-column>
                <el-table-column label="上期变动" width="90" align="right">
                  <template #default="{ row }">{{ formatPct(row.priorChange) }}</template>
                </el-table-column>
              </el-table>
              <div class="summary-lines">
                <div>合计：本期 {{ fmtAmt(salesView.totalCurrent) }} / 上期 {{ fmtAmt(salesView.totalPrior) }}
                  （变动 {{ formatPct(salesView.totalChange) }}）</div>
                <div class="summary-edit">
                  <span>当期含税收入</span>
                  <el-input-number
                    :model-value="pack.salesOverall.taxInclusiveBase"
                    :disabled="isReadonly"
                    :controls="false"
                    size="small"
                    @update:model-value="(v: number | undefined) => updateOverall('sales', 'taxInclusiveBase', Number(v) || 0)"
                  />
                </div>
                <div>月均金额：{{ fmtAmt(salesView.monthlyAvg) }}</div>
                <div :class="{ warn: salesShare != null && salesShare >= 0.3 }">
                  占当期比重：{{ formatPct(salesShare) }}
                </div>
              </div>
            </div>

            <div>
              <div class="side-title">现金采购付款的总体情况</div>
              <el-table :data="purchaseView.rows" border size="small" max-height="420">
                <el-table-column prop="month" label="月份" width="60" align="center" />
                <el-table-column label="本期金额" min-width="110">
                  <template #default="{ row }">
                    <el-input-number
                      :model-value="row.current"
                      :disabled="isReadonly"
                      :controls="false"
                      size="small"
                      style="width: 100%"
                      @update:model-value="(v: number | undefined) => updateMonth('purchase', row.month, 'current', Number(v) || 0)"
                    />
                  </template>
                </el-table-column>
                <el-table-column label="上期金额" min-width="110">
                  <template #default="{ row }">
                    <el-input-number
                      :model-value="row.prior"
                      :disabled="isReadonly"
                      :controls="false"
                      size="small"
                      style="width: 100%"
                      @update:model-value="(v: number | undefined) => updateMonth('purchase', row.month, 'prior', Number(v) || 0)"
                    />
                  </template>
                </el-table-column>
                <el-table-column label="上上期" min-width="100">
                  <template #default="{ row }">
                    <el-input-number
                      :model-value="row.prior2"
                      :disabled="isReadonly"
                      :controls="false"
                      size="small"
                      style="width: 100%"
                      @update:model-value="(v: number | undefined) => updateMonth('purchase', row.month, 'prior2', Number(v) || 0)"
                    />
                  </template>
                </el-table-column>
                <el-table-column label="本期变动" width="90" align="right">
                  <template #default="{ row }">{{ formatPct(row.change) }}</template>
                </el-table-column>
                <el-table-column label="上期变动" width="90" align="right">
                  <template #default="{ row }">{{ formatPct(row.priorChange) }}</template>
                </el-table-column>
              </el-table>
              <div class="summary-lines">
                <div>合计：本期 {{ fmtAmt(purchaseView.totalCurrent) }} / 上期 {{ fmtAmt(purchaseView.totalPrior) }}
                  （变动 {{ formatPct(purchaseView.totalChange) }}）</div>
                <div class="summary-edit">
                  <span>当期含税支出</span>
                  <el-input-number
                    :model-value="pack.purchaseOverall.taxInclusiveBase"
                    :disabled="isReadonly"
                    :controls="false"
                    size="small"
                    @update:model-value="(v: number | undefined) => updateOverall('purchase', 'taxInclusiveBase', Number(v) || 0)"
                  />
                </div>
                <div>月均金额：{{ fmtAmt(purchaseView.monthlyAvg) }}</div>
                <div :class="{ warn: purchaseShare != null && purchaseShare >= 0.3 }">
                  占当期比重：{{ formatPct(purchaseShare) }}
                </div>
              </div>
            </div>
          </div>
          <el-input
            class="mt8"
            :model-value="pack.overallRemark"
            :disabled="isReadonly"
            type="textarea"
            :autosize="{ minRows: 2 }"
            placeholder="备注（可选）"
            @update:model-value="setOverallRemark"
          />
        </el-card>

        <!-- （二）合理性 -->
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="card-header">
              <span class="section-title">（二）现金销售、采购合理性分析</span>
              <el-button size="small" text type="primary" :disabled="isReadonly" :loading="isGenerating('e1-26-reasonableness')" @click="generateAi('reason')">
                <el-icon><MagicStick /></el-icon> AI辅助
              </el-button>
            </div>
          </template>
          <p class="guide-q">现金交易的原因、所在行业常用的结算方式、现金交易比例较高的合理性、是否与其业务性质相匹配？</p>
          <el-input
            type="textarea"
            :model-value="pack.reasonablenessNote"
            :disabled="isReadonly"
            :autosize="{ minRows: 5 }"
            placeholder="根据业务性质与行业惯例说明现金交易合理性…"
            @update:model-value="setReasonableness"
          />
        </el-card>

        <!-- （三）金额分布 -->
        <el-card shadow="never" class="section-card">
          <template #header>
            <span class="section-title">（三）现金销售收款、采购付款的金额分布情况</span>
          </template>
          <div class="dual-grid">
            <div>
              <div class="side-title">现金销售收款</div>
              <el-form label-width="110px" size="small">
                <el-form-item label="现金销售总额">
                  <el-input-number :model-value="pack.salesDist.totalAmount" :disabled="isReadonly" :controls="false" @update:model-value="(v: number | undefined) => updateDist('sales', 'totalAmount', Number(v) || 0)" />
                </el-form-item>
                <el-form-item label="现金销售笔数">
                  <el-input-number :model-value="pack.salesDist.txnCount" :disabled="isReadonly" :controls="false" @update:model-value="(v: number | undefined) => updateDist('sales', 'txnCount', Number(v) || 0)" />
                </el-form-item>
                <el-form-item label="平均每笔金额">
                  <span>{{ fmtAmt(salesAvgPerTxn) }}</span>
                </el-form-item>
              </el-form>
              <div class="strata-bar">
                <span>其中（金额分层，按发行人确定）</span>
                <el-button size="small" :disabled="isReadonly" @click="addStratum('sales')">加档</el-button>
              </div>
              <el-table :data="pack.salesDist.strata" border size="small">
                <el-table-column label="分层" min-width="120">
                  <template #default="{ row }">
                    <el-input :model-value="row.label" :disabled="isReadonly" size="small" @update:model-value="(v: string) => updateStratum('sales', row.id, 'label', v)" />
                  </template>
                </el-table-column>
                <el-table-column label="本期金额" min-width="110">
                  <template #default="{ row }">
                    <el-input-number :model-value="row.current" :disabled="isReadonly" :controls="false" size="small" style="width:100%" @update:model-value="(v: number | undefined) => updateStratum('sales', row.id, 'current', Number(v) || 0)" />
                  </template>
                </el-table-column>
                <el-table-column label="上期金额" min-width="110">
                  <template #default="{ row }">
                    <el-input-number :model-value="row.prior" :disabled="isReadonly" :controls="false" size="small" style="width:100%" @update:model-value="(v: number | undefined) => updateStratum('sales', row.id, 'prior', Number(v) || 0)" />
                  </template>
                </el-table-column>
                <el-table-column label="本期变动" width="90" align="right">
                  <template #default="{ row }">{{ formatPct(row.prior === 0 ? (row.current === 0 ? 0 : null) : (row.current - row.prior) / row.prior) }}</template>
                </el-table-column>
                <el-table-column width="60" align="center">
                  <template #default="{ row }">
                    <el-button v-if="!isReadonly" text type="danger" size="small" @click="removeStratum('sales', row.id)">删</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
            <div>
              <div class="side-title">现金采购付款</div>
              <el-form label-width="110px" size="small">
                <el-form-item label="现金采购总额">
                  <el-input-number :model-value="pack.purchaseDist.totalAmount" :disabled="isReadonly" :controls="false" @update:model-value="(v: number | undefined) => updateDist('purchase', 'totalAmount', Number(v) || 0)" />
                </el-form-item>
                <el-form-item label="现金采购笔数">
                  <el-input-number :model-value="pack.purchaseDist.txnCount" :disabled="isReadonly" :controls="false" @update:model-value="(v: number | undefined) => updateDist('purchase', 'txnCount', Number(v) || 0)" />
                </el-form-item>
                <el-form-item label="平均每笔金额">
                  <span>{{ fmtAmt(purchaseAvgPerTxn) }}</span>
                </el-form-item>
              </el-form>
              <div class="strata-bar">
                <span>其中（金额分层）</span>
                <el-button size="small" :disabled="isReadonly" @click="addStratum('purchase')">加档</el-button>
              </div>
              <el-table :data="pack.purchaseDist.strata" border size="small">
                <el-table-column label="分层" min-width="120">
                  <template #default="{ row }">
                    <el-input :model-value="row.label" :disabled="isReadonly" size="small" @update:model-value="(v: string) => updateStratum('purchase', row.id, 'label', v)" />
                  </template>
                </el-table-column>
                <el-table-column label="本期金额" min-width="110">
                  <template #default="{ row }">
                    <el-input-number :model-value="row.current" :disabled="isReadonly" :controls="false" size="small" style="width:100%" @update:model-value="(v: number | undefined) => updateStratum('purchase', row.id, 'current', Number(v) || 0)" />
                  </template>
                </el-table-column>
                <el-table-column label="上期金额" min-width="110">
                  <template #default="{ row }">
                    <el-input-number :model-value="row.prior" :disabled="isReadonly" :controls="false" size="small" style="width:100%" @update:model-value="(v: number | undefined) => updateStratum('purchase', row.id, 'prior', Number(v) || 0)" />
                  </template>
                </el-table-column>
                <el-table-column label="本期变动" width="90" align="right">
                  <template #default="{ row }">{{ formatPct(row.prior === 0 ? (row.current === 0 ? 0 : null) : (row.current - row.prior) / row.prior) }}</template>
                </el-table-column>
                <el-table-column width="60" align="center">
                  <template #default="{ row }">
                    <el-button v-if="!isReadonly" text type="danger" size="small" @click="removeStratum('purchase', row.id)">删</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </div>
        </el-card>

        <!-- （四）概要 -->
        <el-card shadow="never" class="section-card">
          <template #header>
            <span class="section-title">（四）现金销售收入、采购付款概要分析表</span>
          </template>
          <div class="dual-grid">
            <div>
              <div class="side-title">现金销售收入概要分析表</div>
              <el-table :data="pack.salesProfile" border size="small">
                <el-table-column prop="label" label="项目" min-width="200" />
                <el-table-column label="本期" min-width="140">
                  <template #default="{ row }">
                    <el-input
                      :model-value="String(row.value ?? '')"
                      :disabled="isReadonly"
                      size="small"
                      :placeholder="row.isRatio ? '如 0.25 或 25%' : '金额/数量'"
                      @update:model-value="(v: string) => updateProfile('sales', row.key, 'value', v)"
                    />
                  </template>
                </el-table-column>
                <el-table-column label="备注" min-width="120">
                  <template #default="{ row }">
                    <el-input :model-value="row.remark" :disabled="isReadonly" size="small" @update:model-value="(v: string) => updateProfile('sales', row.key, 'remark', v)" />
                  </template>
                </el-table-column>
              </el-table>
            </div>
            <div>
              <div class="side-title">现金采购付款概要分析表</div>
              <el-table :data="pack.purchaseProfile" border size="small">
                <el-table-column prop="label" label="项目" min-width="200" />
                <el-table-column label="本期" min-width="140">
                  <template #default="{ row }">
                    <el-input
                      :model-value="String(row.value ?? '')"
                      :disabled="isReadonly"
                      size="small"
                      :placeholder="row.isRatio ? '如 0.25 或 25%' : '金额/数量'"
                      @update:model-value="(v: string) => updateProfile('purchase', row.key, 'value', v)"
                    />
                  </template>
                </el-table-column>
                <el-table-column label="备注" min-width="120">
                  <template #default="{ row }">
                    <el-input :model-value="row.remark" :disabled="isReadonly" size="small" @update:model-value="(v: string) => updateProfile('purchase', row.key, 'remark', v)" />
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </div>
        </el-card>

        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="card-header">
              <span>三、审计说明</span>
              <el-button size="small" text type="primary" :disabled="isReadonly" :loading="isGenerating('e1-26-audit-note')" @click="generateAi('note')">
                <el-icon><MagicStick /></el-icon> AI辅助
              </el-button>
            </div>
          </template>
          <el-input
            type="textarea"
            :model-value="auditNote"
            :disabled="isReadonly"
            :autosize="{ minRows: 5 }"
            placeholder="写过程与分析（规模占比、合理性、分层与仅现对象等），不要写正式结论"
            @update:model-value="onNoteInput"
            @change="saveNote(auditNote)"
          />
        </el-card>

        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="card-header">
              <span>四、审计结论</span>
              <el-button size="small" text type="primary" :disabled="isReadonly" :loading="isGenerating('e1-26-audit-conclusion')" @click="generateAi('conclusion')">
                <el-icon><MagicStick /></el-icon> AI辅助
              </el-button>
            </div>
          </template>
          <el-input
            type="textarea"
            :model-value="auditConclusion"
            :disabled="isReadonly"
            :autosize="{ minRows: 3 }"
            placeholder="A 匹配未见异常 / B 除下列异常 / C 舞弊迹象已扩大测试"
            @update:model-value="onConclusionInput"
            @change="saveConclusion(auditConclusion)"
          />
        </el-card>

        <el-alert type="warning" :closable="false" class="tips-alert">
          <template #title>提示</template>
          <p v-for="(t, i) in TIPS" :key="i">{{ i + 1 }}. {{ t }}</p>
        </el-alert>
  </E1IpoSheetChrome>
</template>

<style scoped>
.e1-tab-cash-txn { padding: 12px 0; }
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.mb8 { margin-bottom: 8px; }
.mt8 { margin-top: 8px; }
.section-card { margin-top: 12px; }
.section-title { font-weight: 600; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.dual-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
@media (max-width: 1200px) {
  .dual-grid { grid-template-columns: 1fr; }
}
.side-title { font-weight: 500; margin-bottom: 8px; color: #303133; }
.summary-lines {
  margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.8;
}
.summary-edit { display: flex; align-items: center; gap: 8px; }
.warn { color: #e6a23c; font-weight: 600; }
.guide-q { color: #c0392b; font-size: 13px; margin: 0 0 8px; }
.strata-bar {
  display: flex; justify-content: space-between; align-items: center;
  margin: 8px 0; font-size: 13px;
}
.tips-alert { margin-top: 12px; }
.tips-alert p { margin: 2px 0; font-size: 13px; }
</style>
