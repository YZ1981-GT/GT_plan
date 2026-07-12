<!--
  I3TabInitialValue.vue — I3-4 入账价值测算表（22行13列12公式）
  
  结构：Form-style table per investee
  Row Group 1: 合并成本 = 对价 + 或有对价 + 交易费用 (subtotal formula)
  Row Group 2: 被购方可辨认净资产公允价值 (breakdown rows)
  Row Group 3: 商誉 = 合并成本 - 可辨认净资产公允 (formula result, highlighted)
  
  Features:
  - 12 formula cells (dashed underline + tooltip)
  - Dynamic investee rows (+新增 button with ElMessageBox prompt)
  - Blue gradient guidance area (初始确认规则)
  - 琥珀色方法论 block: CAS20企业合并规则
  - GtIndexChip links to I3-2 明细表
  - Table font 13px

  Spec: .kiro/specs/i3-goodwill/ Task 4.5
  Requirements: 4.1~4.3
-->
<template>
  <div class="i3-initial-value">
    <!-- Section Header -->
    <div class="section-header">
      <span class="section-title">I3-4 入账价值测算表</span>
      <div class="section-actions">
        <el-button size="small" type="primary" text @click="handleAiSuggest">
          <el-icon><MagicStick /></el-icon> AI建议
        </el-button>
        <el-button size="small" type="default" text @click="handleReview">
          💬复核
        </el-button>
      </div>
    </div>

    <!-- 蓝色渐变引导区：初始确认规则说明 -->
    <div class="guide-panel">
      <div class="guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>商誉初始确认规则（CAS20非同一控制下企业合并）</span>
      </div>
      <div class="guide-body">
        <div class="guide-grid">
          <div class="guide-step">
            <span class="step-num">①</span>
            <span class="step-text"><strong>确定合并成本</strong> — 对价 + 或有对价 + 直接交易费用</span>
          </div>
          <div class="guide-step">
            <span class="step-num">②</span>
            <span class="step-text"><strong>确定可辨认净资产公允价值</strong> — 被购方可辨认资产、负债的公允价值之差 × 持股比例</span>
          </div>
          <div class="guide-step">
            <span class="step-num">③</span>
            <span class="step-text"><strong>计算商誉</strong> — 合并成本 − 可辨认净资产公允价值份额 = 商誉（正数）</span>
          </div>
          <div class="guide-step">
            <span class="step-num">④</span>
            <span class="step-text"><strong>核对入账</strong> — 比较初始确认金额与I3-2明细表的一致性</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 琥珀色方法论区块：CAS20企业合并规则 -->
    <div class="methodology-block">
      <div class="methodology-content">
        <strong>CAS20企业合并 — 非同一控制下合并商誉确认</strong><br>
        合并成本：购买方在购买日为取得对被购买方的控制权而付出的资产、发生或承担的负债以及发行的权益性证券的公允价值之和。<br>
        商誉 = 合并成本 &gt; 被购买方可辨认净资产公允价值中属于购买方份额的差额。<br>
        若合并成本 &lt; 净资产公允价值份额，差额计入当期损益（负商誉/营业外收入）。
      </div>
    </div>

    <!-- 被投资单位动态选择 + 新增 -->
    <div class="investee-toolbar">
      <span class="toolbar-label">被投资单位：</span>
      <el-select
        v-model="selectedInvestee"
        placeholder="选择被投资单位"
        size="default"
        style="width: 280px"
        @change="onInvesteeChange"
      >
        <el-option
          v-for="inv in investeeList"
          :key="inv"
          :label="inv"
          :value="inv"
        />
      </el-select>
      <el-button size="small" type="primary" plain @click="handleAddInvestee">
        + 新增
      </el-button>
      <el-button size="small" type="danger" plain :disabled="!selectedInvestee" @click="handleRemoveInvestee">
        删除
      </el-button>
      <GtIndexChip value="I3-2" style="margin-left: 12px" @click="emit('navigate-sheet', 'I3-2 明细表')" />
    </div>

    <!-- 入账测算主表（当选中被投资单位时） -->
    <div v-if="selectedInvestee && currentData" class="calc-table-wrapper">
      <table class="calc-table">
        <thead>
          <tr>
            <th class="col-label">项目</th>
            <th class="col-value">金额（元）</th>
            <th class="col-note">备注</th>
          </tr>
        </thead>
        <tbody>
          <!-- ═══ Row Group 1: 合并成本 ═══ -->
          <tr class="group-header-row">
            <td colspan="3" class="group-header">一、合并成本</td>
          </tr>
          <tr>
            <td class="row-label indent-1">1. 支付对价（公允价值）</td>
            <td class="row-value">
              <el-input-number
                :model-value="currentData.consideration"
                :controls="false"
                size="small"
                :disabled="isReadonly"
                style="width: 100%"
                @update:model-value="(v) => updateField('consideration', v ?? 0)"
              />
            </td>
            <td class="row-note">
              <el-input
                :model-value="currentData.considerationNote"
                size="small"
                :disabled="isReadonly"
                placeholder="现金/股权/资产对价"
                @change="(v: string) => updateField('considerationNote', v)"
              />
            </td>
          </tr>
          <tr>
            <td class="row-label indent-1">2. 或有对价（公允价值）</td>
            <td class="row-value">
              <el-input-number
                :model-value="currentData.contingentConsideration"
                :controls="false"
                size="small"
                :disabled="isReadonly"
                style="width: 100%"
                @update:model-value="(v) => updateField('contingentConsideration', v ?? 0)"
              />
            </td>
            <td class="row-note">
              <el-input
                :model-value="currentData.contingentNote"
                size="small"
                :disabled="isReadonly"
                placeholder="业绩承诺/对赌安排等"
                @change="(v: string) => updateField('contingentNote', v)"
              />
            </td>
          </tr>
          <tr>
            <td class="row-label indent-1">3. 直接交易费用</td>
            <td class="row-value">
              <el-input-number
                :model-value="currentData.transactionCost"
                :controls="false"
                size="small"
                :disabled="isReadonly"
                style="width: 100%"
                @update:model-value="(v) => updateField('transactionCost', v ?? 0)"
              />
            </td>
            <td class="row-note">
              <el-input
                :model-value="currentData.transactionCostNote"
                size="small"
                :disabled="isReadonly"
                placeholder="审计/评估/法律费用等"
                @change="(v: string) => updateField('transactionCostNote', v)"
              />
            </td>
          </tr>
          <!-- F1: 合并成本小计 -->
          <tr class="subtotal-row">
            <td class="row-label indent-0"><strong>合并成本合计</strong></td>
            <td class="row-value">
              <span class="formula-cell" :title="formulaTooltips.mergerCost">
                {{ fmtNum(mergerCost) }}
              </span>
            </td>
            <td class="row-note formula-note">= 对价 + 或有对价 + 交易费用</td>
          </tr>

          <!-- ═══ Row Group 2: 被购方可辨认净资产公允价值 ═══ -->
          <tr class="group-header-row">
            <td colspan="3" class="group-header">二、被购方可辨认净资产公允价值</td>
          </tr>
          <tr>
            <td class="row-label indent-1">1. 资产公允价值合计</td>
            <td class="row-value">
              <el-input-number
                :model-value="currentData.totalAssetsFV"
                :controls="false"
                size="small"
                :disabled="isReadonly"
                style="width: 100%"
                @update:model-value="(v) => updateField('totalAssetsFV', v ?? 0)"
              />
            </td>
            <td class="row-note">
              <el-input
                :model-value="currentData.totalAssetsFVNote"
                size="small"
                :disabled="isReadonly"
                placeholder="被购方全部可辨认资产FV"
                @change="(v: string) => updateField('totalAssetsFVNote', v)"
              />
            </td>
          </tr>
          <tr>
            <td class="row-label indent-1">2. 负债公允价值合计</td>
            <td class="row-value">
              <el-input-number
                :model-value="currentData.totalLiabilitiesFV"
                :controls="false"
                size="small"
                :disabled="isReadonly"
                style="width: 100%"
                @update:model-value="(v) => updateField('totalLiabilitiesFV', v ?? 0)"
              />
            </td>
            <td class="row-note">
              <el-input
                :model-value="currentData.totalLiabilitiesFVNote"
                size="small"
                :disabled="isReadonly"
                placeholder="被购方全部可辨认负债FV"
                @change="(v: string) => updateField('totalLiabilitiesFVNote', v)"
              />
            </td>
          </tr>
          <!-- F2: 可辨认净资产公允价值 = 资产FV - 负债FV -->
          <tr class="subtotal-row">
            <td class="row-label indent-0"><strong>可辨认净资产公允价值</strong></td>
            <td class="row-value">
              <span class="formula-cell" :title="formulaTooltips.netAssetFV">
                {{ fmtNum(netAssetFV) }}
              </span>
            </td>
            <td class="row-note formula-note">= 资产FV - 负债FV</td>
          </tr>
          <tr>
            <td class="row-label indent-1">3. 持股比例(%)</td>
            <td class="row-value">
              <el-input-number
                :model-value="currentData.equityRatio"
                :controls="false"
                :precision="2"
                :min="0"
                :max="100"
                size="small"
                :disabled="isReadonly"
                style="width: 100%"
                @update:model-value="(v) => updateField('equityRatio', v ?? 0)"
              />
            </td>
            <td class="row-note">
              <el-input
                :model-value="currentData.equityRatioNote"
                size="small"
                :disabled="isReadonly"
                placeholder="购买方持股比例"
                @change="(v: string) => updateField('equityRatioNote', v)"
              />
            </td>
          </tr>
          <!-- F3: 净资产公允价值份额 = 净资产FV × 持股比例 -->
          <tr class="subtotal-row">
            <td class="row-label indent-0"><strong>可辨认净资产公允价值份额</strong></td>
            <td class="row-value">
              <span class="formula-cell" :title="formulaTooltips.netAssetFVShare">
                {{ fmtNum(netAssetFVShare) }}
              </span>
            </td>
            <td class="row-note formula-note">= 净资产FV × 持股比例</td>
          </tr>

          <!-- ═══ Row Group 3: 商誉 ═══ -->
          <tr class="group-header-row">
            <td colspan="3" class="group-header">三、商誉（初始确认）</td>
          </tr>
          <!-- F4: 商誉 = 合并成本 - 净资产公允价值份额 -->
          <tr class="goodwill-result-row">
            <td class="row-label indent-0"><strong>商誉</strong></td>
            <td class="row-value">
              <span class="formula-cell goodwill-value" :title="formulaTooltips.goodwill">
                {{ fmtNum(goodwillAmount) }}
              </span>
            </td>
            <td class="row-note formula-note">= 合并成本 − 净资产公允价值份额</td>
          </tr>
          <!-- 负商誉告警 -->
          <tr v-if="goodwillAmount < 0" class="warning-row">
            <td colspan="3" class="negative-goodwill-warning">
              ⚠️ 合并成本 &lt; 净资产公允价值份额，产生"负商誉"（计入营业外收入，需重点关注评估报告公允性）
            </td>
          </tr>

          <!-- ═══ 补充信息行 ═══ -->
          <tr class="group-header-row">
            <td colspan="3" class="group-header">四、补充信息</td>
          </tr>
          <tr>
            <td class="row-label indent-1">购买日期</td>
            <td class="row-value">
              <el-date-picker
                :model-value="currentData.acquisitionDate"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                :disabled="isReadonly"
                style="width: 100%"
                @update:model-value="(v) => updateField('acquisitionDate', v ?? '')"
              />
            </td>
            <td class="row-note">
              <el-input
                :model-value="currentData.acquisitionDateNote"
                size="small"
                :disabled="isReadonly"
                placeholder="合并协议生效日"
                @change="(v: string) => updateField('acquisitionDateNote', v)"
              />
            </td>
          </tr>
          <tr>
            <td class="row-label indent-1">评估机构</td>
            <td class="row-value" colspan="1">
              <el-input
                :model-value="currentData.appraiser"
                size="small"
                :disabled="isReadonly"
                placeholder="评估机构名称"
                @change="(v: string) => updateField('appraiser', v)"
              />
            </td>
            <td class="row-note">
              <el-input
                :model-value="currentData.appraiserNote"
                size="small"
                :disabled="isReadonly"
                placeholder="评估报告编号"
                @change="(v: string) => updateField('appraiserNote', v)"
              />
            </td>
          </tr>
          <tr>
            <td class="row-label indent-1">评估方法</td>
            <td class="row-value" colspan="1">
              <el-select
                :model-value="currentData.valuationMethod"
                size="small"
                :disabled="isReadonly"
                placeholder="选择评估方法"
                style="width: 100%"
                @change="(v: string) => updateField('valuationMethod', v)"
              >
                <el-option label="收益法" value="income" />
                <el-option label="市场法" value="market" />
                <el-option label="资产基础法" value="asset" />
                <el-option label="收益法+市场法" value="income_market" />
              </el-select>
            </td>
            <td class="row-note">
              <el-input
                :model-value="currentData.valuationMethodNote"
                size="small"
                :disabled="isReadonly"
                placeholder="评估方法说明"
                @change="(v: string) => updateField('valuationMethodNote', v)"
              />
            </td>
          </tr>

          <!-- ═══ 勾稽验证 ═══ -->
          <tr class="group-header-row">
            <td colspan="3" class="group-header">五、勾稽验证</td>
          </tr>
          <!-- F5: 与I3-2明细表一致性 -->
          <tr>
            <td class="row-label indent-1">I3-2明细表商誉原值</td>
            <td class="row-value">
              <span class="formula-cell" :title="formulaTooltips.detailGoodwill">
                {{ fmtNum(currentData.detailGoodwillAmount) }}
              </span>
            </td>
            <td class="row-note">
              <GtIndexChip value="I3-2" @click="emit('navigate-sheet', 'I3-2 明细表')" />
              <span class="formula-note" style="margin-left: 8px">从I3-2取数</span>
            </td>
          </tr>
          <!-- F6: 差异 = 本表商誉 - 明细表商誉 -->
          <tr>
            <td class="row-label indent-1">差异（本表 − I3-2）</td>
            <td class="row-value">
              <span
                :class="['formula-cell', reconciliationDiff !== 0 ? 'diff-warning' : 'diff-ok']"
                :title="formulaTooltips.reconciliationDiff"
              >
                {{ fmtNum(reconciliationDiff) }}
              </span>
            </td>
            <td class="row-note formula-note">
              {{ reconciliationDiff === 0 ? '✅ 一致' : '⚠️ 存在差异' }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 无选中被投资单位时 -->
    <div v-else class="no-investee-hint">
      <el-empty description="请选择或新增被投资单位以查看入账价值测算" />
    </div>

    <!-- 审计说明/结论 -->
    <el-card class="conclusion-card" shadow="never" style="margin-top: 16px">
      <template #header>
        <div class="conclusion-header">
          <span>审计说明</span>
          <el-button size="small" :disabled="isReadonly" @click="handleAiConclusion">
            🤖 AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="对入账价值测算的审计说明与结论..."
        @change="persistConclusion"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>合并成本 = 支付对价(FV) + 或有对价(FV) + 直接交易费用</li>
        <li>可辨认净资产FV = 被购方全部可辨认资产FV − 全部可辨认负债FV</li>
        <li>净资产FV份额 = 可辨认净资产FV × 持股比例</li>
        <li>商誉 = 合并成本 − 净资产FV份额（CP-I3-03）</li>
        <li>若商誉&lt;0（负商誉），需重新审阅被购方资产评估是否充分</li>
        <li>与I3-2明细表勾稽确认入账金额一致</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, inject } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { MagicStick, InfoFilled } from '@element-plus/icons-vue'
