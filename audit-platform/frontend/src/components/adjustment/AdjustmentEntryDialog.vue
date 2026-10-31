<template>
  <el-dialog v-model="visible" :title="title" width="920px" append-to-body :close-on-click-modal="false" class="gt-adj-entry-dialog">
    <el-alert
      v-if="accountsReady && !accountOptions.length"
      type="warning" show-icon :closable="false" class="gt-adj-entry-alert"
      title="本项目还没有标准科目，暂时选不了科目"
      description="请先在【试算表 → 科目映射】导入科目表并完成映射，再录入调整分录。"
    />
    <el-alert
      v-if="form.mode === 'edit' && form.reviewStatus === S.REJECTED"
      type="error" show-icon :closable="false" class="gt-adj-entry-alert"
      :title="`复核人驳回：${form.rejectionReason || '（未填写原因）'}`"
      description="修改保存后分录回到草稿，需要重新提交复核。"
    />

    <el-form ref="formRef" :model="form" :rules="FORM_RULES" label-width="64px" class="gt-adj-entry-form" @submit.prevent>
      <div class="gt-adj-entry-row">
        <el-form-item label="类型">
          <el-radio-group v-if="form.mode === 'create'" v-model="form.adjustment_type" size="small">
            <el-radio-button value="aje">审计调整 AJE</el-radio-button>
            <el-radio-button value="rje">重分类 RJE</el-radio-button>
          </el-radio-group>
          <span v-else>{{ form.adjustment_type === 'rje' ? '重分类 RJE' : '审计调整 AJE' }}</span>
        </el-form-item>
        <el-form-item label="编号" prop="adjustment_no">
          <el-input v-if="form.mode === 'create'" v-model="form.adjustment_no" size="small" maxlength="30" clearable
            placeholder="留空自动编号" style="width: 170px" />
          <span v-else class="gt-adj-entry-no">{{ form.adjustment_no }}</span>
        </el-form-item>
        <el-form-item v-if="form.mode === 'create'" label="模板">
          <el-select v-model="templateKey" size="small" clearable placeholder="常用分录（按科目名称匹配）" style="width: 230px"
            @change="onTemplate">
            <el-option-group label="审计调整">
              <el-option v-for="t in ajeTemplates" :key="t.key" :label="t.label" :value="t.key" />
            </el-option-group>
            <el-option-group label="重分类">
              <el-option v-for="t in rjeTemplates" :key="t.key" :label="t.label" :value="t.key" />
            </el-option-group>
          </el-select>
        </el-form-item>
      </div>
      <el-form-item label="摘要" prop="description">
        <el-input v-model="form.description" maxlength="500" show-word-limit
          placeholder="说明调整原因，如：按预期信用损失模型补提应收账款坏账准备" />
      </el-form-item>
    </el-form>

    <div class="gt-adj-entry-lines-head">
      <span class="gt-adj-entry-lines-title">明细行</span>
      <span class="gt-adj-entry-tip">可从 Excel 复制「科目编码、科目名称、借方、贷方」多行，点表格后粘贴</span>
      <span class="gt-adj-entry-spacer" />
      <el-button size="small" @click="addLine">+ 添加行</el-button>
    </div>
    <div class="gt-adj-entry-lines" tabindex="0" @paste="onPaste">
      <el-table :data="form.line_items" border size="small">
        <el-table-column label="#" type="index" width="44" align="center" />
        <el-table-column label="科目" min-width="330">
          <template #default="{ row }">
            <el-select v-model="row.standard_account_code" filterable clearable default-first-option size="small" style="width: 100%"
              :placeholder="row.account_name && !row.standard_account_code ? `未匹配「${row.account_name}」，请选择` : '输入编码或名称搜索'"
              @change="onAccountChange(row)">
              <el-option v-for="opt in accountOptions" :key="opt.code" :label="`${opt.code} ${opt.name}`" :value="opt.code">
                <div class="gt-adj-acct-opt">
                  <span>{{ opt.code }} {{ opt.name }}</span>
                  <span class="gt-adj-acct-meta">
                    <template v-if="opt.balance != null">审定 {{ fmtAmount(opt.balance) }}</template>
                    <template v-if="opt.report_line"> · {{ opt.report_line }}</template>
                  </span>
                </div>
              </el-option>
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="借方" width="150">
          <template #default="{ row }">
            <el-input-number v-model="row.debit_amount" :min="0" :precision="2" :controls="false" size="small" style="width: 100%"
              :placeholder="row.side === 'debit' ? '借方金额' : ''" @change="(v: number | null) => onAmount(row, 'debit_amount', v)" />
          </template>
        </el-table-column>
        <el-table-column label="贷方" width="150">
          <template #default="{ row }">
            <el-input-number v-model="row.credit_amount" :min="0" :precision="2" :controls="false" size="small" style="width: 100%"
              :placeholder="row.side === 'credit' ? '贷方金额' : ''" @change="(v: number | null) => onAmount(row, 'credit_amount', v)" />
          </template>
        </el-table-column>
        <el-table-column width="46" align="center">
          <template #default="{ $index }">
            <el-button link type="danger" :disabled="form.line_items.length <= 1" title="删除此行" @click="removeLine($index)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="gt-adj-entry-totals" :class="{ 'is-unbalanced': totals.diff !== 0 }">
      <span>借方合计 {{ fmtAmountWithZero(totals.debit / 100) }}</span>
      <span>贷方合计 {{ fmtAmountWithZero(totals.credit / 100) }}</span>
      <span>差额 {{ fmtAmountWithZero(totals.diff / 100) }}</span>
      <el-button v-if="totals.diff !== 0" size="small" link type="primary" @click="onFillDiff">差额补平</el-button>
    </div>
    <el-alert v-if="visibleErrors.length" type="error" :closable="false" class="gt-adj-entry-alert">
      <template #title>
        <div v-for="e in visibleErrors" :key="e">{{ e }}</div>
      </template>
    </el-alert>
    <el-alert v-if="serverError" type="error" show-icon :closable="false" class="gt-adj-entry-alert" :title="`保存失败：${serverError}`" />
    <AdjustmentImpactPreview v-if="visible" class="gt-adj-entry-impact" :project-id="projectId" :line-items="previewLines" :year="year" />

    <template #footer>
      <span class="gt-adj-entry-foot-tip">草稿不计入试算表；提交复核并批准后才计入审定数</span>
      <el-button @click="visible = false">取消</el-button>
      <el-button :loading="saving === 'save'" :disabled="!canEdit || !!saving" :title="canEdit ? '' : '项目已归档或无编辑权限'"
        @click="save(false)">{{ form.mode === 'edit' ? '保存' : '保存草稿' }}</el-button>
      <el-button type="primary" :loading="saving === 'submit'" :disabled="!canEdit || !!saving" @click="save(true)">保存并提交复核</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * 调整分录录入弹窗（新建 / 编辑 / 粘贴预填）—— spec adjustment-hall-entry-review-closure 需求 1。
 *
 * 行校验与后端同一套规则（adjustmentLineRules）；保存只建草稿，「保存并提交复核」交给大厅打开提交复核弹窗。
 * 大厅经 ref 调 openCreate / openEdit；草稿每 30 秒存一次，误关页面后可恢复。
 */
