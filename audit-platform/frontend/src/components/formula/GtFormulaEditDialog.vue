<template>
  <el-dialog
    v-model="visible"
    :title="dialogTitle"
    width="720px"
    top="6vh"
    append-to-body
    destroy-on-close
    :close-on-click-modal="false"
    class="gt-formula-edit-dialog"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="formRules"
      label-width="88px"
      label-position="right"
      size="default"
    >
      <!-- 公式来源选择器（三来源：预设 / 自定义 / 参照，Req 25.1） -->
      <el-form-item label="公式来源" prop="formula_source">
        <el-radio-group v-model="form.formula_source" class="gt-fe-source-group">
          <el-radio-button value="preset">📦 预设</el-radio-button>
          <el-radio-button value="custom">✏️ 自定义</el-radio-button>
          <el-radio-button value="reference">🔗 参照已有</el-radio-button>
        </el-radio-group>
        <div class="gt-fe-type-hint">{{ sourceHint }}</div>
      </el-form-item>

      <!-- reference 来源：选参照源公式，复用其表达式（Req 25.5） -->
      <el-form-item v-if="form.formula_source === 'reference'" label="参照公式">
        <el-select
          v-model="form.reference_formula_id"
          class="gt-fe-ref-select"
          placeholder="选择一条已保存公式作为参照来源"
          filterable
          clearable
          :loading="sourceApi.candidatesLoading.value"
          @change="onSelectReference"
        >
          <el-option
            v-for="c in sourceApi.candidates.value"
            :key="c.id"
            :value="c.id"
            :label="`${c.sheet_name ? c.sheet_name + '!' : ''}${c.target_cell} — ${c.expression}`"
          />
        </el-select>
      </el-form-item>

      <!-- custom 来源覆盖预设：提供「恢复预设」按钮（Req 25.4，复用 restore 端点，不重写） -->
      <el-form-item v-if="showRestorePreset" label="预设覆盖">
        <el-button
          size="small"
          :loading="sourceApi.restoring.value"
          @click="onRestorePreset"
        >↩️ 恢复预设公式</el-button>
        <span class="gt-fe-type-hint">删除该单元的自定义覆盖，回退到系统预设公式。</span>
      </el-form-item>

      <!-- 公式类型选择器（三类型统一入口） -->
      <el-form-item label="公式类型" prop="formula_type">
        <el-radio-group v-model="form.formula_type">
          <el-radio-button value="auto_calc">⚡ 自动运算</el-radio-button>
          <el-radio-button value="logic_check">🔍 逻辑判断</el-radio-button>
          <el-radio-button value="reasonability">💡 合理性提示</el-radio-button>
        </el-radio-group>
        <div class="gt-fe-type-hint">{{ typeHint }}</div>
      </el-form-item>

      <!-- ── auto_calc：目标单元 + 表达式 ── -->
      <template v-if="form.formula_type === 'auto_calc'">
        <el-form-item label="目标单元">
          <el-input
            v-model="form.target_cell"
            placeholder="回填结果的目标地址（如 BS-027·期末 / E1-1 审定数）"
            clearable
          />
        </el-form-item>
        <el-form-item label="计算表达式" prop="expression">
          <div class="gt-fe-expr-wrap">
            <el-input
              v-model="form.expression"
              type="textarea"
              :autosize="{ minRows: 3, maxRows: 8 }"
              placeholder="如 TB('1001','期末余额') 或 ROW('BS-001')+ROW('BS-002')"
              resize="none"
              :input-style="monoInputStyle"
            />
            <el-button size="small" class="gt-fe-pick-btn" @click="openRefPicker">🎯 插入引用</el-button>
          </div>
        </el-form-item>
      </template>

      <!-- ── logic_check：条件 + 问题描述 ── -->
      <template v-else-if="form.formula_type === 'logic_check'">
        <el-form-item label="承载单元">
          <el-input
            v-model="form.target_cell"
            placeholder="校验挂载的单元（可选，如 BS-053·勾稽）"
            clearable
          />
        </el-form-item>
        <el-form-item label="判断条件" prop="expression">
          <div class="gt-fe-expr-wrap">
            <el-input
              v-model="form.expression"
              type="textarea"
              :autosize="{ minRows: 3, maxRows: 8 }"
              placeholder="如 ROW('BS-053') = ROW('BS-129')（条件成立视为通过）"
              resize="none"
              :input-style="monoInputStyle"
            />
            <el-button size="small" class="gt-fe-pick-btn" @click="openRefPicker">🎯 插入引用</el-button>
          </div>
        </el-form-item>
        <el-form-item label="问题描述" prop="issue_description">
          <el-input
            v-model="form.issue_description"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
            placeholder="条件不通过时追加到问题清单的描述（如：资产总计应等于负债和所有者权益总计）"
          />
        </el-form-item>
      </template>

      <!-- ── reasonability：触发条件 + 提示文案 ── -->
      <template v-else>
        <el-form-item label="承载单元">
          <el-input
            v-model="form.target_cell"
            placeholder="提示挂载的单元（可选，如 BS-002·货币资金）"
            clearable
          />
        </el-form-item>
        <el-form-item label="触发条件" prop="expression">
          <div class="gt-fe-expr-wrap">
            <el-input
              v-model="form.expression"
              type="textarea"
              :autosize="{ minRows: 3, maxRows: 8 }"
              placeholder="如 CHANGE_RATE('BS-002') > 0.5（条件成立时给出提示）"
              resize="none"
              :input-style="monoInputStyle"
            />
            <el-button size="small" class="gt-fe-pick-btn" @click="openRefPicker">🎯 插入引用</el-button>
          </div>
        </el-form-item>
        <el-form-item label="提示文案" prop="hint_text">
          <el-input
            v-model="form.hint_text"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
            placeholder="触发时追加到提醒清单的文案（如：货币资金变动超 50%，请核实是否合理）"
          />
        </el-form-item>
      </template>

      <!-- 已引用地址（经 ACNR 校验，禁止裸字符串） -->
      <el-form-item v-if="refs.length" label="引用地址">
        <div class="gt-fe-refs">
          <el-tag
            v-for="(r, i) in refs"
            :key="i"
            size="small"
            type="info"
            closable
            @close="removeRef(i)"
          >{{ r }}</el-tag>
        </div>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="validating" @click="onSubmit">保存公式</el-button>
    </template>

    <!-- 引用地址选择器：接 acnr-consumer-wiring Req 14 的 ACNR 选址器（消费候选地址，不自建） -->
    <FormulaRefPicker
      v-model="showRefPicker"
      :report-rows="refPickerData.reportRows"
      :tb-rows="refPickerData.tbRows"
      :note-rows="refPickerData.noteRows"
      @insert="onInsertRef"
    />
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, reactive, watch } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { useAcnr } from '@/services/acnr/useAcnr'
import FormulaRefPicker from './FormulaRefPicker.vue'
import { useFormulaSource, type FormulaSource } from './useFormulaSource'