import { calcInitialGoodwill, calcSubtotal } from '../../composables/useI3FormulaEngine'
import GtIndexChip from '../../GtIndexChip.vue'

// ─── Types ───────────────────────────────────────────────────────────────────

interface InvesteeData {
  /** 支付对价 */
  consideration: number
  considerationNote: string
  /** 或有对价 */
  contingentConsideration: number
  contingentNote: string
  /** 直接交易费用 */
  transactionCost: number
  transactionCostNote: string
  /** 资产公允价值合计 */
  totalAssetsFV: number
  totalAssetsFVNote: string
  /** 负债公允价值合计 */
  totalLiabilitiesFV: number
  totalLiabilitiesFVNote: string
  /** 持股比例(%) */
  equityRatio: number
  equityRatioNote: string
  /** 购买日期 */
  acquisitionDate: string
  acquisitionDateNote: string
  /** 评估机构 */
  appraiser: string
  appraiserNote: string
  /** 评估方法 */
  valuationMethod: string
  valuationMethodNote: string
  /** I3-2明细表商誉原值（跨sheet取数） */
  detailGoodwillAmount: number
}

// ─── Props & Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  'save': [itemId: string, value: any]
  'navigate-sheet': [sheetName: string]
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY = 'I3-4-initial-value'
const CONCLUSION_KEY = 'I3-4-conclusion'

