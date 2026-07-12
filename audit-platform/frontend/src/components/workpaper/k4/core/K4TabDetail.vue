<template>
  <div class="k4-tab-detail">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>K4-2明细表按项目逐笔列示其他流动负债余额。<strong>负债类科目</strong>：期末=期初+贷方(增加)-借方(减少)。明细合计应与K4-1审定表审定数一致。</p>
    </div>

    <!-- 标题栏 + 操作 -->
    <div class="section-head">
      <h3 class="sheet-title">K4-2 其他流动负债明细表</h3>
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

    <!-- 2区段 el-segmented -->
    <el-segmented
      v-model="activeSegmentIdx"
      :options="segmentOptions"
      size="default"
      class="segment-bar"
    />

    <!-- 表格 -->
    <el-table
      :data="detail.detailRows.value"
      border
      size="small"
      :max-height="520"
      class="detail-table"
      show-summary
      :summary-method="summaryMethod"
    >
      <!-- ═══ 区段0 基础 ═══ -->
      <template v-if="activeSegmentIdx === 0">
        <el-table-column label="序号" width="55" align="center">
          <template #default="{ row }">{{ row.seqNo }}</template>
        </el-table-column>
        <el-table-column label="项目" min-width="200">
          <template #default="{ row }">
            <span>{{ row.projectName }}</span>
          </template>
        </el-table-column>
        <el-table-column label="性质" min-width="140">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.nature"
              size="small"
              placeholder="选择性质"
              @change="(v: string) => detail.updateCell(row.rowId, 'nature', v)"
            >
              <el-option v-for="opt in natureOptions" :key="opt" :label="opt" :value="opt" />
            </el-select>
            <span v-else>{{ row.nature || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" min-width="130" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.beginBalance"
              size="small"
              :controls="false"
              class="amount-input"
              @change="(v: number) => detail.updateCell(row.rowId, 'beginBalance', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期增加(贷方)" min-width="140" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.increase"
              size="small"
              :controls="false"
              class="amount-input"
              @change="(v: number) => detail.updateCell(row.rowId, 'increase', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少(借方)" min-width="140" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.decrease"
              size="small"
              :controls="false"
              class="amount-input"
              @change="(v: number) => detail.updateCell(row.rowId, 'decrease', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="130" align="right">
          <template #default="{ row }">
            <el-tooltip content="期末=期初+贷方-借方（负债类）" placement="top">
              <span class="formula-cell">{{ fmtAmt(row.endBalance) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 区段1 检查 ═══ -->
      <template v-if="activeSegmentIdx === 1">
        <el-table-column label="项目" min-width="200">
          <template #default="{ row }">
            <span>{{ row.projectName }}</span>
          </template>
        </el-table-column>
        <el-table-column label="增减原因" min-width="220">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.increaseReason"
              size="small"
              placeholder="增减原因"
              @change="(v: string) => detail.updateCell(row.rowId, 'increaseReason', v)"
            />
            <span v-else>{{ row.increaseReason || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证号" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.voucherRef"
              size="small"
              placeholder="凭证号"
              @change="(v: string) => detail.updateCell(row.rowId, 'voucherRef', v)"
            />
            <span v-else>{{ row.voucherRef || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核查结论" min-width="120">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.checkConclusion"
              size="small"
              placeholder="结论"
              @change="(v: string) => detail.updateCell(row.rowId, 'checkConclusion', v)"
            >
              <el-option v-for="opt in conclusionOptions" :key="opt" :label="opt" :value="opt" />
            </el-select>
            <span v-else>{{ row.checkConclusion || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.remark"
              size="small"
              placeholder="备注"
              @change="(v: string) => detail.updateCell(row.rowId, 'remark', v)"
            />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- 操作列（所有区段共享） -->
      <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
        <template #default="{ $index }">
          <el-button size="small" type="danger" link @click="handleRemoveRow($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部统计卡片 (Req 3.4: 项目数/期末合计) -->
    <div class="stats-bar">
      <el-tag type="info" effect="plain">项目数: {{ detail.subtotals.value.count }}</el-tag>
      <el-tag type="primary" effect="plain">期末合计: {{ fmtAmt(detail.subtotals.value.endBalance) }}</el-tag>
      <el-tag type="success" effect="plain">期初合计: {{ fmtAmt(detail.subtotals.value.beginBalance) }}</el-tag>
    </div>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>18列拆为2区段Tab切换（基础/检查），行数据同步</li>
        <li><strong>负债类科目</strong>：期末余额=期初余额+本期增加(贷方)-本期减少(借方)</li>
        <li>新增行需弹窗输入项目名称后创建</li>
        <li>明细合计应与K4-1审定表其他流动负债审定数一致（交叉验证）</li>
        <li>导入导出支持按模板批量录入明细</li>
        <li>性质分类：预提费用/待转销项税额/代扣代缴/短期融资/其他</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K4TabDetail.vue — K4-2 明细表（18列2区段+动态行+导入导出）
 * Spec: .kiro/specs/k4-other-current-liabilities/ | Task: 4.3
 * Requirements: 3.1-3.4
 *
 * 2区段Tab切换(el-segmented: 基础|检查)，同行同步
 * 区段0 基础：序号/项目/性质(下拉)/期初/本期增加(贷方)/本期减少(借方)/期末(公式:虚线)
 * 区段1 检查：项目(只读)/增减原因/凭证号/核查结论(下拉)/备注
 * 动态行新增：el-button"+ 新增"→ElMessageBox.prompt输入项目名称确认后创建
 * 底部统计卡片：项目数/期末合计
 * el-dropdown导入导出(导出模板/导出数据/导入数据)——useK4ImportExport消费
 * 公式列虚线下划线+cursor:help+tooltip
 * 合计行固定底部
 * 表格字体13px
 * AI按钮(section标题行右侧)
 * 编制提示(details折叠底部)
 * Consumes: useK4Detail composable + useK4ImportExport composable
 *
 * 科目：2245 其他流动负债（**贷方/负债类**）
 */
import { ref, computed, inject, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useK4Detail } from '../../composables/useK4Detail'
import { useK4ImportExport } from '../../composables/useK4ImportExport'

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

// ─── Constants ───────────────────────────────────────────────────────────────

const natureOptions = ['预提费用', '待转销项税额', '代扣代缴', '短期融资', '其他']
const conclusionOptions = ['正常', '异常', '需关注', '待确认']

const segmentOptions = [
  { label: '基础', value: 0 },
  { label: '检查', value: 1 },
]

// ─── Composables ─────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)

const detail = useK4Detail({
  allResponses: allResponsesRef as any,
  saveResponse: (itemId: string, value: any) => {
    emit('save', itemId, value)
  },
})

const {
  exportTemplate,
  exportData,
  importData,
} = useK4ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetCode: 'K4-2',
})

// ─── 区段状态 ────────────────────────────────────────────────────────────────

const activeSegmentIdx = ref(0)

// ─── 合计行 (show-summary) ───────────────────────────────────────────────────

function summaryMethod({ columns }: { columns: any[] }): string[] {
  return columns.map((col, idx) => {
    if (idx === 0) return '合计'
    const key = col.property
    if (!key) return ''

    // 基础区段合计
    if (activeSegmentIdx.value === 0) {
      if (['beginBalance', 'increase', 'decrease', 'endBalance'].includes(key)) {
        const total = detail.detailRows.value.reduce((sum, r) => sum + ((r as any)[key] || 0), 0)
        return fmtAmt(total)
      }
    }
    return ''
  })
}

// ─── 行操作 ──────────────────────────────────────────────────────────────────

async function handleAddRow() {
  await detail.addRow()
}

function handleRemoveRow(idx: number) {
  const row = detail.detailRows.value[idx]
  if (!row) return
  ElMessageBox.confirm(
    `确定删除项目"${row.projectName}"？删除后不可恢复。`,
    '确认删除',
    {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    },
  ).then(() => {
    detail.removeRow(idx)
    ElMessage.success('已删除')
  }).catch(() => {
    // 用户取消
  })
}

// ─── 导入导出 ─────────────────────────────────────────────────────────────────

function handleExportTemplate() { exportTemplate() }
function handleExportData() { exportData() }

function handleImportData() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls'
  input.onchange = async (e) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return
    await importData(file)
  }
  input.click()
}

// ─── AI / 复核 ───────────────────────────────────────────────────────────────

function handleAiGenerate() {
  console.log('[K4-2] AI generate: detail')
}

function handleReview() {
  openReviewDialog('K4-2-detail')
}

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k4-tab-detail {
  padding: 16px;
  font-size: var(--wp-font-size, 13px);
}

/* 方法论上下文（琥珀色左边线+浅黄背景） */
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

/* el-segmented 区段栏 */
.segment-bar {
  margin-bottom: 12px;
}

/* 表格 */
.detail-table {
  font-size: var(--wp-font-size, 13px);
}

.amount-cell {
  font-variant-numeric: tabular-nums;
}

.amount-input {
  width: 100%;
}

.amount-input :deep(.el-input__inner) {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

/* 公式列：虚线下划线 + cursor:help */
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}

/* 合计行固定底部 */
.detail-table :deep(.el-table__footer-wrapper) {
  font-weight: 600;
  position: sticky;
  bottom: 0;
  z-index: 2;
  background: var(--el-bg-color);
}

/* 统计栏 */
.stats-bar {
  display: flex;
  gap: 12px;
  margin-top: 12px;
  padding: 10px 0;
  flex-wrap: wrap;
}

/* 编制提示 */
.compile-hint {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.compile-hint summary {
  cursor: pointer;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.compile-hint ul {
  padding-left: 20px;
  margin-top: 8px;
  line-height: 1.8;
}
</style>
