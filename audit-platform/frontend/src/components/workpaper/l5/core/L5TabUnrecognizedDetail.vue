<template>
  <div class="l5-tab-unrecognized-detail">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">L5-3 未确认融资费用明细表</h3>
        <el-tag type="danger" size="small">借方备抵</el-tag>
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
        <el-button size="small" @click="handleAI('unrecognized')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>未确认融资费用（借方/负债备抵类）：</strong>
        初始确认=名义金额−现值（长期应付款面值与现值之差）。
        后续：每期摊销计入财务费用（实际利率法），未确认余额=初始−累计摊销。
        与L5-2各款项一一对应，与L5-5摊销测算核对。
      </div>
    </div>

    <!-- ═══ 区段Tab切换器 ═══ -->
    <el-segmented v-model="activeSegment" :options="segmentOptions" size="default" class="segment-switcher" />

    <!-- ═══ 明细表主体 ═══ -->
    <el-table :data="computedRows" border size="small" style="width: 100%" highlight-current-row>
      <el-table-column type="index" label="#" width="50" align="center" fixed />
      <el-table-column prop="payableName" label="对应款项" min-width="160" fixed>
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" :model-value="row.payableName" size="small" @change="(val: string) => handleUpdate($index, 'payableName', val)" />
          <span v-else>{{ row.payableName || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 基础信息区段 -->
      <template v-if="activeSegment === 'basic'">
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
        <el-table-column label="初始未确认" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.initialUnrecognized" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'initialUnrecognized', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.initialUnrecognized) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="实际利率(%)" min-width="110" align="right">
          <template #header>
            <el-tooltip content="与L5-5摊销测算利率一致" placement="top">
              <span class="formula-col-header">实际利率(%)</span>
            </el-tooltip>
          </template>
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.effectiveRate * 100" :controls="false" :precision="4" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'effectiveRate', (val ?? 0) / 100)" />
            <span v-else>{{ (row.effectiveRate * 100).toFixed(4) }}%</span>
          </template>
        </el-table-column>
      </template>

      <!-- 摊销信息区段 -->
      <template v-if="activeSegment === 'amortization'">
        <el-table-column label="期初余额" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.beginning" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'beginning', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.beginning) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期新增(借方)" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.periodIncrease" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'periodIncrease', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.periodIncrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期摊销(贷方)" min-width="130" align="right">
          <template #header>
            <el-tooltip content="实际利率法摊销额，由L5-5计算" placement="top">
              <span class="formula-col-header">本期摊销(贷方)</span>
            </el-tooltip>
          </template>
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.periodAmortization" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'periodAmortization', val ?? 0)" />
            <span v-else class="formula-value">{{ fmtAmount(row.periodAmortization) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="累计摊销" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.cumulativeAmortization" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'cumulativeAmortization', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.cumulativeAmortization) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未确认余额" min-width="130" align="right">
          <template #header>
            <el-tooltip content="初始未确认 − 累计摊销" placement="top">
              <span class="formula-col-header">未确认余额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.unrecognizedBalance) }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- 审计调整区段 -->
      <template v-if="activeSegment === 'audit'">
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
      <span>未确认余额合计：<strong>{{ fmtAmount(totalUnrecognizedBalance) }}</strong></span>
      <span>本期摊销合计：<strong>{{ fmtAmount(totalPeriodAmortization) }}</strong></span>
      <span>初始未确认合计：<strong>{{ fmtAmount(totalInitialUnrecognized) }}</strong></span>
      <span>共 <strong>{{ computedRows.length }}</strong> 笔款项</span>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="l5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>未确认融资费用是借方/负债备抵类科目</li>
        <li>未确认余额=初始未确认−累计摊销</li>
        <li>各行应与L5-2明细表款项一一对应</li>
        <li>本期摊销应与L5-5摊销测算表一致</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L5TabUnrecognizedDetail — L5-3 未确认融资费用明细表
 * Requirements: 3.3-3.6
 */
import { computed, inject, onMounted, ref } from 'vue'
import { Plus, MagicStick, Check } from '@element-plus/icons-vue'
import { useL5FormData } from '../../../composables/useL5FormData'
import {
  useL5UnrecognizedDetail,
  type L5UnrecognizedRow,
  L5_UNRECOGNIZED_SEGMENTS,
} from '../../../composables/useL5UnrecognizedDetail'

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

const unrecognizedRows = ref<L5UnrecognizedRow[]>([])

const {
  activeSegment,
  switchSegment,
  computedRows,
  totalUnrecognizedBalance,
  totalPeriodAmortization,
  totalInitialUnrecognized,
  addRow,
  removeRow,
  updateRow,
} = useL5UnrecognizedDetail(formData, unrecognizedRows)

const segmentOptions = L5_UNRECOGNIZED_SEGMENTS.map(s => ({ label: s.label, value: s.key }))

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleAddRow() { addRow() }
function handleRemoveRow(index: number) { removeRow(index) }
function handleUpdate(index: number, field: keyof L5UnrecognizedRow, value: string | number) {
  updateRow(index, field, value)
}
function handleImportExport(command: string) {}
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
.l5-tab-unrecognized-detail { padding: 12px; font-size: 13px; }
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
