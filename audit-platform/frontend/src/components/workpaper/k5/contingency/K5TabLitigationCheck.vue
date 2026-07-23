<template>
  <div class="k5-tab-litigation">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>完整性：</b>所有未决诉讼/仲裁事项均已识别，很可能败诉且金额可估计的已计提预计负债；</li>
        <li><b>计价和分摊：</b>败诉损失金额为最佳估计（结合律师意见），计量恰当；</li>
        <li><b>列报与披露：</b>未决诉讼（含或有负债）已按 CAS13 恰当披露，必要时取得律师声明书。</li>
      </ol>
    </el-alert>

    <!-- ═══ Section标题 ═══ -->
    <div class="section-header">
      <h3>K5-6 未决诉讼检查表</h3>
      <div class="header-actions">
        <el-button size="small" :disabled="isReadonly" @click="handleAddRow">
          <el-icon><Plus /></el-icon> 新增行
        </el-button>
        <el-dropdown size="small" :disabled="isReadonly">
          <el-button size="small">导入导出 <el-icon><ArrowDown /></el-icon></el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item @click="handleImportData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" type="primary" plain @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI评估
        </el-button>
        <el-button size="small" @click="$emit('navigate-sheet', '审定表K5-1')">复核</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <p>未决诉讼按CAS13三级可能性判断：<strong>很可能(>50%)→确认预计负债</strong>；可能(≤50%)→附注披露或有负债；极小可能→不处理。律师函/回函是判断败诉可能性的关键审计证据。</p>
    </div>

    <!-- ═══ 交叉验证指示器 ═══ -->
    <div class="cross-check-bar">
      <span>K5-6 已确认预计损失: <strong>{{ fmtNum(crossCheck.litigationTotal) }}</strong></span>
      <span>K5-1 未决诉讼审定: <strong>{{ fmtNum(crossCheck.adjudicationLitigation) }}</strong></span>
      <el-tag v-if="crossCheck.isMatch" type="success" size="small">✓ 一致</el-tag>
      <el-tag v-else type="danger" size="small">差异 {{ fmtNum(crossCheck.diff) }}</el-tag>
    </div>

    <!-- ═══ 主表 ═══ -->
    <el-table :data="litigationRows" border size="small" style="width: 100%" max-height="520">
      <el-table-column type="index" label="序" width="48" align="center" />
      <el-table-column label="案件名称" min-width="150">
        <template #default="{ row }">
          <el-input v-model="row.caseName" :disabled="isReadonly" size="small" @blur="save(row.rowId, 'caseName', row.caseName)" />
        </template>
      </el-table-column>
      <el-table-column label="涉案金额" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.amount" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:95px" @change="(v:number) => save(row.rowId, 'amount', v)" />
        </template>
      </el-table-column>
      <el-table-column label="我方角色" width="85">
        <template #default="{ row }">
          <el-select v-model="row.partyRole" :disabled="isReadonly" size="small" placeholder="—" @change="(v:string) => save(row.rowId, 'partyRole', v)">
            <el-option label="被告" value="defendant" />
            <el-option label="原告" value="plaintiff" />
            <el-option label="第三人" value="third_party" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="诉讼阶段" width="100">
        <template #default="{ row }">
          <el-select v-model="row.stage" :disabled="isReadonly" size="small" placeholder="阶段" @change="(v:string) => handleStageChange(row, v)">
            <el-option v-for="s in stageOptions" :key="s" :label="s" :value="s" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="律师函" width="80" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.lawyerLetterStatus === 'replied'" type="success" size="small">已回函</el-tag>
          <el-tag v-else-if="row.lawyerLetterStatus === 'sent'" type="warning" size="small">已发函</el-tag>
          <el-tag v-else type="info" size="small">未发</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="律师意见" min-width="140">
        <template #default="{ row }">
          <el-input v-model="row.lawyerOpinion" :disabled="isReadonly" size="small" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" @blur="save(row.rowId, 'lawyerOpinion', row.lawyerOpinion)" />
        </template>
      </el-table-column>
      <el-table-column label="败诉可能性" width="130">
        <template #default="{ row }">
          <el-select v-model="row.lossLikelihood" :disabled="isReadonly" size="small" placeholder="级别" @change="(v:string) => save(row.rowId, 'lossLikelihood', v)">
            <el-option label="很可能(>50%)" value="very_likely" />
            <el-option label="可能(≤50%)" value="possible" />
            <el-option label="极小可能" value="remote" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="应赔/预计损失" width="115" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.estimatedLoss" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:95px" @change="(v:number) => save(row.rowId, 'estimatedLoss', v)" />
        </template>
      </el-table-column>
      <el-table-column label="已计提预计负债" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.bookProvision" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:95px" @change="(v:number) => save(row.rowId, 'bookProvision', v)" />
        </template>
      </el-table-column>
      <el-table-column label="差异金额" width="105" align="right">
        <template #default="{ row }">
          <el-tooltip content="应赔/预计损失 − 已计提" placement="top">
            <span class="formula-cell formula-underline" :class="{ 'diff-warn': Math.abs(row.variance) > 0.01 }">{{ fmtNum(row.variance) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="差异原因" min-width="130">
        <template #default="{ row }">
          <el-input v-model="row.varianceReason" :disabled="isReadonly" size="small" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" placeholder="差异原因" @blur="save(row.rowId, 'varianceReason', row.varianceReason)" />
        </template>
      </el-table-column>
      <el-table-column label="确认" width="72" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.recognition === 'recognize'" type="danger" size="small">确认</el-tag>
          <el-tag v-else-if="row.recognition === 'disclose'" type="warning" size="small">披露</el-tag>
          <el-tag v-else-if="row.recognition === 'ignore'" type="info" size="small">不处理</el-tag>
          <span v-else class="text-muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="📎" width="56" align="center">
        <template #default="{ row }">
          <el-tooltip content="律师函联动（上传+OCR）" placement="top">
            <el-button link size="small" :disabled="isReadonly" @click="handleLawyerLetter(row.rowId)">
              📎
            </el-button>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="" width="48" align="center">
        <template #default="{ $index }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="removeRow($index)">
            <el-icon><Delete /></el-icon>
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 统计摘要 ═══ -->
    <div class="summary-bar">
      <span>合计案件: {{ subtotals.count }}</span>
      <span>涉案金额: {{ fmtNum(subtotals.totalAmount) }}</span>
      <span>已确认损失: <strong class="text-danger">{{ fmtNum(subtotals.recognizedLoss) }}</strong></span>
      <span>需披露损失: <strong class="text-warning">{{ fmtNum(subtotals.disclosedLoss) }}</strong></span>
      <el-button v-if="totalVariance > 0.01 && !isReadonly" size="small" type="warning" style="margin-left: auto" @click="suggestAjeFromVariance">💡 建议补提AJE</el-button>
      <el-button size="small" style="margin-left: auto" @click="openVoucherSampling">⚡ 抽凭</el-button>
    </div>

    <!-- 抽凭引擎 Dialog -->
    <el-dialog v-model="showSamplingDialog" title="⚡ 抽凭引擎（科目 2701 预计负债-诉讼）" width="720px" :close-on-click-modal="false" destroy-on-close>
      <GtVoucherSamplingEngine
        v-if="showSamplingDialog && props.wpId && props.projectId"
        account-code="2701"
        phase="final"
        :workpaper-id="props.wpId"
        :project-id="props.projectId"
        :year="samplingYear"
        @filled="onSampleFilled"
      />
    </el-dialog>

    <!-- ═══ 一审判决败诉提级警告（证监会监管报告第1点） ═══ -->
    <el-alert v-if="firstInstanceLossWarnings.length > 0" type="error" :closable="false" show-icon style="margin-top:10px">
      <template #title>
        <span>⚠️ 一审判决败诉应确认预计负债（{{ firstInstanceLossWarnings.length }} 件）</span>
      </template>
      <template #default>
        <div style="font-size:12px;line-height:1.6;margin-top:4px">
          <div v-for="w in firstInstanceLossWarnings" :key="w.rowId" style="margin-bottom:2px">
            <b>{{ w.caseName }}</b>：阶段=一审/二审，但可能性未标"很可能"。证监会明确：一审判决败诉仍以上诉为由未确认预计负债缺乏合理性。
            <el-button v-if="!isReadonly" size="small" type="danger" link @click="upgradeToVeryLikely(w.rowId)">→ 提级为"很可能"</el-button>
          </div>
        </div>
      </template>
    </el-alert>

    <!-- ═══ 审计说明与结论 ═══ -->
    <el-card shadow="never" class="conclusion-card" style="margin-top:12px">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">审计说明与结论</span>
          <el-button size="small" type="primary" plain @click="handleAiGenerate">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <div style="margin-bottom:10px">
        <label style="font-size:12px;color:#909399;display:block;margin-bottom:4px">审计说明</label>
        <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
          placeholder="概述未决诉讼检查情况：已识别案件数量/涉案总额/已确认预计负债金额/差异处理/律师函取得情况等"
          @change="persistNote" />
      </div>
      <div>
        <label style="font-size:12px;color:#909399;display:block;margin-bottom:4px">审计结论</label>
        <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly"
          placeholder="基于上述检查，对预计负债-未决诉讼的完整性、计价和披露形成结论..."
          @change="persistNote" />
      </div>
    </el-card>

    <!-- ═══ 证监会监管报告提示（方法论上下文）═══ -->
    <div class="csrc-hint">
      <div class="csrc-title">⚠ 证监会《2020年上市公司年报会计监管报告》提示</div>
      <ol>
        <li><b>未恰当确认因诉讼产生的支付义务：</b>未决诉讼被证实很可能导致经济利益流出且金额能可靠计量时，应确认预计负债。个别公司一审判决败诉并要求赔偿的情况下，仍以上诉为由未确认相关损失和预计负债，缺乏合理性。</li>
        <li><b>不恰当抵销预计负债与或有资产：</b>与或有事项相关的义务满足现时义务、很可能流出、金额可计量时应确认预计负债；或有资产只有在基本确定能收到时才确认，不得与预计负债抵销。</li>
        <li><b>业务咨询提示：</b>财务报表批准报出日已取得一审判决且判决公司败诉要求赔偿的，如被审计单位未按一审判决金额计提预计负债，建议项目组尽早履行业务咨询。</li>
      </ol>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="k5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>败诉可能性 > 50% → 确认预计负债，金额为最佳估计（应承担赔偿）</li>
        <li>败诉可能性 ≤ 50% 但非极小 → 附注披露或有负债</li>
        <li>差异金额 = 应承担赔偿（预计损失）− 已计提预计负债，差异应说明原因</li>
        <li>律师函/回函应作为判断败诉可能性的核心证据</li>
        <li>已确认预计损失合计应与 K5-1 未决诉讼行审定数一致</li>
        <li>📎列可上传律师函附件 → OCR识别自动填充律师意见</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K5TabLitigationCheck.vue — K5-6 未决诉讼检查表
 * 律师函联动+可能性判断+预计损失+交叉验证+OCR
 * 抽凭引擎 GtVoucherSamplingEngine dialog + 行级OCR(📎律师函)
 *
 * Spec: .kiro/specs/k5-provisions/ | Task: 4.5, 6.3
 * Requirements: 8.1-8.4
 */
import { ref, toRef, computed, defineAsyncComponent, onMounted } from 'vue'
import { Plus, Delete, MagicStick, ArrowDown } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useK5Litigation } from '../../composables/useK5Litigation'
import http from '@/utils/http'
import type { Ref } from 'vue'

const GtVoucherSamplingEngine = defineAsyncComponent(
  () => import('../../voucher-sampling/GtVoucherSamplingEngine.vue'),
)

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  year?: number
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

// 父组件模板绑定会自动解包 ref → 子组件收到纯 Map；重新包成 ref 供 composable 使用
const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>

const samplingYear = computed(() => props.year ?? new Date().getFullYear())

const {
  litigationRows,
  subtotals,
  crossCheck,
  stageOptions,
  updateCell,
  addRow,
  removeRow,
  setLawyerLetterRef,
} = useK5Litigation({
  allResponses: allResponsesRef,
  saveResponse: async (field: string, value: any) => {
    emit('save', `K5-${field}`, value)
  },
})

function save(rowId: string, field: string, value: any) { updateCell(rowId, field, value) }
function handleAddRow() { addRow() }
function handleAiGenerate() { emit('save', 'K5-6-ai-trigger', { remark: 'litigation-eval' }) }

// ─── 审计说明与结论 ──────────────────────────────────────────────────────────

const auditNote = ref('')
const auditConclusion = ref('')

function loadNote(): void {
  const noteItem = props.allResponses.get('K5-6-audit-note')
  if (noteItem?.remark) auditNote.value = noteItem.remark
  const conclItem = props.allResponses.get('K5-6-audit-conclusion')
  if (conclItem?.remark) auditConclusion.value = conclItem.remark
}

function persistNote(): void {
  emit('save', 'K5-6-audit-note', { remark: auditNote.value })
  emit('save', 'K5-6-audit-conclusion', { remark: auditConclusion.value })
}

// ─── 一审判决自动提级（证监会监管报告第1点） ─────────────────────────────────

/**
 * 一审/二审判决败诉但可能性未标"很可能"的案件 → 提级警告
 * 证监会明确：一审判决败诉仍以上诉为由未确认预计负债缺乏合理性。
 */
const firstInstanceLossWarnings = computed(() => {
  return litigationRows.value.filter((r: any) =>
    (r.stage === '一审' || r.stage === '二审') &&
    r.partyRole === 'defendant' &&
    r.lossLikelihood !== 'very_likely' &&
    r.amount > 0
  )
})

function upgradeToVeryLikely(rowId: string): void {
  updateCell(rowId, 'lossLikelihood', 'very_likely')
  ElMessage.success('已将可能性提级为"很可能"，请确认预计损失金额')
}

// ─── 诉讼阶段变更联动 ───────────────────────────────────────────────────────

function handleStageChange(row: any, newStage: string): void {
  save(row.rowId, 'stage', newStage)
  // 一审/二审 + 被告 + 可能性非"很可能" → 弹提示
  if ((newStage === '一审' || newStage === '二审') && row.partyRole === 'defendant' && row.lossLikelihood !== 'very_likely') {
    ElMessage.warning({
      message: `案件"${row.caseName || '未命名'}"已进入${newStage}阶段，建议评估是否应将败诉可能性提升为"很可能"`,
      duration: 5000,
    })
  }
}

// ─── 导入导出 ────────────────────────────────────────────────────────────────

async function handleExportTemplate(): Promise<void> {
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/k5/export-template`, null, { params: { sheet: 'K5-6' }, responseType: 'blob', _silent: true } as any)
    const blob = new Blob([res.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = 'K5-6_未决诉讼_模板.xlsx'; a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('模板已下载')
  } catch { ElMessage.error('导出模板失败') }
}

async function handleExportData(): Promise<void> {
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/k5/export-data`, null, { params: { sheet: 'K5-6' }, responseType: 'blob', _silent: true } as any)
    const blob = new Blob([res.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = 'K5-6_未决诉讼_数据.xlsx'; a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('数据已导出')
  } catch { ElMessage.error('导出数据失败') }
}

async function handleImportData(): Promise<void> {
  const input = document.createElement('input')
  input.type = 'file'; input.accept = '.xlsx,.xls'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await http.post(`/api/workpapers/${props.wpId}/k5/import-data`, formData, {
        params: { sheet: 'K5-6' },
        headers: { 'Content-Type': 'multipart/form-data' }, _silent: true,
      } as any)
      ElMessage.success(`导入成功，共 ${res?.data?.imported_count ?? res?.data?.data?.rowCount ?? 0} 条`)
    } catch (err: any) {
      ElMessage.error('导入失败：' + (err?.response?.data?.message || err?.response?.data?.detail || '文件格式错误'))
    }
  }
  input.click()
}

