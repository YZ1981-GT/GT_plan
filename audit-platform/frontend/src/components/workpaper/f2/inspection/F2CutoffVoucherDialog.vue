<template>
  <el-dialog
    :model-value="modelValue"
    :title="dialogTitle"
    width="64%"
    top="5vh"
    destroy-on-close
    append-to-body
    class="f2ct-dialog"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <div v-if="form" class="f2ct-body">
      <div class="f2ct-main">
        <el-card shadow="never" class="f2ct-group">
          <template #header><span class="f2ct-gh">基本信息</span></template>
          <div class="f2ct-grid">
            <div class="f2ct-field"><label>存货类别</label>
              <el-select v-model="form.invCategory" size="small" :disabled="readonly" style="width:100%">
                <el-option label="—" value="" />
                <el-option label="原材料" value="raw" />
                <el-option label="产成品" value="finished" />
              </el-select>
            </div>
            <div class="f2ct-field"><label>对手方</label><el-input v-model="form.party" size="small" :disabled="readonly" /></div>
          </div>
        </el-card>

        <el-card shadow="never" class="f2ct-group">
          <template #header><span class="f2ct-gh">① 记账凭证</span></template>
          <div class="f2ct-grid">
            <div class="f2ct-field"><label>记账日期</label>
              <el-date-picker v-model="form.bookDate" type="date" value-format="YYYY-MM-DD" size="small" :disabled="readonly" style="width:100%" /></div>
            <div class="f2ct-field"><label>凭证编号</label><el-input v-model="form.voucherNo" size="small" :disabled="readonly" /></div>
            <div class="f2ct-field"><label>业务内容</label><el-input v-model="form.businessContent" size="small" :disabled="readonly" /></div>
            <div class="f2ct-field"><label>存货名称</label><el-input v-model="form.itemName" size="small" :disabled="readonly" /></div>
            <div class="f2ct-field"><label>数量</label><el-input-number v-model="form.quantity" :controls="false" size="small" :disabled="readonly" style="width:100%" /></div>
            <div class="f2ct-field"><label>账面金额</label><el-input-number v-model="form.amount" :controls="false" size="small" :disabled="readonly" style="width:100%" /></div>
          </div>
        </el-card>

        <el-card shadow="never" class="f2ct-group">
          <template #header><span class="f2ct-gh">② {{ primaryDocLabel }}</span></template>
          <div class="f2ct-grid">
            <div class="f2ct-field"><label>单据日期</label>
              <el-date-picker v-model="form.docDate" type="date" value-format="YYYY-MM-DD" size="small" :disabled="readonly" style="width:100%" /></div>
            <div class="f2ct-field"><label>单据编号</label><el-input v-model="form.docNo" size="small" :disabled="readonly" /></div>
            <div class="f2ct-field"><label>单据金额</label><el-input-number v-model="form.docAmount" :controls="false" size="small" :disabled="readonly" style="width:100%" /></div>
          </div>
        </el-card>

        <el-card v-if="showInspect" shadow="never" class="f2ct-group">
          <template #header><span class="f2ct-gh">③ 质检报告</span></template>
          <div class="f2ct-grid">
            <div class="f2ct-field"><label>质检日期</label>
              <el-date-picker v-model="form.inspectDate" type="date" value-format="YYYY-MM-DD" size="small" :disabled="readonly" style="width:100%" /></div>
            <div class="f2ct-field"><label>质检编号</label><el-input v-model="form.inspectNo" size="small" :disabled="readonly" /></div>
          </div>
        </el-card>
      </div>

      <aside class="f2ct-side">
        <el-card shadow="never" class="f2ct-panel">
          <template #header>
            <span class="f2ct-gh">实时勾稽</span>
            <el-tag size="small" :type="judge.isCorrect ? 'success' : 'danger'">
              {{ judge.isCorrect ? '截止正确' : '需关注' }}
            </el-tag>
          </template>
          <ul class="f2ct-checks">
            <li v-for="c in checks" :key="c.key" :class="'st-' + c.status">
              <span class="f2ct-check-icon">{{ ICON[c.status] }}</span>
              <span class="f2ct-check-label">{{ c.label }}</span>
              <span class="f2ct-check-detail">{{ c.detail }}</span>
            </li>
          </ul>
          <p v-if="judge.suggestion" class="f2ct-suggest">{{ judge.suggestion }}</p>
        </el-card>

        <el-card shadow="never" class="f2ct-panel">
          <template #header><span class="f2ct-gh">结论</span></template>
          <div class="f2ct-field"><label>截止正确</label>
            <el-select v-model="correctChoice" size="small" :disabled="readonly" style="width:100%">
              <el-option label="自动判定" value="auto" />
              <el-option label="强制正确" value="yes" />
              <el-option label="强制不正确" value="no" />
            </el-select>
          </div>
          <div class="f2ct-field"><label>备注</label>
            <el-input v-model="form.remark" type="textarea" :rows="2" size="small" :disabled="readonly" /></div>
        </el-card>
      </aside>
    </div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :disabled="readonly" @click="handleSave">保存本笔</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * F2CutoffVoucherDialog — F2-29~32 截止「逐笔核对」引导式弹窗。
 */
