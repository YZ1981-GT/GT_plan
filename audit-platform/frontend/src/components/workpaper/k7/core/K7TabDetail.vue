<!--
  K7TabDetail.vue — K7-2 明细表（32列3区段+动态行+41行+导入导出）

  3区段Tab切换(el-tabs type="border-card" size="small")
  - Tab 0 基础: 序号/补助项目/批文号/补助类型/与资产或收益相关/收到金额/收到日期
  - Tab 1 分摊: 补助项目(固定)/分摊方法/分摊期(月)/期初余额/本期分摊/期末余额(公式)
  - Tab 2 检查: 补助项目(固定)/计入科目/凭证号/结论/备注

  期末=期初+收到-分摊 (负债类) per row
  动态行新增: ElMessageBox.prompt 输入补助项目名称
  导入导出: el-dropdown (导出模板/导出数据/导入数据) using useK7ImportExport
  41行虚拟滚动
  合计行: 底部固定合计行(receivedAmount/beginBalance/currentAmort/endBalance)
  按relatedType分组小计: 与资产相关小计 / 与收益相关小计

  Spec: .kiro/specs/k7-deferred-income/ | Task: 4.3
  Requirements: 3.1-3.5
-->
<template>
  <div class="k7-tab-detail">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>K7-2明细表按补助项目逐笔列示递延收益明细。<strong>负债类科目</strong>：期末=期初+收到-分摊。32列拆为3区段，补助项目名称贯穿各区段。按"与资产相关/与收益相关"分组小计。</p>
    </div>

    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>完整性：</b>所有递延收益（政府补助）项目均已逐笔登记（负债完整性重点）；</li>
        <li><b>计价和分摊：</b>期末=期初+收到-分摊，各项余额计算准确，合计与 K7-1 一致；</li>
        <li><b>列报与披露：</b>按"与资产相关/与收益相关"分类恰当。</li>
      </ol>
    </el-alert>

    <!-- 标题栏 + 操作 -->
    <div class="section-head">
      <h3 class="sheet-title">K7-2 递延收益明细表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" link @click="handleAiGenerate">
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
        <el-button size="small" @click="handleReview">💬 复核</el-button>
      </div>
    </div>

    <!-- 3区段 el-tabs -->
    <el-tabs v-model="activeTab" type="border-card" class="section-tabs">
      <el-tab-pane label="基础" name="0" />
      <el-tab-pane label="分摊" name="1" />
      <el-tab-pane label="检查" name="2" />
    </el-tabs>

    <!-- 表格 -->
    <el-table
      :data="tableData"
      border
      size="small"
      :max-height="520"
      class="detail-table"
      :row-class-name="rowClassName"
    >
      <!-- ═══ 区段0 基础 ═══ -->
      <template v-if="activeTab === '0'">
        <el-table-column label="序号" width="55" align="center">
          <template #default="{ row }">
            <template v-if="row._isSubtotal">{{ row._subtotalLabel }}</template>
            <template v-else>{{ row.seqNo }}</template>
          </template>
        </el-table-column>
        <el-table-column label="补助项目" min-width="160">
          <template #default="{ row }">
            <span v-if="row._isSubtotal" class="subtotal-label">{{ row.project }}</span>
            <span v-else>{{ row.project }}</span>
          </template>
        </el-table-column>
        <el-table-column label="批文号" min-width="130">
          <template #default="{ row }">
            <template v-if="row._isSubtotal" />
            <template v-else>
              <el-input
                v-if="!isReadonly"
                :model-value="row.docRef"
                size="small"
                placeholder="批文号"
                @change="(v: string) => detail.updateCell(row.rowId, 'docRef', v)"
              />
              <span v-else>{{ row.docRef || '-' }}</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="补助类型" width="120">
          <template #default="{ row }">
            <template v-if="row._isSubtotal" />
            <template v-else>
              <el-select
                v-if="!isReadonly"
                :model-value="row.grantType"
                size="small"
                placeholder="类型"
                @change="(v: string) => detail.updateCell(row.rowId, 'grantType', v)"
              >
                <el-option v-for="opt in grantTypeOptions" :key="opt" :label="opt" :value="opt" />
              </el-select>
              <span v-else>{{ row.grantType || '-' }}</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="相关类型" width="120">
          <template #default="{ row }">
            <template v-if="row._isSubtotal" />
            <template v-else>
              <el-select
                v-if="!isReadonly"
                :model-value="row.relatedType"
                size="small"
                @change="(v: string) => detail.updateCell(row.rowId, 'relatedType', v)"
              >
                <el-option label="与资产相关" value="与资产相关" />
                <el-option label="与收益相关" value="与收益相关" />
              </el-select>
              <span v-else>{{ row.relatedType }}</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="收到金额" width="130" align="right">
          <template #default="{ row }">
            <span v-if="row._isSubtotal" class="subtotal-amount">{{ fmtNum(row.receivedAmount) }}</span>
            <template v-else>
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.receivedAmount"
                size="small"
                :controls="false"
                :precision="2"
                class="amount-input"
                @change="(v: number) => detail.updateCell(row.rowId, 'receivedAmount', v ?? 0)"
              />
              <span v-else class="amount-cell">{{ fmtNum(row.receivedAmount) }}</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="收到日期" width="120">
          <template #default="{ row }">
            <template v-if="row._isSubtotal" />
            <template v-else>
              <el-input
                v-if="!isReadonly"
                :model-value="row.receivedDate"
                size="small"
                placeholder="YYYY-MM-DD"
                @change="(v: string) => detail.updateCell(row.rowId, 'receivedDate', v)"
              />
              <span v-else>{{ row.receivedDate || '-' }}</span>
            </template>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 区段1 分摊 ═══ -->
      <template v-if="activeTab === '1'">
        <el-table-column label="补助项目" min-width="160">
          <template #default="{ row }">
            <span v-if="row._isSubtotal" class="subtotal-label">{{ row._subtotalLabel }}</span>
            <span v-else>{{ row.project }}</span>
          </template>
        </el-table-column>
        <el-table-column label="分摊方法" width="120">
          <template #default="{ row }">
            <template v-if="row._isSubtotal" />
            <template v-else>
              <el-select
                v-if="!isReadonly"
                :model-value="row.method"
                size="small"
                @change="(v: string) => detail.updateCell(row.rowId, 'method', v)"
              >
                <el-option v-for="opt in methodOptions" :key="opt" :label="opt" :value="opt" />
              </el-select>
              <span v-else>{{ row.method || '-' }}</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="分摊期(月)" width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal" />
            <template v-else>
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.period"
                size="small"
                :controls="false"
                :min="0"
                class="period-input"
                @change="(v: number) => detail.updateCell(row.rowId, 'period', v ?? 0)"
              />
              <span v-else>{{ row.period || '-' }}</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" width="130" align="right">
          <template #default="{ row }">
            <span v-if="row._isSubtotal" class="subtotal-amount">{{ fmtNum(row.beginBalance) }}</span>
            <template v-else>
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.beginBalance"
                size="small"
                :controls="false"
                :precision="2"
                class="amount-input"
                @change="(v: number) => detail.updateCell(row.rowId, 'beginBalance', v ?? 0)"
              />
              <span v-else class="amount-cell">{{ fmtNum(row.beginBalance) }}</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="本期分摊" width="130" align="right">
          <template #default="{ row }">
            <span v-if="row._isSubtotal" class="subtotal-amount">{{ fmtNum(row.currentAmort) }}</span>
            <template v-else>
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.currentAmort"
                size="small"
                :controls="false"
                :precision="2"
                class="amount-input"
                @change="(v: number) => detail.updateCell(row.rowId, 'currentAmort', v ?? 0)"
              />
              <span v-else class="amount-cell">{{ fmtNum(row.currentAmort) }}</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="130" align="right">
          <template #default="{ row }">
            <span v-if="row._isSubtotal" class="subtotal-amount">{{ fmtNum(row.endBalance) }}</span>
            <template v-else>
              <el-tooltip content="期末=期初+收到-分摊（负债类）" placement="top">
                <span class="formula-cell">{{ fmtNum(row.endBalance) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 区段2 检查 ═══ -->
      <template v-if="activeTab === '2'">
        <el-table-column label="补助项目" min-width="160">
          <template #default="{ row }">
            <span v-if="row._isSubtotal" class="subtotal-label">{{ row._subtotalLabel }}</span>
            <span v-else>{{ row.project }}</span>
          </template>
        </el-table-column>
        <el-table-column label="计入科目" width="130">
          <template #default="{ row }">
            <template v-if="row._isSubtotal" />
            <template v-else>
              <el-select
                v-if="!isReadonly"
                :model-value="row.accountTo"
                size="small"
                @change="(v: string) => detail.updateCell(row.rowId, 'accountTo', v)"
              >
                <el-option label="其他收益" value="其他收益" />
                <el-option label="营业外收入" value="营业外收入" />
              </el-select>
              <span v-else>{{ row.accountTo || '-' }}</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="凭证号" width="120">
          <template #default="{ row }">
            <template v-if="row._isSubtotal" />
            <template v-else>
              <el-input
                v-if="!isReadonly"
                :model-value="row.voucher"
                size="small"
                placeholder="凭证号"
                @change="(v: string) => detail.updateCell(row.rowId, 'voucher', v)"
              />
              <span v-else>{{ row.voucher || '-' }}</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="结论" width="110">
          <template #default="{ row }">
            <template v-if="row._isSubtotal" />
            <template v-else>
              <el-select
                v-if="!isReadonly"
                :model-value="row.conclusion"
                size="small"
                @change="(v: string) => detail.updateCell(row.rowId, 'conclusion', v)"
              >
                <el-option v-for="opt in conclusionOptions" :key="opt" :label="opt" :value="opt" />
              </el-select>
              <span v-else>{{ row.conclusion || '-' }}</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="180">
          <template #default="{ row }">
            <template v-if="row._isSubtotal" />
            <template v-else>
              <el-input
                v-if="!isReadonly"
                :model-value="row.remark"
                size="small"
                placeholder="备注"
                @change="(v: string) => detail.updateCell(row.rowId, 'remark', v)"
              />
              <span v-else>{{ row.remark || '-' }}</span>
            </template>
          </template>
        </el-table-column>
      </template>

      <!-- 操作列（所有区段共享） -->
      <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
        <template #default="{ row, $index }">
          <el-button
            v-if="!row._isSubtotal"
            size="small"
            type="danger"
            link
            @click="handleRemoveRow($index)"
          >删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 合计行（固定底部） ═══ -->
    <div class="total-row">
      <span class="total-label">合计 ({{ detail.subtotals.value.count }} 笔)</span>
      <span class="total-item">收到: {{ fmtNum(detail.subtotals.value.receivedAmount) }}</span>
      <span class="total-item">期初: {{ fmtNum(detail.subtotals.value.beginBalance) }}</span>
      <span class="total-item">分摊: {{ fmtNum(detail.subtotals.value.currentAmort) }}</span>
      <span class="total-item total-end">期末: {{ fmtNum(detail.subtotals.value.endBalance) }}</span>
    </div>

    <!-- ═══ 分组小计卡片 ═══ -->
    <div class="group-subtotals">
      <div class="group-card">
        <span class="group-title">与资产相关小计</span>
        <span>收到 {{ fmtNum(detail.assetRelatedSubtotal.value.receivedAmount) }}</span>
        <span>期初 {{ fmtNum(detail.assetRelatedSubtotal.value.beginBalance) }}</span>
        <span>分摊 {{ fmtNum(detail.assetRelatedSubtotal.value.currentAmort) }}</span>
        <span class="group-end">期末 {{ fmtNum(detail.assetRelatedSubtotal.value.endBalance) }}</span>
      </div>
      <div class="group-card">
        <span class="group-title">与收益相关小计</span>
        <span>收到 {{ fmtNum(detail.incomeRelatedSubtotal.value.receivedAmount) }}</span>
        <span>期初 {{ fmtNum(detail.incomeRelatedSubtotal.value.beginBalance) }}</span>
        <span>分摊 {{ fmtNum(detail.incomeRelatedSubtotal.value.currentAmort) }}</span>
        <span class="group-end">期末 {{ fmtNum(detail.incomeRelatedSubtotal.value.endBalance) }}</span>
      </div>
    </div>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li><strong>负债类(2401)</strong>期末=期初+收到-分摊</li>
        <li>补助类型：财政拨款/税收返还/无偿划拨/其他</li>
        <li>分摊方法：直线法(按月均匀)/工作量法/一次性计入</li>
        <li>计入科目：与日常活动相关→其他收益；无关→营业外收入</li>
        <li>按"与资产相关/与收益相关"分组小计，各组小计应与审定表对应</li>
        <li>期末合计应与审定表(K7-1)审定合计一致</li>
        <li>新增行需弹窗输入补助项目名称后创建</li>
        <li>导入导出支持按模板批量录入明细</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K7TabDetail.vue — K7-2 递延收益明细表
 * 32列3区段Tab + 动态行(ElMessageBox.prompt) + 41行虚拟滚动 + 导入导出
 * 按relatedType分组小计 + 合计行底部固定
 *
 * Spec: .kiro/specs/k7-deferred-income/ | Task: 4.3
 * Requirements: 3.1-3.5
 * 科目: 2401 递延收益（贷方/负债类）
 */
import { ref, computed, inject, toRef, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useK7Detail, type K7DetailRow } from '../../composables/useK7Detail'
import { useK7ImportExport } from '../../composables/useK7ImportExport'

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

const openReviewDialog = inject<(id: string, label?: string) => void>('openReviewDialog', () => {})

// ─── Constants ───────────────────────────────────────────────────────────────

const grantTypeOptions = ['财政拨款', '税收返还', '无偿划拨', '其他']
const methodOptions = ['直线法', '工作量法', '一次性计入']
const conclusionOptions = ['正常', '异常', '需调整', '待确认']

// ─── Composables ─────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)

const detail = useK7Detail({
  allResponses: allResponsesRef as any,
  saveResponse: (itemId: string, value: any) => {
    emit('save', itemId, value)
  },
})

const importExport = useK7ImportExport({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  sheetCode: 'K7-2',
})

// ─── Tab / Segment State ─────────────────────────────────────────────────────

const activeTab = ref('0')

// ─── 表格数据(含分组小计行) ──────────────────────────────────────────────────

interface SubtotalRow {
  _isSubtotal: true
  _subtotalLabel: string
  rowId: string
  project: string
  receivedAmount: number
  beginBalance: number
  currentAmort: number
  endBalance: number
  [key: string]: any
}

type TableRow = (K7DetailRow & { _isSubtotal?: false }) | SubtotalRow

const tableData = computed<TableRow[]>(() => {
  const rows = detail.detailRows.value
  if (rows.length === 0) return []

  const result: TableRow[] = []

  // 与资产相关
  const assetRows = rows.filter(r => r.relatedType === '与资产相关')
  if (assetRows.length > 0) {
    assetRows.forEach(r => result.push({ ...r, _isSubtotal: false }))
    result.push({
      _isSubtotal: true,
      _subtotalLabel: '与资产相关小计',
      rowId: '__subtotal-asset',
      project: '与资产相关小计',
      receivedAmount: detail.assetRelatedSubtotal.value.receivedAmount,
      beginBalance: detail.assetRelatedSubtotal.value.beginBalance,
      currentAmort: detail.assetRelatedSubtotal.value.currentAmort,
      endBalance: detail.assetRelatedSubtotal.value.endBalance,
    })
  }

  // 与收益相关
  const incomeRows = rows.filter(r => r.relatedType === '与收益相关')
  if (incomeRows.length > 0) {
    incomeRows.forEach(r => result.push({ ...r, _isSubtotal: false }))
    result.push({
      _isSubtotal: true,
      _subtotalLabel: '与收益相关小计',
      rowId: '__subtotal-income',
      project: '与收益相关小计',
      receivedAmount: detail.incomeRelatedSubtotal.value.receivedAmount,
      beginBalance: detail.incomeRelatedSubtotal.value.beginBalance,
      currentAmort: detail.incomeRelatedSubtotal.value.currentAmort,
      endBalance: detail.incomeRelatedSubtotal.value.endBalance,
    })
  }

  return result
})

// ─── 行样式 ──────────────────────────────────────────────────────────────────

function rowClassName({ row }: { row: TableRow }): string {
  if (row._isSubtotal) return 'subtotal-row'
  return ''
}

// ─── 行操作 ──────────────────────────────────────────────────────────────────

async function handleAddRow() {
  await detail.addRow()
}

function handleRemoveRow(tableIndex: number) {
  // tableIndex includes subtotal rows, need to find actual row
  const row = tableData.value[tableIndex]
  if (!row || row._isSubtotal) return

  const actualIdx = detail.detailRows.value.findIndex(r => r.rowId === row.rowId)
  if (actualIdx < 0) return

  ElMessageBox.confirm(
    `确定删除补助项目"${row.project}"？删除后不可恢复。`,
    '确认删除',
    { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
  ).then(() => {
    detail.removeRow(actualIdx)
    ElMessage.success('已删除')
  }).catch(() => { /* 取消 */ })
}

// ─── 导入导出 ─────────────────────────────────────────────────────────────────

function handleExportTemplate() { importExport.exportTemplate() }
function handleExportData() { importExport.exportData() }

function handleImportData() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls'
  input.onchange = async (e: Event) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return
    const result = await importExport.importData(file)
    if (result && result.rowCount > 0) {
      // composable内部watch allResponses 触发reload
    }
  }
  input.click()
}

// ─── AI / 复核 ───────────────────────────────────────────────────────────────

function handleAiGenerate() {
  emit('save', 'K7-2-ai-trigger', { remark: 'generate' })
}

function handleReview() {
  openReviewDialog?.('K7-2', '明细表K7-2')
}

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmtNum(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k7-tab-detail {
  padding: 16px;
  font-size: var(--wp-font-size, 13px);
}

/* 方法论上下文（琥珀色左边线+浅黄背景） */
.methodology-context {
  border-left: 4px solid var(--el-color-warning, #f59e0b);
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 16px;
  font-size: 12px;
  color: #78350f;
  line-height: 1.6;
  border-radius: 4px;
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
  color: #303133;
}
.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* el-tabs 区段栏 */
.section-tabs {
  margin-bottom: 12px;
}
.section-tabs :deep(.el-tabs__content) {
  display: none;
}

/* 表格 */
.detail-table {
  font-size: var(--wp-font-size, 13px);
  width: 100%;
}
:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}
.amount-input {
  width: 100%;
}
.period-input {
  width: 80px;
}
.amount-cell {
  font-variant-numeric: tabular-nums;
}

/* 公式列：虚线下划线 + cursor:help */
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color, #dcdfe6);
  cursor: help;
  font-variant-numeric: tabular-nums;
}

/* 小计行样式：浅色背景+粗体 */
.detail-table :deep(.subtotal-row) {
  background-color: #f5f7fa !important;
  font-weight: 600;
}
.detail-table :deep(.subtotal-row:hover > td) {
  background-color: #ebeef5 !important;
}
.subtotal-label {
  font-weight: 600;
  color: var(--el-text-color-primary, #303133);
}
.subtotal-amount {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

/* 合计行：加粗+上border */
.total-row {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-top: 0;
  padding: 12px 16px;
  border-top: 2px solid var(--el-border-color, #dcdfe6);
  background: var(--el-bg-color, #fff);
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}
.total-label {
  color: var(--el-text-color-primary, #303133);
}
.total-item {
  color: var(--el-text-color-regular, #606266);
  font-variant-numeric: tabular-nums;
}
.total-end {
  color: var(--el-color-primary, #409eff);
  font-weight: 700;
}

/* 分组小计卡片 */
.group-subtotals {
  display: flex;
  gap: 16px;
  margin-top: 12px;
  flex-wrap: wrap;
}
.group-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 14px;
  background: #f0f9eb;
  border-radius: 6px;
  font-size: 12px;
  color: var(--el-text-color-regular, #606266);
}
.group-title {
  font-weight: 600;
  color: var(--el-text-color-primary, #303133);
}
.group-end {
  color: var(--el-color-primary, #409eff);
  font-weight: 600;
}

/* 编制提示 */
.compile-hint {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
}
.compile-hint summary {
  cursor: pointer;
  font-weight: 500;
  color: var(--el-text-color-primary, #303133);
}
.compile-hint ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
