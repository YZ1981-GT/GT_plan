<template>
  <div class="f2-val-sheet f2-related-purchase">
    <header class="sheet-header">
      <div>
        <h3>存货关联采购分析表</h3>
        <span class="code">F2-52</span>
      </div>
      <div class="stat-row">
        <span class="stat">关联采购 {{ fmt(rp.columnTotals.value.relatedAmount) }}</span>
        <span class="stat sub">数量占比 {{ fmtPct(rp.columnTotals.value.currentQtyRatio) }}</span>
        <span class="stat sub">金额占比 {{ fmtPct(rp.columnTotals.value.currentAmtRatio) }}</span>
        <el-tag v-if="rp.highDeviationCount.value" type="danger" size="small">
          单价差异&gt;10% {{ rp.highDeviationCount.value }} 项
        </el-tag>
      </div>
    </header>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 逐笔录入关联方、采购品名、本年关联采购与同类采购总量/总额，系统自动计算占比。</p>
        <p>2. 关联采购单价 = 金额 ÷ 数量；单价差异率与非关联方均价、上年均价比较。</p>
        <p>3. 偏差超过 10% 自动标红；价格异常须在审计说明中说明并索引 F2-65/F2-66 公允性测试。</p>
        <p>4. 关注 CAS 36 号关联方披露及未披露关联方识别（F2-67）。</p>
      </div>
    </details>

    <el-alert type="info" :closable="false" :title="objectiveText" class="objective-alert" />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="rp.addProduct()">+ 关联方采购</el-button>
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-val"
          sheet="F2-52"
          :disabled="isReadonly"
          ai-section="fairness-evaluation"
          :existing-content="rp.auditNote.value"
          :related-context="{ highDeviationCount: rp.highDeviationCount.value }"
          ai-title="AI 生成 · 关联采购公允性评价"
          review-section="F2-52-conclusion"
          @ai-filled="(t: string) => { rp.auditNote.value = t }"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:F2-52" /></span>
        <el-tag size="small" type="info">{{ rp.enrichedProducts.value.length }} 行</el-tag>
      </div>
    </div>

    <div class="table-scroll">
      <table class="matrix-table">
        <thead>
          <tr>
            <th rowspan="2" class="col-party">关联方名称</th>
            <th rowspan="2" class="col-rel">关联关系</th>
            <th rowspan="2" class="col-item">采购存货<br>名称/规格</th>
            <th rowspan="2" class="col-unit">单位</th>
            <th colspan="2" class="grp-rp">本年关联采购</th>
            <th colspan="2" class="grp-total">本年采购总量</th>
            <th colspan="2" class="grp-cy">本年占比</th>
            <th colspan="2" class="grp-py">上年占比</th>
            <th rowspan="2">关联<br>单价</th>
            <th rowspan="2">非关联方<br>均价</th>
            <th rowspan="2">单价<br>差异率</th>
            <th rowspan="2">上年<br>均价</th>
            <th rowspan="2" class="col-idx">索引号</th>
            <th rowspan="2" class="col-act" />
          </tr>
          <tr>
            <th class="sub">数量</th>
            <th class="sub">金额</th>
            <th class="sub">数量</th>
            <th class="sub">金额</th>
            <th class="sub">数量%</th>
            <th class="sub">金额%</th>
            <th class="sub">数量%</th>
            <th class="sub">金额%</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rp.enrichedProducts.value"
            :key="row.id"
            :class="{ 'row-warn': row.highlight }"
          >
            <td class="col-party">
              <el-input v-if="!isReadonly" :model-value="row.relatedPartyName" size="small"
                @update:model-value="(v: string) => rp.updateProduct(row.id, { relatedPartyName: v })" />
              <span v-else>{{ row.relatedPartyName || '—' }}</span>
            </td>
            <td>
              <el-select v-if="!isReadonly" :model-value="row.relationship || undefined" size="small" clearable filterable allow-create
                @update:model-value="(v: string) => rp.updateProduct(row.id, { relationship: v || '' })">
                <el-option v-for="r in relationshipOptions" :key="r" :label="r" :value="r" />
              </el-select>
              <span v-else>{{ row.relationship || '—' }}</span>
            </td>
            <td class="col-item">
              <el-input v-if="!isReadonly" :model-value="row.itemNameSpec" size="small"
                @update:model-value="(v: string) => rp.updateProduct(row.id, { itemNameSpec: v })" />
              <span v-else>{{ row.itemNameSpec || '—' }}</span>
            </td>
            <td>
              <el-input v-if="!isReadonly" :model-value="row.unit" size="small"
                @update:model-value="(v: string) => rp.updateProduct(row.id, { unit: v })" />
              <span v-else>{{ row.unit || '—' }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.relatedQty" size="small" :controls="false"
                class="compact-num" @change="(v: number | undefined) => rp.updateProduct(row.id, { relatedQty: v ?? 0 })" />
              <span v-else class="auto">{{ fmtQty(row.relatedQty) }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.relatedAmount" size="small" :controls="false"
                class="compact-num wide" @change="(v: number | undefined) => rp.updateProduct(row.id, { relatedAmount: v ?? 0 })" />
              <span v-else class="auto">{{ fmt(row.relatedAmount) }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.totalQty" size="small" :controls="false"
                class="compact-num" @change="(v: number | undefined) => rp.updateProduct(row.id, { totalQty: v ?? 0 })" />
              <span v-else class="auto">{{ fmtQty(row.totalQty) }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.totalAmount" size="small" :controls="false"
                class="compact-num wide" @change="(v: number | undefined) => rp.updateProduct(row.id, { totalAmount: v ?? 0 })" />
              <span v-else class="auto">{{ fmt(row.totalAmount) }}</span>
            </td>
            <td class="auto calc">{{ fmtPct(row.currentQtyRatio) }}</td>
            <td class="auto calc">{{ fmtPct(row.currentAmtRatio) }}</td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.priorQtyRatio * 100" size="small" :controls="false"
                class="compact-num" @change="(v: number | undefined) => rp.updateProduct(row.id, { priorQtyRatio: (v ?? 0) / 100 })" />
              <span v-else class="auto">{{ fmtPct(row.priorQtyRatio) }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.priorAmtRatio * 100" size="small" :controls="false"
                class="compact-num" @change="(v: number | undefined) => rp.updateProduct(row.id, { priorAmtRatio: (v ?? 0) / 100 })" />
              <span v-else class="auto">{{ fmtPct(row.priorAmtRatio) }}</span>
            </td>
            <td class="auto calc">{{ fmtUnit(row.relatedUnitPrice) }}</td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.nonRelatedAvgPrice" size="small" :controls="false"
                :precision="4" class="compact-num"
                @change="(v: number | undefined) => rp.updateProduct(row.id, { nonRelatedAvgPrice: v ?? 0 })" />
              <span v-else class="auto">{{ fmtUnit(row.nonRelatedAvgPrice) }}</span>
            </td>
            <td class="auto calc" :class="{ 'var-warn': row.isHighVariance }">
              {{ row.priceVarianceRate != null ? fmtPct(row.priceVarianceRate) : '—' }}
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.priorAvgPrice" size="small" :controls="false"
                :precision="4" class="compact-num"
                @change="(v: number | undefined) => rp.updateProduct(row.id, { priorAvgPrice: v ?? 0 })" />
              <span v-else class="auto">{{ fmtUnit(row.priorAvgPrice) }}</span>
            </td>
            <td class="col-idx">
              <el-input v-if="!isReadonly" :model-value="row.indexRef" size="small" placeholder="wp:F2-65"
                @update:model-value="(v: string) => rp.updateProduct(row.id, { indexRef: v })" />
              <span v-else class="idx">{{ row.indexRef || '—' }}</span>
            </td>
            <td class="col-act">
              <el-button v-if="!isReadonly" link type="danger" size="small" @click="rp.removeProduct(row.id)">删</el-button>
            </td>
          </tr>
          <tr class="row-total">
            <td colspan="4" class="col-item">合计</td>
            <td class="auto">{{ fmtQty(rp.columnTotals.value.relatedQty) }}</td>
            <td class="auto">{{ fmt(rp.columnTotals.value.relatedAmount) }}</td>
            <td class="auto">{{ fmtQty(rp.columnTotals.value.totalQty) }}</td>
            <td class="auto">{{ fmt(rp.columnTotals.value.totalAmount) }}</td>
            <td class="auto calc">{{ fmtPct(rp.columnTotals.value.currentQtyRatio) }}</td>
            <td class="auto calc">{{ fmtPct(rp.columnTotals.value.currentAmtRatio) }}</td>
            <td colspan="2" />
            <td class="auto calc">{{ fmtUnit(rp.columnTotals.value.relatedUnitPrice) }}</td>
            <td colspan="4" />
            <td />
          </tr>
        </tbody>
      </table>
    </div>

    <div class="section-label">1、审计说明</div>
    <div class="note-grid">
      <label v-for="(label, i) in auditNoteLabels" :key="i">
        <span class="note-label" :class="{ emphasis: i >= 2 }">{{ label }}</span>
        <el-input
          :model-value="auditNoteField(i)"
          type="textarea"
          :autosize="{ minRows: 1, maxRows: 4 }"
          :disabled="isReadonly"
          @update:model-value="(v: string) => setAuditNoteField(i, v)"
        />
      </label>
    </div>
    <el-input
      v-model="rp.auditNote.value"
      type="textarea"
      :autosize="{ minRows: 2, maxRows: 6 }"
      :disabled="isReadonly"
      class="free-note"
      placeholder="其他补充说明..."
    />

    <el-card class="opinion-card" shadow="never">
      <template #header><span class="opinion-title">2、审计结论</span></template>
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
import { ref, onMounted, toRef } from 'vue'
import { useF2RelatedPurchase } from '../../composables/useF2RelatedPurchase'
import {
  F2_52_DEFAULT_OBJECTIVE,
  F2_52_AUDIT_NOTE_LABELS,
  F2_52_TIPS,
  RELATIONSHIP_OPTIONS,
  type RelatedPurchaseAuditNotes,
} from '../../composables/useF2RelatedPurchaseFormulas'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
import GtIndexChip from '../../GtIndexChip.vue'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const rp = useF2RelatedPurchase({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const objectiveText = F2_52_DEFAULT_OBJECTIVE
const auditNoteLabels = F2_52_AUDIT_NOTE_LABELS
const tips = F2_52_TIPS
const relationshipOptions = RELATIONSHIP_OPTIONS

const NOTE_FIELDS: (keyof RelatedPurchaseAuditNotes)[] = [
  'weightDescription',
  'weightChangeReason',
  'priceAbnormalReason',
  'undisclosedParty',
]

function auditNoteField(index: number): string {
  const key = NOTE_FIELDS[index]
  return key ? rp.sheet.value.auditNotes[key] : ''
}

function setAuditNoteField(index: number, val: string): void {
  const key = NOTE_FIELDS[index]
  if (key) rp.updateAuditNotes({ [key]: val })
}

const CONCLUSION_KEY = 'F2-52-audit-conclusion'
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
function fmtPct(r: number): string {
  if (!Number.isFinite(r) || r === 0) return '—'
  return `${(r * 100).toFixed(2)}%`
}
</script>

<style scoped src="./f2ValSheetStyles.css"></style>
<style scoped>
.f2-related-purchase { --gt-purple: #4b2d77; --gt-purple-soft: #f3eef8; }

.table-scroll { overflow-x: auto; margin-bottom: 12px; }
.matrix-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
  min-width: 2000px;
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
.grp-rp { background: #f3eef8 !important; }
.grp-total { background: #eef5fc !important; }
.grp-cy { background: #f0f9eb !important; }
.grp-py { background: #fdf6ec !important; }
.col-party { min-width: 88px; }
.col-rel { min-width: 80px; }
.col-item { min-width: 100px; text-align: left !important; padding-left: 4px !important; background: #faf8fc; }
.col-unit { width: 44px; }
.col-idx { min-width: 72px; }
.col-act { width: 36px; }
.row-total td { background: #f0ebf5; font-weight: 600; }
.row-warn td { background: #fef0f0; }
.auto { display: block; text-align: right; padding-right: 3px; white-space: nowrap; color: #606266; }
.calc { color: #4b2d77; font-weight: 500; }
.var-warn { color: #f56c6c !important; font-weight: 600; }
.idx { font-size: 10px; color: #909399; }

.section-label { margin: 14px 0 8px; font-size: 14px; font-weight: 600; color: var(--gt-purple); }
.note-grid { display: flex; flex-direction: column; gap: 10px; margin-bottom: 10px; }
.note-grid label { display: flex; flex-direction: column; gap: 4px; }
.note-label { font-size: 12px; color: #606266; }
.note-label.emphasis { color: #c45656; font-weight: 500; }
.free-note { margin-bottom: 8px; }

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

:deep(.compact-num) { width: 68px; }
:deep(.compact-num.wide) { width: 84px; }
:deep(.compact-num .el-input__inner) { text-align: right; padding: 0 2px; font-size: 10px; }
</style>
