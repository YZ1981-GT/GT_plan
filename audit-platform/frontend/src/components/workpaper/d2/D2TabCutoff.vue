<script setup lang="ts">
/**
 * D2TabCutoff — 截止测试
 * 8列: 序号|发票号|收入日期|入账日期|金额|跨期判定|结论|备注
 * 自动跨期判定, 红色警告header, 底部汇总
 * 集成 GtCutoffAutoSampling 自动提取（Task 11.1）
 */
import { inject, ref, toRef, computed, onMounted, type Ref } from 'vue'
import { useD2Cutoff, type CutoffSample } from '../composables/useD2Cutoff'
import { useD2AiGenerate } from '../composables/useD2AiGenerate'
import GtCutoffAutoSampling from '../cutoff/GtCutoffAutoSampling.vue'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import type { ExtractedVoucher, FillMode } from '../composables/useCutoffAutoSampling'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  bsDate: string
}>()

const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) => v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

// 复核对话集成 (Task 47.1)
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

function handleCellContextMenu(row: any, column: any, event: MouseEvent): void {
  if (!openReviewDialog) return
  event.preventDefault()
  const field = column?.property || 'unknown'
  const rowKey = row?.seq || row?.index || 'unknown'
  openReviewDialog(`D2-cutoff-${rowKey}-${field}`)
}


const {
  samples,
  cutoffCount,
  cutoffTotalAmount,
  hasCutoffIssue,
  addSample,
  removeSample,
  updateCell,
  debounceSave,
} = useD2Cutoff({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  bsDate: toRef(props, 'bsDate') as Ref<string>,
})

// ─── 年度计算（从bsDate提取，如 "2025-12-31" → 2025）─────────────────────────

const year = computed(() => {
  if (props.bsDate && props.bsDate.length >= 4) {
    return parseInt(props.bsDate.slice(0, 4), 10)
  }
  return new Date().getFullYear() - 1
})

// ─── 审计说明/结论（inline 存储）────────────────────────────────────────────
const CONCLUSION_KEY = 'D2-cutoff-conclusion'
const auditConclusion = ref('')

onMounted(() => {
  auditConclusion.value = props.allResponses.get(CONCLUSION_KEY)?.remark || ''
})

function saveConclusion(v: string): void {
  if (props.isReadonly) return
  auditConclusion.value = v
  const item = { item_id: CONCLUSION_KEY, conclusion: null, remark: v }
  props.allResponses.set(CONCLUSION_KEY, item)
  window.dispatchEvent(new CustomEvent('d2:save-items', { detail: { items: [item] } }))
}

const wpIdRef = toRef(props, 'wpId')
const { aiAvailable, generateAndConfirm } = useD2AiGenerate(wpIdRef)
const aiLoadingConclusion = ref(false)

async function generateConclusionAI(): Promise<void> {
  if (props.isReadonly) return
  aiLoadingConclusion.value = true
  try {
    const text = await generateAndConfirm('cutoff-note', auditConclusion.value, {
      sheet: 'D2-cutoff',
      checked: samples.value.length,
      cutoffCount: cutoffCount.value,
      cutoffTotalAmount: cutoffTotalAmount.value,
    }, 'AI · 截止测试结论')
    if (text) saveConclusion(text)
  } finally { aiLoadingConclusion.value = false }
}

const openReviewDialog2 = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const GUIDANCE_TEXTS = [
  '截止测试目的：验证收入及应收账款是否记录于正确的会计期间，防止跨期确认（提前/延后确认收入）。',
  '测试范围：一般选取资产负债表日前后各若干天（如 ±5～10 天）的销售/发货/开票记录，核对收入确认与发货、验收、开票凭证的日期匹配性。',
  '跨期判定：若收入确认日期与实际发货/验收期间跨越资产负债表日，则标记为跨期，需评估对当期收入及应收账款的影响金额。',
  '重大跨期错报应提出调整分录（AJE），并关注管理层是否存在人为调节收入的动机。',
]

// ─── 自动提取填充处理 (Task 11.1) ──────────────────────────────────────────

