<template>
  <!--
    调整 / 抵销分录表单（spec consol-elimination-single-source-push 任务 9.2 / 需求 1.3）
    差额节点面板与「合并抵消分录明细表」共用：多行借贷、借贷平衡校验、科目下拉带方向、归属差额节点。
    - 面板：归属固定为所点的差额节点（lock-target，只显示不下拉）；
    - 明细表：从本项目承载的差额节点里选（targets = tree-lines 的 hosted_nodes），只有一个时默认选中。
    保存成功 ⇒ 关闭并 emit('saved')，由父组件刷新列表；失败原因由 http 拦截器统一提示。
  -->
  <el-dialog :model-value="modelValue" :title="entry ? '修改分录' : '新增分录'" width="720px" append-to-body
    data-testid="elim-form" @update:model-value="(v: boolean) => emit('update:modelValue', v)">
    <el-form ref="formRef" :model="form" :rules="formRules" label-width="84px" size="small">
      <el-form-item label="归属节点" prop="target_key">
        <span v-if="lockTarget" data-testid="elim-form-target">{{ selectedTarget?.label || '' }}</span>
        <template v-else>
          <el-select v-model="form.target_key" style="width:320px" placeholder="选择归属的差额节点"
            data-testid="elim-form-target-select">
            <el-option v-for="t in targets" :key="t.node_key" :label="t.label" :value="t.node_key" />
          </el-select>
          <span class="elim-form-tip">只列出由本合并项目承载的差额节点</span>
        </template>
      </el-form-item>
      <el-form-item label="分录类型" prop="entry_type">
        <el-select v-model="form.entry_type" style="width:220px" data-testid="elim-form-type">
          <el-option v-for="opt in TYPE_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
        </el-select>
        <span class="elim-form-tip">「其他调整」计入调整列，其余类型计入抵销列</span>
      </el-form-item>
      <el-form-item label="说明" prop="description">
        <el-input v-model="form.description" maxlength="500" placeholder="如：抵销母公司与分公司内部往来" />
      </el-form-item>
    </el-form>
    <!-- 列宽合计需小于弹窗内容宽，否则删除列被挤出可视区 -->
    <el-table :data="form.lines" border size="small" data-testid="elim-form-lines">
      <el-table-column label="科目" min-width="200">
        <template #default="{ row }">
          <el-select v-model="row.account_code" filterable allow-create default-first-option size="small"
            style="width:100%" placeholder="选择或输入科目编码" @change="(v: string) => onAccountPicked(row, v)">
            <el-option v-for="a in accounts" :key="a.account_code"
              :label="`${a.account_code} ${a.account_name || ''}（${a.direction === 'credit' ? '贷' : '借'}）`"
              :value="a.account_code" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="科目名称" min-width="120">
        <template #default="{ row }"><el-input v-model="row.account_name" size="small" /></template>
      </el-table-column>
      <el-table-column label="借方" width="120">
        <template #default="{ row }"><el-input v-model="row.debit_amount" size="small" placeholder="0.00" /></template>
      </el-table-column>
      <el-table-column label="贷方" width="120">
        <template #default="{ row }"><el-input v-model="row.credit_amount" size="small" placeholder="0.00" /></template>
      </el-table-column>
      <el-table-column label="" width="56" align="center">
        <template #default="{ $index }">
          <el-button size="small" link type="danger" :disabled="form.lines.length <= 2"
            @click="form.lines.splice($index, 1)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div class="elim-form-footer">
      <el-button size="small" @click="addLine">+ 添加明细行</el-button>
      <span class="elim-form-totals" :class="{ 'elim-form-totals--bad': !!formError }" data-testid="elim-form-totals">
        借方合计 {{ fmtAmount(totals.debit, 2, true) }} ｜ 贷方合计 {{ fmtAmount(totals.credit, 2, true) }}
        <template v-if="formError">｜{{ formError }}</template>
      </span>
    </div>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="saving" :disabled="!!formError" data-testid="elim-form-save"
        @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { rules } from '@/utils/formRules'
import {
  createElimination,
  updateElimination,
  type ConsolAccountOption,
  type EliminationEntry,
  type EliminationType,
} from '@/services/consolidationApi'
import { fmtAmount } from '@/utils/formatters'
import {
  buildEntryPayload,
  emptyLine,
  findTarget,
  linesToForm,
  TYPE_OPTIONS,
  validateLines,
  type ElimTarget,
  type FormLine,
} from '@/components/consolidation/composables/elimNodePanel'

