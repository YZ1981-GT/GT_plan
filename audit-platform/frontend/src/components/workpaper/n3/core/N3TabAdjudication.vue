<template>
  <div class="n3-adjudication">
    <!-- ═══ 审计目标 ═══ -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      title="审计目标"
      description="确认递延所得税负债（2901）期末余额的存在性与计价准确性：应纳税暂时性差异识别完整、适用税率正确，商誉初始确认及拟长期持有的长期股权投资等特殊项处理恰当，与 N3-2 明细表勾稽一致并回写试算表。"
    />

    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <p><strong>递延所得税负债(2901)</strong>：应纳税暂时性差异×适用税率。资产账面价值＞计税基础，或负债账面价值＜计税基础时产生应纳税暂时性差异，确认递延所得税负债。</p>
      <p>特殊项：商誉初始确认、拟长期持有的长期股权投资不确认递延所得税负债。</p>
    </div>

    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-title">
        <span>递延所得税负债审定表 N3-1</span>
        <el-tag type="danger" size="small" class="liability-tag">负债类·贷方</el-tag>
      </div>
      <div class="section-actions">
        <el-button size="small" @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon>AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><ChatDotSquare /></el-icon>复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 负债类科目公式提示 ═══ -->
    <div class="liability-formula-badge">
      <el-icon><WarningFilled /></el-icon>
      <span>⚠️ 负债类贷方科目：期末余额 = 期初余额 + 本期贷方（确认）− 本期借方（转回）</span>
    </div>

    <!-- ═══ 主数据表格 ═══ -->
    <el-table
      :data="tableData"
      border
      size="small"
      show-summary
      :summary-method="getSummaries"
      highlight-current-row
      class="adjudication-table"
      :row-class-name="getRowClassName"
    >
      <!-- 项目列 -->
      <el-table-column prop="category" label="应纳税暂时性差异项目" min-width="160" fixed>
        <template #default="{ row }">
          <span class="category-cell">{{ row.category }}</span>
        </template>
      </el-table-column>

      <!-- 期初余额 -->
      <el-table-column prop="beginning" label="期初余额" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            v-model="row.beginning"
            :controls="false"
            :precision="2"
            size="small"
            class="cell-input"
            @change="(val: number | undefined) => handleCellChange(row.category, 'beginning', val ?? 0)"
          />
          <span v-else :class="['cell-value', { negative: row.beginning < 0 }]">{{ fmtAmount(row.beginning) }}</span>
        </template>
      </el-table-column>

      <!-- 本期贷方(确认) -->
      <el-table-column prop="creditAmount" label="本期贷方(确认)" min-width="130" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            v-model="row.creditAmount"
            :controls="false"
            :precision="2"
            size="small"
            class="cell-input"
            @change="(val: number | undefined) => handleCellChange(row.category, 'creditAmount', val ?? 0)"
          />
          <span v-else :class="['cell-value', { negative: row.creditAmount < 0 }]">{{ fmtAmount(row.creditAmount) }}</span>
        </template>
      </el-table-column>

      <!-- 本期借方(转回) -->
      <el-table-column prop="debitAmount" label="本期借方(转回)" min-width="130" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            v-model="row.debitAmount"
            :controls="false"
            :precision="2"
            size="small"
            class="cell-input"
            @change="(val: number | undefined) => handleCellChange(row.category, 'debitAmount', val ?? 0)"
          />
          <span v-else :class="['cell-value', { negative: row.debitAmount < 0 }]">{{ fmtAmount(row.debitAmount) }}</span>
        </template>
      </el-table-column>

      <!-- 期末余额（公式列） -->
      <el-table-column label="期末余额" min-width="120" align="right">
        <template #header>
          <span class="formula-header" title="期末 = 期初 + 贷方 − 借方（负债类）">期末余额</span>
        </template>
        <template #default="{ row }">
          <el-tooltip content="期末 = 期初 + 贷方 − 借方（负债类贷方科目）" placement="top">
            <span :class="['formula-cell', { negative: row.endBalance < 0 }]">{{ fmtAmount(row.endBalance) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>

      <!-- 未审数 -->
      <el-table-column prop="unadjusted" label="未审数" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            v-model="row.unadjusted"
            :controls="false"
            :precision="2"
            size="small"
            class="cell-input"
            @change="(val: number | undefined) => handleCellChange(row.category, 'unadjusted', val ?? 0)"
          />
          <span v-else :class="['cell-value', { negative: row.unadjusted < 0 }]">{{ fmtAmount(row.unadjusted) }}</span>
        </template>
      </el-table-column>

      <!-- AJE -->
      <el-table-column prop="aje" label="AJE" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            v-model="row.aje"
            :controls="false"
            :precision="2"
            size="small"
            class="cell-input"
            @change="(val: number | undefined) => handleCellChange(row.category, 'aje', val ?? 0)"
          />
          <span v-else :class="['cell-value', { negative: row.aje < 0 }]">{{ fmtAmount(row.aje) }}</span>
        </template>
      </el-table-column>

      <!-- RJE -->
      <el-table-column prop="rje" label="RJE" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            v-model="row.rje"
            :controls="false"
            :precision="2"
            size="small"
            class="cell-input"
            @change="(val: number | undefined) => handleCellChange(row.category, 'rje', val ?? 0)"
          />
          <span v-else :class="['cell-value', { negative: row.rje < 0 }]">{{ fmtAmount(row.rje) }}</span>
        </template>
      </el-table-column>

      <!-- 审定数（公式列） -->
      <el-table-column label="审定数" min-width="120" align="right">
        <template #header>
          <span class="formula-header" title="审定数 = 未审 + AJE + RJE">审定数</span>
        </template>
        <template #default="{ row }">
          <el-tooltip content="审定数 = 未审数 + AJE + RJE" placement="top">
            <span :class="['formula-cell', { negative: row.audited < 0 }]">{{ fmtAmount(row.audited) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>

      <!-- 变动额（公式列） -->
      <el-table-column label="变动额" min-width="110" align="right">
        <template #header>
          <span class="formula-header" title="变动额 = 期末 − 期初">变动额</span>
        </template>
        <template #default="{ row }">
          <el-tooltip content="变动额 = 期末余额 − 期初余额" placement="top">
            <span :class="['formula-cell', { negative: row.change < 0 }]">{{ fmtAmount(row.change) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>

      <!-- 变动率（公式列） -->
      <el-table-column label="变动率" min-width="90" align="right">
        <template #header>
          <span class="formula-header" title="变动率 = 变动额 / 期初">变动率</span>
        </template>
        <template #default="{ row }">
          <el-tooltip content="变动率 = 变动额 ÷ 期初余额" placement="top">
            <span :class="['formula-cell', { negative: row.changeRate < 0 }]">{{ fmtPercent(row.changeRate) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>

      <!-- 原因分析 -->
      <el-table-column label="原因分析" min-width="160">
        <template #header>
          <div class="reason-header">
            <span>原因分析</span>
            <el-button size="small" link type="primary" @click="handleReasonAi">
              <el-icon><MagicStick /></el-icon>
            </el-button>
          </div>
        </template>
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            v-model="row.reason"
            size="small"
            placeholder="变动原因..."
            @change="handleReasonChange(row.category, row.reason)"
          />
          <span v-else class="cell-value">{{ row.reason || '—' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 交叉验证区 ═══ -->
    <div class="cross-validation-section">
      <div class="cv-title">交叉验证</div>
      <div class="cv-indicators">
        <!-- N3-1 vs N3-2明细 -->
        <div class="cv-item" :class="crossValidation.isMatch ? 'cv-match' : 'cv-diff'">
          <span class="cv-label">N3-1审定表 vs N3-2明细表</span>
          <span v-if="crossValidation.isMatch" class="cv-badge cv-badge-ok">✓ 一致</span>
          <span v-else class="cv-badge cv-badge-err">
            ⚠ 差异 {{ fmtAmount(crossValidation.diff) }}
          </span>
        </div>

        <!-- N3 vs N1 对应 -->
        <div class="cv-item" :class="n1Correspondence.canOffset ? 'cv-match' : 'cv-info'">
          <span class="cv-label">N1递延税资产对应</span>
          <span v-if="n1Correspondence.canOffset" class="cv-badge cv-badge-ok">
            可抵销（同一纳税主体）
          </span>
          <span v-else class="cv-badge cv-badge-warn">分列展示（不同主体）</span>
        </div>
      </div>
    </div>

    <!-- ═══ N1对应关系提示 ═══ -->
    <div class="n1-correspondence-section">
      <div class="n1-title">
        <span>N1递延所得税资产 ↔ N3递延所得税负债 对应关系</span>
        <GtIndexChip value="N1-4" :context-project-id="projectIdStr" />
      </div>
      <div class="n1-details">
        <div class="n1-item">
          <span class="n1-label">N1递延税资产（可抵扣暂时性差异）：</span>
          <span class="n1-value">{{ fmtAmount(n1Correspondence.assetPart) }}</span>
        </div>
        <div class="n1-item">
          <span class="n1-label">N3递延税负债（应纳税暂时性差异）：</span>
          <span class="n1-value">{{ fmtAmount(n1Correspondence.liabilityPart) }}</span>
        </div>
        <div class="n1-item">
          <span class="n1-label">本期变动额（供N5核对）：</span>
          <span :class="['n1-value', { negative: deferredTaxChange.change < 0 }]">
            {{ fmtAmount(deferredTaxChange.change) }}
          </span>
          <GtIndexChip value="N5-8" :context-project-id="projectIdStr" />
        </div>
      </div>
    </div>

    <!-- ═══ TB回写 + 联动状态 ═══ -->
    <div class="action-bar">
      <el-button
        type="primary"
        size="small"
        :disabled="isReadonly"
        :loading="writebackLoading"
        @click="handleWritebackTB"
      >
        回写审定数 → TB(2901)
      </el-button>
      <div class="n5-linkage-indicator">
        <span class="n5-label">N5递延税费用联动：</span>
        <span v-if="deferredTaxChange.change !== 0" class="n5-badge n5-badge-ok">
          ✓ 变动 {{ fmtAmount(deferredTaxChange.change) }}
        </span>
        <span v-else class="n5-badge n5-badge-na">— 无变动</span>
      </div>
    </div>

    <!-- ═══ 审计说明+结论 ═══ -->
    <el-card shadow="never" class="audit-notes-card">
      <template #header>
        <div class="notes-header">
          <span>审计说明与结论</span>
          <el-button size="small" @click="handleNotesAi">
            <el-icon><MagicStick /></el-icon>AI辅助
          </el-button>
        </div>
      </template>
      <div class="notes-field">
        <label class="field-label">审计说明</label>
        <el-input
          v-model="auditNotes"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          placeholder="请输入审计说明..."
          :disabled="isReadonly"
          @change="handleNotesSave"
        />
      </div>
      <div class="notes-field">
        <label class="field-label">审计结论</label>
        <el-input
          v-model="auditConclusion"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          placeholder="请输入审计结论..."
          :disabled="isReadonly"
          @change="handleConclusionSave"
        />
      </div>
    </el-card>

    <!-- ═══ 编制提示（折叠底部） ═══ -->
    <details class="n3-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>递延所得税负债（2901）为<strong>负债类贷方科目</strong>：期末 = 期初 + 贷方（确认）− 借方（转回）</li>
        <li>审定数 = 未审数 + AJE调整 + RJE重分类</li>
        <li>应纳税暂时性差异 = 资产账面价值 − 计税基础（资产账面＞计税基础）</li>
        <li>递延所得税负债 = 应纳税暂时性差异 × 适用税率</li>
        <li>商誉初始确认 / 拟长期持有的长期股权投资 → <strong>不确认</strong>递延所得税负债</li>
        <li>N3-2明细表各项目期末递延税负债合计应与本表审定合计一致</li>
        <li>本期变动额（期末−期初）供N5递延所得税费用核对</li>
        <li>"回写审定数"将合计审定数回写至试算表（科目2901期末余额）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N3TabAdjudication — N3-1 递延所得税负债审定表
 *
 * Spec: .kiro/specs/n3-deferred-tax-liabilities/
 * Task: 4.2
 * Requirements: 2.1-2.8
 *
 * 核心职责：
 * - 7项目行（应纳税暂时性差异分类）+ 合计行，78公式覆盖
 * - 负债类期末余额 = 期初 + 贷方 − 借方（2901贷方科目）
 * - 审定数 = 未审 + AJE + RJE
 * - 与N3-2明细表交叉验证
 * - N1递延所得税资产对应关系提示（GtIndexChip跳转N1-4）
 * - TB回写(2901期末余额) + N5递延税费用联动
 * - 审计说明+结论+复核
 *
 * 科目：2901递延所得税负债（贷方/负债类！）
 */
import { ref, computed, inject, watch, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, ChatDotSquare, WarningFilled } from '@element-plus/icons-vue'
// @ts-ignore
import GtIndexChip from '../../GtIndexChip.vue'
import { useN3FormData } from '../../composables/useN3FormData'
import { useN3Adjudication, type N3DiffCategory } from '../../composables/useN3Adjudication'
import { useN3CrossSheet } from '../../composables/useN3CrossSheet'
import { eventBus } from '@/utils/eventBus'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  allResponses: Map<string, any>
  wpId: string | Ref<string>
  projectId: string | Ref<string>
  isReadonly?: boolean
}>()

// ─── Inject 复核对话 ─────────────────────────────────────────────────────────

const openReviewDialog = inject<((section: string) => void) | undefined>(
  'openReviewDialog',
  undefined,
)

const scheduleAutoSnapshot = inject<(() => void) | undefined>('scheduleAutoSnapshot', undefined)

// ─── Refs ────────────────────────────────────────────────────────────────────

const wpIdRef = computed(() => typeof props.wpId === 'string' ? props.wpId : props.wpId.value)
const projectIdRef = computed(() => typeof props.projectId === 'string' ? props.projectId : props.projectId.value)
const projectIdStr = computed(() => projectIdRef.value)

// ─── useN3FormData ───────────────────────────────────────────────────────────

const formData = useN3FormData({
  wpId: computed(() => wpIdRef.value) as Ref<string>,
  projectId: computed(() => projectIdRef.value) as Ref<string>,
})

// ─── Composables ─────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)

const {
  rows,
  total,
  crossValidation,
  updateRow,
  saveAndSync,
} = useN3Adjudication({
  allResponses: allResponsesRef,
  saveField: formData.setField,
  getField: formData.getField,
  writebackTB: formData.writebackTB,
})

const {
  adjudicationVsDetail,
  n3ToN1Correspondence,
  deferredTaxChange,
  publishDeferredTaxLiabilityUpdated,
} = useN3CrossSheet(allResponsesRef)

// ─── 审计说明/结论 ───────────────────────────────────────────────────────────

const auditNotes = ref<string>(formData.getField('1', 'audit-notes') ?? '')
const auditConclusion = ref<string>(formData.getField('1', 'audit-conclusion') ?? '')

// ─── 表格数据（computed + 追加reason字段用于原因分析列） ─────────────────────

interface DisplayRow {
  category: N3DiffCategory
  beginning: number
  creditAmount: number
  debitAmount: number
  endBalance: number
  unadjusted: number
  aje: number
  rje: number
  audited: number
  change: number
  changeRate: number
  reason: string
}

const tableData = computed<DisplayRow[]>(() => {
  return rows.value.map(row => ({
    ...row,
    reason: formData.getField('1', `reason-${row.category}`) ?? '',
  }))
})

// ─── 交叉验证：使用 useN3CrossSheet 结果 ─────────────────────────────────────

const n1Correspondence = computed(() => n3ToN1Correspondence.value)

// ─── TB回写 loading ──────────────────────────────────────────────────────────

const writebackLoading = ref(false)

// ─── 只读判断 ────────────────────────────────────────────────────────────────

const isReadonly = computed(() => props.isReadonly ?? false)

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(val: number | null | undefined): string {
  if (val == null || val === 0) return '—'
  return (val * 100).toFixed(2) + '%'
}

// ─── 单元格变更 → 保存 ──────────────────────────────────────────────────────

async function handleCellChange(
  category: N3DiffCategory,
  field: 'beginning' | 'creditAmount' | 'debitAmount' | 'unadjusted' | 'aje' | 'rje',
  value: number,
) {
  await updateRow(category, field, value)
}

// ─── 原因分析变更 ────────────────────────────────────────────────────────────

async function handleReasonChange(category: N3DiffCategory, reason: string) {
  await formData.setField('1', `reason-${category}`, reason)
}

// ─── 合计行 ──────────────────────────────────────────────────────────────────

function getSummaries({ columns }: { columns: any[] }) {
  const sums: string[] = []
  const LABEL_MAP: Record<string, number | undefined> = {
    '应纳税暂时性差异项目': undefined,
    '期初余额': total.value.beginning,
    '本期贷方(确认)': total.value.credit,
    '本期借方(转回)': total.value.debit,
    '期末余额': total.value.endBalance,
    '未审数': total.value.unadjusted,
    'AJE': total.value.aje,
    'RJE': total.value.rje,
    '审定数': total.value.audited,
    '变动额': total.value.change,
  }
  columns.forEach((col: any, idx: number) => {
    if (idx === 0) {
      sums[idx] = '合计'
      return
    }
    const label = col.label || ''
    if (label === '变动率') {
      const beginTotal = total.value.beginning
      const changeTotal = total.value.change
      if (beginTotal === 0 && changeTotal === 0) { sums[idx] = '—'; return }
      if (beginTotal === 0 && changeTotal > 0) { sums[idx] = '100.00%'; return }
      if (beginTotal === 0) { sums[idx] = '—'; return }
      sums[idx] = ((changeTotal / beginTotal) * 100).toFixed(2) + '%'
      return
    }
    if (label === '原因分析') { sums[idx] = ''; return }
    const val = LABEL_MAP[label]
    sums[idx] = val != null ? fmtAmount(val) : ''
  })
  return sums
}

// ─── 行样式（校验失败红色） ──────────────────────────────────────────────────

function getRowClassName({ row }: { row: any }): string {
  if (row && row.endBalance < 0) return 'row-validation-error'
  return ''
}

// ─── TB回写 ──────────────────────────────────────────────────────────────────

async function handleWritebackTB() {
  writebackLoading.value = true
  try {
    await saveAndSync()
    publishDeferredTaxLiabilityUpdated()
    scheduleAutoSnapshot?.()
    ElMessage.success('审定数已回写试算表（科目2901期末余额）')
  } catch (err: any) {
    ElMessage.error(`回写失败：${err.message || '未知错误'}`)
  } finally {
    writebackLoading.value = false
  }
}

// ─── readField 辅助 + N3-3 净影响合并 ───────────────────────────────────────

function readField(sheet: string, field: string): any {
  const itemId = `N3-${sheet}-${field}`
  const resp = allResponsesRef.value.get(itemId)
  if (!resp?.conclusion) return null
  try { return JSON.parse(resp.conclusion) } catch { return resp.conclusion }
}

/** N3-3 AJE/RJE 净影响（从 N3-3-entries 实时解析） */
const n3AjeNet = computed(() => {
  const val = readField('1', 'aje-net')
  return typeof val === 'number' ? val : 0
})

const n3RjeNet = computed(() => {
  const val = readField('1', 'rje-net')
  return typeof val === 'number' ? val : 0
})

// ─── 监听 allResponses 变化刷新 N3-3 影响 ───────────────────────────────────

watch(allResponsesRef, () => {
  // N3-3 调整分录净影响变化时通知联动
  if (n3AjeNet.value !== 0 || n3RjeNet.value !== 0) {
    eventBus.emit('substantive:adjudicated', {
      wpCode: 'N3',
      accountCode: '2901',
      auditedAmount: total.value.audited,
      adjudicatedAmount: total.value.audited,
      timestamp: Date.now(),
    })
  }
}, { deep: false })

// ─── 审计说明/结论保存 ───────────────────────────────────────────────────────

async function handleNotesSave() {
  await formData.setField('1', 'audit-notes', auditNotes.value)
}

async function handleConclusionSave() {
  await formData.setField('1', 'audit-conclusion', auditConclusion.value)
}

// ─── AI辅助 ──────────────────────────────────────────────────────────────────

const aiLoading = ref(false)

async function callAiGenerateText(section: string, prompt: string, target: 'notes' | 'conclusion' | 'reason') {
  if (aiLoading.value) return
  aiLoading.value = true
  try {
    const { default: http } = await import('@/utils/http')
    const res = await http.post(`/api/workpapers/${wpIdRef.value}/ai/generate-text`, {
      section,
      prompt,
      context: { wpId: wpIdRef.value },
      existingContent: target === 'notes' ? auditNotes.value : target === 'conclusion' ? auditConclusion.value : '',
    })
    const text = res?.data?.content || res?.data?.data?.content || ''
    if (text) {
      if (target === 'notes') { auditNotes.value = text; await handleNotesSave() }
      else if (target === 'conclusion') { auditConclusion.value = text; await handleConclusionSave() }
    }
  } catch { /* 降级静默 */ }
  finally { aiLoading.value = false }
}

function handleAiAssist() {
  callAiGenerateText('n3-adjudication', '请基于递延所得税负债底稿数据，给出审计分析建议', 'notes')
}

function handleNotesAi() {
  callAiGenerateText('n3-adjudication-notes', '请基于递延所得税负债审定表数据，生成审计说明', 'notes')
}

function handleReasonAi() {
  callAiGenerateText('n3-adjudication-reason', '请基于递延所得税负债审定表各项目变动情况，给出变动原因分析', 'notes')
}

// ─── 复核对话 ────────────────────────────────────────────────────────────────

function handleReview() {
  if (openReviewDialog) {
    openReviewDialog('N3-1-审定表')
  } else {
    ElMessage.info('复核对话未配置')
  }
}

// ─── 监听审定数变化 → 自动触发N5联动事件 ─────────────────────────────────────

watch(
  () => total.value.audited,
  () => {
    publishDeferredTaxLiabilityUpdated()
  },
  { immediate: false },
)
</script>

<style scoped>
.audit-objective { margin-bottom: 16px; }
.audit-objective :deep(.el-alert__description) { font-size: var(--wp-font-size, 13px); line-height: 1.6; }
.n3-adjudication {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 方法论上下文（琥珀色左边线+浅黄背景） ─── */
.methodology-context {
  padding: 12px 16px;
  margin-bottom: 16px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-left: 4px solid #d97706;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #92400e;
  line-height: 1.7;
}

.methodology-context p {
  margin: 0 0 4px;
}

.methodology-context p:last-child {
  margin-bottom: 0;
}

/* ─── Section Header ─── */
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.liability-tag {
  font-size: 11px;
}

.section-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ─── 负债类公式提示 ─── */
.liability-formula-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  margin-bottom: 16px;
  background: linear-gradient(135deg, #fce4ec 0%, #f8bbd0 100%);
  border: 1px solid #f48fb1;
  border-left: 4px solid #e91e63;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #880e4f;
}

.liability-formula-badge .el-icon {
  font-size: 16px;
  color: #e91e63;
  flex-shrink: 0;
}

/* ─── 表格样式 ─── */
.adjudication-table {
  margin-bottom: 16px;
}

:deep(.adjudication-table .el-table) {
  font-size: var(--wp-font-size, 13px);
}

.category-cell {
  font-weight: 500;
  color: #303133;
}

.cell-input {
  width: 100%;
}

:deep(.cell-input .el-input__inner) {
  text-align: right;
  font-size: var(--wp-font-size, 13px);
}

.cell-value {
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

/* ─── 负数红色 ─── */
.negative {
  color: #f56c6c !important;
}

/* ─── 公式列样式（虚线下划线+cursor:help） ─── */
.formula-header {
  border-bottom: 1px dashed #409eff;
  cursor: help;
  color: #409eff;
  font-weight: 600;
}

.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  font-weight: 500;
  color: #303133;
  padding-bottom: 1px;
}

/* ─── 原因分析列header ─── */
.reason-header {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* ─── 校验失败行红色高亮 ─── */
:deep(.row-validation-error) {
  background-color: #fef0f0 !important;
}

:deep(.row-validation-error:hover > td) {
  background-color: #fde2e2 !important;
}

/* ─── 交叉验证区 ─── */
.cross-validation-section {
  margin-bottom: 16px;
  padding: 14px 16px;
  background: #fafbfc;
  border: 1px solid #ebeef5;
  border-radius: 8px;
}

.cv-title {
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #303133;
  margin-bottom: 10px;
}

.cv-indicators {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.cv-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 12px;
}

.cv-match {
  background: #e8f5e9;
  border: 1px solid #a5d6a7;
}

.cv-diff {
  background: #fef0f0;
  border: 1px solid #fab6b6;
}

.cv-info {
  background: #e3f2fd;
  border: 1px solid #90caf9;
}

.cv-label {
  color: #606266;
  font-size: 12px;
}

.cv-badge {
  font-weight: 600;
  font-size: 12px;
}

.cv-badge-ok {
  color: #43a047;
}

.cv-badge-err {
  color: #f56c6c;
}

.cv-badge-warn {
  color: #e65100;
}

/* ─── N1对应关系区 ─── */
.n1-correspondence-section {
  margin-bottom: 16px;
  padding: 14px 16px;
  background: #f0f9ff;
  border: 1px solid #bae6fd;
  border-radius: 8px;
}

.n1-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #0369a1;
  margin-bottom: 10px;
}

.n1-details {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.n1-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.n1-label {
  color: #64748b;
}

.n1-value {
  font-weight: 500;
  color: #303133;
}

/* ─── 操作栏 ─── */
.action-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
  padding: 10px 16px;
  background: #f5f7fa;
  border-radius: 6px;
}

.n5-linkage-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--wp-font-size, 13px);
}

.n5-label {
  color: #606266;
}

.n5-badge {
  font-weight: 500;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
}

.n5-badge-ok {
  background: #e8f5e9;
  color: #43a047;
  border: 1px solid #a5d6a7;
}

.n5-badge-na {
  background: #f5f5f5;
  color: #9e9e9e;
  border: 1px solid #e0e0e0;
}

/* ─── 审计说明卡片 ─── */
.audit-notes-card {
  margin-bottom: 16px;
}

.notes-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}

.notes-field {
  margin-bottom: 12px;
}

.notes-field:last-child {
  margin-bottom: 0;
}

.field-label {
  display: block;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #606266;
  margin-bottom: 6px;
}

/* ─── 编制提示折叠 ─── */
.n3-details-tip {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.n3-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.n3-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
