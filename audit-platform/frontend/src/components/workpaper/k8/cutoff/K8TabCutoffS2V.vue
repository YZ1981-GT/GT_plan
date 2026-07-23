<template>
  <div class="k8-cutoff-s2v">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>截止（完整性方向）：</b>由支出凭单/原始凭证追查至记账凭证，确认销售费用记录于正确的会计期间，不存在应记未记（漏记）；</li>
        <li><b>准确性：</b>支出凭单金额与记账凭证入账金额一致。</li>
      </ol>
    </el-alert>

    <!-- ═══ Section标题 + AI + 复核 ═══ -->
    <div class="section-header">
      <span class="section-title">K8-7 截止性测试（原始凭证 → 记账凭证）</span>
      <div class="section-actions">
        <el-tooltip :content="aiAvailable ? 'AI 辅助生成' : 'AI 服务暂不可用'" placement="top">
          <el-button size="small" type="primary" text :loading="aiLoading" :disabled="isReadonly || !aiAvailable" @click="handleAiAssist"><el-icon><MagicStick /></el-icon> AI辅助</el-button>
        </el-tooltip>
        <el-button size="small" text @click="openReviewDialog?.('K8-7-cutoff-s2v')">💬 复核</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>反向截止测试：从<strong>支出凭单/原始凭证</strong>出发，核对是否及时完整入账（完整性认定）。<br/>跨期判定：支出凭单日期与记账凭证日期分属不同会计期间，表明费用未及时入账。<strong>支出凭单金额应与记账凭证金额一致</strong>（不符标红）。跨期行红色高亮。</p>
    </div>

    <!-- ═══ 二、样本选取标准与规模 ═══ -->
    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">二、样本选取标准与规模</span></template>
      <div class="criteria-row">
        <span class="cr-label">选取资产负债表日后</span>
        <el-input-number v-model="criteria.sampleDays" :controls="false" :min="1" :disabled="isReadonly" size="small" style="width:70px" @change="persistCriteria" />
        <span class="cr-label">天的银行对账单/付款凭证/支出凭单等</span>
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
      <template #title>发现 {{ adjustableRows.length }} 笔跨期/需调整凭证（漏记/滞后=本期费用少计错报），可推送至 A13 错报汇总。</template>
    </el-alert>

    <!-- ═══ 资产负债表日前 段 ═══ -->
    <div class="seg-title">资产负债表日<strong>前</strong>（截止日期 {{ periodEnd }} 之前，应记入本期）</div>
    <K8CutoffS2VTable :rows="preCutoffSamples" :is-readonly="isReadonly" :fmt-amt="fmtAmt" @update="onCellUpdate" @remove="onRemove" />

    <!-- ═══ 截止日期分隔线 ═══ -->
    <div class="cutoff-divider">—————— 截止日期：{{ periodEnd }} ——————</div>

    <!-- ═══ 资产负债表日后 段 ═══ -->
    <div class="seg-title">资产负债表日<strong>后</strong>（截止日期 {{ periodEnd }} 之后，应记入下期）</div>
    <K8CutoffS2VTable :rows="postCutoffSamples" :is-readonly="isReadonly" :fmt-amt="fmtAmt" @update="onCellUpdate" @remove="onRemove" />

    <!-- ═══ useCutoffAutoSampling 面板 ═══ -->
    <GtCutoffAutoSampling
      v-if="showCutoffPanel"
      account-code="6601"
      cutoff-direction="pre_cutoff"
      :default-conditions="{ daysBefore: criteria.sampleDays || 5, daysAfter: criteria.sampleDays || 5 }"
      :workpaper-id="props.wpId"
      :project-id="props.projectId"
      :year="currentYear"
      @filled="handleCutoffFilled"
    />

    <!-- ═══ 抽凭引擎 Dialog ═══ -->
    <el-dialog v-model="showSamplingDialog" title="⚡ 抽凭引擎（科目 6601 销售费用-截止S2V）" width="720px" :close-on-click-modal="false" destroy-on-close>
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
        placeholder="请填写反向截止测试（原始→记账）结论：是否存在应记未记/漏记跨期、费用是否及时完整入账、金额是否一致（可点上方 AI辅助 生成草稿）..."
        @blur="(e: FocusEvent) => saveConclusion((e.target as HTMLTextAreaElement)?.value ?? '')"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>反向截止：从支出凭单/原始凭证出发，核对是否已及时完整入账（完整性认定）</li>
        <li>双组列：支出凭单[凭单编号/日期/金额] → 记账凭证[日期/凭证编号/业务内容/对方科目/金额]</li>
        <li>支出凭单金额应与记账凭证金额一致，不符标红需查明</li>
        <li>"自动抽样/截止自动提取"从序时账期末±N天采样（6601 销售费用）</li>
        <li>跨期行红色高亮；发现跨期或存在舞弊风险应扩大测试范围</li>
        <li>样本按资产负债表日前/日后两段列示，验证费用截止是否恰当</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K8TabCutoffS2V.vue — K8-7 截止性测试(原始凭证至记账凭证)
 *
 * 对齐源模板 K8-7：双组列（支出凭单→记账凭证）+ 金额一致校验 + 跨期金额
 * + 资产负债表日前/后两段（截止日期分隔线）+ 样本选取标准（天数/首次承接/提示）。
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
const K8CutoffS2VTable = defineAsyncComponent(() => import('./K8CutoffS2VTable.vue'))

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

