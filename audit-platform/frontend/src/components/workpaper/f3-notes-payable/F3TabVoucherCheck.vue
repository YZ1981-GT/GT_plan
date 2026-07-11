<script setup lang="ts">
/** F3TabVoucherCheck — F3-7 借方/贷方检查 | Task 6.5, 9.3, 14.5 */
import { computed, toRef, inject, type Ref } from 'vue'
import { useF3VoucherCheck } from '../composables/useF3VoucherCheck'
import { useF3AiGenerate } from '../composables/useF3AiGenerate'
import GtVoucherSamplingEngine from '../voucher-sampling/GtVoucherSamplingEngine.vue'
import type { SampledVoucher, FillMode, Phase } from '../composables/useSamplingAlgorithms'
import F3ImportExportToolbar from './F3ImportExportToolbar.vue'
import F3VoucherCheckTable from './F3VoucherCheckTable.vue'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  year?: number
}>()

const reloadWorkpaperData = inject<(() => void) | null>('reloadWorkpaperData', null)
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)
function onImported() { reloadWorkpaperData?.() }

function fmt(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const {
  creditRows, debitRows, creditTotal, debitTotal, creditAbnormal, debitAbnormal,
  auditConclusion, addRow, removeRow, updateCell, applySamplingResults,
} = useF3VoucherCheck({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF3AiGenerate(toRef(props, 'wpId') as Ref<string>)

async function generateAiConclusion(side: 'credit' | 'debit') {
  if (props.isReadonly) return
  const section = side === 'credit' ? 'credit-check-conclusion' : 'debit-check-conclusion'
  const text = await generateAndConfirm(
    section,
    auditConclusion.value,
    {
      side: side === 'credit' ? '贷方(增加)' : '借方(减少)',
      sampleCount: side === 'credit' ? creditRows.value.length : debitRows.value.length,
      totalAmount: side === 'credit' ? creditTotal.value : debitTotal.value,
      abnormalCount: side === 'credit' ? creditAbnormal.value : debitAbnormal.value,
    },
    side === 'credit' ? 'AI 生成 · 贷方检查结论' : 'AI 生成 · 借方检查结论',
  )
  if (text) auditConclusion.value = text
}

const auditYear = computed(() => props.year ?? new Date().getFullYear() - 1)
const currentPhase = computed<Phase>(() => 'final')

function handleSamplingFilled(payload: { samples: SampledVoucher[]; phase: Phase; fillMode: FillMode }): void {
  applySamplingResults(payload.samples, payload.fillMode)
}

function onUpdateCell(side: 'credit' | 'debit', rowId: string, field: string, value: unknown): void {
  updateCell(side, rowId, field, value)
}
</script>

<template>
  <div class="f3-tab-voucher">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 应付票据（科目2201）借贷双向抽凭检查：贷方区（本期增加，开票承兑）与借方区（本期减少，到期兑付/背书转让）独立检查。</p>
        <p>2. 使用下方"自动抽凭"引擎按科目2201抽取样本，样本按借贷方向自动分配填入对应区块；超过 50 行自动启用固定表头滚动。</p>
        <p>3. 核对凭证与票据要素（出票人、面值、到期日）一致性，关注无真实交易背景的融资性票据、关联方票据。</p>
        <p>4. 检查到期未兑付票据的后续处理，异常凭证在审计结论中说明并考虑追加程序。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：通过借贷双向抽凭，验证应付票据增减变动真实、完整、准确，票据具有真实交易背景。"
      class="objective-alert"
    />

    <el-collapse class="sampling-engine-collapse">
      <el-collapse-item title="自动抽凭（科目 2201 应付票据）" name="auto-sampling">
        <GtVoucherSamplingEngine
          account-code="2201"
          :phase="currentPhase"
          default-method="random"
          :workpaper-id="wpId"
          :project-id="projectId"
          :year="auditYear"
          @filled="handleSamplingFilled"
        />
      </el-collapse-item>
    </el-collapse>

    <h4 class="block-title">贷方检查区（增加）</h4>
    <div class="block-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow('credit')">+ 添加行</el-button>
      </div>
      <div class="toolbar-right">
        <F3ImportExportToolbar :wp-id="wpId" :project-id="projectId" sheet="F3-7-credit" :disabled="isReadonly" @imported="onImported" />
        <el-tag size="small" type="info">共 {{ creditRows.length }} 行</el-tag>
      </div>
    </div>
    <F3VoucherCheckTable
      side="credit"
      :rows="creditRows"
      :is-readonly="isReadonly"
      @update-cell="(id, f, v) => onUpdateCell('credit', id, f, v)"
      @remove-row="(id) => removeRow('credit', id)"
    />
    <div class="subtotal">
      贷方小计 {{ fmt(creditTotal) }} |
      <el-tag v-if="creditAbnormal > 0" type="danger" size="small">异常 {{ creditAbnormal }} 笔</el-tag>
      <el-tag v-else type="success" size="small">无异常</el-tag>
    </div>

    <h4 class="block-title">借方检查区（减少）</h4>
    <div class="block-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow('debit')">+ 添加行</el-button>
      </div>
      <div class="toolbar-right">
        <F3ImportExportToolbar :wp-id="wpId" :project-id="projectId" sheet="F3-7-debit" :disabled="isReadonly" @imported="onImported" />
        <el-tag size="small" type="info">共 {{ debitRows.length }} 行</el-tag>
      </div>
    </div>
    <F3VoucherCheckTable
      side="debit"
      :rows="debitRows"
      :is-readonly="isReadonly"
      @update-cell="(id, f, v) => onUpdateCell('debit', id, f, v)"
      @remove-row="(id) => removeRow('debit', id)"
    />
    <div class="subtotal">
      借方小计 {{ fmt(debitTotal) }} |
      <el-tag v-if="debitAbnormal > 0" type="danger" size="small">异常 {{ debitAbnormal }} 笔</el-tag>
      <el-tag v-else type="success" size="small">无异常</el-tag>
    </div>

    <!-- 审计意见区（卡片式） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计结论</span>
          <div class="opinion-actions">
            <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="generateAiConclusion('credit')">🤖 AI贷方</el-button>
            <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="generateAiConclusion('debit')">🤖 AI借方</el-button>
            <el-button size="small" @click="openReviewDialog?.('F3-7-conclusion')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly" placeholder="请输入借贷双向抽凭检查审计结论..." />
    </el-card>
  </div>
</template>

<style scoped>
.f3-tab-voucher {
  padding: 12px;
}
.f3-tab-voucher :deep(.el-table) {
  --el-table-font-size: 13px;
  font-size: 13px;
}
.f3-tab-voucher :deep(.el-table .cell) {
  font-size: 13px !important;
}
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}
.guidance-content p {
  margin: 2px 0;
}
.objective-alert {
  margin-bottom: 12px;
}
.sampling-engine-collapse {
  margin-bottom: 12px;
}
.block-title {
  margin: 12px 0 8px;
  font-size: 14px;
  color: #303133;
}
.block-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.subtotal {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  font-weight: 600;
  margin: 4px 0 12px;
}
.opinion-card {
  margin-top: 16px;
  border-radius: 8px;
}
.opinion-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.opinion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.opinion-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.opinion-actions {
  display: flex;
  gap: 6px;
}
</style>
