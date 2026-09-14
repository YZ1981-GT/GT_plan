<template>
  <el-dialog
    :model-value="modelValue"
    :title="dialogTitle"
    width="64%"
    top="6vh"
    destroy-on-close
    append-to-body
    class="f2sc-dialog"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <div v-if="form" class="f2sc-body">
      <div class="f2sc-main">
        <el-card shadow="never" class="f2sc-group">
          <template #header>
            <span class="f2sc-gh">① 合同 / 加工单位</span>
            <el-upload
              v-if="canOcr"
              :show-file-list="false"
              :auto-upload="false"
              accept=".pdf,.png,.jpg,.jpeg"
              :disabled="!!ocrLoadingId"
              @change="(f: any) => runOcr(f?.raw, 'contract')"
            >
              <el-button link size="small" data-testid="f2-35-ocr-contract" :loading="ocrLoadingId?.endsWith(':contract')">📎 上传识别</el-button>
            </el-upload>
          </template>
          <div class="f2sc-grid">
            <div class="f2sc-field"><label>加工单位</label><el-input v-model="form.processor" size="small" :disabled="readonly" /></div>
            <div class="f2sc-field"><label>合同或协议号</label><el-input v-model="form.contractNo" size="small" :disabled="readonly" /></div>
            <div class="f2sc-field"><label>发出时间</label><el-input v-model="form.issueDate" size="small" :disabled="readonly" /></div>
            <div class="f2sc-field"><label>索引号</label><el-input v-model="form.indexRef" size="small" :disabled="readonly" /></div>
          </div>
        </el-card>

        <el-card shadow="never" class="f2sc-group">
          <template #header>
            <span class="f2sc-gh">② 发出 / 加工费 / 收回</span>
            <el-upload
              v-if="canOcr"
              :show-file-list="false"
              :auto-upload="false"
              accept=".pdf,.png,.jpg,.jpeg"
              :disabled="!!ocrLoadingId"
              @change="(f: any) => runOcr(f?.raw, 'fee')"
            >
              <el-button link size="small" data-testid="f2-35-ocr-fee" :loading="ocrLoadingId?.endsWith(':fee')">📎 上传识别</el-button>
            </el-upload>
          </template>
          <div class="f2sc-grid">
            <div class="f2sc-field"><label>发出材料成本</label><el-input-number v-model="form.issueCost" :controls="false" size="small" :disabled="readonly" style="width:100%" /></div>
            <div class="f2sc-field"><label>加工费</label><el-input-number v-model="form.fee" :controls="false" size="small" :disabled="readonly" style="width:100%" /></div>
            <div class="f2sc-field"><label>收回材料成本</label><el-input-number v-model="form.recoverCost" :controls="false" size="small" :disabled="readonly" style="width:100%" /></div>
            <div class="f2sc-field"><label>应收回(发出+加工费)</label>
              <el-input :model-value="recover.expected.toLocaleString()" size="small" disabled />
            </div>
          </div>
        </el-card>

        <el-card shadow="never" class="f2sc-group">
          <template #header><span class="f2sc-gh">③ 未收回说明</span></template>
          <div class="f2sc-field"><label>未收回原因及是否需函证</label>
            <el-input v-model="form.unrecoveredNote" type="textarea" :rows="2" size="small" :disabled="readonly" />
          </div>
          <div class="f2sc-field" style="margin-top:8px"><label>备注</label>
            <el-input v-model="form.remark" type="textarea" :rows="2" size="small" :disabled="readonly" />
          </div>
        </el-card>
      </div>

      <aside class="f2sc-side">
        <el-card shadow="never" class="f2sc-panel">
          <template #header>
            <span class="f2sc-gh">实时勾稽</span>
            <el-tag size="small" :type="recover.status === 'ok' ? 'success' : recover.status === 'pending' ? 'info' : 'danger'">
              {{ recover.status === 'ok' ? '计价一致'
                : recover.status === 'unrecovered' ? '未全额收回'
                : recover.status === 'valuation' ? '计价差异' : '待填' }}
            </el-tag>
          </template>
          <ul class="f2sc-checks">
            <li v-for="c in checks" :key="c.key" :class="'st-' + c.status">
              <span class="f2sc-check-icon">{{ ICON[c.status] }}</span>
              <span class="f2sc-check-label">{{ c.label }}</span>
              <span class="f2sc-check-detail">{{ c.detail }}</span>
            </li>
          </ul>
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
 * F2SubcontractVoucherDialog — F2-35 表三「逐笔核对」引导式弹窗（对齐 F2-33/34）。
 * 合同组 / 加工费组支持 📎 OCR（复用 /f2/contract-ocr + mapOcrFieldsToSubcontract）。
 */
