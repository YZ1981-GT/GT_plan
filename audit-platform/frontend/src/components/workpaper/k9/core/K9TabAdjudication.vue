<template>
  <div class="k9-tab-adjudication">
    <!-- ═══ Section标题 + AI + 复核 ═══ -->
    <div class="section-header">
      <h3>K9-1 管理费用审定表</h3>
      <div class="header-actions">
        <el-button size="small" type="primary" plain @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI审计说明
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><ChatDotSquare /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>管理费用（6602）为<strong>借方/损益类</strong>科目。取<strong>发生额</strong>而非期末余额！费用类发生额 = 借方发生累计 − 贷方发生（红冲）。审定数 = 未审净额 + AJE + RJE。同比变动率 > ±30% 红色高亮。</p>
    </div>

    <!-- ═══ TB勾稽指示器 ═══ -->
    <div v-if="!detailCrossValidation.isBalanced" class="reconciliation-alert">
      <el-alert type="warning" :closable="false" show-icon>
        <template #title>
          审定表合计 {{ fmtNum(totalRow.audited) }} vs K9-2明细合计差异 {{ fmtNum(detailCrossValidation.diff) }}
        </template>
      </el-alert>
    </div>

    <!-- ═══ 审定表主表（44行虚拟滚动） ═══ -->
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
      <el-table-column prop="projectName" label="项目" width="140" fixed>
        <template #default="{ row }">
          <span v-if="row.isEditable" class="project-name">{{ row.projectName }}</span>
          <span v-else class="project-name subtotal-label">{{ row.projectName }}</span>
        </template>
      </el-table-column>

      <!-- 本期发生额（未审借方） -->
      <el-table-column label="本期发生额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.isEditable"
            :model-value="row.unadjustedDebit"
            :disabled="isReadonly"
            size="small"
            :controls="false"
            :precision="2"
            style="width: 100px"
            @change="(v: number) => handleCellChange(row.rowKey, 'unadjustedDebit', v ?? 0)"
          />
          <span v-else class="formula-cell">{{ fmtNum(row.unadjustedDebit) }}</span>
        </template>
      </el-table-column>

      <!-- 上期发生额 -->
      <el-table-column label="上期发生额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.isEditable"
            :model-value="row.priorAmount"
            :disabled="isReadonly"
            size="small"
            :controls="false"
            :precision="2"
            style="width: 100px"
            @change="(v: number) => handleCellChange(row.rowKey, 'priorAmount', v ?? 0)"
          />
          <span v-else class="formula-cell">{{ fmtNum(row.priorAmount) }}</span>
        </template>
      </el-table-column>

      <!-- 未审净额（公式列） -->
      <el-table-column label="未审" width="110" align="right">
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
            style="width: 80px"
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
            style="width: 80px"
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

      <!-- 同比变动（公式列，>30%红色高亮） -->
      <el-table-column label="同比变动" width="100" align="right">
        <template #default="{ row }">
          <el-tooltip content="公式：(审定−上期) / |上期|" placement="top">
            <span
              class="formula-cell formula-underline"
              :class="{ 'abnormal-highlight': isAbnormal(row.yoyChangeRate) }"
            >
              {{ fmtRate(row.yoyChangeRate) }}
            </span>
          </el-tooltip>
        </template>
      </el-table-column>

      <!-- 备注 -->
      <el-table-column label="备注" min-width="140">
        <template #default="{ row }">
          <el-input
            v-if="row.isEditable"
            :model-value="row.remark"
            :disabled="isReadonly"
            size="small"
            placeholder="备注"
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
        回写试算表(6602发生额)
      </el-button>
      <span v-if="detailCrossValidation.isBalanced" class="match-indicator">
        <el-icon color="#67c23a"><CircleCheckFilled /></el-icon> 明细勾稽平衡
      </span>
      <span v-else class="mismatch-indicator">
        <el-icon color="#f56c6c"><WarningFilled /></el-icon> 明细差异 {{ fmtNum(detailCrossValidation.diff) }}
      </span>
      <span class="tb-value">
        TB(6602): 未审 {{ fmtNum(tbData.unadjusted6602) }} / 审定 {{ fmtNum(tbData.audited6602) }}
      </span>
    </div>

    <!-- ═══ 审计说明+结论 ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-header compact">
          <span>审计说明与结论</span>
          <el-button size="small" type="primary" plain @click="handleAiGenerate">
            <el-icon><MagicStick /></el-icon> AI生成
          </el-button>
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
    <details class="k9-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>损益类科目(6602)：取<strong>发生额</strong>（借方发生累计 − 贷方红冲），非期末余额！</li>
        <li>费用类净额 = 借方发生 − 贷方发生（红冲/冲回）</li>
        <li>审定数 = 未审净额 + AJE + RJE</li>
        <li>同比变动率 = (审定 − 上期) / |上期|，变动率 > ±30% 红色预警需说明原因</li>
        <li>审定合计应与K9-2明细表各项目合计一致（交叉勾稽）</li>
        <li>完成后TB回写6602发生额，发布 substantive:adjudicated 事件通知附注</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K9TabAdjudication.vue — K9-1 管理费用审定表
 * 损益类！44行虚拟滚动，73公式，取发生额非余额
 *
 * 列：项目|本期发生额|上期发生额|未审(公式)|AJE|RJE|审定数(公式)|同比变动(公式)|备注
 * 合计行固定底部 + TB回写(6602发生额) + 明细交叉验证
 * 公式列虚线下划线+cursor:help+tooltip
 * 异常变动率>30%红色高亮
 *
 * Spec: .kiro/specs/k9-admin-expenses/ | Task: 4.2
 * Requirements: 2.1-2.7
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { MagicStick, CircleCheckFilled, WarningFilled, ChatDotSquare } from '@element-plus/icons-vue'
import { useK9Adjudication, type K9AdjRow } from '../../composables/useK9Adjudication'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Ref<Map<string, any>>
  tbData: { unadjusted6602: number; audited6602: number }
  isReadonly: boolean
}>()

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
  writeback,
  saveNote,
  saveConclusion,
} = useK9Adjudication({
  allResponses: props.allResponses,
  projectId: toRef(props, 'projectId') as Ref<string>,
  wpId: toRef(props, 'wpId') as Ref<string>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  onSave: (itemId: string, value: any) => {
    emit('save', itemId, value)
  },
})

