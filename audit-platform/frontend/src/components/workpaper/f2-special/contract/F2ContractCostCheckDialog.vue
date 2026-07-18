<template>
  <el-dialog
    :model-value="modelValue"
    :title="dialogTitle"
    width="74%"
    top="4vh"
    destroy-on-close
    append-to-body
    @update:model-value="(value: boolean) => emit('update:modelValue', value)"
  >
    <div v-if="form" class="check-dialog-body">
      <main class="document-groups">
        <el-card shadow="never" class="document-card">
          <template #header><span>基本信息</span></template>
          <div class="field-grid">
            <label>项目名称<el-input v-model="form.projectName" size="small" :disabled="readonly" /></label>
            <label>合同履约成本科目/明细<el-input v-model="form.accountDetail" size="small" :disabled="readonly" /></label>
          </div>
        </el-card>

        <el-card shadow="never" class="document-card">
          <template #header>
            <span>① 记账凭证</span>
            <el-upload v-if="canOcr" :show-file-list="false" :auto-upload="false"
              accept=".pdf,.png,.jpg,.jpeg" :disabled="isOcrLoading('voucher')"
              @change="(file: any) => runOcr(file?.raw, 'voucher')">
              <el-button link type="primary" size="small" :loading="isOcrLoading('voucher')">📎 上传凭证并识别</el-button>
            </el-upload>
          </template>
          <div class="field-grid">
            <label>凭证号<el-input v-model="form.voucherNo" size="small" :disabled="readonly" /></label>
            <label>业务内容<el-input v-model="form.businessContent" size="small" :disabled="readonly" /></label>
            <label>对方科目<el-input v-model="form.offsetAccount" size="small" :disabled="readonly" /></label>
            <label>对方项目<el-input v-model="form.offsetProject" size="small" :disabled="readonly" /></label>
            <label>金额<el-input-number v-model="form.voucherAmount" :controls="false" size="small" :disabled="readonly" /></label>
          </div>
        </el-card>

        <el-card shadow="never" class="document-card">
          <template #header>
            <span>② 合同 / 协议</span>
            <el-upload v-if="canOcr" :show-file-list="false" :auto-upload="false"
              accept=".pdf,.png,.jpg,.jpeg" :disabled="isOcrLoading('contract')"
              @change="(file: any) => runOcr(file?.raw, 'contract')">
              <el-button link type="primary" size="small" :loading="isOcrLoading('contract')">📎 上传合同并识别</el-button>
            </el-upload>
          </template>
          <div class="field-grid">
            <label>日期/编号<el-input v-model="form.contractDateNo" size="small" :disabled="readonly" /></label>
            <label class="full">主要条款<el-input v-model="form.contractTerms" type="textarea" :rows="2" :disabled="readonly" /></label>
          </div>
        </el-card>

        <el-card shadow="never" class="document-card">
          <template #header>
            <span>③ 到货验收单</span>
            <el-upload
              v-if="canOcr"
              :show-file-list="false"
              :auto-upload="false"
              accept=".pdf,.png,.jpg,.jpeg"
              :disabled="isOcrLoading('receipt')"
              @change="(file: any) => runOcr(file?.raw, 'receipt')"
            >
              <el-button link type="primary" size="small" :loading="isOcrLoading('receipt')">📎 上传验收单并识别</el-button>
            </el-upload>
          </template>
          <div class="field-grid">
            <label>产品名称<el-input v-model="form.receiptProductName" size="small" :disabled="readonly" /></label>
            <label>金额<el-input-number v-model="form.receiptAmount" :controls="false" size="small" :disabled="readonly" /></label>
          </div>
        </el-card>

        <el-card shadow="never" class="document-card">
          <template #header>
            <span>④ 物流单 / 运输单</span>
            <el-upload v-if="canOcr" :show-file-list="false" :auto-upload="false"
              accept=".pdf,.png,.jpg,.jpeg" :disabled="isOcrLoading('logistics')"
              @change="(file: any) => runOcr(file?.raw, 'logistics')">
              <el-button link type="primary" size="small" :loading="isOcrLoading('logistics')">📎 上传物流单并识别</el-button>
            </el-upload>
          </template>
          <div class="field-grid">
            <label>数量<el-input-number v-model="form.logisticsQty" :controls="false" size="small" :disabled="readonly" /></label>
            <label>日期/编号<el-input v-model="form.logisticsDateNo" size="small" :disabled="readonly" /></label>
            <label>产品名称<el-input v-model="form.logisticsProductName" size="small" :disabled="readonly" /></label>
            <label>物流商<el-input v-model="form.logisticsProvider" size="small" :disabled="readonly" /></label>
          </div>
        </el-card>

        <el-card shadow="never" class="document-card">
          <template #header>
            <span>⑤ 费用分配表 / 计算表</span>
            <el-upload v-if="canOcr" :show-file-list="false" :auto-upload="false"
              accept=".pdf,.png,.jpg,.jpeg" :disabled="isOcrLoading('allocation')"
              @change="(file: any) => runOcr(file?.raw, 'allocation')">
              <el-button link type="primary" size="small" :loading="isOcrLoading('allocation')">📎 上传分配表并识别</el-button>
            </el-upload>
          </template>
          <div class="field-grid">
            <label>数量<el-input-number v-model="form.allocQty" :controls="false" size="small" :disabled="readonly" /></label>
            <label>月份<el-input v-model="form.allocMonth" size="small" :disabled="readonly" /></label>
            <label>金额<el-input-number v-model="form.allocAmount" :controls="false" size="small" :disabled="readonly" /></label>
            <label>分配依据<el-input v-model="form.allocBasis" size="small" :disabled="readonly" /></label>
          </div>
        </el-card>
      </main>

      <aside class="check-side">
        <el-card shadow="never">
          <template #header>
            <div class="side-header">
              <span>实时单据勾稽</span>
              <el-tag size="small" :type="hasProblem ? 'danger' : 'success'">
                {{ hasProblem ? '待核对' : '勾稽完成' }}
              </el-tag>
            </div>
          </template>
          <ul class="check-list">
            <li v-for="item in checks" :key="item.key" :class="`status-${item.status}`">
              <span class="check-icon">{{ statusIcon[item.status] }}</span>
              <div><strong>{{ item.label }}</strong><small>{{ item.detail }}</small></div>
            </li>
          </ul>
        </el-card>

        <el-card shadow="never">
          <template #header><span>本笔结论</span></template>
          <label>索引号<el-input v-model="form.indexRef" size="small" :disabled="readonly" /></label>
          <label>是否异常
            <el-select v-model="form.isAbnormal" size="small" :disabled="readonly">
              <el-option label="否" value="否" />
              <el-option label="是" value="是" />
            </el-select>
          </label>
          <label>
            <span class="issue-label">
              异常说明
              <el-button link type="primary" size="small"
                :disabled="readonly || !aiAvailable" :loading="aiLoading"
                @click="runIssueAi">AI 生成</el-button>
            </span>
            <el-input v-model="form.issueDesc" type="textarea" :rows="3" :disabled="readonly" />
          </label>
          <el-button type="primary" class="side-save" :disabled="readonly" @click="save">保存本笔</el-button>
        </el-card>
      </aside>
    </div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :disabled="readonly" @click="save">保存本笔</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch, type Ref } from 'vue'