import { computed, toRef } from 'vue'
import {
  assessCutoffRow,
  evaluateCutoffChecks,
  type CutoffCheckResult,
} from '../../composables/f2CutoffJudgment'
import type { F2CutoffRow } from '../../composables/useF2CutoffSheet'
import { useVoucherCheckDialog } from '../../composables/useVoucherCheckDialog'

const props = defineProps<{
  modelValue: boolean
  row: F2CutoffRow | null
  periodEnd: string
  primaryDocLabel?: string
  showInspect?: boolean
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'save', patch: Partial<F2CutoffRow> & { id: string }): void
}>()

const { form, overrideChoice: correctChoice, buildSavePatch } = useVoucherCheckDialog<F2CutoffRow>({
  modelValue: toRef(props, 'modelValue'),
  row: toRef(props, 'row'),
  overrideKey: 'isCorrectOverride',
  getOverride: (r) => r.isCorrectOverride,
})

const primaryDocLabel = computed(() => props.primaryDocLabel || '入库/出库单')

const dialogTitle = computed(() =>
  form.value
    ? `逐笔核对 · ${form.value.voucherNo || form.value.docNo || '第 ' + form.value.seq + ' 笔'}`
    : '逐笔核对',
)

const checks = computed((): CutoffCheckResult[] => {
  if (!form.value) return []
  return evaluateCutoffChecks({
    voucherNo: form.value.voucherNo,
    bookDate: form.value.bookDate,
    docNo: form.value.docNo,
    docDate: form.value.docDate,
    amount: form.value.amount,
    docAmount: form.value.docAmount,
    periodEnd: props.periodEnd,
  })
})

const judge = computed(() => {
  if (!form.value) {
    return { isCorrect: true, suggestion: '' }
  }
  return assessCutoffRow({
    docDate: form.value.docDate,
    bookDate: form.value.bookDate,
    periodEnd: props.periodEnd,
    voucherNo: form.value.voucherNo,
    docNo: form.value.docNo,
    amount: form.value.amount,
    docAmount: form.value.docAmount,
    overrideCorrect: correctChoice.value === 'auto' ? null : correctChoice.value === 'yes',
  })
})

const ICON: Record<CutoffCheckResult['status'], string> = {
  ok: '✓', mismatch: '✗', missing: '!', pending: '…',
}

function handleSave() {
  const patch = buildSavePatch()
  if (!patch) return
  emit('save', patch)
  emit('update:modelValue', false)
}
</script>

<style scoped>
.f2ct-body { display: grid; grid-template-columns: 1fr 280px; gap: 12px; max-height: 72vh; }
.f2ct-main { overflow-y: auto; padding-right: 4px; display: flex; flex-direction: column; gap: 10px; }
.f2ct-side { display: flex; flex-direction: column; gap: 10px; position: sticky; top: 0; }
.f2ct-group :deep(.el-card__header), .f2ct-panel :deep(.el-card__header) {
  padding: 8px 12px; display: flex; align-items: center; justify-content: space-between;
}
.f2ct-group :deep(.el-card__body), .f2ct-panel :deep(.el-card__body) { padding: 10px 12px; }
.f2ct-gh { font-size: 13px; font-weight: 600; }
.f2ct-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 12px; }
.f2ct-field { display: flex; flex-direction: column; gap: 3px; }
.f2ct-field label { font-size: 12px; color: var(--el-text-color-secondary); }
.f2ct-checks { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.f2ct-checks li { display: grid; grid-template-columns: 18px 1fr; gap: 4px; align-items: start; font-size: 12px; }
.f2ct-checks .f2ct-check-detail { grid-column: 2; color: var(--el-text-color-secondary); font-size: 11px; }
.f2ct-check-icon { font-weight: 700; text-align: center; }
.f2ct-suggest { margin: 8px 0 0; font-size: 12px; color: var(--el-color-warning); }
.st-ok .f2ct-check-icon { color: var(--el-color-success); }
.st-mismatch .f2ct-check-icon, .st-missing .f2ct-check-icon { color: var(--el-color-danger); }
.st-mismatch .f2ct-check-label, .st-missing .f2ct-check-label { color: var(--el-color-danger); }
.st-pending .f2ct-check-icon { color: var(--el-text-color-placeholder); }
</style>
