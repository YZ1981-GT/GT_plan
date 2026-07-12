<template>
  <div class="g6-tab-inventory-roll-forward">
    <!-- ═══ 2区段Tab切换（行同步） ═══ -->
    <div class="tab-bar">
      <button
        class="tab-btn"
        :class="{ active: activeTab === 'rollForward' }"
        @click="switchTab('rollForward')"
      >
        Tab1: 倒轧计算(10列)
      </button>
      <button
        class="tab-btn"
        :class="{ active: activeTab === 'changeDetail' }"
        @click="switchTab('changeDetail')"
      >
        Tab2: 增减明细(8列)
      </button>
    </div>

    <!-- ═══ Tab1: 倒轧计算(10列) ═══ -->
    <el-card v-if="activeTab === 'rollForward'" shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">盘点倒轧表 — 倒轧计算</span>
          <div class="section-actions">
            <el-tag v-if="reconciliation.varianceCount.value > 0" type="danger" size="small">
              {{ reconciliation.varianceCount.value }}项差异
            </el-tag>
            <el-button size="small" :disabled="props.isReadonly" @click="handleAi">✨ AI辅助</el-button>
            <el-button size="small" @click="openReview('G6-10-roll-forward')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="reconciliation.items.value"
        border
        size="small"
        class="recon-table"
        highlight-current-row
        :current-row-key="currentRowId"
        row-key="id"
        @current-change="handleTab1RowChange"
      >
        <!-- 证券名称 -->
        <el-table-column label="证券名称" min-width="150">
          <template #default="{ row, $index }">
            <div class="name-cell">
              <span>{{ row.securitiesName }}</span>
              <el-button
                v-if="!props.isReadonly"
                size="small" type="danger" link
                @click.stop="reconciliation.removeItem(row.id)"
              >🗑️</el-button>
            </div>
          </template>
        </el-table-column>
        <!-- 盘点日数量 -->
        <el-table-column label="盘点日数量" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!props.isReadonly"
              v-model="row.countDateQuantity"
              size="small" :controls="false" :precision="0"
              style="width: 85px"
            />
            <span v-else>{{ row.countDateQuantity }}</span>
          </template>
        </el-table-column>
        <!-- 增减 -->
        <el-table-column label="增减" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!props.isReadonly"
              v-model="row.changeQuantity"
              size="small" :controls="false"
              style="width: 85px"
            />
            <span v-else>{{ row.changeQuantity }}</span>
          </template>
        </el-table-column>
        <!-- 基准日数量（公式列） -->
        <el-table-column label="基准日数量" width="100" align="right">
          <template #default="{ row }">
            <span
              class="formula-cell"
              title="基准日数量 = 盘点日数量 + 增减"
            >{{ row.reportDateQuantity }}</span>
          </template>
        </el-table-column>
        <!-- 账面数量 -->
        <el-table-column label="账面数量" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!props.isReadonly"
              v-model="row.bookQuantity"
              size="small" :controls="false" :precision="0"
              style="width: 85px"
            />
            <span v-else>{{ row.bookQuantity }}</span>
          </template>
        </el-table-column>
        <!-- 差异（公式列，红色高亮） -->
        <el-table-column label="差异" width="100" align="right">
          <template #default="{ row }">
            <span
              class="formula-cell"
              :style="reconciliation.getVarianceCellStyle(row)"
              title="差异 = 基准日数量 - 账面数量"
            >{{ row.variance }}</span>
          </template>
        </el-table-column>
        <!-- 差异原因 -->
        <el-table-column label="差异原因" min-width="150">
          <template #default="{ row }">
            <el-input
              v-if="!props.isReadonly"
              v-model="row.varianceReason"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              size="small"
              placeholder="差异原因..."
              :class="{ 'variance-reason-required': reconciliation.isVarianceReasonMissing(row) }"
            />
            <span v-else>{{ row.varianceReason || '-' }}</span>
          </template>
        </el-table-column>
        <!-- 差异结论 -->
        <el-table-column label="差异结论" width="120">
          <template #default="{ row }">
            <el-input
              v-if="!props.isReadonly"
              v-model="row.varianceConclusion"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              size="small"
              placeholder="结论..."
            />
            <span v-else>{{ row.varianceConclusion || '-' }}</span>
          </template>
        </el-table-column>
        <!-- 索引 -->
        <el-table-column label="索引" width="80">
          <template #default="{ row }">
            <el-input
              v-if="!props.isReadonly"
              v-model="row.indexRef"
              size="small"
              placeholder="索引"
            />
            <span v-else>{{ row.indexRef || '-' }}</span>
          </template>
        </el-table-column>
        <!-- 备注 -->
        <el-table-column label="备注" min-width="150">
          <template #default="{ row }">
            <el-input
              v-if="!props.isReadonly"
              v-model="row.remark"
              size="small"
              placeholder="备注..."
            />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 差异必填校验提示 -->
      <el-alert
        v-if="reconciliation.varianceValidationErrors.value.length > 0"
        type="warning"
        :closable="false"
        class="variance-alert"
      >
        <template #title>
          差异原因必填提示：以下项目存在差异但未填写原因
        </template>
        <ul class="variance-error-list">
          <li v-for="item in reconciliation.varianceValidationErrors.value" :key="item.row.id">
            {{ item.row.securitiesName }}（差异: {{ item.row.variance }}）
          </li>
        </ul>
      </el-alert>
    </el-card>

    <!-- ═══ Tab2: 增减明细(8列) ═══ -->
    <el-card v-if="activeTab === 'changeDetail'" shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">盘点倒轧表 — 增减明细</span>
          <div class="section-actions">
            <el-tag size="small" type="info">
              {{ reconciliation.changeDetailCount.value }}条明细
            </el-tag>
            <el-button size="small" :disabled="props.isReadonly" @click="handleAi">✨ AI辅助</el-button>
            <el-button size="small" @click="openReview('G6-10-change-detail')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="reconciliation.changeDetails.value"
        border
        size="small"
        class="recon-table"
        highlight-current-row
        row-key="id"
      >
        <!-- 证券名称 -->
        <el-table-column label="证券名称" min-width="150">
          <template #default="{ row }">
            <div class="name-cell">
              <span>{{ row.securitiesName }}</span>
              <el-button
                v-if="!props.isReadonly"
                size="small" type="danger" link
                @click.stop="reconciliation.removeChangeDetail(row.id)"
              >🗑️</el-button>
            </div>
          </template>
        </el-table-column>
        <!-- 日期 -->
        <el-table-column label="日期" width="120">
          <template #default="{ row }">
            <el-date-picker
              v-if="!props.isReadonly"
              v-model="row.date"
              type="date"
              size="small"
              value-format="YYYY-MM-DD"
              placeholder="选择日期"
              style="width: 110px"
            />
            <span v-else>{{ row.date || '-' }}</span>
          </template>
        </el-table-column>
        <!-- 交易类型 -->
        <el-table-column label="交易类型" width="100">
          <template #default="{ row }">
            <el-select
              v-if="!props.isReadonly"
              v-model="row.transactionType"
              size="small"
              placeholder="选择"
              style="width: 90px"
            >
              <el-option
                v-for="opt in TRANSACTION_TYPE_OPTIONS"
                :key="opt.value"
                :value="opt.value"
                :label="opt.label"
              />
            </el-select>
            <span v-else>{{ getTransactionTypeLabel(row.transactionType) }}</span>
          </template>
        </el-table-column>
        <!-- 数量 -->
        <el-table-column label="数量" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!props.isReadonly"
              v-model="row.quantity"
              size="small" :controls="false" :precision="0"
              style="width: 85px"
            />
            <span v-else>{{ row.quantity }}</span>
          </template>
        </el-table-column>
        <!-- 金额 -->
        <el-table-column label="金额" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!props.isReadonly"
              v-model="row.amount"
              size="small" :controls="false" :precision="2"
              style="width: 105px"
            />
            <span v-else>{{ fmtNum(row.amount) }}</span>
          </template>
        </el-table-column>
        <!-- 凭证号 -->
        <el-table-column label="凭证号" width="100">
          <template #default="{ row }">
            <el-input
              v-if="!props.isReadonly"
              v-model="row.voucherNo"
              size="small"
              placeholder="凭证号"
            />
            <span v-else>{{ row.voucherNo || '-' }}</span>
          </template>
        </el-table-column>
        <!-- 经办人 -->
        <el-table-column label="经办人" width="100">
          <template #default="{ row }">
            <el-input
              v-if="!props.isReadonly"
              v-model="row.handler"
              size="small"
              placeholder="经办人"
            />
            <span v-else>{{ row.handler || '-' }}</span>
          </template>
        </el-table-column>
        <!-- 备注 -->
        <el-table-column label="备注" min-width="150">
          <template #default="{ row }">
            <el-input
              v-if="!props.isReadonly"
              v-model="row.remark"
              size="small"
              placeholder="备注..."
            />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 底部操作区 ═══ -->
    <div class="bottom-actions">
      <el-button
        v-if="!props.isReadonly"
        type="primary" size="small"
        @click="activeTab === 'rollForward' ? reconciliation.addItem() : reconciliation.addChangeDetail()"
      >
        + 新增行
      </el-button>
      <el-dropdown v-if="!props.isReadonly" size="small" class="import-export-dropdown">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
            <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
            <el-dropdown-item @click="handleImportData">导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <!-- ═══ 审计结论 ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">审计结论</span>
          <div class="section-actions">
            <el-button size="small" :disabled="props.isReadonly" @click="handleAi">✨ AI辅助</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="reconciliation.auditConclusion.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 10 }"
        :disabled="props.isReadonly"
        placeholder="对盘点倒轧结果的审计结论..."
        @input="handleSave"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="guide-details">
      <summary>📋 编制提示</summary>
      <div class="guide-content">
        <p>1. 本表用于将盘点日实际持有数量倒轧至资产负债表日（基准日），以验证期末证券存在性</p>
        <p>2. 基准日数量 = 盘点日数量 ± 盘点日至基准日之间的增减变动</p>
        <p>3. 增减明细应逐笔记录盘点日至基准日的买入、卖出、到期、转让等交易</p>
        <p>4. 差异（基准日数量 - 账面数量）不为零时，必须说明差异原因并形成差异结论</p>
        <p>5. 需将增减明细的数量合计核对至Tab1的增减列，确保数据一致</p>
        <p>6. 凭证号应与增减明细对应的会计凭证相匹配，确保交易真实发生</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G6TabInventoryRollForward.vue — G6-10 盘点倒轧表（2区段Tab + 行同步）
 *
 * Spec: .kiro/specs/g6-other-bond-investment-sppi/ Task 10.4
 * Requirements: 6.2, 6.3, 6.4
 *
 * 功能：
 * - Tab1倒轧计算(10列): 证券名称|盘点日数量|增减|基准日数量(公式)|账面数量|差异(公式,红色)|差异原因|差异结论|索引|备注
 * - Tab2增减明细(8列): 证券名称|日期|交易类型(买入/卖出/到期/转让)|数量|金额|凭证号|经办人|备注
 * - 差异红色高亮 + 差异原因必填
 * - 2区段Tab行同步（selectedRowIndex）
 * - 动态行增删 + 导入导出 + AI辅助 + 审计结论 + 编制提示
 *
 * Props 对齐父级 GtG6OtherBondSppi 传入的 html-data / is-readonly（自加载走 useG6SppiFormData）
 */
