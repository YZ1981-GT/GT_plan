<!--
  GtDFormConfirmation.vue — D 类函证/盘点/访谈子组件（Shell）

  适用范围：~109 sheet（D0/E0/F0/G0/H0/K0/L0 函证 + E1 盘点 + 访谈记录）

  核心交互：
  - confirmation_workflow 4 阶段 stepper
  - 每阶段 fields + formula 自动派生
  - 函证明细动态表格
  - composite 结论
  - debounce 1.5s emit 'save'

  Shell 只做组装：import composable → 实例化 → template 绑定
  Validates: Requirements 5.1
-->

<template>
  <div class="gt-d-form-conf">
    <!-- ─── 顶部头部信息 ─── -->
    <header v-if="hasHeaderInfo" class="gt-dfc__header">
      <div class="gt-dfc__header-meta">
        <span v-if="entityName" class="gt-dfc__entity">{{ entityName }}</span>
        <span v-if="periodEnd" class="gt-dfc__period">{{ periodEnd }}</span>
      </div>
      <div class="gt-dfc__header-right">
        <el-tag v-if="confirmationTypeLabel" size="small" type="primary" effect="plain">{{ confirmationTypeLabel }}</el-tag>
        <span v-if="indexNo" class="gt-dfc__index">索引号：<strong>{{ indexNo }}</strong></span>
      </div>
    </header>

    <!-- ─── 上下文字段区 ─── -->
    <section v-if="contextFields.length" class="gt-dfc__context">
      <el-form :model="contextData" label-position="top" :disabled="readonly" class="gt-dfc__context-form">
        <el-form-item v-for="field in contextFields" :key="field.name" :label="field.label" :required="!!field.required" class="gt-dfc__context-item">
          <component :is="resolveContextInput(field)" v-bind="contextInputProps(field)" v-model="contextData[field.name]" @change="onContextFieldChange(field.name)">
            <template v-if="field.type === 'enum'" #default>
              <el-option v-for="opt in field.enum || []" :key="opt" :label="opt" :value="opt" />
            </template>
          </component>
          <div v-if="field.hint" class="gt-dfc__field-hint"><el-icon><InfoFilled /></el-icon><span>{{ field.hint }}</span></div>
        </el-form-item>
      </el-form>
    </section>

    <!-- ─── 函证工作流 stepper ─── -->
    <section v-if="stages.length" class="gt-dfc__workflow">
      <h3 class="gt-dfc__title">函证工作流</h3>
      <el-steps :active="activeStageIdx" finish-status="success" align-center class="gt-dfc__stepper">
        <el-step v-for="(stage, idx) in stages" :key="stage.id || stage.stage || idx" :title="stage.title || stage.stage" :description="stage.description" :status="stepStatus(idx)" @click="goToStage(idx)" />
      </el-steps>

      <div v-if="currentStage" class="gt-dfc__stage-panel">
        <header class="gt-dfc__stage-header">
          <h4 class="gt-dfc__stage-title">{{ currentStage.title || currentStage.stage }}</h4>
          <p v-if="currentStage.description" class="gt-dfc__stage-desc">{{ currentStage.description }}</p>
        </header>

        <el-form :model="stageData[currentStage.stage] || {}" label-position="top" :disabled="readonly" class="gt-dfc__stage-form">
          <el-form-item v-for="field in (currentStage.fields || [])" :key="field.name" :label="field.label" :required="!!field.required" class="gt-dfc__stage-item">
            <div v-if="field.render === 'index_chip'" class="gt-dfc__chip-cell">
              <el-input v-if="!readonly && !field.readonly" :model-value="stageFieldValue(currentStage.stage, field)" size="small" :type="field.type === 'textarea' ? 'textarea' : 'text'" :rows="field.type === 'textarea' ? 3 : undefined" :maxlength="field.max_length" :placeholder="field.hint || field.label" @update:model-value="(v: any) => setStageField(currentStage!.stage, field, v)" />
              <div v-if="stageFieldValue(currentStage.stage, field)" class="gt-dfc__chip-preview">
                <GtIndexChip v-for="ref in splitRefs(stageFieldValue(currentStage.stage, field))" :key="ref" :value="ref" :validate="true" @click="onIndexChipClick(ref)" />
              </div>
            </div>
            <el-select v-else-if="field.type === 'enum'" :model-value="stageFieldValue(currentStage.stage, field)" :disabled="readonly || !!field.readonly" clearable :placeholder="field.label" @update:model-value="(v: any) => setStageField(currentStage!.stage, field, v)">
              <el-option v-for="opt in field.enum || []" :key="opt" :label="opt" :value="opt" />
            </el-select>
            <el-date-picker v-else-if="field.type === 'date'" :model-value="stageFieldValue(currentStage.stage, field)" :disabled="readonly || !!field.readonly" type="date" :format="field.format || 'YYYY-MM-DD'" :value-format="field.format || 'YYYY-MM-DD'" :placeholder="field.label" class="gt-dfc__date-picker" @update:model-value="(v: any) => setStageField(currentStage!.stage, field, v)" />
            <el-input-number v-else-if="field.type === 'number' || field.type === 'percent'" :model-value="stageFieldValue(currentStage.stage, field)" :disabled="readonly || !!field.readonly" :min="field.min" :max="field.max" :precision="field.render === 'amount' ? 2 : (field.type === 'percent' ? 2 : undefined)" controls-position="right" :class="field.render === 'amount' ? 'gt-amt gt-dfc__amount-input' : ''" @update:model-value="(v: any) => setStageField(currentStage!.stage, field, v)" />
            <el-input v-else-if="field.type === 'textarea'" :model-value="stageFieldValue(currentStage.stage, field)" :disabled="readonly || !!field.readonly" type="textarea" :rows="3" :maxlength="field.max_length" :show-word-limit="!!field.max_length" :placeholder="field.hint || field.label" @update:model-value="(v: any) => setStageField(currentStage!.stage, field, v)" />
            <el-input v-else :model-value="stageFieldValue(currentStage.stage, field)" :disabled="readonly || !!field.readonly" :maxlength="field.max_length" :placeholder="field.hint || field.label" @update:model-value="(v: any) => setStageField(currentStage!.stage, field, v)" />
            <div v-if="field.hint" class="gt-dfc__field-hint"><el-icon><InfoFilled /></el-icon><span>{{ field.hint }}</span></div>
          </el-form-item>
        </el-form>

        <div v-if="(currentStage.actions || []).length" class="gt-dfc__stage-actions">
          <el-button v-for="(action, aIdx) in currentStage.actions || []" :key="action.name || aIdx" type="primary" :icon="DocumentAddIcon" :disabled="readonly" @click="onActionClick(currentStage!.stage, action)">{{ action.label || action.name }}</el-button>
        </div>

        <div class="gt-dfc__stage-nav">
          <el-button :disabled="activeStageIdx === 0" @click="goToStage(activeStageIdx - 1)">上一阶段</el-button>
          <el-button type="primary" :disabled="activeStageIdx >= stages.length - 1" @click="goToStage(activeStageIdx + 1)">下一阶段</el-button>
        </div>
      </div>
    </section>

    <!-- ─── 函证明细动态表格 ─── -->
    <section v-if="dynamicTable" class="gt-dfc__detail">
      <div class="gt-dfc__toolbar">
        <h3 class="gt-dfc__title">函证明细</h3>
        <div v-if="!readonly" class="gt-dfc__toolbar-actions">
          <el-tooltip :content="`已添加 ${tableRows.length} / ${maxRows} 行`" placement="top">
            <el-button size="small" :icon="PlusIcon" :disabled="reachedMaxRows" @click="handleAddRow">新增函证</el-button>
          </el-tooltip>
        </div>
      </div>
      <el-table :data="tableRows" border size="small" class="gt-dfc__table" empty-text="暂无函证记录，点击「新增函证」开始填写">
        <el-table-column v-for="col in tableColumns" :key="col.field" :label="col.label" :min-width="col.width || 120" resizable>
          <template #default="{ row, $index }">
            <div v-if="col.render === 'index_chip'" class="gt-dfc__chip-cell">
              <el-input v-if="!readonly && !col.readonly" v-model="row[col.field]" size="small" :maxlength="col.max_length" :placeholder="col.label" @change="onCellChange(row, col.field, $index)" />
              <div v-if="row[col.field]" class="gt-dfc__chip-preview">
                <GtIndexChip v-for="ref in splitRefs(row[col.field])" :key="ref" :value="ref" :validate="true" @click="onIndexChipClick(ref)" />
              </div>
            </div>
            <div v-else-if="col.render === 'attachment_chip'" class="gt-dfc__attach-cell">
              <el-input v-if="!readonly" v-model="row[col.field]" size="small" :maxlength="col.max_length" placeholder="附件 UUID 或 URL" @change="onCellChange(row, col.field, $index)">
                <template #prefix><el-icon><PaperclipIcon /></el-icon></template>
              </el-input>
              <el-link v-if="row[col.field]" type="primary" :underline="false" class="gt-dfc__attach-link" @click="onAttachmentClick(row[col.field])">
                <el-icon><PaperclipIcon /></el-icon><span>{{ truncateAttachment(row[col.field]) }}</span>
              </el-link>
            </div>
            <el-select v-else-if="col.type === 'enum'" v-model="row[col.field]" :disabled="readonly || !!col.readonly" size="small" clearable :placeholder="col.label" :class="col.render === 'tag' ? `gt-dfc__tag-select is-${tagClass(col, row[col.field])}` : ''" @change="onCellChange(row, col.field, $index)">
              <el-option v-for="opt in col.enum || []" :key="opt" :label="opt" :value="opt" />
            </el-select>
            <el-input-number v-else-if="col.type === 'number'" v-model="row[col.field]" :disabled="readonly || !!col.readonly" :min="col.min" :max="col.max" :precision="col.render === 'amount' ? 2 : undefined" size="small" controls-position="right" :class="col.render === 'amount' ? 'gt-amt gt-dfc__amount-input' : ''" @change="onCellChange(row, col.field, $index)" />
            <el-date-picker v-else-if="col.type === 'date'" v-model="row[col.field]" :disabled="readonly || !!col.readonly" type="date" size="small" :format="col.format || 'YYYY-MM-DD'" :value-format="col.format || 'YYYY-MM-DD'" :placeholder="col.label" class="gt-dfc__date-picker" @change="onCellChange(row, col.field, $index)" />
            <el-input v-else v-model="row[col.field]" :disabled="readonly || !!col.readonly" size="small" :maxlength="col.max_length" :placeholder="col.label" @change="onCellChange(row, col.field, $index)" />
          </template>
        </el-table-column>
        <el-table-column v-if="!readonly" label="操作" width="80" fixed="right">
          <template #default="{ $index }">
            <el-button link type="danger" size="small" @click="handleRemoveRow($index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- ─── composite 结论区 ─── -->
    <section v-if="hasComposite" class="gt-dfc__conclusion">
      <h3 class="gt-dfc__title">函证结论</h3>
      <el-form-item v-if="explanationField" :label="explanationField.label" class="gt-dfc__concl-item">
        <el-input v-model="conclusionData.audit_explanation" type="textarea" :rows="4" :disabled="readonly" :maxlength="explanationField.max_length" :show-word-limit="!!explanationField.max_length" :placeholder="explanationField.hint || explanationField.label" @change="onConclusionFieldChange('audit_explanation')" />
        <div v-if="explanationField.hint" class="gt-dfc__field-hint"><el-icon><InfoFilled /></el-icon><span>{{ explanationField.hint }}</span></div>
      </el-form-item>
      <el-form-item v-if="overallField" :label="overallField.label" :required="!!overallField.required" class="gt-dfc__concl-item">
        <el-radio-group v-model="conclusionData.overall_conclusion" :disabled="readonly" class="gt-dfc__overall-group" @change="onConclusionFieldChange('overall_conclusion')">
          <el-radio v-for="opt in overallOptions" :key="opt.value" :value="opt.value" :class="['gt-dfc__overall-option', `is-${opt.class || 'info'}`]">
            <div class="gt-dfc__overall-label">
              <el-icon v-if="opt.icon && conclusionIcons[opt.icon]" class="gt-dfc__overall-icon"><component :is="conclusionIcons[opt.icon]" /></el-icon>
              <div class="gt-dfc__overall-text">
                <span class="gt-dfc__overall-name">{{ opt.label }}</span>
                <span v-if="opt.description" class="gt-dfc__overall-desc">{{ opt.description }}</span>
              </div>
            </div>
          </el-radio>
        </el-radio-group>
      </el-form-item>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ElInput, ElInputNumber, ElDatePicker, ElSelect } from 'element-plus'
