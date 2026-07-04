<script setup lang="ts">
/** F3TabRelatedParty — F3-6 关联方检查 | Task 6.4 */
import { toRef, inject, type Ref } from 'vue'
import { useF3RelatedParty } from '../composables/useF3RelatedParty'
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

const { rows, summary, auditNote, addRow, removeRow, updateCell, rowClassName } = useF3RelatedParty({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF3AiGenerate(toRef(props, 'wpId') as Ref<string>)

async function generateAiNote() {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'related-evaluation',
    auditNote.value,
    {
      partyCount: rows.value.length,
      totalFace: summary.value.totalFace,
      unfairCount: summary.value.unfairCount,
    },
    'AI 生成 · 关联方评价',
  )
  if (text) auditNote.value = text
}

const fairnessOptions = ['公允', '基本公允', '不公允', '无法判断']
</script>

<template>
  <div class="f3-tab-related">
    <details class="guidance-details"><summary>📋 编制提示</summary><p>占比&gt;30% 橙色高亮集中度风险。</p></details>
    <div class="toolbar">
      <el-button size="small" :disabled="isReadonly" @click="addRow">+ 添加行</el-button>
      <F3ImportExportToolbar :wp-id="wpId" :project-id="projectId" sheet="F3-6" :disabled="isReadonly" @imported="onImported" />
    </div>
    <el-table :data="rows" border size="small" :row-class-name="rowClassName" style="font-size:13px">
      <el-table-column prop="seq" label="序号" width="55" />
      <el-table-column label="关联方" min-width="120">
        <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.partyName" size="small" @change="(v: string) => updateCell(row.rowId, 'partyName', v)" /><span v-else>{{ row.partyName }}</span></template>
      </el-table-column>
      <el-table-column label="关联关系" width="100">
        <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.relationship" size="small" @change="(v: string) => updateCell(row.rowId, 'relationship', v)" /><span v-else>{{ row.relationship }}</span></template>
      </el-table-column>
      <el-table-column label="面值" width="110" align="right">
        <template #default="{ row }"><el-input-number v-if="!isReadonly" :model-value="row.faceValue" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'faceValue', v ?? 0)" /><span v-else>{{ fmt(row.faceValue) }}</span></template>
      </el-table-column>
      <el-table-column label="占比%" width="90" align="right"><template #default="{ row }"><span class="formula-cell">{{ row.concentration.toFixed(2) }}%</span></template></el-table-column>
      <el-table-column label="定价公允性" width="110">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.fairness" size="small" @change="(v: string) => updateCell(row.rowId, 'fairness', v)">
            <el-option v-for="o in fairnessOptions" :key="o" :label="o" :value="o" />
          </el-select>
          <span v-else>{{ row.fairness }}</span>
        </template>
      </el-table-column>
      <el-table-column label="审计评价" min-width="120">
        <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.auditEvaluation" size="small" @change="(v: string) => updateCell(row.rowId, 'auditEvaluation', v)" /><span v-else>{{ row.auditEvaluation }}</span></template>
      </el-table-column>
      <el-table-column label="操作" width="55"><template #default="{ row }"><el-button link type="danger" size="small" :disabled="isReadonly" @click="removeRow(row.rowId)">删</el-button></template></el-table-column>
    </el-table>
    <div class="summary">关联方票据合计 {{ fmt(summary.totalFace) }} | 不公允 {{ summary.unfairCount }} 笔</div>
    <el-card shadow="never"><template #header><div class="audit-header"><span>审计说明</span><el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="generateAiNote">AI 辅助</el-button></div></template><el-input v-model="auditNote" type="textarea" :rows="3" :disabled="isReadonly" /></el-card>
  </div>
</template>

<style scoped>
.f3-tab-related { font-size: 13px; }
.toolbar { margin-bottom: 8px; }
.formula-cell { background: #f5f7fa; border-bottom: 1px dashed #c0c4cc; }
:deep(.concentration-warn td) { background: #fdf6ec !important; }
.summary { margin: 8px 0; text-align: right; font-weight: 600; }
.audit-header { display: flex; justify-content: space-between; align-items: center; }
</style>