import { computed, inject, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  useG6SppiReconciliation,
  TRANSACTION_TYPE_OPTIONS,
} from '../../composables/useG6SppiReconciliation'
import { useG6SppiFormData } from '../../composables/useG6SppiFormData'
import type { ReconciliationItem, ReconciliationData } from '../../composables/useG6SppiReconciliation'

const props = defineProps<{
  htmlData: Record<string, any> | null
  isReadonly: boolean
  wpId: string
  projectId: string
}>()

// ─── 复核对话 inject ───
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

function openReview(sectionId: string): void {
  openReviewDialog(sectionId)
}

// ─── 数据层 ───
const formData = useG6SppiFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const reconciliation = useG6SppiReconciliation()

// ─── Tab 状态 ───
const activeTab = computed(() => reconciliation.activeTab.value)

function switchTab(tab: 'rollForward' | 'changeDetail'): void {
  reconciliation.switchTab(tab)
}

// ─── 行同步 ───
const currentRowId = computed(() => {
  const rows = reconciliation.items.value
  if (rows.length === 0) return ''
  const idx = reconciliation.selectedRowIndex.value
  return rows[idx]?.id || rows[0]?.id || ''
})

function handleTab1RowChange(row: ReconciliationItem | null): void {
  if (!row) return
  const idx = reconciliation.items.value.findIndex(r => r.id === row.id)
  if (idx >= 0) reconciliation.selectRow(idx)
}

