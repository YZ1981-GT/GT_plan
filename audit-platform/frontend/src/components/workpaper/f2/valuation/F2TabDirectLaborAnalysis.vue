<template>
  <div class="f2-val-sheet f2-labor">
    <header class="sheet-header">
      <div><h3>直接人工分析表</h3><span class="code">F2-42</span></div>
      <div class="stat-row">
        <span class="stat">人工合计 {{ fmt(lb.laborGrandTotal.value) }}</span>
        <el-tag v-if="lb.varianceCount.value" type="warning" size="small">
          单位成本异常 {{ lb.varianceCount.value }} 项
        </el-tag>
      </div>
    </header>

    <el-alert type="info" :closable="false" show-icon class="objective-alert" title="一、测试目标" />
    <el-input
      :model-value="objectiveText"
      type="textarea"
      :autosize="{ minRows: 2, maxRows: 4 }"
      :disabled="isReadonly"
      class="section-text"
      @update:model-value="(v: string) => { objectiveText = v }"
    />

    <div class="section-label">二、审计程序</div>
    <el-input
      :model-value="lb.auditProcedure.value"
      type="textarea"
      :autosize="{ minRows: 2, maxRows: 4 }"
      :disabled="isReadonly"
      class="section-text"
      :placeholder="defaultProcedure"
      @update:model-value="(v: string) => lb.setProcedure(v)"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="lb.addLine()">+ 产品</el-button>
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-val"
          sheet="F2-42"
          :disabled="isReadonly"
          ai-section="labor-analysis"
          :existing-content="lb.auditNote.value"
          :related-context="{ varianceCount: lb.varianceCount.value }"
          ai-title="AI 生成 · 直接人工分析结论"
          review-section="F2-42-conclusion"
          @ai-filled="(t: string) => { lb.auditNote.value = t }"
        />
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:F2-42" /></span>
        <el-tag size="small" type="info">{{ lb.enrichedLines.value.length }} 个产品</el-tag>
      </div>
    </div>

    <!-- 表1：各月发生的直接人工 -->
    <div class="table-title">各月发生的直接人工</div>
    <LaborMatrixTable
      :lines="lb.enrichedLines.value"
      :month-labels="monthLabels"
      :is-readonly="isReadonly"
      summary-label="合计"
      value-kind="labor"
      prior-field="laborPriorYear"
      change-rate-field="laborChangeRate"
      total-field="laborTotal"
      @update-name="(id, v) => lb.updateLine(id, { productName: v })"
      @update-month="(id, m, v) => lb.updateLaborMonth(id, m, v)"
      @update-prior="(id, v) => lb.updateLine(id, { laborPriorYear: v })"
      @update-reason="(id, v) => lb.updateLine(id, { changeReason: v })"
      @remove="(id) => lb.removeLine(id)"
    />

    <!-- 表2：各月产量/工时 -->
    <div class="table-title">各月产量/工时</div>
    <LaborMatrixTable
      :lines="lb.enrichedLines.value"
      :month-labels="monthLabels"
      :is-readonly="isReadonly"
      summary-label="合计"
      value-kind="output"
      prior-field="outputPriorYear"
      change-rate-field="outputChangeRate"
      total-field="outputTotal"
      @update-name="(id, v) => lb.updateLine(id, { productName: v })"
      @update-month="(id, m, v) => lb.updateOutputMonth(id, m, v)"
      @update-prior="(id, v) => lb.updateLine(id, { outputPriorYear: v })"
      @remove="(id) => lb.removeLine(id)"
    />

    <!-- 表3：单位人工成本（自动） -->
    <div class="table-title">单位人工成本 <span class="formula-hint">= 直接人工 ÷ 产量/工时</span></div>
    <LaborMatrixTable
      :lines="lb.enrichedLines.value"
      :month-labels="monthLabels"
      :is-readonly="true"
      summary-label="平均值"
      value-kind="unit"
      prior-field="unitPriorYear"
      change-rate-field="unitChangeRate"
      total-field="unitAverage"
      highlight-variance
      @update-prior="(id, v) => lb.updateLine(id, { unitPriorYear: v })"
    />

    <el-card shadow="never" class="conclusion-card">
      <template #header><span class="conclusion-header">三、审计说明</span></template>
      <el-input
        v-model="lb.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="直接人工分析审计说明..."
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
import { useF2DirectLaborAnalysis } from '../../composables/useF2DirectLaborAnalysis'
import {
  LABOR_MONTH_LABELS,
  F2_42_DEFAULT_OBJECTIVE,
  F2_42_PROCEDURE,
  F2_42_TIPS,
} from '../../composables/useF2DirectLaborMatrixFormulas'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
import GtIndexChip from '../../GtIndexChip.vue'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'
import LaborMatrixTable from './F2LaborMatrixTable.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const lb = useF2DirectLaborAnalysis({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const tips = F2_42_TIPS
const defaultProcedure = F2_42_PROCEDURE
const objectiveText = ref(F2_42_DEFAULT_OBJECTIVE)
const monthLabels = LABOR_MONTH_LABELS

const CONCLUSION_KEY = 'F2-42-audit-conclusion'
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
  if (!v) return '0'
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}
</script>

<style scoped src="./f2ValSheetStyles.css"></style>
<style scoped>
.f2-labor { --gt-purple: #4b2d77; --gt-purple-soft: #f3eef8; }
.section-label { margin: 14px 0 8px; font-size: 14px; font-weight: 600; }
.section-text { margin-bottom: 10px; }
.table-title {
  margin: 16px 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--gt-purple);
}
.formula-hint { font-weight: 400; color: #909399; font-size: 12px; }
.conclusion-card { margin-top: 14px; }
.conclusion-header { font-weight: 600; font-size: 14px; }
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
</style>
