<template>
  <div class="k12-tab-detail">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>发生与完整性：</b>各明细项营业外收入真实发生、记录完整，合计与 K12-1 审定数一致；</li>
        <li><b>准确性与分类：</b>各项金额准确、按收入性质恰当分类。</li>
      </ol>
    </el-alert>

    <!-- ═══ Section标题 + AI + 复核 + 导入导出 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <h3>K12-2 营业外收入明细表</h3>
        <el-tag size="small" type="info" effect="plain">{{ detailRows.length }} 行</el-tag>
      </div>
      <div class="header-actions">
        <el-button size="small" type="primary" text :loading="aiLoading" @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <CycleImportExportDropdown
          :wp-id="props.wpId"
          api-prefix="k12"
          sheet="K12-2"
          :disabled="props.isReadonly"
          @imported="emit('imported')"
        />
        <GtReviewTrigger section-id="K12-2-detail" label="💬 复核" />
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>
        逐笔登记本期营业外收入明细，按来源分类（政府补助/债务重组利得/资产盘盈/罚款收入/捐赠利得等）。
        <strong>损益类贷方科目</strong>：金额取贷方发生额。合计行联动K12-1审定表净发生额。
      </p>
    </div>

    <!-- ═══ 跨底稿引用（GtIndexChip） ═══ -->
    <div class="cross-ref-bar">
      <span class="cross-refs-label">关联引用：</span>
      <GtIndexChip value="K12-1" :context-project-id="props.projectId" />
      <GtIndexChip value="K12-4" :context-project-id="props.projectId" />
    </div>

    <!-- ═══ 3区段 Tab（基础 | 分析 | 检查） ═══ -->
    <el-segmented
      v-model="activeSegment"
      :options="segmentOptions"
      size="small"
      class="segment-toggle"
    />

    <!-- ═══ 明细表格 ═══ -->
    <el-table
      :data="detailRows"
      border
      size="small"
      style="width: 100%; font-size: 13px"
      max-height="520"
      show-summary
      :summary-method="getSummaries"
    >
      <el-table-column type="index" label="#" width="42" align="center" />

      <!-- 区段1: 基础 -->
      <template v-if="activeSegment === '基础'">
        <el-table-column prop="incomeSource" label="收入来源" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.incomeSource" size="small" @change="(v: string) => updateCell(row.rowKey, 'incomeSource', v)" />
            <span v-else>{{ row.incomeSource || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="incomeType" label="收入类型" width="120">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.incomeType" size="small" placeholder="—" filterable allow-create @change="(v: string) => updateCell(row.rowKey, 'incomeType', v)">
              <el-option value="与日常活动无关的政府补助" label="与日常活动无关的政府补助" />
              <el-option value="捐赠利得" label="捐赠利得" />
              <el-option value="盘盈利得（不包括存货盘盈及固定资产盘盈）" label="盘盈利得（不含存货及固定资产盘盈）" />
              <el-option value="碳排放配额出售利得" label="碳排放配额出售利得" />
              <el-option value="债务重组利得" label="债务重组利得" />
              <el-option value="罚款收入" label="罚款收入" />
              <el-option value="确实无法支付" label="确实无法支付" />
              <el-option value="其他" label="其他" />
            </el-select>
            <span v-else>{{ row.incomeType || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="counterparty" label="对方单位" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.counterparty" size="small" @change="(v: string) => updateCell(row.rowKey, 'counterparty', v)" />
            <span v-else>{{ row.counterparty || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="amount" label="金额(元)" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.amount" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateCell(row.rowKey, 'amount', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="occurrenceDate" label="发生日期" width="130">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" :model-value="row.occurrenceDate" type="date" size="small" value-format="YYYY-MM-DD" style="width:100%" @change="(v: string) => updateCell(row.rowKey, 'occurrenceDate', v || '')" />
            <span v-else>{{ row.occurrenceDate || '—' }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- 区段2: 分析 -->
      <template v-if="activeSegment === '分析'">
        <el-table-column prop="incomeSource" label="收入来源" min-width="140">
          <template #default="{ row }"><span>{{ row.incomeSource || '—' }}</span></template>
        </el-table-column>
        <el-table-column prop="amount" label="金额" width="120" align="right">
          <template #default="{ row }"><span>{{ fmtAmt(row.amount) }}</span></template>
        </el-table-column>
        <el-table-column prop="proportion" label="占比" width="90" align="right">
          <template #default="{ row }"><span>{{ row.amount && totalAmount > 0 ? ((row.amount / totalAmount) * 100).toFixed(1) + '%' : '—' }}</span></template>
        </el-table-column>
        <el-table-column prop="yoyChange" label="同比变动" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.yoyChange" size="small" :controls="false" :precision="2" style="width:100%" placeholder="%" @change="(v: number | undefined) => updateCell(row.rowKey, 'yoyChange', v ?? 0)" />
            <span v-else>{{ row.yoyChange != null && row.yoyChange !== 0 ? (row.yoyChange * 100).toFixed(1) + '%' : '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="说明" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small" @change="(v: string) => updateCell(row.rowKey, 'remark', v)" />
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- 区段3: 检查 -->
      <template v-if="activeSegment === '检查'">
        <el-table-column prop="incomeSource" label="收入来源" min-width="130">
          <template #default="{ row }"><span>{{ row.incomeSource || '—' }}</span></template>
        </el-table-column>
        <el-table-column prop="basisDocument" label="依据文件" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.basisDocument" size="small" @change="(v: string) => updateCell(row.rowKey, 'basisDocument', v)" />
            <span v-else>{{ row.basisDocument || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="voucherNo" label="凭证号" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small" @change="(v: string) => updateCell(row.rowKey, 'voucherNo', v)" />
            <span v-else>{{ row.voucherNo || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="isOccasional" label="偶发性" width="85">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.isOccasional" size="small" @change="(v: string) => updateCell(row.rowKey, 'isOccasional', v)">
              <el-option value="是" label="是" /><el-option value="否" label="否" />
            </el-select>
            <span v-else>{{ row.isOccasional || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="conclusion" label="结论" width="90">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.conclusion" size="small" @change="(v: string) => updateCell(row.rowKey, 'conclusion', v)">
              <el-option value="合规" label="合规" /><el-option value="存疑" label="存疑" /><el-option value="不合规" label="不合规" />
            </el-select>
            <span v-else>{{ row.conclusion || '—' }}</span>
          </template>
        </el-table-column>
        <!-- 📎 行级OCR列 -->
        <el-table-column label="📎" width="65" align="center">
          <template #default="{ row }">
            <el-button link size="small" :disabled="isReadonly" @click="handleOcrUpload(row.rowKey)">📎</el-button>
            <span v-if="row.ocrAttachment" class="ocr-indicator">✓</span>
          </template>
        </el-table-column>
        <el-table-column prop="checkRemark" label="备注" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.checkRemark" size="small" @change="(v: string) => updateCell(row.rowKey, 'checkRemark', v)" />
            <span v-else>{{ row.checkRemark || '—' }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- 操作列（所有区段） -->
      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-button link size="small" type="danger" @click="removeRow(row.rowKey)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 操作栏 ═══ -->
    <div class="table-actions">
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleAddRow">+ 新增收入明细</el-button>
    </div>

    <!-- OCR file input (隐藏) -->
    <input ref="ocrFileInput" type="file" accept="image/*,.pdf" style="display:none" @change="handleOcrFileSelected" />

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>逐笔登记本期营业外收入明细，损益类取贷方发生额</li>
        <li>按来源分类：政府补助/债务重组利得/资产盘盈/罚款收入/捐赠利得/确实无法支付等</li>
        <li>分析区段自动计算占比和同比变动率</li>
        <li>检查区段核对依据文件/凭证号/偶发性判断</li>
        <li>📎附件列：上传原始证据→OCR自动识别→确认后填入备注字段</li>
        <li>合计行自动聚合，联动K12-1审定表发生额</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K12TabDetail.vue — K12-2 营业外收入明细表（26列3区段，动态行）
 *
 * Spec: .kiro/specs/k12-non-operating-income/ | Task: 6.3
 * Requirements: 3.1-3.4
 *
 * 功能：
 * - 26列拆为3区段Tab切换：基础(6列)|分析(5列)|检查(7列)
 * - 动态行（max 200）+ 按来源分行
 * - 行级OCR（📎列 POST /d4/contract-ocr → ElMessageBox确认 → merge）
 * - GtIndexChip跨底稿引用（K12-1 / K12-4）
 * - 合计行（show-summary）
 */
import { ref, computed, defineAsyncComponent, watch } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { generateK12AiText } from '../../composables/useK12AiText'

const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))
const GtReviewTrigger = defineAsyncComponent(() => import('../../GtReviewTrigger.vue'))
const CycleImportExportDropdown = defineAsyncComponent(() => import('../../shared/CycleImportExportDropdown.vue'))

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  /** 导入完成 → 父宿主重载 allResponses（父绑定 @imported="selfLoad()"） */
  (e: 'imported'): void
}>()

// ─── Detail Row 数据 ─────────────────────────────────────────────────────────

interface DetailRow {
  rowKey: string
  // 基础区段
  incomeSource: string
  incomeType: string
  counterparty: string
  amount: number
  occurrenceDate: string
  // 分析区段
  yoyChange: number
  remark: string
  // 检查区段
  basisDocument: string
  voucherNo: string
  isOccasional: string
  conclusion: string
  checkRemark: string
  ocrAttachment: string
}

const STORAGE_KEY = 'K12-2-detail-rows'

const detailRows = ref<DetailRow[]>([])
const activeSegment = ref('基础')
const segmentOptions = ['基础', '分析', '检查']

// ─── 从 allResponses 恢复数据 ────────────────────────────────────────────────

function restoreFromResponses(): void {
  const responses = props.allResponses
  if (!responses || responses.size === 0) return

  const stored = responses.get(STORAGE_KEY)
  if (stored) {
    try {
      const raw = stored.remark || stored.conclusion || stored
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
      if (Array.isArray(parsed)) {
        detailRows.value = parsed
      }
    } catch { /* ignore */ }
  }
}

watch(() => props.allResponses, restoreFromResponses, { immediate: true })

// ─── CRUD ────────────────────────────────────────────────────────────────────

let rowIdCounter = Date.now()

function createRow(overrides?: Partial<DetailRow>): DetailRow {
  return {
    rowKey: `dt-${++rowIdCounter}`,
    incomeSource: '',
    incomeType: '',
    counterparty: '',
    amount: 0,
    occurrenceDate: '',
    yoyChange: 0,
    remark: '',
    basisDocument: '',
    voucherNo: '',
    isOccasional: '',
    conclusion: '',
    checkRemark: '',
    ocrAttachment: '',
    ...overrides,
  }
}

function updateCell(rowKey: string, field: keyof DetailRow, value: any): void {
  const row = detailRows.value.find(r => r.rowKey === rowKey)
  if (row) {
    ;(row as any)[field] = value
    persistRows()
  }
}

function removeRow(rowKey: string): void {
  detailRows.value = detailRows.value.filter(r => r.rowKey !== rowKey)
  persistRows()
}

async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入收入来源名称', '新增收入明细', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：XX政府补助/XX债务重组利得...',
    })
    if (value?.trim()) {
      detailRows.value.push(createRow({ incomeSource: value.trim() }))
      persistRows()
    }
  } catch { /* cancelled */ }
}

function persistRows(): void {
  emit('save', STORAGE_KEY, JSON.stringify(detailRows.value))
  // P0-5: 写 K12-2-subtotal 供 K12-1 审定表交叉验证读取（此前从不写→K12-1 恒显假差异）
  emit('save', 'K12-2-subtotal', String(totalAmount.value))
}

// ─── 合计 ────────────────────────────────────────────────────────────────────

const totalAmount = computed(() => detailRows.value.reduce((s, r) => s + (r.amount || 0), 0))

function getSummaries({ columns, data }: any): string[] {
  return columns.map((col: any, idx: number) => {
    if (idx === 0) return '合计'
    if (col.property === 'amount') return fmtAmt(totalAmount.value)
    return ''
  })
}

// ─── UI Helpers ──────────────────────────────────────────────────────────────

function fmtAmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const aiLoading = ref(false)

async function handleAiAssist(): Promise<void> {
  if (aiLoading.value) return
  aiLoading.value = true
  try {
    const context: Record<string, unknown> = {
      科目: '6301 营业外收入明细',
      明细笔数: detailRows.value.length,
      合计金额: fmtAmt(totalAmount.value),
      来源分布: detailRows.value
        .map(r => `${r.incomeSource || '未命名'}(${r.incomeType || '—'})=${fmtAmt(r.amount)}`)
        .slice(0, 30)
        .join('；'),
    }
    const content = await generateK12AiText(props.wpId, {
      prompt: '你是资深审计师。请基于营业外收入明细数据，分析各来源占比、异常波动及分类合理性（与日常活动无关计入营业外收入，相关计入其他收益），并提示非经常性损益列报关注点。',
      section: 'K12-2-analysis',
      context,
    })
    if (!content) return
    // 无独立说明字段：以 ElMessageBox 呈现供参考
    await ElMessageBox.alert(content, 'AI 明细分析建议', { confirmButtonText: '知道了' })
  } catch { /* cancelled */ } finally {
    aiLoading.value = false
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
      { confirmButtonText: '填入备注', cancelButtonText: '取消', type: 'info' },
    )

    // merge到checkRemark字段（检查区段的备注）
    const row = detailRows.value.find(r => r.rowKey === currentOcrRowKey)
    if (row) {
      row.checkRemark = row.checkRemark ? `${row.checkRemark}\n[OCR] ${ocrText}` : `[OCR] ${ocrText}`
      row.ocrAttachment = file.name
      persistRows()
      ElMessage.success('OCR内容已填入备注')
    }
  } catch (err: any) {
    if (err !== 'cancel' && err?.message !== 'cancel') {
      ElMessage.error('OCR识别失败：' + (err?.response?.data?.detail || err?.message || '未知错误'))
    }
  }
}
</script>

<style scoped>
.k12-tab-detail { padding: 12px; font-size: var(--wp-font-size, 13px); }

.section-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px;
}
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-left h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; align-items: center; }

.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b;
  padding: 10px 14px; margin-bottom: 12px;
  border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6;
}
.methodology-context p { margin: 0; }

.cross-ref-bar {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  margin-bottom: 12px; padding: 6px 12px;
  background: #f5f7fa; border-radius: 6px;
}
.cross-refs-label { color: #909399; font-size: 12px; white-space: nowrap; }

.segment-toggle { margin-bottom: 12px; }

.ocr-indicator { color: #67c23a; font-size: 11px; margin-left: 2px; }
.table-actions { display: flex; gap: 8px; margin-top: 12px; }

:deep(.el-table) { font-size: var(--wp-font-size, 13px); }

.compile-hint {
  margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary);
  padding: 12px 16px; background: #fafafa;
  border: 1px solid #ebeef5; border-radius: 6px;
}
.compile-hint summary { cursor: pointer; font-weight: 500; color: #303133; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