const formulaTooltips = {
  mergerCost: '合并成本 = 对价 + 或有对价 + 交易费用 [F1]',
  netAssetFV: '可辨认净资产FV = 资产FV − 负债FV [F2]',
  netAssetFVShare: '净资产FV份额 = 净资产FV × 持股比例 [F3]',
  goodwill: '商誉 = 合并成本 − 净资产FV份额 (calcInitialGoodwill) [F4]',
  detailGoodwill: '从I3-2明细表取数 [F5]',
  reconciliationDiff: '差异 = 本表商誉 − I3-2明细表商誉 [F6]',
}

// ─── State ───────────────────────────────────────────────────────────────────

const selectedInvestee = ref('')
const auditConclusion = ref('')

/** All investee data: Map<investeeName, InvesteeData> */
const dataMap = ref<Map<string, InvesteeData>>(new Map())

// ─── Load from allResponses ──────────────────────────────────────────────────

function loadData() {
  const raw = props.allResponses.get(STORAGE_KEY)
  if (raw) {
    try {
      const parsed = typeof raw === 'string'
        ? JSON.parse(raw)
        : (raw.remark ? JSON.parse(raw.remark) : raw)
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        const map = new Map<string, InvesteeData>()
        for (const [name, data] of Object.entries(parsed as Record<string, any>)) {
          map.set(name, normalizeInvesteeData(data))
        }
        dataMap.value = map
      }
    } catch { /* ignore parse errors */ }
  }
  // Load conclusion
  const concRaw = props.allResponses.get(CONCLUSION_KEY)
  if (concRaw) {
    auditConclusion.value = typeof concRaw === 'string'
      ? concRaw
      : (concRaw.conclusion ?? concRaw.remark ?? '')
  }
}

