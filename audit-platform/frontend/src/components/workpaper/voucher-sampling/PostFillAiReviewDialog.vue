<template>
  <el-dialog
    :model-value="modelValue"
    :title="dialogTitle"
    width="640px"
    :close-on-click-modal="false"
    append-to-body
    destroy-on-close
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
    @closed="onClosed"
  >
    <!-- AI 不可用提示（不阻断已回写数据，R26.7） -->
    <el-alert
      v-if="!aiAvailable"
      type="warning"
      :closable="false"
      show-icon
      class="pfar-alert"
      title="AI 服务暂不可用"
      description="凭证已成功回写，不受影响。您可稍后重试 AI 复核，或直接在底稿审计说明中手工录入。"
    />

    <!-- 询问是否发起复核（R26.1/26.2） -->
    <template v-else-if="stage === 'prompt'">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="pfar-alert"
        :title="`已回写 ${rows.length} 条凭证，是否发起 AI 复核？`"
        :description="promptDesc"
      />
      <div class="pfar-summary">
        <span class="pfar-summary-label">回写凭证摘要：</span>
        <span class="pfar-summary-text">{{ voucherSummaryText }}</span>
      </div>
    </template>

    <!-- 复核进行中 -->
    <div v-else-if="stage === 'loading'" v-loading="true" class="pfar-loading">
      AI 正在基于回写凭证识别潜在异常与跨期问题……
    </div>

    <!-- 展示复核意见（R26.4）→ 确认前不定稿（R26.8） -->
    <template v-else-if="stage === 'result'">
      <el-card shadow="never" class="pfar-opinion-card">
        <template #header>
          <div class="pfar-opinion-header">
            <span class="pfar-opinion-title">🤖 AI 复核意见（供参考，需人工确认后方可填入）</span>
          </div>
        </template>
        <div class="pfar-opinion-body">{{ opinion }}</div>
      </el-card>
      <div class="pfar-confirm-hint">确认后将填入底稿审计说明；确认前不作为最终结论写入。</div>
    </template>

    <template #footer>
      <div class="pfar-footer">
        <template v-if="!aiAvailable">
          <el-button @click="close">知道了</el-button>
        </template>
        <template v-else-if="stage === 'prompt'">
          <el-button @click="close">暂不复核</el-button>
          <el-button type="primary" @click="startReview">发起 AI 复核</el-button>
        </template>
        <template v-else-if="stage === 'loading'">
          <el-button disabled>复核中…</el-button>
        </template>
        <template v-else-if="stage === 'result'">
          <el-button @click="close">取消（不写入）</el-button>
          <el-button type="primary" @click="applyOpinion">确认填入审计说明</el-button>
        </template>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * PostFillAiReviewDialog.vue — 回写后 AI 复核弹窗（检查表 + 截止共用）
 *
 * Spec: .kiro/specs/voucher-check-sampling-integration (Requirement 26)
 *
 * 抽凭/截止凭证回写完成 → 弹出「是否发起 AI 复核」→ Auditor 发起
 * → POST /api/workpapers/{wpId}/ai/generate-text（section=voucher-review/cutoff-review，
 *   context=回写凭证摘要，prompt=识别异常/跨期）→ 展示意见
 * → 确认填入审计说明（@applied）/ 取消不写入；AI 不可用提示且不阻断已回写数据；
 *   确认前不定稿。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

/** 回写凭证行（同时兼容抽凭 SampledVoucher 与截止 ExtractedVoucher 形态） */
export interface PostFillReviewRow {
  voucherNo?: string
  voucherDate?: string | null
  summary?: string | null
  debitAmount?: string | number | null
  creditAmount?: string | number | null
  counterpartAccount?: string | null
  /** 抽凭：布尔异常标识 */
  abnormal?: boolean
  /** 检查表：异常类型文本（如「跨期疑点」） */
  isAbnormal?: string
  /** 截止：跨期状态（cross_period / within / ...） */
  cutoffStatus?: string
  [key: string]: unknown
}

export type ReviewSection = 'voucher-review' | 'cutoff-review'

const props = withDefaults(defineProps<{
  modelValue: boolean
  wpId: string
  rows: PostFillReviewRow[]
  section: ReviewSection
  aiAvailable: boolean
}>(), {
  rows: () => [],
})

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'applied', text: string): void
}>()

type Stage = 'prompt' | 'loading' | 'result'
const stage = ref<Stage>('prompt')
const opinion = ref('')

/** 弹窗打开时重置到询问阶段 */
watch(
  () => props.modelValue,
  (visible) => {
    if (visible) {
      stage.value = 'prompt'
      opinion.value = ''
    }
  },
)

const isCutoff = computed(() => props.section === 'cutoff-review')

const dialogTitle = computed(() =>
  isCutoff.value ? '截止凭证回写后 AI 复核' : '抽凭回写后 AI 复核',
)

const promptDesc = computed(() =>
  isCutoff.value
    ? 'AI 将基于回写的截止凭证识别潜在跨期确认问题，给出复核意见供您确认。'
    : 'AI 将基于回写的抽样凭证识别潜在异常（金额异常、无原始凭证、对方科目异常、重复入账等），给出复核意见供您确认。',
)

