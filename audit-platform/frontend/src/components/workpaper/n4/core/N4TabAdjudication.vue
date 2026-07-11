<template>
  <div class="n4-adjudication">
    <!-- ═══ 审计目标 ═══ -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      title="审计目标"
      description="确认税金及附加（6403）本期发生额的完整性与准确性：各税种（消费税/城建税及附加/房产税/城镇土地使用税/印花税等）计入费用的金额正确，与 N2 应交税费各税种本期计提额一致，并计入利润表勾稽无误。"
    />

    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <p><strong>税金及附加(6403)</strong>：损益类借方科目，取本期发生额。包含消费税、城建税、教育费附加、地方教育附加、房产税、城镇土地使用税、车船税、印花税、资源税等。费用确认额应与N2应交税费各税种本期计提额一致。</p>
    </div>

    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-title">
        <span>税金及附加审定表 N4-1</span>
        <el-tag type="warning" size="small">损益类·借方·取发生额</el-tag>
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

    <!-- ═══ 跨底稿引用 GtIndexChip ═══ -->
    <div class="cross-ref-bar">
      <span class="cross-refs-label">关联底稿：</span>
      <GtIndexChip value="N4-2" :context-project-id="props.projectId" />
      <GtIndexChip value="N2-1" :context-project-id="props.projectId" />
      <GtIndexChip value="A" :context-project-id="props.projectId" />
      <GtIndexChip value="TB" :context-project-id="props.projectId" />
    </div>

    <!-- ═══ 主数据表格（10税种行+合计行） ═══ -->
    <el-table
      :data="tableData"
      border
      size="small"
      class="adjudication-table"
      :row-class-name="getRowClassName"
    >
      <el-table-column prop="taxType" label="税种" min-width="150" fixed>
        <template #default="{ row }">
          <span :class="['tax-type-cell', { 'total-row': row.isTotal }]">{{ row.taxType }}</span>
        </template>
      </el-table-column>

      <el-table-column label="未审数" min-width="120" align="right">
        <template #header>
          <span class="normal-header">未审数</span>
        </template>
        <template #default="{ row }">
          <el-input-number
            v-if="!props.isReadonly && !row.isTotal"
            :model-value="row.unadjusted"
            :controls="false"
            :precision="2"
            size="small"
            class="cell-input"
            @change="(val: number | undefined) => handleCellChange(row.rowKey, 'unadjusted', val ?? 0)"
          />
          <span v-else class="cell-value">{{ fmtAmount(row.unadjusted) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="AJE" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!props.isReadonly && !row.isTotal"
            :model-value="row.aje"
            :controls="false"
            :precision="2"
            size="small"
            class="cell-input"
            @change="(val: number | undefined) => handleCellChange(row.rowKey, 'aje', val ?? 0)"
          />
          <span v-else class="cell-value">{{ fmtAmount(row.aje) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="RJE" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!props.isReadonly && !row.isTotal"
            :model-value="row.rje"
            :controls="false"
            :precision="2"
            size="small"
            class="cell-input"
            @change="(val: number | undefined) => handleCellChange(row.rowKey, 'rje', val ?? 0)"
          />
          <span v-else class="cell-value">{{ fmtAmount(row.rje) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="审定数" min-width="120" align="right">
        <template #header>
          <el-tooltip content="审定数 = 未审数 + AJE + RJE" placement="top">
            <span class="formula-header">审定数</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-tooltip content="审定数 = 未审数 + AJE + RJE" placement="top">
            <span class="formula-cell">{{ fmtAmount(row.audited) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>

      <el-table-column label="上期数" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!props.isReadonly && !row.isTotal"
            :model-value="row.prior"
            :controls="false"
            :precision="2"
            size="small"
            class="cell-input"
            @change="(val: number | undefined) => handleCellChange(row.rowKey, 'prior', val ?? 0)"
          />
          <span v-else class="cell-value">{{ fmtAmount(row.prior) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="同比变动" min-width="100" align="right">
        <template #header>
          <el-tooltip content="同比变动 = (审定数 − 上期数) / |上期数|" placement="top">
            <span class="formula-header">同比变动</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-tooltip content="同比变动 = (审定数 − 上期数) / |上期数|" placement="top">
            <span :class="['formula-cell', yoyClass(row.yoyChange)]">{{ fmtPercent(row.yoyChange) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ N4-2明细合计交叉验证 ═══ -->
    <div class="cross-validation-section">
      <div class="cv-title">交叉验证</div>
      <div class="cv-indicators">
        <div class="cv-item" :class="adjVsDetail.isMatch ? 'cv-match' : 'cv-diff'">
          <span class="cv-label">N4-1审定合计 vs N4-2明细合计</span>
          <span class="cv-badge" :class="adjVsDetail.isMatch ? 'cv-badge-ok' : 'cv-badge-err'">
            {{ adjVsDetail.isMatch ? '✓ 一致' : '⚠ 差异 ' + fmtAmount(adjVsDetail.diff) }}
          </span>
        </div>
      </div>
    </div>

    <!-- ═══ N2计提对应比较 ═══ -->
    <div class="n2-comparison-section">
      <div class="n2-header">
        <span class="n2-title">N2应交税费计提对应</span>
        <el-button size="small" link type="primary" @click="handleRefreshN2">刷新N2数据</el-button>
      </div>
      <el-table :data="n2ComparisonData" border size="small" class="n2-table">
        <el-table-column prop="tax" label="税种" min-width="130" />
        <el-table-column prop="expense" label="N4费用确认" min-width="110" align="right">
          <template #default="{ row }">
            <span>{{ fmtAmount(row.expense) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="accrual" label="N2计提额" min-width="110" align="right">
          <template #default="{ row }">
            <span>{{ fmtAmount(row.accrual) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="diff" label="差异" min-width="100" align="right">
          <template #default="{ row }">
            <span :class="Math.abs(row.diff) >= 0.01 ? 'diff-err' : 'diff-ok'">
              {{ Math.abs(row.diff) < 0.01 ? '—' : fmtAmount(row.diff) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="!hasN2Data" class="n2-empty-hint">
        <el-tag type="warning" size="small">N2未编制或数据尚未同步</el-tag>
      </div>
    </div>

    <!-- ═══ TB回写按钮 ═══ -->
    <div class="action-bar">
      <el-button
        type="primary"
        size="small"
        :disabled="props.isReadonly || !adjudication.isChanged.value"
        :loading="writebackLoading"
        @click="handleWritebackTB"
      >
        保存审定 → TB(6403·本期发生额)
      </el-button>
      <span class="action-hint">损益类科目回写本期发生额口径（借方科目：借−贷）</span>
    </div>

    <!-- ═══ 审计说明+结论 ═══ -->
    <el-card shadow="never" class="audit-notes-card">
      <template #header>
        <div class="notes-header">
          <span>审计说明与结论</span>
          <el-button size="small" @click="handleNotesAi"><el-icon><MagicStick /></el-icon>AI辅助</el-button>
        </div>
      </template>
      <div class="notes-field">
        <label class="field-label">审计说明</label>
        <el-input
          v-model="auditNote"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          placeholder="请输入审计说明（各税种费用确认情况、变动分析等）..."
          :disabled="props.isReadonly"
          @change="handleNoteSave"
        />
      </div>
      <div class="notes-field">
        <label class="field-label">审计结论</label>
        <el-input
          v-model="auditConcl"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          placeholder="请输入审计结论..."
          :disabled="props.isReadonly"
          @change="handleConclusionSave"
        />
      </div>
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="n4-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>税金及附加(6403)为<strong>损益类借方科目</strong>，取本期发生额（非余额）</li>
        <li>审定数 = 未审数 + AJE + RJE</li>
        <li>同比变动 = (审定数 − 上期数) / |上期数|；上期数为0显示"—"</li>
        <li>N4-1审定合计应与N4-2明细合计一致（交叉验证）</li>
        <li>各税种费用确认额应与N2应交税费计提额一致（费用确认=计提）</li>
        <li>"保存审定"回写试算表（科目6403，本期发生额口径）并通知A利润表勾稽</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N4TabAdjudication — 税金及附加审定表N4-1
 *
 * 83公式+损益类发生额取数+税种分行+N4-2交叉验证+N2计提对应+TB回写+A利润表勾稽
 *
 * Spec: .kiro/specs/n4-taxes-and-surcharges/ Task 4.2
 * Requirements: 2.1-2.8
 */
import { ref, computed, inject, onMounted, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, ChatDotSquare } from '@element-plus/icons-vue'
import { useN4FormData } from '../../composables/useN4FormData'
import { useN4Adjudication, type N4AdjRow } from '../../composables/useN4Adjudication'
import { useN4CrossSheet } from '../../composables/useN4CrossSheet'
import { api } from '@/services/apiProxy'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'

const props = defineProps<{
  allResponses: Map<string, any>
  wpId: string
  projectId: string
  isReadonly?: boolean
}>()

const openReviewDialog = inject<((section: string) => void) | undefined>('openReviewDialog', undefined)

// ─── Refs ────────────────────────────────────────────────────────────────────

const wpIdRef = computed(() => props.wpId) as Ref<string>
const projectIdRef = computed(() => props.projectId) as Ref<string>
const allResponsesRef = computed(() => props.allResponses) as Ref<Map<string, any>>
const isReadonlyRef = computed(() => !!props.isReadonly)

// ─── Composables ─────────────────────────────────────────────────────────────

const formData = useN4FormData({ wpId: wpIdRef, projectId: projectIdRef })

const adjudication = useN4Adjudication({
  allResponses: allResponsesRef,
  projectId: projectIdRef,
  wpId: wpIdRef,
  isReadonly: isReadonlyRef,
  onSave: (itemId: string, value: any) => {
    formData.saveResponse(itemId, value)
  },
  writebackTB: async (auditedAmount: number) => {
    await formData.writebackTB(auditedAmount)
  },
})

const crossSheet = useN4CrossSheet(allResponsesRef, { wpId: wpIdRef, projectId: projectIdRef })

// ─── Local state ─────────────────────────────────────────────────────────────

const writebackLoading = ref(false)
const auditNote = ref('')
const auditConcl = ref('')

// ─── Table data (10 rows + total) ────────────────────────────────────────────

interface DisplayRow {
  rowKey: string
  taxType: string
  unadjusted: number
  aje: number
  rje: number
  audited: number
  prior: number
  yoyChange: number | null
  isTotal: boolean
}

const tableData = computed<DisplayRow[]>(() => {
  const detail: DisplayRow[] = adjudication.rows.value.map((row) => ({
    rowKey: row.rowKey,
    taxType: row.taxType,
    unadjusted: row.unadjusted,
    aje: row.aje,
    rje: row.rje,
    audited: row.audited,
    prior: row.prior,
    yoyChange: row.yoyChange,
    isTotal: false,
  }))

  const total = adjudication.totalRow.value
  detail.push({
    rowKey: '__total__',
    taxType: '合  计',
    unadjusted: total.unadjusted,
    aje: total.aje,
    rje: total.rje,
    audited: total.audited,
    prior: total.prior,
    yoyChange: total.yoyChange,
    isTotal: true,
  })

  return detail
})

// ─── N4-2 cross validation ───────────────────────────────────────────────────

const adjVsDetail = computed(() => crossSheet.adjudicationVsDetail.value)

// ─── N2 comparison ───────────────────────────────────────────────────────────

const n2ComparisonData = computed(() => crossSheet.n4VsN2Accrual.value)
const hasN2Data = computed(() => n2ComparisonData.value.some(item => item.accrual !== 0))

// ─── Init / Load ─────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.selfLoad()
  // 恢复审计说明/结论
  auditNote.value = adjudication.auditNote.value
  auditConcl.value = adjudication.auditConclusion.value
  // 尝试刷新N2数据
  crossSheet.refreshN2AccrualData()
  // 初始化未审数（从TB发生额seed）
  if (formData.tbData.value.unadjustedNet !== 0 && !_hasExistingRows()) {
    // 如果没有已保存数据，用TB总发生额作为"合计"参考（逐税种需手动分配）
  }
})

/** 检查是否已有保存的行数据 */
function _hasExistingRows(): boolean {
  return adjudication.rows.value.some(r => r.unadjusted !== 0 || r.aje !== 0 || r.rje !== 0)
}

// ─── Cell change ─────────────────────────────────────────────────────────────

function handleCellChange(rowKey: string, field: keyof N4AdjRow, value: number): void {
  adjudication.updateCell(rowKey, field, value)
}

// ─── TB Writeback ────────────────────────────────────────────────────────────

async function handleWritebackTB(): Promise<void> {
  writebackLoading.value = true
  try {
    await adjudication.writeback()
    // 发布A利润表勾稽事件
    crossSheet.publishTaxesSurchargesUpdated()
    ElMessage.success('审定数已回写试算表（科目6403·本期发生额）')
  } catch {
    ElMessage.error('回写失败，请稍后重试')
  } finally {
    writebackLoading.value = false
  }
}

// ─── Notes / Conclusion ──────────────────────────────────────────────────────

function handleNoteSave(): void {
  adjudication.saveNote(auditNote.value)
}
function handleConclusionSave(): void {
  adjudication.saveConclusion(auditConcl.value)
}

// ─── AI / Review ─────────────────────────────────────────────────────────────

async function handleAiAssist(): Promise<void> {
  const wpId = props.wpId
  if (!wpId) { ElMessage.info('AI辅助：底稿ID缺失'); return }
  try {
    const res = await api.post(`/api/workpapers/${wpId}/ai/generate-text`, {
      prompt: '请分析税金及附加各税种本期费用确认的合理性，包括同比变动分析和与N2计提额的一致性检查',
      context: JSON.stringify({
        rows: adjudication.rows.value,
        totalAudited: adjudication.totalRow.value.audited,
        n2Comparison: crossSheet.n4VsN2Accrual.value,
      }),
      section: 'N4-1-adjudication',
      existingContent: auditNote.value,
    })
    const text = res?.data?.content ?? res?.content ?? ''
    if (text) {
      auditNote.value = text
      adjudication.saveNote(text)
      ElMessage.success('AI分析已生成')
    }
  } catch {
    ElMessage.info('AI辅助分析税金及附加审定表...')
  }
}

function handleNotesAi(): void {
  handleAiAssist()
}

function handleReview(): void {
  openReviewDialog ? openReviewDialog('N4-1-审定表') : ElMessage.info('复核对话未配置')
}

function handleRefreshN2(): void {
  crossSheet.refreshN2AccrualData()
  ElMessage.info('正在刷新N2计提数据...')
}

// ─── Row class (N2 diff highlight) ───────────────────────────────────────────

function getRowClassName({ row }: { row: DisplayRow }): string {
  if (row.isTotal) return 'total-row-bg'
  const hasDiff = crossSheet.taxDiffHighlights.value.get(row.taxType)
  return hasDiff ? 'n2-diff-row' : ''
}

// ─── Formatters ──────────────────────────────────────────────────────────────

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(val: number | null | undefined): string {
  if (val == null) return '—'
  return (val * 100).toFixed(2) + '%'
}

function yoyClass(val: number | null | undefined): string {
  if (val == null) return ''
  if (val > 0.3) return 'yoy-high'
  if (val < -0.3) return 'yoy-low'
  return ''
}
</script>

<style scoped>
.audit-objective { margin-bottom: 16px; }
.audit-objective :deep(.el-alert__description) { font-size: 13px; line-height: 1.6; }
.n4-adjudication { padding: 12px; font-size: 13px; }

/* ─── 方法论上下文 ─── */
.methodology-context { padding: 12px 16px; margin-bottom: 16px; background: #fffbeb; border: 1px solid #fde68a; border-left: 4px solid #d97706; border-radius: 6px; font-size: 13px; color: #92400e; line-height: 1.7; }
.methodology-context p { margin: 0; }

/* ─── Section header ─── */
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { display: flex; align-items: center; gap: 10px; font-size: 15px; font-weight: 600; color: #303133; }
.section-actions { display: flex; align-items: center; gap: 8px; }

/* ─── 跨底稿引用 ─── */
.cross-ref-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; }
.cross-refs-label { font-size: 12px; color: #909399; }

/* ─── 主表格 ─── */
.adjudication-table { margin-bottom: 16px; }
:deep(.adjudication-table) { font-size: 13px; }
.tax-type-cell { font-weight: 500; color: #303133; }
.total-row { font-weight: 700; color: #409eff; }
.cell-input { width: 100%; }
:deep(.cell-input .el-input__inner) { text-align: right; font-size: 13px; }
.cell-value { font-size: 13px; color: #606266; }
.normal-header { font-weight: 600; }
.formula-header { border-bottom: 1px dashed #409eff; cursor: help; color: #409eff; font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; font-weight: 500; color: #303133; padding-bottom: 1px; }

/* ─── YoY coloring ─── */
.yoy-high { color: #f56c6c; font-weight: 600; }
.yoy-low { color: #67c23a; font-weight: 600; }

/* ─── Row highlighting ─── */
:deep(.n2-diff-row) { background-color: #fef0f0 !important; }
:deep(.total-row-bg) { background-color: #f5f7fa !important; font-weight: 700; }

/* ─── 交叉验证 ─── */
.cross-validation-section { margin-bottom: 16px; padding: 14px 16px; background: #fafbfc; border: 1px solid #ebeef5; border-radius: 8px; }
.cv-title { font-size: 13px; font-weight: 500; color: #303133; margin-bottom: 10px; }
.cv-indicators { display: flex; flex-wrap: wrap; gap: 10px; }
.cv-item { display: flex; align-items: center; gap: 8px; padding: 6px 12px; border-radius: 6px; font-size: 12px; }
.cv-match { background: #e8f5e9; border: 1px solid #a5d6a7; }
.cv-diff { background: #fef0f0; border: 1px solid #fab6b6; }
.cv-label { color: #606266; }
.cv-badge { font-weight: 600; font-size: 12px; }
.cv-badge-ok { color: #43a047; }
.cv-badge-err { color: #f56c6c; }

/* ─── N2计提对应 ─── */
.n2-comparison-section { margin-bottom: 16px; padding: 14px 16px; background: #fafbfc; border: 1px solid #ebeef5; border-radius: 8px; }
.n2-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.n2-title { font-size: 13px; font-weight: 500; color: #303133; }
.n2-table { margin-bottom: 8px; }
:deep(.n2-table) { font-size: 13px; }
.n2-empty-hint { text-align: center; padding: 6px 0; }
.diff-err { color: #f56c6c; font-weight: 600; }
.diff-ok { color: #67c23a; }

/* ─── 操作栏 ─── */
.action-bar { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; padding: 10px 16px; background: #f5f7fa; border-radius: 6px; }
.action-hint { font-size: 12px; color: #909399; }

/* ─── 审计说明/结论 ─── */
.audit-notes-card { margin-bottom: 16px; }
.notes-header { display: flex; align-items: center; justify-content: space-between; font-size: 14px; font-weight: 500; }
.notes-field { margin-bottom: 12px; }
.notes-field:last-child { margin-bottom: 0; }
.field-label { display: block; font-size: 13px; font-weight: 500; color: #606266; margin-bottom: 6px; }

/* ─── 编制提示 ─── */
.n4-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266; }
.n4-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; margin-bottom: 8px; }
.n4-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
