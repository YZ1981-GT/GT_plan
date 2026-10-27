<script setup lang="ts">
import WpAmountInput from '../shared/WpAmountInput.vue'
/**
 * D1MemoNoteCard — 单张票据备查簿卡片（纵向分组，便于宽表字段填写）
 */
import { computed } from 'vue'
import AttachmentEyeButton from '@/components/attachment/AttachmentEyeButton.vue'
import type { MemoRow } from '../composables/useD1MemoReconciliation'
import GtReviewDot from '../GtReviewDot.vue'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  row: MemoRow
  warnings: string[]
  isReadonly: boolean
  projectId: string
  noteTypeOptions: string[]
  statusOptions: string[]
  derecognizedOptions: string[]
  ynOptions: string[]
  ratingOptions: string[]
  relatedOptions: string[]
}>()

const emit = defineEmits<{
  (e: 'update', field: keyof MemoRow, value: string | number): void
  (e: 'remove'): void
  (e: 'upload-ocr', file: File): void
  (e: 'remove-attachment'): void
  (e: 'apply-ocr', mode: 'empty-only' | 'override-all'): void
}>()

// 状态取权威模板 K 列下拉值；本期背书 / 到期承兑 / 贴现按模板公式自动取票据金额
const statusHint = computed(() => {
  if (props.row.status === '贴现') return '联动：自动标记「审计日已贴现背书」，票据金额计入本期贴现'
  if (props.row.status === '背书') return '联动：自动标记「审计日已贴现背书」，票据金额计入本期背书'
  if (props.row.status === '到期承兑') return '票据金额计入本期到期承兑'
  return ''
})

/** 「金额变动」组：权威模板 Q~W 的行公式，只读 */
const DERIVED_AMOUNT_FIELDS: Array<{ key: keyof MemoRow; label: string }> = [
  { key: 'beginningBalance', label: '年初余额（自动）' },
  { key: 'currentReceived', label: '本期收到（自动）' },
  { key: 'currentEndorsed', label: '本期背书（自动）' },
  { key: 'currentMatured', label: '本期到期承兑（自动）' },
  { key: 'currentDiscounted', label: '本期贴现（自动）' },
  { key: 'endingBalance', label: '年末持有票据余额（自动）' },
  { key: 'unexpiredEndorsedDiscounted', label: '期末未到期背书或贴现金额（自动）' },
]

const ocrBadge = computed(() => {
  switch (props.row.ocrStatus) {
    case 'processing': return { text: '识别中...', type: 'warning' as const }
    case 'done': return { text: 'OCR已完成', type: 'success' as const }
    case 'failed': return { text: '识别失败', type: 'danger' as const }
    default: return null
  }
})

function handleUpload(file: any): boolean {
  emit('upload-ocr', file.raw || file)
  return false
}
</script>

