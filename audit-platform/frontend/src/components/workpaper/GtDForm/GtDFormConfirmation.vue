<!--
  GtDFormConfirmation.vue — D 类函证/盘点/访谈子组件（实现版）

  适用范围：~109 sheet（D0/E0/F0/G0/H0/K0/L0 函证 + E1 盘点 + 访谈记录）
  样本 schema：D-D0-N0.yaml（函证统计与生成）

  核心交互：
  - confirmation_workflow 4 阶段（generation / dispatch / reply / discrepancy）
    用 el-steps 横向 stepper，点击切换激活阶段
  - 每个阶段一组 fields：text / textarea / number / date / enum / percent
    + render hints（amount / index_chip / tag）
    + readonly + formula 自动派生（safe evaluator，仅 4 则运算 + 字段引用）
  - generation 阶段 actions[] → 渲染按钮，emit 'confirmation-action'
    （payload: { action, api, payload }）
  - 函证明细动态表格（max_rows=500）：12 列 含 attachment_chip 渲染
  - composite 结论（audit_explanation textarea + overall_conclusion radio + 4 options）
  - debounce 1.5s emit 'save'
  - 字段变更 emit 'field-change' 带 stage 前缀（如 workflow.dispatch.dispatch_method）
  - 索引/调整分录 chip 点击 emit 'jump-to-reference'

  锚定 spec workpaper-html-renderer Task 8.6
  Validates: Requirements 3.5（D 子模式 4）

  cross-ref:updated 订阅由 `useWpRenderer.ts` 集中处理（Task 13.2），本组件不直接订阅。
-->

