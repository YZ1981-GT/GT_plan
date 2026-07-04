<script setup lang="ts">
/** F3TabOverdueCheck — F3-5 逾期票据检查 | Task 6.4 */
import { toRef, inject, type Ref } from 'vue'
import { useF3OverdueCheck } from '../composables/useF3OverdueCheck'
import { useF3AiGenerate } from '../composables/useF3AiGenerate'
import F3ImportExportToolbar from './F3ImportExportToolbar.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const reloadWorkpaperData = inject<(() => void) | null>('reloadWorkpaperData', null)
function onImported() { reloadWorkpaperData?.() }

function fmt(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const { rows, summary, auditConclusion, addRow, removeRow, updateCell, rowClassName } = useF3OverdueCheck({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF3AiGenerate(toRef(props, 'wpId') as Ref<string>)

async function generateAiConclusion() {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'overdue-evaluation',
    auditConclusion.value,
    {
      overdueCount: summary.value.count,
      overdueAmount: summary.value.totalAmount,
      highRiskCount: summary.value.highRisk,
      transferredCount: summary.value.transferred,
    },
    'AI 生成 · 逾期检查评价',
  )
  if (text) auditConclusion.value = text
}

const riskOptions = ['低', '中', '高', '极高']
</script>

<template>
  <div class="f3-tab-overdue">
    <details class="guidance-details"><summary>📋 编制提示</summary><p>逾期&gt;90天建议高风险(红)，&gt;30天橙色。</p></details>
    <div class="toolbar">
      <el-button size="small" :disabled="isReadonly" @click="addRow">+ 添加行</el-button>
      <F3ImportExportToolbar :wp-id="wpId" :project-id="projectId" sheet="F3-5" :disabled="isReadonly" @imported="onImported" />
    </div>
    <el-table :data="rows" border size="small" :row-class-name="rowClassName" style="font-size:13px">
      <el-table-column prop="seq" label="序号" width="55" />
      <el-table-column label="出票人" min-width="100">
        <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.drawer" size="small" @change="(v: string) => updateCell(row.rowId, 'drawer', v)" /><span v-else>{{ row.drawer }}</span></template>
      </el-table-column>
      <el-table-column label="到期日" width="110">
        <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.dueDate" size="small" @change="(v: string) => updateCell(row.rowId, 'dueDate', v)" /><span v-else>{{ row.dueDate }}</span></template>
      </el-table-column>
      <el-table-column label="面值" width="100" align="right">
        <template #default="{ row }"><el-input-number v-if="!isReadonly" :model-value="row.faceValue" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'faceValue', v ?? 0)" /><span v-else>{{ fmt(row.faceValue) }}</span></template>
      </el-table-column>
      <el-table-column label="逾期天数" width="90" align="right"><template #default="{ row }"><span class="formula-cell">{{ row.overdueDays }}</span></template></el-table-column>
      <el-table-column label="风险等级" width="100">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.riskLevel" size="small" @change="(v: string) => updateCell(row.rowId, 'riskLevel', v)">
            <el-option v-for="o in riskOptions" :key="o" :label="o" :value="o" />
          </el-select>
          <span v-else>{{ row.riskLevel }}</span>
        </template>
      </el-table-column>
      <el-table-column label="审计建议" min-width="120">
        <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.auditAdvice" size="small" @change="(v: string) => updateCell(row.rowId, 'auditAdvice', v)" /><span v-else>{{ row.auditAdvice }}</span></template>
      </el-table-column>
      <el-table-column label="操作" width="55"><template #default="{ row }"><el-button link type="danger" size="small" :disabled="isReadonly" @click="removeRow(row.rowId)">删</el-button></template></el-table-column>
    </el-table>
    <div class="summary">逾期 {{ summary.count }} 笔 / 金额 {{ fmt(summary.totalAmount) }} / 高风险 {{ summary.highRisk }} 笔 / 已转应付 {{ summary.transferred }} 笔</div>
    <el-card shadow="never">
      <template #header>
        <div class="audit-header">
          <span>审计结论</span>
          <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="generateAiConclusion">AI 辅助</el-button>
        </div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :rows="3" :disabled="isReadonly" />
    </el-card>
  </div>
</template>

<style scoped>
.f3-tab-overdue { font-size: 13px; }
.toolbar { margin-bottom: 8px; }
.formula-cell { background: #f5f7fa; border-bottom: 1px dashed #c0c4cc; }
:deep(.risk-high td) { background: #fef0f0 !important; }
:deep(.risk-medium td) { background: #fdf6ec !important; }
.summary { margin: 8px 0; text-align: right; font-weight: 600; }
.audit-header { display: flex; justify-content: space-between; align-items: center; }
</style>
