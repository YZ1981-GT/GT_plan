<script setup lang="ts">
/**
 * D2VcCardView — 凭证检查表卡片视图
 *
 * Task: 7.3
 * Requirements: 3.3, 4.5
 *
 * 每笔凭证一张 el-card：
 * - Header: 客户名称 + 凭证编号 (right-aligned)
 * - Body: 凭证日期 | 借方金额 | 贷方金额
 * - Progress bar: 5项核对完成率
 * - Tags: 异常(red) / 来源(info)
 * - Attachment: 缩略图预览
 * - Expandable: 点击展开编辑详情
 */
import { ref, computed, inject } from 'vue'
import type { VoucherCheckRow } from '../composables/useD2VoucherCheckEnhanced'

const props = defineProps<{
  rows: VoucherCheckRow[]
  isReadonly: boolean
  wpId: string
  projectId: string
}>()

const emit = defineEmits<{
  (e: 'update-row', rowId: string, field: keyof VoucherCheckRow, value: any): void
}>()

// ─── Display Prefs ───────────────────────────────────────────────────────────
const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) => (v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })),
})

// ─── Expanded State ──────────────────────────────────────────────────────────
const expandedRowIds = ref<Set<string>>(new Set())

function toggleExpand(rowId: string): void {
  if (expandedRowIds.value.has(rowId)) {
    expandedRowIds.value.delete(rowId)
  } else {
    expandedRowIds.value.add(rowId)
  }
  // Trigger reactivity
  expandedRowIds.value = new Set(expandedRowIds.value)
}

function isExpanded(rowId: string): boolean {
  return expandedRowIds.value.has(rowId)
}

// ─── Check Completion ────────────────────────────────────────────────────────
function getCheckCompletion(row: VoucherCheckRow): number {
  const checks = [row.check1, row.check2, row.check3, row.check4, row.check5]
  const completed = checks.filter(c => c && c.trim()).length
  return (completed / 5) * 100
}

function getCheckCompletedCount(row: VoucherCheckRow): number {
  const checks = [row.check1, row.check2, row.check3, row.check4, row.check5]
  return checks.filter(c => c && c.trim()).length
}

function progressColor(percentage: number): string {
  if (percentage >= 100) return '#67c23a'
  if (percentage >= 60) return '#409eff'
  if (percentage >= 20) return '#e6a23c'
  return '#909399'
}

// ─── Field Update ────────────────────────────────────────────────────────────
function onFieldChange(rowId: string, field: keyof VoucherCheckRow, value: any): void {
  if (props.isReadonly) return
  emit('update-row', rowId, field, value)
}

// ─── Abnormal Options ────────────────────────────────────────────────────────
const abnormalOptions = [
  '金额异常',
  '跨期疑点',
  '对方科目异常',
  '无支持性文件',
  '关联方交易',
  '其他异常',
]

// ─── Edit Fields Definition (17 fields) ──────────────────────────────────────
const editFields: { field: keyof VoucherCheckRow; label: string; type: 'text' | 'number' | 'date' | 'select' | 'textarea' }[] = [
  { field: 'customerName', label: '客户名称', type: 'text' },
  { field: 'voucherDate', label: '凭证日期', type: 'date' },
  { field: 'voucherNo', label: '凭证编号', type: 'text' },
  { field: 'businessContent', label: '业务内容', type: 'textarea' },
  { field: 'counterpartAccount', label: '对方科目', type: 'text' },
  { field: 'counterpartDetail', label: '对方明细科目', type: 'text' },
  { field: 'debitAmount', label: '借方金额', type: 'number' },
  { field: 'creditAmount', label: '贷方金额', type: 'number' },
  { field: 'supportingDoc', label: '支持性文件', type: 'text' },
  { field: 'check1', label: '核对内容1：金额一致性', type: 'text' },
  { field: 'check2', label: '核对内容2：日期一致性', type: 'text' },
  { field: 'check3', label: '核对内容3：对方科目匹配', type: 'text' },
  { field: 'check4', label: '核对内容4：业务内容相符', type: 'text' },
  { field: 'check5', label: '核对内容5：附件完整性', type: 'text' },
  { field: 'indexRef', label: '索引号', type: 'text' },
  { field: 'isAbnormal', label: '是否异常', type: 'select' },
  { field: 'remark', label: '备注说明', type: 'textarea' },
]
</script>