<template>
  <div class="gt-d-form-conf">
    <!-- ─── 顶部头部信息（只读展示） ─── -->
    <header v-if="hasHeaderInfo" class="gt-dfc__header">
      <div class="gt-dfc__header-meta">
        <span v-if="entityName" class="gt-dfc__entity">{{ entityName }}</span>
        <span v-if="periodEnd" class="gt-dfc__period">{{ periodEnd }}</span>
      </div>
      <div class="gt-dfc__header-right">
        <el-tag
          v-if="confirmationTypeLabel"
          size="small"
          type="primary"
          effect="plain"
        >{{ confirmationTypeLabel }}</el-tag>
        <span v-if="indexNo" class="gt-dfc__index">
          索引号：<strong>{{ indexNo }}</strong>
        </span>
      </div>
    </header>

    <!-- ─── 上下文字段区（schema.fields） ─── -->
    <section v-if="contextFields.length" class="gt-dfc__context">
      <el-form
        :model="contextData"
        label-position="top"
        :disabled="readonly"
        class="gt-dfc__context-form"
      >
        <el-form-item
          v-for="field in contextFields"
          :key="field.name"
          :label="field.label"
          :required="!!field.required"
          class="gt-dfc__context-item"
        >
          <component
            :is="resolveContextInput(field)"
            v-bind="contextInputProps(field)"
            v-model="contextData[field.name]"
            @change="onContextFieldChange(field.name)"
          >
            <template v-if="field.type === 'enum'" #default>
              <el-option
                v-for="opt in field.enum || []"
                :key="opt"
                :label="opt"
                :value="opt"
              />
            </template>
          </component>
          <div v-if="field.hint" class="gt-dfc__field-hint">
            <el-icon><InfoFilled /></el-icon>
            <span>{{ field.hint }}</span>
          </div>
        </el-form-item>
      </el-form>
    </section>

    <!-- ─── 函证工作流（4 阶段 stepper） ─── -->
    <section v-if="stages.length" class="gt-dfc__workflow">
      <h3 class="gt-dfc__title">函证工作流</h3>
      <el-steps
        :active="activeStageIdx"
        finish-status="success"
        align-center
        class="gt-dfc__stepper"
      >
        <el-step
          v-for="(stage, idx) in stages"
          :key="stage.id || stage.stage || idx"
          :title="stage.title || stage.stage"
          :description="stage.description"
          :status="stepStatus(idx)"
          @click="goToStage(idx)"
        />
      </el-steps>

      <!-- 当前阶段内容 -->
      <div v-if="currentStage" class="gt-dfc__stage-panel">
        <header class="gt-dfc__stage-header">
          <h4 class="gt-dfc__stage-title">{{ currentStage.title || currentStage.stage }}</h4>
          <p
            v-if="currentStage.description"
            class="gt-dfc__stage-desc"
          >{{ currentStage.description }}</p>
        </header>

        <!-- 阶段字段 -->
        <el-form
          :model="stageData[currentStage.stage] || {}"
          label-position="top"
          :disabled="readonly"
          class="gt-dfc__stage-form"
        >
          <el-form-item
            v-for="field in (currentStage.fields || [])"
            :key="field.name"
            :label="field.label"
            :required="!!field.required"
            class="gt-dfc__stage-item"
          >
            <!-- index_chip render（如 tracking_no_link / adjustment_proposal） -->
            <div
              v-if="field.render === 'index_chip'"
              class="gt-dfc__chip-cell"
            >
              <el-input
                v-if="!readonly && !field.readonly"
                :model-value="stageFieldValue(currentStage.stage, field)"
                size="small"
                :type="field.type === 'textarea' ? 'textarea' : 'text'"
                :rows="field.type === 'textarea' ? 3 : undefined"
                :maxlength="field.max_length"
                :placeholder="field.hint || field.label"
                @update:model-value="(v: any) => setStageField(currentStage!.stage, field, v)"
              />
              <div
                v-if="stageFieldValue(currentStage.stage, field)"
                class="gt-dfc__chip-preview"
              >
                <GtIndexChip
                  v-for="ref in splitRefs(stageFieldValue(currentStage.stage, field))"
                  :key="ref"
                  :value="ref"
                  :validate="true"
                  @click="onIndexChipClick(ref)"
                />
              </div>
            </div>

            <!-- enum -->
            <el-select
              v-else-if="field.type === 'enum'"
              :model-value="stageFieldValue(currentStage.stage, field)"
              :disabled="readonly || !!field.readonly"
              clearable
              :placeholder="field.label"
              @update:model-value="(v: any) => setStageField(currentStage!.stage, field, v)"
            >
              <el-option
                v-for="opt in field.enum || []"
                :key="opt"
                :label="opt"
                :value="opt"
              />
            </el-select>

            <!-- date -->
            <el-date-picker
              v-else-if="field.type === 'date'"
              :model-value="stageFieldValue(currentStage.stage, field)"
              :disabled="readonly || !!field.readonly"
              type="date"
              :format="field.format || 'YYYY-MM-DD'"
              :value-format="field.format || 'YYYY-MM-DD'"
              :placeholder="field.label"
              class="gt-dfc__date-picker"
              @update:model-value="(v: any) => setStageField(currentStage!.stage, field, v)"
            />

            <!-- number / amount / percent -->
            <el-input-number
              v-else-if="field.type === 'number' || field.type === 'percent'"
              :model-value="stageFieldValue(currentStage.stage, field)"
              :disabled="readonly || !!field.readonly"
              :min="field.min"
              :max="field.max"
              :precision="field.render === 'amount' ? 2 : (field.type === 'percent' ? 2 : undefined)"
              controls-position="right"
              :class="field.render === 'amount' ? 'gt-amt gt-dfc__amount-input' : ''"
              @update:model-value="(v: any) => setStageField(currentStage!.stage, field, v)"
            />

            <!-- textarea -->
            <el-input
              v-else-if="field.type === 'textarea'"
              :model-value="stageFieldValue(currentStage.stage, field)"
              :disabled="readonly || !!field.readonly"
              type="textarea"
              :rows="3"
              :maxlength="field.max_length"
              :show-word-limit="!!field.max_length"
              :placeholder="field.hint || field.label"
              @update:model-value="(v: any) => setStageField(currentStage!.stage, field, v)"
            />

            <!-- text 默认 -->
            <el-input
              v-else
              :model-value="stageFieldValue(currentStage.stage, field)"
              :disabled="readonly || !!field.readonly"
              :maxlength="field.max_length"
              :placeholder="field.hint || field.label"
              @update:model-value="(v: any) => setStageField(currentStage!.stage, field, v)"
            />

            <div v-if="field.hint" class="gt-dfc__field-hint">
              <el-icon><InfoFilled /></el-icon>
              <span>{{ field.hint }}</span>
            </div>
          </el-form-item>
        </el-form>

        <!-- 阶段操作按钮（仅 generation 阶段有 actions） -->
        <div
          v-if="(currentStage.actions || []).length"
          class="gt-dfc__stage-actions"
        >
          <el-button
            v-for="(action, aIdx) in currentStage.actions || []"
            :key="action.name || aIdx"
            type="primary"
            :icon="DocumentAddIcon"
            :disabled="readonly"
            @click="onActionClick(currentStage!.stage, action)"
          >{{ action.label || action.name }}</el-button>
        </div>

        <!-- 阶段导航 -->
        <div class="gt-dfc__stage-nav">
          <el-button
            :disabled="activeStageIdx === 0"
            @click="goToStage(activeStageIdx - 1)"
          >上一阶段</el-button>
          <el-button
            type="primary"
            :disabled="activeStageIdx >= stages.length - 1"
            @click="goToStage(activeStageIdx + 1)"
          >下一阶段</el-button>
        </div>
      </div>
    </section>

    <!-- ─── 函证明细动态表格 ─── -->
    <section v-if="dynamicTable" class="gt-dfc__detail">
      <div class="gt-dfc__toolbar">
        <h3 class="gt-dfc__title">函证明细</h3>
        <div v-if="!readonly" class="gt-dfc__toolbar-actions">
          <el-tooltip
            :content="`已添加 ${tableRows.length} / ${maxRows} 行`"
            placement="top"
          >
            <el-button
              size="small"
              :icon="PlusIcon"
              :disabled="reachedMaxRows"
              @click="handleAddRow"
            >新增函证</el-button>
          </el-tooltip>
        </div>
      </div>

      <el-table
        :data="tableRows"
        border
        size="small"
        class="gt-dfc__table"
        empty-text="暂无函证记录，点击「新增函证」开始填写"
      >
        <el-table-column
          v-for="col in tableColumns"
          :key="col.field"
          :label="col.label"
          :min-width="col.width || 120"
          resizable
        >
          <template #default="{ row, $index }">
            <!-- index_chip：调整分录引用（J 列） -->
            <div v-if="col.render === 'index_chip'" class="gt-dfc__chip-cell">
              <el-input
                v-if="!readonly && !col.readonly"
                v-model="row[col.field]"
                size="small"
                :maxlength="col.max_length"
                :placeholder="col.label"
                @change="onCellChange(row, col.field, $index)"
              />
              <div v-if="row[col.field]" class="gt-dfc__chip-preview">
                <GtIndexChip
                  v-for="ref in splitRefs(row[col.field])"
                  :key="ref"
                  :value="ref"
                  :validate="true"
                  @click="onIndexChipClick(ref)"
                />
              </div>
            </div>

            <!-- attachment_chip：回函扫描件（K 列） -->
            <div v-else-if="col.render === 'attachment_chip'" class="gt-dfc__attach-cell">
              <el-input
                v-if="!readonly"
                v-model="row[col.field]"
                size="small"
                :maxlength="col.max_length"
                placeholder="附件 UUID 或 URL"
                @change="onCellChange(row, col.field, $index)"
              >
                <template #prefix>
                  <el-icon><PaperclipIcon /></el-icon>
                </template>
              </el-input>
              <el-link
                v-if="row[col.field]"
                type="primary"
                :underline="false"
                class="gt-dfc__attach-link"
                @click="onAttachmentClick(row[col.field])"
              >
                <el-icon><PaperclipIcon /></el-icon>
                <span>{{ truncateAttachment(row[col.field]) }}</span>
              </el-link>
            </div>

            <!-- enum 单选（含 tag 渲染） -->
            <el-select
              v-else-if="col.type === 'enum'"
              v-model="row[col.field]"
              :disabled="readonly || !!col.readonly"
              size="small"
              clearable
              :placeholder="col.label"
              :class="col.render === 'tag' ? `gt-dfc__tag-select is-${tagClass(col, row[col.field])}` : ''"
              @change="onCellChange(row, col.field, $index)"
            >
              <el-option
                v-for="opt in col.enum || []"
                :key="opt"
                :label="opt"
                :value="opt"
              />
            </el-select>

            <!-- number / amount -->
            <el-input-number
              v-else-if="col.type === 'number'"
              v-model="row[col.field]"
              :disabled="readonly || !!col.readonly"
              :min="col.min"
              :max="col.max"
              :precision="col.render === 'amount' ? 2 : undefined"
              size="small"
              controls-position="right"
              :class="col.render === 'amount' ? 'gt-amt gt-dfc__amount-input' : ''"
              @change="onCellChange(row, col.field, $index)"
            />

            <!-- date -->
            <el-date-picker
              v-else-if="col.type === 'date'"
              v-model="row[col.field]"
              :disabled="readonly || !!col.readonly"
              type="date"
              size="small"
              :format="col.format || 'YYYY-MM-DD'"
              :value-format="col.format || 'YYYY-MM-DD'"
              :placeholder="col.label"
              class="gt-dfc__date-picker"
              @change="onCellChange(row, col.field, $index)"
            />

            <!-- text 默认 -->
            <el-input
              v-else
              v-model="row[col.field]"
              :disabled="readonly || !!col.readonly"
              size="small"
              :maxlength="col.max_length"
              :placeholder="col.label"
              @change="onCellChange(row, col.field, $index)"
            />
          </template>
        </el-table-column>

        <!-- 操作列 -->
        <el-table-column
          v-if="!readonly"
          label="操作"
          width="80"
          fixed="right"
        >
          <template #default="{ $index }">
            <el-button
              link
              type="danger"
              size="small"
              @click="handleRemoveRow($index)"
            >删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- ─── composite 结论区（审计说明 + 整体结论） ─── -->
    <section v-if="hasComposite" class="gt-dfc__conclusion">
      <h3 class="gt-dfc__title">函证结论</h3>

      <el-form-item
        v-if="explanationField"
        :label="explanationField.label"
        class="gt-dfc__concl-item"
      >
        <el-input
          v-model="conclusionData.audit_explanation"
          type="textarea"
          :rows="4"
          :disabled="readonly"
          :maxlength="explanationField.max_length"
          :show-word-limit="!!explanationField.max_length"
          :placeholder="explanationField.hint || explanationField.label"
          @change="onConclusionFieldChange('audit_explanation')"
        />
        <div v-if="explanationField.hint" class="gt-dfc__field-hint">
          <el-icon><InfoFilled /></el-icon>
          <span>{{ explanationField.hint }}</span>
        </div>
      </el-form-item>

      <el-form-item
        v-if="overallField"
        :label="overallField.label"
        :required="!!overallField.required"
        class="gt-dfc__concl-item"
      >
        <el-radio-group
          v-model="conclusionData.overall_conclusion"
          :disabled="readonly"
          class="gt-dfc__overall-group"
          @change="onConclusionFieldChange('overall_conclusion')"
        >
          <el-radio
            v-for="opt in overallOptions"
            :key="opt.value"
            :value="opt.value"
            :class="['gt-dfc__overall-option', `is-${opt.class || 'info'}`]"
          >
            <div class="gt-dfc__overall-label">
              <el-icon
                v-if="opt.icon && conclusionIcons[opt.icon]"
                class="gt-dfc__overall-icon"
              >
                <component :is="conclusionIcons[opt.icon]" />
              </el-icon>
              <div class="gt-dfc__overall-text">
                <span class="gt-dfc__overall-name">{{ opt.label }}</span>
                <span
                  v-if="opt.description"
                  class="gt-dfc__overall-desc"
                >{{ opt.description }}</span>
              </div>
            </div>
          </el-radio>
        </el-radio-group>
      </el-form-item>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import {
  ElInput,
  ElInputNumber,
  ElDatePicker,
  ElSelect,
} from 'element-plus'
import {
  InfoFilled,
  CircleCheck,
  CircleCheckFilled,
  WarningFilled,
  CircleCloseFilled,
  Plus as PlusIcon,
  DocumentAdd as DocumentAddIcon,
  Paperclip as PaperclipIcon,
} from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import type { DFormSchema, DFormData, FieldChangePayload } from './GtDForm.vue'