import { computed, nextTick, reactive, ref } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import AdjustmentImpactPreview from './AdjustmentImpactPreview.vue'
import { createAdjustment, updateAdjustment, type AccountOption } from '@/services/auditPlatformApi'
import { fmtAmount, fmtAmountWithZero } from '@/utils/formatters'
import { MISSING_AUDIT_YEAR_MESSAGE } from '@/composables/useProjectAuditYear'
import { useAutoSave } from '@/composables/useAutoSave'
import { adjustmentErrorMessage, reportAdjustmentError } from '@/composables/useAdjustmentHallActions'
import {
  fillDifference, isBlankLine, lineRuleErrors, lineTotals, linesForSubmit, parsePastedLines,
  type EditableLine, type EntrySavedPayload,
} from './adjustmentLineRules'
import { QUICK_TEMPLATES, applyQuickTemplate } from './adjustmentQuickTemplates'
import { ADJUSTMENT_STATUS as S } from '@/constants/statusEnum'

const props = withDefaults(defineProps<{
  projectId: string
  year: number | null
  accountOptions: AccountOption[]
  /** 科目下拉已加载（加载完仍为空才提示先做科目映射） */
  accountsReady?: boolean
  canEdit?: boolean
}>(), { accountsReady: true, canEdit: true })

const emit = defineEmits<{ saved: [payload: EntrySavedPayload] }>()