<template>
  <div class="vc-card-view">
    <el-empty v-if="!rows.length" description="暂无凭证数据" :image-size="60">
      <template #description>
        <p class="empty-hint">请通过抽凭引擎添加凭证或手动新增行</p>
      </template>
    </el-empty>

    <div v-else class="card-grid">
      <div
        v-for="row in rows"
        :key="row.rowId"
        class="vc-card"
        :class="{ 'is-expanded': isExpanded(row.rowId), 'is-abnormal': !!row.isAbnormal }"
        @click="toggleExpand(row.rowId)"
      >
        <!-- Card Header -->
        <div class="card-header">
          <div class="card-customer" :title="row.customerName || '(未填写客户)'">
            {{ row.customerName || '(未填写客户)' }}
          </div>
          <span class="card-voucher-no">{{ row.voucherNo || '—' }}</span>
        </div>

        <!-- Card Body: Key Info -->
        <div class="card-body-top">
          <div class="body-item">
            <span class="body-label">日期</span>
            <span class="body-value">{{ row.voucherDate || '—' }}</span>
          </div>
          <div class="body-item amount-item">
            <span class="body-label">借方</span>
            <span class="body-value amount-text">{{ displayPrefs.fmtAmount(row.debitAmount) }}</span>
          </div>
          <div class="body-item amount-item">
            <span class="body-label">贷方</span>
            <span class="body-value amount-text">{{ displayPrefs.fmtAmount(row.creditAmount) }}</span>
          </div>
        </div>

        <!-- Check Progress -->
        <div class="card-progress">
          <div class="progress-header">
            <span class="progress-label">核对进度</span>
            <span class="progress-count">{{ getCheckCompletedCount(row) }}/5</span>
          </div>
          <el-progress
            :percentage="getCheckCompletion(row)"
            :stroke-width="6"
            :show-text="false"
            :color="progressColor(getCheckCompletion(row))"
          />
        </div>

        <!-- Tags -->
        <div class="card-tags">
          <el-tag v-if="row.isAbnormal" type="danger" size="small" effect="dark">
            异常：{{ row.isAbnormal }}
          </el-tag>
          <el-tag v-if="row.source" type="info" size="small" effect="plain">
            {{ row.source }}
          </el-tag>
        </div>

        <!-- Attachment Thumbnails -->
        <div v-if="row.attachments && row.attachments.length" class="card-attachments">
          <div class="att-label">附件 ({{ row.attachments.length }})</div>
          <div class="att-thumbs">
            <div
              v-for="att in row.attachments.slice(0, 3)"
              :key="att.fileId"
              class="att-thumb"
              :title="att.fileName"
            >
              <img
                v-if="att.thumbnailUrl"
                :src="att.thumbnailUrl"
                :alt="att.fileName"
                class="thumb-img"
              />
              <div v-else class="thumb-placeholder">
                <span class="thumb-icon">📄</span>
                <span class="thumb-name">{{ att.fileName?.slice(0, 6) || '附件' }}</span>
              </div>
              <el-tag
                v-if="att.ocrStatus === 'success'"
                size="small"
                type="success"
                class="ocr-badge"
              >OCR</el-tag>
            </div>
            <div v-if="row.attachments.length > 3" class="att-more">
              +{{ row.attachments.length - 3 }}
            </div>
          </div>
        </div>

        <!-- Expand Indicator -->
        <div class="card-expand-hint">
          <el-icon :class="{ rotated: isExpanded(row.rowId) }">
            <svg viewBox="0 0 1024 1024" width="14" height="14">
              <path d="M512 714.7L137.6 340.3c-12.5-12.5-12.5-32.8 0-45.3s32.8-12.5 45.3 0L512 624.1l329.1-329.1c12.5-12.5 32.8-12.5 45.3 0s12.5 32.8 0 45.3L512 714.7z" fill="currentColor" />
            </svg>
          </el-icon>
        </div>

        <!-- Expanded Detail (edit form) -->
        <transition name="detail-expand">
          <div
            v-if="isExpanded(row.rowId)"
            class="card-detail"
            @click.stop
          >
            <el-divider style="margin: 8px 0" />
            <el-form
              label-position="top"
              size="small"
              :disabled="isReadonly"
              class="detail-form"
            >
              <div class="detail-grid">
                <el-form-item
                  v-for="ef in editFields"
                  :key="ef.field"
                  :label="ef.label"
                  class="detail-field"
                  :class="{ 'full-width': ef.type === 'textarea' }"
                >
                  <!-- Date -->
                  <el-date-picker
                    v-if="ef.type === 'date'"
                    :model-value="(row as any)[ef.field]"
                    type="date"
                    value-format="YYYY-MM-DD"
                    placeholder="选择日期"
                    style="width: 100%"
                    @update:model-value="onFieldChange(row.rowId, ef.field, $event)"
                  />
                  <!-- Number -->
                  <el-input-number
                    v-else-if="ef.type === 'number'"
                    :model-value="(row as any)[ef.field]"
                    :precision="2"
                    :controls="false"
                    style="width: 100%"
                    @update:model-value="onFieldChange(row.rowId, ef.field, $event)"
                  />
                  <!-- Select (abnormal) -->
                  <el-select
                    v-else-if="ef.type === 'select'"
                    :model-value="(row as any)[ef.field]"
                    filterable
                    allow-create
                    clearable
                    placeholder="选择或输入异常类型"
                    style="width: 100%"
                    @update:model-value="onFieldChange(row.rowId, ef.field, $event)"
                  >
                    <el-option
                      v-for="opt in abnormalOptions"
                      :key="opt"
                      :label="opt"
                      :value="opt"
                    />
                  </el-select>
                  <!-- Textarea -->
                  <el-input
                    v-else-if="ef.type === 'textarea'"
                    type="textarea"
                    :autosize="{ minRows: 2, maxRows: 4 }"
                    :model-value="(row as any)[ef.field]"
                    :placeholder="`请输入${ef.label}`"
                    @update:model-value="onFieldChange(row.rowId, ef.field, $event)"
                  />
                  <!-- Text -->
                  <el-input
                    v-else
                    :model-value="(row as any)[ef.field]"
                    :placeholder="`请输入${ef.label}`"
                    @update:model-value="onFieldChange(row.rowId, ef.field, $event)"
                  />
                </el-form-item>
              </div>
            </el-form>
          </div>
        </transition>
      </div>
    </div>
  </div>