// ─── Types ───────────────────────────────────────────────────────────────────

type FieldType = 'text' | 'textarea' | 'number' | 'percent' | 'date' | 'enum'
type RenderHint = 'amount' | 'tag' | 'index_chip' | 'attachment_chip' | string

interface FieldDef {
  name: string
  label: string
  type?: FieldType
  cell?: string
  enum?: string[]
  render?: RenderHint
  readonly?: boolean
  required?: boolean
  hint?: string
  max_length?: number
  min?: number
  max?: number
  format?: string
  formula?: string
  source?: string
  default?: any
  default_from?: string
}

interface ActionDef {
  name: string
  label: string
  emit?: string
  api?: string
  payload?: Record<string, any>
}

interface StageDef {
  stage: string                            // 'generation' / 'dispatch' / 'reply' / 'discrepancy'
  id?: string
  title?: string
  description?: string
  start_row?: number
  end_row?: number | string
  fields?: FieldDef[]
  actions?: ActionDef[]
}

interface ColumnDef {
  field: string
  label: string
  type?: FieldType
  enum?: string[]
  render?: RenderHint
  readonly?: boolean
  width?: number
  min?: number
  max?: number
  max_length?: number
  format?: string
  formula?: string
}

interface DynamicTableSchema {
  start_row?: number
  end_row?: number | string
  header_row?: number
  add_row_button?: boolean
  max_rows?: number
  columns?: Record<string, ColumnDef>
}

