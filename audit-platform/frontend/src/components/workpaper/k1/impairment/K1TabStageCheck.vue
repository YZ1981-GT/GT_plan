<!--
  K1TabStageCheck.vue — K1-7 三阶段划分检查表

  Columns: 往来对象/期末余额/信用风险是否显著增加(下拉)/是否已发生信用减值(下拉)/划分阶段(公式:determineStage)/上期阶段/变动说明
  Features:
  1. 63行虚拟滚动 (el-table max-height)
  2. Stage3行红色背景 / Stage2行橙色背景 / Stage1默认
  3. 统计面板: Stage1/2/3 各多少笔+金额占比
  4. 与K1-2明细阶段列联动(syncStagesToDetail)
  5. 动态行新增 (ElMessageBox.prompt)
  6. 导入导出 + AI辅助 + 复核
  7. 琥珀色方法论上下文 + 编制提示
  8. Uses: useK1StageCheck composable

  Spec: .kiro/specs/k1-other-receivables/ Task 4.5
  Requirements: 5.1-5.5
-->
<template>
  <div class="k1-tab-stage-check">
    <!-- 方法论上下文（琥珀色） -->
    <div class="methodology-context">
      <p>K1-7三阶段划分检查表按CAS 22要求将每笔其他应收款划分为ECL三阶段。
        阶段判定逻辑：已发生信用减值→Stage 3（整个存续期ECL）；信用风险显著增加→Stage 2（整个存续期ECL）；
        否则→Stage 1（12个月ECL）。划分结果自动联动K1-2明细表阶段列和K1-8坏账测算。</p>
    </div>

    <!-- 标题栏 + 操作 -->
    <div class="section-head">
      <h3 class="sheet-title">K1-7 三阶段划分检查表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" link @click="handleAiGenerate('K1-7-stage')">
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
        <el-button size="small" @click="handleReview('K1-7-stage')">💬 复核</el-button>
      </div>
    </div>

    <!-- 统计面板 -->
    <div class="stage-summary-panel">
      <div class="summary-card stage-1-card">
        <div class="card-label">Stage 1（正常）</div>
        <div class="card-stat">
          <span class="stat-count">{{ summary.stage1Count }} 笔</span>
          <span class="stat-amount">{{ fmtAmt(summary.stage1Total) }}</span>
          <span class="stat-pct">{{ fmtPct(summary.stage1Total) }}</span>
        </div>
      </div>
      <div class="summary-card stage-2-card">
        <div class="card-label">Stage 2（显著增加）</div>
        <div class="card-stat">
          <span class="stat-count">{{ summary.stage2Count }} 笔</span>
          <span class="stat-amount">{{ fmtAmt(summary.stage2Total) }}</span>
          <span class="stat-pct">{{ fmtPct(summary.stage2Total) }}</span>
        </div>
      </div>
      <div class="summary-card stage-3-card">
        <div class="card-label">Stage 3（已减值）</div>
        <div class="card-stat">
          <span class="stat-count">{{ summary.stage3Count }} 笔</span>
          <span class="stat-amount">{{ fmtAmt(summary.stage3Total) }}</span>
          <span class="stat-pct">{{ fmtPct(summary.stage3Total) }}</span>
        </div>
      </div>
    </div>

    <!-- 主表格（63行虚拟滚动） -->
    <el-table
      :data="rows"
      border
      size="small"
      :max-height="520"
      class="stage-check-table"
      :row-style="tableRowStyle"
    >
      <el-table-column label="往来对象" min-width="140" fixed>
        <template #default="{ row }">
          <span>{{ row.counterparty }}</span>
        </template>
      </el-table-column>

      <el-table-column label="期末余额" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.endBalance" size="small"
            :controls="false" class="amount-input"
            @change="(v: number) => handleUpdate(row.id, 'endBalance', v ?? 0)" />
          <span v-else class="amount-cell">{{ fmtAmt(row.endBalance) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="信用风险是否显著增加" min-width="160" align="center">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.isSignificantIncrease" size="small"
            @change="(v: boolean) => handleUpdate(row.id, 'isSignificantIncrease', v)">
            <el-option label="是" :value="true" />
            <el-option label="否" :value="false" />
          </el-select>
          <el-tag v-else :type="row.isSignificantIncrease ? 'warning' : 'info'" size="small">
            {{ row.isSignificantIncrease ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="是否已发生信用减值" min-width="150" align="center">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.isImpaired" size="small"
            @change="(v: boolean) => handleUpdate(row.id, 'isImpaired', v)">
            <el-option label="是" :value="true" />
            <el-option label="否" :value="false" />
          </el-select>
          <el-tag v-else :type="row.isImpaired ? 'danger' : 'info'" size="small">
            {{ row.isImpaired ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="划分阶段" min-width="110" align="center">
        <template #default="{ row }">
          <span class="formula-cell" title="阶段=已减值→3；显著增加→2；否则→1">
            <el-tag :type="stageTagType(row.stage)" size="small" effect="dark">
              Stage {{ row.stage }}
            </el-tag>
          </span>
        </template>
      </el-table-column>

      <el-table-column label="上期阶段" min-width="100" align="center">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.priorStage" size="small"
            @change="(v: number) => handleUpdate(row.id, 'priorStage', v)">
            <el-option label="Stage 1" :value="1" />
            <el-option label="Stage 2" :value="2" />
            <el-option label="Stage 3" :value="3" />
          </el-select>
          <span v-else>Stage {{ row.priorStage }}</span>
        </template>
      </el-table-column>

      <el-table-column label="变动说明" min-width="160">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.changeNote" size="small"
            placeholder="阶段变动原因"
            @change="(v: string) => handleUpdate(row.id, 'changeNote', v)" />
          <span v-else>{{ row.changeNote || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="danger" link @click="handleRemoveRow(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- K1-2联动按钮 -->
    <div class="sync-actions">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="handleSyncToDetail">
        同步阶段至K1-2明细 →
      </el-button>
      <el-button size="small" link type="primary" @click="emit('navigate-sheet', 'K1-2 明细表')">
        跳转K1-2 →
      </el-button>
    </div>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>阶段判定逻辑：已发生信用减值→Stage 3；信用风险显著增加→Stage 2；否则→Stage 1（自动计算）</li>
        <li>Stage 3行以红色背景标记，Stage 2行以橙色背景标记</li>
        <li>完成划分后点击"同步阶段至K1-2明细"联动更新K1-2明细表阶段列</li>
        <li>上期阶段变动时需填写变动说明，作为阶段迁移审计证据</li>
        <li>统计面板实时显示各阶段笔数和金额占比</li>
        <li>"新增"按钮弹出对话框输入往来对象名称后创建行</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K1TabStageCheck.vue — K1-7 三阶段划分检查表
 * Spec: .kiro/specs/k1-other-receivables/ | Task: 4.5
 * Requirements: 5.1-5.5
 *
 * ECL阶段判定 + Stage着色 + 统计面板 + K1-2联动 + 虚拟滚动
 */
import { computed, inject, toRef, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useK1StageCheck, type K1StageRow } from '../../composables/useK1StageCheck'
import { useK1ImportExport } from '../../composables/useK1ImportExport'

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
  summary,
  loadRows,
  addRow,
  removeRow,
  updateRow,
  getRowStyle,
  syncStagesToDetail,
  serializeRows,
} = useK1StageCheck({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
})

const {
  exportTemplate,
  exportData,
  importData,
} = useK1ImportExport({ wpId: toRef(props, 'wpId') })

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  loadRows()
})

// ─── 合计金额（用于占比计算） ─────────────────────────────────────────────────

const totalBalance = computed(() =>
  summary.value.stage1Total + summary.value.stage2Total + summary.value.stage3Total
)

// ─── 行操作 ──────────────────────────────────────────────────────────────────

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入往来对象名称',
      '新增阶段划分行',
      { confirmButtonText: '确定', cancelButtonText: '取消', inputPlaceholder: '往来对象名称' }
    )
    if (!value || !value.trim()) {
      ElMessage.warning('往来对象名称不能为空')
      return
    }
    addRow(value.trim(), 0)
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

function handleUpdate(id: string, field: keyof K1StageRow, value: any) {
  updateRow(id, field, value)
  persistRows()
}

/** 持久化行数据 */
function persistRows() {
  const itemId = 'K1-7-stage-rows'
  const payload = { item_id: itemId, conclusion: null, remark: serializeRows() }
  props.allResponses.set(itemId, payload)
  emit('save', itemId, { remark: serializeRows() })
}

/** 同步阶段到K1-2明细 */
function handleSyncToDetail() {
  const stageMap = syncStagesToDetail()
  // 将阶段映射序列化后存储，供K1-2读取
  const mapObj = Object.fromEntries(stageMap)
  const syncId = 'K1-7-stage-sync'
  const payload = { item_id: syncId, conclusion: null, remark: JSON.stringify(mapObj) }
  props.allResponses.set(syncId, payload)
  emit('save', syncId, { remark: JSON.stringify(mapObj) })
  ElMessage.success(`已同步 ${stageMap.size} 笔阶段划分至K1-2明细`)
}

// ─── 导入导出 ─────────────────────────────────────────────────────────────────

function handleExportTemplate() { exportTemplate('K1-7') }
function handleExportData() { exportData('K1-7') }

function handleImportData() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls'
  input.onchange = async (e) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return
    const result = await importData('K1-7', file)
    if (result) { loadRows() }
  }
  input.click()
}

// ─── 表格行样式（Stage着色） ─────────────────────────────────────────────────

function tableRowStyle({ row }: { row: K1StageRow }): Record<string, string> {
  if (row.stage === 3) return { 'background-color': '#fde2e2' }
  if (row.stage === 2) return { 'background-color': '#fdf0e2' }
  return {}
}

// ─── UI Helpers ──────────────────────────────────────────────────────────────

function stageTagType(stage: 1 | 2 | 3): 'success' | 'warning' | 'danger' {
  if (stage === 3) return 'danger'
  if (stage === 2) return 'warning'
  return 'success'
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(stageTotal: number): string {
  if (totalBalance.value === 0) return '0.00%'
  return ((stageTotal / totalBalance.value) * 100).toFixed(2) + '%'
}

function handleAiGenerate(section: string) {
  console.log('[K1-7] AI generate:', section)
}
function handleReview(id: string) { openReviewDialog(id) }
</script>

<style scoped>
.k1-tab-stage-check {
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

/* 统计面板 */
.stage-summary-panel {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}
.summary-card {
  border-radius: 6px;
  padding: 10px 14px;
  border: 1px solid var(--el-border-color-lighter);
}
.summary-card .card-label {
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 6px;
}
.summary-card .card-stat {
  display: flex;
  gap: 12px;
  align-items: baseline;
  font-size: 12px;
}
.stat-count { font-weight: 600; }
.stat-amount { font-variant-numeric: tabular-nums; }
.stat-pct { color: var(--el-text-color-secondary); }

.stage-1-card { background: #f0fdf4; border-color: #bbf7d0; }
.stage-1-card .card-label { color: var(--el-color-success-dark-2); }
.stage-2-card { background: #fffbeb; border-color: #fde68a; }
.stage-2-card .card-label { color: var(--el-color-warning-dark-2); }
.stage-3-card { background: #fef2f2; border-color: #fecaca; }
.stage-3-card .card-label { color: var(--el-color-danger-dark-2); }

/* 表格 */
.stage-check-table {
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
}

/* 同步按钮区 */
.sync-actions {
  margin-top: 14px;
  display: flex;
  gap: 12px;
  align-items: center;
}

/* 编制提示 */
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