import { InfoFilled, CircleCheck, CircleCheckFilled, WarningFilled, CircleCloseFilled, Plus as PlusIcon, DocumentAdd as DocumentAddIcon, Paperclip as PaperclipIcon } from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import type { DFormSchema, DFormData, FieldChangePayload } from './GtDForm.vue'
import { useConfirmationState, type StageDef, type FieldDef, type ActionDef } from './composables/useConfirmationState'
import { useConfirmationFields, type ColumnDef, type DynamicTableSchema, type CompositeConclusion, type OverallOption, type ConclusionFieldDef, type TableRow } from './composables/useConfirmationFields'

// ─── Props / Emits ───────────────────────────────────────────────────────────

interface ActionEventPayload {
  stage: string
  action: string
  emit_name?: string
  api?: string
  payload?: Record<string, any>
  context: Record<string, any>
}

const props = withDefaults(defineProps<{
  wpId: string
  sheetName: string
  schema: DFormSchema
  htmlData: DFormData
  readonly?: boolean
}>(), { readonly: false })

const emit = defineEmits<{
  'field-change': [payload: FieldChangePayload]
  'jump-to-reference': [refCode: string]
  'save': [data: DFormData]
  'confirmation-action': [payload: ActionEventPayload]
}>()

// ─── Static maps ─────────────────────────────────────────────────────────────