export type FormulaType = 'auto_calc' | 'logic_check' | 'reasonability'
export type { FormulaSource } from './useFormulaSource'

/** 三类型公式编辑载荷（与 design.md FormulaRecord 逻辑模型对齐）。 */
export interface FormulaEditPayload {
  formula_type: FormulaType
  target_cell: string
  expression: string
  /** logic_check 不通过时的问题描述 */
  issue_description?: string
  /** reasonability 触发时的提示文案 */
  hint_text?: string
  /** 规范化引用（formula_ref / addr_id），禁裸字符串（Req 11.5） */
  refs: string[]
  /** 公式来源：预设 / 自定义 / 参照已有（Req 25.1/25.6） */
  formula_source: FormulaSource
  /** reference 来源时携带的被参照源公式 id（Req 25.5） */
  reference_formula_id?: string | null
}

/** 弹窗作用域，统一用于底稿 / 报表 / 附注三处（Req 8.5）。 */
export type FormulaDialogScope = 'workpaper' | 'report' | 'note'

const props = withDefaults(defineProps<{
  modelValue: boolean
  /** 编辑现有公式时传入初始值；新建时留空 */
  initial?: Partial<FormulaEditPayload> | null
  /** 弹窗所属页面：底稿 / 报表 / 附注 */
  scope?: FormulaDialogScope
  /** 供 ACNR 选址器懒加载引用数据（可选，选址器优先用 addressRegistry store） */
  reportRows?: any[]
  tbRows?: any[]
  noteRows?: any[]
  /** 底稿 id：reference 候选懒加载 + custom 恢复预设（Req 25.4/25.5） */
  wpId?: string
  /**
   * custom 恢复预设所需的 cell_key（`{sheet_name}!{cell_ref}`）；
   * 提供且当前公式为预设覆盖时展示「恢复预设」按钮（Req 25.4）。
   */
  cellKey?: string
  /** 当前公式是否为预设覆盖（is_preset_override），决定是否可恢复预设 */
  isPresetOverride?: boolean
}>(), {
  initial: null,
  scope: 'workpaper',
  reportRows: () => [],
  tbRows: () => [],
  noteRows: () => [],
  wpId: '',
  cellKey: '',
  isPresetOverride: false,
})

