<template>
  <div class="f2-val-sheet">
    <header class="sheet-header">
      <div><h3>直接人工分析表</h3><span class="code">F2-42</span></div>
      <div class="stat-row">
        <span class="stat">计算合计 {{ lb.laborGrandTotal.value.toLocaleString() }}</span>
        <el-tag v-if="lb.varianceCount.value" type="warning" size="small">{{ lb.varianceCount.value }} 行差异>5%</el-tag>
      </div>
    </header>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 直接人工按部门/工种分析人数、工时、工资率与人工费用的匹配性，验证人工成本归集与分配的合理性（CAS 1 号存货加工成本）。</p>
        <p>2. 灰色底纹列为自动计算列（计算人工费、占比），据工时×工资率自动测算，不可手工编辑。</p>
        <p>3. 计算人工费与实际人工费差异率超过 5% 的行自动标橙，须核查工时统计、工资率取数或人工费归集是否存在异常。</p>
        <p>4. 关注人工费用是否跨期、是否将非生产人员薪酬错误计入直接人工，影响存货成本计价。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：验证直接人工成本归集与分配的合理性，通过工时、工资率重新计算复核人工费用，识别异常波动，为存货加工成本准确性提供分析证据。"
      class="objective-alert"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="lb.addRow()">+ 新增</el-button>
      </div>
      <div class="toolbar-right">
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
        <span class="chip-wrap"><GtIndexChip value="wp:F2-1" /></span>
        <el-tag size="small" type="info">共 {{ lb.enrichedRows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-table
      :data="lb.enrichedRows.value" border size="small" max-height="460"
      :row-class-name="({ row }) => (typeof row.varianceRate === 'number' && Math.abs(row.varianceRate) > 0.05) ? 'warn-row' : ''"
    >
      <el-table-column label="部门/产品" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.department" size="small"
            @change="(v: string) => lb.updateRow(row.rowId, { department: v })" />
          <span v-else>{{ row.department }}</span>
        </template>
      </el-table-column>
      <el-table-column label="工种" width="90">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.jobType" size="small"
            @change="(v: string) => lb.updateRow(row.rowId, { jobType: v })" />
          <span v-else>{{ row.jobType }}</span>
        </template>
      </el-table-column>
      <el-table-column label="人数" width="80">
        <template #default="{ row }">
          <el-input-number :model-value="row.headcount" size="small" :controls="false" :disabled="isReadonly"
            class="compact-num" @change="(v: number) => lb.updateRow(row.rowId, { headcount: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="工时" width="80">
        <template #default="{ row }">
          <el-input-number :model-value="row.hours" size="small" :controls="false" :disabled="isReadonly"
            class="compact-num" @change="(v: number) => lb.updateRow(row.rowId, { hours: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="工资率" width="85">
        <template #default="{ row }">
          <el-input-number :model-value="row.wageRate" size="small" :controls="false" :disabled="isReadonly"
            class="compact-num" @change="(v: number) => lb.updateRow(row.rowId, { wageRate: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="计算人工费" width="105" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="formula" title="工时 × 工资率">{{ row.calculatedLabor.toLocaleString() }}</span></template>
      </el-table-column>
      <el-table-column label="实际人工费" width="105">
        <template #default="{ row }">
          <el-input-number :model-value="row.actualLabor" size="small" :controls="false" :disabled="isReadonly"
            class="compact-num" @change="(v: number) => lb.updateRow(row.rowId, { actualLabor: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="占比%" width="75" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="formula" title="本行实际人工费 ÷ 人工费合计 × 100%">{{ row.sharePct.toFixed(1) }}</span></template>
      </el-table-column>
      <el-table-column label="" width="48">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="lb.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header"><span class="opinion-title">审计说明</span></div>
      </template>
      <el-input v-model="lb.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="直接人工分析审计说明..." />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useF2DirectLaborAnalysis } from '../../composables/useF2DirectLaborAnalysis'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
import GtIndexChip from '../../GtIndexChip.vue'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()
const lb = useF2DirectLaborAnalysis({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})
</script>

<style scoped src="./f2ValSheetStyles.css"></style>
