<template>
  <div class="k13-tab-detail">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>发生与完整性：</b>各明细项营业外支出真实发生、记录完整，合计与 K13-1 审定数一致；</li>
        <li><b>准确性与分类：</b>各项金额准确、按支出性质恰当分类，关注税前扣除性。</li>
      </ol>
    </el-alert>

    <!-- ═══ Section标题 + AI + 复核 + 导入导出 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <h3>K13-2 营业外支出明细表</h3>
        <el-tag size="small" type="info" effect="plain">{{ rows.length }} 行</el-tag>
      </div>
      <div class="header-actions">
        <el-dropdown trigger="click" @command="handleImportExportCmd">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item command="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item command="importData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" type="primary" text @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" text @click="openReviewDialog?.('K13-2-detail', '营业外支出明细')">💬 复核</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>
        逐笔登记本期营业外支出明细，按去向分类（非流动资产处置损失/捐赠支出/罚款滞纳金/债务重组损失/资产盘亏损失等）。
        <strong>损益类借方科目</strong>：金额取借方发生额。合计行联动K13-1审定表发生额。
      </p>
    </div>

    <!-- ═══ 跨底稿引用（GtIndexChip） ═══ -->
    <div class="cross-ref-bar">
      <span class="cross-refs-label">关联引用：</span>
      <GtIndexChip value="K13-1" :context-project-id="props.projectId" />
      <GtIndexChip value="K13-4" :context-project-id="props.projectId" />
    </div>

    <!-- ═══ 3区段 Tab（基础信息 | 分析 | 检查） ═══ -->
    <el-segmented
      v-model="currentTab"
      :options="tabLabels"
      size="small"
      class="segment-toggle"
    />

    <!-- ═══ 明细表格（27行虚拟滚动 via max-height） ═══ -->
    <el-table
      :data="rows"
      border
      size="small"
      style="width: 100%; font-size: 13px"
      max-height="560"
      show-summary
      :summary-method="getSummaries"
    >
      <el-table-column type="index" label="#" width="42" align="center" />

      <!-- ════════ 区段1: 基础信息 ════════ -->
      <template v-if="currentTab === '基础信息'">
        <el-table-column prop="project" label="支出去向/项目" min-width="150">
          <template #default="{ row }">
            <el-input v-if="!isReadonly && row.isEditable" :model-value="row.project" size="small" @change="(v: string) => updateCell(row.rowKey, 'project', v)" />
            <span v-else>{{ row.project || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="expenseType" label="支出类型" width="140">
          <template #default="{ row }">
            <el-select v-if="!isReadonly && row.isEditable" :model-value="row.expenseType" size="small" placeholder="—" @change="(v: string) => updateCell(row.rowKey, 'expenseType', v)">
              <el-option v-for="opt in expenseTypeOptions" :key="opt" :value="opt" :label="opt" />
            </el-select>
            <span v-else>{{ row.expenseType || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="counterparty" label="对方单位" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly && row.isEditable" :model-value="row.counterparty" size="small" @change="(v: string) => updateCell(row.rowKey, 'counterparty', v)" />
            <span v-else>{{ row.counterparty || '—' }}</span>
          </template>
        </el-table-column>
        <!-- 1~12月列 -->
        <el-table-column v-for="m in 12" :key="`m-${m}`" :label="`${m}月`" width="85" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && row.isEditable" :model-value="row.monthAmounts[m - 1]" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateMonthAmount(row.rowKey, m - 1, v ?? 0)" />
            <span v-else>{{ fmtAmt(row.monthAmounts[m - 1]) }}</span>
          </template>
        </el-table-column>
        <!-- 本期合计（公式列） -->
        <el-table-column label="本期合计" width="110" align="right">
          <template #header>
            <span class="formula-col" title="=SUM(1~12月)">本期合计</span>
          </template>
          <template #default="{ row }">
            <span class="formula-value" :title="`=SUM(1~12月) → ${fmtAmt(row.monthTotal)}`">{{ fmtAmt(row.monthTotal) }}</span>
          </template>
        </el-table-column>
        <!-- AJE -->
        <el-table-column prop="aje" label="AJE" width="95" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && row.isEditable" :model-value="row.aje" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateCell(row.rowKey, 'aje', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>
        <!-- RJE -->
        <el-table-column prop="rje" label="RJE" width="95" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && row.isEditable" :model-value="row.rje" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateCell(row.rowKey, 'rje', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.rje) }}</span>
          </template>
        </el-table-column>
        <!-- 审定数（公式列） -->
        <el-table-column label="审定数" width="110" align="right">
          <template #header>
            <span class="formula-col" title="=本期合计+AJE+RJE">审定数</span>
          </template>
          <template #default="{ row }">
            <span class="formula-value" :title="`=合计+AJE+RJE → ${fmtAmt(row.audited)}`">{{ fmtAmt(row.audited) }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- ════════ 区段2: 分析 ════════ -->
      <template v-if="currentTab === '分析'">
        <el-table-column prop="project" label="支出去向" min-width="140">
          <template #default="{ row }"><span>{{ row.project || '—' }}</span></template>
        </el-table-column>
        <el-table-column prop="nonRecurring" label="非经常性" width="85" align="center">
          <template #default="{ row }">
            <el-checkbox v-if="!isReadonly && row.isEditable" :model-value="row.nonRecurring" @change="(v: boolean) => updateCell(row.rowKey, 'nonRecurring', v)" />
            <span v-else>{{ row.nonRecurring ? '✓' : '' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="crossRef" label="交叉引用" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly && row.isEditable" :model-value="row.crossRef" size="small" @change="(v: string) => updateCell(row.rowKey, 'crossRef', v)" />
            <span v-else>{{ row.crossRef || '—' }}</span>
          </template>
        </el-table-column>
        <!-- 占比（公式列） -->
        <el-table-column label="占比" width="85" align="right">
          <template #header>
            <span class="formula-col" title="=本行审定/合计审定">占比</span>
          </template>
          <template #default="{ row }">
            <span class="formula-value" :title="`=审定数/总计`">{{ row.proportion != null ? (row.proportion * 100).toFixed(1) + '%' : '—' }}</span>
          </template>
        </el-table-column>
        <!-- 上期金额 -->
        <el-table-column prop="priorAmount" label="上期金额" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && row.isEditable" :model-value="row.priorAmount" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateCell(row.rowKey, 'priorAmount', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.priorAmount) }}</span>
          </template>
        </el-table-column>
        <!-- 上期AJE -->
        <el-table-column prop="priorAje" label="上期AJE" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && row.isEditable" :model-value="row.priorAje" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateCell(row.rowKey, 'priorAje', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.priorAje) }}</span>
          </template>
        </el-table-column>
        <!-- 上期RJE -->
        <el-table-column prop="priorRje" label="上期RJE" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && row.isEditable" :model-value="row.priorRje" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateCell(row.rowKey, 'priorRje', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.priorRje) }}</span>
          </template>
        </el-table-column>
        <!-- 上期审定（公式列） -->
        <el-table-column label="上期审定" width="110" align="right">
          <template #header>
            <span class="formula-col" title="=上期金额+上期AJE+上期RJE">上期审定</span>
          </template>
          <template #default="{ row }">
            <span class="formula-value" :title="`=上期+AJE+RJE`">{{ fmtAmt(row.priorAudited) }}</span>
          </template>
        </el-table-column>
        <!-- 上期占比（公式列） -->
        <el-table-column label="上期占比" width="85" align="right">
          <template #header>
            <span class="formula-col" title="=上期审定/上期合计">上期占比</span>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ row.priorProportion != null ? (row.priorProportion * 100).toFixed(1) + '%' : '—' }}</span>
          </template>
        </el-table-column>
        <!-- 同比变动（公式列） -->
        <el-table-column label="同比变动" width="100" align="right">
          <template #header>
            <span class="formula-col" title="=(本期审定-上期审定)/上期审定">同比变动</span>
          </template>
          <template #default="{ row }">
            <span class="formula-value" :class="{ 'yoy-warn': row.yoyChange != null && Math.abs(row.yoyChange) > 0.3 }" :title="`=(本期-上期)/上期`">
              {{ row.yoyChange != null ? (row.yoyChange * 100).toFixed(1) + '%' : '—' }}
            </span>
          </template>
        </el-table-column>
      </template>

      <!-- ════════ 区段3: 检查 (placeholder, K13-4 handles detail) ════════ -->
      <template v-if="currentTab === '检查'">
        <el-table-column prop="project" label="支出去向" min-width="130">
          <template #default="{ row }"><span>{{ row.project || '—' }}</span></template>
        </el-table-column>
        <el-table-column prop="audited" label="审定金额" width="110" align="right">
          <template #default="{ row }"><span>{{ fmtAmt(row.audited) }}</span></template>
        </el-table-column>
        <el-table-column prop="expenseType" label="支出类型" width="130">
          <template #default="{ row }"><span>{{ row.expenseType || '—' }}</span></template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="180">
          <template #default="{ row }">
            <el-input v-if="!isReadonly && row.isEditable" :model-value="row.remark" size="small" @change="(v: string) => updateCell(row.rowKey, 'remark', v)" />
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="100" align="center">
          <template #default>
            <el-tag size="small" type="info">→ K13-4</el-tag>
          </template>
        </el-table-column>
      </template>

      <!-- 操作列（所有区段，非只读时显示） -->
      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-button v-if="row.isEditable" link size="small" type="danger" @click="handleRemoveRow(row.rowKey)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 操作栏 ═══ -->
    <div class="table-actions">
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleAddRow">+ 新增明细</el-button>
    </div>

    <!-- 隐藏的文件导入input -->
    <input ref="importFileInput" type="file" accept=".xlsx,.xls,.csv" style="display:none" @change="handleFileSelected" />

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>逐笔登记本期营业外支出明细，损益类取<strong>借方发生额</strong></li>
        <li>按去向分类：非流动资产处置损失/捐赠支出/罚款滞纳金/债务重组损失/资产盘亏损失/其他</li>
        <li>基础区段：录入12个月发生额+AJE/RJE，审定数自动计算</li>
        <li>分析区段：标记非经常性+自动计算占比和同比变动率</li>
        <li>检查区段：查看概况，详细检查见K13-4</li>
        <li>合计行自动聚合，联动K13-1审定表发生额</li>
        <li>同比变动 &gt; ±30% 时标黄提醒关注</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K13TabDetail.vue — K13-2 营业外支出明细表（26列3区段+动态行+27行+导入导出）
 *
 * Spec: .kiro/specs/k13-non-operating-expense/ | Task: 4.3
 * Requirements: 3.1-3.4
 *
 * 功能：
 * - 26列拆为3区段Tab切换：基础信息(项目/类型/单位/1~12月/合计/AJE/RJE/审定) | 分析(非经常/引用/占比/上期/同比) | 检查(placeholder→K13-4)
 * - 动态行（ElMessageBox.prompt命名后创建）
 * - 导入导出：el-dropdown「导入导出▾」3项 使用useK13ImportExport
 * - 合计行（show-summary, sticky via max-height）
 * - 公式列虚线下划线 + tooltip
 * - 虚拟滚动：max-height=560 支持27+行
 *
 * 科目：6711营业外支出（损益类借方科目，取发生额）
 */
import { ref, computed, inject, defineAsyncComponent, toRef } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useK13Detail, EXPENSE_TYPE_OPTIONS, DETAIL_TABS } from '../../composables/useK13Detail'
import { useK13ImportExport } from '../../composables/useK13ImportExport'

const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
}>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── Composable: useK13Detail ────────────────────────────────────────────────

const {
  rows,
  subtotal,
  activeTab,
  updateCell,
  updateMonthAmount,
  addRow,
  removeRow,
} = useK13Detail({
  allResponses: toRef(props, 'allResponses'),
  projectId: toRef(props, 'projectId'),
  wpId: toRef(props, 'wpId'),
  isReadonly: toRef(props, 'isReadonly'),
  onSave: (itemId: string, value: any) => emit('save', itemId, value),
})

// ─── Composable: useK13ImportExport ──────────────────────────────────────────

const importExport = useK13ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  sheetCode: 'K13-2',
})

// ─── Tab mapping ─────────────────────────────────────────────────────────────

const tabLabels = DETAIL_TABS.map(t => t.label)
const currentTab = ref('基础信息')

// ─── 支出类型选项 ────────────────────────────────────────────────────────────

const expenseTypeOptions = EXPENSE_TYPE_OPTIONS

// ─── 动态行操作（ElMessageBox.prompt） ───────────────────────────────────────

async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入支出去向/项目名称', '新增明细', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：XX罚款/XX捐赠支出/XX资产报废...',
    })
    if (value?.trim()) {
      addRow(value.trim())
    }
  } catch { /* cancelled */ }
}