function handleLawyerLetter(rowId: string) {
  // 触发律师函上传+OCR流程（行级OCR: POST contract-ocr → 确认弹窗 → 填入律师意见）
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.pdf,.png,.jpg,.jpeg'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    const formData = new FormData()
    formData.append('file', file)
    formData.append('doc_type', 'lawyer_letter')
    try {
      const res = await http.post(`/api/workpapers/${props.wpId}/d4/contract-ocr`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        _silent: true,
      } as any)
      const ocrResult = res?.data?.data ?? res?.data ?? {}
      const ocrText = ocrResult.extracted_fields?.full_text
        || ocrResult.text || ocrResult.content || JSON.stringify(ocrResult)
      // 确认弹窗
      await ElMessageBox.confirm(
        `OCR识别结果：\n${ocrText.substring(0, 300)}${ocrText.length > 300 ? '...' : ''}\n\n是否填入律师意见字段？`,
        '律师函OCR识别',
        { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' }
      )
      // 填入律师意见
      setLawyerLetterRef(rowId, ocrText)
      ElMessage.success('已将OCR识别结果填入律师意见')
    } catch (err: any) {
      if (err !== 'cancel' && err?.toString() !== 'cancel') {
        ElMessage.warning('OCR识别失败或已取消')
      }
    }
  }
  input.click()
}