interface EntryForm {
  mode: 'create' | 'edit'
  entryGroupId: string
  reviewStatus: string
  rejectionReason: string
  adjustment_type: 'aje' | 'rje'
  adjustment_no: string
  description: string
  line_items: EditableLine[]
}

const blankLine = (): EditableLine => ({ standard_account_code: '', account_name: '', debit_amount: undefined, credit_amount: undefined })
const blankForm = (): EntryForm => ({
  mode: 'create', entryGroupId: '', reviewStatus: 'draft', rejectionReason: '', adjustment_type: 'aje',
  adjustment_no: '', description: '', line_items: [blankLine(), blankLine()],
})

const visible = ref(false)
const form = reactive<EntryForm>(blankForm())
const saving = ref<'' | 'save' | 'submit'>('')
/** 点过保存后才把全部规则错误列出来（录入过程中只看合计差额） */
const attempted = ref(false)
const serverError = ref('')
const templateKey = ref('')

const ajeTemplates = QUICK_TEMPLATES.filter((t) => t.type === 'aje')
const rjeTemplates = QUICK_TEMPLATES.filter((t) => t.type === 'rje')
const title = computed(() => (form.mode === 'edit' ? `编辑分录 ${form.adjustment_no}` : '新建调整分录'))
const totals = computed(() => lineTotals(form.line_items))
const ruleErrors = computed(() => lineRuleErrors(form.line_items))
const visibleErrors = computed(() => (attempted.value ? ruleErrors.value.slice(0, 6) : []))

const formRef = ref<FormInstance>()
/** 摘要必填（不能只有空格）；编号可空、不超过 30 字（后端同限，重复由后端判） */
const FORM_RULES: FormRules = {
  description: [{ required: true, whitespace: true, message: '请填写摘要', trigger: 'blur' }],
  adjustment_no: [{ max: 30, message: '编号不超过 30 个字符', trigger: 'blur' }],
}
const previewLines = computed(() => linesForSubmit(form.line_items).filter((li) => li.standard_account_code))

function reset(next: Partial<EntryForm> = {}) {
  Object.assign(form, blankForm(), next)
  attempted.value = false
  serverError.value = ''
  templateKey.value = ''
  void nextTick(() => formRef.value?.clearValidate())
}

/** 新建；可带粘贴 / 外部预填的明细与摘要 */
function openCreate(prefill?: { lines?: EditableLine[]; description?: string; problems?: string[] }) {
  reset({
    line_items: prefill?.lines?.length ? prefill.lines.map((li) => ({ ...li })) : [blankLine(), blankLine()],
    description: prefill?.description || '',
  })
  visible.value = true
  if (prefill?.problems?.length) ElMessage.warning({ message: prefill.problems.slice(0, 3).join('；'), duration: 6000, showClose: true })
}

