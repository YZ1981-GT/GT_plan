<template>
<div class="f1-analysis">
  <details class="guidance-details">
    <summary>📋 编制提示</summary>
    <div class="guidance-content">
      <p>1. 按 Excel F1-4：余额分析 → 借方发生额 → 贷方发生额 → 大额供应商 → 分块说明与结论。</p>
      <p>2. 灰色列为自动计算（变动额/比例、汇总行、占比、期末余额、账面价值）。</p>
      <p>3. 性质拆分可「从 F1-2 汇总」；大额供应商可「从 F1-2 取大额」后补账龄、原因、期后结算。</p>
      <p>4. 大额收回款项、大额期末余额须关注商业合理性与关联方资金占用。</p>
    </div>
  </details>

  <el-alert
    type="info"
    :closable="false"
    title="审计目标：核实预付款项存在性与计价；通过分析余额、借贷发生额及大额供应商，识别异常波动、减值迹象与资金占用风险。"
    class="objective-alert"
  />

  <el-alert
    v-if="top5ConcentrationWarning"
    type="warning"
    :title="top5ConcentrationWarning"
    :closable="false"
    show-icon
    style="margin-bottom: 12px"
  />
  <el-alert
    v-for="(hint, idx) in crossCycleHints"
    :key="'xcycle-' + idx"
    type="warning"
    :title="hint"
    :closable="false"
    show-icon
    style="margin-bottom: 8px"
  />

  <div class="analysis-card linkage-card">
    <div class="card-title-row">
      <h4 class="card-title">跨科目联动锚点（F2 / F4）</h4>
      <el-button
        size="small"
        type="primary"
        plain
        :disabled="isReadonly || !hasTbContext"
        @click="doFillFromTb"
      >从试算表带入余额（存货/应付）</el-button>
    </div>
    <p class="guide-tip">可「从试算表带入」存货余额(1401)与应付账款期末余额(2202)；存货采购金额需手工/从 F2 录入。填入后上方将给出周转与并存勾稽提示。</p>
    <el-table :data="linkageAnchorRows" size="small" border>
      <el-table-column label="项目" min-width="220" prop="label" />
      <el-table-column label="本期" width="140" align="right">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            v-model.number="editBuf['link.' + row.key + '.current']"
            size="small"
            @focus="() => { editBuf['link.' + row.key + '.current'] = row.current }"
            @change="() => commitLinkage(row.key, 'current')"
          />
          <span v-else class="amt">{{ fmtAmount(row.current) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="上期" width="140" align="right">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            v-model.number="editBuf['link.' + row.key + '.prior']"
            size="small"
            @focus="() => { editBuf['link.' + row.key + '.prior'] = row.prior }"
            @change="() => commitLinkage(row.key, 'prior')"
          />
          <span v-else class="amt">{{ fmtAmount(row.prior) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="索引" width="100">
        <template #default="{ row }">
          <span class="chip-wrap"><GtIndexChip :value="row.indexChip" :context-project-id="projectId" /></span>
        </template>
      </el-table-column>
    </el-table>
  </div>

  <div class="tab-toolbar">
    <div class="toolbar-left">
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="fillFromDetail">从 F1-2 汇总性质</el-button>
      <el-button size="small" :disabled="isReadonly" @click="fillMajorSuppliersFromDetail()">从 F1-2 取大额供应商</el-button>
    </div>
    <div class="toolbar-right">
      <span class="chip-wrap"><GtIndexChip value="wp:F1-2" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">大额 {{ supplierRows.length }} 户</el-tag>
    </div>
  </div>

  <F1SheetAttachments
    :project-id="projectId"
    :wp-id="wpId"
    sheet-code="F1-4"
    label="分析表附件"
  />

  <!-- 1. 余额分析 -->
  <div class="analysis-card">
    <h4 class="card-title">1. 预付款项余额分析</h4>
    <el-table :data="balanceRows" size="small" border stripe :row-class-name="periodRowClass">
      <el-table-column label="项目" min-width="280">
        <template #default="{ row }">
          <span :class="{ indent: row.indent }">{{ row.label }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期金额" width="130" align="right">
        <template #default="{ row }">
          <template v-if="row.rowKind === 'ratio'">{{ ratioCurrent(row) }}</template>
          <el-input v-else-if="row.editable && !isReadonly" v-model.number="editBuf[row.rowKey + '.current']" size="small"
            @focus="() => seedEdit(row, 'current')"
            @change="() => commitPeriod('balance', row, 'current')" />
          <span v-else class="amt auto">{{ fmtAmount(row.current) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="上期金额" width="130" align="right">
        <template #default="{ row }">
          <template v-if="row.rowKind === 'ratio'">{{ ratioPrior(row) }}</template>
          <el-input v-else-if="row.editable && !isReadonly" v-model.number="editBuf[row.rowKey + '.prior']" size="small"
            @focus="() => seedEdit(row, 'prior')"
            @change="() => commitPeriod('balance', row, 'prior')" />
          <span v-else class="amt auto">{{ fmtAmount(row.prior) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="变动金额" width="120" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span v-if="row.rowKind !== 'ratio'" class="amt auto">{{ fmtAmount(row.changeAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="变动比例" width="100" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span v-if="row.rowKind !== 'ratio'" :class="{ 'rate-exceed': isRateHigh(row.changeRate) }">{{ fmtRate(row.changeRate) }}</span>
        </template>
      </el-table-column>
    </el-table>
    <div class="note-block">
      <div class="note-label">
        审计说明
        <el-button size="small" :disabled="isReadonly || !aiAvailable || aiLoading" :loading="aiLoading" @click="genNote('balance')">🤖AI</el-button>
      </div>
      <el-input type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" :disabled="isReadonly"
        :model-value="notes.balance" @update:model-value="(v: string) => updateNote('balance', v)"
        placeholder="说明余额结构变动及存货相关预付占比是否合理..." />
    </div>
  </div>

  <!-- 2. 借方发生额 -->
  <div class="analysis-card">
    <h4 class="card-title">2. 预付账款借方发生额分析</h4>
    <el-table :data="debitRows" size="small" border stripe :row-class-name="periodRowClass">
      <el-table-column label="项目" min-width="300">
        <template #default="{ row }">
          <span :class="{ indent: row.indent }">{{ row.indent ? '其中：' + row.label : row.label }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期金额" width="130" align="right">
        <template #default="{ row }">
          <template v-if="row.rowKind === 'ratio'">{{ ratioCurrent(row) }}</template>
          <el-input v-else-if="row.editable && !isReadonly" v-model.number="editBuf['d.' + row.rowKey + '.current']" size="small"
            @focus="() => seedEdit(row, 'current', 'd.')"
            @change="() => commitPeriod('debit', row, 'current')" />
          <span v-else class="amt auto">{{ fmtAmount(row.current) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="上期金额" width="130" align="right">
        <template #default="{ row }">
          <template v-if="row.rowKind === 'ratio'">{{ ratioPrior(row) }}</template>
          <el-input v-else-if="row.editable && !isReadonly" v-model.number="editBuf['d.' + row.rowKey + '.prior']" size="small"
            @focus="() => seedEdit(row, 'prior', 'd.')"
            @change="() => commitPeriod('debit', row, 'prior')" />
          <span v-else class="amt auto">{{ fmtAmount(row.prior) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="变动金额" width="120" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span v-if="row.rowKind !== 'ratio'" class="amt auto">{{ fmtAmount(row.changeAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="变动比例" width="100" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span v-if="row.rowKind !== 'ratio'" :class="{ 'rate-exceed': isRateHigh(row.changeRate) }">{{ fmtRate(row.changeRate) }}</span>
        </template>
      </el-table-column>
    </el-table>
    <div class="note-block">
      <div class="note-label">
        审计说明
        <el-button size="small" :disabled="isReadonly || !aiAvailable || aiLoading" :loading="aiLoading" @click="genNote('debit')">🤖AI</el-button>
      </div>
      <el-input type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" :disabled="isReadonly"
        :model-value="notes.debit" @update:model-value="(v: string) => updateNote('debit', v)"
        placeholder="分析借方新增结构及与存货采购的勾稽关系..." />
    </div>
  </div>

  <!-- 3. 贷方发生额 -->
  <div class="analysis-card">
    <h4 class="card-title">3. 预付账款贷方发生额分析</h4>
    <p class="guide-tip">如存在大额预付账款收回，关注合理性、是否存在关联方资金占用等情形。</p>
    <el-table :data="creditRows" size="small" border stripe :row-class-name="periodRowClass">
      <el-table-column label="项目" min-width="260">
        <template #default="{ row }">
          <span :class="{ indent: row.indent }">{{ row.indent ? (row.rowKey === 'toInventory' ? '其中：' : '') + row.label : row.label }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期金额" width="130" align="right">
        <template #default="{ row }">
          <el-input v-if="row.editable && !isReadonly" v-model.number="editBuf['c.' + row.rowKey + '.current']" size="small"
            @focus="() => seedEdit(row, 'current', 'c.')"
            @change="() => commitPeriod('credit', row, 'current')" />
          <span v-else class="amt auto">{{ fmtAmount(row.current) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="上期金额" width="130" align="right">
        <template #default="{ row }">
          <el-input v-if="row.editable && !isReadonly" v-model.number="editBuf['c.' + row.rowKey + '.prior']" size="small"
            @focus="() => seedEdit(row, 'prior', 'c.')"
            @change="() => commitPeriod('credit', row, 'prior')" />
          <span v-else class="amt auto">{{ fmtAmount(row.prior) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="变动金额" width="120" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="amt auto">{{ fmtAmount(row.changeAmount) }}</span></template>
      </el-table-column>
      <el-table-column label="变动比例" width="100" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span :class="{ 'rate-exceed': isRateHigh(row.changeRate) }">{{ fmtRate(row.changeRate) }}</span>
        </template>
      </el-table-column>
    </el-table>
    <div class="note-block">
      <div class="note-label">
        审计说明
        <el-button size="small" :disabled="isReadonly || !aiAvailable || aiLoading" :loading="aiLoading" @click="genNote('credit')">🤖AI</el-button>
      </div>
      <el-input type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" :disabled="isReadonly"
        :model-value="notes.credit" @update:model-value="(v: string) => updateNote('credit', v)"
        placeholder="说明贷方结转路径；对大额收回款项评价合理性..." />
    </div>
  </div>

  <!-- 4. 大额供应商 -->
  <div class="analysis-card">
    <div class="card-title-row">
      <h4 class="card-title">4. 大额供应商预付账款期末余额分析</h4>
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addSupplierRow">+ 添加行</el-button>
    </div>
    <p class="guide-tip">如存在大额预付账款期末余额，应重点关注支付预付款的商业合理性、交易是否真实、是否存在关联方资金占用。</p>
    <el-table :data="supplierDisplayRows" size="small" border stripe :row-class-name="supplierRowClass">
      <el-table-column label="供应商名称" width="150" fixed>
        <template #default="{ row }">
          <el-input v-if="!row._subtotal" :model-value="row.supplierName" size="small" :disabled="isReadonly"
            @change="(v: string) => updateSupplierCell(row.rowId, 'supplierName', v)" />
          <span v-else class="subtotal-label">小计</span>
        </template>
      </el-table-column>
      <el-table-column label="期初余额" width="110" align="right">
        <template #default="{ row }">
          <el-input v-if="!row._subtotal" :model-value="row.priorBalance" size="small" :disabled="isReadonly"
            @change="(v: any) => updateSupplierCell(row.rowId, 'priorBalance', v)" />
          <span v-else class="amt">{{ fmtAmount(row.priorBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="借方发生" width="110" align="right">
        <template #default="{ row }">
          <el-input v-if="!row._subtotal" :model-value="row.debit" size="small" :disabled="isReadonly"
            @change="(v: any) => updateSupplierCell(row.rowId, 'debit', v)" />
          <span v-else class="amt">{{ fmtAmount(row.debit) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方发生" width="110" align="right">
        <template #default="{ row }">
          <el-input v-if="!row._subtotal" :model-value="row.credit" size="small" :disabled="isReadonly"
            @change="(v: any) => updateSupplierCell(row.rowId, 'credit', v)" />
          <span v-else class="amt">{{ fmtAmount(row.credit) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末余额" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="amt auto">{{ fmtAmount(row.endBalance) }}</span></template>
      </el-table-column>
      <el-table-column label="减：坏账准备" width="110" align="right">
        <template #default="{ row }">
          <el-input v-if="!row._subtotal" :model-value="row.badDebt" size="small" :disabled="isReadonly"
            @change="(v: any) => updateSupplierCell(row.rowId, 'badDebt', v)" />
          <span v-else class="amt">{{ fmtAmount(row.badDebt) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="账面价值" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="amt auto">{{ fmtAmount(row.bookValue) }}</span></template>
      </el-table-column>
      <el-table-column label="发生时间及账龄" width="160">
        <template #default="{ row }">
          <el-select
            v-if="!row._subtotal"
            :model-value="row.aging"
            size="small"
            :disabled="isReadonly"
            filterable
            allow-create
            clearable
            placeholder="选择账龄"
            @change="(v: string) => updateSupplierCell(row.rowId, 'aging', v ?? '')"
          >
            <el-option v-for="opt in agingOptions" :key="opt" :label="opt" :value="opt" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="发生原因" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!row._subtotal" :model-value="row.reason" size="small" :disabled="isReadonly"
            @change="(v: string) => updateSupplierCell(row.rowId, 'reason', v)" />
        </template>
      </el-table-column>
      <el-table-column label="期后结算" width="110" align="right">
        <template #default="{ row }">
          <el-input v-if="!row._subtotal" :model-value="row.postSettlement" size="small" :disabled="isReadonly"
            @change="(v: any) => updateSupplierCell(row.rowId, 'postSettlement', v)" />
          <span v-else class="amt">{{ fmtAmount(row.postSettlement) }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-popconfirm v-if="!row._subtotal" title="确认删除？" @confirm="removeSupplierRow(row.rowId)">
            <template #reference><el-button size="small" type="danger" link>删除</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>
    <div class="note-block">
      <div class="note-label">
        审计说明
        <el-button size="small" :disabled="isReadonly || !aiAvailable || aiLoading" :loading="aiLoading" @click="genNote('supplier')">🤖AI</el-button>
      </div>
      <el-input type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" :disabled="isReadonly"
        :model-value="notes.supplier" @update:model-value="(v: string) => updateNote('supplier', v)"
        placeholder="评价大额供应商预付的商业合理性、真实性及期后结算情况..." />
    </div>
  </div>

  <!-- 结论 -->
  <el-card class="opinion-card" shadow="never">
    <template #header>
      <div class="opinion-header">
        <span class="opinion-title">三、审计结论</span>
        <el-button size="small" :disabled="isReadonly || !aiAvailable || aiLoading" :loading="aiLoading" @click="genConclusion">🤖AI</el-button>
      </div>
    </template>
    <el-input
      type="textarea"
      :autosize="{ minRows: 3, maxRows: 8 }"
      :disabled="isReadonly"
      :model-value="conclusion"
      @update:model-value="(v: string) => updateConclusion(v)"
      placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项调整外，其余未见异常。C、由于存在重大未调整事项或审计范围受限，不可确认。"
    />
  </el-card>
</div>
</template>

<script setup lang="ts">
/**
 * F1TabAnalysis.vue — F1-4 实质性分析表（对齐 Excel）
 */
import { computed, reactive, toRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { isChangeRateExceeding } from '../composables/useF1FormulaEngine'
import {
  useF1Analysis,
  type AnalysisNatureKey,
  type PeriodAmountRow,
  type CreditBreakdownRow,
} from '../composables/useF1Analysis'
import { useF1AiGenerate } from '../composables/useF1AiGenerate'
import type { useF1CrossSheet } from '../composables/useF1CrossSheet'
import type { ChecklistResponse } from '../composables/useF1FormData'
import { useAgingConfig } from '@/composables/useAgingConfig'
import { ADJUDICATION_LABEL_BY_SEGMENT_KEY } from '../composables/agingPresets'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'
import F1SheetAttachments from './F1SheetAttachments.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  crossSheet: ReturnType<typeof useF1CrossSheet>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  /** 后端 render 提供的试算表锚点余额（存货 1401 / 应付 2202，本期期末） */
  tbContext?: { inventoryBalance?: number; payableBalance?: number }
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>
const wpIdRef = toRef(props, 'wpId') as Ref<string>
const projectIdRef = toRef(props, 'projectId') as Ref<string>

const { bands } = useAgingConfig(projectIdRef, 'F1')
const agingOptions = computed(() => {
  const labels = bands.value.map((b) => ADJUDICATION_LABEL_BY_SEGMENT_KEY[b.key] || b.label)
  return labels.length ? labels : ['1年以内(含1年)', '1至2年(含2年)', '2至3年(含3年)', '3年以上']
})

const {
  balanceRows,
  debitRows,
  creditRows,
  supplierRows,
  supplierSubtotal,
    top5ConcentrationWarning,
    crossCycleHints,
    payableBalance,
    notes,
    conclusion,
    updateBalanceNature,
    updateInventoryBalance,
    updateDebitNature,
    updateInventoryPurchase,
    updatePayableBalance,
    updateCreditBreakdown,
    updateNote,
    updateConclusion,
    addSupplierRow,
    removeSupplierRow,
    updateSupplierCell,
    fillFromDetail,
    fillMajorSuppliersFromDetail,
    fillCrossCycleFromTb,
  } = useF1Analysis({
  allResponses: allResponsesRef,
  wpId: wpIdRef,
  projectId: toRef(props, 'projectId') as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  crossSheet: props.crossSheet,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})

const projectId = computed(() => props.projectId)

const hasTbContext = computed(() => {
  const c = props.tbContext
  return !!c && ((c.inventoryBalance ?? 0) !== 0 || (c.payableBalance ?? 0) !== 0)
})

function doFillFromTb() {
  const r = fillCrossCycleFromTb({
    inventoryBalance: props.tbContext?.inventoryBalance ?? 0,
    payableBalance: props.tbContext?.payableBalance ?? 0,
  })
  if (r.inventoryFilled || r.payableFilled) {
    const parts: string[] = []
    if (r.inventoryFilled) parts.push('存货余额')
    if (r.payableFilled) parts.push('应付余额')
    ElMessage.success(`已从试算表带入：${parts.join('、')}`)
  } else {
    ElMessage.info('锚点已有数值或试算表无数据，未覆盖已录入值')
  }
}

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF1AiGenerate(wpIdRef)

const editBuf = reactive<Record<string, number>>({})

/** 跨科目锚点：存货余额在余额分析中已有编辑；此处集中展示采购+应付便于联动 */
const linkageAnchorRows = computed(() => {
  const purchase = debitRows.value.find(r => r.rowKey === 'inventoryPurchase')
  return [
    {
      key: 'inventoryPurchase',
      label: '存货采购金额（对照 F2）',
      current: purchase?.current ?? 0,
      prior: purchase?.prior ?? 0,
      indexChip: 'wp:F2-1',
    },
    {
      key: 'payableBalance',
      label: '应付账款期末余额（对照 F4）',
      current: payableBalance.value.current,
      prior: payableBalance.value.prior,
      indexChip: 'wp:F4-1',
    },
  ]
})

function commitLinkage(key: string, field: 'current' | 'prior') {
  const val = editBuf['link.' + key + '.' + field]
  if (key === 'inventoryPurchase') updateInventoryPurchase(field, val)
  else if (key === 'payableBalance') updatePayableBalance(field, val)
}

function seedEdit(row: { rowKey: string; current: number; prior: number }, field: 'current' | 'prior', prefix = '') {
  editBuf[prefix + row.rowKey + '.' + field] = row[field]
}

function commitPeriod(
  section: 'balance' | 'debit' | 'credit',
  row: PeriodAmountRow | CreditBreakdownRow,
  field: 'current' | 'prior',
) {
  const prefix = section === 'balance' ? '' : section === 'debit' ? 'd.' : 'c.'
  const val = editBuf[prefix + row.rowKey + '.' + field]
  if (section === 'balance') {
    if (row.rowKey === 'inventoryBalance') updateInventoryBalance(field, val)
    else updateBalanceNature(row.rowKey as AnalysisNatureKey, field, val)
  } else if (section === 'debit') {
    if (row.rowKey === 'inventoryPurchase') updateInventoryPurchase(field, val)
    else updateDebitNature(row.rowKey as AnalysisNatureKey, field, val)
  } else {
    updateCreditBreakdown(row.rowKey, field, val)
  }
}

const supplierDisplayRows = computed(() => [
  ...supplierRows.value.map(r => ({ ...r, _subtotal: false })),
  { ...supplierSubtotal.value, rowId: '__subtotal__', supplierName: '小计', aging: '', reason: '', _subtotal: true },
])

function periodRowClass({ row }: { row: any }) {
  if (row.rowKind === 'total') return 'total-row'
  if (row.rowKind === 'ratio') return 'ratio-row'
  return ''
}

function supplierRowClass({ row }: { row: any }) {
  return row._subtotal ? 'subtotal-row' : ''
}

function ratioCurrent(row: any): string {
  if (row.ratioDisplay) return String(row.ratioDisplay).split(' / ')[0] || '-'
  return row.current ? `${Number(row.current).toFixed(2)}%` : '#DIV/0!'
}

function ratioPrior(row: any): string {
  if (row.ratioDisplay) return String(row.ratioDisplay).split(' / ')[1] || '-'
  return row.prior ? `${Number(row.prior).toFixed(2)}%` : '#DIV/0!'
}

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function fmtRate(rate: number | '' | 'N/A'): string {
  if (rate === '' || rate === 'N/A') return rate === '' ? '-' : 'N/A'
  return `${(rate * 100).toFixed(1)}%`
}

function isRateHigh(rate: number | '' | 'N/A'): boolean {
  return isChangeRateExceeding(rate, 0.3)
}

function noteContext() {
  return {
    sheet: 'F1-4',
    supplierCount: supplierRows.value.length,
    concentrationWarning: top5ConcentrationWarning.value || '',
    balanceTotal: balanceRows.value.find(r => r.rowKey === 'total')?.current ?? 0,
    debitTotal: debitRows.value.find(r => r.rowKey === 'total')?.current ?? 0,
    creditTotal: creditRows.value.find(r => r.rowKey === 'total')?.current ?? 0,
  }
}

async function genNote(section: 'balance' | 'debit' | 'credit' | 'supplier') {
  const map = {
    balance: { key: 'analysis-balance-note' as const, title: '余额分析说明', get: () => notes.value.balance },
    debit: { key: 'analysis-debit-note' as const, title: '借方发生额说明', get: () => notes.value.debit },
    credit: { key: 'analysis-credit-note' as const, title: '贷方发生额说明', get: () => notes.value.credit },
    supplier: { key: 'analysis-supplier-note' as const, title: '大额供应商说明', get: () => notes.value.supplier },
  }
  const m = map[section]
  const text = await generateAndConfirm(m.key, m.get(), noteContext(), m.title)
  if (text) updateNote(section, text)
}

async function genConclusion() {
  const text = await generateAndConfirm('analysis-conclusion', conclusion.value, noteContext(), '审计结论')
  if (text) updateConclusion(text)
}
</script>

<style scoped>
.f1-analysis { padding: 16px; }
.f1-analysis :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f1-analysis :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }

.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }

.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }

.analysis-card { margin-bottom: 20px; padding: 16px; background: #fff; border: 1px solid #ebeef5; border-radius: 6px; }
.card-title { font-size: 14px; font-weight: 600; margin: 0 0 12px; color: #303133; }
.card-title-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.card-title-row .card-title { margin: 0; }
.guide-tip { font-size: 12px; color: #409eff; margin: 0 0 10px; line-height: 1.5; }
.indent { padding-left: 1.5em; }
.amt { text-align: right; display: inline-block; width: 100%; }
.auto { color: #909399; }
.rate-exceed { color: #f56c6c; font-weight: 600; }
.subtotal-label { font-weight: 700; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
:deep(.total-row) { background-color: #fafafa !important; font-weight: 600; }
:deep(.ratio-row) { background-color: #f0f9eb !important; }
:deep(.subtotal-row) { background-color: #fafafa !important; font-weight: 600; }

.note-block { margin-top: 12px; }
.note-label { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; font-size: 13px; font-weight: 500; }

.opinion-card { margin-top: 8px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; }
</style>