watch(() => props.allResponses, () => loadData(), { immediate: true })

// ─── Computed ────────────────────────────────────────────────────────────────

const investeeList = computed(() => Array.from(dataMap.value.keys()))

const currentData = computed<InvesteeData | null>(() => {
  if (!selectedInvestee.value) return null
  return dataMap.value.get(selectedInvestee.value) ?? null
})

/** F1: 合并成本 = 对价 + 或有对价 + 交易费用 */
const mergerCost = computed(() => {
  if (!currentData.value) return 0
  const d = currentData.value
  return calcSubtotal([d.consideration, d.contingentConsideration, d.transactionCost])
})

/** F2: 可辨认净资产FV = 资产FV - 负债FV */
const netAssetFV = computed(() => {
  if (!currentData.value) return 0
  return currentData.value.totalAssetsFV - currentData.value.totalLiabilitiesFV
})

/** F3: 净资产FV份额 = 净资产FV × 持股比例 */
const netAssetFVShare = computed(() => {
  if (!currentData.value) return 0
  return netAssetFV.value * (currentData.value.equityRatio / 100)
})

/** F4: 商誉 = 合并成本 - 净资产FV份额 (核心公式 CP-I3-03) */
const goodwillAmount = computed(() => {
  return calcInitialGoodwill(mergerCost.value, netAssetFVShare.value)
})

