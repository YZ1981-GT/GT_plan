<template>
  <div class="k10-tab-other-income-check">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>发生：</b>记录的其他收益确已发生且与本期相关；</li>
        <li><b>完整性与准确性：</b>其他收益记录完整、金额准确，无虚列或漏记；</li>
        <li><b>分类与列报：</b>与资产/收益相关政府补助分类恰当、列报披露充分。</li>
      </ol>
    </el-alert>

    <!-- ═══ 标题 + 按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <h3 class="section-title">K10-6 其他收益检查表</h3>
        <el-tag type="success" effect="dark" size="small" class="account-badge">
          分类正确性·确认条件·覆盖率
        </el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" type="primary" plain @click="handleImportFromDetail">
          <el-icon><Download /></el-icon> 从K10-2带入
        </el-button>
        <el-button size="small" @click="handleVoucherSampling">
          <el-icon><Tickets /></el-icon> 抽凭引擎
        </el-button>
        <GtReviewTrigger section-id="K10-6-other-income-check" label="💬 复核" />
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>其他收益分类正确性核查：</strong>
        与日常活动相关的政府补助 → 其他收益(6117)；与日常活动无关 → 营业外收入(6301/K12)。
        核查要点：①分类正确性（是否与日常活动相关） ②确认条件是否满足（已收到/权利确定）
        ③金额准确性。检查覆盖率 = 检查金额合计 / K10-2明细合计。
      </div>
    </div>

    <!-- ═══ 跨底稿引用 ═══ -->
    <div class="cross-ref-bar">
      <span class="cross-refs-label">关联引用：</span>
      <GtIndexChip value="wp:K10-1" :context-project-id="props.projectId" />
      <GtIndexChip value="wp:K10-2" :context-project-id="props.projectId" />
      <GtIndexChip value="wp:K10-4" :context-project-id="props.projectId" />
      <GtIndexChip value="wp:K12" :context-project-id="props.projectId" />
    </div>

    <!-- ④ 分类错配提示（分类为营业外收入 → 应重分类至 6301/K12） -->
    <div v-if="checks.misclassifiedRows.value.length > 0" class="non-compliant-alert">
      <el-alert type="warning" :closable="false" show-icon>
        <template #title>
          {{ checks.misclassifiedRows.value.length }} 项分类为「营业外收入」，与日常活动无关，应重分类至营业外收入(6301) → K12，请在 K10-3 编制重分类调整（RJE）
        </template>
      </el-alert>
    </div>

    <!-- ⑤ 覆盖率不足告警 -->
    <div v-if="detailTotal > 0 && coveragePercent < 80" class="non-compliant-alert">
      <el-alert type="warning" :closable="false" show-icon
        :title="`检查覆盖率 ${coveragePercent}% 低于建议阈值 80%，建议扩大检查范围或从 K10-2 带入更多检查项`" />
    </div>

    <!-- ═══ 不合规红色提示 ═══ -->
    <div v-if="checks.incomeCheckSummary.value.nonCompliant > 0" class="non-compliant-alert">
      <el-alert
        type="error"
        :closable="false"
        show-icon
      >
        <template #title>
          存在 {{ checks.incomeCheckSummary.value.nonCompliant }} 项不合规：{{ checks.incomeCheckSummary.value.nonCompliantItems.join('、') }}
        </template>
      </el-alert>
    </div>

    <!-- ═══ 覆盖率显示 ═══ -->
    <div class="coverage-bar">
      <span class="coverage-label">检查覆盖率：</span>
      <el-progress
        :percentage="coveragePercent"
        :color="coveragePercent >= 80 ? '#67c23a' : coveragePercent >= 50 ? '#e6a23c' : '#f56c6c'"
        :stroke-width="16"
        :text-inside="true"
        style="width: 200px"
      />
      <span class="coverage-text">
        {{ fmtAmount(checkAmountTotal) }} / {{ fmtAmount(detailTotal) }}
      </span>
    </div>

    <!-- ═══ 检查表格 ═══ -->
    <el-table
      :data="checks.incomeCheckRows.value"
      border
      size="small"
      style="width: 100%"
      empty-text="暂无其他收益检查项目"
      :row-class-name="incomeCheckRowClass"
      class="check-table"
    >
      <el-table-column prop="checkItem" label="检查项目" min-width="140">
        <template #default="{ row }">
          <span class="project-name">{{ row.checkItem || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="检查金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!props.isReadonly && row.isEditable"
            :model-value="row.checkAmount"
            :controls="false"
            size="small"
            style="width: 100%"
            @change="(val: number | undefined) => checks.updateIncomeCheckCell(row.rowKey, 'checkAmount', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.checkAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="分类" width="140">
        <template #default="{ row }">
          <el-select
            v-if="!props.isReadonly && row.isEditable"
            :model-value="row.classification"
            size="small"
            style="width: 100%"
            placeholder="选择分类"
            @change="(val: string) => checks.updateIncomeCheckCell(row.rowKey, 'classification', val)"
          >
            <el-option label="其他收益(6117)" value="其他收益" />
            <el-option label="营业外收入(6301)" value="营业外收入" />
          </el-select>
          <span v-else>{{ row.classification || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="分类正确性" width="120" align="center">
        <template #default="{ row }">
          <el-select
            v-if="!props.isReadonly && row.isEditable"
            :model-value="row.classificationCorrect"
            size="small"
            style="width: 100%"
            @change="(val: string) => checks.updateIncomeCheckCell(row.rowKey, 'classificationCorrect', val)"
          >
            <el-option v-for="opt in checkOptions" :key="opt" :label="opt" :value="opt" />
          </el-select>
          <el-tag v-else :type="statusTagType(row.classificationCorrect)" size="small">{{ row.classificationCorrect }}</el-tag>
        </template>
      </el-table-column>

      <el-table-column label="确认条件" width="120" align="center">
        <template #default="{ row }">
          <el-select
            v-if="!props.isReadonly && row.isEditable"
            :model-value="row.conditionMet"
            size="small"
            style="width: 100%"
            @change="(val: string) => checks.updateIncomeCheckCell(row.rowKey, 'conditionMet', val)"
          >
            <el-option v-for="opt in checkOptions" :key="opt" :label="opt" :value="opt" />
          </el-select>
          <el-tag v-else :type="statusTagType(row.conditionMet)" size="small">{{ row.conditionMet }}</el-tag>
        </template>
      </el-table-column>

      <el-table-column label="总体结论" width="140" align="center">
        <template #default="{ row }">
          <el-select
            v-if="!props.isReadonly && row.isEditable"
            :model-value="row.overallStatus"
            size="small"
            style="width: 100%"
            @change="(val: string) => checks.updateIncomeCheckCell(row.rowKey, 'overallStatus', val)"
          >
            <el-option v-for="opt in checkOptions" :key="opt" :label="opt" :value="opt" />
          </el-select>
          <el-tag v-else :type="statusTagType(row.overallStatus)" size="small">{{ row.overallStatus }}</el-tag>
          <!-- ③ 建议（与当前不一致时可一键采纳） -->
          <div v-if="!props.isReadonly && row.isEditable && statusDiffers(row)" class="suggest-row">
            <span class="suggest-label">建议:</span>
            <el-tag :type="statusTagType(suggestedStatus(row))" size="small" effect="plain">{{ suggestedStatus(row) }}</el-tag>
            <el-button size="small" link type="primary" @click="adoptSuggestion(row)">采纳</el-button>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="备注" min-width="140">
        <template #default="{ row }">
          <el-input
            v-if="!props.isReadonly && row.isEditable"
            :model-value="row.remark"
            size="small"
            placeholder="备注"
            @change="(val: string) => checks.updateIncomeCheckCell(row.rowKey, 'remark', val)"
          />
          <span v-else>{{ row.remark || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 📎 附件列 -->
      <el-table-column label="📎" width="60" align="center">
        <template #default="{ row }">
          <el-upload
            v-if="!props.isReadonly"
            :show-file-list="false"
            :auto-upload="false"
            accept=".pdf,.png,.jpg,.jpeg"
            @change="(file: any) => handleOCR(row, file)"
          >
            <el-button size="small" link type="primary">📎</el-button>
          </el-upload>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column v-if="!props.isReadonly" label="" width="60" align="center">
        <template #default="{ row }">
          <el-button v-if="row.isEditable" type="danger" size="small" link @click="checks.removeRow(row.rowKey)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 新增按钮 ═══ -->
    <div v-if="!props.isReadonly" class="add-row-bar">
      <el-button size="small" type="primary" plain @click="handleAddRow">
        + 新增检查项目
      </el-button>
      <el-button size="small" plain :disabled="checks.incomeCheckRows.value.length === 0" @click="applyAllSuggestions">
        按判断填充总体结论
      </el-button>
    </div>

    <!-- ═══ 统计摘要 ═══ -->
    <div class="summary-stats">
      <el-tag type="success" size="small" effect="plain">
        合规: {{ checks.incomeCheckSummary.value.compliant }}
      </el-tag>
      <el-tag type="danger" size="small" effect="plain">
        不合规: {{ checks.incomeCheckSummary.value.nonCompliant }}
      </el-tag>
      <el-tag type="info" size="small" effect="plain">
        不适用: {{ checks.incomeCheckSummary.value.notApplicable }}
      </el-tag>
      <el-tag size="small" effect="plain">
        合计: {{ checks.incomeCheckSummary.value.total }} 项
      </el-tag>
    </div>

    <!-- ═══ 检查说明与结论（AI辅助） ═══ -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="note-card-header">
          <span>检查说明与结论</span>
          <el-button size="small" type="primary" text :loading="aiLoading" @click="handleAI">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="noteText"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="props.isReadonly"
        placeholder="填写其他收益检查说明与结论（分类正确性6117 vs 6301、确认条件、覆盖率及总体结论）..."
        @change="handleNoteSave"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="k10-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>分类正确性：与日常活动相关 → 其他收益(6117)；与日常活动无关 → 营业外收入(6301/K12)</li>
        <li>日常活动相关判断：补助用于日常经营活动（如研发支出/稳岗补贴/即征即退）= 其他收益</li>
        <li>确认条件：已收到或有确凿证据表明能够收到；金额能可靠计量</li>
        <li>覆盖率建议≥80%（检查金额合计/K10-2明细合计）</li>
        <li>📎列可上传凭证，OCR识别后自动填入备注</li>
        <li>抽凭引擎（科目6117）可批量生成抽样方案，选样后凭证号回填至第一检查行备注</li>
      </ul>
    </details>

    <!-- ═══ 抽凭引擎Dialog（科目 6117，wrap el-dialog + @filled 范式，对齐 K4/K8/G6） ═══ -->
    <el-dialog
      v-model="voucherDialogVisible"
      title="⚡ 抽凭引擎（科目 6117 其他收益）"
      width="720px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <GtVoucherSamplingEngine
        v-if="voucherDialogVisible && props.wpId && props.projectId"
        :project-id="props.projectId"
        :workpaper-id="props.wpId"
        account-code="6117"
        phase="final"
        :year="currentYear"
        @filled="handleSampleFilled"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * K10TabOtherIncomeCheck — K10-6 其他收益综合检查表
 *
 * Spec: .kiro/specs/k10-other-income/
 * Task: 4.5
 * Requirements: 5.1-5.4
 *
 * 功能：
 * - 逐项检查：分类正确性/确认条件/总体结论
 * - 关键逻辑：与日常活动相关→6117其他收益, 与日常活动无关→6301营业外收入(K12)
 * - 覆盖率显示（检查金额合计/明细合计 %）
 * - 📎附件列（行级OCR）
 * - 不合规红色摘要提示
 * - 抽凭引擎(GtVoucherSamplingEngine dialog，科目 6117，@filled 回填至检查行备注)
 * - Dropdown选项：合规/不合规/不适用
 */
import { computed, defineAsyncComponent, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, Tickets, Download } from '@element-plus/icons-vue'
import { useK10Checks, deriveOverallStatus, type CheckStatus } from '../../composables/useK10Checks'
import { parseNum, calcSubtotal } from '../../composables/useK10FormulaEngine'
import { api } from '@/services/apiProxy'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const GtVoucherSamplingEngine = defineAsyncComponent(
  () => import('../../voucher-sampling/GtVoucherSamplingEngine.vue')
)
const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  year?: number
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
}>()

// ─── Composables ─────────────────────────────────────────────────────────────

const checks = useK10Checks({
  allResponses: computed(() => props.allResponses),
  projectId: computed(() => props.projectId),
  wpId: computed(() => props.wpId),
  sheetKey: 'K10-6',
  isReadonly: computed(() => props.isReadonly),
  onSave: (itemId, value) => emit('save', itemId, value),
})

// ─── Constants ───────────────────────────────────────────────────────────────

const checkOptions: CheckStatus[] = ['合规', '不合规', '不适用']

// ─── UI State ────────────────────────────────────────────────────────────────

const voucherDialogVisible = ref(false)
const currentYear = computed<number>(() => props.year && props.year > 0 ? props.year : new Date().getFullYear())

// ─── Computed: 覆盖率 ────────────────────────────────────────────────────────

const checkAmountTotal = computed(() =>
  calcSubtotal(checks.incomeCheckRows.value.map(r => r.checkAmount))
)

const detailTotal = computed(() => {
  const raw = props.allResponses.get('K10-2-subtotal')
  return parseNum(raw?.remark ?? raw?.conclusion ?? 0)
})

const coveragePercent = computed(() => {
  if (!detailTotal.value || detailTotal.value === 0) return 0
  const rate = (checkAmountTotal.value / detailTotal.value) * 100
  return Math.min(Math.round(rate * 10) / 10, 100)
})

// ─── Handlers ────────────────────────────────────────────────────────────────

function fmtAmount(val: number | undefined | null): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function statusTagType(status: CheckStatus): 'success' | 'danger' | 'info' {
  if (status === '合规') return 'success'
  if (status === '不合规') return 'danger'
  return 'info'
}

function incomeCheckRowClass({ row }: { row: any }): string {
  if (row.overallStatus === '不合规') return 'non-compliant-row'
  return ''
}

/** ① 从 K10-2 明细带入检查项 */
function handleImportFromDetail(): void {
  const added = checks.importIncomeChecksFromDetail()
  if (added > 0) ElMessage.success(`已从 K10-2 明细带入 ${added} 项检查项目`)
  else ElMessage.info('无可带入项（K10-2 无明细或检查项已存在）')
}

/** ③ 总体结论建议（由分类正确性+确认条件派生） */
function suggestedStatus(row: any): CheckStatus {
  return deriveOverallStatus(row.classificationCorrect, row.conditionMet)
}
function statusDiffers(row: any): boolean {
  return row.overallStatus !== suggestedStatus(row)
}
function adoptSuggestion(row: any): void {
  checks.updateIncomeCheckCell(row.rowKey, 'overallStatus', suggestedStatus(row))
}
/** 一键按判断填充所有行的总体结论 */
function applyAllSuggestions(): void {
  for (const row of checks.incomeCheckRows.value) {
    const s = suggestedStatus(row)
    if (row.overallStatus !== s) checks.updateIncomeCheckCell(row.rowKey, 'overallStatus', s)
  }
  ElMessage.success('已按分类正确性/确认条件填充总体结论')
}

/** 新增行 */
async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入检查项目名称',
      '新增其他收益检查项',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPlaceholder: '如：研发补助-XX公司...',
        inputValidator: (val: string) => {
          if (!val || !val.trim()) return '请输入检查项目名称'
          return true
        },
      },
    )
    checks.addIncomeCheckRow(value.trim())
  } catch {
    // 用户取消
  }
}

/** 📎行级OCR处理 */
async function handleOCR(row: any, file: any): Promise<void> {
  if (!file?.raw) return
  const formData = new FormData()
  formData.append('file', file.raw)
  try {
    const res = await api.post('/d4/contract-ocr', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    const ocrText = res?.data?.text || res?.text || ''
    if (ocrText) {
      await ElMessageBox.confirm(
        `OCR识别结果：\n${ocrText.slice(0, 200)}...\n\n是否填入备注？`,
        'OCR识别',
        { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' },
      )
      checks.updateIncomeCheckCell(row.rowKey, 'remark', ocrText.trim())
      ElMessage.success('已填入备注')
    } else {
      ElMessage.warning('OCR未识别到内容')
    }
  } catch {
    // 用户取消或请求失败
  }
}

function handleVoucherSampling(): void {
  voucherDialogVisible.value = true
}

/**
 * 抽凭引擎 @filled 回调（payload: { samples, phase, fillMode, method }）。
 * K10-6 抽凭为整表级（工具栏按钮），选样后将凭证号回填到第一检查行的备注；
 * 若尚无检查行则提示用户先新增检查项。
 */
function handleSampleFilled(payload: { samples?: any[] } | any): void {
  voucherDialogVisible.value = false
  const samples: any[] = payload?.samples ?? []
  if (samples.length === 0) return
  // ② 每笔抽样凭证生成一条检查行（贡献覆盖率），checkItem=业务内容/对方，checkAmount=贷方(收益增加)
  let created = 0
  for (const s of samples) {
    const ref = s.voucherNo || s.voucher_no || s.ref || ''
    const summary = s.summary || s.business || s.abstract || s.counterpartAccount || s.counterparty || ''
    const amount = Number(s.creditAmount ?? s.credit_amount ?? s.amount ?? s.debitAmount ?? 0)
    const checkItem = summary || (ref ? `凭证 ${ref}` : `抽样凭证`)
    checks.addIncomeCheckRowFull({
      checkItem,
      checkAmount: Math.abs(amount),
      classification: '其他收益',
      remark: ref ? `抽凭：${ref}` : '',
    })
    created++
  }
  ElMessage.success(`已选取 ${created} 笔凭证并生成检查行（计入覆盖率）`)
}

// ─── 检查说明 + AI ───────────────────────────────────────────────────────────
const noteText = ref('')
const aiLoading = ref(false)

function loadNote(): void {
  const saved = props.allResponses.get('K10-6-note')
  if (saved) noteText.value = (saved.remark ?? saved.conclusion ?? '') as string
}

function handleNoteSave(): void {
  emit('save', 'K10-6-note', { remark: noteText.value })
}

async function handleAI(): Promise<void> {
  if (!props.wpId) return
  aiLoading.value = true
  try {
    const s = checks.incomeCheckSummary.value
    const ctx = {
      检查覆盖率: `${coveragePercent.value}%`,
      检查金额合计: String(checkAmountTotal.value),
      明细合计: String(detailTotal.value),
      合规项: String(s.compliant),
      不合规项: String(s.nonCompliant),
      不合规明细: (s.nonCompliantItems || []).join('、') || '无',
    }
    const res = await api.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'K10-6-note',
      prompt: '为K10其他收益检查表生成检查说明与结论：分类正确性(6117其他收益 vs 6301营业外收入)、确认条件满足情况、检查覆盖率及总体结论。',
      existingContent: noteText.value,
      context: ctx,
    })
    const content = (res?.data?.content ?? res?.content ?? '') as string
    if (content) { noteText.value = content; handleNoteSave(); ElMessage.success('AI生成完成') }
    else ElMessage.warning('AI未返回内容，请手动填写')
  } catch { ElMessage.warning('AI生成失败，请手动填写') } finally { aiLoading.value = false }
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  checks.initFromResponses()
  loadNote()
})
</script>

