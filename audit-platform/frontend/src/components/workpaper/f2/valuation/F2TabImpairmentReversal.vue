<template>
  <div class="f2-val-sheet f2-reversal">
    <header class="sheet-header">
      <div>
        <h3>存货跌价准备转回核对表</h3>
        <span class="code">F2-49</span>
      </div>
      <div class="stat-row">
        <span class="stat">转回合计 {{ fmt(rev.columnTotals.value.reversalTotal) }}</span>
        <span class="stat sub">期初跌价 {{ fmt(rev.columnTotals.value.priorProvision) }}</span>
        <el-tag v-if="rev.summary.value.reverseCount" type="success" size="small">
          转回 {{ rev.summary.value.reverseCount }} 项
        </el-tag>
        <el-tag v-if="rev.summary.value.verifyFailCount" type="danger" size="small">
          核对差异 {{ rev.summary.value.verifyFailCount }} 项
        </el-tag>
      </div>
    </header>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 转回金额 = 上期末已计提跌价 × (本年发出数量 ÷ 期初结存数量)，在原计提金额内转回。</p>
        <p>2. 按生产领用、销售、研发领用等发出结构，将转回金额分摊至营业成本、研发费用等科目。</p>
        <p>3. 转回金额核对 = 跌价转回合计 − 各科目转回之和；发出明细合计应与本年发出数量勾稽。</p>
        <p>4. 未勾选"单独计提跌价"的存货不参与本表转回测算。</p>
      </div>
    </details>

    <el-alert type="info" :closable="false" :title="objectiveText" class="objective-alert" />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="rev.addProduct()">+ 存货</el-button>
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-val"
          sheet="F2-49"
          :disabled="isReadonly"
          review-section="F2-49-conclusion"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:F2-49" /></span>
        <el-tag size="small" type="info">{{ filledCount }} 行</el-tag>
      </div>
    </div>

    <div class="table-scroll">
      <table class="matrix-table">
        <thead>
          <tr>
            <th rowspan="2" class="col-cat">存货类别</th>
            <th rowspan="2" class="col-code">编码</th>
            <th rowspan="2" class="col-name">名称</th>
            <th rowspan="2" class="col-spec">规格</th>
            <th rowspan="2" class="col-unit">单位</th>
            <th colspan="3" class="grp-open">期初</th>
            <th colspan="4" class="grp-aging col-aging-h">库龄</th>
            <th rowspan="2" class="col-flag">单独计提</th>
            <th rowspan="2">上期末跌价</th>
            <th colspan="5" class="grp-issue">本年发出数量</th>
            <th rowspan="2" class="col-rev">转回合计</th>
            <th colspan="3" class="grp-acct">转回科目</th>
            <th rowspan="2" class="col-verify">核对</th>
            <th rowspan="2" class="col-act" />
          </tr>
          <tr>
            <th class="sub">数量</th>
            <th class="sub">单价</th>
            <th class="sub open-amt">金额</th>
            <th class="sub aging">1年内</th>
            <th class="sub aging">1-2年</th>
            <th class="sub aging">2-3年</th>
            <th class="sub aging">3年以上</th>
            <th class="sub">合计</th>
            <th class="sub">生产领用</th>
            <th class="sub">销售</th>
            <th class="sub">研发领用</th>
            <th class="sub">其他</th>
            <th class="sub">营业成本</th>
            <th class="sub">研发费用</th>
            <th class="sub">其他</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rev.enrichedProducts.value"
            :key="row.id"
            :class="{
              'row-warn': row.highlight,
              'row-aging': row.agingMismatch || row.issuanceMismatch,
            }"
          >
            <td class="col-cat">
              <el-input v-if="!isReadonly" :model-value="row.category" size="small"
                @update:model-value="(v: string) => rev.updateProduct(row.id, { category: v })" />
              <span v-else>{{ row.category || '—' }}</span>
            </td>
            <td>
              <el-input v-if="!isReadonly" :model-value="row.itemCode" size="small"
                @update:model-value="(v: string) => rev.updateProduct(row.id, { itemCode: v })" />
              <span v-else>{{ row.itemCode || '—' }}</span>
            </td>
            <td class="col-name">
              <el-input v-if="!isReadonly" :model-value="row.itemName" size="small"
                @update:model-value="(v: string) => rev.updateProduct(row.id, { itemName: v })" />
              <span v-else>{{ row.itemName || '—' }}</span>
            </td>
            <td>
              <el-input v-if="!isReadonly" :model-value="row.specification" size="small"
                @update:model-value="(v: string) => rev.updateProduct(row.id, { specification: v })" />
              <span v-else>{{ row.specification || '—' }}</span>
            </td>
            <td>
              <el-input v-if="!isReadonly" :model-value="row.unit" size="small"
                @update:model-value="(v: string) => rev.updateProduct(row.id, { unit: v })" />
              <span v-else>{{ row.unit || '—' }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.openingQty" size="small" :controls="false"
                class="compact-num" @change="(v: number | undefined) => rev.updateProduct(row.id, { openingQty: v ?? 0 })" />
              <span v-else class="auto">{{ fmtQty(row.openingQty) }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.openingUnitPrice" size="small" :controls="false"
                :precision="4" class="compact-num"
                @change="(v: number | undefined) => rev.updateProduct(row.id, { openingUnitPrice: v ?? 0 })" />
              <span v-else class="auto">{{ fmtUnit(row.openingUnitPrice) }}</span>
            </td>
            <td class="auto calc open-amt">{{ fmt(row.openingAmount) }}</td>
            <td class="aging-cell">
              <el-input-number v-if="!isReadonly" :model-value="row.aging.within1y" size="small" :controls="false"
                class="compact-num" @change="(v: number | undefined) => rev.updateAging(row.id, { within1y: v ?? 0 })" />
              <span v-else class="auto">{{ fmtQty(row.aging.within1y) }}</span>
            </td>
            <td class="aging-cell">
              <el-input-number v-if="!isReadonly" :model-value="row.aging.y1to2" size="small" :controls="false"
                class="compact-num" @change="(v: number | undefined) => rev.updateAging(row.id, { y1to2: v ?? 0 })" />
              <span v-else class="auto">{{ fmtQty(row.aging.y1to2) }}</span>
            </td>
            <td class="aging-cell">
              <el-input-number v-if="!isReadonly" :model-value="row.aging.y2to3" size="small" :controls="false"
                class="compact-num" @change="(v: number | undefined) => rev.updateAging(row.id, { y2to3: v ?? 0 })" />
              <span v-else class="auto">{{ fmtQty(row.aging.y2to3) }}</span>
            </td>
            <td class="aging-cell">
              <el-input-number v-if="!isReadonly" :model-value="row.aging.over3y" size="small" :controls="false"
                class="compact-num" @change="(v: number | undefined) => rev.updateAging(row.id, { over3y: v ?? 0 })" />
              <span v-else class="auto">{{ fmtQty(row.aging.over3y) }}</span>
            </td>
            <td class="col-flag">
              <el-checkbox v-if="!isReadonly" :model-value="row.separateProvision"
                @change="(v) => rev.updateProduct(row.id, { separateProvision: !!v })" />
              <span v-else>{{ row.separateProvision ? '是' : '否' }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.priorProvision" size="small" :controls="false"
                class="compact-num wide"
                @change="(v: number | undefined) => rev.updateProduct(row.id, { priorProvision: v ?? 0 })" />
              <span v-else class="auto">{{ fmt(row.priorProvision) }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.issuance.total" size="small" :controls="false"
                class="compact-num" @change="(v: number | undefined) => rev.updateIssuance(row.id, { total: v ?? 0 })" />
              <span v-else class="auto">{{ fmtQty(row.issuance.total) }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.issuance.production" size="small" :controls="false"
                class="compact-num" @change="(v: number | undefined) => rev.updateIssuance(row.id, { production: v ?? 0 })" />
              <span v-else class="auto">{{ fmtQty(row.issuance.production) }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.issuance.sales" size="small" :controls="false"
                class="compact-num" @change="(v: number | undefined) => rev.updateIssuance(row.id, { sales: v ?? 0 })" />
              <span v-else class="auto">{{ fmtQty(row.issuance.sales) }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.issuance.rnd" size="small" :controls="false"
                class="compact-num" @change="(v: number | undefined) => rev.updateIssuance(row.id, { rnd: v ?? 0 })" />
              <span v-else class="auto">{{ fmtQty(row.issuance.rnd) }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.issuance.other" size="small" :controls="false"
                class="compact-num" @change="(v: number | undefined) => rev.updateIssuance(row.id, { other: v ?? 0 })" />
              <span v-else class="auto">{{ fmtQty(row.issuance.other) }}</span>
            </td>
            <td class="auto calc col-rev rev-amt">{{ fmt(row.reversalTotal) }}</td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.accountSplit.costOfSales" size="small" :controls="false"
                class="compact-num" placeholder="自动"
                @change="(v: number | undefined) => rev.updateAccountSplit(row.id, { costOfSales: v ?? 0 })" />
              <span v-else class="auto">{{ fmt(row.effectiveCostOfSales) }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.accountSplit.rndExpense" size="small" :controls="false"
                class="compact-num" placeholder="自动"
                @change="(v: number | undefined) => rev.updateAccountSplit(row.id, { rndExpense: v ?? 0 })" />
              <span v-else class="auto">{{ fmt(row.effectiveRndExpense) }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.accountSplit.other" size="small" :controls="false"
                class="compact-num" placeholder="自动"
                @change="(v: number | undefined) => rev.updateAccountSplit(row.id, { other: v ?? 0 })" />
              <span v-else class="auto">{{ fmt(row.effectiveOther) }}</span>
            </td>
            <td class="col-verify" :class="row.verifyOk ? 'verify-ok' : 'verify-fail'">
              {{ row.reversalTotal ? (row.verifyOk ? 'OK' : fmt(row.verificationDiff)) : '—' }}
            </td>
            <td class="col-act">
              <el-button v-if="!isReadonly" link type="danger" size="small" @click="rev.removeProduct(row.id)">删</el-button>
            </td>
          </tr>
          <tr class="row-total">
            <td colspan="5" class="col-name">合计</td>
            <td class="auto">{{ fmtQty(rev.columnTotals.value.openingQty) }}</td>
            <td />
            <td class="auto calc">{{ fmt(rev.columnTotals.value.openingAmount) }}</td>
            <td colspan="4" />
            <td />
            <td class="auto">{{ fmt(rev.columnTotals.value.priorProvision) }}</td>
            <td class="auto">{{ fmtQty(rev.columnTotals.value.issuanceTotal) }}</td>
            <td colspan="3" />
            <td />
            <td class="auto calc rev-amt">{{ fmt(rev.columnTotals.value.reversalTotal) }}</td>
            <td class="auto">{{ fmt(rev.columnTotals.value.costOfSales) }}</td>
            <td class="auto">{{ fmt(rev.columnTotals.value.rndExpense) }}</td>
            <td class="auto">{{ fmt(rev.columnTotals.value.other) }}</td>
            <td />
            <td />
          </tr>
        </tbody>
      </table>
    </div>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">1、审计说明</span>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="runAi('reversal-note')"
          >AI 填写审计说明</el-button>
        </div>
      </template>
      <el-input v-model="rev.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="说明跌价转回的测算依据、发出核对及科目分摊..." />
    </el-card>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">2、审计结论</span>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="runAi('reversal-conclusion')"
          >AI 生成结论</el-button>
        </div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="A、未见异常。B、除上述应调整事项外，其余未见异常。C、不可确认。"
        @update:model-value="saveAuditConclusion" />
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
import { ref, computed, onMounted, toRef, type Ref } from 'vue'
import { useF2ImpairmentReversal } from '../../composables/useF2ImpairmentReversal'
import { useF2ValuationAiGenerate, type F2ValAiSection } from '../../composables/useF2ValuationAiGenerate'
import {
  F2_49_DEFAULT_OBJECTIVE,
  F2_49_TIPS,
  isBlankReversalItem,
} from '../../composables/useF2ImpairmentReversalFormulas'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
import GtIndexChip from '../../GtIndexChip.vue'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const rev = useF2ImpairmentReversal({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const objectiveText = F2_49_DEFAULT_OBJECTIVE
const tips = F2_49_TIPS
const filledCount = computed(
  () => rev.enrichedProducts.value.filter((row) => !isBlankReversalItem(row)).length,
)

const CONCLUSION_KEY = 'F2-49-audit-conclusion'
const auditConclusion = ref('')
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  const item = { item_id: CONCLUSION_KEY, conclusion: null, remark: val }
  props.allResponses.set(CONCLUSION_KEY, item)
  window.dispatchEvent(new CustomEvent('f2-val:save-items', { detail: { items: [item] } }))
}
onMounted(() => {
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

const wpIdRef = toRef(() => props.wpId || '') as Ref<string>
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2ValuationAiGenerate(wpIdRef)

function aiContext(): Record<string, unknown> {
  return {
    sheet: 'F2-49',
    itemCount: filledCount.value,
    reversalTotal: rev.columnTotals.value.reversalTotal,
    priorProvisionTotal: rev.columnTotals.value.priorProvision,
    reverseCount: rev.summary.value.reverseCount,
    verifyFailCount: rev.summary.value.verifyFailCount,
    issuanceMismatchCount: rev.summary.value.issuanceMismatchCount,
    agingMismatchCount: rev.summary.value.agingMismatchCount,
    accountAllocation: {
      costOfSales: rev.columnTotals.value.costOfSales,
      rndExpense: rev.columnTotals.value.rndExpense,
      other: rev.columnTotals.value.other,
    },
  }
}

async function runAi(section: F2ValAiSection): Promise<void> {
  const isNote = section === 'reversal-note'
  const existing = isNote ? rev.auditNote.value : auditConclusion.value
  const title = isNote ? 'AI 生成 · 跌价转回审计说明' : 'AI 生成 · 跌价转回审计结论'
  const text = await generateAndConfirm(section, existing || '', aiContext(), title)
  if (!text) return
  if (isNote) rev.auditNote.value = text
  else saveAuditConclusion(text)
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
</script>

<style scoped src="./f2ValSheetStyles.css"></style>
<style scoped>
.f2-reversal { --gt-purple: #4b2d77; --gt-purple-soft: #f3eef8; --gt-aging: #f3eef8; }

.table-scroll { overflow-x: auto; margin-bottom: 12px; }
.matrix-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
  min-width: 2400px;
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
.grp-open { background: #ede8f4 !important; }
.grp-aging, .col-aging-h { color: #c45656; }
.grp-issue { background: #eef5fc !important; }
.grp-acct { background: #f0f9eb !important; }
.matrix-table th.sub.aging { color: #c45656; }
.col-cat { min-width: 68px; }
.col-code { min-width: 64px; }
.col-name { min-width: 80px; text-align: left !important; padding-left: 4px !important; background: #faf8fc; }
.col-spec { min-width: 64px; }
.col-unit { width: 44px; }
.col-flag { width: 56px; }
.col-rev { min-width: 80px; }
.col-verify { min-width: 56px; font-weight: 600; }
.col-act { width: 36px; }
.open-amt, .aging-cell { background: var(--gt-aging) !important; }
.rev-amt { color: #67c23a; font-weight: 600; }
.row-total td { background: #f0ebf5; font-weight: 600; }
.row-warn td { background: #fdf6ec; }
.row-aging td { box-shadow: inset 0 0 0 1px #f56c6c; }
.auto { text-align: right; padding-right: 3px; white-space: nowrap; color: #606266; }
span.auto { display: block; }
.calc { font-weight: 500; color: #4b2d77; }
.verify-ok { color: #67c23a; }
.verify-fail { color: #f56c6c; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }

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

:deep(.compact-num) { width: 60px; }
:deep(.compact-num.wide) { width: 76px; }
:deep(.compact-num .el-input__inner) { text-align: right; padding: 0 2px; font-size: 10px; }
</style>