const emit = defineEmits<{
  'update:modelValue': [val: boolean]
  'save': [payload: FormulaEditPayload]
  /** 恢复预设成功后通知父级刷新（Req 25.4） */
  'restore-preset': [cellKey: string]
}>()

const acnr = useAcnr()
const sourceApi = useFormulaSource()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const SCOPE_LABEL: Record<FormulaDialogScope, string> = {
  workpaper: '底稿',
  report: '报表',
  note: '附注',
}

const dialogTitle = computed(() => `编辑公式 — ${SCOPE_LABEL[props.scope]}`)

const TYPE_HINTS: Record<FormulaType, string> = {
  auto_calc: '求值后将结果回填到目标单元。',
  logic_check: '条件不通过时产出问题清单，绝不修改任何数据值。',
  reasonability: '触发条件成立时产出提醒，绝不修改任何数据值。',
}
const typeHint = computed(() => TYPE_HINTS[form.formula_type])

const SOURCE_HINTS: Record<FormulaSource, string> = {
  preset: '来自系统预设库的标准公式（一键套用）。',
  custom: '自定义编辑的公式；若覆盖了预设可恢复。',
  reference: '参照另一条已保存公式，复用其表达式（源公式变更时同步失效）。',
}
const sourceHint = computed(() => SOURCE_HINTS[form.formula_source])

/** custom 来源 + 提供 cell_key + 属预设覆盖时，展示「恢复预设」按钮（Req 25.4）。 */
const showRestorePreset = computed(
  () =>
    form.formula_source === 'custom' &&
    !!props.wpId &&
    !!props.cellKey &&
    props.isPresetOverride,
)

const monoInputStyle = {
  fontSize: '12px',
  fontFamily: 'Cascadia Code, Fira Code, Consolas, monospace',
  lineHeight: '1.5',
}

// ── 表单状态 ──
function emptyForm(): FormulaEditPayload {
  return {
    formula_type: 'auto_calc',
    target_cell: '',
    expression: '',
    issue_description: '',
    hint_text: '',
    refs: [],
    formula_source: 'custom',
    reference_formula_id: null,
  }
}

const form = reactive<FormulaEditPayload>(emptyForm())
const refs = ref<string[]>([])
const validating = ref(false)
const formRef = ref<FormInstance>()

// 按公式类型动态校验：表达式恒为必填；问题描述/提示文案按类型必填
const formRules = computed<FormRules>(() => ({
  expression: [{ required: true, message: '请填写公式表达式', trigger: 'blur' }],
  issue_description: form.formula_type === 'logic_check'
    ? [{ required: true, message: '请填写问题描述', trigger: 'blur' }]
    : [],
  hint_text: form.formula_type === 'reasonability'
    ? [{ required: true, message: '请填写提示文案', trigger: 'blur' }]
    : [],
}))

// 打开时用 initial 初始化，关闭复位；formula_source 回显（Req 25.6）
watch(visible, (v) => {
  if (v) {
    const src = props.initial || {}
    Object.assign(form, emptyForm(), {
      formula_type: (src.formula_type as FormulaType) || 'auto_calc',
      target_cell: src.target_cell || '',
      expression: src.expression || '',
      issue_description: src.issue_description || '',
      hint_text: src.hint_text || '',
      formula_source: (src.formula_source as FormulaSource) || 'custom',
      reference_formula_id: src.reference_formula_id ?? null,
    })
    refs.value = Array.isArray(src.refs) ? [...src.refs] : []
    // reference 来源：懒加载候选源公式供选择/回显
    if (form.formula_source === 'reference' && props.wpId) {
      void sourceApi.loadReferenceCandidates(props.wpId)
    }
  }
})