// ─── 数据加载 ───
onMounted(async () => {
  await formData.loadAll()
  initFromData()
})

watch(() => props.htmlData, (newData) => {
  if (newData) initFromData()
})

function initFromData(): void {
  const content = formData.parseContent()
  if (content.reconciliation) {
    reconciliation.loadData(content.reconciliation as ReconciliationData)
  }
}

// ─── 保存 ───
function handleSave(): void {
  formData.debouncedSave('G6-10-reconciliation-data', {
    conclusion: JSON.stringify(reconciliation.toJSON()),
  })
}

// watch items/changeDetails 深度变化保存
watch([() => reconciliation.items.value, () => reconciliation.changeDetails.value], () => {
  handleSave()
}, { deep: true })

// ─── AI辅助 ───
function handleAi(): void {
  ElMessage.info('AI辅助(盘点倒轧结论)功能将在AI模块完成后启用')
}

// ─── 导入导出（占位） ───
function handleExportTemplate(): void {
  ElMessage.info('导出模板功能将在导入导出模块完成后启用')
}
function handleExportData(): void {
  ElMessage.info('导出数据功能将在导入导出模块完成后启用')
}
function handleImportData(): void {
  ElMessage.info('导入数据功能将在导入导出模块完成后启用')
}

// ─── 交易类型标签 ───
function getTransactionTypeLabel(value: string): string {
  const opt = TRANSACTION_TYPE_OPTIONS.find(o => o.value === value)
  return opt?.label || value || '-'
}