interface OverallOption {
  value: string
  label: string
  class?: 'success' | 'warning' | 'danger' | 'info'
  icon?: string
  description?: string
}

interface ConclusionFieldDef {
  name: string
  label: string
  type?: string
  cell_after_table?: number
  max_length?: number
  required?: boolean
  hint?: string
  enum?: OverallOption[]
}

interface CompositeConclusion {
  mode?: 'composite' | string
  audit_explanation_field?: ConclusionFieldDef
  overall_conclusion_field?: ConclusionFieldDef
}

type TableRow = Record<string, any> & { _row_id?: string }

interface ConfirmationData extends DFormData {
  context?: Record<string, any>
  workflow?: Record<string, Record<string, any>>      // stage → fields map
  active_stage?: string
  rows?: TableRow[]
  conclusion?: {
    audit_explanation?: string
    overall_conclusion?: string
  }
}

interface ActionEventPayload {
  stage: string
  action: string
  emit_name?: string
  api?: string
  payload?: Record<string, any>
  context: Record<string, any>
}

// ─── Confirmation type label map ─────────────────────────────────────────────

const CONFIRMATION_TYPE_LABELS: Record<string, string> = {
  receivable: '应收函证',
  payable: '应付函证',
  bank: '银行函证',
  loan: '借款函证',
  investment: '投资函证',
  inventory: '存货函证',
  inspection: '盘点',
  interview: '访谈记录',
}

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = withDefaults(defineProps<{
  wpId: string
  sheetName: string
  schema: DFormSchema
  htmlData: DFormData
  readonly?: boolean
}>(), {
  readonly: false,
})

const emit = defineEmits<{
  'field-change': [payload: FieldChangePayload]
  'jump-to-reference': [refCode: string]
  'save': [data: DFormData]
  'confirmation-action': [payload: ActionEventPayload]
}>()

// ─── Refs（按 setup const 顺序铁律放最前） ────────────────────────────────────