import {
  useF2SpecialContractOcr,
  type F2SpeDocumentType,
} from '../../composables/useF2SpecialContractOcr'
import { useF2SpecialAiGenerate } from '../../composables/useF2SpecialAiGenerate'
import {
  evaluateContractCostEvidence,
  type ContractCostCheckSample,
  type ContractCostCheckStatus,
} from '../../composables/useF2ContractCostCheckFormulas'

const props = defineProps<{
  modelValue: boolean
  row: ContractCostCheckSample | null
  wpId?: string
  readonly?: boolean
}>()

const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void
  (event: 'save', patch: ContractCostCheckSample): void
}>()

const form = ref<ContractCostCheckSample | null>(null)
watch(
  () => [props.modelValue, props.row] as const,
  ([visible, row]) => {
    if (visible && row) form.value = { ...row }
  },
  { immediate: true },
)

const dialogTitle = computed(() =>
  `逐笔单据核对 · ${form.value?.projectName || form.value?.voucherNo || '未命名样本'}`,
)
const checks = computed(() => form.value ? evaluateContractCostEvidence(form.value) : [])
const hasProblem = computed(() => checks.value.some((item) => item.status !== 'ok'))
const statusIcon: Record<ContractCostCheckStatus, string> = {
  ok: '✓',
  missing: '!',
  mismatch: '✕',
}
const canOcr = computed(() => !!props.wpId && !props.readonly)
const { ocrLoadingId, uploadAndMerge } = useF2SpecialContractOcr(
  computed(() => props.wpId || '') as Ref<string>,
)
const {
  aiAvailable,
  loading: aiLoading,
  generateAndConfirm,
} = useF2SpecialAiGenerate(computed(() => props.wpId || '') as Ref<string>)