const CONFIRMATION_TYPE_LABELS: Record<string, string> = {
  receivable: '应收函证', payable: '应付函证', bank: '银行函证',
  loan: '借款函证', investment: '投资函证', inventory: '存货函证',
  inspection: '盘点', interview: '访谈记录',
}

const conclusionIcons: Record<string, any> = { CircleCheck, CircleCheckFilled, WarningFilled, CircleCloseFilled }

const TAG_STATUS_MAP: Record<string, string> = {
  '已确认': 'success', '已回函相符': 'success', '需关注': 'warning',
  '已回函不符': 'warning', '待替代': 'warning', '替代程序': 'warning',
  '退回': 'danger', '未回函': 'info',
}

// ─── Schema-derived computeds ────────────────────────────────────────────────

const fixedCells = computed(() => (props.schema as any)?.fixed_cells ?? {})
const entityName = computed(() => fixedCells.value?.A3 || '')
const periodEnd = computed(() => fixedCells.value?.A4 || '')
const indexNo = computed(() => fixedCells.value?.L3 || fixedCells.value?.P3 || fixedCells.value?.O3 || fixedCells.value?.J3 || '')
const hasHeaderInfo = computed(() => !!(entityName.value || periodEnd.value || indexNo.value || confirmationTypeLabel.value))
const confirmationType = computed(() => (props.schema as any)?.confirmation_type || '')
const confirmationTypeLabel = computed(() => CONFIRMATION_TYPE_LABELS[confirmationType.value] || '')
const contextFields = computed<FieldDef[]>(() => { const arr = (props.schema as any)?.fields; return Array.isArray(arr) ? arr : [] })
const stages = computed<StageDef[]>(() => { const wf = (props.schema as any)?.confirmation_workflow; const arr = wf?.stages; return Array.isArray(arr) ? arr : [] })
const dynamicTable = computed<DynamicTableSchema | null>(() => { const dt = (props.schema as any)?.dynamic_table; return dt && typeof dt === 'object' ? dt : null })
const tableColumns = computed<ColumnDef[]>(() => { const cols = dynamicTable.value?.columns ?? {}; return Object.entries(cols).map(([, def]) => def as ColumnDef) })
const maxRows = computed(() => dynamicTable.value?.max_rows ?? 500)
const conclusionBlock = computed<CompositeConclusion | null>(() => { const c = (props.schema as any)?.conclusion; return c && typeof c === 'object' ? c : null })
const hasComposite = computed(() => conclusionBlock.value?.mode === 'composite' && !!(conclusionBlock.value?.audit_explanation_field || conclusionBlock.value?.overall_conclusion_field))
const explanationField = computed(() => conclusionBlock.value?.audit_explanation_field || null)
const overallField = computed(() => conclusionBlock.value?.overall_conclusion_field || null)
const overallOptions = computed<OverallOption[]>(() => { const opts = overallField.value?.enum; return Array.isArray(opts) ? opts : [] })

