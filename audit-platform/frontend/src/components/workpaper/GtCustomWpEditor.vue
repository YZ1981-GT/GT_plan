<!--
  GtCustomWpEditor.vue — 自定义底稿轻量编辑视图（componentType=custom）
  网格只读展示 + 工具栏「公式」→ FormulaEditDialog → PUT /api/workpapers/{wpId}/formulas
-->
<template>
  <div class="gt-custom-wp">
    <div class="gt-custom-wp__toolbar">
      <el-button
        type="primary"
        size="small"
        :disabled="!wpGenerated"
        @click="openFormulaDialog"
      >
        公式
      </el-button>
      <span v-if="!wpGenerated" class="gt-custom-wp__hint">底稿未生成，无法编辑公式</span>
    </div>
    <GtGridSheet
      :wp-id="wpId"
      :sheet-name="sheetName"
      :schema="schema"
      :html-data="htmlData"
      readonly
    />
    <FormulaEditDialog
      v-model="showFormulaDialog"
      :row="formulaDialogRow"
      :project-id="projectId"
      :year="year"
      :wp-context="wpContext"
      @save="onFormulaSave"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'
import GtGridSheet from '@/components/workpaper/GtGridSheet.vue'
import FormulaEditDialog from '@/components/formula/FormulaEditDialog.vue'

export interface WpFormulaContext {
  wpId: string
  wpCode: string
  sheetName: string
  projectId: string
  year: number
  cells: Array<{ cell: string; label: string }>
}

const emit = defineEmits<{
  'formula-saved': []
}>()

const props = defineProps<{
  wpId: string
  sheetName: string
  schema?: Record<string, unknown>
  htmlData?: Record<string, unknown>
  readonly?: boolean
  wpGenerated?: boolean
  projectId?: string
  year?: number
  wpCode?: string
}>()

const showFormulaDialog = ref(false)
const formulaDialogRow = ref<Record<string, string>>({})

const wpContext = computed<WpFormulaContext | undefined>(() => {
  if (!props.projectId) return undefined
  const cells = props.htmlData?.cells as Record<string, unknown> | undefined
  const cellList: Array<{ cell: string; label: string }> = []
  if (cells && typeof cells === 'object') {
    for (const [ref, raw] of Object.entries(cells)) {
      let label = ref
      if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
        const o = raw as Record<string, unknown>
        label = String(o.label ?? o.name ?? o.value ?? ref)
      }
      cellList.push({ cell: ref, label })
    }
  }
  return {
    wpId: props.wpId,
    wpCode: props.wpCode || '',
    sheetName: props.sheetName,
    projectId: props.projectId,
    year: props.year ?? new Date().getFullYear(),
    cells: cellList,
  }
})

function openFormulaDialog() {
  if (!props.wpGenerated) {
    ElMessage.warning('底稿未生成，无法编辑公式')
    return
  }
  formulaDialogRow.value = {
    row_code: `CUSTOM:${props.wpId}:${props.sheetName}`,
    row_name: props.sheetName,
  }
  showFormulaDialog.value = true
}

async function onFormulaSave(payload: {
  formula: string
  category: string
  description: string
  target_cell?: string
}) {
  if (!payload.formula?.trim()) {
    ElMessage.warning('公式表达式不能为空')
    return
  }
  const target = (payload.target_cell || '').trim()
  const cellMatch = target.match(/([A-Z]+\d+)/i)
  const targetCell = cellMatch ? cellMatch[1].toUpperCase() : ''
  if (!targetCell) {
    ElMessage.warning('请先选择目标单元格（如 B5）')
    return
  }
  if (!props.projectId) {
    ElMessage.error('缺少项目上下文，无法保存公式')
    return
  }
  try {
    const res = await api.put(`/api/workpapers/${props.wpId}/formulas`, {
      sheet_name: props.sheetName,
      target_cell: targetCell,
      expression: payload.formula,
      year: props.year ?? new Date().getFullYear(),
      template_type: 'soe',
      category: payload.category,
      description: payload.description,
    }) as { evaluated_value?: string; eval_warnings?: string[] }
    if (res?.eval_warnings?.length) {
      ElMessage.warning(`公式已保存（部分引用求值告警: ${res.eval_warnings.length}）`)
    } else {
      ElMessage.success('公式已保存')
    }
    emit('formula-saved')
  } catch (e) {
    handleApiError(e, '保存公式失败')
  }
}
</script>

<style scoped>
.gt-custom-wp__toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
  padding: 6px 0;
}
.gt-custom-wp__hint {
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
}
:deep(.gt-custom-wp__toolbar .el-button--primary) {
  --el-button-bg-color: var(--gt-color-primary, #4b2d77);
  --el-button-border-color: var(--gt-color-primary, #4b2d77);
}
</style>