function openEdit(row: {
  entry_group_id: string; adjustment_no?: string | null; adjustment_type?: string; description?: string | null
  review_status?: string; rejection_reason?: string | null
  line_items?: Array<{ standard_account_code: string; account_name?: string | null; detail_account_code?: string | null
    report_line_code?: string | null; debit_amount: unknown; credit_amount: unknown }>
}) {
  const amount = (v: unknown) => (Number(v) ? Number(v) : undefined)
  reset({
    mode: 'edit',
    entryGroupId: row.entry_group_id,
    reviewStatus: row.review_status || 'draft',
    rejectionReason: row.rejection_reason || '',
    adjustment_type: String(row.adjustment_type || 'aje').toLowerCase() === 'rje' ? 'rje' : 'aje',
    adjustment_no: row.adjustment_no || '',
    description: row.description || '',
    line_items: (row.line_items || []).map((li) => ({
      standard_account_code: li.standard_account_code,
      account_name: li.account_name || '',
      detail_account_code: li.detail_account_code || null,
      report_line_code: li.report_line_code || null,
      debit_amount: amount(li.debit_amount),
      credit_amount: amount(li.credit_amount),
    })),
  })
  if (!form.line_items.length) form.line_items = [blankLine(), blankLine()]
  visible.value = true
}

function addLine() {
  form.line_items.push(blankLine())
}

function removeLine(idx: number) {
  form.line_items.splice(idx, 1)
}

function onAccountChange(row: EditableLine) {
  const opt = props.accountOptions.find((o) => o.code === row.standard_account_code)
  row.account_name = opt?.name || ''
  row.detail_account_code = null
  row.report_line_code = null
}

/** 一行只能记一个方向：填了借方就清空贷方，反之亦然 */
function onAmount(row: EditableLine, field: 'debit_amount' | 'credit_amount', value: number | null) {
  if (value) row[field === 'debit_amount' ? 'credit_amount' : 'debit_amount'] = undefined
}

function onFillDiff() {
  form.line_items = fillDifference(form.line_items)
}

function onTemplate(key: string) {
  const tpl = QUICK_TEMPLATES.find((t) => t.key === key)
  if (!tpl) return
  const applied = applyQuickTemplate(tpl, props.accountOptions)
  form.adjustment_type = applied.type
  if (!form.description.trim()) form.description = applied.description
  const kept = form.line_items.filter((li) => !isBlankLine(li))
  form.line_items = [...kept, ...applied.lines]
  if (applied.unmatched.length) {
    ElMessage.warning({ message: `本项目科目中没有找到「${applied.unmatched.join('」「')}」，请在对应行手工选择科目`, duration: 6000, showClose: true })
  }
}

/** 表格里粘贴 Excel 多行：追加为明细行（单个值的粘贴交给输入框自己处理） */
function onPaste(e: ClipboardEvent) {
  const text = e.clipboardData?.getData('text/plain') || ''
  if (!text.includes('\t')) return
  e.preventDefault()
  const parsed = parsePastedLines(text, props.accountOptions)
  if (!parsed.lines.length) return
  form.line_items = [...form.line_items.filter((li) => !isBlankLine(li)), ...parsed.lines]
  if (!form.description.trim() && parsed.summary) form.description = parsed.summary
  const tail = parsed.problems.length ? `；${parsed.problems.slice(0, 2).join('；')}` : ''
  ElMessage({ type: parsed.problems.length ? 'warning' : 'success', message: `已粘贴 ${parsed.lines.length} 行${tail}`, showClose: true })
}

function savedMessage(no: string): string {
  if (form.mode === 'create') return `已保存为草稿 ${no}。草稿不计入试算表，提交复核并批准后才计入审定数`
  return form.reviewStatus === S.REJECTED ? `已保存 ${no}，分录回到草稿，需要重新提交复核` : `已保存 ${no}`
}

