<template>
  <div class="k8-cutoff-v2s">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>截止（发生方向）：</b>由记账凭证追查至支出凭单/原始凭证，确认期末前后记录的销售费用真实发生且记录于正确期间（防止多记/提前记）；</li>
        <li><b>准确性：</b>记账凭证入账金额与支出凭单金额一致。</li>
      </ol>
    </el-alert>

    <!-- ═══ Section标题 + AI + 复核 ═══ -->
    <div class="section-header">
      <span class="section-title">K8-6 截止性测试（记账凭证 → 原始凭证）</span>
      <div class="section-actions">
        <el-tooltip :content="aiAvailable ? 'AI 辅助生成' : 'AI 服务暂不可用'" placement="top">
          <el-button size="small" type="primary" text :loading="aiLoading" :disabled="isReadonly || !aiAvailable" @click="handleAiAssist"><el-icon><MagicStick /></el-icon> AI辅助</el-button>
        </el-tooltip>
        <el-button size="small" text @click="openReviewDialog?.('K8-6-cutoff-v2s')">💬 复核</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>正向截止测试：从<strong>记账凭证</strong>出发，核对支出凭单/原始凭证日期（期末±N天）。验证已入账销售费用是否有真实原始凭证支持且记录在正确期间（存在/发生认定）。<br/>跨期判定：记账日期与支出凭单日期分属不同会计期间。<strong>记账金额应与支出凭单金额一致</strong>（不符标红）。跨期行红色高亮。</p>
    </div>

    <!-- ═══ 二、样本选取标准与规模 ═══ -->
    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">二、样本选取标准与规模</span></template>
      <div class="criteria-row">
        <span class="cr-label">抽取资产负债表日前后</span>
        <el-input-number v-model="criteria.sampleDays" :controls="false" :min="1" :disabled="isReadonly" size="small" style="width:70px" @change="persistCriteria" />
        <span class="cr-label">天的</span>
        <el-input-number v-model="criteria.sampleCount" :controls="false" :min="0" :disabled="isReadonly" size="small" style="width:70px" @change="persistCriteria" />
        <span class="cr-label">张记账凭证</span>
        <el-checkbox v-model="criteria.firstEngagement" :disabled="isReadonly" size="small" style="margin-left:16px" @change="persistCriteria">首次承接（同时执行前期期末截止测试）</el-checkbox>
      </div>
      <el-alert type="warning" :closable="false" show-icon style="margin-top:8px;font-size:12px">
        <template #title>如存在跨期舞弊风险，或所检查样本中发现跨期，应扩大测试范围。</template>
      </el-alert>
    </el-card>

    <!-- ═══ 统计卡片 ═══ -->
    <div class="stats-card">
      <div class="stat-item"><span class="stat-label">总样本数</span><span class="stat-value">{{ summary.totalSamples }}</span></div>
      <div class="stat-item"><span class="stat-label">日前 / 日后</span><span class="stat-value">{{ preCutoffSamples.length }} / {{ postCutoffSamples.length }}</span></div>
      <div class="stat-item"><span class="stat-label">跨期笔数</span><span class="stat-value stat-danger">{{ summary.crossPeriodCount }}</span></div>
      <div class="stat-item"><span class="stat-label">跨期金额</span><span class="stat-value stat-danger">{{ fmtAmt(summary.crossAmountTotal) }}</span></div>
      <div class="stat-item"><span class="stat-label">金额不符</span><span class="stat-value" :class="{ 'stat-danger': summary.mismatchCount > 0 }">{{ summary.mismatchCount }}</span></div>
      <div class="stat-item"><span class="stat-label">证据不完整</span><span class="stat-value" :class="{ 'stat-danger': summary.incompleteCount > 0 }">{{ summary.incompleteCount }}</span></div>
    </div>

    <!-- ═══ 操作栏 ═══ -->
    <div class="table-actions">
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="addSample()">+ 新增</el-button>
      <el-button size="small" type="warning" plain :loading="isLoading" :disabled="isReadonly" @click="autoSample">自动抽样</el-button>
      <el-button size="small" type="success" plain :disabled="isReadonly" @click="showCutoffPanel = true">📥 截止自动提取</el-button>
      <el-button size="small" plain :disabled="isReadonly" @click="showSamplingDialog = true">🎲 抽凭</el-button>
      <el-button size="small" type="danger" plain :disabled="isReadonly || adjustableRows.length === 0" @click="pushToA13">推送跨期至 A13</el-button>
    </div>

    <!-- ═══ 跨期→A13 提示 ═══ -->
    <el-alert v-if="adjustableRows.length > 0" type="warning" :closable="false" show-icon style="margin-bottom:12px;font-size:12px">
      <template #title>发现 {{ adjustableRows.length }} 笔跨期/需调整凭证（提前/多记本期销售费用=错报），可推送至 A13 错报汇总。</template>
    </el-alert>

    <!-- ═══ 资产负债表日前 段 ═══ -->
    <div class="seg-title">资产负债表日<strong>前</strong>（截止日期 {{ periodEnd }} 之前，应记入本期）</div>
    <K8CutoffV2STable :rows="preCutoffSamples" :is-readonly="isReadonly" :fmt-amt="fmtAmt" @update="onCellUpdate" @remove="onRemove" />

    <!-- ═══ 截止日期分隔线 ═══ -->
    <div class="cutoff-divider">—————— 截止日期：{{ periodEnd }} ——————</div>

    <!-- ═══ 资产负债表日后 段 ═══ -->
    <div class="seg-title">资产负债表日<strong>后</strong>（截止日期 {{ periodEnd }} 之后，应记入下期）</div>
    <K8CutoffV2STable :rows="postCutoffSamples" :is-readonly="isReadonly" :fmt-amt="fmtAmt" @update="onCellUpdate" @remove="onRemove" />

    <!-- ═══ useCutoffAutoSampling 面板 ═══ -->
    <GtCutoffAutoSampling
      v-if="showCutoffPanel"
      account-code="6601"
      cutoff-direction="post_cutoff"
      :default-conditions="{ daysBefore: criteria.sampleDays || 5, daysAfter: criteria.sampleDays || 5 }"
      :workpaper-id="props.wpId"
      :project-id="props.projectId"
      :year="currentYear"
      @filled="handleCutoffFilled"
    />

    <!-- ═══ 抽凭引擎 Dialog ═══ -->
    <el-dialog v-model="showSamplingDialog" title="⚡ 抽凭引擎（科目 6601 销售费用-截止V2S）" width="720px" :close-on-click-modal="false" destroy-on-close>
      <GtVoucherSamplingEngine
        v-if="showSamplingDialog && props.wpId && props.projectId"
        :project-id="props.projectId"
        :workpaper-id="props.wpId"
        account-code="6601"
        phase="final"
        :year="currentYear"
        @filled="handleVoucherFilled"
      />
    </el-dialog>

    <!-- ═══ 四、审计说明 ═══ -->
    <el-card shadow="never" class="summary-card">
      <template #header><span class="card-title">四、审计说明</span></template>
      <el-input
        :model-value="conclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="请填写正向截止测试（记账→原始）结论：是否存在多记/提前记跨期、已入账费用是否有真实原始凭证支持、金额是否一致（可点上方 AI辅助 生成草稿）..."
        @blur="(e: FocusEvent) => saveConclusion((e.target as HTMLTextAreaElement)?.value ?? '')"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>正向截止：从记账凭证出发，核对支出凭单/原始凭证日期（存在/发生认定）</li>
        <li>双组列：记账凭证[日期/凭证编号/业务内容/对方科目/金额] → 支出凭单[凭单编号/日期/金额]</li>
        <li>记账金额应与支出凭单金额一致，不符标红需查明</li>
        <li>"自动抽样/截止自动提取"从序时账期末前后±N天采样（6601 销售费用）</li>
        <li>跨期行红色高亮；发现跨期或存在舞弊风险应扩大测试范围</li>
        <li>样本按资产负债表日前/日后两段列示，验证费用截止是否恰当</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K8TabCutoffV2S.vue — K8-6 截止性测试(记账凭证至原始凭证)
 *
 * 对齐源模板 K8-6：双组列（记账凭证→支出凭单）+ 金额一致校验 + 跨期金额
 * + 资产负债表日前/后两段（截止日期分隔线）+ 样本选取标准（天数/张数/首次承接/提示）。
 *
 * Spec: .kiro/specs/k8-selling-expenses/ | Requirements: 5.1-5.6
 */