// ─── Composable: State (must be first — fields depends on activeStageNo) ────

const { activeStageNo, activeStageIdx, currentStage, goToStage, stepStatus } = useConfirmationState({
  stages,
  initialActiveStage: (props.htmlData as any)?.active_stage,
})

// ─── Composable: Fields (depends on activeStageNo from state) ────────────────

const {
  contextData, stageData, tableRows, conclusionData, reachedMaxRows,
  setStageField, stageFieldValue, handleAddRow, handleRemoveRow,
  onCellChange, onContextFieldChange, onConclusionFieldChange, debounceSave,
} = useConfirmationFields({
  schema: () => props.schema,
  htmlData: () => props.htmlData,
  emit: emit as any,
  readonly: () => props.readonly,
  stages,
  activeStageNo,
  contextFields,
  tableColumns,
  maxRows,
})

// ─── Shell-only helpers (template utilities, no business logic) ──────────────

function splitRefs(value: any): string[] {
  if (!value) return []
  const text = String(value).trim()
  if (!text) return []
  return text.split(/[\s,，、;；]+/).map(s => s.trim()).filter(Boolean)
}

function truncateAttachment(value: any): string {
  const s = String(value || '').trim()
  if (!s) return ''
  if (s.length <= 24) return s
  return s.slice(0, 12) + '…' + s.slice(-8)
}

