<template>
  <div class="k8-tab-adjudication">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>发生：</b>记录的销售费用确已发生且与被审计单位相关；</li>
        <li><b>完整性：</b>所有应当记录的销售费用均已记录，不存在漏记或跨期；</li>
        <li><b>准确性：</b>销售费用金额计算准确、记录金额恰当；</li>
        <li><b>截止：</b>销售费用记录于正确的会计期间；</li>
        <li><b>分类：</b>销售费用已记录于恰当账户并恰当列报。</li>
      </ol>
    </el-alert>
    <!-- 四表库取数溯源面板 -->
    <WpFourTableSourcePanel
      v-if="props.tbSourceCodes"
      :source-codes="props.tbSourceCodes"
      gross-label="销售费用"
    />


    <!-- ═══ Section标题 + AI + 复核 ═══ -->
    <div class="section-header">
      <h3>K8-1 销售费用审定表</h3>
      <div class="header-actions">
        <GtIndexChip value="K8-2" :context-project-id="props.projectId" />
        <el-button size="small" type="warning" plain :disabled="isReadonly" :loading="adjPull.loading.value" @click="openBringInAdjustment">
          <el-icon><Download /></el-icon> 带入调整
        </el-button>
        <el-button size="small" type="warning" plain :disabled="isReadonly" @click="handlePullFromDetail">
          从 K8-2 带入
        </el-button>
        <el-tooltip :content="aiAvailable ? 'AI 辅助生成' : 'AI 服务暂不可用'" placement="top">
          <el-button size="small" type="primary" plain :loading="aiLoading" :disabled="isReadonly || !aiAvailable" @click="handleAiGenerate">
            <el-icon><MagicStick /></el-icon> AI审计说明
          </el-button>
        </el-tooltip>
        <el-button size="small" @click="handleReview">
          <el-icon><ChatDotSquare /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>销售费用（6601）为<strong>借方/损益类</strong>科目。取<strong>发生额</strong>而非期末余额！费用类发生额 = 借方发生累计 − 贷方发生（红冲）。审定数 = 未审净额 + AJE + RJE。同比变动率 > ±30% 红色高亮。</p>
    </div>

    <!-- ═══ TB勾稽指示器 ═══ -->
    <div v-if="!detailCrossValidation.isBalanced" class="reconciliation-alert">
      <el-alert type="warning" :closable="false" show-icon>
        <template #title>
          审定表合计 {{ fmtNum(totalRow.audited) }} vs K8-2明细合计差异 {{ fmtNum(detailCrossValidation.diff) }}
        </template>
      </el-alert>
    </div>

    <!-- ═══ TB(6601)核对指示器（源模板 TB数据/差异 行）═══ -->
    <div v-if="tbReconcile.hasTb && !tbReconcile.isBalanced" class="reconciliation-alert">
      <el-alert type="warning" :closable="false" show-icon>
        <template #title>
          审定合计 {{ fmtNum(totalRow.audited) }} 与试算平衡表(6601)审定发生额 {{ fmtNum(tbReconcile.tbAudited) }} 差异 {{ fmtNum(tbReconcile.diff) }}，请核对
        </template>
      </el-alert>
    </div>

    <!-- ═══ 审定表主表（29行×12列） ═══ -->
    <el-table
      :data="tableData"
      border
      size="small"
      style="width: 100%"
      :row-class-name="adjRowClass"
      max-height="560"
      show-summary
      :summary-method="summaryMethod"
    >
      <!-- 费用项目 -->
      <el-table-column prop="projectName" label="费用项目" width="130" fixed>
        <template #default="{ row }">
          <span v-if="row.isEditable" class="project-name">{{ row.projectName }}</span>
          <span v-else class="project-name subtotal-label">{{ row.projectName }}</span>
        </template>
      </el-table-column>

      <!-- 未审借方 -->
      <el-table-column label="未审借方" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.isEditable"
            :model-value="row.unadjustedDebit"
            :disabled="isReadonly"
            size="small"
            :controls="false"
            :precision="2"
            style="width:90px"
            @change="(v: number) => handleCellChange(row.rowKey, 'unadjustedDebit', v ?? 0)"
          />
          <span v-else class="formula-cell">{{ fmtNum(row.unadjustedDebit) }}</span>
        </template>
      </el-table-column>

      <!-- 未审贷方 -->
      <el-table-column label="未审贷方" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.isEditable"
            :model-value="row.unadjustedCredit"
            :disabled="isReadonly"
            size="small"
            :controls="false"
            :precision="2"
            style="width:90px"
            @change="(v: number) => handleCellChange(row.rowKey, 'unadjustedCredit', v ?? 0)"
          />
          <span v-else class="formula-cell">{{ fmtNum(row.unadjustedCredit) }}</span>
        </template>
      </el-table-column>

      <!-- 未审净额（公式列） -->
      <el-table-column label="未审净额" width="110" align="right">
        <template #default="{ row }">
          <el-tooltip content="公式：借方发生 − 贷方发生" placement="top">
            <span class="formula-cell formula-underline">{{ fmtNum(row.unadjusted) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>

      <!-- AJE -->
      <el-table-column label="AJE" width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.isEditable"
            :model-value="row.aje"
            :disabled="isReadonly"
            size="small"
            :controls="false"
            :precision="2"
            style="width:80px"
            @change="(v: number) => handleCellChange(row.rowKey, 'aje', v ?? 0)"
          />
          <span v-else class="formula-cell">{{ fmtNum(row.aje) }}</span>
        </template>
      </el-table-column>

      <!-- RJE -->
      <el-table-column label="RJE" width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.isEditable"
            :model-value="row.rje"
            :disabled="isReadonly"
            size="small"
            :controls="false"
            :precision="2"
            style="width:80px"
            @change="(v: number) => handleCellChange(row.rowKey, 'rje', v ?? 0)"
          />
          <span v-else class="formula-cell">{{ fmtNum(row.rje) }}</span>
        </template>
      </el-table-column>

      <!-- 审定数（公式列） -->
      <el-table-column label="审定数" width="120" align="right">
        <template #default="{ row }">
          <el-tooltip content="公式：未审净额 + AJE + RJE" placement="top">
            <span class="formula-cell formula-underline">{{ fmtNum(row.audited) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>

      <!-- 上期 -->
      <el-table-column label="上期" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.isEditable"
            :model-value="row.priorAmount"
            :disabled="isReadonly"
            size="small"
            :controls="false"
            :precision="2"
            style="width:90px"
            @change="(v: number) => handleCellChange(row.rowKey, 'priorAmount', v ?? 0)"
          />
          <span v-else class="formula-cell">{{ fmtNum(row.priorAmount) }}</span>
        </template>
      </el-table-column>

      <!-- 同比变动额（公式列） -->
      <el-table-column label="同比变动额" width="115" align="right">
        <template #default="{ row }">
          <el-tooltip content="公式：审定数 − 上期" placement="top">
            <span class="formula-cell formula-underline">{{ fmtNum(row.yoyChange) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>

      <!-- 同比变动率（公式列，>30%红色高亮） -->
      <el-table-column label="同比变动率" width="110" align="right">
        <template #default="{ row }">
          <el-tooltip content="公式：变动额 / |上期|" placement="top">
            <span
              class="formula-cell formula-underline"
              :class="{ 'abnormal-highlight': isAbnormal(row.yoyChangeRate) }"
            >
              {{ fmtRate(row.yoyChangeRate) }}
            </span>
          </el-tooltip>
        </template>
      </el-table-column>

      <!-- 原因分析（源模板：变动率超阈值须说明原因）-->
      <el-table-column label="原因分析" min-width="150">
        <template #default="{ row }">
          <el-input
            v-if="row.isEditable"
            :model-value="row.remark"
            :disabled="isReadonly"
            size="small"
            :placeholder="isAbnormal(row.yoyChangeRate) ? '变动率超30%，请说明原因' : '原因分析'"
            :class="{ 'required-field': isAbnormal(row.yoyChangeRate) && !row.remark }"
            @blur="(e: FocusEvent) => handleCellChange(row.rowKey, 'remark', (e.target as HTMLInputElement)?.value ?? '')"
          />
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 合计行固定底部 ═══ -->
    <div class="total-row-bar">
      <span class="total-label">合  计</span>
      <span class="total-item">未审净额: <strong>{{ fmtNum(totalRow.unadjusted) }}</strong></span>
      <span class="total-item">AJE: <strong>{{ fmtNum(totalRow.aje) }}</strong></span>
      <span class="total-item">RJE: <strong>{{ fmtNum(totalRow.rje) }}</strong></span>
      <span class="total-item">审定数: <strong>{{ fmtNum(totalRow.audited) }}</strong></span>
      <span class="total-item">上期: <strong>{{ fmtNum(totalRow.priorAmount) }}</strong></span>
      <span class="total-item" :class="{ 'abnormal-highlight': isAbnormal(totalRow.yoyChangeRate) }">
        变动率: <strong>{{ fmtRate(totalRow.yoyChangeRate) }}</strong>
      </span>
    </div>

    <!-- ═══ TB回写按钮 ═══ -->
    <div class="tb-writeback-bar">
      <el-button type="primary" size="small" :disabled="isReadonly" @click="handleTbWriteback">
        回写试算表(6601发生额)
      </el-button>
      <span v-if="detailCrossValidation.isBalanced" class="match-indicator">
        <el-icon color="#67c23a"><CircleCheckFilled /></el-icon> 明细勾稽平衡
      </span>
      <span v-else class="mismatch-indicator">
        <el-icon color="#f56c6c"><WarningFilled /></el-icon> 明细差异 {{ fmtNum(detailCrossValidation.diff) }}
      </span>
      <span class="tb-value">
        TB(6601): 未审 {{ fmtNum(tbData.unadjusted6601) }} / 审定 {{ fmtNum(tbData.audited6601) }}
        <template v-if="tbReconcile.hasTb">
          · 差异 <strong :class="tbReconcile.isBalanced ? 'tb-diff-ok' : 'tb-diff-warn'">{{ fmtNum(tbReconcile.diff) }}</strong>
        </template>
      </span>
    </div>

    <!-- ═══ 审计说明+结论 ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-header compact">
          <span>审计说明与结论</span>
          <el-tooltip :content="aiAvailable ? 'AI 辅助生成' : 'AI 服务暂不可用'" placement="top">
            <el-button size="small" type="primary" plain :loading="aiLoading" :disabled="isReadonly || !aiAvailable" @click="handleAiGenerate">
              <el-icon><MagicStick /></el-icon> AI生成
            </el-button>
          </el-tooltip>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 5 }"
        :disabled="isReadonly"
        placeholder="审计说明（执行的审计程序、发现的问题等）..."
        style="margin-bottom: 12px"
        @blur="handleSaveNote"
      />
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 5 }"
        :disabled="isReadonly"
        placeholder="审计结论..."
        @blur="handleSaveConclusion"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="k8-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>损益类科目(6601)：取<strong>发生额</strong>（借方发生累计 − 贷方红冲），非期末余额！</li>
        <li>费用类净额 = 借方发生 − 贷方发生（红冲/冲回）</li>
        <li>审定数 = 未审净额 + AJE + RJE</li>
        <li>同比变动率 = (审定 − 上期) / |上期|，变动率 > ±30% 红色预警需说明原因</li>
        <li>审定合计应与K8-2明细表各项目合计一致（交叉勾稽）</li>
        <li>完成后TB回写6601发生额，发布 substantive:adjudicated 事件通知附注</li>
        <li>「带入调整」：按科目6601拉取调整分录，逐笔选目标费用行累加到 AJE/RJE，带入后自动联动披露/附注</li>
      </ul>
    </details>

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="6601 销售费用"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * K8TabAdjudication.vue — K8-1 销售费用审定表
 * 损益类！29行×12列，73公式，取发生额非余额
 *
 * 列：费用项目|未审借方|未审贷方|未审净额(公式)|AJE|RJE|审定数(公式)|上期|同比变动额(公式)|同比变动率(公式)|备注
 * 合计行固定底部
 * 公式列虚线下划线+cursor:help+tooltip
 * 异常变动率>30%红色高亮
 *
 * Spec: .kiro/specs/k8-selling-expenses/ | Task: 4.2
 * Requirements: 2.1-2.7
 */
import WpFourTableSourcePanel from '../../shared/WpFourTableSourcePanel.vue'
import { computed, inject, toRef, defineAsyncComponent, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, CircleCheckFilled, WarningFilled, ChatDotSquare, Download } from '@element-plus/icons-vue'
import { useK8Adjudication, type K8AdjRow } from '../../composables/useK8Adjudication'
import { useK8AiGenerate } from '../../composables/useK8AiGenerate'
import { useAuditContext } from '@/composables/useAuditContext'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'

const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  tbData: { unadjusted6601: number; audited6601: number }
  isReadonly: boolean
  prefill?: Array<{ name: string; unadjustedDebit: number; unadjustedCredit: number }>
  tbSourceCodes?: Record<string, any> | null
}>()

// 父组件模板绑定会自动解包 ref → 子组件收到纯 Map；重新包成 ref 供 composable 使用
const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

// ─── 复核对话 inject ─────────────────────────────────────────────────────────
const openReviewDialog = inject<(sectionId: string, label?: string) => void>('openReviewDialog', () => {})

// ─── Composable wiring ───────────────────────────────────────────────────────

const {
  rows,
  totalRow,
  auditNote,
  auditConclusion,
  detailCrossValidation,
  updateCell,
  pullFromDetail,
  writeback,
  saveNote,
  saveConclusion,
} = useK8Adjudication({
  allResponses: allResponsesRef,
  projectId: toRef(props, 'projectId') as Ref<string>,
  wpId: toRef(props, 'wpId') as Ref<string>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  prefill: computed(() => props.prefill ?? []) as Ref<Array<{ name: string; unadjustedDebit: number; unadjustedCredit: number }>>,
  onSave: (itemId: string, value: any) => {
    emit('save', itemId, value)
  },
})

// ─── 从集中登记带入调整（6601 销售费用，损益借方） ────────────────────────────
const { adjPull, visible: bringInVisible, rowOptions: bringInRowOptions, open: openBringInAdjustment, apply: onBringInApply } = useAdjudicationBringIn({
  projectId: toRef(props, 'projectId') as any,
  year: useAuditContext().year as any,
  subjectPrefix: '6601',
  direction: 'debit', // 损益借方（费用）：净发生额 = 借 − 贷
  subjectCode: '6601',
  wpCode: 'K8',
  subjectLabel: '销售费用(6601)',
  rows,
  updateCell,
  totalAudited: () => totalRow.value.audited,
})

// ─── 表格数据 ────────────────────────────────────────────────────────────────

const tableData = computed(() => rows.value)

/** 变动率>±30%异常判定 */
const CHANGE_RATE_THRESHOLD = 0.3

function isAbnormal(rate: number | null): boolean {
  if (rate === null || rate === undefined) return false
  return Math.abs(rate) > CHANGE_RATE_THRESHOLD
}

/** 审定合计 vs 试算平衡表(6601)审定发生额核对（源模板 TB数据/差异 行）；仅 TB 已取数时判定，避免误报 */
const tbReconcile = computed(() => {
  const tbAudited = props.tbData?.audited6601 ?? 0
  const diff = totalRow.value.audited - tbAudited
  return {
    tbAudited,
    diff,
    hasTb: Math.abs(tbAudited) > 0.005,
    isBalanced: Math.abs(diff) < 0.01,
  }
})

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleCellChange(rowKey: string, field: keyof K8AdjRow, value: number | string): void {
  updateCell(rowKey, field, value)
}

function handleTbWriteback(): void {
  writeback()
}

async function handlePullFromDetail(): Promise<void> {
  if (props.isReadonly) return
  try {
    await ElMessageBox.confirm(
      '将按 K8-2 明细科目重建审定表各行（未审=月度合计、账项调整、重分类、上期审定），此操作会覆盖当前审定表已填内容。是否继续？',
      '从 K8-2 带入确认',
      { confirmButtonText: '带入并覆盖', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return // 用户取消
  }
  const r = pullFromDetail()
  if (r.ok) ElMessage.success(r.message)
  else ElMessage.warning(r.message)
}

function handleSaveNote(): void {
  saveNote(auditNote.value)
}

function handleSaveConclusion(): void {
  saveConclusion(auditConclusion.value)
}

// ─── AI 辅助（统一 /ai/generate-text 端点）─────────────────────────────────
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useK8AiGenerate({
  wpId: toRef(props, 'wpId') as Ref<string>,
})

async function handleAiGenerate(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'k8-adjudication-note',
    auditNote.value || '',
    {
      审定合计: totalRow.value.audited,
      未审合计: totalRow.value.unadjusted,
      同比变动率: totalRow.value.yoyChangeRate == null ? '—' : (totalRow.value.yoyChangeRate * 100).toFixed(2) + '%',
      明细勾稽: detailCrossValidation.value.isBalanced ? '平衡' : `差异${detailCrossValidation.value.diff.toFixed(2)}`,
      任务: '请为销售费用审定表生成审计说明（执行的审计程序、发生额审定依据、同比波动、与明细表勾稽情况）',
    },
    'AI 生成 · 审计说明',
  )
  if (text) saveNote(text)
}

function handleReview(): void {
  openReviewDialog('K8-1', '销售费用审定表复核')
}

// ─── Row class ───────────────────────────────────────────────────────────────

function adjRowClass({ row }: { row: K8AdjRow }): string {
  if (!row.isEditable) return 'subtotal-row'
  if (isAbnormal(row.yoyChangeRate)) return 'abnormal-row'
  return ''
}

// ─── Summary method (el-table show-summary) ──────────────────────────────────

function summaryMethod({ columns }: { columns: any[] }): string[] {
  return columns.map((col, idx) => {
    if (idx === 0) return '合  计'
    // 合计行数据已由totalRow显示，此处返回空（用底部栏替代）
    return ''
  })
}

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmtNum(v: number | null | undefined): string {
  if (v === null || v === undefined) return '-'
  if (v === 0) return '0.00'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return (v * 100).toFixed(2) + '%'
}
</script>

<style scoped>
.k8-tab-adjudication { padding: 12px; font-size: var(--wp-font-size, 13px); }

/* ─── Section header ─── */
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.section-header.compact { margin-bottom: 0; }
.header-actions { display: flex; gap: 8px; }

/* ─── 方法论上下文 ─── */
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }

/* ─── 勾稽 ─── */
.reconciliation-alert { margin-bottom: 12px; }

/* ─── 表格 ─── */
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.project-name { font-size: var(--wp-font-size, 13px); color: #303133; }
.subtotal-label { font-weight: 600; }
.formula-cell { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #303133; }
.formula-underline { border-bottom: 1px dashed #909399; cursor: help; }
.abnormal-highlight { color: #f56c6c !important; font-weight: 600; }
:deep(.subtotal-row) { background-color: #f0f9eb !important; font-weight: 600; }
:deep(.abnormal-row) { background-color: #fef0f0 !important; }

/* ─── 合计行底部栏 ─── */
.total-row-bar {
  display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
  margin: 12px 0; padding: 10px 14px;
  background: linear-gradient(90deg, #f0f9eb 0%, #f8fdf8 100%);
  border: 1px solid #e1f3d8; border-radius: 6px; font-size: var(--wp-font-size, 13px);
}
.total-label { font-weight: 700; color: #303133; min-width: 50px; }
.total-item { color: #606266; }
.total-item strong { color: #303133; font-family: 'JetBrains Mono', monospace; }

/* ─── TB回写栏 ─── */
.tb-writeback-bar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin: 12px 0; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; }
.match-indicator, .mismatch-indicator { display: flex; align-items: center; gap: 4px; font-size: var(--wp-font-size, 13px); }
.match-indicator { color: #67c23a; }
.mismatch-indicator { color: #f56c6c; }
.tb-value { margin-left: auto; font-size: 12px; color: #909399; font-family: 'JetBrains Mono', monospace; }
.tb-diff-ok { color: #67c23a; }
.tb-diff-warn { color: #f56c6c; }
.required-field :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px #f56c6c inset; }

/* ─── 审计说明+结论 ─── */
.conclusion-card { margin-top: 16px; }

/* ─── 编制提示 ─── */
.k8-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.k8-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.k8-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