/** F6: 勾稽差异 = 本表商誉 - I3-2明细表商誉 */
const reconciliationDiff = computed(() => {
  if (!currentData.value) return 0
  return goodwillAmount.value - (currentData.value.detailGoodwillAmount || 0)
})

// ─── Helpers ─────────────────────────────────────────────────────────────────

function normalizeInvesteeData(raw: any): InvesteeData {
  return {
    consideration: Number(raw?.consideration) || 0,
    considerationNote: raw?.considerationNote ?? '',
    contingentConsideration: Number(raw?.contingentConsideration) || 0,
    contingentNote: raw?.contingentNote ?? '',
    transactionCost: Number(raw?.transactionCost) || 0,
    transactionCostNote: raw?.transactionCostNote ?? '',
    totalAssetsFV: Number(raw?.totalAssetsFV) || 0,
    totalAssetsFVNote: raw?.totalAssetsFVNote ?? '',
    totalLiabilitiesFV: Number(raw?.totalLiabilitiesFV) || 0,
    totalLiabilitiesFVNote: raw?.totalLiabilitiesFVNote ?? '',
    equityRatio: Number(raw?.equityRatio) || 100,
    equityRatioNote: raw?.equityRatioNote ?? '',
    acquisitionDate: raw?.acquisitionDate ?? '',
    acquisitionDateNote: raw?.acquisitionDateNote ?? '',
    appraiser: raw?.appraiser ?? '',
    appraiserNote: raw?.appraiserNote ?? '',
    valuationMethod: raw?.valuationMethod ?? '',
    valuationMethodNote: raw?.valuationMethodNote ?? '',
    detailGoodwillAmount: Number(raw?.detailGoodwillAmount) || 0,
  }
}