// ─── 数字格式化 ───
function fmtNum(v: number | undefined, decimals = 2): string {
  if (v === undefined || v === null) return '-'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

// ─── 暴露接口 ───
defineExpose({
  toJSON: () => reconciliation.toJSON(),
})
</script>

<style scoped>
.g6-tab-inventory-roll-forward {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── Tab切换按钮 ─── */
.tab-bar {
  display: flex;
  gap: 0;
  margin-bottom: 12px;
  border-bottom: 2px solid #e4e7ed;
}

.tab-btn {
  padding: 8px 20px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  border: none;
  background: transparent;
  color: #606266;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  transition: color 0.2s, border-color 0.2s;
}

.tab-btn:hover {
  color: #409eff;
}

.tab-btn.active {
  color: #409eff;
  border-bottom-color: #409eff;
  font-weight: 600;
}

/* ─── Section卡片 ─── */
.section-card {
  margin-bottom: 16px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.section-title {
  font-weight: 600;
  font-size: 14px;
}

.section-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* ─── 表格 ─── */
.recon-table {
  font-size: var(--wp-font-size, 13px);
}

/* ─── 名称单元格 ─── */
.name-cell {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

/* ─── 公式列样式（虚线下划线+cursor:help+tooltip来源） ─── */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding: 2px 4px;
  display: inline-block;
}

/* ─── 差异原因必填红色边框 ─── */
.variance-reason-required :deep(.el-textarea__inner) {
  box-shadow: 0 0 0 1px #f56c6c inset;
}

/* ─── 差异校验提示 ─── */
.variance-alert {
  margin-top: 12px;
}

.variance-error-list {
  margin: 4px 0 0 16px;
  padding: 0;
  font-size: 12px;
}

/* ─── 底部操作 ─── */
.bottom-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  margin: 12px 0;
}

.import-export-dropdown {
  margin-left: 8px;
}

/* ─── 审计结论 ─── */
.conclusion-card {
  margin-bottom: 16px;
}

/* ─── 编制提示 ─── */
.guide-details {
  margin-top: 16px;
}

.guide-details summary {
  cursor: pointer;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  font-weight: 600;
}

.guide-content {
  padding: 8px 12px;
  background: #fffbeb;
  border-left: 3px solid #f59e0b;
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.8;
}

.guide-content p {
  margin: 0;
}
</style>