function generateRowId(): string {
  return `ct-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

/**
 * 将 ExtractedVoucher 映射为 CutoffSample
 * 标记 source: "自动提取"
 */
function mapVoucherToSample(voucher: ExtractedVoucher, seq: number): CutoffSample {
  const debit = voucher.debitAmount ? parseFloat(voucher.debitAmount) : 0
  const credit = voucher.creditAmount ? parseFloat(voucher.creditAmount) : 0
  const amount = debit > 0 ? debit : -credit
  return {
    rowId: generateRowId(),
    seq,
    invoiceNo: voucher.voucherNo || '',
    revenueDate: voucher.voucherDate || '',
    receivableDate: voucher.voucherDate || '',
    amount,
    isCutoff: voucher.cutoffStatus === '可能跨期',
    conclusion: voucher.cutoffStatus || '',
    remark: voucher.remark || '',
    source: '自动提取',
  }
}

/**
 * 处理 GtCutoffAutoSampling @filled 事件
 * 按 fillMode 合并到 samples，触发 debounce 保存
 */
function handleAutoExtractFilled(payload: { samples: ExtractedVoucher[]; fillMode: FillMode }): void {
  const { samples: extracted, fillMode } = payload
  const mapped = extracted.map((v, idx) => mapVoucherToSample(v, idx + 1))

  if (fillMode === 'replace') {
    // 替换模式：清空后填充
    samples.value = mapped.map((s, i) => ({ ...s, seq: i + 1 }))
  } else if (fillMode === 'merge') {
    // 合并模式：按凭证号(invoiceNo)去重
    const existingNos = new Set(samples.value.map(s => s.invoiceNo))
    const newSamples = mapped.filter(s => !existingNos.has(s.invoiceNo))
    const startSeq = samples.value.length + 1
    newSamples.forEach((s, i) => { s.seq = startSeq + i })
    samples.value.push(...newSamples)
  } else {
    // append 模式（默认）：追加到末尾
    const startSeq = samples.value.length + 1
    mapped.forEach((s, i) => { s.seq = startSeq + i })
    samples.value.push(...mapped)
  }

  // 触发 debounce 2s 自动保存
  debounceSave()
}

/**
 * 处理回写后 AI 复核弹窗 @applied（Req 26.5）：将确认后的复核意见填入审计结论。
 * 确认前不定稿（弹窗内部保证），此处仅在用户确认后写入。
 */
function handleReviewApplied(text: string): void {
  if (props.isReadonly || !text) return
  const merged = auditConclusion.value
    ? `${auditConclusion.value}\n\n【AI 复核意见】\n${text}`
    : text
  saveConclusion(merged)
}
</script>

<template>
  <div class="d2-tab-cutoff">
    <div class="tab-header">
      <h4>应收账款截止测试</h4>
      <GtReviewTrigger section-id="D2-cutoff-header" />
    </div>

    <el-alert type="info" :closable="false" show-icon title="审计目标" class="audit-objective">
      <template #default>
        <p>核实收入及应收账款是否记录于正确的会计期间，识别资产负债表日前后的跨期确认错报。</p>
      </template>
    </el-alert>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addSample">+ 添加样本</el-button>
      </div>
    </div>

    <!-- 自动提取面板 (Task 11.1) -->
    <div v-if="!isReadonly" class="auto-extract-section">
      <el-collapse>
        <el-collapse-item title="自动提取凭证" name="auto-extract">
          <GtCutoffAutoSampling
            account-code="1122"
            cutoff-direction="post_cutoff"
            :workpaper-id="wpId"
            :project-id="projectId"
            :year="year"
            @filled="handleAutoExtractFilled"
            @applied="handleReviewApplied"
          />
        </el-collapse-item>
      </el-collapse>
    </div>

    <!-- 跨期警告 -->
    <el-alert v-if="hasCutoffIssue" type="error" :closable="false" class="cutoff-alert">
      发现{{ cutoffCount }}笔跨期，合计金额{{ displayPrefs.fmtAmount(cutoffTotalAmount) }}
    </el-alert>

    <!-- 主表 -->
    <el-table :data="samples" border size="small" style="width: 100%">
      <el-table-column label="序号" width="68">
        <template #default="{ $index, row }">
          {{ $index + 1 }}<GtReviewDot row-prefix="D2-cutoff" :row-key="row.rowId" />
        </template>
      </el-table-column>
      <el-table-column label="发票号" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.invoiceNo" size="small" @change="(v: string) => updateCell(row.rowId, 'invoiceNo', v)" />
          <span v-else>{{ row.invoiceNo || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="收入日期" width="140">
        <template #default="{ row }">
          <el-date-picker
            v-if="!isReadonly"
            :model-value="row.revenueDate"
            type="date"
            value-format="YYYY-MM-DD"
            size="small"
            style="width:100%"
            @change="(v: string) => updateCell(row.rowId, 'revenueDate', v)"
          />
          <span v-else>{{ row.revenueDate || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="入账日期" width="140">
        <template #default="{ row }">
          <el-date-picker
            v-if="!isReadonly"
            :model-value="row.receivableDate"
            type="date"
            value-format="YYYY-MM-DD"
            size="small"
            style="width:100%"
            @change="(v: string) => updateCell(row.rowId, 'receivableDate', v)"
          />
          <span v-else>{{ row.receivableDate || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.amount"
            size="small"
            :controls="false"
            :precision="2"
            @change="(v: number) => updateCell(row.rowId, 'amount', v)"
          />
          <span v-else>{{ displayPrefs.fmtAmount(row.amount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="跨期判定" width="80" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.isCutoff" type="danger" size="small">跨期</el-tag>
          <span v-else style="color:#909399">正常</span>
        </template>
      </el-table-column>
      <el-table-column label="结论" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.conclusion" size="small" @change="(v: string) => updateCell(row.rowId, 'conclusion', v)" />
          <span v-else>{{ row.conclusion || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.remark" size="small" placeholder="备注" @change="(v: string) => updateCell(row.rowId, 'remark', v)" />
          <span v-else>{{ row.remark || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="来源" width="80" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.source === '自动提取'" type="success" size="small">自动提取</el-tag>
          <el-tag v-else-if="row.source === '手动添加'" size="small">手动添加</el-tag>
          <span v-else style="color:#909399">-</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button type="danger" link size="small" @click="removeSample(row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部汇总 -->
    <div class="summary-bar">
      <span>已检查: {{ samples.length }}笔</span>
      <span>跨期笔数: <b :style="{ color: cutoffCount > 0 ? '#f56c6c' : '' }">{{ cutoffCount }}</b></span>
      <span>跨期金额: {{ displayPrefs.fmtAmount(cutoffTotalAmount) }}</span>
    </div>

    <!-- 审计结论 -->
    <div class="section-subtitle">审计结论</div>
    <div class="note-section">
      <el-input type="textarea" autosize :model-value="auditConclusion" placeholder="请输入截止测试结论..." :disabled="isReadonly" @change="saveConclusion" />
      <div class="note-actions">
        <el-tooltip :content="aiAvailable ? 'AI 辅助生成结论' : 'AI 服务暂不可用'" placement="top">
          <el-button size="small" :loading="aiLoadingConclusion" :disabled="isReadonly || !aiAvailable" @click="generateConclusionAI">🤖 AI</el-button>
        </el-tooltip>
        <el-button v-if="openReviewDialog2" size="small" @click="openReviewDialog2('D2-cutoff-conclusion')">💬 复核</el-button>
      </div>
    </div>

    <details class="guidance-fold">
      <summary>📋 编制提示</summary>
      <p v-for="(t, i) in GUIDANCE_TEXTS" :key="'g-' + i">{{ t }}</p>
    </details>
  </div>
</template>

<style scoped>
.d2-tab-cutoff { padding: 12px; }
.tab-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.tab-header h4 { margin: 0; font-size: 15px; }
.audit-objective { margin-bottom: 12px; }
.audit-objective p { margin: 0; font-size: 13px; line-height: 1.6; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.toolbar-left { display: flex; gap: 8px; }
.section-subtitle { font-size: 14px; font-weight: 600; color: #303133; margin: 16px 0 10px; }
.note-section { margin-bottom: 8px; }
.note-actions { margin-top: 6px; display: flex; gap: 8px; }
.guidance-fold { margin: 16px 0; border-left: 3px solid #409eff; background: #ecf5ff; padding: 10px 14px; border-radius: 0 4px 4px 0; font-size: 13px; color: #606266; }
.guidance-fold summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-fold p { margin: 6px 0; line-height: 1.6; }
.auto-extract-section { margin-bottom: 12px; }
.auto-extract-section :deep(.el-collapse-item__header) { font-size: 13px; font-weight: 500; }
.cutoff-alert { margin-bottom: 12px; }
.summary-bar {
  display: flex; gap: 24px; padding: 8px 12px; margin-top: 10px;
  background: #fafafa; border: 1px solid #ebeef5; border-radius: 4px; font-size: 13px;
}
</style>