const contextData = ref<Record<string, any>>({})
const stageData = ref<Record<string, Record<string, any>>>({})
const activeStageNo = ref<string>('')
const tableRows = ref<TableRow[]>([])
const conclusionData = ref<{
  audit_explanation: string
  overall_conclusion: string
}>({
  audit_explanation: '',
  overall_conclusion: '',
})

let saveTimer: ReturnType<typeof setTimeout> | null = null

// ─── Static maps ─────────────────────────────────────────────────────────────

const conclusionIcons: Record<string, any> = {
  CircleCheck,
  CircleCheckFilled,
  WarningFilled,
  CircleCloseFilled,
}

// 状态 → tag class（receipt status / row_conclusion 列）
const TAG_STATUS_MAP: Record<string, string> = {
  '已确认': 'success',
  '已回函相符': 'success',
  '需关注': 'warning',
  '已回函不符': 'warning',
  '待替代': 'warning',
  '替代程序': 'warning',
  '退回': 'danger',
  '未回函': 'info',
}

// ─── Computed ────────────────────────────────────────────────────────────────

const fixedCells = computed(() => (props.schema as any)?.fixed_cells ?? {})

const entityName = computed(() => fixedCells.value?.A3 || '')
const periodEnd = computed(() => fixedCells.value?.A4 || '')
const indexNo = computed(
  () => fixedCells.value?.L3 || fixedCells.value?.P3 || fixedCells.value?.O3 || fixedCells.value?.J3 || ''
)
const hasHeaderInfo = computed(
  () => !!(entityName.value || periodEnd.value || indexNo.value || confirmationTypeLabel.value)
)

const confirmationType = computed(
  () => (props.schema as any)?.confirmation_type || ''
)
const confirmationTypeLabel = computed(
  () => CONFIRMATION_TYPE_LABELS[confirmationType.value] || ''
)

const contextFields = computed<FieldDef[]>(() => {
  const arr = (props.schema as any)?.fields
  return Array.isArray(arr) ? (arr as FieldDef[]) : []
})

const stages = computed<StageDef[]>(() => {
  const wf = (props.schema as any)?.confirmation_workflow
  const arr = wf?.stages
  return Array.isArray(arr) ? (arr as StageDef[]) : []
})

const activeStageIdx = computed(() => {
  if (!stages.value.length) return 0
  const idx = stages.value.findIndex(s => s.stage === activeStageNo.value)
  return idx >= 0 ? idx : 0
})

const currentStage = computed<StageDef | null>(
  () => stages.value[activeStageIdx.value] ?? null
)

const dynamicTable = computed<DynamicTableSchema | null>(() => {
  const dt = (props.schema as any)?.dynamic_table
  return dt && typeof dt === 'object' ? dt : null
})

const tableColumns = computed<ColumnDef[]>(() => {
  const cols = dynamicTable.value?.columns ?? {}
  return Object.entries(cols).map(([_cell, def]) => def as ColumnDef)
})

const maxRows = computed(() => dynamicTable.value?.max_rows ?? 500)

const reachedMaxRows = computed(() => tableRows.value.length >= maxRows.value)

const conclusionBlock = computed<CompositeConclusion | null>(() => {
  const c = (props.schema as any)?.conclusion
  return c && typeof c === 'object' ? c : null
})

const hasComposite = computed(
  () =>
    conclusionBlock.value?.mode === 'composite' &&
    !!(
      conclusionBlock.value?.audit_explanation_field ||
      conclusionBlock.value?.overall_conclusion_field
    )
)

const explanationField = computed(
  () => conclusionBlock.value?.audit_explanation_field || null
)
const overallField = computed(
  () => conclusionBlock.value?.overall_conclusion_field || null
)

const overallOptions = computed<OverallOption[]>(() => {
  const opts = overallField.value?.enum
  return Array.isArray(opts) ? (opts as OverallOption[]) : []
})

// ─── Helpers ─────────────────────────────────────────────────────────────────

