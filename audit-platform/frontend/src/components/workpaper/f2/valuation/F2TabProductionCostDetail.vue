<template>
  <div class="f2-val-sheet f2-prod-cost">
    <header class="sheet-header">
      <div><h3>生产成本明细表</h3><span class="code">F2-41</span></div>
      <div class="stat-row">
        <span class="stat">12月末余额 {{ fmt(totals.yearEndTotal) }}</span>
        <span class="stat sub">材料 {{ fmt(totals.rawMaterial) }}</span>
        <span class="stat sub">人工 {{ fmt(totals.labor) }}</span>
        <span class="stat sub">费用 {{ fmt(totals.overhead) }}</span>
      </div>
    </header>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      :title="`一、测试目标：${defaultObjective}`"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="pc.addBlock()">+ 成本对象</el-button>
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-val"
          sheet="F2-41"
          :disabled="isReadonly"
          ai-section="cost-analysis"
          :existing-content="pc.auditNote.value"
          ai-title="AI 生成 · 生产成本分析结论"
          review-section="F2-41-conclusion"
          @ai-filled="(t: string) => { pc.auditNote.value = t }"
        />
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:F2-41" /></span>
        <el-tag size="small" type="info">{{ pc.enrichedBlocks.value.length }} 个成本对象</el-tag>
      </div>
    </div>

    <section v-for="(block, bi) in pc.enrichedBlocks.value" :key="block.id" class="cost-block">
      <div class="block-head">
        <span class="block-title">成本对象{{ bi + 1 }}：</span>
        <el-input
          :model-value="block.productName"
          size="small"
          :disabled="isReadonly"
          placeholder="产品/成本对象名称"
          class="name-input"
          @update:model-value="(v: string) => pc.updateBlock(block.id, { productName: v })"
        />
        <el-button
          link
          type="danger"
          size="small"
          :disabled="isReadonly || pc.enrichedBlocks.value.length <= 1"
          @click="pc.removeBlock(block.id)"
        >删除</el-button>
      </div>

      <div class="table-scroll">
        <table class="matrix-table">
          <thead>
            <tr>
              <th rowspan="2" class="col-item">项目</th>
              <th colspan="12">月份</th>
              <th rowspan="2" class="col-total">合计</th>
              <th rowspan="2" class="col-prior">上年度</th>
              <th rowspan="2" class="col-rate">变动率</th>
              <th rowspan="2" class="col-reason">变动原因</th>
            </tr>
            <tr>
              <th v-for="m in monthLabels" :key="m.key">{{ m.label }}</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="row in block.rows" :key="row.key">
              <tr v-if="row.key === 'rawMaterial'" class="row-section">
                <td colspan="17" class="section-label">本期增加：</td>
              </tr>
              <tr
                :class="{
                  'row-indent': row.indent,
                  'row-computed': isComputed(row),
                  'row-opening': row.key === 'opening',
                  'row-ending': row.key === 'monthEnd',
                }"
              >
              <td class="col-item" :class="{ indent: row.indent }">{{ row.label }}</td>
              <td v-for="mk in monthKeys" :key="mk">
                <template v-if="isEditable(row, mk)">
                  <el-input-number
                    :model-value="row.months[mk]"
                    size="small"
                    :controls="false"
                    :disabled="isReadonly"
                    class="compact-num"
                    @change="(v: number | undefined) => pc.updateCell(block.id, row.key, mk, v ?? 0)"
                  />
                </template>
                <span v-else class="auto">{{ fmt(row.months[mk]) }}</span>
              </td>
              <td class="auto col-total">{{ fmt(row.total) }}</td>
              <td>
                <el-input-number
                  v-if="!isComputed(row)"
                  :model-value="row.priorYear"
                  size="small"
                  :controls="false"
                  :disabled="isReadonly"
                  class="compact-num"
                  @change="(v: number | undefined) => pc.updateRowMeta(block.id, row.key, { priorYear: v ?? 0 })"
                />
                <span v-else class="auto">{{ fmt(row.priorYear) }}</span>
              </td>
              <td class="auto col-rate">{{ fmtRate(row.changeRate) }}</td>
              <td>
                <el-input
                  v-if="!isComputed(row)"
                  :model-value="row.changeReason"
                  size="small"
                  :disabled="isReadonly"
                  @update:model-value="(v: string) => pc.updateRowMeta(block.id, row.key, { changeReason: v })"
                />
              </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </section>

    <el-card shadow="never" class="conclusion-card">
      <template #header><span class="conclusion-header">三、审计说明</span></template>
      <el-input
        v-model="pc.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="填写生产成本明细审计说明..."
      />
    </el-card>

    <el-card shadow="never" class="conclusion-card">
      <template #header><span class="conclusion-header">四、审计结论</span></template>
      <el-input
        :model-value="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="填写审计结论。"
        @update:model-value="saveAuditConclusion"
      />
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
import { useF2ProductionCostDetail } from '../../composables/useF2ProductionCostDetail'
import {
  PROD_COST_MONTH_KEYS,
  F2_41_TIPS,
  F2_41_DEFAULT_OBJECTIVE,
  type ProdCostMatrixRow,
  type ProdCostMonthKey,
} from '../../composables/useF2ProductionCostMatrixFormulas'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
import GtIndexChip from '../../GtIndexChip.vue'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const pc = useF2ProductionCostDetail({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const tips = F2_41_TIPS
const defaultObjective = F2_41_DEFAULT_OBJECTIVE

const monthKeys = PROD_COST_MONTH_KEYS
const monthLabels = [
  { key: '01', label: '1月' }, { key: '02', label: '2月' }, { key: '03', label: '3月' },
  { key: '04', label: '4月' }, { key: '05', label: '5月' }, { key: '06', label: '6月' },
  { key: '07', label: '7月' }, { key: '08', label: '8月' }, { key: '09', label: '9月' },
  { key: '10', label: '10月' }, { key: '11', label: '11月' }, { key: '12', label: '12月' },
]

const totals = pc.totals

const CONCLUSION_KEY = 'F2-41-audit-conclusion'
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

function isComputed(row: ProdCostMatrixRow): boolean {
  return row.kind === 'computed' || row.kind === 'ending'
}

function isEditable(row: ProdCostMatrixRow, mk: ProdCostMonthKey): boolean {
  if (isComputed(row)) return false
  if (row.key === 'opening' && mk !== '01') return false
  return true
}

function fmt(v: number): string {
  if (v === 0 || v == null || !Number.isFinite(v)) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(r: number | '' | 'N/A'): string {
  if (r === '' || r === 'N/A') return '—'
  return `${r.toFixed(2)}%`
}
</script>

<style scoped src="./f2ValSheetStyles.css"></style>
<style scoped>
.f2-prod-cost { --gt-purple: #4b2d77; --gt-purple-soft: #f3eef8; }

.cost-block {
  margin-bottom: 20px;
  border: 1px solid #e4dceb;
  border-radius: 6px;
  overflow: hidden;
}
.block-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: var(--gt-purple-soft);
  border-bottom: 1px solid #e4dceb;
}
.block-title { font-weight: 600; font-size: 13px; color: var(--gt-purple); }
.name-input { width: 220px; max-width: 40vw; }

.table-scroll { overflow-x: auto; }
.matrix-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  min-width: 1400px;
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
.col-item { width: 120px; text-align: left !important; padding-left: 8px !important; background: #faf8fc; }
.col-total { background: #f0ebf5 !important; min-width: 80px; }
.col-prior { min-width: 80px; }
.col-rate { min-width: 64px; }
.col-reason { min-width: 100px; }
.row-section td { background: #f7f3fb; font-weight: 600; text-align: left !important; padding-left: 12px !important; }
.indent { padding-left: 20px !important; }
.row-computed td { background: #f5f7fa; }
.row-opening td { background: #f7f3fb; }
.row-ending td { background: #f0ebf5; font-weight: 600; }
.auto {
  display: block;
  text-align: right;
  padding-right: 4px;
  color: #606266;
  white-space: nowrap;
}

.conclusion-card { margin-top: 14px; }
.conclusion-header { font-weight: 600; font-size: 14px; }

.tips-box {
  margin-top: 16px;
  padding: 12px 16px;
  background: #ecf5ff;
  border-left: 3px solid #409eff;
  border-radius: 4px;
  font-size: 13px;
  color: #3a4a6b;
  line-height: 1.7;
}
.tips-title { font-weight: 600; color: #409eff; margin-bottom: 6px; }
.tips-box ol { margin: 0; padding-left: 1.4em; }

:deep(.compact-num) { width: 68px; }
:deep(.compact-num .el-input__inner) { text-align: right; padding: 0 3px; font-size: 11px; }
</style>
