<!--
  J1VoucherCard.vue — J1-8 单笔凭证检查卡片（可展开 + 证据区 + 📎OCR）

  一张卡片 = 一笔凭证。头部展示关键信息 + 核对进度；展开后：
    - 可编辑字段（日期/凭证号/薪酬项目/对方科目/金额/人数/审批人）
    - 核对内容勾选（5 项）
    - 证据区：薪酬计算表 / 付款审批单 / 银行回单，各支持 📎 上传 + OCR 识别回填
    - 异常标记 + 备注
-->
<template>
  <div class="jvc-card" :class="{ 'jvc-abnormal': row.abnormal }">
    <!-- 卡片头部 -->
    <div class="jvc-head" @click="expanded = !expanded">
      <el-icon class="jvc-caret" :class="{ open: expanded }"><ArrowRight /></el-icon>
      <span class="jvc-seq">#{{ seq }}</span>
      <span class="jvc-name">{{ row.debtorName || '（未填薪酬项目）' }}</span>
      <span class="jvc-voucher">{{ row.voucherNo || '凭证号—' }}</span>
      <span class="jvc-amount">{{ fmtAmt(amount) }}</span>
      <el-tag :type="checkedCount === 5 ? 'success' : checkedCount === 0 ? 'info' : 'warning'" size="small" effect="plain" class="jvc-progress">
        核对 {{ checkedCount }}/5
      </el-tag>
      <el-tag v-if="row.sampleSource" size="small" type="primary" effect="plain">{{ row.sampleSource }}</el-tag>
      <el-tag v-if="row.abnormal" size="small" type="danger" effect="dark">异常</el-tag>
      <span class="jvc-spacer" />
      <el-button v-if="!isReadonly" size="small" type="danger" link @click.stop="$emit('remove', row.id)">删除</el-button>
    </div>

    <!-- 展开内容 -->
    <el-collapse-transition>
      <div v-show="expanded" class="jvc-body">
        <!-- 基础字段 -->
        <div class="jvc-fields">
          <div class="jvc-field">
            <label>薪酬项目</label>
            <el-input v-model="row.debtorName" :disabled="isReadonly" size="small" placeholder="工资/社保/公积金/福利…" @change="emitChange" />
          </div>
          <div class="jvc-field">
            <label>日期</label>
            <el-input v-model="row.date" :disabled="isReadonly" size="small" placeholder="YYYY-MM-DD" @change="emitChange" />
          </div>
          <div class="jvc-field">
            <label>凭证编号</label>
            <el-input v-model="row.voucherNo" :disabled="isReadonly" size="small" @change="emitChange" />
          </div>
          <div class="jvc-field">
            <label>对方科目</label>
            <el-input v-model="row.offsetAccount" :disabled="isReadonly" size="small" placeholder="如 生产成本/管理费用" @change="emitChange" />
          </div>
          <div class="jvc-field">
            <label>{{ direction === 'credit' ? '贷方金额（计提）' : '借方金额（发放）' }}</label>
            <el-input-number v-if="direction === 'credit'" v-model="row.creditAmount" :controls="false" :disabled="isReadonly" size="small" class="jvc-num" @change="emitChange" />
            <el-input-number v-else v-model="row.debitAmount" :controls="false" :disabled="isReadonly" size="small" class="jvc-num" @change="emitChange" />
          </div>
          <div class="jvc-field">
            <label>人数</label>
            <el-input-number v-model="row.staffCount" :controls="false" :min="0" :disabled="isReadonly" size="small" class="jvc-num" @change="emitChange" />
          </div>
          <div class="jvc-field">
            <label>审批人</label>
            <el-input v-model="row.approver" :disabled="isReadonly" size="small" @change="emitChange" />
          </div>
          <div class="jvc-field jvc-field-wide">
            <label>业务内容/摘要</label>
            <el-input v-model="row.businessContent" :disabled="isReadonly" size="small" @change="emitChange" />
          </div>
        </div>

        <!-- 核对内容 -->
        <div class="jvc-checks">
          <label class="jvc-checks-label">核对内容</label>
          <el-checkbox-group :model-value="checkedValues" :disabled="isReadonly" @update:model-value="onChecksChange">
            <el-checkbox v-for="(lbl, i) in checkLabels" :key="i" :value="i">{{ i + 1 }}.{{ lbl }}</el-checkbox>
          </el-checkbox-group>
        </div>

        <!-- 证据区 -->
        <div class="jvc-evidence">
          <div class="jvc-ev-title">证据附件（上传后自动 OCR 识别回填）</div>
          <div class="jvc-ev-grid">
            <div v-for="ev in evidenceTypes" :key="ev.key" class="jvc-ev-item">
              <span class="jvc-ev-name">{{ ev.label }}</span>
              <el-upload
                v-if="!isReadonly"
                :show-file-list="false"
                :auto-upload="false"
                :on-change="(f: any) => onFilePick(f, ev.key)"
                accept=".pdf,.png,.jpg,.jpeg,.tiff,.bmp"
              >
                <el-button size="small" :loading="ocrLoadingId === row.id" text bg>📎 {{ row.attachments?.[ev.key] ? '已传' : '上传' }}</el-button>
              </el-upload>
              <el-tag v-if="row.attachments?.[ev.key]" size="small" type="success" effect="plain" class="jvc-ev-tag">{{ row.attachments[ev.key] }}</el-tag>
            </div>
          </div>
        </div>

        <!-- 异常 + 备注 -->
        <div class="jvc-foot">
          <span class="jvc-abn">
            异常标记
            <el-switch v-model="row.abnormal" :disabled="isReadonly" size="small" @change="emitChange" />
          </span>
          <el-input v-model="row.remark" :disabled="isReadonly" size="small" placeholder="异常说明/备注" class="jvc-remark" @change="emitChange" />
        </div>
      </div>
    </el-collapse-transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ArrowRight } from '@element-plus/icons-vue'