function handleRemoveRow(rowKey: string): void {
  removeRow(rowKey)
}

// ─── 导入导出处理 ────────────────────────────────────────────────────────────

const importFileInput = ref<HTMLInputElement | null>(null)

function handleImportExportCmd(cmd: string): void {
  switch (cmd) {
    case 'exportTemplate':
      importExport.exportTemplate()
      break
    case 'exportData':
      importExport.exportData()
      break
    case 'importData':
      importFileInput.value?.click()
      break
  }
}

async function handleFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  input.value = '' // reset

  const result = await importExport.importData(file)
  if (result && result.rowCount > 0) {
    // 触发重新加载
    ElMessage.success(`已导入 ${result.rowCount} 行明细数据`)
  }
}

// ─── 合计行 ──────────────────────────────────────────────────────────────────

function getSummaries({ columns }: any): string[] {
  return columns.map((col: any, idx: number) => {
    if (idx === 0) return '合计'
    if (currentTab.value === '基础信息') {
      if (col.property === 'aje') return fmtAmt(subtotal.value.aje)
      if (col.property === 'rje') return fmtAmt(subtotal.value.rje)
      // 本期合计列和审定数列通过label匹配
      if (col.label === '本期合计') return fmtAmt(subtotal.value.monthTotal)
      if (col.label === '审定数') return fmtAmt(subtotal.value.audited)
    }
    if (currentTab.value === '分析') {
      if (col.label === '上期审定') return fmtAmt(subtotal.value.priorAudited)
    }
    return ''
  })
}