function tagClass(col: ColumnDef, value: any): string {
  if (!value) return 'info'
  return TAG_STATUS_MAP[String(value)] || 'info'
}

function resolveContextInput(field: FieldDef): any {
  switch (field.type) {
    case 'enum': return ElSelect
    case 'date': return ElDatePicker
    case 'number': case 'percent': return ElInputNumber
    default: return ElInput
  }
}

function contextInputProps(field: FieldDef): Record<string, any> {
  const base: Record<string, any> = { disabled: props.readonly || !!field.readonly, placeholder: field.hint || field.label }
  if (field.type === 'textarea') { base.type = 'textarea'; base.rows = 3; base.maxlength = field.max_length; base.showWordLimit = !!field.max_length }
  else if (field.type === 'date') { base.type = 'date'; base.format = field.format || 'YYYY-MM-DD'; base.valueFormat = field.format || 'YYYY-MM-DD' }
  else if (field.type === 'number' || field.type === 'percent') { base.min = field.min; base.max = field.max; base.controlsPosition = 'right' }
  else if (field.type === 'enum') { base.clearable = true }
  else { base.maxlength = field.max_length }
  return base
}

function onActionClick(stageName: string, action: ActionDef) {
  emit('confirmation-action', {
    stage: stageName, action: action.name, emit_name: action.emit, api: action.api, payload: action.payload,
    context: { wp_id: props.wpId, sheet_name: props.sheetName, confirmation_type: confirmationType.value, stage_data: { ...(stageData.value[stageName] || {}) } },
  })
}

function onIndexChipClick(refCode: string) { emit('jump-to-reference', refCode) }

function onAttachmentClick(value: any) {
  const s = String(value || '').trim()
  if (!s) return
  emit('jump-to-reference', s.startsWith('Att:') || s.startsWith('http') ? s : `Att:${s}`)
}
</script>