// ═══ 样本选取标准（组件层持久化 K8-7-criteria）═══
const criteria = ref<{ sampleDays: number; firstEngagement: boolean }>({ sampleDays: 5, firstEngagement: false })
function persistCriteria(): void {
  emit('save', 'K8-7-criteria', { remark: JSON.stringify(criteria.value) })
}
onMounted(() => {
  const raw = props.allResponses.get('K8-7-criteria')?.remark
  if (raw) {
    try {
      const d = typeof raw === 'string' ? JSON.parse(raw) : raw
      criteria.value = { sampleDays: Number(d.sampleDays) || 5, firstEngagement: !!d.firstEngagement }
    } catch { /* ignore */ }
  }
})

// ═══ Composable ═══
const {
  samples,
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
  direction: 'S2V',
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

// ═══ 跨期 → A13 错报联动（反向截止/完整性方向；对齐 K9-7、useCycleCutoff）═══
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
      source: 'K8-7',
      items: rows.map((r) => ({
        voucherNo: r.voucherNo || '',
        amount: Number(r.amount || 0),
        description: `截止跨期（原始${r.sourceDate || '-'}/记账${r.bookDate || '-'}）${r.summary || '销售费用截止性异常'}`.trim(),
        indexRef: 'K8-7',
      })),
      timestamp: Date.now(),
    })
    ElMessage.success(`已推送 ${rows.length} 笔跨期凭证至 A13 错报汇总`)
  } catch {
    ElMessage.warning('推送失败，请稍后重试')
  }
}

function fmtAmt(v: number | null | undefined): string {
  if (v == null || Math.abs(v) < 0.005) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
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
      方向: '反向截止（原始凭证→记账凭证，完整性认定）',
      总样本数: summary.value.totalSamples,
      跨期笔数: summary.value.crossPeriodCount,
      跨期金额: summary.value.crossAmountTotal,
      金额不符笔数: summary.value.mismatchCount,
      任务: '请为销售费用反向截止性测试形成结论（是否存在应记未记/漏记跨期、费用是否及时完整入账、支出凭单与记账金额是否一致）',
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
      sourceVoucherNo: v.voucherNo,
      sourceDate: v.voucherDate,
      sourceAmount: amt,
      voucherNo: v.voucherNo,
      bookDate: v.voucherDate,
      summary: v.summary || '',
      businessContent: v.summary || '',
      amount: amt,
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
      sourceVoucherNo: v.voucherNo || v.voucher_no || '',
      sourceDate: v.voucherDate || v.voucher_date || '',
      sourceAmount: amt,
      voucherNo: v.voucherNo || v.voucher_no || '',
      bookDate: v.voucherDate || v.voucher_date || '',
      summary: v.summary || '',
      businessContent: v.summary || '',
      offsetAccount: v.counterpartAccount || v.offsetAccount || '',
      amount: amt,
    })
  }
  showSamplingDialog.value = false
  if (vouchers.length) ElMessage.success(`已填入${vouchers.length}笔凭证`)
}
</script>

<style scoped>
.k8-cutoff-s2v { font-size: var(--wp-font-size, 13px); padding: 16px; }
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