// ─── UI Helpers ──────────────────────────────────────────────────────────────

function fmtAmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function handleAiAssist(): void {
  ElMessage.info('AI辅助明细分析...')
}
</script>

<style scoped>
.k13-tab-detail { padding: 12px; font-size: var(--wp-font-size, 13px); }

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
  border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6;
}
.methodology-context p { margin: 0; }

.cross-ref-bar {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  margin-bottom: 12px; padding: 6px 12px;
  background: #f5f7fa; border-radius: 6px;
}
.cross-refs-label { color: #909399; font-size: 12px; white-space: nowrap; }

.segment-toggle { margin-bottom: 12px; }

/* 公式列样式 — 虚线下划线 + cursor:help + tooltip */
.formula-col {
  border-bottom: 1px dashed #909399;
  cursor: help;
  color: #606266;
}
.formula-value {
  border-bottom: 1px dashed #c0c4cc;
  cursor: help;
  color: #303133;
}

/* 同比变动>±30%高亮 */
.yoy-warn { color: #e6a23c; font-weight: 600; }

.table-actions { display: flex; gap: 8px; margin-top: 12px; }

:deep(.el-table) { font-size: var(--wp-font-size, 13px); }

/* sticky合计行 */
:deep(.el-table__footer-wrapper) {
  position: sticky; bottom: 0; z-index: 2;
  background: #fafafa; font-weight: 600;
}

.compile-hint {
  margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary);
  padding: 12px 16px; background: #fafafa;
  border: 1px solid #ebeef5; border-radius: 6px;
}
.compile-hint summary { cursor: pointer; font-weight: 500; color: #303133; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