<style scoped>
.gt-d-form-conf { display: flex; flex-direction: column; gap: 16px; padding: 16px; }
.gt-dfc__header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; padding: 10px 14px; background: var(--gt-color-bg-soft, #f5f7fa); border-radius: 6px; font-size: 13px; }
.gt-dfc__header-meta { display: flex; align-items: center; gap: 16px; }
.gt-dfc__header-right { display: flex; align-items: center; gap: 10px; }
.gt-dfc__entity { font-weight: 600; color: var(--el-text-color-primary); }
.gt-dfc__period { color: var(--el-text-color-regular); }
.gt-dfc__index { font-size: 12px; color: var(--el-text-color-secondary); }
.gt-dfc__index strong { color: var(--el-color-primary); margin-left: 4px; }
.gt-dfc__title { margin: 0 0 8px 0; font-size: 15px; font-weight: 600; color: var(--el-text-color-primary); }
.gt-dfc__context { border: 1px solid var(--el-border-color-light); border-radius: 6px; padding: 12px 16px; background: var(--gt-color-bg-white, #fff); }
.gt-dfc__context-form { display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 12px 16px; }
.gt-dfc__context-item { margin-bottom: 0; }
.gt-dfc__workflow { border: 1px solid var(--el-border-color-light); border-radius: 6px; padding: 16px; background: var(--gt-color-bg-white, #fff); }
.gt-dfc__stepper { margin-bottom: 16px; cursor: pointer; }
.gt-dfc__stepper :deep(.el-step__head) { cursor: pointer; }
.gt-dfc__stepper :deep(.el-step__title) { cursor: pointer; font-size: 13px; }
.gt-dfc__stage-panel { padding: 12px; border-radius: 4px; background: var(--el-color-primary-light-9); }
.gt-dfc__stage-header { margin-bottom: 12px; }
.gt-dfc__stage-title { margin: 0 0 4px 0; font-size: 14px; font-weight: 600; color: var(--el-color-primary); }
.gt-dfc__stage-desc { margin: 0; font-size: 12px; color: var(--el-text-color-secondary); }
.gt-dfc__stage-form { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px 16px; }
.gt-dfc__stage-item { margin-bottom: 0; }
.gt-dfc__stage-actions { display: flex; gap: 8px; margin-top: 12px; padding: 12px; background: var(--el-color-warning-light-9); border-radius: 4px; }
.gt-dfc__stage-nav { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; padding-top: 12px; border-top: 1px dashed var(--el-border-color-lighter); }
.gt-dfc__detail { border: 1px solid var(--el-border-color-light); border-radius: 6px; padding: 12px 16px; background: var(--gt-color-bg-white, #fff); }
.gt-dfc__toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.gt-dfc__toolbar-actions { display: flex; gap: 8px; }
.gt-dfc__table { width: 100%; }
.gt-dfc__chip-cell { display: flex; flex-direction: column; gap: 4px; }
.gt-dfc__chip-preview { display: flex; flex-wrap: wrap; gap: 4px; }
.gt-dfc__attach-cell { display: flex; flex-direction: column; gap: 4px; }
.gt-dfc__attach-link { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; word-break: break-all; }
.gt-dfc__amount-input :deep(.el-input__inner) { font-family: 'Arial Narrow', Arial, sans-serif; font-variant-numeric: tabular-nums; text-align: right; }
.gt-dfc__date-picker { width: 100%; }
.gt-dfc__tag-select.is-success :deep(.el-select__selected-item) { color: var(--el-color-success); font-weight: 500; }
.gt-dfc__tag-select.is-warning :deep(.el-select__selected-item) { color: var(--el-color-warning); font-weight: 500; }
.gt-dfc__tag-select.is-danger :deep(.el-select__selected-item) { color: var(--el-color-danger); font-weight: 500; }
.gt-dfc__tag-select.is-info :deep(.el-select__selected-item) { color: var(--el-text-color-secondary); }
.gt-dfc__field-hint { display: flex; align-items: center; gap: 4px; margin-top: 4px; font-size: 12px; color: var(--el-text-color-secondary); }
.gt-dfc__field-hint .el-icon { color: var(--el-color-info); }
.gt-dfc__conclusion { display: flex; flex-direction: column; gap: 12px; padding: 16px; border: 1px solid var(--el-border-color-light); border-radius: 6px; background: var(--el-color-primary-light-9); }
.gt-dfc__concl-item { margin-bottom: 0; }
.gt-dfc__overall-group { display: flex; flex-direction: column; gap: 8px; width: 100%; }
.gt-dfc__overall-group :deep(.el-radio) { height: auto; padding: 10px 12px; margin-right: 0; align-items: flex-start; border: 1px solid transparent; border-radius: 4px; transition: background 0.15s, border-color 0.15s; }
.gt-dfc__overall-group :deep(.el-radio:hover) { background: var(--el-color-primary-light-8); }
.gt-dfc__overall-group :deep(.el-radio.is-checked) { background: var(--el-color-primary-light-8); border-color: var(--el-color-primary-light-5); }
.gt-dfc__overall-option.is-success :deep(.el-radio.is-checked) { border-color: var(--el-color-success); background: var(--el-color-success-light-8); }
.gt-dfc__overall-option.is-warning :deep(.el-radio.is-checked) { border-color: var(--el-color-warning); background: var(--el-color-warning-light-8); }
.gt-dfc__overall-option.is-danger :deep(.el-radio.is-checked) { border-color: var(--el-color-danger); background: var(--el-color-danger-light-8); }
.gt-dfc__overall-label { display: inline-flex; align-items: flex-start; gap: 8px; font-size: 14px; color: var(--el-text-color-primary); }
.gt-dfc__overall-icon { font-size: 18px; margin-top: 1px; }
.gt-dfc__overall-text { display: flex; flex-direction: column; gap: 2px; }
.gt-dfc__overall-name { font-weight: 500; }
.gt-dfc__overall-desc { font-size: 12px; color: var(--el-text-color-secondary); }
.gt-dfc__overall-option.is-success .gt-dfc__overall-icon { color: var(--el-color-success); }
.gt-dfc__overall-option.is-warning .gt-dfc__overall-icon { color: var(--el-color-warning); }
.gt-dfc__overall-option.is-danger .gt-dfc__overall-icon { color: var(--el-color-danger); }
.gt-dfc__overall-option.is-info .gt-dfc__overall-icon { color: var(--el-color-info); }
</style>
