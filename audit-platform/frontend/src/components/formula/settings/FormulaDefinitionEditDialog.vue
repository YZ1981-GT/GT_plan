<!--
  编辑一个公式位的定义（全局设置页、模板详情共用；spec formula-global-settings-sync）。
  执行字段（参与冲突判定）与说明字段（跟随，不判冲突）分组显示；字段由公式域清单给出。
  只在内存里暂存，提交由调用方在「预览并发布 / 发布新版本」时统一做。
-->
<template>
  <el-dialog v-model="visible" :title="title" width="620px" append-to-body destroy-on-close
    data-testid="formula-definition-edit">
    <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
      <div class="gt-fde-group">执行字段（改动会与已适配的项目比对）</div>
      <el-form-item v-for="f in execFields" :key="f" :label="label(f)" :prop="f">
        <!-- 枚举字段给中文选项（原样显示 auto_calc 之类的取值，界面不可读） -->
        <el-select v-if="optionsOf(f)" v-model="form[f]" clearable style="width: 100%" :data-testid="`fde-select-${f}`">
          <el-option v-for="o in optionsOf(f)" :key="o.value" :value="o.value" :label="o.label" />
        </el-select>
        <el-input v-else v-model="form[f]" :type="isLong(f) ? 'textarea' : 'text'" :rows="2" :placeholder="placeholder(f)" />
      </el-form-item>
      <template v-if="descFields.length">
        <div class="gt-fde-group">说明字段（跟随更新，不产生冲突）</div>
        <el-form-item v-for="f in descFields" :key="f" :label="label(f)">
          <el-input v-model="form[f]" />
        </el-form-item>
      </template>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" data-testid="fde-ok" @click="onOk">暂存修改</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { FIELD_LABELS, type Definition } from '@/composables/formula/useFormulaSettings'

defineOptions({ name: 'FormulaDefinitionEditDialog' })

const props = withDefaults(defineProps<{
  modelValue: boolean
  title?: string
  execFields: string[]
  descFields?: string[]
  definition: Definition | null
}>(), { title: '编辑公式', descFields: () => [] })

const emit = defineEmits<{ 'update:modelValue': [value: boolean]; save: [definition: Definition] }>()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const formRef = ref<FormInstance>()
const form = reactive<Record<string, string>>({})
/** 主公式字段必填（报表 / 附注为 formula，底稿为 expression，表间审核为左右取数） */
const REQUIRED = new Set(['formula', 'expression', 'left_ref', 'right_ref'])
const rules = computed<FormRules>(() => Object.fromEntries(props.execFields.filter((f) => REQUIRED.has(f))
  .slice(0, 1).map((f) => [f, [{ required: true, message: `请填写${label(f)}`, trigger: 'blur' }]])))

watch(() => props.modelValue, (open) => {
  if (!open) return
  for (const k of Object.keys(form)) delete form[k]
  for (const f of [...props.execFields, ...props.descFields]) {
    const v = props.definition?.[f]
    form[f] = v == null ? '' : String(v)
  }
}, { immediate: true })

function label(f: string): string {
  return FIELD_LABELS[f] || f
}

type Option = { value: string; label: string }
/** 与公式管理中心分类页签同口径 */
const CATEGORY_OPTIONS: Option[] = [
  { value: 'auto_calc', label: '自动运算' }, { value: 'logic_check', label: '逻辑审核' },
  { value: 'reasonability', label: '提示合理性' },
]
/** 与后端 cross_check_rules.OPERATORS 同口径（不认识的值按「=」执行） */
const OPERATOR_OPTIONS: Option[] = [
  { value: '=', label: '等于（=）' }, { value: '<=', label: '小于等于（<=）' }, { value: '>=', label: '大于等于（>=）' },
]
function optionsOf(f: string): Option[] | null {
  const base = f === 'formula_category' || f === 'formula_type' ? CATEGORY_OPTIONS : f === 'operator' ? OPERATOR_OPTIONS : null
  if (!base) return null
  const cur = form[f]
  // 现有值不在清单里（旧数据）时保留为一项，避免打开再保存时被静默清空
  return cur && !base.some((o) => o.value === cur) ? [...base, { value: cur, label: cur }] : base
}
function isLong(f: string): boolean {
  return ['formula', 'aje_formula', 'rje_formula', 'expression', 'left_ref', 'right_ref'].includes(f)
}
function placeholder(f: string): string {
  if (f === 'formula') return "如 TB('1001','期末余额') 或 ROW('BS-002')"
  if (f === 'operator') return '= / <= / >='
  if (f === 'tolerance') return '默认 0.01'
  return ''
}

async function onOk() {
  if (!(await formRef.value?.validate().catch(() => false))) return
  const out: Definition = { ...(props.definition || {}) }
  for (const f of [...props.execFields, ...props.descFields]) {
    const v = (form[f] ?? '').trim()
    if (f === 'tolerance') out[f] = v === '' ? null : (Number.isFinite(Number(v)) ? Number(v) : v)
    else out[f] = v === '' ? null : v
  }
  emit('save', out)
  visible.value = false
}
</script>

<style scoped>
.gt-fde-group { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin: 4px 0 8px; }
</style>