import type { K1VoucherRow } from '../../composables/useK1VoucherCheck'

// row 上会有 useK1VoucherCheck 之外的扩展字段（staffCount/approver/sampleSource/attachments）
type J1Row = K1VoucherRow & {
  staffCount?: number
  approver?: string
  sampleSource?: string
  attachments?: Record<string, string>
}

const props = defineProps<{
  row: J1Row
  seq: number
  direction: 'credit' | 'debit' | 'post'
  checkLabels: string[]
  isReadonly: boolean
  ocrLoadingId: string | null
  defaultExpanded?: boolean
}>()

const emit = defineEmits<{
  (e: 'change'): void
  (e: 'remove', id: string): void
  (e: 'upload', payload: { rowId: string; file: File; evidenceKey: string }): void
}>()

const expanded = ref(props.defaultExpanded ?? false)

const evidenceTypes = [
  { key: 'calc', label: '薪酬计算表' },
  { key: 'approval', label: '付款审批单' },
  { key: 'bank', label: '银行回单' },
]

const amount = computed(() => props.direction === 'credit' ? (props.row.creditAmount || 0) : (props.row.debitAmount || 0))
const checkedCount = computed(() => (props.row.checks || []).filter(Boolean).length)
const checkedValues = computed(() => (props.row.checks || []).map((c, i) => (c ? i : -1)).filter(i => i >= 0))

function onChecksChange(vals: any) {
  const arr = vals as number[]
  props.row.checks = Array.from({ length: 5 }, (_, i) => arr.includes(i))
  emit('change')
}

function onFilePick(uploadFile: any, evidenceKey: string) {
  const file: File | undefined = uploadFile?.raw
  if (!file) return
  if (!props.row.attachments) props.row.attachments = {}
  props.row.attachments[evidenceKey] = file.name
  emit('upload', { rowId: props.row.id, file, evidenceKey })
}

function emitChange() { emit('change') }

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.jvc-card { border: 1px solid var(--el-border-color-light); border-radius: 6px; margin-bottom: 8px; background: #fff; overflow: hidden; font-size: 13px; }
.jvc-card.jvc-abnormal { border-color: #fca5a5; }
.jvc-head { display: flex; align-items: center; gap: 8px; padding: 8px 12px; cursor: pointer; background: #fafbfc; user-select: none; }
.jvc-head:hover { background: #f0f4fa; }
.jvc-caret { transition: transform 0.2s; color: var(--el-text-color-secondary); }
.jvc-caret.open { transform: rotate(90deg); }
.jvc-seq { font-weight: 600; color: var(--el-text-color-secondary); font-size: 12px; }
.jvc-name { font-weight: 600; min-width: 100px; }
.jvc-voucher { color: var(--el-text-color-secondary); font-size: 12px; }
.jvc-amount { font-variant-numeric: tabular-nums; font-weight: 600; color: #1e40af; }
.jvc-progress { margin-left: 4px; }
.jvc-spacer { flex: 1; }
.jvc-body { padding: 12px 14px; border-top: 1px dashed var(--el-border-color-light); }
.jvc-fields { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px 14px; }
.jvc-field { display: flex; flex-direction: column; gap: 3px; }
.jvc-field-wide { grid-column: span 2; }
.jvc-field label { font-size: 12px; color: var(--el-text-color-secondary); }
.jvc-num { width: 100%; }
.jvc-checks { margin-top: 12px; display: flex; flex-direction: column; gap: 4px; }
.jvc-checks-label { font-size: 12px; color: var(--el-text-color-secondary); }
.jvc-checks :deep(.el-checkbox) { margin-right: 12px; font-size: 12px; }
.jvc-evidence { margin-top: 12px; padding: 10px 12px; background: #f8fafc; border-radius: 5px; border: 1px solid #eef2f7; }
.jvc-ev-title { font-size: 12px; color: #475569; margin-bottom: 8px; font-weight: 500; }
.jvc-ev-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.jvc-ev-item { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.jvc-ev-name { font-size: 12px; color: var(--el-text-color-regular); min-width: 72px; }
.jvc-ev-tag { max-width: 120px; overflow: hidden; text-overflow: ellipsis; }
.jvc-foot { margin-top: 12px; display: flex; align-items: center; gap: 14px; }
.jvc-abn { font-size: 12px; color: var(--el-text-color-secondary); display: flex; align-items: center; gap: 6px; }
.jvc-remark { flex: 1; }
</style>
