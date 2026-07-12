<template>
  <div class="g4-tab-inventory-reconciliation">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计目标：通过盘点日实存倒轧至资产负债表日，确认报表日证券结存数量与账面结存一致，差异已查明并说明。"
      style="margin-bottom: 12px"
    />
    <!-- Section标题 + 复核按钮 -->
    <div class="section-header">
      <h3 class="section-title">G4-8 盘点倒轧结存表</h3>
      <div class="section-actions">
        <el-button size="small" type="primary" plain @click="emitAi('reconciliation-conclusion')">
          <el-icon><MagicStick /></el-icon> AI
        </el-button>
        <el-button size="small" :icon="ChatDotRound" @click="handleReview('G4-8盘点倒轧结存表')">复核</el-button>
      </div>
    </div>

    <!-- 3区段Tab (el-segmented) -->
    <el-segmented
      v-model="activeTab"
      :options="tabOptions"
      size="default"
      class="reconciliation-tabs"
      @change="(val: any) => reconciliationLogic.switchTab(val as any)"
    />

    <!-- 动态列表格 -->
    <el-table
      :data="items"
      border
      stripe
      size="small"
      highlight-current-row
      :row-class-name="getRowClassName"
      class="reconciliation-table"
      @current-change="handleRowClick"
    >
      <!-- ═══ 盘点日实存(6列) ═══ -->
      <template v-if="activeTab === 'countDate'">
        <el-table-column label="证券名称" min-width="140">
          <template #default="{ row }">
            <el-input v-model="row.securitiesName" size="small" :disabled="isReadonly" @change="reconciliationLogic.updateItem(row.id, { securitiesName: row.securitiesName })" />
          </template>
        </el-table-column>
        <el-table-column label="数量" min-width="90">
          <template #default="{ row }">
            <el-input-number v-model="row.countQuantity" size="small" :controls="false" :disabled="isReadonly" @change="reconciliationLogic.updateItem(row.id, { countQuantity: row.countQuantity })" />
          </template>
        </el-table-column>
        <el-table-column label="面值" min-width="110">
          <template #default="{ row }">
            <el-input-number v-model="row.countFaceValue" size="small" :controls="false" :disabled="isReadonly" @change="reconciliationLogic.updateItem(row.id, { countFaceValue: row.countFaceValue })" />
          </template>
        </el-table-column>
        <el-table-column label="总计" min-width="110">
          <template #default="{ row }">
            <el-tooltip content="总计 = 面值 × 数量" placement="top">
              <span class="formula-cell">{{ row.countTotal.toFixed(2) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="票面利率(%)" min-width="100">
          <template #default="{ row }">
            <el-input-number v-model="row.countCouponRate" size="small" :controls="false" :precision="4" :disabled="isReadonly" @change="reconciliationLogic.updateItem(row.id, { countCouponRate: row.countCouponRate })" />
          </template>
        </el-table-column>
        <el-table-column label="到期日" min-width="130">
          <template #default="{ row }">
            <el-date-picker v-model="row.countMaturityDate" type="date" value-format="YYYY-MM-DD" size="small" style="width: 100%;" :disabled="isReadonly" @change="reconciliationLogic.updateItem(row.id, { countMaturityDate: row.countMaturityDate })" />
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 增减变动(2列) ═══ -->
      <template v-if="activeTab === 'changes'">
        <el-table-column label="证券名称" prop="securitiesName" min-width="140" />
        <el-table-column label="增减数量" min-width="110">
          <template #default="{ row }">
            <el-input-number v-model="row.changeQuantity" size="small" :controls="false" :disabled="isReadonly" @change="reconciliationLogic.updateItem(row.id, { changeQuantity: row.changeQuantity })" />
          </template>
        </el-table-column>
        <el-table-column label="增减面值总额" min-width="120">
          <template #default="{ row }">
            <el-input-number v-model="row.changeFaceValueTotal" size="small" :controls="false" :disabled="isReadonly" @change="reconciliationLogic.updateItem(row.id, { changeFaceValueTotal: row.changeFaceValueTotal })" />
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 报表日实存+差异(10列) ═══ -->
      <template v-if="activeTab === 'reportDate'">
        <el-table-column label="证券名称" prop="securitiesName" min-width="120" />
        <el-table-column label="报表日数量" min-width="100">
          <template #default="{ row }">
            <el-tooltip content="报表日数量 = 盘点日数量 + 增减数量" placement="top">
              <span class="formula-cell">{{ row.reportQuantity }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="报表日面值" min-width="110">
          <template #default="{ row }">
            <el-input-number v-model="row.reportFaceValue" size="small" :controls="false" :disabled="isReadonly" @change="reconciliationLogic.updateItem(row.id, { reportFaceValue: row.reportFaceValue })" />
          </template>
        </el-table-column>
        <el-table-column label="报表日总计" min-width="110">
          <template #default="{ row }">
            <el-tooltip content="报表日总计 = 报表日面值 × 报表日数量" placement="top">
              <span class="formula-cell">{{ row.reportTotal.toFixed(2) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="票面利率(%)" min-width="100">
          <template #default="{ row }">
            <el-input-number v-model="row.reportCouponRate" size="small" :controls="false" :precision="4" :disabled="isReadonly" @change="reconciliationLogic.updateItem(row.id, { reportCouponRate: row.reportCouponRate })" />
          </template>
        </el-table-column>
        <el-table-column label="到期日" min-width="120">
          <template #default="{ row }">
            <el-date-picker v-model="row.reportMaturityDate" type="date" value-format="YYYY-MM-DD" size="small" style="width: 100%;" :disabled="isReadonly" @change="reconciliationLogic.updateItem(row.id, { reportMaturityDate: row.reportMaturityDate })" />
          </template>
        </el-table-column>
        <el-table-column label="账面结存数量" min-width="110">
          <template #default="{ row }">
            <el-input-number v-model="row.bookQuantity" size="small" :controls="false" :disabled="isReadonly" @change="reconciliationLogic.updateItem(row.id, { bookQuantity: row.bookQuantity })" />
          </template>
        </el-table-column>
        <el-table-column label="账面结存面值" min-width="110">
          <template #default="{ row }">
            <el-input-number v-model="row.bookFaceValue" size="small" :controls="false" :disabled="isReadonly" @change="reconciliationLogic.updateItem(row.id, { bookFaceValue: row.bookFaceValue })" />
          </template>
        </el-table-column>
        <el-table-column label="账面结存总计" min-width="110">
          <template #default="{ row }">
            <el-input-number v-model="row.bookTotal" size="small" :controls="false" :disabled="isReadonly" @change="reconciliationLogic.updateItem(row.id, { bookTotal: row.bookTotal })" />
          </template>
        </el-table-column>
        <el-table-column label="差异" min-width="100">
          <template #default="{ row, $index }">
            <el-tooltip content="差异 = 报表日总计 - 账面结存总计" placement="top">
              <span :class="['formula-cell', { 'variance-red': varianceHighlights[$index] }]">
                {{ row.variance.toFixed(2) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="140">
          <template #default="{ row, $index }">
            <el-input
              v-model="row.remark"
              size="small"
              :disabled="isReadonly"
              :class="{ 'remark-required': varianceHighlights[$index] }"
              :placeholder="varianceHighlights[$index] ? '差异非零，请填写说明' : ''"
              @change="reconciliationLogic.updateItem(row.id, { remark: row.remark })"
            />
          </template>
        </el-table-column>
      </template>

      <!-- 操作列（所有Tab共享） -->
      <el-table-column label="操作" width="60" align="center" fixed="right">
        <template #default="{ row }">
          <el-button
            type="danger"
            link
            size="small"
            :disabled="isReadonly || items.length <= 1"
            @click="reconciliationLogic.removeItem(row.id)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 合计行 -->
    <div class="summary-row">
      <span class="summary-label">合计：</span>
      <template v-if="activeTab === 'countDate'">
        <span class="summary-item">数量: {{ summary.countQuantityTotal }}</span>
        <span class="summary-item">面值: {{ summary.countFaceValueTotal.toFixed(2) }}</span>
        <span class="summary-item">总计: {{ summary.countTotalTotal.toFixed(2) }}</span>
      </template>
      <template v-if="activeTab === 'changes'">
        <span class="summary-item">增减数量: {{ summary.changeQuantityTotal }}</span>
        <span class="summary-item">增减面值总额: {{ summary.changeFaceValueTotalTotal.toFixed(2) }}</span>
      </template>
      <template v-if="activeTab === 'reportDate'">
        <span class="summary-item">报表日数量: {{ summary.reportQuantityTotal }}</span>
        <span class="summary-item">报表日总计: {{ summary.reportTotalTotal.toFixed(2) }}</span>
        <span class="summary-item">账面结存总计: {{ summary.bookTotalTotal.toFixed(2) }}</span>
        <span :class="['summary-item', { 'variance-red': Math.abs(summary.varianceTotal) >= 0.01 }]">差异合计: {{ summary.varianceTotal.toFixed(2) }}</span>
      </template>
    </div>

    <!-- 新增行 + 导入导出 -->
    <div class="table-actions">
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="reconciliationLogic.addItem()">
        + 新增倒轧行
      </el-button>
      <slot name="importExport" />
    </div>

    <!-- 审计结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <span>审计结论</span>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 8 }"
        placeholder="请输入倒轧表审计结论..."
        :disabled="isReadonly"
        @change="reconciliationLogic.setAuditConclusion(auditConclusion)"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>编制提示</summary>
      <div class="guidance-content">
        <p>1. 3个区段Tab共享同一组行数据，切换Tab仅改变显示的列。</p>
        <p>2. 盘点日实存：填写实际盘点到的证券数量和面值，总计自动计算。</p>
        <p>3. 增减变动：填写从盘点日到资产负债表日期间的证券增减。</p>
        <p>4. 报表日实存+差异：报表日数量=盘点日数量+增减数量(自动)；差异=报表日总计-账面结存总计(自动)。</p>
        <p>5. 差异非零的行以红色高亮，且备注为必填。</p>
        <p>6. 点击行可跨Tab保持选中状态（行同步）。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G4TabInventoryReconciliation.vue — G4-8 盘点倒轧结存表
 *
 * Spec: .kiro/specs/g4-bond-investment-sppi/ Task 7.4
 * Requirements: 5.1~5.10, 9.1~9.5, 9.10
 *
 * 完整实现：
 * - 3区段Tab (el-segmented): 盘点日实存(6列)/增减变动(2列)/报表日实存+差异(10列)
 * - 动态列切换（Tab切换仅切换列定义，不销毁el-table实例）
 * - selectedRowIndex 跨Tab行同步
 * - 差异行红色高亮 (|差异|>0)
 * - 合计行 + 审计结论 + AI辅助 + 复核对话
 */
import { inject, toRef, computed } from 'vue'
import { ChatDotRound, MagicStick } from '@element-plus/icons-vue'
import { useG4SppiReconciliation, TAB_OPTIONS } from '@/composables/useG4SppiReconciliation'
import type { ReconciliationItem, ReconciliationTab } from '@/composables/useG4SppiReconciliation'
import { useG4SppiFormData } from '@/composables/useG4SppiFormData'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'aiGenerate', section: string): void
}>()

// ─── 复核对话 inject ────────────────────────────────────────────────────────
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog')
function handleReview(sectionId: string): void {
  openReviewDialog?.(sectionId)
}
function emitAi(section: string): void {
  emit('aiGenerate', section)
}

// ─── 数据层（自包含：父级不传 allResponses/debouncedSave，对齐 G4TabBusinessModel） ───
const formData = useG4SppiFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
formData.loadAll()

// ─── composable ──────────────────────────────────────────────────────────────
const reconciliationLogic = useG4SppiReconciliation({
  allResponses: formData.allResponses,
  debouncedSave: formData.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const { activeTab, selectedRowIndex, items, summary, varianceHighlights, auditConclusion } = reconciliationLogic

// Tab选项（用于el-segmented）
const tabOptions = TAB_OPTIONS.map((t) => ({ label: t.label, value: t.key }))

// ─── 行选中（跨Tab同步） ──────────────────────────────────────────────────
function handleRowClick(row: ReconciliationItem | null): void {
  if (!row) return
  const idx = items.value.findIndex((i) => i.id === row.id)
  if (idx >= 0) reconciliationLogic.selectRow(idx)
}

function getRowClassName({ row, rowIndex }: { row: ReconciliationItem; rowIndex: number }): string {
  const classes: string[] = []
  if (rowIndex === selectedRowIndex.value) classes.push('selected-row')
  if (varianceHighlights.value[rowIndex]) classes.push('variance-highlight-row')
  return classes.join(' ')
}
</script>

<style scoped>
.g4-tab-inventory-reconciliation { font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; }
.section-actions { display: flex; gap: 6px; align-items: center; }

.reconciliation-tabs { margin-bottom: 12px; }

.reconciliation-table { margin-bottom: 8px; }
.reconciliation-table :deep(.selected-row) { background-color: #ecf5ff !important; }
.reconciliation-table :deep(.variance-highlight-row td) { background-color: #fef0f0 !important; }

.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 1px;
}
.variance-red {
  color: #f56c6c;
  font-weight: 600;
}
.remark-required :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px #f56c6c inset;
}

.summary-row {
  padding: 8px 12px;
  background: #f5f7fa;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  margin-bottom: 12px;
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  font-size: var(--wp-font-size, 13px);
}
.summary-label { font-weight: 600; color: #303133; }
.summary-item { color: #606266; }

.table-actions {
  display: flex;
  gap: 8px;
  margin: 8px 0 16px;
}

.conclusion-card { margin: 12px 0; }
.conclusion-card :deep(.el-card__header) {
  padding: 8px 16px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
}

.guidance-details {
  margin-top: 16px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #606266;
}
.guidance-content {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
  line-height: 1.8;
}
.guidance-content p { margin: 0; }
</style>