</template>

<style scoped>
.vc-card-view {
  min-height: 200px;
  font-size: 13px;
}
.empty-hint {
  color: #909399;
  font-size: 13px;
}

/* Grid layout: 2 columns on desktop */
.card-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}
@media (max-width: 860px) {
  .card-grid {
    grid-template-columns: 1fr;
  }
}

/* Card */
.vc-card {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 14px 16px;
  background: #fff;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
  transition: box-shadow 0.2s, border-color 0.2s;
  cursor: pointer;
}
.vc-card:hover {
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.08);
  border-color: #d9ecff;
}
.vc-card.is-expanded {
  border-color: #409eff;
  box-shadow: 0 4px 14px rgba(64, 158, 255, 0.12);
}
.vc-card.is-abnormal {
  border-left: 3px solid #f56c6c;
}

/* Header */
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.card-customer {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}
.card-voucher-no {
  font-size: 12px;
  color: #909399;
  white-space: nowrap;
  font-family: 'Courier New', monospace;
}

/* Body Top */
.card-body-top {
  display: flex;
  gap: 16px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.body-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.body-label {
  font-size: 11px;
  color: #909399;
}
.body-value {
  font-size: 13px;
  color: #606266;
}
.amount-text {
  font-weight: 600;
  color: #303133;
  text-align: right;
}
.amount-item {
  text-align: right;
}

/* Progress */
.card-progress {
  border-top: 1px dashed #ebeef5;
  padding-top: 8px;
  margin-bottom: 8px;
}
.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.progress-label {
  font-size: 12px;
  color: #909399;
}
.progress-count {
  font-size: 12px;
  font-weight: 600;
  color: #409eff;
}

/* Tags */
.card-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 6px;
  min-height: 22px;
}

/* Attachments */
.card-attachments {
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px dashed #ebeef5;
}
.att-label {
  font-size: 11px;
  color: #909399;
  margin-bottom: 4px;
}
.att-thumbs {
  display: flex;
  gap: 6px;
  align-items: center;
}
.att-thumb {
  width: 48px;
  height: 48px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  overflow: hidden;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}
.thumb-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.thumb-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}
.thumb-icon {
  font-size: 16px;
}
.thumb-name {
  font-size: 9px;
  color: #909399;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 42px;
}
.ocr-badge {
  position: absolute;
  top: 0;
  right: 0;
  font-size: 9px !important;
  padding: 0 2px !important;
  height: 14px !important;
  line-height: 14px !important;
  border-radius: 0 4px 0 4px;
}
.att-more {
  font-size: 12px;
  color: #909399;
  padding: 0 4px;
}

/* Expand indicator */
.card-expand-hint {
  text-align: center;
  margin-top: 6px;
  color: #c0c4cc;
  transition: color 0.2s;
}
.vc-card:hover .card-expand-hint {
  color: #409eff;
}
.card-expand-hint .el-icon {
  transition: transform 0.3s;
}
.card-expand-hint .rotated {
  transform: rotate(180deg);
}

/* Detail expand transition */
.detail-expand-enter-active,
.detail-expand-leave-active {
  transition: all 0.3s ease;
  overflow: hidden;
}
.detail-expand-enter-from,
.detail-expand-leave-to {
  opacity: 0;
  max-height: 0;
}
.detail-expand-enter-to,
.detail-expand-leave-from {
  opacity: 1;
  max-height: 800px;
}

/* Detail form */
.card-detail {
  cursor: default;
}
.detail-form {
  font-size: 13px;
}
.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px 12px;
}
.detail-field.full-width {
  grid-column: 1 / -1;
}
.detail-form :deep(.el-form-item) {
  margin-bottom: 8px;
}
.detail-form :deep(.el-form-item__label) {
  font-size: 12px;
  color: #909399;
  padding-bottom: 2px;
}
</style>
