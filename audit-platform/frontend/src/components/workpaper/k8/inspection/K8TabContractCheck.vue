<template>
  <div class="k8-contract-check">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>发生与准确性：</b>合同项下销售费用（律师费/咨询费/租赁费/保险费/物业费等）真实发生、金额与合同一致；</li>
        <li><b>截止与分类：</b>按合同履行期间恰当摊销确认，本期应计损益计入正确期间与账户。</li>
      </ol>
    </el-alert>

    <!-- ═══ Section标题 + AI + 复核 ═══ -->
    <div class="section-header">
      <h3>K8-5 合同费用摊销核对表</h3>
      <div class="header-actions">
        <el-tooltip :content="aiAvailable ? 'AI 辅助生成' : 'AI 服务暂不可用'" placement="top">
          <el-button size="small" type="primary" text :loading="aiLoading" :disabled="isReadonly || !aiAvailable" @click="handleAiAssist"><el-icon><MagicStick /></el-icon> AI辅助</el-button>
        </el-tooltip>
        <el-button size="small" text @click="openReviewDialog?.('K8-5-contract-check')">💬 复核</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>检查按合同期摊销的销售费用合同（律师/咨询/租赁/保险/物业等）：核对合同金额、摊销期间及本期<strong>应计损益</strong>与账面<strong>已计损益</strong>是否一致。<br/><strong>合同总月份</strong>=合同期跨月数（含首尾月）；<strong>本期应计月份</strong>=合同期∩摊销期跨月数；<strong>本期应计损益</strong>=合同金额÷合同总月份×本期应计月份；<strong>差异</strong>=应计−已计（|差异|&gt;1元 红色高亮需查明）。</p>
    </div>

    <!-- ═══ 摊销期设置 ═══ -->
    <div class="amort-period-bar">
      <span class="ap-label">摊销期间：</span>
      <el-date-picker :model-value="amortStart" type="date" size="small" value-format="YYYY-MM-DD" :disabled="isReadonly" placeholder="期初" style="width:150px" @change="(v: string) => handlePeriodChange(v, amortEnd)" />
      <span class="ap-sep">至</span>
      <el-date-picker :model-value="amortEnd" type="date" size="small" value-format="YYYY-MM-DD" :disabled="isReadonly" placeholder="期末" style="width:150px" @change="(v: string) => handlePeriodChange(amortStart, v)" />
    </div>

    <!-- ═══ 差异摘要 ═══ -->
    <el-alert v-if="diffWarnings.length > 0" type="error" :closable="false" show-icon style="margin-bottom:10px">
      <template #title>⚠️ {{ diffWarnings.length }} 项应计损益与账面已计存在差异（&gt;1元）</template>
      <template #default>
        <span v-for="(r, i) in diffWarnings" :key="r.rowKey" class="diff-tag">{{ r.projectName || `合同${i + 1}` }}(差异{{ fmtAmt(r.diff) }}){{ i < diffWarnings.length - 1 ? '、' : '' }}</span>
      </template>
    </el-alert>

    <!-- ═══ 合同摊销核对表格 ═══ -->
    <el-table :data="rows" border size="small" style="width:100%;font-size:13px" max-height="480" :row-class-name="rowClassName">
      <el-table-column type="index" label="#" width="42" align="center" fixed />
      <el-table-column label="项目" min-width="110" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.projectName" size="small" placeholder="如 律师费" @change="(v: string) => updateCell(row.rowKey, 'projectName', v)" />
          <span v-else>{{ row.projectName || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="对方单位" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.counterparty" size="small" @change="(v: string) => updateCell(row.rowKey, 'counterparty', v)" />
          <span v-else>{{ row.counterparty || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="合同内容" min-width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.contractContent" size="small" @change="(v: string) => updateCell(row.rowKey, 'contractContent', v)" />
          <span v-else>{{ row.contractContent || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="合同金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.contractAmount" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateCell(row.rowKey, 'contractAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.contractAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="实际开票方" min-width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.invoiceParty" size="small" @change="(v: string) => updateCell(row.rowKey, 'invoiceParty', v)" />
          <span v-else>{{ row.invoiceParty || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="支付条件" min-width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.paymentTerm" size="small" @change="(v: string) => updateCell(row.rowKey, 'paymentTerm', v)" />
          <span v-else>{{ row.paymentTerm || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="合同开始" width="130">
        <template #default="{ row }">
          <el-date-picker v-if="!isReadonly" :model-value="row.startDate" type="date" size="small" value-format="YYYY-MM-DD" style="width:100%" @change="(v: string) => updateCell(row.rowKey, 'startDate', v)" />
          <span v-else>{{ row.startDate || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="合同结束" width="130">
        <template #default="{ row }">
          <el-date-picker v-if="!isReadonly" :model-value="row.endDate" type="date" size="small" value-format="YYYY-MM-DD" style="width:100%" @change="(v: string) => updateCell(row.rowKey, 'endDate', v)" />
          <span v-else>{{ row.endDate || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="合同总月份" width="90" align="right">
        <template #default="{ row }">
          <el-tooltip content="公式：合同期跨月数（含首尾月）" placement="top">
            <span class="formula-cell formula-underline">{{ row.totalMonths }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="本期应计月份" width="105" align="right">
        <template #default="{ row }">
          <el-tooltip content="公式：合同期∩摊销期跨月数（可手工覆盖）" placement="top">
            <el-input-number v-if="!isReadonly" :model-value="row.accrualMonths" size="small" :controls="false" :precision="0" :min="0" style="width:80px" @change="(v: number | undefined) => updateCell(row.rowKey, 'accrualMonths', v ?? 0)" />
            <span v-else class="formula-cell">{{ row.accrualMonths }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="本期应计损益" width="120" align="right">
        <template #default="{ row }">
          <el-tooltip content="公式：合同金额÷总月份×应计月份" placement="top">
            <span class="formula-cell formula-underline">{{ fmtAmt(row.accruedPL) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="本期已计损益" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.bookedPL" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateCell(row.rowKey, 'bookedPL', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.bookedPL) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="差异" width="110" align="right">
        <template #default="{ row }">
          <el-tooltip content="公式：应计−已计" placement="top">
            <span class="formula-cell formula-underline" :class="{ 'abnormal-highlight': Math.abs(row.diff) > 1 }">{{ fmtAmt(row.diff) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="合同索引" min-width="90">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.contractIndex" size="small" @change="(v: string) => updateCell(row.rowKey, 'contractIndex', v)" />
          <span v-else>{{ row.contractIndex || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="凭证索引" min-width="90">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.voucherIndex" size="small" @change="(v: string) => updateCell(row.rowKey, 'voucherIndex', v)" />
          <span v-else>{{ row.voucherIndex || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="审计结论" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.conclusion" size="small" @change="(v: string) => updateCell(row.rowKey, 'conclusion', v)" />
          <span v-else>{{ row.conclusion || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="📎" width="70" align="center">
        <template #default="{ row }">
          <el-button link size="small" :disabled="isReadonly" @click="handleOcrUpload(row.rowKey)">📎</el-button>
          <span v-if="row.ocrAttachment" class="ocr-indicator">✓</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="88" align="center" fixed="right">
        <template #default="{ row }">
          <el-button link size="small" type="primary" @click="openAmortDialog(row)">编辑</el-button>
          <el-button link size="small" type="danger" @click="removeRow(row.rowKey)">删</el-button>
        </template>
      </el-table-column>
      <template #append>
        <div class="table-total">
          合计　合同金额：{{ fmtAmt(totals.contractAmount) }}　应计损益：{{ fmtAmt(totals.accruedPL) }}　已计损益：{{ fmtAmt(totals.bookedPL) }}　差异：{{ fmtAmt(totals.diff) }}
        </div>
      </template>
    </el-table>

    <!-- ═══ 操作栏 ═══ -->
    <div class="table-actions">
      <el-button size="small" type="primary" @click="openAmortDialog(null)">✏️ 引导录入</el-button>
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleAddContract">+ 新增合同</el-button>
      <el-button size="small" plain :disabled="isReadonly" @click="showSamplingDialog = true">🎲 抽凭</el-button>
      <el-button v-if="diffWarnings.length > 0" size="small" type="danger" plain :disabled="isReadonly" @click="pushDiffToK83">推送差异至 K8-3（{{ diffWarnings.length }}）</el-button>
    </div>

    <!-- ═══ 抽凭引擎 Dialog ═══ -->
    <el-dialog v-model="showSamplingDialog" title="⚡ 抽凭引擎（科目 6601 销售费用-合同检查）" width="720px" :close-on-click-modal="false" destroy-on-close>
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

    <!-- OCR file input (隐藏) -->
    <input ref="ocrFileInput" type="file" accept="image/*,.pdf" style="display:none" @change="handleOcrFileSelected" />

    <!-- ═══ 引导式录入弹窗 ═══ -->
    <K8ContractAmortDialog
      v-model:visible="amortDialogVisible"
      :row="editingRow"
      :amort-start="amortStart"
      :amort-end="amortEnd"
      :is-readonly="isReadonly"
      @save="onAmortDialogSave"
    />

    <!-- ═══ 检查结论 ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header><span>合同检查结论</span></template>
      <el-input
        :model-value="conclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="请填写合同费用摊销核对结论（应计与已计是否一致、差异原因及调整建议）..."
        @blur="(e: FocusEvent) => saveConclusion((e.target as HTMLTextAreaElement)?.value ?? '')"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>适用按合同期摊销的费用：律师费/咨询费/租赁费/保险费/物业费等</li>
        <li>本期应计损益=合同金额÷合同总月份×本期应计月份（直线摊销）</li>
        <li>本期应计月份默认取合同期∩摊销期跨月数，可手工覆盖</li>
        <li>差异=应计−已计，|差异|&gt;1元红色标记并查明原因（多计/少计/未及时摊销）</li>
        <li>支持行级📎OCR核查原始合同，抽凭引擎（科目6601）核查凭证</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K8TabContractCheck.vue — K8-5 销售费用合同费用摊销核对表
 *
 * 🔴 重建：原用通用「合规检查」模型（金额匹配/审批/真实性），与致同源模板不符。
 * 源模板 K8-5 为合同费用摊销核对表（合同总月份/本期应计月份/应计损益 vs 已计/差异）。
 * 复用 useK8ContractAmortization（纯摊销计算）。
 */
import { ref, toRef, inject, computed, defineAsyncComponent } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useK8ContractAmortization, type K8AmortRow } from '@/components/workpaper/composables/useK8ContractAmortization'
import { useK8AiGenerate } from '@/components/workpaper/composables/useK8AiGenerate'
import http from '@/utils/http'
import type { Ref } from 'vue'

const GtVoucherSamplingEngine = defineAsyncComponent(
  () => import('../../voucher-sampling/GtVoucherSamplingEngine.vue'),
)
const K8ContractAmortDialog = defineAsyncComponent(() => import('./K8ContractAmortDialog.vue'))

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

// ═══ Composable ═══
const {
  rows,
  conclusion,
  amortStart,
  amortEnd,
  diffWarnings,
  diffAdjustmentDrafts,
  totals,
  addRow,
  addRowReturnKey,
  applyRowPatch,
  removeRow,
  updateCell,
  setAmortPeriod,
  saveConclusion,
} = useK8ContractAmortization({
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  projectId: toRef(props, 'projectId'),
  wpId: toRef(props, 'wpId'),
  year: toRef(props, 'year') as Ref<number | undefined>,
  isReadonly: toRef(props, 'isReadonly'),
  onSave: (itemId, value) => emit('save', itemId, typeof value === 'string' ? { remark: value } : { remark: JSON.stringify(value) }),
})

// ═══ AI 辅助 ═══
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useK8AiGenerate({
  wpId: toRef(props, 'wpId'),
})
async function handleAiAssist(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'k8-contract-amort-conclusion',
    conclusion.value || '',
    {
      合同笔数: rows.value.length,
      差异笔数: diffWarnings.value.length,
      应计损益合计: totals.value.accruedPL,
      已计损益合计: totals.value.bookedPL,
      任务: '请为销售费用合同费用摊销核对表形成检查结论（应计损益与账面已计是否一致、差异原因及是否需调整）',
    },
    'AI 生成 · 合同摊销核对结论',
  )
  if (text) saveConclusion(text)
}

// ═══ 摊销期变更 ═══
function handlePeriodChange(start: string, end: string): void {
  setAmortPeriod(start || amortStart.value, end || amortEnd.value)
}

// ═══ 新增合同（弹窗输入名称） ═══
async function handleAddContract(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入合同费用项目名称', '新增合同', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：律师费 / 咨询费 / 租赁费',
    })
    if (value?.trim()) addRow(value.trim())
  } catch { /* cancelled */ }
}

// ═══ 引导式录入弹窗（点点点，17列宽表）═══
const amortDialogVisible = ref(false)
const editingRow = ref<K8AmortRow | null>(null)
function openAmortDialog(row: K8AmortRow | null): void {
  editingRow.value = row
  amortDialogVisible.value = true
}
function onAmortDialogSave(rowKey: string | null, patch: any): void {
  const key = rowKey ?? addRowReturnKey(patch.projectName || '')
  if (key) applyRowPatch(key, patch)
}

// ═══ 差异 → K8-3 调整分录推送（append + 去重标记）═══
function pushDiffToK83(): void {
  if (props.isReadonly) return
  const drafts = diffAdjustmentDrafts.value
  if (!drafts.length) { ElMessage.info('无摊销差异，无需推送'); return }
  // 读现有 K8-3 分录，按摘要去重后追加
  let existing: any[] = []
  const raw = props.allResponses.get('K8-3-adj-entries')?.remark
  try { const p = typeof raw === 'string' ? JSON.parse(raw) : raw; if (Array.isArray(p)) existing = p } catch { /* ignore */ }
  const existSummaries = new Set(existing.map((e: any) => e.summary))
  let added = 0
  let nextId = existing.length + 1
  for (const d of drafts) {
    if (existSummaries.has(d.summary)) continue
    existing.push({
      id: `entry-k85-${Date.now()}-${nextId++}`,
      seq: existing.length + 1,
      category: d.category,
      summary: d.summary,
      reportItem: d.reportItem,
      accountName: d.accountName,
      noteItem: d.noteItem,
      debitAmount: d.debitAmount,
      creditAmount: d.creditAmount,
      indexRef: d.indexRef,
      remark: d.remark,
    })
    added++
  }
  existing.forEach((e: any, i: number) => { e.seq = i + 1 })
  emit('save', 'K8-3-adj-entries', { remark: JSON.stringify(existing) })
  ElMessage.success(added > 0 ? `已推送 ${added} 条摊销差异至 K8-3 调整分录（可去 K8-3 复核借贷）` : '差异分录已存在于 K8-3，未重复推送')
}

// ═══ UI Helpers ═══
function rowClassName({ row }: { row: K8AmortRow }): string {
  return Math.abs(row.diff) > 1 ? 'diff-row' : ''
}

function fmtAmt(v: number | null | undefined): string {
  if (v == null || Math.abs(v) < 0.005) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ═══ 抽凭引擎 ═══
const showSamplingDialog = ref(false)
function handleVoucherFilled(payload: any): void {
  const vouchers = payload?.samples ?? []
  for (const v of vouchers) {
    addRow(v.summary || v.voucherNo || '抽凭样本')
  }
  showSamplingDialog.value = false
  if (vouchers.length) ElMessage.success(`已填入${vouchers.length}笔凭证样本`)
}

// ═══ 行级OCR ═══
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
  input.value = ''
  try {
    const formData = new FormData()
    formData.append('file', file)
    ElMessage.info('正在OCR识别...')
    const res = await http.post('/api/d4/contract-ocr', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    const ocrText = res.data?.data?.text || res.data?.text || ''
    if (!ocrText) { ElMessage.warning('OCR未识别到文字内容'); return }
    await ElMessageBox.confirm(
      `OCR识别结果：\n\n${ocrText.slice(0, 500)}${ocrText.length > 500 ? '...' : ''}`,
      'OCR识别确认',
      { confirmButtonText: '填入合同内容', cancelButtonText: '取消', type: 'info' },
    )
    const row = rows.value.find((r: K8AmortRow) => r.rowKey === currentOcrRowKey)
    if (row) {
      const merged = row.contractContent ? `${row.contractContent}\n[OCR] ${ocrText}` : `[OCR] ${ocrText}`
      updateCell(currentOcrRowKey, 'contractContent', merged)
      updateCell(currentOcrRowKey, 'ocrAttachment', file.name)
      ElMessage.success('OCR内容已填入合同内容')
    }
  } catch (err: any) {
    if (err !== 'cancel' && err?.message !== 'cancel') {
      ElMessage.error('OCR识别失败：' + (err?.response?.data?.detail || err?.message || '未知错误'))
    }
  }
}
</script>

<style scoped>
.k8-contract-check { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; align-items: center; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }
.amort-period-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; }
.ap-label { font-size: var(--wp-font-size, 13px); color: #606266; }
.ap-sep { color: #909399; }
.diff-tag { font-size: 12px; color: #f56c6c; }
.formula-cell { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #303133; }
.formula-underline { border-bottom: 1px dashed #909399; cursor: help; }
.abnormal-highlight { color: #f56c6c !important; font-weight: 600; }
.ocr-indicator { color: #67c23a; font-size: 11px; margin-left: 2px; }
.table-actions { display: flex; gap: 8px; margin-top: 12px; }
.table-total { padding: 6px 12px; text-align: right; font-size: 12px; color: var(--el-text-color-regular); font-weight: 600; }
.conclusion-card { margin-top: 16px; }
:deep(.diff-row) { background-color: #fef2f2 !important; }
:deep(.diff-row:hover > td) { background-color: #fee2e2 !important; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; }
.compile-hint summary { cursor: pointer; font-weight: 500; color: #303133; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
