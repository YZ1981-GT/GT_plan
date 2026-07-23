<template>
  <el-dialog
    :model-value="modelValue"
    :title="dialogTitle"
    width="72%"
    top="4vh"
    destroy-on-close
    append-to-body
    class="k1vc-dialog"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <div v-if="form" class="k1vc-body">
      <div class="k1vc-main">
        <el-card shadow="never" class="k1vc-group">
          <template #header><span class="k1vc-gh">基本信息</span></template>
          <div class="k1vc-grid">
            <div class="k1vc-field">
              <label>债务人名称</label>
              <el-input v-model="form.debtorName" size="small" :disabled="readonly" />
            </div>
            <div class="k1vc-field">
              <label>日期</label>
              <el-input v-model="form.date" size="small" placeholder="YYYY-MM-DD" :disabled="readonly" />
            </div>
            <div class="k1vc-field">
              <label>索引号</label>
              <el-input v-model="form.indexNo" size="small" :disabled="readonly" />
            </div>
          </div>
        </el-card>

        <el-card shadow="never" class="k1vc-group">
          <template #header><span class="k1vc-gh">① 记账凭证</span></template>
          <div class="k1vc-grid">
            <div class="k1vc-field">
              <label>凭证编号</label>
              <el-input v-model="form.voucherNo" size="small" :disabled="readonly" />
            </div>
            <div class="k1vc-field">
              <label>业务内容</label>
              <el-input v-model="form.businessContent" size="small" :disabled="readonly" />
            </div>
            <div class="k1vc-field">
              <label>对方科目</label>
              <el-input v-model="form.offsetAccount" size="small" :disabled="readonly" />
            </div>
            <div class="k1vc-field">
              <label>对方明细科目</label>
              <el-input v-model="form.offsetSubAccount" size="small" :disabled="readonly" />
            </div>
            <div v-if="mode === 'occurrence'" class="k1vc-field">
              <label>借方金额</label>
              <el-input-number v-model="form.debitAmount" :controls="false" size="small" :disabled="readonly" style="width:100%" />
            </div>
            <div class="k1vc-field">
              <label>{{ mode === 'post' ? '收款金额（贷方）' : '贷方金额' }}</label>
              <el-input-number v-model="form.creditAmount" :controls="false" size="small" :disabled="readonly" style="width:100%" />
            </div>
          </div>
        </el-card>

        <el-card shadow="never" class="k1vc-group">
          <template #header>
            <span class="k1vc-gh">② 支持性文件 / 证据</span>
            <el-upload
              v-if="!readonly"
              :show-file-list="false"
              :auto-upload="false"
              accept=".pdf,.png,.jpg,.jpeg,.webp"
              :disabled="ocrLoading"
              @change="(f: any) => onOcrFile(f?.raw)"
            >
              <el-button link size="small" type="primary" :loading="ocrLoading">📎 OCR 识别</el-button>
            </el-upload>
          </template>
          <div class="k1vc-grid">
            <div class="k1vc-field k1vc-span2">
              <label>支持性文件</label>
              <el-input v-model="form.supportingDoc" type="textarea" :rows="2" size="small" :disabled="readonly" />
            </div>
            <div v-if="form.ocrAttachment" class="k1vc-field k1vc-span2">
              <el-tag size="small" type="success">已附：{{ form.ocrAttachment }}</el-tag>
            </div>
          </div>
        </el-card>

        <el-card shadow="never" class="k1vc-group">
          <template #header><span class="k1vc-gh">③ 五项核对</span></template>
          <div class="k1vc-checks-edit">
            <el-checkbox
              v-for="(label, i) in checkLabels"
              :key="i"
              :model-value="!!form.checks[i]"
              :disabled="readonly"
              @change="(v: boolean | string | number) => setCheck(i, !!v)"
            >
              {{ i + 1 }}. {{ label }}
            </el-checkbox>
          </div>
        </el-card>
      </div>

      <aside class="k1vc-side">
        <el-card shadow="never" class="k1vc-panel">
          <template #header>
            <span class="k1vc-gh">实时勾稽</span>
            <el-tag size="small" :type="sideTagType">{{ sideTagLabel }}</el-tag>
          </template>
          <ul class="k1vc-live">
            <li v-for="c in liveChecks" :key="c.key" :class="'st-' + c.status">
              <span class="k1vc-icon">{{ ICON[c.status] }}</span>
              <span class="k1vc-llabel">{{ c.label }}</span>
              <span class="k1vc-ldetail">{{ c.detail }}</span>
            </li>
          </ul>
        </el-card>

        <el-card shadow="never" class="k1vc-panel">
          <template #header><span class="k1vc-gh">结论</span></template>
          <div class="k1vc-field">
            <label>是否异常</label>
            <el-switch v-model="form.abnormal" :disabled="readonly" />
          </div>
          <div class="k1vc-field">
            <label>备注</label>
            <el-input v-model="form.remark" type="textarea" :rows="3" size="small" :disabled="readonly" />
          </div>
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
 * K1VoucherCheckDialog — K1-12 凭证级「逐笔核对」引导弹窗
 * 对齐 F2-33：分组录入 + 右侧实时勾稽 + OCR 确认回写
 */
