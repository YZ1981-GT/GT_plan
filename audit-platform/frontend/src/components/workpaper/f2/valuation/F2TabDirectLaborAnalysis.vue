<template>
  <div class="f2-val-sheet">
    <header class="sheet-header">
      <div><h3>直接人工分析表</h3><span class="code">F2-42</span></div>
      <div class="stat-row">
        <span class="stat">计算合计 {{ lb.laborGrandTotal.value.toLocaleString() }}</span>
        <el-tag v-if="lb.varianceCount.value" type="warning" size="small">{{ lb.varianceCount.value }} 行差异>5%</el-tag>
      </div>
    </header>

    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="lb.addRow()">+ 新增</el-button>
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
      <el-table-column label="计算人工费" width="105" align="right">
        <template #default="{ row }"><span class="formula">{{ row.calculatedLabor.toLocaleString() }}</span></template>
      </el-table-column>
      <el-table-column label="实际人工费" width="105">
        <template #default="{ row }">
          <el-input-number :model-value="row.actualLabor" size="small" :controls="false" :disabled="isReadonly"
            class="compact-num" @change="(v: number) => lb.updateRow(row.rowId, { actualLabor: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="占比%" width="75" align="right">
        <template #default="{ row }">{{ row.sharePct.toFixed(1) }}</template>
      </el-table-column>
      <el-table-column label="" width="48">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="lb.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <footer class="footer">
      <h4>审计说明</h4>
      <el-input v-model="lb.auditNote.value" type="textarea" :rows="3" :disabled="isReadonly" />
    </footer>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useF2DirectLaborAnalysis } from '../../composables/useF2DirectLaborAnalysis'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
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
