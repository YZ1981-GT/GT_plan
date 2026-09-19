<template>
  <div class="f2-val-sheet f2-obsolete">
    <header class="sheet-header">
      <div>
        <h3>长库龄/呆滞/超过保质期存货明细表</h3>
        <span class="code">F2-48</span>
      </div>
      <div class="stat-row">
        <span class="stat">结存合计 {{ fmt(obs.columnTotals.value.endingAmount) }}</span>
        <span class="stat sub">跌价合计 {{ fmt(obs.columnTotals.value.provisionAmount) }}</span>
        <el-tag v-if="obs.summary.value.longAgeCount" type="warning" size="small">
          长库龄 {{ obs.summary.value.longAgeCount }} 项
        </el-tag>
        <el-tag v-if="obs.summary.value.agingMismatchCount" type="danger" size="small">
          库龄勾稽异常 {{ obs.summary.value.agingMismatchCount }} 项
        </el-tag>
      </div>
    </header>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 列示存在长库龄、呆滞、冷背、过时或超过保质期等减值迹象的存货明细及库龄分布。</p>
        <p>2. 结存金额 = 结存数量 × 结存单价（紫色底纹区域）；库龄四档数量合计应等于结存数量。</p>
        <p>3. 减值迹象栏据盘点与管理层的分析填列；计提跌价金额为账面已计提数，供 F2-47 比较测试。</p>
        <p>4. 2 年以上库龄或存在减值迹象的行自动高亮，须关注可变现净值与跌价充分性。</p>
      </div>
    </details>

    <el-alert type="info" :closable="false" :title="objectiveText" class="objective-alert" />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="obs.addProduct()">+ 存货</el-button>
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-val"
          sheet="F2-48"
          :disabled="isReadonly"
          review-section="F2-48-conclusion"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:F2-48" /></span>
        <el-tag size="small" type="info">{{ filledCount }} 行</el-tag>
      </div>
    </div>

    <div class="table-scroll">
      <table class="matrix-table">
        <thead>
          <tr>
            <th rowspan="2" class="col-cat">存货类别</th>
            <th rowspan="2" class="col-code">存货编码</th>
            <th rowspan="2" class="col-name">存货名称</th>
            <th rowspan="2" class="col-spec">存货规格</th>
            <th rowspan="2" class="col-unit">单位</th>
            <th rowspan="2">结存数量</th>
            <th rowspan="2">结存单价</th>
            <th rowspan="2" class="col-amt">结存金额</th>
            <th colspan="4" class="col-aging-h">库龄</th>
            <th rowspan="2" class="col-sign">减值迹象</th>
            <th rowspan="2" class="col-prov">计提跌价金额</th>
            <th rowspan="2" class="col-act" />
          </tr>
          <tr>
            <th class="sub aging">1年以内</th>
            <th class="sub aging">1-2年</th>
            <th class="sub aging">2-3年</th>
            <th class="sub aging">3年以上</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in obs.enrichedProducts.value"
            :key="row.id"
            :class="{
              'row-warn': row.highlight,
              'row-aging': row.agingMismatch,
            }"
          >
            <td class="col-cat">
              <el-input v-if="!isReadonly" :model-value="row.category" size="small"
                @update:model-value="(v: string) => obs.updateProduct(row.id, { category: v })" />
              <span v-else>{{ row.category || '—' }}</span>
            </td>
            <td>
              <el-input v-if="!isReadonly" :model-value="row.itemCode" size="small"
                @update:model-value="(v: string) => obs.updateProduct(row.id, { itemCode: v })" />
              <span v-else>{{ row.itemCode || '—' }}</span>
            </td>
            <td class="col-name">
              <el-input v-if="!isReadonly" :model-value="row.itemName" size="small"
                @update:model-value="(v: string) => obs.updateProduct(row.id, { itemName: v })" />
              <span v-else>{{ row.itemName || '—' }}</span>
            </td>
            <td>
              <el-input v-if="!isReadonly" :model-value="row.specification" size="small"
                @update:model-value="(v: string) => obs.updateProduct(row.id, { specification: v })" />
              <span v-else>{{ row.specification || '—' }}</span>
            </td>
            <td>
              <el-input v-if="!isReadonly" :model-value="row.unit" size="small"
                @update:model-value="(v: string) => obs.updateProduct(row.id, { unit: v })" />
              <span v-else>{{ row.unit || '—' }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.qty" size="small" :controls="false"
                class="compact-num" @change="(v: number | undefined) => obs.updateProduct(row.id, { qty: v ?? 0 })" />
              <span v-else class="auto">{{ fmtQty(row.qty) }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.unitPrice" size="small" :controls="false"
                :precision="4" class="compact-num"
                @change="(v: number | undefined) => obs.updateProduct(row.id, { unitPrice: v ?? 0 })" />
              <span v-else class="auto">{{ fmtUnit(row.unitPrice) }}</span>
            </td>
            <td class="auto calc col-amt">{{ fmt(row.endingAmount) }}</td>
            <td class="aging-cell">
              <el-input-number v-if="!isReadonly" :model-value="row.aging.within1y" size="small" :controls="false"
                class="compact-num" @change="(v: number | undefined) => obs.updateAging(row.id, { within1y: v ?? 0 })" />
              <span v-else class="auto">{{ fmtQty(row.aging.within1y) }}</span>
            </td>
            <td class="aging-cell">
              <el-input-number v-if="!isReadonly" :model-value="row.aging.y1to2" size="small" :controls="false"
                class="compact-num" @change="(v: number | undefined) => obs.updateAging(row.id, { y1to2: v ?? 0 })" />
              <span v-else class="auto">{{ fmtQty(row.aging.y1to2) }}</span>
            </td>
            <td class="aging-cell">
              <el-input-number v-if="!isReadonly" :model-value="row.aging.y2to3" size="small" :controls="false"
                class="compact-num" @change="(v: number | undefined) => obs.updateAging(row.id, { y2to3: v ?? 0 })" />
              <span v-else class="auto">{{ fmtQty(row.aging.y2to3) }}</span>
            </td>
            <td class="aging-cell">
              <el-input-number v-if="!isReadonly" :model-value="row.aging.over3y" size="small" :controls="false"
                class="compact-num" @change="(v: number | undefined) => obs.updateAging(row.id, { over3y: v ?? 0 })" />
              <span v-else class="auto">{{ fmtQty(row.aging.over3y) }}</span>
            </td>
            <td class="col-sign">
              <el-select v-if="!isReadonly" :model-value="row.impairmentSigns || undefined" size="small"
                clearable filterable allow-create default-first-option
                placeholder="选择或输入"
                @update:model-value="(v: string) => obs.updateProduct(row.id, { impairmentSigns: v || '' })">
                <el-option v-for="s in signOptions" :key="s" :label="s" :value="s" />
              </el-select>
              <span v-else :class="{ 'sign-warn': row.hasImpairmentSign }">{{ row.impairmentSigns || '—' }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.provisionAmount" size="small" :controls="false"
                class="compact-num wide"
                @change="(v: number | undefined) => obs.updateProduct(row.id, { provisionAmount: v ?? 0 })" />
              <span v-else class="auto">{{ fmt(row.provisionAmount) }}</span>
            </td>
            <td class="col-act">
              <el-button v-if="!isReadonly" link type="danger" size="small" @click="obs.removeProduct(row.id)">删</el-button>
            </td>
          </tr>
          <tr class="row-total">
            <td colspan="5" class="col-name">合计</td>
            <td class="auto">{{ fmtQty(obs.columnTotals.value.qty) }}</td>
            <td />
            <td class="auto calc">{{ fmt(obs.columnTotals.value.endingAmount) }}</td>
            <td class="auto aging-cell">{{ fmtQty(obs.columnTotals.value.agingWithin1y) }}</td>
            <td class="auto aging-cell">{{ fmtQty(obs.columnTotals.value.agingY1to2) }}</td>
            <td class="auto aging-cell">{{ fmtQty(obs.columnTotals.value.agingY2to3) }}</td>
            <td class="auto aging-cell">{{ fmtQty(obs.columnTotals.value.agingOver3y) }}</td>
            <td />
            <td class="auto">{{ fmt(obs.columnTotals.value.provisionAmount) }}</td>
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
            @click="runAi('obsolete-note')"
          >AI 填写审计说明</el-button>
        </div>
      </template>
      <el-input v-model="obs.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="说明长库龄/呆滞/超保质期存货的识别过程、减值迹象分析及与跌价准备的勾稽..." />
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
            @click="runAi('obsolete-conclusion')"
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
import { useF2ObsoleteInventory } from '../../composables/useF2ObsoleteInventory'
import { useF2ValuationAiGenerate, type F2ValAiSection } from '../../composables/useF2ValuationAiGenerate'
import {
  F2_48_DEFAULT_OBJECTIVE,
  F2_48_TIPS,
  IMPAIRMENT_SIGN_OPTIONS,
  isBlankObsoleteItem,
} from '../../composables/useF2ObsoleteInventoryFormulas'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
import GtIndexChip from '../../GtIndexChip.vue'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const obs = useF2ObsoleteInventory({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const objectiveText = F2_48_DEFAULT_OBJECTIVE
const tips = F2_48_TIPS
const signOptions = IMPAIRMENT_SIGN_OPTIONS

const CONCLUSION_KEY = 'F2-48-audit-conclusion'
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

const filledCount = computed(
  () => obs.enrichedProducts.value.filter((r) => !isBlankObsoleteItem(r)).length,
)

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2ValuationAiGenerate(
  toRef(() => props.wpId || '') as Ref<string>,
)

function aiContext(): Record<string, unknown> {
  return {
    sheet: 'F2-48',
    rowCount: filledCount.value,
    endingTotal: obs.columnTotals.value.endingAmount,
    provisionTotal: obs.columnTotals.value.provisionAmount,
    longAgeCount: obs.summary.value.longAgeCount,
    obsoleteCount: obs.summary.value.obsoleteCount,
    expiredCount: obs.summary.value.expiredCount,
    agingMismatchCount: obs.summary.value.agingMismatchCount,
  }
}

async function runAi(section: F2ValAiSection) {
  const existing = section === 'obsolete-note' ? (obs.auditNote.value || '') : (auditConclusion.value || '')
  const title = section === 'obsolete-note' ? 'AI 生成 · 审计说明' : 'AI 生成 · 呆滞存货结论'
  const text = await generateAndConfirm(section, existing, aiContext(), title)
  if (!text) return
  if (section === 'obsolete-note') {
    obs.auditNote.value = text
  } else {
    auditConclusion.value = text
    saveAuditConclusion(text)
  }
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
.f2-obsolete { --gt-purple: #4b2d77; --gt-purple-soft: #f3eef8; --gt-aging: #f3eef8; }

.table-scroll { overflow-x: auto; margin-bottom: 12px; }
.matrix-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  min-width: 1280px;
}
.matrix-table th,
.matrix-table td {
  border: 1px solid #d4c8e0;
  padding: 2px 4px;
  text-align: center;
  vertical-align: middle;
}
.matrix-table thead th {
  background: var(--gt-purple-soft);
  color: #3d2a55;
  font-weight: 600;
}
.matrix-table th.sub.aging { color: #c45656; font-weight: 600; }
.col-aging-h { color: #c45656; }
.col-cat { min-width: 72px; }
.col-code { min-width: 72px; }
.col-name { min-width: 88px; text-align: left !important; padding-left: 6px !important; background: #faf8fc; }
.col-spec { min-width: 72px; }
.col-unit { width: 48px; }
.col-amt { min-width: 88px; background: var(--gt-aging) !important; }
.aging-cell { background: var(--gt-aging) !important; }
.col-sign { min-width: 100px; }
.col-prov { min-width: 88px; }
.col-act { width: 40px; }
.row-total td { background: #f0ebf5; font-weight: 600; }
.row-warn td { background: #fdf6ec; }
.row-aging td { box-shadow: inset 0 0 0 1px #f56c6c; }
.auto { text-align: right; padding-right: 4px; white-space: nowrap; color: #606266; }
span.auto { display: block; }
.calc { font-weight: 500; color: #4b2d77; }
.sign-warn { color: #e6a23c; font-weight: 600; }

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

:deep(.compact-num) { width: 72px; }
:deep(.compact-num.wide) { width: 88px; }
:deep(.compact-num .el-input__inner) { text-align: right; padding: 0 3px; font-size: 11px; }
</style>