import { computed, toRef, type Ref } from 'vue'
import {
  evaluateSubcontractRecover,
  evaluateSubcontractRecoverChecks,
  type SubcontractSupplier2Row,
  type PurchaseCheckStatus,
} from '../../composables/useF2InspectionCheckFormulas'
import { useVoucherCheckDialog } from '../../composables/useVoucherCheckDialog'
import { useF2SubcontractOcr, type SubcontractOcrTarget } from '../../composables/useF2SubcontractOcr'

const props = defineProps<{
  modelValue: boolean
  row: SubcontractSupplier2Row | null
  wpId?: string
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'save', patch: Partial<SubcontractSupplier2Row> & { id: string }): void
}>()

const { form, buildSavePatch } = useVoucherCheckDialog<SubcontractSupplier2Row>({
  modelValue: toRef(props, 'modelValue'),
  row: toRef(props, 'row'),
  overrideKey: false,
})

const dialogTitle = computed(() =>
  form.value
    ? `逐笔核对 · ${form.value.processor || form.value.contractNo || '第 ' + form.value.seq + ' 笔'}`
    : '逐笔核对',
)

const recover = computed(() =>
  form.value ? evaluateSubcontractRecover(form.value) : { expected: 0, variance: 0, status: 'pending' as const, detail: '' },
)
const checks = computed(() => (form.value ? evaluateSubcontractRecoverChecks(form.value) : []))
const ICON: Record<PurchaseCheckStatus, string> = { ok: '✓', mismatch: '✗', missing: '!', pending: '…' }

const canOcr = computed(() => !!props.wpId && !props.readonly)
const { ocrLoadingId, uploadAndMerge } = useF2SubcontractOcr(
  computed(() => props.wpId || '') as Ref<string>,
)

function runOcr(file: File | undefined, target: SubcontractOcrTarget) {
  if (!file || !form.value) return
  void uploadAndMerge(form.value.id, file, target, (_id, patch) => {
    if (form.value) Object.assign(form.value, patch)
  })
}

function handleSave() {
  const patch = buildSavePatch()
  if (!patch) return
  emit('save', patch)
  emit('update:modelValue', false)
}
</script>

<style scoped>
.f2sc-body { display: grid; grid-template-columns: 1fr 280px; gap: 12px; max-height: 70vh; }
.f2sc-main { overflow-y: auto; padding-right: 4px; display: flex; flex-direction: column; gap: 10px; }
.f2sc-side { display: flex; flex-direction: column; gap: 10px; position: sticky; top: 0; }
.f2sc-group :deep(.el-card__header), .f2sc-panel :deep(.el-card__header) {
  padding: 8px 12px; display: flex; align-items: center; justify-content: space-between;
}
.f2sc-group :deep(.el-card__body), .f2sc-panel :deep(.el-card__body) { padding: 10px 12px; }
.f2sc-gh { font-size: 13px; font-weight: 600; }
.f2sc-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 12px; }
.f2sc-field { display: flex; flex-direction: column; gap: 3px; }
.f2sc-field label { font-size: 12px; color: var(--el-text-color-secondary); }
.f2sc-checks { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.f2sc-checks li { display: grid; grid-template-columns: 18px 1fr; gap: 4px; align-items: start; font-size: 12px; }
.f2sc-checks .f2sc-check-detail { grid-column: 2; color: var(--el-text-color-secondary); font-size: 11px; }
.f2sc-check-icon { font-weight: 700; text-align: center; }
.st-ok .f2sc-check-icon { color: var(--el-color-success); }
.st-mismatch .f2sc-check-icon, .st-missing .f2sc-check-icon { color: var(--el-color-danger); }
.st-mismatch .f2sc-check-label, .st-missing .f2sc-check-label { color: var(--el-color-danger); }
.st-pending .f2sc-check-icon { color: var(--el-text-color-placeholder); }
</style>