// ─── 表格数据 ────────────────────────────────────────────────────────────────

const tableData = computed(() => rows.value)

/** 变动率>±30%异常判定 */
const CHANGE_RATE_THRESHOLD = 0.3

function isAbnormal(rate: number | null): boolean {
  if (rate === null || rate === undefined) return false
  return Math.abs(rate) > CHANGE_RATE_THRESHOLD
}

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleCellChange(rowKey: string, field: keyof K9AdjRow, value: number | string): void {
  updateCell(rowKey, field, value)
}

function handleTbWriteback(): void {
  writeback()
}

function handleSaveNote(): void {
  saveNote(auditNote.value)
}

function handleSaveConclusion(): void {
  saveConclusion(auditConclusion.value)
}

function handleAiGenerate(): void {
  emit('save', 'K9-1-ai-trigger', { remark: 'generate' })
}

function handleReview(): void {
  openReviewDialog('K9-1', '管理费用审定表复核')
}

// ─── Row class ───────────────────────────────────────────────────────────────

function adjRowClass({ row }: { row: K9AdjRow }): string {
  if (!row.isEditable) return 'subtotal-row'
  if (isAbnormal(row.yoyChangeRate)) return 'abnormal-row'
  return ''
}

// ─── Summary method (el-table show-summary) ──────────────────────────────────

function summaryMethod({ columns }: { columns: any[] }): string[] {
  return columns.map((_, idx) => {
    if (idx === 0) return '合  计'
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
.k9-tab-adjudication { padding: 12px; font-size: 13px; }

/* ─── Section header ─── */
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.section-header.compact { margin-bottom: 0; }
.header-actions { display: flex; gap: 8px; }

/* ─── 方法论上下文 ─── */
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 13px; color: #78350f; line-height: 1.6; }

/* ─── 勾稽 ─── */
.reconciliation-alert { margin-bottom: 12px; }

/* ─── 表格 ─── */
:deep(.el-table) { font-size: 13px; }
.project-name { font-size: 13px; color: #303133; }
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
  border: 1px solid #e1f3d8; border-radius: 6px; font-size: 13px;
}
.total-label { font-weight: 700; color: #303133; min-width: 50px; }
.total-item { color: #606266; }
.total-item strong { color: #303133; font-family: 'JetBrains Mono', monospace; }

/* ─── TB回写栏 ─── */
.tb-writeback-bar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin: 12px 0; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; }
.match-indicator, .mismatch-indicator { display: flex; align-items: center; gap: 4px; font-size: 13px; }
.match-indicator { color: #67c23a; }
.mismatch-indicator { color: #f56c6c; }
.tb-value { margin-left: auto; font-size: 12px; color: #909399; font-family: 'JetBrains Mono', monospace; }

/* ─── 审计说明+结论 ─── */
.conclusion-card { margin-top: 16px; }

/* ─── 编制提示 ─── */
.k9-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266; }
.k9-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.k9-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