defineOptions({ name: 'ConsolElimEntryForm' })

const props = withDefaults(defineProps<{
  modelValue: boolean
  projectId: string
  year: number | null
  /** 可选的归属差额节点（明细表 = hosted_nodes；面板 = 所点节点一个） */
  targets: ReadonlyArray<ElimTarget>
  /** 归属固定为 targets[0]，只显示不下拉（差额节点面板） */
  lockTarget?: boolean
  /** 科目下拉（本树数据叶子试算表科目 ∪ 本树分录明细科目） */
  accounts?: ReadonlyArray<ConsolAccountOption>
  /** 修改的分录；null = 新增 */
  entry?: EliminationEntry | null
  /** 新增时的默认分录类型 */
  defaultType?: EliminationType
}>(), {
  lockTarget: false,
  accounts: () => [],
  entry: null,
  defaultType: 'internal_ar_ap',
})
const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'saved', entry: EliminationEntry | null, mode: 'create' | 'update'): void
}>()

const saving = ref(false)
const form = reactive<{ target_key: string; entry_type: EliminationType; description: string; lines: FormLine[] }>({
  target_key: '',
  entry_type: props.defaultType,
  description: '',
  lines: [emptyLine(), emptyLine()],
})
const formRef = ref<FormInstance>()
// 表头字段规则；明细行（借贷平衡、有金额必有科目）由 validateLines 校验，不通过时保存按钮禁用并显示原因
const formRules: FormRules = {
  target_key: [rules.required('归属节点', 'change')],
  entry_type: [rules.required('分录类型', 'change')],
  description: [{ max: 500, message: '说明不超过 500 个字', trigger: 'blur' }],
}

const selectedTarget = computed<ElimTarget | null>(
  () => props.targets.find((t) => t.node_key === form.target_key) || null,
)
const check = computed(() => validateLines(form.lines))
const formError = computed(() => {
  if (!selectedTarget.value) return props.targets.length ? '请选择归属节点' : '本合并项目没有可录入的差额节点'
  return check.value.error
})
const totals = computed(() => ({ debit: check.value.debit.toString(), credit: check.value.credit.toString() }))

/** 打开时按「新增 / 修改」重置表单：修改回填原分录（归属按 branch_entity_code 找回选项） */
function reset() {
  const entry = props.entry
  const fallback = props.lockTarget || props.targets.length === 1 ? props.targets[0] : null
  if (entry) {
    form.target_key = (props.lockTarget ? fallback : findTarget(props.targets, entry.branch_entity_code))?.node_key || ''
    form.entry_type = (TYPE_OPTIONS.find((o) => o.value === entry.entry_type)?.value) || 'other'
    form.description = entry.description || ''
    form.lines = linesToForm(entry)
  } else {
    form.target_key = fallback?.node_key || ''
    form.entry_type = props.defaultType
    form.description = ''
    form.lines = [emptyLine(), emptyLine()]
  }
}

watch(() => props.modelValue, (visible) => { if (visible) reset() }, { immediate: true })

function addLine() {
  form.lines.push(emptyLine())
}

function onAccountPicked(line: FormLine, code: string) {
  const opt = props.accounts.find((a) => a.account_code === code)
  if (opt?.account_name) line.account_name = opt.account_name
}

async function save() {
  const target = selectedTarget.value
  if (!target || formError.value) return
  if (formRef.value) {
    const ok = await formRef.value.validate().catch(() => false)
    if (!ok) return
  }
  saving.value = true
  const editingId = props.entry?.id || ''
  try {
    const payload = buildEntryPayload(target, form, {
      projectId: props.projectId, year: props.year, forUpdate: !!editingId,
    })
    const saved = editingId
      ? await updateElimination(editingId, props.projectId, payload)
      : await createElimination(props.projectId, payload)
    ElMessage.success(editingId ? '分录已修改' : '分录已保存为草稿，提交审批并审批后计入合并数')
    emit('update:modelValue', false)
    emit('saved', saved ?? null, editingId ? 'update' : 'create')
  } catch {
    /* 失败原因（含后端归属校验说明）由 http 拦截器统一提示 */
  } finally {
    saving.value = false
  }
}

defineExpose({ form, reset })
</script>

<style scoped>
.elim-form-tip { margin-left: 8px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.elim-form-footer { display: flex; align-items: center; justify-content: space-between; margin-top: 8px; }
.elim-form-totals { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); }
.elim-form-totals--bad { color: var(--gt-color-coral, #e6443e); }
</style>