function createEmptyInvesteeData(): InvesteeData {
  return normalizeInvesteeData({})
}

function fmtNum(v: unknown): string {
  if (v === 0) return '0.00'
  if (typeof v === 'number') {
    return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(v ?? '')
}

// ─── Events ──────────────────────────────────────────────────────────────────

function onInvesteeChange(_name: string) {
  // Selection changed, computed will auto-update
}

function updateField(field: keyof InvesteeData, value: any) {
  if (!selectedInvestee.value || props.isReadonly) return
  const current = dataMap.value.get(selectedInvestee.value)
  if (!current) return
  ;(current as any)[field] = value
  // Force reactivity
  dataMap.value = new Map(dataMap.value)
  persistData()
}

// ─── Add / Remove Investee ───────────────────────────────────────────────────

async function handleAddInvestee() {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入被投资单位名称',
      '新增被投资单位',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPlaceholder: '例如：XX科技有限公司',
        inputValidator: (v) => {
          if (!v?.trim()) return '名称不能为空'
          if (dataMap.value.has(v.trim())) return '该被投资单位已存在'
          return true
        },
      }
    )
    if (value?.trim()) {
      const name = value.trim()
      dataMap.value.set(name, createEmptyInvesteeData())
      dataMap.value = new Map(dataMap.value)
      selectedInvestee.value = name
      persistData()
      ElMessage.success(`已添加：${name}`)
    }
  } catch {
    // cancelled
  }
}

async function handleRemoveInvestee() {
  if (!selectedInvestee.value) return
  try {
    await ElMessageBox.confirm(
      `确认删除"${selectedInvestee.value}"的入账测算数据？`,
      '删除确认',
      { type: 'warning' }
    )
    dataMap.value.delete(selectedInvestee.value)
    dataMap.value = new Map(dataMap.value)
    selectedInvestee.value = investeeList.value[0] ?? ''
    persistData()
    ElMessage.success('已删除')
  } catch {
    // cancelled
  }
}

// ─── Persistence ─────────────────────────────────────────────────────────────

function persistData() {
  const obj: Record<string, InvesteeData> = {}
  for (const [name, data] of dataMap.value.entries()) {
    obj[name] = { ...data }
  }
  emit('save', STORAGE_KEY, JSON.stringify(obj))
}

function persistConclusion() {
  emit('save', CONCLUSION_KEY, auditConclusion.value)
}

// ─── AI Suggest ──────────────────────────────────────────────────────────────

function handleAiSuggest() {
  if (!selectedInvestee.value) {
    ElMessage.warning('请先选择被投资单位')
    return
  }
  ElMessage.info(`AI正在为"${selectedInvestee.value}"生成入账测算建议...`)
}

function handleAiConclusion() {
  if (!selectedInvestee.value) {
    ElMessage.warning('请先选择被投资单位')
    return
  }
  const d = currentData.value!
  const draft =
    `经测算，"${selectedInvestee.value}"商誉初始确认：` +
    `合并成本 ${fmtNum(mergerCost.value)} 元` +
    `（对价 ${fmtNum(d.consideration)} + 或有对价 ${fmtNum(d.contingentConsideration)} + 交易费用 ${fmtNum(d.transactionCost)}），` +
    `被购方可辨认净资产公允价值份额 ${fmtNum(netAssetFVShare.value)} 元` +
    `（净资产FV ${fmtNum(netAssetFV.value)} × 持股 ${d.equityRatio}%），` +
    `商誉 = ${fmtNum(goodwillAmount.value)} 元。` +
    (reconciliationDiff.value === 0
      ? '与I3-2明细表一致，入账金额正确。'
      : `与I3-2明细表存在差异 ${fmtNum(reconciliationDiff.value)} 元，需进一步核实。`)

  auditConclusion.value = auditConclusion.value
    ? `${auditConclusion.value}\n${draft}`
    : draft
  persistConclusion()
}