async function save(submit: boolean) {
  attempted.value = true
  serverError.value = ''
  if (props.year == null) {
    ElMessage.warning(MISSING_AUDIT_YEAR_MESSAGE)
    return
  }
  const formOk = await (formRef.value?.validate().then(() => true, () => false) ?? Promise.resolve(true))
  if (!formOk) return
  if (ruleErrors.value.length) {
    ElMessage.warning(ruleErrors.value[0])
    return
  }
  saving.value = submit ? 'submit' : 'save'
  try {
    const line_items = linesForSubmit(form.line_items)
    const description = form.description.trim()
    const result: { entry_group_id: string; adjustment_no: string } = form.mode === 'edit'
      ? await updateAdjustment(props.projectId, form.entryGroupId, { description, line_items })
      : await createAdjustment(props.projectId, {
        adjustment_type: form.adjustment_type, year: props.year, description, line_items,
        adjustment_no: form.adjustment_no.trim() || undefined,
      })
    const payload: EntrySavedPayload = {
      entryGroupId: String(result?.entry_group_id || form.entryGroupId),
      adjustmentNo: result?.adjustment_no || form.adjustment_no,
      mode: form.mode,
      submit,
    }
    ElMessage.success({
      message: submit ? `已保存 ${payload.adjustmentNo}，请选择复核人后提交` : savedMessage(payload.adjustmentNo),
      duration: 5000, showClose: true,
    })
    clearDraft()
    visible.value = false
    emit('saved', payload)
  } catch (err) {
    const status = (err as { response?: { status?: number } })?.response?.status
    if (status === 423) {
      reportAdjustmentError(err, '保存')
    } else {
      serverError.value = adjustmentErrorMessage(err)
    }
  } finally {
    saving.value = ''
  }
}

// ── 草稿自动保存（兼容旧页面存的 {isEditing, editingGroupId} 形状）──
const { clearDraft } = useAutoSave(
  () => `adjustment_form_${props.projectId}`,
  () => (visible.value ? JSON.parse(JSON.stringify(form)) : null),
  (data: any) => {
    if (!data) return
    reset({
      mode: data.mode === 'edit' || data.isEditing ? 'edit' : 'create',
      entryGroupId: data.entryGroupId || data.editingGroupId || '',
      reviewStatus: data.reviewStatus || 'draft',
      rejectionReason: data.rejectionReason || '',
      adjustment_type: data.adjustment_type === 'rje' ? 'rje' : 'aje',
      adjustment_no: data.adjustment_no || '',
      description: data.description || '',
      line_items: Array.isArray(data.line_items) && data.line_items.length ? data.line_items : [blankLine(), blankLine()],
    })
    visible.value = true
  },
  { enabled: visible },
)

defineExpose({ openCreate, openEdit, visible })
</script>

<style scoped>
.gt-adj-entry-alert { margin-bottom: 10px; }
.gt-adj-entry-form :deep(.el-form-item) { margin-bottom: 12px; }
.gt-adj-entry-row { display: flex; flex-wrap: wrap; gap: 0 12px; }
.gt-adj-entry-no { font-weight: 600; color: var(--gt-color-primary); }
.gt-adj-entry-lines-head {
  display: flex; align-items: center; gap: 10px;
  padding-bottom: 6px; margin-bottom: 6px;
  border-bottom: 1px solid var(--gt-color-border-light);
}
.gt-adj-entry-lines-title { font-weight: 600; }
.gt-adj-entry-tip { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.gt-adj-entry-spacer { flex: 1; }
.gt-adj-acct-opt { display: flex; justify-content: space-between; gap: 12px; width: 100%; }
.gt-adj-acct-meta {
  font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary);
  font-variant-numeric: tabular-nums; white-space: nowrap;
}
.gt-adj-entry-totals {
  display: flex; justify-content: flex-end; align-items: center; gap: 18px;
  margin: 8px 0; padding: 6px 12px;
  border-radius: var(--gt-radius-sm);
  background: var(--gt-color-success-light);
  color: var(--gt-color-success);
  font-weight: 600; font-variant-numeric: tabular-nums;
}
.gt-adj-entry-totals.is-unbalanced { background: var(--gt-color-coral-light); color: var(--gt-color-coral); }
.gt-adj-entry-impact { margin-top: 8px; }
.gt-adj-entry-lines:focus { outline: none; }
.gt-adj-entry-foot-tip { float: left; line-height: 32px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
</style>