// ─── 抽凭引擎 ────────────────────────────────────────────────────────────────

const showSamplingDialog = ref(false)

function openVoucherSampling() {
  showSamplingDialog.value = true
}

// ─── 差异 → 建议 AJE（推送 K5-3）────────────────────────────────────────────

/** 未补提差额合计（应确认的预计损失 − 已计提，仅>0部分） */
const totalVariance = computed(() => {
  return litigationRows.value
    .filter((r: any) => r.recognition === 'recognize' && (r.variance ?? 0) > 0.01)
    .reduce((sum: number, r: any) => sum + (r.variance ?? 0), 0)
})

async function suggestAjeFromVariance(): Promise<void> {
  if (totalVariance.value <= 0.01) return
  const amt = totalVariance.value
  try {
    await ElMessageBox.confirm(
      `检测到未决诉讼应确认但未计提差异合计 ${fmtNum(amt)} 元。\n\n建议生成调整分录：\n  借：营业外支出 6711  ${fmtNum(amt)}\n  贷：预计负债 2701  ${fmtNum(amt)}\n\n是否推送至 K5-3 调整分录汇总？`,
      '建议补提预计负债',
      { confirmButtonText: '推送至K5-3', cancelButtonText: '取消', type: 'warning' }
    )
    // 推送 AJE 至 K5-3（通过 allResponses 写入 K5-3-entries）
    emit('save', 'K5-3-suggested-aje', {
      remark: JSON.stringify({
        source: 'K5-6-litigation-variance',
        entryType: 'AJE',
        summary: `补提未决诉讼预计负债（差异 ${fmtNum(amt)}）`,
        debitAccountCode: '6711',
        debitAccountName: '营业外支出',
        creditAccountCode: '2701',
        creditAccountName: '预计负债',
        amount: amt,
      }),
    })
    ElMessage.success('已推送补提建议至K5-3调整分录')
  } catch {
    // 用户取消
  }
}

