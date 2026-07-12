<script setup lang="ts">
/**
 * D4TabRevenueDetail — D4-2 主营业务收入明细（22列月度宽表）
 *
 * el-table横向滚动22列 + 固定col A + 搜索框 + 虚拟滚动(>30行 placeholder)
 * 自动计算列灰底 + 变动>30%红色 + 金额fmtAmount右对齐
 * "添加产品行"/"从序时账导入" + 合计行 + 核对行
 * 审计说明/结论 + AI(disabled) + GtIndexChip→D4-8
 *
 * Requirements: 3.1-3.10, 19.3, 21.2
 */
import { ref, computed, inject, toRef, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useD4RevenueDetail, type RevenueDetailRow } from '../../composables/useD4RevenueDetail'
import { isChangeRateExceeding } from '../../composables/useD4FormulaEngine'
import { useD4ImportExport } from '../../composables/useD4ImportExport'
import { useWorkpaperBrowseMode } from '../../composables/useWorkpaperBrowseMode'
import { virtualTextCol, virtualNumCol } from '../../composables/virtualColumnHelpers'
import type { VirtualColumn } from '@/composables/useVirtualTable'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

// ─── 金额格式化 ───────────────────────────────────────────────────────
function fmtAmount(v: number): string {
  if (v === 0) return '-'
  if (v < 0) return `(${Math.abs(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(rate: number | '' | 'N/A'): string {
  if (rate === '' || rate === 'N/A') return rate === '' ? '-' : 'N/A'
  return (rate * 100).toFixed(1) + '%'
}

// ─── Composable ───────────────────────────────────────────────────────
const {
  rows,
  filteredRows,
  subtotalRow,
  verificationRow,
  searchQuery,
  addRow,
  removeRow,
  updateCell,
  importFromLedger,
} = useD4RevenueDetail({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

// ─── 导入导出 ─────────────────────────────────────────────────────────
const { exportTemplate, exportData, importData, importing } = useD4ImportExport({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
})

function handleImportUpload(file: File): boolean {
  importData('D4-2', file)
  return false // 阻止 el-upload 自动上传
}

// ─── 虚拟滚动 / browseMode ───────────────────────────────────────────
const browseRows = filteredRows
const browseRowCount = computed(() => filteredRows.value.length)

function fmtBrowseAmt(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const virtualColumns = computed<VirtualColumn[]>(() => [
  virtualTextCol('product', '产品/服务', 140),
  virtualNumCol('periodTotal', '本期未审合计', 110, fmtBrowseAmt),
  virtualNumCol('audited', '本期审定', 110, fmtBrowseAmt),
  virtualTextCol('remark', '备注', 120),
])

const {
  browseMode,
  useVirtualScroll: useBrowseVirtualScroll,
  rowEventHandlers,
  tableWidth,
  tableHeight,
  toggleBrowseMode,
} = useWorkpaperBrowseMode({
  rows: browseRows,
  virtualColumns,
  tableWidth: 1400,
})

// ─── 样式判断 ─────────────────────────────────────────────────────────
function getRateCellClass(rate: number | '' | 'N/A'): string {
  if (isChangeRateExceeding(rate, 0.3)) return 'rate-warning'
  return ''
}

function getRowClassName({ row }: { row: RevenueDetailRow }): string {
  if (row.rowId === 'subtotal') return 'subtotal-row-bg'
  return ''
}

// ─── 审计说明/结论（使用 allResponses 存取） ─────────────────────────────
const auditNote = computed({
  get: () => props.allResponses.get('D4-2-note')?.remark || '',
  set: (val: string) => {
    const map = props.allResponses as Map<string, any>
    map.set('D4-2-note', { item_id: 'D4-2-note', conclusion: null, remark: val })
  },
})

const auditConclusion = computed({
  get: () => props.allResponses.get('D4-2-conclusion')?.remark || '',
  set: (val: string) => {
    const map = props.allResponses as Map<string, any>
    map.set('D4-2-conclusion', { item_id: 'D4-2-conclusion', conclusion: null, remark: val })
  },
})

// ─── 核对结果 ─────────────────────────────────────────────────────────
const hasDifference = computed(() => Math.abs(verificationRow.value.diff) > 0.005)

// ─── 月份标签 ─────────────────────────────────────────────────────────
const monthLabels = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']

// ─── AI辅助（真实接入 /d4/ai-generate） ──────────────────────────────
const aiAvailable = ref(false)
const aiLoadingKey = ref<string | null>(null)
async function checkAiHealth() {
  try {
    const res = await http.get('/api/ai/health', { _silent: true } as any)
    const s = res.data?.data?.status ?? res.data?.status
    aiAvailable.value = s === 'healthy' || s === 'degraded'
  } catch { aiAvailable.value = false }
}
checkAiHealth()

async function callD4Ai(section: string, existing: string): Promise<string> {
  const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, {
    section, existingContent: existing, relatedContext: {},
  }, { _silent: true } as any)
  return res.data?.data?.content ?? res.data?.content ?? ''
}

async function generateNote() {
  if (props.isReadonly || !aiAvailable.value) return
  aiLoadingKey.value = 'note'
  try {
    const ctx = rows.value.map(r =>
      `${r.product}: 本期审定=${fmtAmount(r.audited)}, 未审变动=${fmtRate(r.unadjustedChangeRate)}`
    ).join('\n')
    const text = await callD4Ai('revenue-change', ctx)
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text.length > 300 ? text.slice(0, 300) + '…' : text, 'AI 生成 · 审计说明', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' })
    auditNote.value = text
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败') }
  finally { aiLoadingKey.value = null }
}

async function generateConclusion() {
  if (props.isReadonly || !aiAvailable.value) return
  aiLoadingKey.value = 'conclusion'
  try {
    const ctx = `审计说明：${auditNote.value || '（未填写）'}\n核对：${hasDifference.value ? '与TB有差异' + fmtAmount(verificationRow.value.diff) : '与TB核对一致'}`
    const text = await callD4Ai('adj-conclusion', ctx)
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text.length > 300 ? text.slice(0, 300) + '…' : text, 'AI 生成 · 审计结论', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' })
    auditConclusion.value = text
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败') }
  finally { aiLoadingKey.value = null }
}

const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')
</script>

<template>
  <div class="d4-tab-revenue-detail">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表列示被审计单位各产品/服务的月度收入明细。</p>
        <p>2. 灰色底纹列为自动计算列（合计/审定/变动率），不可手动编辑。</p>
        <p>3. 变动率超过30%自动标红，请关注并在审计说明中解释。</p>
        <p>4. 支持从序时账（tb_ledger）按产品月度汇总自动导入。</p>
      </div>
    </details>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-input
          v-model="searchQuery"
          placeholder="搜索产品名称..."
          size="small"
          clearable
          style="width: 200px"
        />
        <el-button size="small" :disabled="isReadonly" @click="addRow">+ 添加产品行</el-button>
        <el-tooltip placement="top" :show-after="300">
          <template #content>
            从序时账(tb_ledger)按科目6001、按产品维度、按月汇总导入。<br/>
            取数条件：当前项目年度 + 科目编码6001开头 + 贷方发生额。
          </template>
          <el-button size="small" :disabled="isReadonly" @click="importFromLedger">从序时账导入</el-button>
        </el-tooltip>
      </div>
      <div class="toolbar-right">
        <el-dropdown size="small" trigger="click" :disabled="isReadonly">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="exportTemplate('D4-2')">导出模板</el-dropdown-item>
              <el-dropdown-item @click="exportData('D4-2')">导出数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload
                  :show-file-list="false"
                  accept=".xlsx,.xls"
                  :before-upload="handleImportUpload"
                  :disabled="importing"
                >
                  <span>导入数据</span>
                </el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <span class="chip-wrap"><GtIndexChip value="wp:D4-8" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <!-- 虚拟滚动 / browseMode -->
    <div v-if="useBrowseVirtualScroll" class="virtual-toolbar">
      <el-alert type="info" :closable="false" class="virtual-hint">
        行数较多（{{ browseRowCount }} 行）· {{ browseMode ? '虚拟滚动速览' : '表格编辑' }}模式 · 双击行可切换编辑
      </el-alert>
      <el-button size="small" @click="toggleBrowseMode">
        {{ browseMode ? '切换表格编辑' : '切换虚拟速览' }}
      </el-button>
    </div>
    <el-table-v2
      v-if="useBrowseVirtualScroll && browseMode"
      :columns="virtualColumns"
      :data="browseRows"
      :width="tableWidth"
      :height="tableHeight"
      :row-height="36"
      :header-height="40"
      :row-event-handlers="rowEventHandlers"
      fixed
      class="virtual-table"
    />

    <!-- 主表（22列宽表） -->
    <div v-if="!useBrowseVirtualScroll || !browseMode" class="table-wrapper">
      <el-table
        :data="[...filteredRows, subtotalRow]"
        border
        size="small"
        :row-class-name="getRowClassName"
        style="width: 100%"
        :max-height="600"
      >
        <!-- A: 项目（产品/服务） -->
        <el-table-column prop="product" label="产品/服务" width="140" fixed>
          <template #default="{ row }">
            <template v-if="row.rowId === 'subtotal'">
              <span class="font-bold">合计</span>
            </template>
            <template v-else>
              <el-input
                v-if="!isReadonly"
                :model-value="row.product"
                size="small"
                placeholder="产品名称"
                @change="(v: string) => updateCell(row.rowId, 'product', v)"
              />
              <span v-else>{{ row.product || '(未命名)' }}</span>
            </template>
          </template>
        </el-table-column>

        <!-- B~M: 1月~12月 -->
        <el-table-column
          v-for="(label, mIdx) in monthLabels"
          :key="mIdx"
          :label="label"
          width="95"
          align="right"
        >
          <template #default="{ row }">
            <template v-if="row.rowId === 'subtotal'">
              <span class="font-bold">{{ fmtAmount(row.months[mIdx]) }}</span>
            </template>
            <template v-else>
              <el-input
                v-if="!isReadonly"
                :model-value="row.months[mIdx]"
                size="small"
                type="number"
                style="text-align: right"
                @change="(v: string) => updateCell(row.rowId, `month-${mIdx}`, v)"
              />
              <span v-else>{{ fmtAmount(row.months[mIdx]) }}</span>
            </template>
          </template>
        </el-table-column>

        <!-- N: 本期未审合计（自动计算，灰底） -->
        <el-table-column label="未审合计" width="120" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="auto-calc-value">{{ fmtAmount(row.periodTotal) }}</span>
          </template>
        </el-table-column>

        <!-- O: 本期审计调整 -->
        <el-table-column label="审计调整" width="110" align="right">
          <template #default="{ row }">
            <template v-if="row.rowId === 'subtotal'">
              <span class="font-bold">{{ fmtAmount(row.auditAdjustment) }}</span>
            </template>
            <template v-else>
              <el-input
                v-if="!isReadonly"
                :model-value="row.auditAdjustment"
                size="small"
                type="number"
                @change="(v: string) => updateCell(row.rowId, 'auditAdjustment', v)"
              />
              <span v-else>{{ fmtAmount(row.auditAdjustment) }}</span>
            </template>
          </template>
        </el-table-column>

        <!-- P: 本期审定数（自动，灰底） -->
        <el-table-column label="本期审定" width="120" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="audited-cell auto-calc-value">{{ fmtAmount(row.audited) }}</span>
          </template>
        </el-table-column>

        <!-- Q: 上期未审数 -->
        <el-table-column label="上期未审" width="110" align="right">
          <template #default="{ row }">
            <template v-if="row.rowId === 'subtotal'">
              <span class="font-bold">{{ fmtAmount(row.priorUnadjusted) }}</span>
            </template>
            <template v-else>
              <el-input
                v-if="!isReadonly"
                :model-value="row.priorUnadjusted"
                size="small"
                type="number"
                @change="(v: string) => updateCell(row.rowId, 'priorUnadjusted', v)"
              />
              <span v-else>{{ fmtAmount(row.priorUnadjusted) }}</span>
            </template>
          </template>
        </el-table-column>

        <!-- R: 上期审计调整 -->
        <el-table-column label="上期调整" width="110" align="right">
          <template #default="{ row }">
            <template v-if="row.rowId === 'subtotal'">
              <span class="font-bold">{{ fmtAmount(row.priorAdjustment) }}</span>
            </template>
            <template v-else>
              <el-input
                v-if="!isReadonly"
                :model-value="row.priorAdjustment"
                size="small"
                type="number"
                @change="(v: string) => updateCell(row.rowId, 'priorAdjustment', v)"
              />
              <span v-else>{{ fmtAmount(row.priorAdjustment) }}</span>
            </template>
          </template>
        </el-table-column>

        <!-- S: 上期审定数（自动，灰底） -->
        <el-table-column label="上期审定" width="120" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="auto-calc-value">{{ fmtAmount(row.priorAudited) }}</span>
          </template>
        </el-table-column>

        <!-- T: 未审变动率（自动，灰底） -->
        <el-table-column label="未审变动" width="95" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span :class="getRateCellClass(row.unadjustedChangeRate)">
              {{ fmtRate(row.unadjustedChangeRate) }}
            </span>
          </template>
        </el-table-column>

        <!-- U: 审定变动率（自动，灰底） -->
        <el-table-column label="审定变动" width="95" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span :class="getRateCellClass(row.auditedChangeRate)">
              {{ fmtRate(row.auditedChangeRate) }}
            </span>
          </template>
        </el-table-column>

        <!-- V: 备注 -->
        <el-table-column label="备注" min-width="120">
          <template #default="{ row }">
            <template v-if="row.rowId === 'subtotal'">
              <span>-</span>
            </template>
            <template v-else>
              <el-input
                v-if="!isReadonly"
                :model-value="row.remark"
                size="small"
                placeholder="备注"
                @change="(v: string) => updateCell(row.rowId, 'remark', v)"
              />
              <span v-else>{{ row.remark || '-' }}</span>
            </template>
          </template>
        </el-table-column>

        <!-- 操作 -->
        <el-table-column label="" width="50" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.rowId !== 'subtotal' && !isReadonly"
              type="danger"
              size="small"
              link
              @click="removeRow(row.rowId)"
            >删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 核对行 -->
    <div class="tb-check-row">
      <span class="tb-label">与试算平衡表核对（科目6001）：</span>
      <el-tag v-if="hasDifference" type="danger" size="small">差异 {{ fmtAmount(verificationRow.diff) }}</el-tag>
      <el-tag v-else type="success" size="small">核对一致</el-tag>
    </div>

    <!-- 审计意见区（卡片式，与D4-1/D4-5统一） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明与结论</span>
          <div class="opinion-chips">
            <GtIndexChip value="wp:D4-1" :context-project-id="projectId" />
            <GtIndexChip value="wp:D4-8" :context-project-id="projectId" />
          </div>
        </div>
      </template>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">1. 审计说明</span>
          <div class="opinion-actions">
            <el-tooltip :content="aiTip" placement="top">
              <el-button size="small" type="primary" plain :loading="aiLoadingKey === 'note'"
                :disabled="isReadonly || !aiAvailable" @click="generateNote">🤖 AI辅助</el-button>
            </el-tooltip>
            <el-button size="small" @click="openReviewDialog?.('D4-2-note')">💬</el-button>
          </div>
        </div>
        <el-input
          v-model="auditNote"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          placeholder="请输入审计说明（如：XX公司收入主要集中在第X季度，主要原因是……，经查询同行业数据，季节变化符合行业周期）..."
          :disabled="isReadonly"
        />
      </div>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">2. 审计结论</span>
          <el-tooltip :content="aiTip" placement="top">
            <el-button size="small" type="primary" plain :loading="aiLoadingKey === 'conclusion'"
              :disabled="isReadonly || !aiAvailable" @click="generateConclusion">🤖 AI辅助</el-button>
          </el-tooltip>
        </div>
        <el-input
          v-model="auditConclusion"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          placeholder="请输入审计结论..."
          :disabled="isReadonly"
        />
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.d4-tab-revenue-detail {
  padding: 12px;
}
.d4-tab-revenue-detail :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.d4-tab-revenue-detail :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p {
  margin: 2px 0;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.chip-wrap { display: inline-flex; align-items: center; }
.virtual-hint {
  margin-bottom: 8px;
}
.table-wrapper {
  margin-bottom: 12px;
  overflow-x: auto;
}
:deep(.auto-calc-col) {
  background-color: #f5f7fa !important;
}
.auto-calc-value {
  color: #606266;
}
.rate-warning {
  color: #f56c6c;
  font-weight: 600;
}
.audited-cell {
  font-weight: 600;
}
.font-bold {
  font-weight: 600;
}
:deep(.subtotal-row-bg) {
  background-color: #fafafa !important;
  font-weight: 600;
}
.tb-check-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  margin-bottom: 16px;
  font-size: var(--wp-font-size, 13px);
}
.tb-label {
  color: #909399;
}
.audit-note-section {
  margin-bottom: 16px;
}
.virtual-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.virtual-hint {
  flex: 1;
}

.note-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.note-header h4 {
  margin: 0;
  font-size: 14px;
  color: #303133;
}
.note-actions {
  display: flex;
  gap: 6px;
}
.opinion-card {
  margin-top: 16px;
  border-radius: 8px;
}
.opinion-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.opinion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.opinion-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.opinion-chips {
  display: flex;
  gap: 6px;
}
.opinion-section {
  margin-bottom: 16px;
}
.opinion-section:last-child {
  margin-bottom: 0;
}
.opinion-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.opinion-section-label {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}
.opinion-actions {
  display: flex;
  gap: 6px;
}
</style>
