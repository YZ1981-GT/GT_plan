<template>
  <div class="n4-tab-detail">
    <!-- ═══ Section标题 + AI + 复核 + 导入导出 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <h3>N4-2 税金及附加明细表</h3>
        <el-tag size="small" type="info" effect="plain">{{ detail.rows.value.length }} 税种</el-tag>
      </div>
      <div class="header-actions">
        <el-dropdown size="small" trigger="click" @command="handleImportExport">
          <el-button size="small" type="info" plain>
            导入导出 ▾
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
              <el-dropdown-item command="import-data" divided>导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" type="primary" text @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" text @click="openReviewDialog?.('N4-2-detail', '税金及附加明细')">💬 复核</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>
        按税种逐行登记本期税金及附加发生额明细，核对计税依据×税率。
        <strong>本期税额 = 计税依据 × 税率</strong>；同比变动 = (本期-上期)/上期；差异 = 本期税额 - N2计提额。
        差异≠0的行标红高亮，需查明原因。合计行联动N4-1审定表交叉验证。
      </p>
    </div>

    <!-- ═══ 跨底稿引用 ═══ -->
    <div class="cross-ref-bar">
      <span class="cross-refs-label">关联引用：</span>
      <GtIndexChip value="N4-1" :context-project-id="props.projectId" />
      <GtIndexChip value="N2-1" :context-project-id="props.projectId" />
    </div>

    <!-- ═══ 明细表格（11列） ═══ -->
    <el-table
      :data="detail.rows.value"
      border
      size="small"
      style="width: 100%; font-size: 13px"
      max-height="560"
      :row-class-name="getRowClassName"
    >
      <!-- 序号 -->
      <el-table-column prop="seq" label="序号" width="50" align="center" fixed="left" />

      <!-- 税种 -->
      <el-table-column prop="taxType" label="税种" min-width="130" fixed="left">
        <template #default="{ row }">
          <span>{{ row.taxType || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 计税依据 -->
      <el-table-column prop="taxBasis" label="计税依据" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly && row.isEditable"
            :model-value="row.taxBasis"
            size="small"
            :controls="false"
            :precision="2"
            style="width: 100%"
            @change="(v: number | undefined) => detail.updateCell(row.rowKey, 'taxBasis', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(row.taxBasis) }}</span>
        </template>
      </el-table-column>

      <!-- 税率 -->
      <el-table-column prop="taxRate" label="税率" width="90" align="center">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly && row.isEditable"
            :model-value="row.taxRate"
            size="small"
            :controls="false"
            :precision="6"
            :step="0.01"
            style="width: 100%"
            @change="(v: number | undefined) => detail.updateCell(row.rowKey, 'taxRate', v ?? 0)"
          />
          <span v-else>{{ fmtRate(row.taxRate) }}</span>
        </template>
      </el-table-column>

      <!-- 本期税额（公式列：计税依据×税率） -->
      <el-table-column label="本期税额" min-width="120" align="right" class-name="formula-col">
        <template #header>
          <span class="formula-header" title="本期税额 = 计税依据 × 税率">本期税额</span>
        </template>
        <template #default="{ row }">
          <el-tooltip :content="`${fmtAmt(row.taxBasis)} × ${fmtRate(row.taxRate)} = ${fmtAmt(row.periodAmount)}`" placement="top">
            <span class="formula-value">{{ fmtAmt(row.periodAmount) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>

      <!-- 上期税额 -->
      <el-table-column prop="priorAmount" label="上期税额" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly && row.isEditable"
            :model-value="row.priorAmount"
            size="small"
            :controls="false"
            :precision="2"
            style="width: 100%"
            @change="(v: number | undefined) => detail.updateCell(row.rowKey, 'priorAmount', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(row.priorAmount) }}</span>
        </template>
      </el-table-column>

      <!-- 同比变动（公式列） -->
      <el-table-column label="同比变动" width="100" align="right" class-name="formula-col">
        <template #header>
          <span class="formula-header" title="同比变动 = (本期-上期)/上期">同比变动</span>
        </template>
        <template #default="{ row }">
          <el-tooltip :content="row.yoyChange != null ? `(${fmtAmt(row.periodAmount)} - ${fmtAmt(row.priorAmount)}) / ${fmtAmt(row.priorAmount)}` : '上期为0，不计算'" placement="top">
            <span class="formula-value" :class="{ negative: row.yoyChange != null && row.yoyChange < 0 }">
              {{ fmtYoy(row.yoyChange) }}
            </span>
          </el-tooltip>
        </template>
      </el-table-column>

      <!-- N2计提额（只读，来自EventBus） -->
      <el-table-column prop="n2Accrual" label="N2计提额" min-width="110" align="right">
        <template #header>
          <span class="n2-header" title="来自N2应交税费底稿计提额（只读）">N2计提额</span>
        </template>
        <template #default="{ row }">
          <span class="n2-value">{{ fmtAmt(row.n2Accrual) }}</span>
        </template>
      </el-table-column>

      <!-- 差异（公式列：本期税额 - N2计提额） -->
      <el-table-column label="差异" width="100" align="right" class-name="formula-col">
        <template #header>
          <span class="formula-header" title="差异 = 本期税额 - N2计提额">差异</span>
        </template>
        <template #default="{ row }">
          <el-tooltip :content="`${fmtAmt(row.periodAmount)} - ${fmtAmt(row.n2Accrual)} = ${fmtAmt(row.diff)}`" placement="top">
            <span class="formula-value" :class="{ 'diff-nonzero': row.diff !== 0 }">
              {{ fmtAmt(row.diff) }}
            </span>
          </el-tooltip>
        </template>
      </el-table-column>

      <!-- 核查结论 -->
      <el-table-column prop="conclusion" label="结论" min-width="120">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly && row.isEditable"
            :model-value="row.conclusion"
            size="small"
            placeholder="—"
            clearable
            @change="(v: string) => detail.updateCell(row.rowKey, 'conclusion', v)"
          >
            <el-option v-for="opt in CONCLUSION_OPTIONS" :key="opt" :value="opt" :label="opt" />
          </el-select>
          <span v-else>{{ row.conclusion || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 备注 -->
      <el-table-column prop="remark" label="备注" min-width="120">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly && row.isEditable"
            :model-value="row.remark"
            size="small"
            @change="(v: string) => detail.updateCell(row.rowKey, 'remark', v)"
          />
          <span v-else>{{ row.remark || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-button v-if="row.isEditable" link size="small" type="danger" @click="handleRemoveRow(row.rowKey)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 合计行（底部固定） ═══ -->
    <div class="subtotal-bar">
      <span class="subtotal-label">合  计</span>
      <span class="subtotal-item">本期税额: <strong>{{ fmtAmt(detail.subtotal.value.periodAmount) }}</strong></span>
      <span class="subtotal-item">上期税额: <strong>{{ fmtAmt(detail.subtotal.value.priorAmount) }}</strong></span>
      <span class="subtotal-item">N2计提: <strong>{{ fmtAmt(detail.subtotal.value.n2Accrual) }}</strong></span>
      <span class="subtotal-item formula-value" :class="{ 'diff-nonzero': detail.subtotal.value.diff !== 0 }" :title="`差异合计 = ${detail.subtotal.value.periodAmount} - ${detail.subtotal.value.n2Accrual}`">
        差异: <strong>{{ fmtAmt(detail.subtotal.value.diff) }}</strong>
      </span>
    </div>

    <!-- ═══ 操作栏 ═══ -->
    <div class="table-actions">
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleAddRow">+ 新增税种</el-button>
    </div>

    <!-- ═══ 底部统计摘要面板 ═══ -->
    <div class="stats-panel">
      <div class="stat-item">
        <span class="stat-label">税种数</span>
        <span class="stat-value">{{ detail.summary.value.taxCount }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">总金额（本期）</span>
        <span class="stat-value">{{ fmtAmt(detail.summary.value.totalAmount) }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">平均同比变动</span>
        <span class="stat-value" :class="{ negative: detail.summary.value.avgYoyChange != null && detail.summary.value.avgYoyChange < 0 }">
          {{ fmtYoy(detail.summary.value.avgYoyChange) }}
        </span>
      </div>
      <div class="stat-item">
        <span class="stat-label">差异行数</span>
        <span class="stat-value" :class="{ 'diff-nonzero': diffRowCount > 0 }">{{ diffRowCount }}</span>
      </div>
    </div>

    <!-- 导入 file input (隐藏) -->
    <input ref="importFileInput" type="file" accept=".xlsx,.xls" style="display:none" @change="handleImportFileSelected" />

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>逐笔登记本期税金及附加明细，按税种分行记录</li>
        <li>本期税额 = 计税依据 × 税率（公式自动计算，不可手动修改）</li>
        <li>同比变动 = (本期-上期)/上期（上期为0时显示"—"）</li>
        <li>差异 = 本期税额 - N2计提额，差异≠0的行自动标红</li>
        <li>N2计提额为只读数据，来自N2应交税费底稿（EventBus联动）</li>
        <li>合计行联动N4-1审定表，用于交叉验证</li>
        <li>动态新增时需先输入税种名称</li>
        <li>支持导入导出（模板/数据/导入），建议行数较多时用导入功能</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N4TabDetail.vue — N4-2 税金及附加明细表（11列18公式，动态行）
 *
 * Spec: .kiro/specs/n4-taxes-and-surcharges/ | Task: 4.3
 * Requirements: 3.1-3.6
 *
 * 功能：
 * - 11列：序号/税种/计税依据/税率/本期税额(公式)/上期税额/同比变动(公式)/N2计提额(只读)/差异(公式)/结论/备注
 * - 18公式：本期税额=计税依据×税率；同比变动=(本期-上期)/上期；差异=本期-N2计提额
 * - 动态行新增（ElMessageBox.prompt输入税种名称）
 * - N2计提额只读（来自EventBus 'tax-accrual:updated'）
 * - 差异≠0红色行高亮
 * - 统计摘要（税种数/总金额/平均同比）
 * - el-dropdown导入导出（三级：模板/数据/导入）
 * - GtIndexChip跨底稿引用（N4-1 / N2-1）
 */
import { ref, computed, inject, toRef, defineAsyncComponent } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useN4Detail } from '../../composables/useN4Detail'
import { useN4ImportExport } from '../../composables/useN4ImportExport'

const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
}>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── Constants ───────────────────────────────────────────────────────────────

const CONCLUSION_OPTIONS = ['正常', '差异已查明', '需进一步核查'] as const

// ─── Composable ──────────────────────────────────────────────────────────────

const isReadonly = computed(() => props.isReadonly ?? false)

const detail = useN4Detail({
  allResponses: toRef(props, 'allResponses'),
  projectId: toRef(props, 'projectId'),
  wpId: toRef(props, 'wpId'),
  isReadonly: toRef(props, 'isReadonly'),
  onSave: (itemId, value) => emit('save', itemId, value),
})

const importExport = useN4ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

// ─── 导入导出 ────────────────────────────────────────────────────────────────

const importFileInput = ref<HTMLInputElement | null>(null)

function handleImportExport(command: string): void {
  switch (command) {
    case 'export-template':
      importExport.exportTemplate('N4-2')
      break
    case 'export-data':
      importExport.exportData('N4-2')
      break
    case 'import-data':
      importFileInput.value?.click()
      break
  }
}

async function handleImportFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  input.value = ''

  const result = await importExport.importData(file, 'N4-2')
  if (result.success && result.rowCount && result.rowCount > 0) {
    // 刷新数据：重新初始化
    detail.initFromResponses()
    ElMessage.success(`已导入 ${result.rowCount} 行税种明细`)
  }
}

// ─── 行操作 ──────────────────────────────────────────────────────────────────

async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入税种名称', '新增税种', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：城市维护建设税/印花税/房产税...',
    })
    if (value?.trim()) {
      detail.addRow(value.trim())
    }
  } catch { /* cancelled */ }
}

function handleRemoveRow(rowKey: string): void {
  detail.removeRow(rowKey)
}

// ─── 行样式：差异≠0标红 ─────────────────────────────────────────────────────

function getRowClassName({ row }: { row: any }): string {
  if (row.diff !== 0) return 'diff-highlight-row'
  return ''
}

// ─── 统计 ────────────────────────────────────────────────────────────────────

const diffRowCount = computed(() => {
  return detail.rows.value.filter(r => r.diff !== 0).length
})

// ─── UI Helpers ──────────────────────────────────────────────────────────────

function fmtAmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(v: number | null | undefined): string {
  if (v == null || v === 0) return '—'
  // 显示为百分比（如 0.07 → 7%）
  return (v * 100).toFixed(2).replace(/\.?0+$/, '') + '%'
}

function fmtYoy(v: number | null | undefined): string {
  if (v == null) return '—'
  const pct = (v * 100).toFixed(1)
  return (v > 0 ? '+' : '') + pct + '%'
}

function handleAiAssist(): void {
  ElMessage.info('AI辅助分析税金及附加明细...')
}
</script>

<style scoped>
.n4-tab-detail { padding: 12px; font-size: 13px; }

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
  border-radius: 4px; font-size: 13px; color: #78350f; line-height: 1.6;
}
.methodology-context p { margin: 0; }

.cross-ref-bar {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  margin-bottom: 12px; padding: 6px 12px;
  background: #f5f7fa; border-radius: 6px;
}
.cross-refs-label { color: #909399; font-size: 12px; white-space: nowrap; }

/* 公式列样式 */
:deep(.formula-col) .cell { border-bottom: 1px dashed #909399; }
.formula-header {
  cursor: help;
  border-bottom: 1px dashed #606266;
  padding-bottom: 1px;
}
.formula-value {
  cursor: help;
  border-bottom: 1px dashed #c0c4cc;
  padding-bottom: 1px;
}

/* N2只读列样式 */
.n2-header {
  cursor: help;
  color: #909399;
  border-bottom: 1px dashed #c0c4cc;
  padding-bottom: 1px;
}
.n2-value {
  color: #909399;
  font-style: italic;
}

/* 差异标红 */
.diff-nonzero { color: #f56c6c; font-weight: 600; }
.negative { color: #f56c6c; }

/* 行高亮：差异≠0红色背景 */
:deep(.diff-highlight-row) {
  background-color: #fef0f0 !important;
}
:deep(.diff-highlight-row:hover > td) {
  background-color: #fde2e2 !important;
}

:deep(.el-table) { font-size: 13px; }

.subtotal-bar {
  display: flex; gap: 16px; align-items: center; flex-wrap: wrap;
  margin-top: 10px; padding: 8px 14px;
  background: #f5f7fa; border-radius: 6px;
  font-size: 13px;
}
.subtotal-label { font-weight: 700; color: #303133; min-width: 48px; }
.subtotal-item { color: #606266; }
.subtotal-item strong { color: #303133; }

.table-actions { display: flex; gap: 8px; margin-top: 12px; }

.stats-panel {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;
  margin-top: 16px; padding: 12px 16px;
  background: #fafafa; border-radius: 8px; border: 1px solid #ebeef5;
}
.stat-item { text-align: center; }
.stat-label { display: block; font-size: 11px; color: #909399; margin-bottom: 4px; }
.stat-value { display: block; font-size: 14px; font-weight: 600; color: #303133; }

.compile-hint {
  margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary);
  padding: 12px 16px; background: #fafafa;
  border: 1px solid #ebeef5; border-radius: 6px;
}
.compile-hint summary { cursor: pointer; font-weight: 500; color: #303133; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