function onSampleFilled(payload: any) {
  showSamplingDialog.value = false
  const samples = payload?.samples ?? []
  if (samples.length > 0) {
    ElMessage.success(`抽凭样本已填入 ${samples.length} 笔`)
  } else {
    ElMessage.info('未获取到样本数据')
  }
}

function fmtNum(v: number): string {
  if (!v && v !== 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────
onMounted(() => { loadNote() })
</script>

<style scoped>
.k5-tab-litigation { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }
.cross-check-bar { display: flex; align-items: center; gap: 16px; margin-bottom: 12px; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; font-size: var(--wp-font-size, 13px); }
.formula-cell { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #303133; }
.formula-underline { border-bottom: 1px dashed #909399; cursor: help; }
.diff-warn { color: #e6a23c; font-weight: 600; }
.csrc-hint { margin-top: 12px; padding: 12px 14px; background: #fffbeb; border-left: 4px solid #f59e0b; border-radius: 4px; font-size: 12px; color: #78350f; line-height: 1.6; }
.csrc-title { font-weight: 600; margin-bottom: 6px; }
.csrc-hint ol { padding-left: 18px; margin: 0; }
.csrc-hint li { margin-bottom: 4px; }
.text-muted { color: #c0c4cc; font-size: 12px; }
.text-danger { color: #f56c6c; }
.text-warning { color: #e6a23c; }
.summary-bar { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 10px; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; align-items: center; }
.conclusion-card :deep(.el-card__header) { padding: 8px 14px; }
.conclusion-card :deep(.el-card__body) { padding: 12px 14px; }
.card-header-row { display: flex; align-items: center; justify-content: space-between; }
.card-title { font-weight: 600; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.k5-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.k5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.k5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