// 切到 reference 来源时按需加载候选源公式
watch(
  () => form.formula_source,
  (s) => {
    if (s === 'reference' && props.wpId && !sourceApi.candidates.value.length) {
      void sourceApi.loadReferenceCandidates(props.wpId)
    }
  },
)

/** 选中参照源公式：复用其表达式（reference 解析后端已落地，前端仅复用+携带 id）。 */
function onSelectReference(id: string | null) {
  form.reference_formula_id = id || null
  if (!id) return
  const picked = sourceApi.candidates.value.find((c) => c.id === id)
  if (picked) {
    form.expression = picked.expression
    if (picked.formula_type) form.formula_type = picked.formula_type as FormulaType
  }
}

/** 恢复预设：调 restore 端点删除自定义覆盖（Req 25.4，不重写端点）。 */
async function onRestorePreset() {
  if (!props.wpId || !props.cellKey) return
  const ok = await sourceApi.restorePreset(props.wpId, props.cellKey)
  if (ok) {
    ElMessage.success('已恢复预设公式')
    emit('restore-preset', props.cellKey)
    visible.value = false
  } else {
    ElMessage.error('恢复预设失败')
  }
}

// ── ACNR 选址器 ──
const showRefPicker = ref(false)
const refPickerData = computed(() => ({
  reportRows: props.reportRows,
  tbRows: props.tbRows,
  noteRows: props.noteRows,
}))

function openRefPicker() {
  showRefPicker.value = true
}

/** 选址器插入引用：拼接到表达式并登记到 refs（去重）。 */
function onInsertRef(formulaRef: string) {
  if (!formulaRef) return
  const cur = form.expression || ''
  form.expression = cur ? `${cur}${cur.trimEnd().endsWith('(') ? '' : ' '}${formulaRef}` : formulaRef
  if (!refs.value.includes(formulaRef)) refs.value.push(formulaRef)
}

function removeRef(i: number) {
  refs.value.splice(i, 1)
}

// ── 从表达式提取 grammar 引用（覆盖手动输入的引用） ──
const REF_FN = 'WP|TB|ROW|SUM_ROW|SUM_TB|NOTE|REPORT|AUX|PREV'
const REF_RE = new RegExp(`\\b(?:${REF_FN})\\([^)]*\\)`, 'g')

function collectRefs(): string[] {
  const found = new Set<string>()
  for (const r of refs.value) if (r) found.add(r)
  const matches = (form.expression || '').match(REF_RE)
  if (matches) for (const m of matches) found.add(m.trim())
  return [...found]
}

// ── 提交：先经 ACNR full_resolve 校验，悬空则提示且不保存（Req 8.4） ──
async function onSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  const allRefs = collectRefs()
  validating.value = true
  try {
    const dangling: string[] = []
    for (const r of allRefs) {
      const res = await acnr.resolveFormula(r)
      if (!res.found) dangling.push(r)
    }
    if (dangling.length) {
      ElMessage.error(`存在悬空引用，无法保存：${dangling.join('、')}`)
      return
    }
  } finally {
    validating.value = false
  }

  const payload: FormulaEditPayload = {
    formula_type: form.formula_type,
    target_cell: form.target_cell.trim(),
    expression: form.expression.trim(),
    refs: allRefs,
    formula_source: form.formula_source,
    reference_formula_id:
      form.formula_source === 'reference' ? form.reference_formula_id ?? null : null,
  }
  if (form.formula_type === 'logic_check') payload.issue_description = form.issue_description?.trim()
  if (form.formula_type === 'reasonability') payload.hint_text = form.hint_text?.trim()

  emit('save', payload)
  visible.value = false
}
</script>

<style scoped>
.gt-formula-edit-dialog :deep(.el-dialog__body) {
  padding-top: 12px;
}
.gt-fe-type-hint {
  margin-left: 12px;
  font-size: var(--gt-font-size-xs, 12px);
  color: var(--gt-color-text-tertiary, #909399);
}
.gt-fe-expr-wrap {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
}
.gt-fe-pick-btn {
  align-self: flex-start;
}
.gt-fe-refs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.gt-fe-source-group {
  flex-wrap: wrap;
}
.gt-fe-ref-select {
  width: 100%;
}
</style>