import { ref, toRef, inject, computed, onMounted, defineAsyncComponent } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import { useK8Cutoff } from '@/components/workpaper/composables/useK8Cutoff'
import { useK8AiGenerate } from '@/components/workpaper/composables/useK8AiGenerate'
import type { Ref } from 'vue'
import type { ExtractedVoucher, FillMode } from '@/components/workpaper/composables/useCutoffAutoSampling'

const GtCutoffAutoSampling = defineAsyncComponent(() => import('../../cutoff/GtCutoffAutoSampling.vue'))
const GtVoucherSamplingEngine = defineAsyncComponent(() => import('../../voucher-sampling/GtVoucherSamplingEngine.vue'))
const K8CutoffV2STable = defineAsyncComponent(() => import('./K8CutoffV2STable.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  year?: number
}>()

const emit = defineEmits<{ (e: 'save', itemId: string, value: any): void }>()
const openReviewDialog = inject<(section?: string) => void>('openReviewDialog', () => {})

const currentYear = computed(() => props.year ?? new Date().getFullYear())
// 🔴 修复：截止日期从 props.year 派生，不再让 composable 回退硬编码 '2025-12-31'
const periodEnd = computed(() => `${currentYear.value}-12-31`)

// ═══ 样本选取标准（组件层持久化 K8-6-criteria）═══
const criteria = ref<{ sampleDays: number; sampleCount: number; firstEngagement: boolean }>({ sampleDays: 5, sampleCount: 0, firstEngagement: false })
function persistCriteria(): void {
  emit('save', 'K8-6-criteria', { remark: JSON.stringify(criteria.value) })
}
onMounted(() => {
  const raw = props.allResponses.get('K8-6-criteria')?.remark
  if (raw) {
    try {
      const d = typeof raw === 'string' ? JSON.parse(raw) : raw
      criteria.value = { sampleDays: Number(d.sampleDays) || 5, sampleCount: Number(d.sampleCount) || 0, firstEngagement: !!d.firstEngagement }
    } catch { /* ignore */ }
  }
})

// ═══ Composable ═══
const {
  preCutoffSamples,
  postCutoffSamples,
  summary,
  conclusion,
  isLoading,
  autoSample,
  addSample,
  removeSample,
  updateCell,
  saveConclusion,
} = useK8Cutoff({
  direction: 'V2S',
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  projectId: toRef(props, 'projectId'),
  wpId: toRef(props, 'wpId'),
  periodEnd,
  isReadonly: toRef(props, 'isReadonly'),
  onSave: (itemId, value) => emit('save', itemId, typeof value === 'string' ? { remark: value } : { remark: JSON.stringify(value) }),
})

function onCellUpdate(rowKey: string, field: string, value: any): void {
  updateCell(rowKey, field, value)
}
function onRemove(rowKey: string): void {
  removeSample(rowKey)
}

function fmtAmt(v: number | null | undefined): string {
  if (v == null || Math.abs(v) < 0.005) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ═══ 跨期 → A13 错报联动（对齐 K9-6/7、useCycleCutoff；crossWpEventBridge 白名单事件）═══
const adjustableRows = computed(() =>
  [...preCutoffSamples.value, ...postCutoffSamples.value].filter(
    (r) => r.isCross || r.conclusion === '跨期' || r.conclusion === '需调整',
  ),
)
function pushToA13(): void {
  const rows = adjustableRows.value
  if (rows.length === 0) { ElMessage.info('无跨期/需调整凭证'); return }
  try {
    eventBus.emit('a13:push-misstatement' as any, {
      wpCode: 'K8',
      accountCode: '6601',
      projectId: props.projectId,
      source: 'K8-6',
      items: rows.map((r) => ({
        voucherNo: r.voucherNo || '',
        amount: Number(r.amount || 0),
        description: `截止跨期（记账${r.bookDate || '-'}/原始${r.sourceDate || '-'}）${r.summary || '销售费用截止性异常'}`.trim(),
        indexRef: 'K8-6',
      })),
      timestamp: Date.now(),
    })
    ElMessage.success(`已推送 ${rows.length} 笔跨期凭证至 A13 错报汇总`)
  } catch {
    ElMessage.warning('推送失败，请稍后重试')
  }
}

// ═══ AI 辅助 ═══
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useK8AiGenerate({
  wpId: toRef(props, 'wpId'),
})
async function handleAiAssist(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'cutoff-review',
    conclusion.value || '',
    {
      方向: '正向截止（记账凭证→原始凭证，存在/发生认定）',
      总样本数: summary.value.totalSamples,
      跨期笔数: summary.value.crossPeriodCount,
      跨期金额: summary.value.crossAmountTotal,
      金额不符笔数: summary.value.mismatchCount,
      任务: '请为销售费用正向截止性测试形成结论（是否存在多记/提前记跨期、已入账费用是否有真实原始凭证支持、记账与支出凭单金额是否一致）',
    },
    'AI 生成 · 截止测试结论',
  )
  if (text) saveConclusion(text)
}

// ═══ useCutoffAutoSampling 集成（序时账±N天） ═══
const showCutoffPanel = ref(false)
function handleCutoffFilled(payload: { samples: ExtractedVoucher[]; fillMode: FillMode }): void {
  for (const v of payload.samples) {
    const amt = v.debitAmount ? parseFloat(v.debitAmount) : (v.creditAmount ? parseFloat(v.creditAmount) : 0)
    addSample({
      voucherNo: v.voucherNo,
      bookDate: v.voucherDate,
      summary: v.summary || '',
      businessContent: v.summary || '',
      amount: amt,
      sourceVoucherNo: v.voucherNo,
      sourceDate: v.voucherDate,
      sourceAmount: amt,
    })
  }
  showCutoffPanel.value = false
  ElMessage.success(`已填入${payload.samples.length}笔截止样本`)
}

// ═══ 抽凭引擎 ═══
const showSamplingDialog = ref(false)
function handleVoucherFilled(payload: any): void {
  const vouchers = payload?.samples ?? []
  for (const v of vouchers) {
    const amt = v.debitAmount ? parseFloat(v.debitAmount) : (v.creditAmount ? parseFloat(v.creditAmount) : 0)
    addSample({
      voucherNo: v.voucherNo || v.voucher_no || '',
      bookDate: v.voucherDate || v.voucher_date || '',
      summary: v.summary || '',
      businessContent: v.summary || '',
      offsetAccount: v.counterpartAccount || v.offsetAccount || '',
      amount: amt,
      sourceVoucherNo: v.voucherNo || v.voucher_no || '',
      sourceDate: v.voucherDate || v.voucher_date || '',
      sourceAmount: amt,
    })
  }
  showSamplingDialog.value = false
  if (vouchers.length) ElMessage.success(`已填入${vouchers.length}笔凭证`)
}
</script>

<style scoped>
.k8-cutoff-v2s { font-size: var(--wp-font-size, 13px); padding: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { font-size: 15px; font-weight: 600; color: #303133; }
.section-actions { display: flex; align-items: center; gap: 4px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.6; }
.section-card { margin-bottom: 12px; }
.section-card :deep(.el-card__header) { padding: 8px 14px; }
.section-card :deep(.el-card__body) { padding: 12px 14px; }
.card-title { font-weight: 600; }
.criteria-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-size: 13px; color: #606266; }
.cr-label { font-size: 13px; color: #606266; }
.stats-card { display: flex; gap: 24px; padding: 12px 16px; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; margin-bottom: 14px; }
.stat-item { display: flex; flex-direction: column; align-items: center; }
.stat-label { font-size: 12px; color: #6b7280; }
.stat-value { font-size: 18px; font-weight: 700; color: #1f2937; }
.stat-danger { color: #dc2626; }
.table-actions { display: flex; gap: 8px; margin-bottom: 12px; }
.seg-title { font-size: 13px; font-weight: 600; color: #303133; margin: 6px 0; }
.seg-title strong { color: #2563eb; }
.cutoff-divider { text-align: center; color: #dc2626; font-weight: 600; font-size: 13px; margin: 14px 0; letter-spacing: 1px; }
.summary-card { margin-top: 16px; }
.summary-card :deep(.el-card__header) { padding: 8px 14px; }
.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; }
.compile-hint summary { cursor: pointer; font-weight: 500; color: #303133; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
