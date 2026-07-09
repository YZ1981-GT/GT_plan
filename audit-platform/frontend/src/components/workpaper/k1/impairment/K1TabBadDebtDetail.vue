<!--
  K1TabBadDebtDetail.vue — K1-3 坏账准备明细表（21公式 + 三阶段矩阵）

  Columns: 项目|期初坏账|本期计提|本期转回|本期核销|期末坏账(公式)|计提比例(公式)|阶段|对应应收期末|备注
  Features:
  1. 期末坏账 = 期初 + 计提 - 转回 - 核销 (via useK1BadDebt composable)
  2. 计提比例 = 期末坏账 / 其他应收款期末
  3. 三阶段转入转出矩阵 (Stage1/2/3 summary at bottom)
  4. 与K1-8测算交叉验证 (crossValidation computed showing diff)
  5. 与K1-1审定坏账准备合计一致验证
  6. 动态行新增 (ElMessageBox.prompt)
  7. el-table max-height for scroll
  8. AI辅助 + 复核按钮右对齐
  9. 方法论上下文(琥珀色) + 编制提示折叠
  10. 导入导出

  Spec: .kiro/specs/k1-other-receivables/ Task 4.4
  Requirements: 4.1-4.5
-->
<template>
  <div class="k1-tab-bad-debt-detail">
    <!-- 方法论上下文（琥珀色） -->
    <div class="methodology-context">
      <p>K1-3坏账准备明细表逐项列示各往来对象坏账准备的计提、转回和核销情况。
        期末坏账=期初+计提-转回-核销；计提比例=期末坏账÷其他应收款期末余额。
        最终合计须与K1-1审定表坏账准备一致，并与K1-8测算交叉验证差异。</p>
    </div>

    <!-- 标题栏 + 操作 -->
    <div class="section-head">
      <h3 class="sheet-title">K1-3 坏账准备明细表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" link @click="handleAiGenerate('K1-3-baddebt')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" :disabled="isReadonly" @click="handleAddRow">＋ 新增</el-button>
        <el-dropdown trigger="click" size="small">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item @click="handleImportData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="handleReview('K1-3-baddebt')">💬 复核</el-button>
      </div>
    </div>

    <!-- 主表格 -->
    <el-table
      :data="rows"
      border
      size="small"
      :max-height="480"
      class="bad-debt-table"
      show-summary
      :summary-method="summaryMethod"
    >
      <el-table-column label="项目" min-width="130" fixed>
        <template #default="{ row }">
          <span>{{ row.label }}</span>
        </template>
      </el-table-column>

      <el-table-column label="期初坏账" min-width="115" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.beginBadDebt" size="small"
            :controls="false" class="amount-input"
            @change="(v: number) => handleUpdate(row.id, 'beginBadDebt', v ?? 0)" />
          <span v-else class="amount-cell">{{ fmtAmt(row.beginBadDebt) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="本期计提" min-width="115" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.provision" size="small"
            :controls="false" class="amount-input"
            @change="(v: number) => handleUpdate(row.id, 'provision', v ?? 0)" />
          <span v-else class="amount-cell">{{ fmtAmt(row.provision) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="本期转回" min-width="115" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.reversal" size="small"
            :controls="false" class="amount-input"
            @change="(v: number) => handleUpdate(row.id, 'reversal', v ?? 0)" />
          <span v-else class="amount-cell">{{ fmtAmt(row.reversal) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="本期核销" min-width="115" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.writeoff" size="small"
            :controls="false" class="amount-input"
            @change="(v: number) => handleUpdate(row.id, 'writeoff', v ?? 0)" />
          <span v-else class="amount-cell">{{ fmtAmt(row.writeoff) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="期末坏账" min-width="120" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="期末坏账=期初+计提-转回-核销">
            {{ fmtAmt(row.endBadDebt) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="计提比例" min-width="100" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="计提比例=期末坏账÷其他应收款期末">
            {{ row.provisionRate != null ? (row.provisionRate * 100).toFixed(2) + '%' : '-' }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="阶段" min-width="90" align="center">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.stage" size="small"
            @change="(v: number) => handleUpdate(row.id, 'stage', v)">
            <el-option label="Stage 1" :value="1" />
            <el-option label="Stage 2" :value="2" />
            <el-option label="Stage 3" :value="3" />
          </el-select>
          <el-tag v-else :type="stageTagType(row.stage)" size="small">
            Stage {{ row.stage }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="对应应收期末" min-width="125" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.receivableEnd" size="small"
            :controls="false" class="amount-input"
            @change="(v: number) => handleUpdate(row.id, 'receivableEnd', v ?? 0)" />
          <span v-else class="amount-cell">{{ fmtAmt(row.receivableEnd) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="备注" min-width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.remark" size="small" placeholder="备注"
            @change="(v: string) => handleUpdate(row.id, 'remark', v)" />
          <span v-else>{{ row.remark || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="danger" link @click="handleRemoveRow(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 三阶段转入转出矩阵 -->
    <div class="stage-matrix">
      <h4 class="matrix-title">三阶段矩阵汇总</h4>
      <div class="matrix-grid">
        <div v-for="s in [1, 2, 3] as const" :key="s" class="matrix-card" :class="`stage-${s}`">
          <div class="card-header">Stage {{ s }}</div>
          <div class="card-body">
            <div class="metric">
              <span class="metric-label">项数</span>
              <span class="metric-value">{{ stageMatrix[s].count }}</span>
            </div>
            <div class="metric">
              <span class="metric-label">期末坏账合计</span>
              <span class="metric-value">{{ fmtAmt(stageMatrix[s].total) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 交叉验证面板 -->
    <div class="cross-validation-panel">
      <h4 class="cv-title">交叉验证</h4>
      <div class="cv-items">
        <!-- 与K1-8测算交叉验证 -->
        <div class="cv-item" :class="{ 'cv-pass': crossValidation.isMatch, 'cv-fail': !crossValidation.isMatch }">
          <span class="cv-label">vs K1-8测算</span>
          <span class="cv-detail">
            企业计提: {{ fmtAmt(crossValidation.bookedProvision) }} |
            测算应计提: {{ fmtAmt(crossValidation.calcProvision) }} |
            差异: <strong>{{ fmtAmt(crossValidation.diff) }}</strong>
          </span>
          <el-tag :type="crossValidation.isMatch ? 'success' : 'danger'" size="small" effect="plain">
            {{ crossValidation.isMatch ? '一致' : '有差异' }}
          </el-tag>
          <el-button v-if="!crossValidation.isMatch" size="small" link type="primary"
            @click="emit('navigate-sheet', 'K1-8 坏账准备测算')">跳转K1-8 →</el-button>
        </div>

        <!-- 与K1-1审定坏账准备合计一致验证 -->
        <div class="cv-item" :class="{ 'cv-pass': adjudicationMatch.isMatch, 'cv-fail': !adjudicationMatch.isMatch }">
          <span class="cv-label">vs K1-1审定坏账</span>
          <span class="cv-detail">
            K1-3合计: {{ fmtAmt(totalEndBadDebt) }} |
            K1-1审定坏账: {{ fmtAmt(adjudicationBadDebt) }} |
            差异: <strong>{{ fmtAmt(adjudicationMatch.diff) }}</strong>
          </span>
          <el-tag :type="adjudicationMatch.isMatch ? 'success' : 'danger'" size="small" effect="plain">
            {{ adjudicationMatch.isMatch ? '一致' : '有差异' }}
          </el-tag>
          <el-button v-if="!adjudicationMatch.isMatch" size="small" link type="primary"
            @click="emit('navigate-sheet', 'K1-1 审定表')">跳转K1-1 →</el-button>
        </div>
      </div>
    </div>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>期末坏账 = 期初坏账 + 本期计提 - 本期转回 - 本期核销（公式自动计算）</li>
        <li>计提比例 = 期末坏账 ÷ 对应应收款期末余额（公式自动计算）</li>
        <li>阶段划分：Stage1(12个月ECL) / Stage2(整个存续期ECL) / Stage3(已减值)</li>
        <li>三阶段矩阵汇总各阶段项数和坏账合计</li>
        <li>期末坏账合计须与K1-1审定表坏账准备合计一致</li>
        <li>与K1-8测算结果交叉验证：差异应在容差范围(0.01)内</li>
        <li>"新增"按钮弹出对话框输入项目名称后创建行</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K1TabBadDebtDetail.vue — K1-3 坏账准备明细表
 * Spec: .kiro/specs/k1-other-receivables/ | Task: 4.4
 * Requirements: 4.1-4.5
 *
 * 21公式 + 计提/转回/核销管理 + 三阶段矩阵 + K1-8交叉验证 + K1-1一致验证
 */
import { computed, inject, toRef, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useK1BadDebt, type K1BadDebtRow } from '../../../composables/useK1BadDebt'
import { useK1ImportExport } from '../../../composables/useK1ImportExport'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

// ─── Injections ──────────────────────────────────────────────────────────────

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── Composables ─────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)

const {
  rows,
  totalEndBadDebt,
  totalProvision,
  stageMatrix,
  crossValidation,
  loadRows,
  addRow,
  removeRow,
  updateRow,
  serializeRows,
} = useK1BadDebt({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
})

const {
  exportTemplate,
  exportData,
  importData,
} = useK1ImportExport({ wpId: toRef(props, 'wpId') })

// ─── K1-1审定坏账验证 ────────────────────────────────────────────────────────

/** 从allResponses读取K1-1审定坏账准备合计 */
const adjudicationBadDebt = computed(() => {
  const item = props.allResponses.get('K1-1-audited-bad-debt')
  if (!item) return 0
  const raw = item.remark ?? item.conclusion
  const n = Number(raw)
  return Number.isFinite(n) ? n : 0
})

/** K1-3合计 vs K1-1审定坏账准备差异 */
const adjudicationMatch = computed(() => {
  const diff = totalEndBadDebt.value - adjudicationBadDebt.value
  return { diff, isMatch: Math.abs(diff) < 0.01 }
})

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  loadRows()
})

// ─── 行操作 ──────────────────────────────────────────────────────────────────

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入坏账准备项目名称',
      '新增坏账明细行',
      { confirmButtonText: '确定', cancelButtonText: '取消', inputPlaceholder: '项目名称（如：往来对象名）' }
    )
    if (!value || !value.trim()) {
      ElMessage.warning('项目名称不能为空')
      return
    }
    addRow(value.trim())
    persistRows()
    ElMessage.success(`已新增：${value.trim()}`)
  } catch {
    // 用户取消
  }
}

function handleRemoveRow(id: string) {
  removeRow(id)
  persistRows()
}

function handleUpdate(id: string, field: keyof K1BadDebtRow, value: any) {
  updateRow(id, field, value)
  persistRows()
}

/** 持久化行数据 + 更新交叉验证所需合计值 */
function persistRows() {
  const itemId = 'K1-3-baddebt-rows'
  const payload = { item_id: itemId, conclusion: null, remark: serializeRows() }
  props.allResponses.set(itemId, payload)
  emit('save', itemId, { remark: serializeRows() })

  // 同步更新期末坏账合计供K1-1/K1-8交叉验证读取
  const endTotalId = 'K1-3-bad-debt-end'
  const endPayload = { item_id: endTotalId, conclusion: null, remark: String(totalEndBadDebt.value) }
  props.allResponses.set(endTotalId, endPayload)
  emit('save', endTotalId, { remark: String(totalEndBadDebt.value) })
}

// ─── 合计行方法 ──────────────────────────────────────────────────────────────

function summaryMethod({ columns, data }: { columns: any[]; data: K1BadDebtRow[] }) {
  const sums: string[] = []
  columns.forEach((col: any, idx: number) => {
    if (idx === 0) { sums[idx] = '合计'; return }
    const prop = col.property
    if (['beginBadDebt', 'provision', 'reversal', 'writeoff', 'endBadDebt', 'receivableEnd'].includes(prop)) {
      const total = data.reduce((acc, row) => acc + ((row as any)[prop] || 0), 0)
      sums[idx] = fmtAmt(total)
    } else {
      sums[idx] = ''
    }
  })
  return sums
}

// ─── 导入导出 ─────────────────────────────────────────────────────────────────

function handleExportTemplate() { exportTemplate('K1-3' as any) }
function handleExportData() { exportData('K1-3' as any) }

function handleImportData() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls'
  input.onchange = async (e) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return
    const result = await importData('K1-3' as any, file)
    if (result) { loadRows() }
  }
  input.click()
}

// ─── UI Helpers ──────────────────────────────────────────────────────────────

function stageTagType(stage: 1 | 2 | 3): 'success' | 'warning' | 'danger' {
  if (stage === 3) return 'danger'
  if (stage === 2) return 'warning'
  return 'success'
}

function handleAiGenerate(section: string) {
  console.log('[K1-3] AI generate:', section)
}
function handleReview(id: string) { openReviewDialog(id) }

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k1-tab-bad-debt-detail {
  padding: 16px;
  font-size: 13px;
}

/* 方法论上下文（琥珀色） */
.methodology-context {
  border-left: 4px solid var(--el-color-warning);
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 16px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  line-height: 1.6;
}

/* 标题栏 */
.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.sheet-title {
  font-size: 15px;
  font-weight: 600;
  margin: 0;
}
.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 表格 */
.bad-debt-table {
  font-size: 13px;
}
.amount-cell {
  font-variant-numeric: tabular-nums;
}
.amount-input {
  width: 100%;
}
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}

/* ═══ 三阶段矩阵 ═══ */
.stage-matrix {
  margin-top: 20px;
}
.matrix-title {
  font-size: 14px;
  font-weight: 600;
  margin: 0 0 10px;
}
.matrix-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
.matrix-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  overflow: hidden;
}
.matrix-card .card-header {
  padding: 6px 12px;
  font-weight: 600;
  font-size: 13px;
  color: #fff;
}
.matrix-card.stage-1 .card-header { background: var(--el-color-success); }
.matrix-card.stage-2 .card-header { background: var(--el-color-warning); }
.matrix-card.stage-3 .card-header { background: var(--el-color-danger); }
.matrix-card .card-body {
  padding: 10px 12px;
}
.metric {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 3px 0;
}
.metric-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.metric-value {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

/* ═══ 交叉验证面板 ═══ */
.cross-validation-panel {
  margin-top: 20px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 12px 16px;
}
.cv-title {
  font-size: 14px;
  font-weight: 600;
  margin: 0 0 10px;
}
.cv-items {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.cv-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 12px;
}
.cv-item.cv-pass {
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
}
.cv-item.cv-fail {
  background: #fef2f2;
  border: 1px solid #fecaca;
}
.cv-label {
  font-weight: 600;
  min-width: 100px;
}
.cv-detail {
  flex: 1;
  color: var(--el-text-color-regular);
}

/* ═══ 编制提示 ═══ */
.compile-hint {
  margin-top: 16px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.compile-hint summary {
  cursor: pointer;
  font-weight: 500;
}
.compile-hint ul {
  padding-left: 20px;
  margin-top: 8px;
  line-height: 1.8;
}
</style>
