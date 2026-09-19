<template>
  <div class="f2-val-sheet f2-impairment">
    <header class="sheet-header">
      <div>
        <h3>存货跌价准备测试表</h3>
        <span class="code">F2-47</span>
      </div>
      <div class="stat-row">
        <span class="stat">账面合计 {{ fmt(imp.columnTotals.value.bookCost) }}</span>
        <span class="stat sub">应计提 {{ fmt(imp.columnTotals.value.requiredProvision) }}</span>
        <el-tag v-if="imp.needsConclusionCount.value" type="warning" size="small">
          {{ imp.needsConclusionCount.value }} 笔需填备注
        </el-tag>
        <el-tag v-if="imp.agingMismatchCount.value" type="danger" size="small">
          库龄合计异常 {{ imp.agingMismatchCount.value }} 项
        </el-tag>
        <el-button size="small" :disabled="isReadonly || pullPriceLoading" :loading="pullPriceLoading" @click="handlePullRecentPrice">参考近期售价</el-button>
      </div>
    </header>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 期末存货按成本与可变现净值孰低计量；有合同价的按合同价，无合同的按市场售价测算 NRV。</p>
        <p>2. 灰色列为自动计算（账面单位成本、NRV、应计提、审定数、应补提等），据录入的售价/成本/费率自动测算。</p>
        <p>3. 库龄四档合计应与库存数量勾稽；应计提&gt;0 且备注为空的行自动提示复核。</p>
        <p>4. 结合 F2-48 长库龄明细与盘点结果，评价跌价准备计提充分性。</p>
      </div>
    </details>

    <div class="section-label">一、审计目标</div>
    <ol class="objectives">
      <li v-for="(obj, i) in objectives" :key="i">{{ obj }}</li>
    </ol>

    <div class="section-label">二、样本选取标准与范围</div>
    <div class="meta-grid">
      <label>
        <span class="sampling-label">
          审计对象
          <el-button
            link
            type="primary"
            size="small"
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="runAi('impairment-audit-object')"
          >AI</el-button>
        </span>
        <el-input
          :model-value="imp.sheet.value.sampling.auditObject"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 4 }"
          class="sampling-textarea"
          :disabled="isReadonly"
          placeholder="类别、品种、金额等"
          @update:model-value="(v: string) => imp.updateSampling({ auditObject: v })"
        />
      </label>
      <label>
        <span class="sampling-label">
          具体样本选取
          <el-button
            link
            type="primary"
            size="small"
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="runAi('impairment-sample-criteria')"
          >AI</el-button>
        </span>
        <el-input
          :model-value="imp.sheet.value.sampling.sampleCriteria"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 4 }"
          class="sampling-textarea"
          :disabled="isReadonly"
          @update:model-value="(v: string) => imp.updateSampling({ sampleCriteria: v })"
        />
      </label>
      <label>
        抽样方法
        <el-select
          :model-value="imp.sheet.value.sampling.samplingMethod || undefined"
          :disabled="isReadonly"
          clearable
          placeholder="选择"
          @update:model-value="(v: string) => imp.updateSampling({ samplingMethod: v || '' })"
        >
          <el-option v-for="m in samplingMethods" :key="m" :label="m" :value="m" />
        </el-select>
      </label>
      <label>
        <span class="sampling-label">
          抽样过程
          <el-button
            link
            type="primary"
            size="small"
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="runAi('impairment-sampling-process')"
          >AI</el-button>
        </span>
        <el-input
          :model-value="imp.sheet.value.sampling.samplingProcess"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 4 }"
          class="sampling-textarea"
          :disabled="isReadonly"
          @update:model-value="(v: string) => imp.updateSampling({ samplingProcess: v })"
        />
      </label>
    </div>

    <div class="section-label">三、审计过程</div>
    <el-input
      :model-value="imp.sheet.value.auditProcedure"
      type="textarea"
      :autosize="{ minRows: 4, maxRows: 8 }"
      :disabled="isReadonly"
      class="section-text"
      @update:model-value="(v: string) => imp.setProcedure(v)"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="imp.addProduct()">+ 样本</el-button>
        <el-button size="small" :disabled="isReadonly" @click="imp.publishImpairmentCalculated()">发布跌价测算</el-button>
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-val"
          sheet="F2-47"
          :disabled="isReadonly"
          review-section="F2-47-conclusion"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:F2-47" /></span>
        <el-tag size="small" type="info">{{ filledCount }} 个样本</el-tag>
      </div>
    </div>

    <div class="table-scroll">
      <table class="matrix-table">
        <thead>
          <tr>
            <th rowspan="2" class="col-cat">存货类别</th>
            <th rowspan="2" class="col-code">编码</th>
            <th rowspan="2" class="col-name">名称</th>
            <th rowspan="2" class="col-unit">单位</th>
            <th rowspan="2">数量</th>
            <th rowspan="2">账面成本</th>
            <th rowspan="2">账面单价</th>
            <th colspan="4">库龄</th>
            <th rowspan="2">状态</th>
            <th rowspan="2">持有目的</th>
            <th rowspan="2">销售费用率</th>
            <th rowspan="2">税率</th>
            <th colspan="7">可变现净值</th>
            <th rowspan="2">应计提</th>
            <th rowspan="2">审定数</th>
            <th rowspan="2">账面计提</th>
            <th rowspan="2">应补提</th>
            <th rowspan="2">备注</th>
            <th rowspan="2" class="col-act" />
          </tr>
          <tr>
            <th class="sub">1年内</th>
            <th class="sub">1-2年</th>
            <th class="sub">2-3年</th>
            <th class="sub">3年以上</th>
            <th class="sub">售价-市价</th>
            <th class="sub">售价-合约</th>
            <th class="sub">依据索引</th>
            <th class="sub">至完工成本</th>
            <th class="sub">销售费用</th>
            <th class="sub">相关税费</th>
            <th class="sub">NRV</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in imp.enrichedProducts.value"
            :key="row.id"
            :class="{
              'row-warn': row.needsRemark,
              'row-aging': row.agingMismatch,
            }"
          >
            <td class="col-cat">
              <el-input v-if="!isReadonly" :model-value="row.category" size="small"
                @update:model-value="(v: string) => imp.updateProduct(row.id, { category: v })" />
              <span v-else>{{ row.category || '—' }}</span>
            </td>
            <td>
              <el-input v-if="!isReadonly" :model-value="row.itemCode" size="small"
                @update:model-value="(v: string) => imp.updateProduct(row.id, { itemCode: v })" />
              <span v-else>{{ row.itemCode || '—' }}</span>
            </td>
            <td class="col-name">
              <el-input v-if="!isReadonly" :model-value="row.itemName" size="small"
                @update:model-value="(v: string) => imp.updateProduct(row.id, { itemName: v })" />
              <span v-else>{{ row.itemName || '—' }}</span>
            </td>
            <td>
              <el-input v-if="!isReadonly" :model-value="row.unit" size="small"
                @update:model-value="(v: string) => imp.updateProduct(row.id, { unit: v })" />
              <span v-else>{{ row.unit || '—' }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.qty" size="small" :controls="false"
                class="compact-num" @change="(v: number | undefined) => imp.updateProduct(row.id, { qty: v ?? 0 })" />
              <span v-else class="auto">{{ fmtQty(row.qty) }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.bookCost" size="small" :controls="false"
                class="compact-num wide" @change="(v: number | undefined) => imp.updateProduct(row.id, { bookCost: v ?? 0 })" />
              <span v-else class="auto">{{ fmt(row.bookCost) }}</span>
            </td>
            <td class="auto calc">{{ fmtUnit(row.bookUnitCost) }}</td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.aging.within1y" size="small" :controls="false"
                class="compact-num" @change="(v: number | undefined) => imp.updateProduct(row.id, { aging: { ...row.aging, within1y: v ?? 0 } })" />
              <span v-else class="auto">{{ fmtQty(row.aging.within1y) }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.aging.y1to2" size="small" :controls="false"
                class="compact-num" @change="(v: number | undefined) => imp.updateProduct(row.id, { aging: { ...row.aging, y1to2: v ?? 0 } })" />
              <span v-else class="auto">{{ fmtQty(row.aging.y1to2) }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.aging.y2to3" size="small" :controls="false"
                class="compact-num" @change="(v: number | undefined) => imp.updateProduct(row.id, { aging: { ...row.aging, y2to3: v ?? 0 } })" />
              <span v-else class="auto">{{ fmtQty(row.aging.y2to3) }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.aging.over3y" size="small" :controls="false"
                class="compact-num" @change="(v: number | undefined) => imp.updateProduct(row.id, { aging: { ...row.aging, over3y: v ?? 0 } })" />
              <span v-else class="auto">{{ fmtQty(row.aging.over3y) }}</span>
            </td>
            <td>
              <el-select v-if="!isReadonly" :model-value="row.inventoryStatus || undefined" size="small" clearable
                @update:model-value="(v: string) => imp.updateProduct(row.id, { inventoryStatus: v || '' })">
                <el-option v-for="s in statusOptions" :key="s" :label="s" :value="s" />
              </el-select>
              <span v-else>{{ row.inventoryStatus || '—' }}</span>
            </td>
            <td>
              <el-select v-if="!isReadonly" :model-value="row.holdingPurpose || undefined" size="small" clearable
                @update:model-value="(v: string) => imp.updateProduct(row.id, { holdingPurpose: v || '' })">
                <el-option v-for="p in purposeOptions" :key="p" :label="p" :value="p" />
              </el-select>
              <span v-else>{{ row.holdingPurpose || '—' }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.sellingExpenseRate" size="small" :controls="false"
                class="compact-num" @change="(v: number | undefined) => imp.updateProduct(row.id, { sellingExpenseRate: v ?? 0 })" />
              <span v-else class="auto">{{ fmtPct(row.sellingExpenseRate) }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.taxRate" size="small" :controls="false"
                class="compact-num" @change="(v: number | undefined) => imp.updateProduct(row.id, { taxRate: v ?? 0 })" />
              <span v-else class="auto">{{ fmtPct(row.taxRate) }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.pricePreContract" size="small" :controls="false"
                class="compact-num" @change="(v: number | undefined) => imp.updateProduct(row.id, { pricePreContract: v ?? 0 })" />
              <span v-else class="auto">{{ fmtUnit(row.pricePreContract) }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.priceContract" size="small" :controls="false"
                class="compact-num" @change="(v: number | undefined) => imp.updateProduct(row.id, { priceContract: v ?? 0 })" />
              <span v-else class="auto">{{ fmtUnit(row.priceContract) }}</span>
            </td>
            <td>
              <el-input v-if="!isReadonly" :model-value="row.priceBasisIndex" size="small"
                @update:model-value="(v: string) => imp.updateProduct(row.id, { priceBasisIndex: v })" />
              <span v-else class="idx">{{ row.priceBasisIndex || '—' }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.completionCost" size="small" :controls="false"
                class="compact-num wide" @change="(v: number | undefined) => imp.updateProduct(row.id, { completionCost: v ?? 0 })" />
              <span v-else class="auto">{{ fmt(row.completionCost) }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.sellingExpense" size="small" :controls="false"
                class="compact-num" @change="(v: number | undefined) => imp.updateProduct(row.id, { sellingExpense: v ?? 0 })" />
              <span v-else class="auto" :title="row.sellingExpenseRate ? '按费率测算' : ''">{{ fmt(row.computedSellingExpense) }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.relatedTax" size="small" :controls="false"
                class="compact-num" @change="(v: number | undefined) => imp.updateProduct(row.id, { relatedTax: v ?? 0 })" />
              <span v-else class="auto">{{ fmt(row.computedRelatedTax) }}</span>
            </td>
            <td class="auto calc">{{ fmt(row.nrv) }}</td>
            <td class="auto calc" :class="{ 'var-warn': row.requiredProvision > 0 }">{{ fmt(row.requiredProvision) }}</td>
            <td class="auto calc">{{ fmt(row.auditedAmount) }}</td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.bookedProvision" size="small" :controls="false"
                class="compact-num" @change="(v: number | undefined) => imp.updateProduct(row.id, { bookedProvision: v ?? 0 })" />
              <span v-else class="auto">{{ fmt(row.bookedProvision) }}</span>
            </td>
            <td class="auto calc" :class="{ 'var-warn': row.additionalProvision > 0 }">{{ fmt(row.additionalProvision) }}</td>
            <td>
              <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
                @update:model-value="(v: string) => imp.updateProduct(row.id, { remark: v })" />
              <span v-else>{{ row.remark || '—' }}</span>
            </td>
            <td class="col-act">
              <el-upload
                v-if="wpId && !isReadonly"
                :show-file-list="false"
                :auto-upload="false"
                accept=".pdf,.png,.jpg,.jpeg"
                :disabled="ocrLoadingId === row.id"
                @change="(uf: any) => handleOcrUpload(row.id, uf?.raw)"
              >
                <el-button link size="small" :loading="ocrLoadingId === row.id">📎</el-button>
              </el-upload>
              <el-button v-if="!isReadonly" link type="danger" size="small" @click="imp.removeProduct(row.id)">删</el-button>
            </td>
          </tr>
          <tr class="row-total">
            <td colspan="4" class="col-name">合计</td>
            <td class="auto">{{ fmtQty(imp.columnTotals.value.qty) }}</td>
            <td class="auto">{{ fmt(imp.columnTotals.value.bookCost) }}</td>
            <td />
            <td colspan="4" />
            <td colspan="4" />
            <td colspan="7" />
            <td class="auto">{{ fmt(imp.columnTotals.value.requiredProvision) }}</td>
            <td class="auto">{{ fmt(imp.columnTotals.value.auditedAmount) }}</td>
            <td class="auto">{{ fmt(imp.columnTotals.value.bookedProvision) }}</td>
            <td class="auto">{{ fmt(imp.columnTotals.value.additionalProvision) }}</td>
            <td colspan="2" />
          </tr>
        </tbody>
      </table>
    </div>

    <div class="section-label">四、审计说明（按类别汇总）</div>
    <table class="summary-table">
      <thead>
        <tr>
          <th>存货类别</th>
          <th>账面成本</th>
          <th>审计调后计提</th>
          <th>审计调整金额</th>
          <th>计提比例</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="s in imp.categorySummaries.value" :key="s.category">
          <td>{{ s.category }}</td>
          <td class="auto">{{ fmt(s.bookCost) }}</td>
          <td class="auto">{{ fmt(s.auditedProvision) }}</td>
          <td class="auto">{{ fmt(s.auditAdjustment) }}</td>
          <td class="auto">{{ fmtRatio(s.provisionRatio) }}</td>
        </tr>
        <tr v-if="!imp.categorySummaries.value.length">
          <td colspan="5" class="empty-hint">录入样本后按类别自动汇总</td>
        </tr>
      </tbody>
    </table>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明</span>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="runAi('impairment-note')"
          >AI 填写审计说明</el-button>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="概述可变现净值测算程序、抽样情况与测试结果..." />
    </el-card>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">五、审计结论</span>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="runAi('impairment-conclusion')"
          >AI 生成结论</el-button>
        </div>
      </template>
      <el-input v-model="imp.testConclusion.value" type="textarea" :autosize="{ minRows: 3, maxRows: 6 }" :disabled="isReadonly"
        placeholder="A、跌价准备计提充分、准确，未见异常。B、除上述应调整事项外，其余未见异常。C、不可确认。" />
    </el-card>

    <div class="tips-box">
      <div class="tips-title">提示</div>
      <ol>
        <li v-for="(tip, i) in tips" :key="i">{{ tip }}</li>
      </ol>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, toRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useF2ImpairmentTest } from '../../composables/useF2ImpairmentTest'
import { useF2ImpairmentOcr } from '../../composables/useF2ImpairmentOcr'
import { useF2ValuationAiGenerate, type F2ValAiSection } from '../../composables/useF2ValuationAiGenerate'
import {
  F2_47_OBJECTIVES,
  F2_47_TIPS,
  SAMPLING_METHOD_OPTIONS,
  INVENTORY_STATUS_OPTIONS,
  HOLDING_PURPOSE_OPTIONS,
  isBlankProduct,
} from '../../composables/useF2ImpairmentTestFormulas'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
import GtIndexChip from '../../GtIndexChip.vue'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'

const props = defineProps<{
  wpId?: string
  projectId?: string
  year?: number
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const imp = useF2ImpairmentTest({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const objectives = F2_47_OBJECTIVES
const tips = F2_47_TIPS
const samplingMethods = SAMPLING_METHOD_OPTIONS
const statusOptions = INVENTORY_STATUS_OPTIONS
const purposeOptions = HOLDING_PURPOSE_OPTIONS

const filledCount = computed(
  () => imp.enrichedProducts.value.filter((r) => !isBlankProduct(r)).length,
)

const NOTE_KEY = 'F2-47-audit-note'
const auditNote = ref('')
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
})
function saveAuditNote(): void {
  if (props.isReadonly) return
  const item = { item_id: NOTE_KEY, conclusion: null, remark: auditNote.value }
  props.allResponses.set(NOTE_KEY, item)
  window.dispatchEvent(new CustomEvent('f2-val:save-items', { detail: { items: [item] } }))
}
watch(auditNote, () => saveAuditNote())

const pullPriceLoading = ref(false)
async function handlePullRecentPrice(): Promise<void> {
  if (props.isReadonly || pullPriceLoading.value) return
  const pid = props.projectId || ''
  const yr = props.year || new Date().getFullYear() - 1
  if (!pid) {
    ElMessage.info('无近期售价参考（缺少项目信息）')
    return
  }
  pullPriceLoading.value = true
  try {
    const result = await imp.pullRecentPrice(pid, yr)
    if (result.filled === 0 && result.skipped === 0) {
      ElMessage.info('无近期售价参考')
    } else if (result.filled > 0 && result.skipped > 0) {
      ElMessage.success(`参考带入 ${result.filled} 项（${result.skipped} 项已有手录未覆盖）`)
    } else if (result.filled > 0) {
      ElMessage.success(`参考带入 ${result.filled} 项售价`)
    } else {
      ElMessage.info(`${result.skipped} 项已有手录售价，未覆盖`)
    }
  } finally {
    pullPriceLoading.value = false
  }
}

const wpIdRef = toRef(() => props.wpId || '') as Ref<string>
const { ocrLoadingId, uploadAndMerge } = useF2ImpairmentOcr(
  wpIdRef,
  toRef(() => props.projectId || '') as Ref<string>,
)
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2ValuationAiGenerate(wpIdRef)

function aiContext(): Record<string, unknown> {
  return {
    sheet: 'F2-47',
    sampleCount: filledCount.value,
    samplingMethod: imp.sheet.value.sampling.samplingMethod,
    sampleItems: imp.enrichedProducts.value
      .filter((r) => !isBlankProduct(r))
      .slice(0, 30)
      .map((r) => ({
        category: r.category,
        itemName: r.itemName,
        bookCost: r.bookCost,
        inventoryStatus: r.inventoryStatus,
        requiredProvision: r.requiredProvision,
      })),
    bookCostTotal: imp.columnTotals.value.bookCost,
    requiredProvisionTotal: imp.columnTotals.value.requiredProvision,
    auditedAmountTotal: imp.columnTotals.value.auditedAmount,
    bookedProvisionTotal: imp.columnTotals.value.bookedProvision,
    additionalProvisionTotal: imp.columnTotals.value.additionalProvision,
    needsConclusionCount: imp.needsConclusionCount.value,
    agingMismatchCount: imp.agingMismatchCount.value,
    categorySummaries: imp.categorySummaries.value,
  }
}

const AI_TARGETS: Partial<Record<F2ValAiSection, {
  title: string
  get: () => string
  set: (t: string) => void
}>> = {
  'impairment-note': {
    title: 'AI 生成 · 审计说明',
    get: () => auditNote.value,
    set: (t) => { auditNote.value = t },
  },
  'impairment-conclusion': {
    title: 'AI 生成 · 跌价测试结论',
    get: () => imp.testConclusion.value,
    set: (t) => { imp.testConclusion.value = t },
  },
  'impairment-audit-object': {
    title: 'AI 生成 · 审计对象',
    get: () => imp.sheet.value.sampling.auditObject,
    set: (t) => imp.updateSampling({ auditObject: t }),
  },
  'impairment-sample-criteria': {
    title: 'AI 生成 · 具体样本选取',
    get: () => imp.sheet.value.sampling.sampleCriteria,
    set: (t) => imp.updateSampling({ sampleCriteria: t }),
  },
  'impairment-sampling-process': {
    title: 'AI 生成 · 抽样过程',
    get: () => imp.sheet.value.sampling.samplingProcess,
    set: (t) => imp.updateSampling({ samplingProcess: t }),
  },
}

async function runAi(section: F2ValAiSection): Promise<void> {
  const target = AI_TARGETS[section]
  if (!target) return
  const text = await generateAndConfirm(section, target.get() || '', aiContext(), target.title)
  if (text) target.set(text)
}

function handleOcrUpload(rowId: string, file?: File) {
  if (!file) return
  void uploadAndMerge(rowId, file, (id, patch) => imp.updateRow(id, patch))
}

function fmt(v: number): string {
  if (!Number.isFinite(v) || v === 0) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtQty(v: number): string {
  if (!Number.isFinite(v) || v === 0) return '—'
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}
function fmtUnit(v: number): string {
  if (!Number.isFinite(v) || v === 0) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
}
function fmtPct(v: number): string {
  if (!Number.isFinite(v) || v === 0) return '—'
  return `${v.toFixed(2)}%`
}
function fmtRatio(r: number): string {
  if (!Number.isFinite(r) || r === 0) return '—'
  return `${(r * 100).toFixed(2)}%`
}
</script>

<style scoped src="./f2ValSheetStyles.css"></style>
<style scoped>
.f2-impairment { --gt-purple: #4b2d77; --gt-purple-soft: #f3eef8; }
.section-label { margin: 14px 0 8px; font-size: 14px; font-weight: 600; color: var(--gt-purple); }
.objectives { margin: 0 0 12px; padding-left: 1.4em; font-size: 13px; line-height: 1.7; color: #606266; }
.section-text { margin-bottom: 12px; }

.meta-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px 16px;
  margin-bottom: 12px;
}
.meta-grid label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: #606266;
}
.sampling-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.sampling-label .el-button { padding: 0; height: auto; font-size: 12px; }
:deep(.sampling-textarea .el-textarea__inner) {
  min-height: 54px !important;
  line-height: 20px;
  padding: 7px 11px;
}

.table-scroll { overflow-x: auto; margin-bottom: 12px; }
.matrix-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
  min-width: 2200px;
}
.matrix-table th,
.matrix-table td {
  border: 1px solid #d4c8e0;
  padding: 2px 3px;
  text-align: center;
  vertical-align: middle;
}
.matrix-table thead th {
  background: var(--gt-purple-soft);
  color: #3d2a55;
  font-weight: 600;
}
.matrix-table th.sub { font-weight: 500; font-size: 10px; }
.col-cat { min-width: 72px; }
.col-code { min-width: 64px; }
.col-name { min-width: 88px; text-align: left !important; padding-left: 4px !important; background: #faf8fc; }
.col-unit { width: 48px; }
.col-act { width: 52px; }
.row-total td { background: #f0ebf5; font-weight: 600; }
.row-warn td { background: #fdf6ec; }
.row-aging td { box-shadow: inset 0 0 0 1px #f56c6c; }
.auto { text-align: right; padding-right: 3px; white-space: nowrap; color: #606266; }
span.auto { display: block; }
.calc { background: #f8f6fa; color: #4b2d77; }
.var-warn { color: #f56c6c !important; font-weight: 600; }
.idx { font-size: 10px; color: #909399; }

.summary-table {
  width: 100%;
  max-width: 720px;
  border-collapse: collapse;
  font-size: 13px;
  margin-bottom: 14px;
}
.summary-table th,
.summary-table td {
  border: 1px solid #d4c8e0;
  padding: 6px 8px;
  text-align: center;
}
.summary-table th {
  background: var(--gt-purple-soft);
  color: #3d2a55;
  font-weight: 600;
}
.empty-hint { color: #909399; font-style: italic; }

.tips-box {
  margin-top: 16px;
  padding: 12px 16px;
  background: #ecf5ff;
  border-left: 3px solid #409eff;
  border-radius: 4px;
  font-size: 13px;
  line-height: 1.7;
}
.tips-title { font-weight: 600; color: #409eff; margin-bottom: 6px; }
.tips-box ol { margin: 0; padding-left: 1.4em; }

:deep(.compact-num) { width: 64px; }
:deep(.compact-num.wide) { width: 80px; }
:deep(.compact-num .el-input__inner) { text-align: right; padding: 0 2px; font-size: 11px; }
</style>