<template>
  <div class="memo-card">
    <div class="memo-card-header">
      <div class="memo-card-title">
        <span class="note-no">{{ row.noteNumber || '（未填票据号）' }}</span>
        <el-tag size="small" effect="plain">{{ row.noteType }}</el-tag>
        <GtReviewDot row-prefix="D1-memo" :row-key="row.rowId" />
      </div>
      <el-button
        v-if="row.rowType === 'dynamic' && !isReadonly"
        type="danger"
        size="small"
        text
        @click="emit('remove')"
      >
        删除
      </el-button>
    </div>

    <el-alert
      v-if="warnings.length"
      type="warning"
      :closable="false"
      show-icon
      class="warn-alert"
      :title="warnings.join('；')"
    />

    <el-alert v-if="statusHint" type="info" :closable="false" class="hint-alert" :title="statusHint" />

    <div class="upload-zone">
      <div v-if="row.attachmentName" class="uploaded-file">
        <span class="file-name">{{ row.attachmentName }}</span>
        <AttachmentEyeButton
          v-if="row.attachmentId"
          :attachment-id="row.attachmentId"
          :file-name="row.attachmentName"
        />
        <el-tag v-if="ocrBadge" :type="ocrBadge.type" size="small">{{ ocrBadge.text }}</el-tag>
        <el-button v-if="!isReadonly" size="small" @click="emit('apply-ocr', 'empty-only')">回填空字段</el-button>
        <el-button v-if="!isReadonly" size="small" @click="emit('apply-ocr', 'override-all')">覆盖回填</el-button>
        <el-button v-if="!isReadonly" type="danger" size="small" text @click="emit('remove-attachment')">移除</el-button>
      </div>
      <el-upload
        v-else
        :disabled="isReadonly"
        :show-file-list="false"
        :auto-upload="false"
        accept=".pdf,.png,.jpg,.jpeg"
        drag
        @change="handleUpload"
      >
        <div class="upload-content">
          <span class="upload-text">上传票据附件（PDF/图片），OCR识别后可回填</span>
        </div>
      </el-upload>
    </div>

    <!-- 基本信息 -->
    <div class="field-group">
      <div class="group-title">基本信息</div>
      <el-form label-position="top" size="small">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="票据类型">
              <el-select
                :model-value="row.noteType"
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: string) => emit('update', 'noteType', v)"
              >
                <el-option v-for="o in noteTypeOptions" :key="o" :label="o" :value="o" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="票据号">
              <el-input
                :model-value="row.noteNumber"
                :disabled="isReadonly"
                @change="(v: string) => emit('update', 'noteNumber', v)"
              />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="收到日期">
              <el-date-picker
                :model-value="row.receivedDate"
                type="date"
                value-format="YYYY-MM-DD"
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: string) => emit('update', 'receivedDate', v || '')"
              />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="出票日">
              <el-date-picker
                :model-value="row.issueDate"
                type="date"
                value-format="YYYY-MM-DD"
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: string) => emit('update', 'issueDate', v || '')"
              />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="到期日">
              <el-date-picker
                :model-value="row.maturityDate"
                type="date"
                value-format="YYYY-MM-DD"
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: string) => emit('update', 'maturityDate', v || '')"
              />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="前手">
              <el-input
                :model-value="row.endorser"
                :disabled="isReadonly"
                @change="(v: string) => emit('update', 'endorser', v)"
              />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="出票人">
              <el-input
                :model-value="row.issuer"
                :disabled="isReadonly"
                @change="(v: string) => emit('update', 'issuer', v)"
              />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="承兑人">
              <el-input
                :model-value="row.acceptor"
                :disabled="isReadonly"
                placeholder="填写后联动信用评级"
                @change="(v: string) => emit('update', 'acceptor', v)"
              />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="金额">
              <WpAmountInput
                :model-value="row.amount"
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: number) => emit('update', 'amount', v || 0)"
              />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </div>

    <!-- 流转 -->
    <div class="field-group">
      <div class="group-title">流转</div>
      <el-form label-position="top" size="small">
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="状态">
              <el-select
                :model-value="row.status"
                clearable
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: string) => emit('update', 'status', v || '')"
              >
                <el-option v-for="o in statusOptions" :key="o" :label="o" :value="o" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="流转日">
              <el-date-picker
                :model-value="row.transferDate"
                type="date"
                value-format="YYYY-MM-DD"
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: string) => emit('update', 'transferDate', v || '')"
              />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="被背书人">
              <el-input
                :model-value="row.endorsee"
                :disabled="isReadonly"
                @change="(v: string) => emit('update', 'endorsee', v)"
              />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="贴现银行">
              <el-input
                :model-value="row.discountBank"
                :disabled="isReadonly"
                @change="(v: string) => emit('update', 'discountBank', v)"
              />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="贴现息">
              <el-input-number
                :model-value="row.discountInterest"
                :controls="false"
                :precision="2"
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: number) => emit('update', 'discountInterest', v || 0)"
              />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </div>

    <!-- 金额变动 -->
    <div class="field-group">
      <div class="group-title">金额变动 <span class="auto-tag">按收到日期、票据状态、到期日与流转日期自动计算</span></div>
      <el-form label-position="top" size="small">
        <el-row :gutter="12">
          <el-col v-for="f in DERIVED_AMOUNT_FIELDS" :key="f.key" :span="8">
            <el-form-item :label="f.label">
              <WpAmountInput
                :model-value="row[f.key] as number"
                disabled
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="是否质押">
              <el-select
                :model-value="row.isPledged"
                clearable
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: string) => emit('update', 'isPledged', v || '')"
              >
                <el-option v-for="o in ynOptions" :key="o" :label="o" :value="o" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="审计日已贴现背书">
              <el-select
                :model-value="row.isDiscountedEndorsed"
                clearable
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: string) => emit('update', 'isDiscountedEndorsed', v || '')"
              >
                <el-option v-for="o in ynOptions" :key="o" :label="o" :value="o" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </div>

    <!-- 审定 -->
    <div class="field-group">
      <div class="group-title">审定列报</div>
      <el-form label-position="top" size="small">
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="是否终止确认">
              <el-select
                :model-value="row.isDerecognized"
                clearable
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: string) => emit('update', 'isDerecognized', v || '')"
              >
                <el-option v-for="o in derecognizedOptions" :key="o" :label="o" :value="o" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="信用评级">
              <el-select
                :model-value="row.creditRating"
                clearable
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: string) => emit('update', 'creditRating', v || '')"
              >
                <el-option v-for="o in ratingOptions" :key="o" :label="o" :value="o" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="关联关系">
              <el-select
                :model-value="row.relatedParty"
                clearable
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: string) => emit('update', 'relatedParty', v || '')"
              >
                <el-option v-for="o in relatedOptions" :key="o" :label="o" :value="o" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="审定应收款项融资">
              <WpAmountInput
                :model-value="row.auditedFinancing"
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: number) => emit('update', 'auditedFinancing', v || 0)"
              />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="审定应收票据">
              <WpAmountInput
                :model-value="row.auditedNotes"
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: number) => emit('update', 'auditedNotes', v || 0)"
              />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="是否逾期">
              <el-select
                :model-value="row.isOverdue"
                clearable
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: string) => emit('update', 'isOverdue', v || '')"
              >
                <el-option v-for="o in ynOptions" :key="o" :label="o" :value="o" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="逾期转应收金额">
              <WpAmountInput
                :model-value="row.overdueTransferAmount"
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: number) => emit('update', 'overdueTransferAmount', v || 0)"
              />
            </el-form-item>
          </el-col>
          <el-col :span="16">
            <el-form-item label="备注">
              <el-input
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 4 }"
                :model-value="row.remarkText"
                :disabled="isReadonly"
                @input="(v: string) => emit('update', 'remarkText', v)"
              />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </div>

    <div class="cross-ref">
      <span class="cross-ref-label">下游勾稽</span>
      <GtIndexChip value="wp:D1-8" :context-project-id="projectId" />
      <GtIndexChip value="wp:D1-6" :context-project-id="projectId" />
      <GtIndexChip value="wp:D1-2" :context-project-id="projectId" />
    </div>
  </div>
</template>

<style scoped>
.memo-card { padding: 4px 0 12px; }
.memo-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.memo-card-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.note-no { font-size: 15px; font-weight: 600; color: #303133; }
.warn-alert, .hint-alert { margin-bottom: 12px; }
.upload-zone {
  margin-bottom: 12px;
  border: 1px dashed #dcdfe6;
  border-radius: 8px;
  padding: 10px;
  background: #fafbfc;
}
.upload-zone :deep(.el-upload-dragger) {
  border: none;
  background: transparent;
  padding: 8px;
}
.upload-content { font-size: 12px; color: #909399; }
.uploaded-file { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.file-name { color: #303133; font-weight: 500; }
.field-group {
  margin-bottom: 16px;
  padding: 12px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fafafa;
}
.group-title {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
  color: #303133;
  margin-bottom: 10px;
}
.auto-tag {
  font-size: 11px;
  font-weight: 400;
  color: #909399;
}
.cross-ref {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.cross-ref-label { font-size: 12px; color: #909399; }
</style>
