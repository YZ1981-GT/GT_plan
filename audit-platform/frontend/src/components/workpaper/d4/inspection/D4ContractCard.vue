<script setup lang="ts">
/**
 * D4ContractCard — 单份合同检查卡片
 *
 * 纵向展示20+1字段，分5组（基础/交付/条款/签署/收入确认）
 * 顶部附件上传区 + OCR状态
 */
import { computed } from 'vue'
import { FIELD_GROUPS, type ContractInspectionItem } from '../../composables/useD4ContractInspection'

const props = defineProps<{
  item: ContractInspectionItem
  isReadonly: boolean
  ocrLoading: boolean
}>()

const emit = defineEmits<{
  (e: 'update', field: keyof ContractInspectionItem, value: any): void
  (e: 'upload', file: File): void
  (e: 'remove-attachment'): void
}>()

function onFieldUpdate(key: string, val: any) {
  emit('update', key as keyof ContractInspectionItem, val)
}

function handleUpload(file: any): boolean {
  emit('upload', file.raw || file)
  return false
}

const ocrBadge = computed(() => {
  switch (props.item.ocrStatus) {
    case 'processing': return { text: '识别中...', type: 'warning' as const }
    case 'done': return { text: 'OCR已填充', type: 'success' as const }
    case 'failed': return { text: '识别失败', type: 'danger' as const }
    default: return null
  }
})

const filledCount = computed(() => {
  let count = 0
  const item = props.item
  if (item.contractNo) count++
  if (item.counterparty) count++
  if (item.signDate) count++
  if (item.serviceContent) count++
  if (item.contractAmount > 0) count++
  if (item.deliveryTime) count++
  if (item.deliveryMethod) count++
  if (item.settlementMethod) count++
  if (item.settlementTime) count++
  if (item.warrantyClause) count++
  if (item.returnClause) count++
  if (item.breachClause) count++
  if (item.specialTerms) count++
  if (item.isSigned) count++
  if (item.isSealed) count++
  if (item.recognitionMethod) count++
  if (item.acceptanceClause) count++
  if (item.recognitionTime) count++
  if (item.controlTransferDoc) count++
  if (item.specialTransaction) count++
  if (item.conclusion) count++
  return count
})
</script>

