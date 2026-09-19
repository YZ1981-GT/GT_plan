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

        <!-- 证据区：各外部单据独立字段 + 📎上传OCR -->
        <div class="jvc-evidence">
          <div class="jvc-ev-title">外部单据核对（每份单据有独立字段，📎 上传自动 OCR 识别回填）</div>

          <!-- 贷方：职工薪酬计算表 -->
          <div v-if="direction === 'credit'" class="jvc-doc">
            <div class="jvc-doc-head">
              <span class="jvc-doc-name">职工薪酬计算表</span>
              <el-upload v-if="!isReadonly" :show-file-list="false" :auto-upload="false" :on-change="(f: any) => onFilePick(f, 'calc')" accept=".pdf,.png,.jpg,.jpeg,.tiff,.bmp">
                <el-button size="small" :loading="ocrLoadingId === row.id" text bg>📎 {{ row.attachments?.calc ? '已传' : '上传' }}</el-button>
              </el-upload>
              <el-tag v-if="row.attachments?.calc" size="small" type="success" effect="plain" class="jvc-ev-tag">{{ row.attachments.calc }}</el-tag>
            </div>
            <div class="jvc-doc-fields">
              <div class="jvc-df"><label>月份</label><el-input v-model="ev.calc.month" :disabled="isReadonly" size="small" placeholder="如2025-01" @change="emitChange" /></div>
              <div class="jvc-df"><label>金额</label><el-input-number v-model="ev.calc.amount" :controls="false" :disabled="isReadonly" size="small" class="jvc-num" @change="emitChange" /></div>
              <div class="jvc-df"><label>是否经过恰当审批</label>
                <el-select v-model="ev.calc.approved" :disabled="isReadonly" size="small" placeholder="—" @change="emitChange">
                  <el-option label="是" value="是" /><el-option label="否" value="否" /><el-option label="不适用" value="不适用" />
                </el-select>
              </div>
            </div>
          </div>

          <!-- 借方/期后：付款审批单 + 银行回单 -->
          <template v-else>
            <div class="jvc-doc">
              <div class="jvc-doc-head">
                <span class="jvc-doc-name">付款审批单</span>
                <el-upload v-if="!isReadonly" :show-file-list="false" :auto-upload="false" :on-change="(f: any) => onFilePick(f, 'approval')" accept=".pdf,.png,.jpg,.jpeg,.tiff,.bmp">
                  <el-button size="small" :loading="ocrLoadingId === row.id" text bg>📎 {{ row.attachments?.approval ? '已传' : '上传' }}</el-button>
                </el-upload>
                <el-tag v-if="row.attachments?.approval" size="small" type="success" effect="plain" class="jvc-ev-tag">{{ row.attachments.approval }}</el-tag>
              </div>
              <div class="jvc-doc-fields">
                <div class="jvc-df"><label>日期/编号</label><el-input v-model="ev.approval.dateNo" :disabled="isReadonly" size="small" placeholder="审批单日期/编号" @change="emitChange" /></div>
                <div class="jvc-df"><label>是否经过恰当审批</label>
                  <el-select v-model="ev.approval.approved" :disabled="isReadonly" size="small" placeholder="—" @change="emitChange">
                    <el-option label="是" value="是" /><el-option label="否" value="否" /><el-option label="不适用" value="不适用" />
                  </el-select>
                </div>
              </div>
            </div>
            <div class="jvc-doc">
              <div class="jvc-doc-head">
                <span class="jvc-doc-name">银行回单</span>
                <el-upload v-if="!isReadonly" :show-file-list="false" :auto-upload="false" :on-change="(f: any) => onFilePick(f, 'bank')" accept=".pdf,.png,.jpg,.jpeg,.tiff,.bmp">
                  <el-button size="small" :loading="ocrLoadingId === row.id" text bg>📎 {{ row.attachments?.bank ? '已传' : '上传' }}</el-button>
                </el-upload>
                <el-tag v-if="row.attachments?.bank" size="small" type="success" effect="plain" class="jvc-ev-tag">{{ row.attachments.bank }}</el-tag>
              </div>
              <div class="jvc-doc-fields">
                <div class="jvc-df"><label>日期</label><el-input v-model="ev.bank.date" :disabled="isReadonly" size="small" placeholder="YYYY-MM-DD" @change="emitChange" /></div>
                <div class="jvc-df"><label>摘要/说明</label><el-input v-model="ev.bank.summary" :disabled="isReadonly" size="small" @change="emitChange" /></div>
                <div class="jvc-df"><label>金额</label><el-input-number v-model="ev.bank.amount" :controls="false" :disabled="isReadonly" size="small" class="jvc-num" @change="emitChange" /></div>
              </div>
            </div>
          </template>
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

// row 上会有 useK1VoucherCheck 之外的扩展字段（staffCount/approver/sampleSource/attachments/evidence）
interface J1Evidence {
  calc: { month: string; amount: number; approved: string }        // 职工薪酬计算表
  approval: { dateNo: string; approved: string }                    // 付款审批单
  bank: { date: string; summary: string; amount: number }           // 银行回单
}
type J1Row = K1VoucherRow & {
  staffCount?: number
  approver?: string
  sampleSource?: string
  attachments?: Record<string, string>
  evidence?: J1Evidence
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

// 惰性初始化各外部单据的独立字段（存于 row.evidence，随 ...r 展开序列化持久化）
function ensureEvidence(): void {
  if (!props.row.evidence) props.row.evidence = {} as J1Evidence
  const e = props.row.evidence
  if (!e.calc) e.calc = { month: '', amount: 0, approved: '' }
  if (!e.approval) e.approval = { dateNo: '', approved: '' }
  if (!e.bank) e.bank = { date: '', summary: '', amount: 0 }
}
ensureEvidence()
const ev = computed<J1Evidence>(() => props.row.evidence as J1Evidence)

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
.jvc-doc { background: #fff; border: 1px solid #e5eaf0; border-radius: 5px; padding: 8px 10px; margin-bottom: 8px; }
.jvc-doc:last-child { margin-bottom: 0; }
.jvc-doc-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.jvc-doc-name { font-size: 12px; font-weight: 600; color: #334155; }
.jvc-doc-fields { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px 12px; }
.jvc-df { display: flex; flex-direction: column; gap: 3px; }
.jvc-df label { font-size: 12px; color: var(--el-text-color-secondary); }
.jvc-ev-tag { max-width: 140px; overflow: hidden; text-overflow: ellipsis; }
.jvc-foot { margin-top: 12px; display: flex; align-items: center; gap: 14px; }
.jvc-abn { font-size: 12px; color: var(--el-text-color-secondary); display: flex; align-items: center; gap: 6px; }
.jvc-remark { flex: 1; }
</style>