<style scoped>
.k10-tab-other-income-check { padding: 12px; font-size: var(--wp-font-size, 13px); }

.section-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px; flex-wrap: wrap; gap: 8px;
}
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; }
.account-badge { font-size: 11px; }

.methodology-context {
  background: linear-gradient(135deg, #fffbe6 0%, #fff8e1 100%);
  border-left: 3px solid #e6a23c;
  padding: 8px 12px; margin-bottom: 12px;
  border-radius: 0 4px 4px 0; font-size: 12px; color: #8b6914;
}
.methodology-text strong { color: #c77d00; }

.non-compliant-alert { margin-bottom: 12px; }

/* 覆盖率 */
.coverage-bar {
  display: flex; align-items: center; gap: 12px;
  margin-bottom: 12px; padding: 8px 12px;
  background: #f5f7fa; border-radius: 6px;
}
.coverage-label { font-size: 12px; color: #606266; white-space: nowrap; }
.coverage-text { font-size: 12px; color: #909399; }

.check-table { font-size: var(--wp-font-size, 13px); }
.check-table :deep(.non-compliant-row) { background: #fef0f0 !important; }
.project-name { font-weight: 500; }

.cross-ref-bar {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  margin-bottom: 12px; padding: 6px 12px;
  background: #f5f7fa; border-radius: 6px;
}
.cross-refs-label { color: #909399; font-size: 12px; white-space: nowrap; }

.suggest-row { display: flex; align-items: center; justify-content: center; gap: 4px; margin-top: 4px; }
.suggest-label { font-size: 11px; color: #909399; }

.add-row-bar { margin-top: 12px; }

.summary-stats {
  display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; align-items: center;
}

.k10-details-tip {
  margin-top: 16px; padding: 8px 12px;
  background: #f5f7fa; border-radius: 4px;
  font-size: 12px; color: #606266;
}
.k10-details-tip summary { cursor: pointer; font-weight: 500; color: #409eff; }
.k10-details-tip ul { margin: 8px 0 0 0; padding-left: 20px; }
.k10-details-tip li { margin-bottom: 4px; }

.note-card { margin-top: 16px; }
.note-card-header { display: flex; justify-content: space-between; align-items: center; }
.note-card-header span { font-weight: 600; font-size: 14px; }
</style>
