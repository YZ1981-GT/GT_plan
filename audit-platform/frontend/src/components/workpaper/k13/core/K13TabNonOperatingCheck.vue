<template>
  <div class="k13-tab-check">
    <!-- ═══ Section标题 + AI + 复核 ═══ -->
    <div class="section-header">
      <h3>K13-4 营业外支出检查表</h3>
      <div class="header-actions">
        <el-button size="small" type="primary" text @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" text @click="openReviewDialog?.('K13-4-check', '营业外支出检查')">💬 复核</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>
        逐笔检查营业外支出6个维度：真实性/依据合规/审批完整/分类正确性（与日常活动无关→6711；与日常相关→管理费用6602）/
        期间归属/税前扣除性（捐赠12%限额/罚款不可扣/资产损失需备案）。从K13-2明细表抽凭核查，不合规项红色标记汇总。
      </p>
    </div>

    <!-- ═══ 跨底稿引用（GtIndexChip） ═══ -->
    <div class="cross-ref-bar">
      <span class="cross-refs-label">关联引用：</span>
      <GtIndexChip value="K13-2" :context-project-id="props.projectId" />
      <GtIndexChip value="K10" :context-project-id="props.projectId" />
      <GtIndexChip value="A13" :context-project-id="props.projectId" />
      <GtIndexChip value="L1" :context-project-id="props.projectId" />
    </div>

    <!-- ═══ 不合规摘要（红色el-alert） ═══ -->
    <el-alert
      v-if="hasNonCompliant"
      type="error"
      :closable="false"
      show-icon
      style="margin-bottom: 10px"
    >
      <template #title>⚠️ 发现 {{ nonComplianceSummary.count }} 项不合规</template>
      <template #default>
        <ul class="non-compliance-list">
          <li v-for="item in nonComplianceSummary.items" :key="`${item.index}-${item.field}`">
            第{{ item.index }}项「{{ item.label }}」
          </li>
        </ul>
      </template>
    </el-alert>

    <!-- ═══ 检查进度条 ═══ -->
    <div class="progress-bar-section">
      <span class="progress-label">检查进度：{{ checkProgress.completed }}/{{ checkProgress.total }}</span>
      <el-progress
        :percentage="Math.round(checkProgress.rate * 100)"
        :stroke-width="8"
        :show-text="false"
        style="flex: 1; margin-left: 10px"
      />
      <span class="progress-pct">{{ Math.round(checkProgress.rate * 100) }}%</span>
    </div>

    <!-- ═══ 检查表格 ═══ -->
    <el-table
      :data="rows"
      border
      size="small"
      style="width: 100%; font-size: 13px"
      max-height="520"
      :row-class-name="getRowClassName"
    >
      <el-table-column type="index" label="#" width="42" align="center" />
      <el-table-column prop="checkItem" label="检查项" min-width="130">
        <template #default="{ row }">
          <el-tooltip :content="row.description" placement="top" :show-after="300">
            <span class="check-item-name">{{ row.checkItem }}</span>
          </el-tooltip>
        </template>
      </el-table-column>

      <!-- 六大维度 el-select -->
      <el-table-column prop="truthfulness" label="真实性" width="100">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.truthfulness"
            size="small"
            placeholder="—"
            clearable
            @change="(v: string) => updateCompliance(row.rowKey, 'truthfulness', v)"
          >
            <el-option v-for="opt in COMPLIANCE_OPTIONS" :key="opt" :value="opt" :label="opt" />
          </el-select>
          <span v-else :class="{ 'non-comply': row.truthfulness === '不合规' }">{{ row.truthfulness || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="compliance" label="依据合规" width="100">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.compliance"
            size="small"
            placeholder="—"
            clearable
            @change="(v: string) => updateCompliance(row.rowKey, 'compliance', v)"
          >
            <el-option v-for="opt in COMPLIANCE_OPTIONS" :key="opt" :value="opt" :label="opt" />
          </el-select>
          <span v-else :class="{ 'non-comply': row.compliance === '不合规' }">{{ row.compliance || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="approval" label="审批完整" width="100">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.approval"
            size="small"
            placeholder="—"
            clearable
            @change="(v: string) => updateCompliance(row.rowKey, 'approval', v)"
          >
            <el-option v-for="opt in COMPLIANCE_OPTIONS" :key="opt" :value="opt" :label="opt" />
          </el-select>
          <span v-else :class="{ 'non-comply': row.approval === '不合规' }">{{ row.approval || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="classification" label="分类正确" width="100">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.classification"
            size="small"
            placeholder="—"
            clearable
            @change="(v: string) => updateCompliance(row.rowKey, 'classification', v)"
          >
            <el-option v-for="opt in COMPLIANCE_OPTIONS" :key="opt" :value="opt" :label="opt" />
          </el-select>
          <span v-else :class="{ 'non-comply': row.classification === '不合规' }">{{ row.classification || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="periodAttribution" label="期间归属" width="100">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.periodAttribution"
            size="small"
            placeholder="—"
            clearable
            @change="(v: string) => updateCompliance(row.rowKey, 'periodAttribution', v)"
          >
            <el-option v-for="opt in COMPLIANCE_OPTIONS" :key="opt" :value="opt" :label="opt" />
          </el-select>
          <span v-else :class="{ 'non-comply': row.periodAttribution === '不合规' }">{{ row.periodAttribution || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 税前扣除性列（4选项dropdown） -->
      <el-table-column prop="taxDeductibility" label="税前扣除性" width="135">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.taxDeductibility"
            size="small"
            placeholder="—"
            clearable
            @change="(v: string) => updateTaxDeductibility(row.rowKey, v)"
          >
            <el-option v-for="opt in TAX_DEDUCTIBILITY_OPTIONS" :key="opt" :value="opt" :label="opt" />
          </el-select>
          <span v-else>{{ row.taxDeductibility || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 📎 行级抽凭 -->
      <el-table-column label="抽凭" width="60" align="center">
        <template #default="{ row }">
          <el-button
            link
            size="small"
            :disabled="isReadonly"
            @click="handleRowSampling(row.rowKey)"
            :title="row.voucherNumber ? `凭证号: ${row.voucherNumber}` : '点击抽凭'"
          >📎</el-button>
          <span v-if="row.voucherNumber" class="voucher-indicator">✓</span>
        </template>
      </el-table-column>

      <!-- 📎 行级OCR -->
      <el-table-column label="OCR" width="60" align="center">
        <template #default="{ row }">
          <el-button link size="small" :disabled="isReadonly" @click="handleOcrUpload(row.rowKey)">📎</el-button>
          <span v-if="row.ocrAttachment" class="ocr-indicator">✓</span>
        </template>
      </el-table-column>

      <!-- 检查结果 -->
      <el-table-column prop="checkResult" label="检查结果" min-width="150">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.checkResult"
            size="small"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 3 }"
            placeholder="检查结果/审计证据"
            @blur="(e: FocusEvent) => updateCell(row.rowKey, 'checkResult', (e.target as HTMLTextAreaElement)?.value ?? '')"
          />
          <span v-else>{{ row.checkResult || '—' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 抽凭引擎 Dialog（行级） ═══ -->
    <el-dialog
      v-model="showSamplingDialog"
      title="⚡ 抽凭引擎（科目 6711 营业外支出 — 检查表）"
      width="720px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <GtVoucherSamplingEngine
        v-if="showSamplingDialog && props.wpId && props.projectId"
        :project-id="props.projectId"
        :workpaper-id="props.wpId"
        account-code="6711"
        phase="substantive"
        :year="currentYear"
        @filled="handleVoucherFilled"
      />
    </el-dialog>

    <!-- OCR file input (隐藏) -->
    <input ref="ocrFileInput" type="file" accept="image/*,.pdf" style="display:none" @change="handleOcrFileSelected" />

    <!-- ═══ 检查结论 ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="conclusion-header">
          <span>检查结论</span>
          <el-button size="small" type="primary" text @click="handleAiConclusion">
            <el-icon><MagicStick /></el-icon> AI生成
          </el-button>
        </div>
      </template>
      <el-input
        :model-value="checkConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="请填写营业外支出分类正确性及税前扣除性检查结论..."
        @blur="(e: FocusEvent) => saveConclusion((e.target as HTMLTextAreaElement)?.value ?? '')"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>逐笔检查营业外支出6个维度：���实性/依据合规/审批完整/分类正确性/期间归属/税前扣除性</li>
        <li><strong>分类正确性</strong>：与日常活动<strong>无关</strong>的损失→6711营业外支出；与日常相关→6602管理费用/6601销售费用</li>
        <li><strong>税前扣除性</strong>：捐赠≤12%利润可扣/罚款滞纳金不可扣/资产损失需备案后扣除</li>
        <li>典型营业外支出：非流动资产处置损失/捐赠支出/罚款滞纳金/债务重组损失/资产盘亏损失</li>
        <li>📎抽凭列：从K13-2明细表抽取样本逐项核查</li>
        <li>📎OCR列：上传原始证据→OCR自动识别→确认后填入检查结果字段</li>
        <li>不合规项红色高亮，汇总显示在表格上方el-alert中</li>
        <li>检查结果为所得税(L1)提供税前扣除依据</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K13TabNonOperatingCheck.vue — K13-4 营业外支出检查表
 *
 * Spec: .kiro/specs/k13-non-operating-expense/ | Task: 4.4
 * Requirements: 4.1-4.3
 *
 * 功能：
 * - 13 默认检查项 × 6检查维度（合规/不合规/不适用 el-select）
 * - 税前扣除性列：4选项下拉（可全额扣除/限额扣除(12%)/不可扣除/需备案后扣除）
 * - 红色不合规摘要 el-alert（顶部，列出所有不合规项）
 * - 行级抽凭（GtVoucherSamplingEngine dialog，📎 per row）
 * - 行级OCR（📎附件列 POST contract-ocr → ElMessageBox确认 → merge to checkResult）
 * - 检查进度条（completed/total）
 * - 底部结论 el-card textarea + AI button
 *
 * 使用 useK13Check composable 管理所有逻辑
 */
import { ref, computed, inject, defineAsyncComponent, toRef } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import {
  useK13Check,
  COMPLIANCE_OPTIONS,
  TAX_DEDUCTIBILITY_OPTIONS,
} from '../../composables/useK13Check'

const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))
const GtVoucherSamplingEngine = defineAsyncComponent(
  () => import('../../voucher-sampling/GtVoucherSamplingEngine.vue'),
)

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  onSave?: (itemId: string, value: any) => void
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
}>()

const isReadonly = computed(() => props.isReadonly)
const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── Composable ──────────────────────────────────────────────────────────────

function handleSave(itemId: string, value: any): void {
  if (props.onSave) props.onSave(itemId, value)
  emit('save', itemId, value)
}

const {
  rows,
  checkConclusion,
  nonComplianceSummary,
  hasNonCompliant,
  checkProgress,
  updateCompliance,
  updateTaxDeductibility,
  updateCell,
  setSamplingResult,
  setOcrResult,
  saveConclusion,
} = useK13Check({
  allResponses: toRef(props, 'allResponses'),
  projectId: toRef(props, 'projectId'),
  wpId: toRef(props, 'wpId'),
  isReadonly: toRef(props, 'isReadonly'),
  onSave: handleSave,
})

// ─── UI helpers ──────────────────────────────────────────────────────────────

function getRowClassName({ row }: { row: any }): string {
  if (
    row.truthfulness === '不合规' ||
    row.compliance === '不合规' ||
    row.approval === '不合规' ||
    row.classification === '不合规' ||
    row.periodAttribution === '不合规'
  ) {
    return 'non-compliance-row'
  }
  return ''
}

// ─── AI辅助 ──────────────────────────────────────────────────────────────────

async function handleAiAssist(): Promise<void> {
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'non-operating-check',
      prompt: '根据营业外支出检查表各项检查结果，生成分类正确性和税前扣除性分析评价',
      context: JSON.stringify({
        checkRows: rows.value.map(r => ({
          checkItem: r.checkItem,
          truthfulness: r.truthfulness,
          compliance: r.compliance,
          approval: r.approval,
          classification: r.classification,
          periodAttribution: r.periodAttribution,
          taxDeductibility: r.taxDeductibility,
        })),
        nonComplianceCount: nonComplianceSummary.value.count,
      }),
      existingContent: checkConclusion.value,
    })
    const text = res.data?.data?.content || res.data?.content || ''
    if (text) {
      checkConclusion.value = text
      handleSave('K13-4-conclusion', text)
      ElMessage.success('AI检查评价已生成')
    }
  } catch {
    ElMessage.warning('AI生成暂不可用，请手动填写')
  }
}

async function handleAiConclusion(): Promise<void> {
  await handleAiAssist()
}

// ─── 行级抽凭（GtVoucherSamplingEngine） ────────────────────────────────────

const showSamplingDialog = ref(false)
const currentSamplingRowKey = ref('')
const currentYear = computed(() => new Date().getFullYear())

function handleRowSampling(rowKey: string): void {
  currentSamplingRowKey.value = rowKey
  showSamplingDialog.value = true
}

function handleVoucherFilled(payload: any): void {
  const samples = payload?.samples ?? []
  if (samples.length > 0 && currentSamplingRowKey.value) {
    const first = samples[0]
    const voucherNo = first.voucherNo || first.voucherNumber || ''
    const summary = first.summary || first.abstractText || ''
    setSamplingResult(currentSamplingRowKey.value, voucherNo, summary)
    ElMessage.success(`凭证 ${voucherNo} 已填入检查项`)
  }
  showSamplingDialog.value = false
}

// ─── 行级OCR（📎附件列 → POST contract-ocr → ElMessageBox确认 → merge） ────

const ocrFileInput = ref<HTMLInputElement | null>(null)
let currentOcrRowKey = ''

function handleOcrUpload(rowKey: string): void {
  currentOcrRowKey = rowKey
  ocrFileInput.value?.click()
}

async function handleOcrFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  input.value = '' // reset

  try {
    const formData = new FormData()
    formData.append('file', file)

    ElMessage.info('正在OCR识别...')
    const res = await http.post('/api/d4/contract-ocr', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    const ocrData = res.data?.data || res.data || {}
    const ocrText = ocrData.text || ocrData.content || ''

    if (!ocrText) {
      ElMessage.warning('OCR未识别到文字内容')
      return
    }

    // ElMessageBox 确认弹窗
    await ElMessageBox.confirm(
      `OCR识别结果：\n\n${ocrText.slice(0, 500)}${ocrText.length > 500 ? '...' : ''}`,
      'OCR识别确认',
      { confirmButtonText: '填入检查结果', cancelButtonText: '取消', type: 'info' },
    )

    // merge到checkResult字段
    setOcrResult(currentOcrRowKey, file.name, ocrText)
    ElMessage.success('OCR内容已填入检查结果')
  } catch (err: any) {
    if (err !== 'cancel' && err?.message !== 'cancel') {
      ElMessage.error('OCR识别失败：' + (err?.response?.data?.detail || err?.message || '未知错误'))
    }
  }
}
</script>

<style scoped>
.k13-tab-check { padding: 12px; font-size: 13px; }

.section-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px;
}
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; align-items: center; }

.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b;
  padding: 10px 14px; margin-bottom: 12px;
  border-radius: 4px; font-size: 13px; color: #78350f; line-height: 1.6;
}
.methodology-context p { margin: 0; }

.cross-ref-bar {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  margin-bottom: 12px; padding: 6px 12px;
  background: #f5f7fa; border-radius: 6px;
}
.cross-refs-label { color: #909399; font-size: 12px; white-space: nowrap; }

.non-compliance-list { margin: 4px 0 0; padding-left: 16px; font-size: 12px; }
.non-comply { color: #f56c6c; font-weight: 600; }
.voucher-indicator { color: #409eff; font-size: 11px; margin-left: 2px; }
.ocr-indicator { color: #67c23a; font-size: 11px; margin-left: 2px; }

.progress-bar-section {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 12px; padding: 8px 12px;
  background: #f0f9eb; border-radius: 6px;
}
.progress-label { font-size: 12px; color: #606266; white-space: nowrap; }
.progress-pct { font-size: 12px; color: #67c23a; font-weight: 600; min-width: 36px; text-align: right; }

.check-item-name {
  cursor: help; border-bottom: 1px dashed #c0c4cc;
}

.conclusion-card { margin-top: 16px; }
.conclusion-header {
  display: flex; justify-content: space-between; align-items: center;
}

:deep(.non-compliance-row) { background-color: #fef2f2 !important; }
:deep(.non-compliance-row:hover > td) { background-color: #fee2e2 !important; }
:deep(.el-table) { font-size: 13px; }

.compile-hint {
  margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary);
  padding: 12px 16px; background: #fafafa;
  border: 1px solid #ebeef5; border-radius: 6px;
}
.compile-hint summary { cursor: pointer; font-weight: 500; color: #303133; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