import { computed, toRef } from 'vue'
import { useVoucherCheckDialog } from '../../composables/useVoucherCheckDialog'
import { useK1VoucherOcr } from '../../composables/useK1VoucherOcr'
import {
  K1_VOUCHER_CHECK_LABELS,
  evaluateK1VoucherChecks,
  isK1VoucherRowChecksComplete,
  k1VoucherCardStatus,
  type K1VoucherCheckStatus,
  type K1VoucherRow,
} from '../../composables/useK1VoucherCheck'

const props = defineProps<{
  modelValue: boolean
  row: K1VoucherRow | null
  mode?: 'occurrence' | 'post'
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'save', patch: Partial<K1VoucherRow> & { id: string }): void
}>()

const checkLabels = K1_VOUCHER_CHECK_LABELS
const mode = computed(() => props.mode ?? 'occurrence')

const { form, buildSavePatch } = useVoucherCheckDialog<K1VoucherRow>({
  modelValue: toRef(props, 'modelValue'),
  row: toRef(props, 'row'),
  overrideKey: false,
})

const { ocrLoading, runOcr } = useK1VoucherOcr()

const dialogTitle = computed(() => {
  if (!form.value) return '逐笔核对'
  const name = form.value.debtorName || form.value.voucherNo || '本笔'
  return `逐笔核对 · ${mode.value === 'post' ? '期后收款' : '本期发生'} · ${name}`
})

const liveChecks = computed(() => (form.value ? evaluateK1VoucherChecks(form.value) : []))
const sideStatus = computed(() => (form.value ? k1VoucherCardStatus(form.value) : null))
const sideTagType = computed(() => sideStatus.value?.type ?? 'info')
const sideTagLabel = computed(() => sideStatus.value?.label ?? '—')

const ICON: Record<K1VoucherCheckStatus, string> = {
  ok: '✓',
  missing: '!',
  pending: '…',
  warn: '⚠',
}

function setCheck(index: number, checked: boolean): void {
  if (!form.value || props.readonly) return
  const next = [...(form.value.checks || [false, false, false, false, false])]
  while (next.length < 5) next.push(false)
  next[index] = checked
  form.value.checks = next
  // 五项全勾且未强制异常时，清除异常；任一项未勾不自动改异常
  if (isK1VoucherRowChecksComplete(form.value) && !form.value.abnormal) {
    /* keep */
  }
}

function onOcrFile(file?: File): void {
  if (!file || !form.value || props.readonly) return
  void runOcr(file, (text, fileName) => {
    if (!form.value) return
    form.value.supportingDoc = form.value.supportingDoc
      ? `${form.value.supportingDoc}\n[OCR] ${text}`
      : `[OCR] ${text}`
    form.value.ocrAttachment = fileName
    if (!form.value.remark?.includes('[OCR]')) {
      form.value.remark = form.value.remark
        ? `${form.value.remark}\n[OCR附件] ${fileName}`
        : `[OCR附件] ${fileName}`
    }
  })
}

function handleSave(): void {
  const patch = buildSavePatch()
  if (!patch) return
  emit('save', patch)
  emit('update:modelValue', false)
}
</script>

<style scoped>
.k1vc-body {
  display: grid;
  grid-template-columns: 1fr 280px;
  gap: 12px;
  max-height: calc(92vh - 140px);
  overflow: auto;
}
.k1vc-main { display: flex; flex-direction: column; gap: 10px; }
.k1vc-group :deep(.el-card__header) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
}
.k1vc-gh { font-weight: 600; font-size: 13px; }
.k1vc-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 12px;
}
.k1vc-field { display: flex; flex-direction: column; gap: 4px; }
.k1vc-field label { font-size: 12px; color: var(--el-text-color-secondary); }
.k1vc-span2 { grid-column: 1 / -1; }
.k1vc-checks-edit { display: flex; flex-direction: column; gap: 6px; }
.k1vc-side { display: flex; flex-direction: column; gap: 10px; }
.k1vc-panel :deep(.el-card__header) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
}
.k1vc-live { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.k1vc-live li { display: grid; grid-template-columns: 18px 1fr; gap: 2px 6px; font-size: 12px; }
.k1vc-llabel { grid-column: 2; font-weight: 500; }
.k1vc-ldetail { grid-column: 2; color: var(--el-text-color-secondary); }
.st-ok .k1vc-icon { color: var(--el-color-success); }
.st-pending .k1vc-icon { color: var(--el-color-info); }
.st-warn .k1vc-icon { color: var(--el-color-warning); }
.st-missing .k1vc-icon { color: var(--el-color-danger); }
@media (max-width: 900px) {
  .k1vc-body { grid-template-columns: 1fr; }
}
</style>