function genRowId(): string {
  return `cw-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function buildEmptyRow(): TableRow {
  const row: TableRow = { _row_id: genRowId() }
  for (const col of tableColumns.value) {
    if (col.type === 'number') row[col.field] = null
    else row[col.field] = ''
  }
  // 自动填充序号
  const seqCol = tableColumns.value.find(c => c.field === 'seq')
  if (seqCol) {
    row.seq = tableRows.value.length + 1
  }
  return row
}

function splitRefs(value: any): string[] {
  if (!value) return []
  const text = String(value).trim()
  if (!text) return []
  return text
    .split(/[\s,，、;；]+/)
    .map(s => s.trim())
    .filter(Boolean)
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
    case 'number':
    case 'percent': return ElInputNumber
    case 'textarea':
    case 'text':
    default:
      return ElInput
  }
}

function contextInputProps(field: FieldDef): Record<string, any> {
  const base: Record<string, any> = {
    disabled: props.readonly || !!field.readonly,
    placeholder: field.hint || field.label,
  }
  if (field.type === 'textarea') {
    base.type = 'textarea'
    base.rows = 3
    base.maxlength = field.max_length
    base.showWordLimit = !!field.max_length
  } else if (field.type === 'date') {
    base.type = 'date'
    base.format = field.format || 'YYYY-MM-DD'
    base.valueFormat = field.format || 'YYYY-MM-DD'
  } else if (field.type === 'number' || field.type === 'percent') {
    base.min = field.min
    base.max = field.max
    base.controlsPosition = 'right'
  } else if (field.type === 'enum') {
    base.clearable = true
  } else {
    base.maxlength = field.max_length
  }
  return base
}

// ─── Formula evaluation ──────────────────────────────────────────────────────

/**
 * Safe formula evaluator — supports four basic ops + field references + numeric literals.
 * 例如：'sample_amount / total_amount * 100' / 'dispatch_count - reply_count'
 */
function evalFormula(formula: string, ctx: Record<string, any>): number | null {
  if (!formula || typeof formula !== 'string') return null
  // 仅允许字段名（[a-zA-Z_][a-zA-Z0-9_]*） + 数字 + 运算符 + 空格 + 括号
  if (!/^[\w\s.+\-*/()0-9]+$/.test(formula)) return null

  // 替换字段引用为数值
  const replaced = formula.replace(/[a-zA-Z_][a-zA-Z0-9_]*/g, (name) => {
    const v = ctx[name]
    const n = Number(v)
    if (!Number.isFinite(n)) return '0'
    return String(n)
  })
  try {
    // eslint-disable-next-line no-new-func
    const result = new Function(`"use strict"; return (${replaced});`)()
    if (typeof result === 'number' && Number.isFinite(result)) return result
    return null
  } catch {
    return null
  }
}

function applyFormulasForStage(stageName: string) {
  const stage = stages.value.find(s => s.stage === stageName)
  if (!stage) return
  const stageBucket = stageData.value[stageName] || {}
  for (const f of stage.fields || []) {
    if (f.readonly && f.formula) {
      const v = evalFormula(f.formula, stageBucket)
      if (v !== null) stageBucket[f.name] = v
    }
  }
  stageData.value[stageName] = { ...stageBucket }
}

// ─── Stage field accessors ──────────────────────────────────────────────────

function stageFieldValue(stageName: string, field: FieldDef): any {
  const bucket = stageData.value[stageName]
  return bucket ? bucket[field.name] : undefined
}

function setStageField(stageName: string, field: FieldDef, value: any) {
  if (!stageData.value[stageName]) stageData.value[stageName] = {}
  const oldValue = stageData.value[stageName][field.name]
  stageData.value[stageName][field.name] = value
  // 触发该阶段所有 readonly+formula 字段重算
  applyFormulasForStage(stageName)
  emit('field-change', {
    field_name: `workflow.${stageName}.${field.name}`,
    old_value: oldValue,
    new_value: value,
    cell: field.cell,
  })
  debounceSave()
}

// ─── Stage navigation ───────────────────────────────────────────────────────

function goToStage(idx: number) {
  if (idx < 0 || idx >= stages.value.length) return
  const target = stages.value[idx]
  if (target) {
    activeStageNo.value = target.stage
  }
}

function stepStatus(idx: number): 'wait' | 'process' | 'finish' | 'success' | 'error' {
  if (idx < activeStageIdx.value) return 'finish'
  if (idx === activeStageIdx.value) return 'process'
  return 'wait'
}

// ─── Context field handlers ─────────────────────────────────────────────────

function onContextFieldChange(name: string) {
  emit('field-change', {
    field_name: `context.${name}`,
    old_value: undefined,
    new_value: contextData.value[name],
  })
  debounceSave()
}

// ─── Action button handler ──────────────────────────────────────────────────

function onActionClick(stageName: string, action: ActionDef) {
  const payload: ActionEventPayload = {
    stage: stageName,
    action: action.name,
    emit_name: action.emit,
    api: action.api,
    payload: action.payload,
    context: {
      wp_id: props.wpId,
      sheet_name: props.sheetName,
      confirmation_type: confirmationType.value,
      stage_data: { ...(stageData.value[stageName] || {}) },
    },
  }
  emit('confirmation-action', payload)
}

// ─── Table row handlers ─────────────────────────────────────────────────────

function handleAddRow() {
  if (reachedMaxRows.value) return
  tableRows.value.push(buildEmptyRow())
  debounceSave()
}

function handleRemoveRow(idx: number) {
  tableRows.value.splice(idx, 1)
  // 重排序号
  const hasSeq = tableColumns.value.some(c => c.field === 'seq')
  if (hasSeq) {
    tableRows.value.forEach((r, i) => {
      r.seq = i + 1
    })
  }
  debounceSave()
}

function onCellChange(row: TableRow, fieldName: string, idx: number) {
  // 处理动态表格 formula 列（如 H 列 discrepancy = account_balance - reply_amount）
  for (const col of tableColumns.value) {
    if (col.readonly && col.formula) {
      const v = evalFormula(col.formula, row)
      if (v !== null) row[col.field] = v
    }
  }
  emit('field-change', {
    field_name: `rows[${idx}].${fieldName}`,
    old_value: undefined,
    new_value: row[fieldName],
  })
  debounceSave()
}

function onIndexChipClick(refCode: string) {
  emit('jump-to-reference', refCode)
}

function onAttachmentClick(value: any) {
  // 附件 chip 点击 → emit jump-to-reference 让上层路由（'Att:<uuid>' 或直接 URL）
  const s = String(value || '').trim()
  if (!s) return
  const refCode = s.startsWith('Att:') || s.startsWith('http') ? s : `Att:${s}`
  emit('jump-to-reference', refCode)
}

// ─── Conclusion handlers ────────────────────────────────────────────────────

function onConclusionFieldChange(name: 'audit_explanation' | 'overall_conclusion') {
  emit('field-change', {
    field_name: `conclusion.${name}`,
    old_value: undefined,
    new_value: conclusionData.value[name],
  })
  debounceSave()
}

// ─── Init / Sync ────────────────────────────────────────────────────────────

function initData() {
  const data = (props.htmlData ?? {}) as ConfirmationData

  // 上下文字段
  const ctxIn = data.context && typeof data.context === 'object' ? data.context : {}
  const ctxOut: Record<string, any> = {}
  for (const f of contextFields.value) {
    const fallback = (f as any).default ?? ''
    ctxOut[f.name] = (ctxIn as Record<string, any>)[f.name] ?? fallback
  }
  contextData.value = ctxOut

  // 工作流阶段数据
  const wfIn = data.workflow && typeof data.workflow === 'object' ? data.workflow : {}
  const wfOut: Record<string, Record<string, any>> = {}
  for (const stage of stages.value) {
    const bucketIn = (wfIn as Record<string, Record<string, any>>)[stage.stage] || {}
    const bucketOut: Record<string, any> = {}
    for (const f of stage.fields || []) {
      bucketOut[f.name] = bucketIn[f.name] ?? (f.default ?? (f.type === 'number' || f.type === 'percent' ? null : ''))
    }
    wfOut[stage.stage] = bucketOut
  }
  stageData.value = wfOut

  // 应用所有阶段的 readonly+formula 字段
  for (const stage of stages.value) {
    applyFormulasForStage(stage.stage)
  }

  // 激活阶段
  if (typeof data.active_stage === 'string' && stages.value.some(s => s.stage === data.active_stage)) {
    activeStageNo.value = data.active_stage
  } else {
    activeStageNo.value = stages.value[0]?.stage ?? ''
  }

  // 表格行
  const rowsIn = Array.isArray(data.rows) ? data.rows : []
  tableRows.value = rowsIn.map((r): TableRow => {
    const cleaned: TableRow = { _row_id: r._row_id || genRowId() }
    for (const col of tableColumns.value) {
      if (Object.prototype.hasOwnProperty.call(r, col.field)) {
        cleaned[col.field] = r[col.field]
      } else if (col.type === 'number') {
        cleaned[col.field] = null
      } else {
        cleaned[col.field] = ''
      }
    }
    return cleaned
  })

  // 结论
  const c = data.conclusion && typeof data.conclusion === 'object' ? data.conclusion : {}
  conclusionData.value = {
    audit_explanation: typeof c.audit_explanation === 'string' ? c.audit_explanation : '',
    overall_conclusion: typeof c.overall_conclusion === 'string' ? c.overall_conclusion : '',
  }
}

initData()

watch(
  () => props.htmlData,
  () => {
    initData()
  },
  { deep: true }
)

watch(
  () => props.schema,
  () => {
    initData()
  },
  { deep: true }
)

// ─── Save payload + debounce ─────────────────────────────────────────────────

function buildSavePayload(): ConfirmationData {
  const payload: ConfirmationData = {
    ...(props.htmlData || {}),
    context: { ...contextData.value },
    workflow: JSON.parse(JSON.stringify(stageData.value)),
    active_stage: activeStageNo.value,
    rows: tableRows.value.map(r => {
      const out: TableRow = {}
      if (r._row_id) out._row_id = r._row_id
      for (const col of tableColumns.value) {
        out[col.field] = r[col.field]
      }
      return out
    }),
    conclusion: { ...conclusionData.value },
  }
  return payload
}

function debounceSave() {
  if (props.readonly) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    emit('save', buildSavePayload())
  }, 1500)
}

// ─── Cleanup ────────────────────────────────────────────────────────────────

onBeforeUnmount(() => {
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
})
</script>

<style scoped>
.gt-d-form-conf {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px;
}

/* ── Header ── */
.gt-dfc__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  padding: 10px 14px;
  background: var(--gt-color-bg-soft, #f5f7fa);
  border-radius: 6px;
  font-size: 13px;
}
.gt-dfc__header-meta {
  display: flex;
  align-items: center;
  gap: 16px;
}
.gt-dfc__header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.gt-dfc__entity {
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.gt-dfc__period {
  color: var(--el-text-color-regular);
}
.gt-dfc__index {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.gt-dfc__index strong {
  color: var(--el-color-primary);
  margin-left: 4px;
}

/* ── Common ── */
.gt-dfc__title {
  margin: 0 0 8px 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

/* ── Context ── */
.gt-dfc__context {
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  padding: 12px 16px;
  background: var(--gt-color-bg-white, #fff);
}
.gt-dfc__context-form {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
  gap: 12px 16px;
}
.gt-dfc__context-item {
  margin-bottom: 0;
}

/* ── Workflow stepper ── */
.gt-dfc__workflow {
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  padding: 16px;
  background: var(--gt-color-bg-white, #fff);
}
.gt-dfc__stepper {
  margin-bottom: 16px;
  cursor: pointer;
}
.gt-dfc__stepper :deep(.el-step__head) {
  cursor: pointer;
}
.gt-dfc__stepper :deep(.el-step__title) {
  cursor: pointer;
  font-size: 13px;
}
.gt-dfc__stage-panel {
  padding: 12px;
  border-radius: 4px;
  background: var(--el-color-primary-light-9);
}
.gt-dfc__stage-header {
  margin-bottom: 12px;
}
.gt-dfc__stage-title {
  margin: 0 0 4px 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-color-primary);
}
.gt-dfc__stage-desc {
  margin: 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.gt-dfc__stage-form {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px 16px;
}
.gt-dfc__stage-item {
  margin-bottom: 0;
}
.gt-dfc__stage-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  padding: 12px;
  background: var(--el-color-warning-light-9);
  border-radius: 4px;
}
.gt-dfc__stage-nav {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px dashed var(--el-border-color-lighter);
}

/* ── Detail table ── */
.gt-dfc__detail {
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  padding: 12px 16px;
  background: var(--gt-color-bg-white, #fff);
}
.gt-dfc__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.gt-dfc__toolbar-actions {
  display: flex;
  gap: 8px;
}
.gt-dfc__table {
  width: 100%;
}
.gt-dfc__chip-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.gt-dfc__chip-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.gt-dfc__attach-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.gt-dfc__attach-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  word-break: break-all;
}
.gt-dfc__amount-input :deep(.el-input__inner) {
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  text-align: right;
}
.gt-dfc__date-picker {
  width: 100%;
}
.gt-dfc__tag-select.is-success :deep(.el-select__selected-item) {
  color: var(--el-color-success);
  font-weight: 500;
}
.gt-dfc__tag-select.is-warning :deep(.el-select__selected-item) {
  color: var(--el-color-warning);
  font-weight: 500;
}
.gt-dfc__tag-select.is-danger :deep(.el-select__selected-item) {
  color: var(--el-color-danger);
  font-weight: 500;
}
.gt-dfc__tag-select.is-info :deep(.el-select__selected-item) {
  color: var(--el-text-color-secondary);
}

/* ── Field hint ── */
.gt-dfc__field-hint {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.gt-dfc__field-hint .el-icon {
  color: var(--el-color-info);
}

/* ── Conclusion ── */
.gt-dfc__conclusion {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  background: var(--el-color-primary-light-9);
}
.gt-dfc__concl-item {
  margin-bottom: 0;
}
.gt-dfc__overall-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}
.gt-dfc__overall-group :deep(.el-radio) {
  height: auto;
  padding: 10px 12px;
  margin-right: 0;
  align-items: flex-start;
  border: 1px solid transparent;
  border-radius: 4px;
  transition: background 0.15s, border-color 0.15s;
}
.gt-dfc__overall-group :deep(.el-radio:hover) {
  background: var(--el-color-primary-light-8);
}
.gt-dfc__overall-group :deep(.el-radio.is-checked) {
  background: var(--el-color-primary-light-8);
  border-color: var(--el-color-primary-light-5);
}
.gt-dfc__overall-option.is-success :deep(.el-radio.is-checked) {
  border-color: var(--el-color-success);
  background: var(--el-color-success-light-8);
}
.gt-dfc__overall-option.is-warning :deep(.el-radio.is-checked) {
  border-color: var(--el-color-warning);
  background: var(--el-color-warning-light-8);
}
.gt-dfc__overall-option.is-danger :deep(.el-radio.is-checked) {
  border-color: var(--el-color-danger);
  background: var(--el-color-danger-light-8);
}
.gt-dfc__overall-label {
  display: inline-flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 14px;
  color: var(--el-text-color-primary);
}
.gt-dfc__overall-icon {
  font-size: 18px;
  margin-top: 1px;
}
.gt-dfc__overall-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.gt-dfc__overall-name {
  font-weight: 500;
}
.gt-dfc__overall-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.gt-dfc__overall-option.is-success .gt-dfc__overall-icon {
  color: var(--el-color-success);
}
.gt-dfc__overall-option.is-warning .gt-dfc__overall-icon {
  color: var(--el-color-warning);
}
.gt-dfc__overall-option.is-danger .gt-dfc__overall-icon {
  color: var(--el-color-danger);
}
.gt-dfc__overall-option.is-info .gt-dfc__overall-icon {
  color: var(--el-color-info);
}
</style>