<template>
  <div class="contract-card">
    <!-- 附件上传区 -->
    <div class="upload-zone">
      <div v-if="item.attachmentName" class="uploaded-file">
        <el-icon><svg viewBox="0 0 1024 1024" width="16" height="16"><path fill="currentColor" d="M160 832h704a32 32 0 1 1 0 64H160a32 32 0 1 1 0-64zm384-253.696 236.288-236.352 45.248 45.248L512 700.8 198.464 387.2l45.248-45.248L480 578.304V128h64v450.304z"/></svg></el-icon>
        <span class="file-name">{{ item.attachmentName }}</span>
        <el-tag v-if="ocrBadge" :type="ocrBadge.type" size="small">{{ ocrBadge.text }}</el-tag>
        <el-button v-if="!isReadonly" type="danger" size="small" link @click="$emit('remove-attachment')">移除</el-button>
      </div>
      <el-upload
        v-else
        :disabled="isReadonly || ocrLoading"
        :show-file-list="false"
        :auto-upload="false"
        accept=".pdf,.png,.jpg,.jpeg"
        drag
        @change="handleUpload"
      >
        <div class="upload-content">
          <el-icon v-if="ocrLoading" class="is-loading"><svg viewBox="0 0 1024 1024" width="20" height="20"><path fill="currentColor" d="M512 64a32 32 0 0 1 32 32v192a32 32 0 0 1-64 0V96a32 32 0 0 1 32-32zm0 640a32 32 0 0 1 32 32v192a32 32 0 1 1-64 0V736a32 32 0 0 1 32-32z"/></svg></el-icon>
          <el-icon v-else><svg viewBox="0 0 1024 1024" width="20" height="20"><path fill="currentColor" d="M544 864V672h128L512 480 352 672h128v192H320V672H160l352-352 352 352H704v192H544z"/></svg></el-icon>
          <span class="upload-text">{{ ocrLoading ? '正在OCR识别...' : '上传合同附件（PDF/图片），自动OCR提取信息' }}</span>
        </div>
      </el-upload>
    </div>

    <!-- 填写进度 -->
    <div class="progress-bar">
      <el-progress :percentage="Math.round(filledCount / 21 * 100)" :stroke-width="4" :show-text="false"
        :color="filledCount === 21 ? '#67c23a' : undefined" />
      <span class="progress-text">已填 {{ filledCount }}/21 项</span>
    </div>

    <!-- 字段分组 -->
    <div v-for="group in FIELD_GROUPS" :key="group.label" class="field-group">
      <div class="group-label">{{ group.label }}</div>
      <div v-for="field in group.fields" :key="field.key" class="field-row">
        <label class="field-label">{{ field.label }}</label>
        <div class="field-input">
          <!-- 文本输入 -->
          <el-input
            v-if="field.type === 'text'"
            :model-value="(item as any)[field.key]"
            :disabled="isReadonly"
            size="small"
            :placeholder="`请输入${field.label}`"
            @input="(v: string) => onFieldUpdate(field.key, v)"
          />
          <!-- 日期 -->
          <el-date-picker
            v-else-if="field.type === 'date'"
            :model-value="(item as any)[field.key]"
            :disabled="isReadonly"
            type="date"
            size="small"
            value-format="YYYY-MM-DD"
            placeholder="选择日期"
            style="width: 100%"
            @update:model-value="(v: string) => onFieldUpdate(field.key, v)"
          />
          <!-- 数字 -->
          <el-input-number
            v-else-if="field.type === 'number'"
            :model-value="(item as any)[field.key]"
            :disabled="isReadonly"
            :controls="false"
            size="small"
            :precision="2"
            :min="0"
            style="width: 100%"
            @update:model-value="(v: number) => onFieldUpdate(field.key, v)"
          />
          <!-- 多行文本 -->
          <el-input
            v-else-if="field.type === 'textarea'"
            type="textarea"
            :rows="2"
            :model-value="(item as any)[field.key]"
            :disabled="isReadonly"
            :placeholder="`请输入${field.label}`"
            @input="(v: string) => onFieldUpdate(field.key, v)"
          />
          <!-- Y/N/NA 选择 -->
          <el-radio-group
            v-else-if="field.type === 'radio'"
            :model-value="(item as any)[field.key]"
            :disabled="isReadonly"
            size="small"
            @update:model-value="(v: string) => onFieldUpdate(field.key, v)"
          >
            <el-radio-button value="Y">是</el-radio-button>
            <el-radio-button value="N">否</el-radio-button>
            <el-radio-button value="NA">N/A</el-radio-button>
          </el-radio-group>
          <!-- 时段法/时点法 -->
          <el-radio-group
            v-else-if="field.type === 'method'"
            :model-value="(item as any)[field.key]"
            :disabled="isReadonly"
            size="small"
            @update:model-value="(v: string) => onFieldUpdate(field.key, v)"
          >
            <el-radio-button value="时点法">时点法</el-radio-button>
            <el-radio-button value="时段法">时段法</el-radio-button>
          </el-radio-group>
        </div>
      </div>
    </div>

    <!-- 结论 -->
    <div class="field-group conclusion-group">
      <div class="group-label">结论</div>
      <div class="field-row">
        <label class="field-label">合同条款是否符合行业惯例，不同期间和客户是否保持一致</label>
        <div class="field-input">
          <el-radio-group
            :model-value="item.conclusion"
            :disabled="isReadonly"
            size="small"
            @update:model-value="(v: string) => onFieldUpdate('conclusion', v)"
          >
            <el-radio-button value="Y">合规</el-radio-button>
            <el-radio-button value="N">存在问题</el-radio-button>
            <el-radio-button value="NA">不适用</el-radio-button>
          </el-radio-group>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.contract-card { padding: 12px 0; }

.upload-zone {
  margin-bottom: 14px;
  border: 1px dashed #dcdfe6;
  border-radius: 8px;
  padding: 12px;
  background: #fafbfc;
}
.upload-zone :deep(.el-upload-dragger) {
  padding: 12px;
  border: none;
  background: transparent;
}
.upload-content {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #909399;
  font-size: 13px;
}
.uploaded-file {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.file-name {
  color: #303133;
  font-weight: 500;
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.progress-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}
.progress-bar :deep(.el-progress) { flex: 1; }
.progress-text { font-size: 12px; color: #909399; white-space: nowrap; }

.field-group {
  margin-bottom: 16px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 12px;
}
.group-label {
  font-size: 13px;
  font-weight: 600;
  color: #7c5cff;
  margin-bottom: 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid #f0ecff;
}
.field-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 10px;
}
.field-row:last-child { margin-bottom: 0; }
.field-label {
  width: 200px;
  flex-shrink: 0;
  font-size: 13px;
  color: #606266;
  line-height: 32px;
}
.field-input { flex: 1; min-width: 0; }

.conclusion-group {
  border-color: #e6a23c;
}
.conclusion-group .group-label {
  color: #e6a23c;
  border-bottom-color: #faecd8;
}
</style>