/** 单行金额（借优先，其次贷），转为「元」文本 */
function rowAmountText(row: PostFillReviewRow): string {
  const raw = row.debitAmount ?? row.creditAmount
  const num = typeof raw === 'string' ? Number(raw) : (raw ?? 0)
  if (!num || Number.isNaN(num)) return '0.00 元'
  return `${num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} 元`
}

/** 是否跨期 / 异常行 */
function rowAnomalyText(row: PostFillReviewRow): string {
  if (row.isAbnormal) return `｜异常：${row.isAbnormal}`
  if (row.cutoffStatus && /cross|跨期/i.test(row.cutoffStatus)) return '｜跨期'
  if (row.abnormal) return '｜异常'
  return ''
}

/** 回写凭证摘要文本（展示用，最多前 8 条） */
const voucherSummaryText = computed(() => {
  if (!props.rows.length) return '（无凭证）'
  const parts = props.rows.slice(0, 8).map((r) => {
    const no = r.voucherNo || '（无凭证号）'
    const date = r.voucherDate || ''
    return `${no}${date ? ` ${date}` : ''} ${rowAmountText(r)}${rowAnomalyText(r)}`
  })
  const more = props.rows.length > 8 ? ` 等共 ${props.rows.length} 条` : ''
  return parts.join('；') + more
})

/** 构建发送给 AI 的凭证上下文（key→value） */
function buildContext(): Record<string, string> {
  const total = props.rows.length
  const abnormalCount = props.rows.filter(
    (r) => r.isAbnormal || r.abnormal || (r.cutoffStatus && /cross|跨期/i.test(r.cutoffStatus)),
  ).length
  const detail = props.rows
    .map((r, i) => {
      const no = r.voucherNo || '（无凭证号）'
      const date = r.voucherDate || ''
      const summary = r.summary || ''
      const counter = r.counterpartAccount ? `对方科目 ${r.counterpartAccount}` : ''
      return `${i + 1}. 凭证 ${no}${date ? ` ${date}` : ''} ${rowAmountText(r)} ${summary} ${counter}${rowAnomalyText(r)}`.trim()
    })
    .join('\n')
  return {
    回写凭证笔数: String(total),
    异常或跨期笔数: String(abnormalCount),
    凭证明细: detail || '（无凭证）',
  }
}

/** 复核提示词（system prompt，区分抽凭/截止） */
function buildPrompt(): string {
  return isCutoff.value
    ? '你是资深审计师。请基于以下截止性测试回写的凭证，识别是否存在跨期确认（收入/成本/费用提前或滞后确认）问题，逐条指出可疑凭证及理由，并给出截止准确性的复核意见。以专业、简洁的中文输出，作为审计说明草稿供人工确认。'
    : '你是资深审计师。请基于以下抽样回写的凭证，识别潜在异常（金额异常、缺少原始凭证、对方科目异常、重复入账、跨期确认等），逐条指出可疑凭证及理由，并给出复核意见。以专业、简洁的中文输出，作为审计说明草稿供人工确认。'
}

/** 发起 AI 复核（R26.3）：调用通用 generate-text 端点 */
async function startReview() {
  if (!props.wpId) {
    ElMessage.warning('缺少底稿标识，无法发起复核')
    return
  }
  stage.value = 'loading'
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/ai/generate-text`,
      {
        prompt: buildPrompt(),
        context: buildContext(),
        existingContent: '',
        section: props.section,
      },
      { _silent: true } as any,
    )
    const text: string = res.data?.data?.content ?? res.data?.content ?? ''
    if (!text) {
      ElMessage.warning('AI 未生成复核意见')
      stage.value = 'prompt'
      return
    }
    opinion.value = text
    stage.value = 'result'
  } catch {
    // AI 不可用/失败：提示不阻断已回写数据（R26.7）
    ElMessage.warning('AI 服务暂不可用，凭证已回写不受影响')
    stage.value = 'prompt'
  }
}

/** 确认采用复核意见（R26.5）→ 填入审计说明；确认前不定稿（R26.8） */
function applyOpinion() {
  if (!opinion.value) return
  emit('applied', opinion.value)
  close()
}

/** 取消（R26.6）：不写入 */
function close() {
  emit('update:modelValue', false)
}

function onClosed() {
  stage.value = 'prompt'
  opinion.value = ''
}

defineExpose({ stage, opinion, startReview, applyOpinion, close, buildContext, buildPrompt })
</script>

<style scoped>
.pfar-alert { margin-bottom: 12px; }
.pfar-summary { font-size: 13px; color: #606266; line-height: 1.6; padding: 4px 0; }
.pfar-summary-label { font-weight: 600; color: #303133; }
.pfar-summary-text { color: #606266; }
.pfar-loading { min-height: 80px; display: flex; align-items: center; justify-content: center; color: #909399; font-size: 13px; }
.pfar-opinion-card { margin-bottom: 8px; }
.pfar-opinion-header { display: flex; align-items: center; }
.pfar-opinion-title { font-size: 13px; font-weight: 600; color: #303133; }
.pfar-opinion-body { font-size: 13px; line-height: 1.7; color: #303133; white-space: pre-wrap; max-height: 320px; overflow-y: auto; }
.pfar-confirm-hint { font-size: 12px; color: #e6a23c; margin-top: 4px; }
.pfar-footer { display: flex; justify-content: flex-end; gap: 8px; }
</style>
