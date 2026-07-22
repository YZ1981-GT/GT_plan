<template>
  <div class="k9-tab-detail">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>发生与完整性：</b>各明细项管理费用真实发生且记录完整，合计与 K9-1 审定数一致；</li>
        <li><b>准确性与分类：</b>各费用明细金额准确、按费用性质恰当分类。</li>
      </ol>
    </el-alert>

    <!-- ═══ Section标题 + 导入导出 + AI + 复核 ═══ -->
    <div class="section-header">
      <h3>K9-2 管理费用明细表</h3>
      <div class="header-actions">
        <el-dropdown size="small" trigger="click" @command="handleImportExport">
          <el-button size="small">
            导入导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
              <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" type="primary" plain @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI波动分析
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><ChatDotSquare /></el-icon> 复核
        </el-button>
        <el-button
          size="small"
          type="warning"
          plain
          :loading="pullingI1"
          :disabled="isReadonly"
          data-testid="k9-pull-i1-amort"
          @click="handlePullI1Amort"
        >
          从 I1-9 取摊销
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>管理费用明细表从<strong>tb_ledger明细科目</strong>取发生额。25列拆为3区段Tab提升可操作性。合计行联动审定表K9-1。同比变动率&gt;±30%红色高亮需说明波动原因。</p>
    </div>

    <!-- ═══ 3区段Tab切换（el-segmented） ═══ -->
    <div class="tab-bar">
      <el-segmented
        v-model="activeTab"
        :options="tabOptions"
        size="small"
      />
      <div class="tab-right">
        <el-button size="small" type="success" plain :disabled="isReadonly" @click="handleAddRow">
          <el-icon><Plus /></el-icon> 新增明细
        </el-button>
      </div>
    </div>

    <!-- ═══ 明细表主表（55行虚拟滚动） ═══ -->
    <el-table
      :data="tableData"
      border
      size="small"
      style="width: 100%"
      max-height="660"
      :row-class-name="detailRowClass"
    >
      <!-- 序号 -->
      <el-table-column type="index" label="序号" width="50" align="center" fixed />

      <!-- ═══ 基础区段 ═══ -->
      <template v-if="activeTab === 'basic'">
        <el-table-column prop="accountCode" label="科目编码" width="100" align="center">
          <template #default="{ row }">
            <el-input
              v-if="row.isEditable"
              :model-value="row.accountCode"
              :disabled="isReadonly"
              size="small"
              placeholder="编码"
              style="width: 80px"
              @blur="(e: FocusEvent) => handleCellChange(row.rowKey, 'accountCode', (e.target as HTMLInputElement)?.value ?? '')"
            />
            <span v-else>{{ row.accountCode }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="accountName" label="明细科目" min-width="140">
          <template #default="{ row }">
            <span class="account-name">{{ row.accountName }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期发生额" width="120" align="right">
          <template #default="{ row }">
            <el-tooltip content="公式：SUM(1~12月)" placement="top">
              <span class="formula-cell formula-underline">{{ fmtNum(row.unadjTotal) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
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
        <el-table-column label="审定数" width="120" align="right">
          <template #default="{ row }">
            <el-tooltip content="公式：未审+AJE+RJE" placement="top">
              <span class="formula-cell formula-underline">{{ fmtNum(row.audited) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
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
        <el-table-column label="操作" width="60" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.isEditable"
              type="danger"
              link
              size="small"
              :disabled="isReadonly"
              @click="handleRemoveRow(row.rowKey)"
            >
              <el-icon><Delete /></el-icon>
            </el-button>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 分析区段 ═══ -->
      <template v-if="activeTab === 'analysis'">
        <el-table-column prop="accountName" label="明细科目" min-width="140" fixed />
        <el-table-column label="本期审定" width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtNum(row.audited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上期发生" width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtNum(row.priorAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="同比变动率" width="110" align="right">
          <template #default="{ row }">
            <el-tooltip content="公式：(本期−上期)/|上期|" placement="top">
              <span
                class="formula-cell formula-underline"
                :class="{ 'abnormal-highlight': isAbnormalRate(row.yoyChangeRate) }"
              >
                {{ fmtRate(row.yoyChangeRate) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="占收入比" width="100" align="right">
          <template #default="{ row }">
            <el-tooltip content="公式：审定数/营业收入" placement="top">
              <span class="formula-cell formula-underline">{{ fmtRate(row.ratioToRevenue) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="波动说明" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="row.isEditable"
              :model-value="row.fluctuationNote"
              :disabled="isReadonly"
              size="small"
              placeholder="变动率>30%需说明波动原因"
              @blur="(e: FocusEvent) => handleCellChange(row.rowKey, 'fluctuationNote', (e.target as HTMLInputElement)?.value ?? '')"
            />
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 检查区段 ═══ -->
      <template v-if="activeTab === 'inspection'">
        <el-table-column prop="accountName" label="明细科目" min-width="140" fixed />
        <el-table-column label="审定数" width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtNum(row.audited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证抽查" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="row.isEditable"
              :model-value="row.voucherCheckResult"
              :disabled="isReadonly"
              size="small"
              placeholder="凭证抽查结论"
              @blur="(e: FocusEvent) => handleCellChange(row.rowKey, 'voucherCheckResult', (e.target as HTMLInputElement)?.value ?? '')"
            />
          </template>
        </el-table-column>
        <el-table-column label="核查结论" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="row.isEditable"
              :model-value="row.inspectionConclusion"
              :disabled="isReadonly"
              size="small"
              placeholder="核查结论"
              @blur="(e: FocusEvent) => handleCellChange(row.rowKey, 'inspectionConclusion', (e.target as HTMLInputElement)?.value ?? '')"
            />
          </template>
        </el-table-column>
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
      </template>
    </el-table>

    <!-- ═══ 底部统计栏 ═══ -->
    <div class="subtotal-bar">
      <span class="total-label">合  计</span>
      <span class="total-item">未审合计: <strong>{{ fmtNum(subtotal.unadjTotal) }}</strong></span>
      <span class="total-item">AJE: <strong>{{ fmtNum(subtotal.aje) }}</strong></span>
      <span class="total-item">RJE: <strong>{{ fmtNum(subtotal.rje) }}</strong></span>
      <span class="total-item">审定合计: <strong>{{ fmtNum(subtotal.audited) }}</strong></span>
      <span class="total-item">上期合计: <strong>{{ fmtNum(subtotal.priorAmount) }}</strong></span>
      <span class="total-item">共 <strong>{{ tableData.length }}</strong> 行</span>
    </div>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="k9-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>明细表从<strong>tb_ledger</strong>明细科目取发生额（非期末余额）</li>
        <li>25列按3区段Tab切换（基础/分析/检查）</li>
        <li>本期发生额=SUM(1~12月)；审定数=未审+AJE+RJE</li>
        <li>同比变动率=(本期−上期)/|上期|；占收入比=审定数/营业收入</li>
        <li>合计行应与K9-1审定表合计保持一致（交叉勾稽）</li>
        <li>变动率&gt;±30%需在"波动说明"列填写原因</li>
        <li>可点「从 I1-9 取摊销」回填本表「无形资产摊销」行（来自 I1-9-alloc-totals）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K9TabDetail.vue — K9-2 管理费用明细表
 * 55行×25列→3区段Tab（基础/分析/检查）+ 虚拟滚动
 *
 * 区段Tab用el-segmented切换，行同步。
 * 动态行新增：弹ElMessageBox.prompt输入科目名称确认后创建。
 * 导入导出：useK9ImportExport。
 * 合计行联动审定表K9-1。
 *
 * Spec: .kiro/specs/k9-admin-expenses/ | Task: 4.3
 * Requirements: 3.1-3.4
 */
import { computed, inject, ref, toRef, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, ChatDotSquare, ArrowDown, Plus, Delete } from '@element-plus/icons-vue'
import { useK9Detail, DETAIL_TABS, type K9DetailTabKey } from '../../composables/useK9Detail'
import { useK9ImportExport } from '../../composables/useK9ImportExport'
import { pullI1AmortIntoExpenseDetail } from '../../composables/expenseWpI1AmortPull'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  tbData?: { unadjusted6602?: number; audited6602?: number }
  isReadonly: boolean
}>()

// 父组件模板绑定会自动解包 ref → 子组件收到纯 Map；重新包成 ref 供 composable 使用
const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

// ─── 复核对话 inject ─────────────────────────────────────────────────────────
const openReviewDialog = inject<(sectionId: string, label?: string) => void>('openReviewDialog', () => {})

// ─── Tab state ───────────────────────────────────────────────────────────────
const activeTab = ref<K9DetailTabKey>('basic')
const tabOptions = DETAIL_TABS.map(t => ({ label: t.label, value: t.key }))

// ─── Composable wiring ───────────────────────────────────────────────────────

const {
  rows,
  subtotal,
  updateCell,
  addRow,
  removeRow,
  applyI1AmortAmount,
} = useK9Detail({
  allResponses: allResponsesRef,
  projectId: toRef(props, 'projectId') as Ref<string>,
  wpId: toRef(props, 'wpId') as Ref<string>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  onSave: (itemId: string, value: any) => {
    emit('save', itemId, value)
  },
})

const pullingI1 = ref(false)

async function handlePullI1Amort() {
  if (props.isReadonly) return
  pullingI1.value = true
  try {
    const result = await pullI1AmortIntoExpenseDetail(props.projectId, 'K9')
    if (!result.amount) {
      ElMessage.warning(result.message || 'I1-9 摊销合计为 0')
      return
    }
    const applied = applyI1AmortAmount(result.amount)
    if (applied.ok) ElMessage.success(applied.message)
    else ElMessage.warning(applied.message)
  } catch (e: any) {
    ElMessage.error(e?.message || '拉取 I1-9 失败')
  } finally {
    pullingI1.value = false
  }
}

// ─── 导入导出 composable ─────────────────────────────────────────────────────

const { exportTemplate, exportData, importData } = useK9ImportExport({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  sheetCode: 'K9-2',
})

// ─── 表格数据 ────────────────────────────────────────────────────────────────

const tableData = computed(() => rows.value)

const CHANGE_RATE_THRESHOLD = 0.3

function isAbnormalRate(rate: number | null): boolean {
  if (rate === null || rate === undefined) return false
  return Math.abs(rate) > CHANGE_RATE_THRESHOLD
}

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleCellChange(rowKey: string, field: string, value: any): void {
  updateCell(rowKey, field, value)
}

async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入明细科目名称', '新增明细科目', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPlaceholder: '如：差旅费、办公费等',
      inputValidator: (v: string) => {
        if (!v || !v.trim()) return '科目名称不能为空'
        return true
      },
    })
    if (value && value.trim()) {
      addRow(value.trim())
    }
  } catch {
    // cancelled
  }
}

function handleRemoveRow(rowKey: string): void {
  removeRow(rowKey)
}

function handleImportExport(command: string): void {
  switch (command) {
    case 'export-template': exportTemplate(); break
    case 'export-data': exportData(); break
    case 'import-data': triggerImport(); break
  }
}

/** 触发文件选择器进行导入 */
function triggerImport(): void {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls,.csv'
  input.onchange = async (e: Event) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (file) await importData(file)
  }
  input.click()
}

function handleAiGenerate(): void {
  emit('save', 'K9-2-ai-trigger', { remark: 'generate' })
}

function handleReview(): void {
  openReviewDialog('K9-2', '管理费用明细表复核')
}

// ─── Row class ───────────────────────────────────────────────────────────────

function detailRowClass({ row }: { row: any }): string {
  if (isAbnormalRate(row.yoyChangeRate)) return 'abnormal-row'
  return ''
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
.k9-tab-detail { padding: 12px; font-size: var(--wp-font-size, 13px); }

/* ─── Section header ─── */
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; }

/* ─── 方法论上下文 ─── */
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }

/* ─── Tab栏 ─── */
.tab-bar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.tab-right { display: flex; gap: 8px; }

/* ─── 表格 ─── */
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.account-name { font-size: var(--wp-font-size, 13px); color: #303133; }
.formula-cell { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #303133; }
.formula-underline { border-bottom: 1px dashed #909399; cursor: help; }
.abnormal-highlight { color: #f56c6c !important; font-weight: 600; }
:deep(.abnormal-row) { background-color: #fef0f0 !important; }

/* ─── 底部统计栏 ─── */
.subtotal-bar {
  display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
  margin: 12px 0; padding: 10px 14px;
  background: linear-gradient(90deg, #eef6ff 0%, #f5faff 100%);
  border: 1px solid #d6e4f0; border-radius: 6px; font-size: var(--wp-font-size, 13px);
}
.total-label { font-weight: 700; color: #303133; min-width: 50px; }
.total-item { color: #606266; }
.total-item strong { color: #303133; font-family: 'JetBrains Mono', monospace; }

/* ─── 编制提示 ─── */
.k9-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.k9-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.k9-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