async function runIssueAi(): Promise<void> {
  if (!form.value) return
  const row = form.value
  const context = {
    sheet: 'F2-56',
    projectName: row.projectName,
    accountDetail: row.accountDetail,
    voucherNo: row.voucherNo,
    businessContent: row.businessContent,
    voucherAmount: row.voucherAmount,
    contractDateNo: row.contractDateNo,
    contractTerms: row.contractTerms,
    receiptProductName: row.receiptProductName,
    receiptAmount: row.receiptAmount,
    logisticsDateNo: row.logisticsDateNo,
    logisticsProvider: row.logisticsProvider,
    allocationMonth: row.allocMonth,
    allocationAmount: row.allocAmount,
    allocationBasis: row.allocBasis,
    isAbnormal: row.isAbnormal,
    evidenceChecks: checks.value.map((item) => ({
      document: item.label,
      status: item.status,
      detail: item.detail,
    })),
  }
  const text = await generateAndConfirm(
    'contract-check-issue',
    row.issueDesc || '',
    context,
    'AI 生成 · 本笔异常说明',
  )
  if (text && form.value) form.value.issueDesc = text
}

function isOcrLoading(documentType: F2SpeDocumentType): boolean {
  return ocrLoadingId.value === `${form.value?.id}:${documentType}`
}

function runOcr(file: File | undefined, documentType: F2SpeDocumentType): void {
  if (!file || !form.value) return
  void uploadAndMerge(form.value.id, file, (_id, patch) => {
    if (form.value) Object.assign(form.value, patch)
  }, documentType)
}

function save(): void {
  if (!form.value) return
  emit('save', { ...form.value })
  emit('update:modelValue', false)
}
</script>

<style scoped>
.check-dialog-body { display: grid; grid-template-columns: minmax(0, 1fr) 310px; gap: 14px; height: 66vh; overflow: hidden; }
.document-groups { overflow-y: auto; padding-right: 4px; display: flex; flex-direction: column; gap: 10px; }
.check-side { display: flex; flex-direction: column; gap: 10px; overflow-y: auto; padding-right: 2px; }
/* 固定高度 + flex 列布局下，子卡片默认 flex-shrink:1 会被压扁重叠，必须禁止收缩 */
.document-groups > .el-card,
.check-side > .el-card { flex-shrink: 0; }
.issue-label { display: flex; align-items: center; justify-content: space-between; }
.side-save { width: 100%; margin-top: 4px; }
.document-card :deep(.el-card__header) { display: flex; align-items: center; justify-content: space-between; padding: 9px 12px; font-weight: 600; }
.document-card :deep(.el-card__body) { padding: 10px 12px; }
.field-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 9px 12px; }
label { display: flex; flex-direction: column; gap: 4px; margin-bottom: 9px; font-size: 12px; color: var(--el-text-color-secondary); }
.field-grid label { margin-bottom: 0; }
.field-grid .full { grid-column: 1 / -1; }
.field-grid :deep(.el-input-number), .check-side :deep(.el-select) { width: 100%; }
.side-header { display: flex; align-items: center; justify-content: space-between; }
.check-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.check-list li { display: flex; gap: 8px; padding: 8px; border-radius: 4px; background: #f5f7fa; }
.check-list strong, .check-list small { display: block; }
.check-list small { margin-top: 2px; color: #909399; line-height: 1.35; }
.check-icon { width: 18px; font-weight: 700; text-align: center; }
.status-ok .check-icon { color: #67c23a; }
.status-missing .check-icon { color: #e6a23c; }
.status-mismatch .check-icon { color: #f56c6c; }
@media (max-width: 1000px) {
  .check-dialog-body { grid-template-columns: 1fr; height: auto; max-height: 66vh; overflow-y: auto; }
  .document-groups, .check-side { overflow: visible; }
}
</style>