// ─── Review ──────────────────────────────────────────────────────────────────

function handleReview() {
  openReviewDialog('I3-4-入账价值测算')
}
</script>

<style scoped>
.i3-initial-value {
  font-size: var(--wp-font-size, 13px);
  padding: 16px;
}

/* Section Header */
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
}
.section-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* 蓝色渐变引导面板 */
.guide-panel {
  background: linear-gradient(135deg, #eff6ff, #dbeafe);
  border: 1px solid #93c5fd;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}
.guide-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: #1e40af;
  margin-bottom: 12px;
}
.guide-body {
  font-size: 12px;
  color: #1e3a5f;
  line-height: 1.6;
}
.guide-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.guide-step {
  display: flex;
  align-items: flex-start;
  gap: 6px;
}
.step-num {
  color: #2563eb;
  font-weight: 700;
  font-size: 14px;
  flex-shrink: 0;
}
.step-text {
  font-size: 12px;
  color: #334155;
}

/* 琥珀色方法论区块 */
.methodology-block {
  border-left: 4px solid #f59e0b;
  background: #fffbeb;
  padding: 12px 16px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
  font-size: 12px;
  line-height: 1.7;
  color: #78350f;
}
.methodology-content strong {
  color: #92400e;
  font-size: var(--wp-font-size, 13px);
}

/* 被投资单位工具栏 */
.investee-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #f9fafb;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  flex-wrap: wrap;
}
.toolbar-label {
  font-weight: 600;
  color: #374151;
  white-space: nowrap;
}

/* 入账测算主表 */
.calc-table-wrapper {
  overflow-x: auto;
  margin-bottom: 16px;
}
.calc-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--wp-font-size, 13px);
}
.calc-table th,
.calc-table td {
  border: 1px solid #e5e7eb;
  padding: 8px 12px;
  text-align: left;
  vertical-align: middle;
}
.calc-table thead th {
  background: #f3f4f6;
  font-weight: 600;
  color: #374151;
  text-align: center;
}
.col-label { width: 220px; }
.col-value { width: 240px; text-align: right; }
.col-note { min-width: 200px; }

/* 行分组标题 */
.group-header-row td {
  background: #f9fafb;
}
.group-header {
  font-weight: 700;
  font-size: var(--wp-font-size, 13px);
  color: #1f2937;
  padding: 10px 12px;
}

/* 缩进 */
.indent-0 { padding-left: 12px; }
.indent-1 { padding-left: 28px; }

/* 行值列 */
.row-value {
  text-align: right;
}
.row-note {
  font-size: 12px;
  color: #6b7280;
}

/* 小计行 */
.subtotal-row td {
  background: #fafafa;
  border-top: 1px solid #d1d5db;
}

/* 公式列：虚线下划线 + cursor:help */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  display: inline-block;
  min-width: 80px;
  text-align: right;
  font-weight: 600;
  color: #1f2937;
  padding: 2px 4px;
}
.formula-note {
  font-size: 11px;
  color: #9ca3af;
  font-style: italic;
}

/* 商誉结果行高亮 */
.goodwill-result-row td {
  background: linear-gradient(135deg, #fef3c7, #fde68a);
  border-top: 2px solid #f59e0b;
  border-bottom: 2px solid #f59e0b;
}
.goodwill-value {
  font-size: 15px;
  font-weight: 700;
  color: #92400e;
  border-bottom-color: #92400e;
}

/* 差异样式 */
.diff-warning {
  color: #dc2626;
  border-bottom-color: #dc2626;
}
.diff-ok {
  color: #16a34a;
  border-bottom-color: #16a34a;
}

/* 负商誉告警 */
.warning-row td {
  background: #fef2f2;
}
.negative-goodwill-warning {
  color: #dc2626;
  font-weight: 600;
  text-align: center;
  padding: 10px;
}

/* 无选中提示 */
.no-investee-hint {
  margin-top: 40px;
}

/* 审计结论 */
.conclusion-card {
  margin-top: 16px;
}
.conclusion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* 编制提示 */
.prep-hint {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
}
.prep-hint summary {
  cursor: pointer;
  font-weight: 500;
}
.prep-hint ul {
  margin: 8px 0 0;
  padding-left: 18px;
  line-height: 1.8;
}
</style>
