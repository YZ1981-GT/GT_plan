<template>
  <div class="l5-tab-detail">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">L5-2 长期应付款明细表</h3>
        <el-tag type="warning" size="small">30列·区段Tab</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          <el-icon><Plus /></el-icon> 新增款项
        </el-button>
        <el-dropdown :disabled="isReadonly" @command="handleImportExport" trigger="click">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item command="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item command="importData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="handleAI('detail')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 审计目标 ═══ -->
    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
      <template #title>
        <strong>审计目标：</strong>核实长期应付款各笔款项的真实性、完整性与计价（现值/折现率），明细合计与审定表 L5-1 勾稽一致，各行与 L5-5 摊销测算一一对应。
      </template>
    </el-alert>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>30列按3区段Tab管理：</strong>
        未审数区（款项来源/债权人/起止日/名义金额/折现率/现值/期初/增加/偿还/期末余额） →
        调整区（未审/AJE/RJE/审定） → 审定数区（币种/担保/备注）。
        负债类：期末=期初+本期增加(贷方)−本期偿还(借方)。各行与L5-5摊销测算一一对应。
      </div>
    </div>

    <!-- ═══ 区段Tab切换器 ═══ -->
    <el-segmented v-model="activeSegment" :options="segmentOptions" size="default" class="segment-switcher" />

    <!-- ═══ 明细表主体 ═══ -->
    <el-table :data="computedRows" border size="small" style="width: 100%" highlight-current-row>
      <el-table-column type="index" label="#" width="50" align="center" fixed />
      <el-table-column prop="payableName" label="款项名称" min-width="160" fixed>
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" :model-value="row.payableName" size="small" @change="(val: string) => handleUpdate($index, 'payableName', val)" />
          <span v-else>{{ row.payableName || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 未审数区段 -->
      <template v-if="activeSegment === 'unadjusted'">
        <el-table-column label="债权人" min-width="140">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" :model-value="row.creditor" size="small" @change="(val: string) => handleUpdate($index, 'creditor', val)" />
            <span v-else>{{ row.creditor || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="起始日" min-width="120">
          <template #default="{ row, $index }">
            <el-date-picker v-if="!isReadonly" :model-value="row.startDate" type="date" size="small" value-format="YYYY-MM-DD" style="width:100%" @change="(val: string) => handleUpdate($index, 'startDate', val)" />
            <span v-else>{{ row.startDate || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="到期日" min-width="120">
          <template #default="{ row, $index }">
            <el-date-picker v-if="!isReadonly" :model-value="row.maturityDate" type="date" size="small" value-format="YYYY-MM-DD" style="width:100%" @change="(val: string) => handleUpdate($index, 'maturityDate', val)" />
            <span v-else>{{ row.maturityDate || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="款项类型" min-width="130">
          <template #default="{ row, $index }">
            <el-select v-if="!isReadonly" :model-value="row.category" size="small" style="width:100%" @change="(val: string) => handleUpdate($index, 'category', val)">
              <el-option label="融资租赁" value="融资租赁" />
              <el-option label="分期付款" value="分期付款" />
              <el-option label="其他" value="其他" />
            </el-select>
            <span v-else>{{ row.category || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="名义金额" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.nominalAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'nominalAmount', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.nominalAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="折现率(%)" min-width="100" align="right">
          <template #header>
            <el-tooltip content="实际利率（EIR），与L5-5摊销一致" placement="top">
              <span class="formula-col-header">折现率(%)</span>
            </el-tooltip>
          </template>
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.discountRate * 100" :controls="false" :precision="4" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'discountRate', (val ?? 0) / 100)" />
            <span v-else>{{ (row.discountRate * 100).toFixed(4) }}%</span>
          </template>
        </el-table-column>
        <el-table-column label="现值" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.presentValue" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'presentValue', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.presentValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.beginning" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'beginning', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.beginning) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期增加(贷方)" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.periodIncrease" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'periodIncrease', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.periodIncrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期偿还(借方)" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.periodRepayment" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'periodRepayment', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.periodRepayment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="130" align="right">
          <template #header>
            <el-tooltip content="期初+本期增加(贷方)−本期偿还(借方)，负债类" placement="top">
              <span class="formula-col-header">期末余额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endBalance) }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- 调整区段 -->
      <template v-if="activeSegment === 'adjustment'">
        <el-table-column label="未审数" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.unadjusted" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'unadjusted', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.aje" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'aje', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.rje" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'rje', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="130" align="right">
          <template #header>
            <el-tooltip content="未审+AJE+RJE" placement="top">
              <span class="formula-col-header">审定数</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.unadjusted + row.aje + row.rje) }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- 审定数区段 -->
      <template v-if="activeSegment === 'audited'">
        <el-table-column label="币种" min-width="100">
          <template #default="{ row, $index }">
            <el-select v-if="!isReadonly" :model-value="row.currency" size="small" style="width:100%" @change="(val: string) => handleUpdate($index, 'currency', val)">
              <el-option label="CNY" value="CNY" />
              <el-option label="USD" value="USD" />
              <el-option label="EUR" value="EUR" />
            </el-select>
            <span v-else>{{ row.currency || 'CNY' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="担保方式" min-width="160">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" :model-value="row.guaranteeType" size="small" @change="(val: string) => handleUpdate($index, 'guaranteeType', val)" />
            <span v-else>{{ row.guaranteeType || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="200">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small" @change="(val: string) => handleUpdate($index, 'remark', val)" />
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="操作" width="70" align="center" fixed="right">
        <template #default="{ $index }">
          <el-button type="danger" text size="small" @click="handleRemoveRow($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 合计区 ═══ -->
    <div class="summary-bar">
      <span>期末余额合计：<strong>{{ fmtAmount(totalEndBalance) }}</strong></span>
      <span>期初余额合计：<strong>{{ fmtAmount(totalBeginning) }}</strong></span>
      <span>名义金额合计：<strong>{{ fmtAmount(totalNominalAmount) }}</strong></span>
      <span>共 <strong>{{ computedRows.length }}</strong> 笔款项</span>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="l5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>30列按3区段Tab拆分，行跨区段同步</li>
        <li>负债类：期末=期初+本期增加(贷方)−本期偿还(借方)</li>
        <li>各行应与L5-5摊销测算表按款项一一对应</li>
        <li>明细合计应与审定表L5-1核对一致</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L5TabDetail — L5-2 长期应付款明细表（30列·区段Tab）
 * Requirements: 3.1-3.6
 */
import { computed, inject, onMounted, ref } from 'vue'
import { Plus, MagicStick, Check } from '@element-plus/icons-vue'
import { useL5FormData } from '../../composables/useL5FormData'
import { useL5Detail, type L5DetailRow, L5_DETAIL_SEGMENTS } from '../../composables/useL5Detail'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<() => void>('openReviewDialog', () => {})

// ─── FormData + Composable ──────────────────────────────────────────────────

const formData = useL5FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const detailRows = ref<L5DetailRow[]>([])

const {
  activeSegment,
  switchSegment,
  computedRows,
  totalEndBalance,
  totalBeginning,
  totalNominalAmount,
  addRow,
  removeRow,
  updateRow,
} = useL5Detail(formData, detailRows)

const segmentOptions = L5_DETAIL_SEGMENTS.map(s => ({ label: s.label, value: s.key }))

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleAddRow() { addRow() }
function handleRemoveRow(index: number) { removeRow(index) }
function handleUpdate(index: number, field: keyof L5DetailRow, value: string | number) {
  updateRow(index, field, value)
}
function handleImportExport(command: string) {
  // Delegate to useL5ImportExport composable
}
function handleAI(_section: string) {}
function handleReview() { openReviewDialog?.() }

function fmtAmount(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

onMounted(async () => {
  await formData.loadData()
})
</script>

<style scoped>
.l5-tab-detail { padding: 12px; font-size: 13px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: 13px; color: #6b5900; line-height: 1.6; }
.segment-switcher { margin-bottom: 12px; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
:deep(.el-table) { font-size: 13px; }
.summary-bar { display: flex; gap: 24px; padding: 10px 16px; margin-top: 12px; background: #f5f7fa; border-radius: 6px; font-size: 13px; color: #606266; }
.l5-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266; }
.l5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
