<template>
  <div class="k12-tab-non-operating-check">
    <!-- ═══ Section标题 + AI + 复核 ═══ -->
    <div class="section-header">
      <h3>K12-4 营业外收入检查表</h3>
      <div class="header-actions">
        <el-button size="small" type="primary" text @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" text @click="openReviewDialog?.('K12-4-check', '营业外收入检查')">💬 复核</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>
        逐笔检查营业外收入真实性、依据合规性、分类正确性（与日常活动无关→6301；与日常相关→6117 K10）、
        期间归属及税务处理合规性。从K12-2明细表抽凭核查，不合规项红色标记汇总。
      </p>
    </div>

    <!-- ═══ 跨底稿引用（GtIndexChip） ═══ -->
    <div class="cross-ref-bar">
      <span class="cross-refs-label">关联引用：</span>
      <GtIndexChip value="K12-2" :context-project-id="props.projectId" />
      <GtIndexChip value="K10" :context-project-id="props.projectId" />
      <GtIndexChip value="A13" :context-project-id="props.projectId" />
    </div>

    <!-- ═══ 不合规摘要（有不合规项时显示） ═══ -->
    <el-alert
      v-if="nonComplianceCount > 0"
      type="error"
      :closable="false"
      show-icon
      style="margin-bottom: 10px"
    >
      <template #title>⚠️ 发现 {{ nonComplianceCount }} 项不合规</template>
      <template #default>
        <ul class="non-compliance-list">
          <li v-for="item in nonComplianceItems" :key="item.rowKey">
            {{ item.incomeSource }}：{{ item.nonComplianceReason || '未说明原因' }}
          </li>
        </ul>
      </template>
    </el-alert>

    <!-- ═══ 检查表格 ═══ -->
    <el-table
      :data="checkRows"
      border
      size="small"
      style="width: 100%; font-size: 13px"
      max-height="480"
      :row-class-name="getRowClassName"
    >
      <el-table-column type="index" label="#" width="42" align="center" />
      <el-table-column prop="incomeSource" label="收入来源" min-width="140">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.incomeSource"
            size="small"
            placeholder="收入来源"
            @change="(v: string) => updateCell(row.rowKey, 'incomeSource', v)"
          />
          <span v-else>{{ row.incomeSource || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="amount" label="金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.amount"
            size="small"
            :controls="false"
            :precision="2"
            style="width: 100%"
            @change="(v: number | undefined) => updateCell(row.rowKey, 'amount', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(row.amount) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="authenticity" label="真实性" width="90">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.authenticity"
            size="small"
            placeholder="—"
            @change="(v: string) => updateCell(row.rowKey, 'authenticity', v)"
          >
            <el-option value="合规" label="合规" />
            <el-option value="不合规" label="不合规" />
            <el-option value="不适用" label="不适用" />
          </el-select>
          <span v-else :class="{ 'non-comply': row.authenticity === '不合规' }">{{ row.authenticity || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="basisCompliance" label="依据合规" width="90">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.basisCompliance"
            size="small"
            placeholder="—"
            @change="(v: string) => updateCell(row.rowKey, 'basisCompliance', v)"
          >
            <el-option value="合规" label="合规" />
            <el-option value="不合规" label="不合规" />
            <el-option value="不适用" label="不适用" />
          </el-select>
          <span v-else :class="{ 'non-comply': row.basisCompliance === '不合规' }">{{ row.basisCompliance || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="classification" label="分类正确" width="90">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.classification"
            size="small"
            placeholder="—"
            @change="(v: string) => updateCell(row.rowKey, 'classification', v)"
          >
            <el-option value="合规" label="合规" />
            <el-option value="不合规" label="不合规" />
            <el-option value="不适用" label="不适用" />
          </el-select>
          <span v-else :class="{ 'non-comply': row.classification === '不合规' }">{{ row.classification || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="periodAttribution" label="期间归属" width="90">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.periodAttribution"
            size="small"
            placeholder="—"
            @change="(v: string) => updateCell(row.rowKey, 'periodAttribution', v)"
          >
            <el-option value="合规" label="合规" />
            <el-option value="不合规" label="不合规" />
            <el-option value="不适用" label="不适用" />
          </el-select>
          <span v-else :class="{ 'non-comply': row.periodAttribution === '不合规' }">{{ row.periodAttribution || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="taxCompliance" label="税务处理" width="90">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.taxCompliance"
            size="small"
            placeholder="—"
            @change="(v: string) => updateCell(row.rowKey, 'taxCompliance', v)"
          >
            <el-option value="合规" label="合规" />
            <el-option value="不合规" label="不合规" />
            <el-option value="不适用" label="不适用" />
          </el-select>
          <span v-else :class="{ 'non-comply': row.taxCompliance === '不合规' }">{{ row.taxCompliance || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="voucherNo" label="凭证号" width="100">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.voucherNo"
            size="small"
            placeholder="凭证号"
            @change="(v: string) => updateCell(row.rowKey, 'voucherNo', v)"
          />
          <span v-else>{{ row.voucherNo || '—' }}</span>
        </template>
      </el-table-column>
      <!-- 📎 行级OCR列 -->
      <el-table-column label="📎" width="65" align="center">
        <template #default="{ row }">
          <el-button link size="small" :disabled="isReadonly" @click="handleOcrUpload(row.rowKey)">📎</el-button>
          <span v-if="row.ocrAttachment" class="ocr-indicator">✓</span>
        </template>
      </el-table-column>
      <el-table-column prop="evidence" label="审计证据" min-width="130">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.evidence"
            size="small"
            placeholder="审计证据/备注"
            @change="(v: string) => updateCell(row.rowKey, 'evidence', v)"
          />
          <span v-else>{{ row.evidence || '—' }}</span>
        </template>
      </el-table-column>
      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="" width="50" align="center">
        <template #default="{ row }">
          <el-button link size="small" type="danger" @click="removeRow(row.rowKey)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 操作栏 ═══ -->
    <div class="table-actions">
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleAddRow">+ 新增检查项</el-button>
      <el-button size="small" plain :disabled="isReadonly" @click="showSamplingDialog = true">🎲 抽凭</el-button>
    </div>

    <!-- ═══ 抽凭引擎 Dialog ═══ -->
    <el-dialog
      v-model="showSamplingDialog"
      title="⚡ 抽凭引擎（科目 6301 营业外收入 — 检查表）"
      width="720px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <GtVoucherSamplingEngine
        v-if="showSamplingDialog && props.wpId && props.projectId"
        :project-id="props.projectId"
        :workpaper-id="props.wpId"
        account-code="6301"
        phase="substantive"
        :year="currentYear"
        @filled="handleVoucherFilled"
      />
    </el-dialog>

    <!-- OCR file input (隐藏) -->
    <input ref="ocrFileInput" type="file" accept="image/*,.pdf" style="display:none" @change="handleOcrFileSelected" />

    <!-- ═══ 检查结论 ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header><span>检查结论</span></template>
      <el-input
        :model-value="checkConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="请填写营业外收入分类正确性检查结论..."
        @blur="(e: FocusEvent) => saveConclusion((e.target as HTMLTextAreaElement)?.value ?? '')"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>逐笔检查营业外收入5个维度：真实性/依据合规/分类正确/期间归属/税务处理</li>
        <li>分类正确性：与日常活动<strong>无关</strong>的利得→6301营业外收入；与日常相关→6117其他收益(K10)</li>
        <li>典型营业外收入：政府补助/债务重组利得/资产盘盈/罚款收入/捐赠利得/确实无法支付的款项</li>
        <li>使用🎲抽凭从K12-2明细表中随机抽取样本核查</li>
        <li>📎附件列：上传原始证据→OCR自动识别→确认后填入审计证据字段</li>
        <li>不合规项红色高亮，汇总显示在表格上方</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K12TabNonOperatingCheck.vue — K12-4 营业外收入检查表
 *
 * Spec: .kiro/specs/k12-non-operating-income/ | Task: 6.3
 * Requirements: 4.2
 *
 * 功能：
 * - 逐笔检查：真实性/依据合规/分类正确性/期间归属/税务处理
 * - 抽凭引擎（GtVoucherSamplingEngine dialog → 样本填入）
 * - 行级OCR（📎列 POST /d4/contract-ocr → ElMessageBox确认 → merge到evidence）
 * - GtIndexChip跨底稿引用（K12-2 / K10 / A13）
 * - 不合规项红色摘要
 */
import { ref, computed, inject, defineAsyncComponent, watch } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

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
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
}>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── Check Row 数据 ──────────────────────────────────────────────────────────

interface CheckRow {
  rowKey: string
  incomeSource: string
  amount: number
  authenticity: string
  basisCompliance: string
  classification: string
  periodAttribution: string
  taxCompliance: string
  voucherNo: string
  evidence: string
  ocrAttachment: string
}

const STORAGE_KEY = 'K12-4-check-rows'
const CONCLUSION_KEY = 'K12-4-conclusion'

const checkRows = ref<CheckRow[]>([])
const checkConclusion = ref('')

// ─── 从 allResponses 恢复数据 ────────────────────────────────────────────────

function restoreFromResponses(): void {
  const responses = props.allResponses
  if (!responses || responses.size === 0) return

  // 恢复检查行
  const stored = responses.get(STORAGE_KEY)
  if (stored) {
    try {
      const raw = stored.remark || stored.conclusion || stored
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
      if (Array.isArray(parsed)) {
        checkRows.value = parsed
      }
    } catch { /* ignore */ }
  }

  // 恢复结论
  const conclusionData = responses.get(CONCLUSION_KEY)
  if (conclusionData) {
    checkConclusion.value = conclusionData.remark || conclusionData.conclusion || ''
  }
}

watch(() => props.allResponses, restoreFromResponses, { immediate: true })

// ─── CRUD ────────────────────────────────────────────────────────────────────

let rowIdCounter = Date.now()

function createRow(overrides?: Partial<CheckRow>): CheckRow {
  return {
    rowKey: `ck-${++rowIdCounter}`,
    incomeSource: '',
    amount: 0,
    authenticity: '',
    basisCompliance: '',
    classification: '',
    periodAttribution: '',
    taxCompliance: '',
    voucherNo: '',
    evidence: '',
    ocrAttachment: '',
    ...overrides,
  }
}

function updateCell(rowKey: string, field: keyof CheckRow, value: any): void {
  const row = checkRows.value.find(r => r.rowKey === rowKey)
  if (row) {
    ;(row as any)[field] = value
    persistRows()
  }
}

function removeRow(rowKey: string): void {
  checkRows.value = checkRows.value.filter(r => r.rowKey !== rowKey)
  persistRows()
}

async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入收入来源名称', '新增检查项', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：政府补助/债务重组利得/罚款收入...',
    })
    if (value?.trim()) {
      checkRows.value.push(createRow({ incomeSource: value.trim() }))
      persistRows()
    }
  } catch { /* cancelled */ }
}

function persistRows(): void {
  emit('save', STORAGE_KEY, JSON.stringify(checkRows.value))
}

function saveConclusion(val: string): void {
  checkConclusion.value = val
  emit('save', CONCLUSION_KEY, val)
}

// ─── 不合规摘要 ──────────────────────────────────────────────────────────────

const nonComplianceItems = computed(() =>
  checkRows.value.filter(r =>
    r.authenticity === '不合规' ||
    r.basisCompliance === '不合规' ||
    r.classification === '不合规' ||
    r.periodAttribution === '不合规' ||
    r.taxCompliance === '不合规',
  ).map(r => ({
    ...r,
    nonComplianceReason: [
      r.authenticity === '不合规' ? '真实性不合规' : '',
      r.basisCompliance === '不合规' ? '依据不合规' : '',
      r.classification === '不合规' ? '分类不正确' : '',
      r.periodAttribution === '不合规' ? '期间归属不当' : '',
      r.taxCompliance === '不合规' ? '税务处理不合规' : '',
    ].filter(Boolean).join('、'),
  })),
)

const nonComplianceCount = computed(() => nonComplianceItems.value.length)

// ─── UI Helpers ──────────────────────────────────────────────────────────────

function fmtAmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function getRowClassName({ row }: { row: CheckRow }): string {
  if (
    row.authenticity === '不合规' ||
    row.basisCompliance === '不合规' ||
    row.classification === '不合规' ||
    row.periodAttribution === '不合规' ||
    row.taxCompliance === '不合规'
  ) {
    return 'non-compliance-row'
  }
  return ''
}

function handleAiAssist(): void {
  ElMessage.info('AI辅助分类正确性检查评估...')
}

// ─── 抽凭引擎 ────────────────────────────────────────────────────────────────

const showSamplingDialog = ref(false)
const currentYear = computed(() => new Date().getFullYear())

function handleVoucherFilled(payload: any): void {
  const vouchers = payload?.samples ?? []
  for (const v of vouchers) {
    checkRows.value.push(createRow({
      incomeSource: v.summary || v.abstractText || v.voucherNo || '抽凭样本',
      amount: v.amount ?? v.creditAmount ?? 0,
      voucherNo: v.voucherNo || '',
    }))
  }
  showSamplingDialog.value = false
  if (vouchers.length) {
    persistRows()
    ElMessage.success(`已填入 ${vouchers.length} 笔凭证样本`)
  }
}

// ─── 行级OCR（📎附件列 → POST /d4/contract-ocr → ElMessageBox确认 → merge） ─

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
      { confirmButtonText: '填入证据', cancelButtonText: '取消', type: 'info' },
    )

    // merge到evidence字段
    const row = checkRows.value.find(r => r.rowKey === currentOcrRowKey)
    if (row) {
      row.evidence = row.evidence ? `${row.evidence}\n[OCR] ${ocrText}` : `[OCR] ${ocrText}`
      row.ocrAttachment = file.name
      persistRows()
      ElMessage.success('OCR内容已填入审计证据')
    }
  } catch (err: any) {
    if (err !== 'cancel' && err?.message !== 'cancel') {
      ElMessage.error('OCR识别失败：' + (err?.response?.data?.detail || err?.message || '未知错误'))
    }
  }
}
</script>

<style scoped>
.k12-tab-non-operating-check { padding: 12px; font-size: 13px; }

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
.ocr-indicator { color: #67c23a; font-size: 11px; margin-left: 2px; }

.table-actions { display: flex; gap: 8px; margin-top: 12px; }
.conclusion-card { margin-top: 16px; }

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
