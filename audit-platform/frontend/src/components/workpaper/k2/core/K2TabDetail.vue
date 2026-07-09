<!--
  K2TabDetail.vue — K2-2 明细表（18列 → 2区段Tab）

  2区段Tab切换：基础(序号/项目名称/性质/期初余额/增加/减少/期末余额(公式))
              / 检查(项目名称/增减原因/凭证号/核查结论/备注)
  区段间行同步：所有区段共享同一行集合，切换Tab只改可见列
  公式列：期末余额=期初+增加-减少 (dashed underline + tooltip)
  动态行：ElMessageBox.prompt输入项目名称再创建
  底部统计：项目数 / 期末合计
  导入导出：el-dropdown「导入导出▾」(导出模板/导出数据/导入数据)
  性质列：el-select(预付款项/待摊费用/合同取得成本/待抵扣税额/押金保证金/其他)

  Spec: .kiro/specs/k2-other-current-assets/ Task 4.3
  Requirements: 3.1-3.4
-->
<template>
  <div class="k2-tab-detail">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>K2-2明细表按项目逐笔列示其他流动资产余额及增减变动。期末余额(公式)=期初+增加-减少，合计行联动审定表K2-1。</p>
    </div>

    <!-- 标题栏 + 操作 -->
    <div class="section-head">
      <h3 class="sheet-title">K2-2 其他流动资产明细表</h3>
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

    <!-- 2区段Tab -->
    <el-tabs v-model="activeSegment" type="border-card" class="segment-tabs">
      <el-tab-pane label="基础" name="basic" />
      <el-tab-pane label="检查" name="check" />
    </el-tabs>

    <!-- 表格 -->
    <el-table
      :data="detail.rows.value"
      border
      size="small"
      :max-height="520"
      class="detail-table"
    >
      <!-- ═══ 基础区段列 ═══ -->
      <template v-if="activeSegment === 'basic'">
        <el-table-column label="序号" width="55" align="center">
          <template #default="{ row }">{{ row.seqNo }}</template>
        </el-table-column>
        <el-table-column label="项目名称" min-width="160">
          <template #default="{ row }">
            <span>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="性质" min-width="130">
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
        <el-table-column label="本期增加" min-width="120" align="right">
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
        <el-table-column label="本期减少" min-width="120" align="right">
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
            <el-tooltip content="期末=期初+增加-减少" placement="top">
              <span class="formula-cell">{{ fmtAmt(row.endBalance) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 检查区段列 ═══ -->
      <template v-if="activeSegment === 'check'">
        <el-table-column label="项目名称" min-width="160">
          <template #default="{ row }">
            <span>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="增减原因" min-width="180">
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
              <el-option label="正常" value="正常" />
              <el-option label="异常" value="异常" />
              <el-option label="待确认" value="待确认" />
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

      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="danger" link @click="handleRemoveRow(row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部统计栏 -->
    <div class="stats-bar">
      <el-tag type="info" effect="plain">项目数: {{ detail.subtotals.value.count }}</el-tag>
      <el-tag type="primary" effect="plain">期末合计: {{ fmtAmt(detail.subtotals.value.endBalance) }}</el-tag>
    </div>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>18列拆为2区段Tab切换（基础/检查），行数据同步</li>
        <li>期末余额(公式)=期初余额+本期增加-本期减少</li>
        <li>性质列选项：预付款项/待摊费用/合同取得成本/待抵扣税额/押金保证金/其他</li>
        <li>新增行需弹窗输入项目名称后创建</li>
        <li>明细合计应与K2-1审定表其他流动资产总额一致</li>
        <li>导入导出支持按模板批量录入明细</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K2TabDetail.vue — K2-2 明细表
 * Spec: .kiro/specs/k2-other-current-assets/ | Task: 4.3
 * Requirements: 3.1-3.4
 * 18列2区段Tab + 动态行 + 公式列 + 导入导出 + 统计
 */
import { ref, computed, inject, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useK2Detail } from '../../../composables/useK2Detail'
import { useK2ImportExport } from '../../../composables/useK2ImportExport'

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

const natureOptions = ['预付款项', '待摊费用', '合同取得成本', '待抵扣税额', '押金保证金', '其他']

// ─── Composables ─────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)

const detail = useK2Detail(allResponsesRef as any, {
  onSave: (itemId: string, value: any) => {
    emit('save', itemId, { remark: value })
  },
})

const {
  exportTemplate,
  exportData,
  importData,
} = useK2ImportExport({ wpId: toRef(props, 'wpId') })

// ─── 区段状态 ────────────────────────────────────────────────────────────────

const activeSegment = ref<'basic' | 'check'>('basic')

// ─── 行操作 ──────────────────────────────────────────────────────────────────

async function handleAddRow() {
  await detail.addRow()
}

function handleRemoveRow(rowId: string) {
  ElMessageBox.confirm('确定删除该明细行？删除后不可恢复。', '确认删除', {
    confirmButtonText: '删除',
    cancelButtonText: '取消',
    type: 'warning',
  }).then(() => {
    detail.removeRow(rowId)
    ElMessage.success('已删除')
  }).catch(() => {
    // 用户取消
  })
}

// ─── 导入导出 ─────────────────────────────────────────────────────────────────

function handleExportTemplate() { exportTemplate('K2-2') }
function handleExportData() { exportData('K2-2') }

function handleImportData() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls'
  input.onchange = async (e) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return
    await importData('K2-2', file)
  }
  input.click()
}

// ─── AI / 复核 ───────────────────────────────────────────────────────────────

function handleAiGenerate() {
  console.log('[K2-2] AI generate: detail')
}
function handleReview() { openReviewDialog('K2-2-detail') }

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k2-tab-detail {
  padding: 16px;
  font-size: 13px;
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

/* 区段Tab */
.segment-tabs {
  margin-bottom: 0;
}
.segment-tabs :deep(.el-tabs__content) {
  display: none;
}

/* 表格 */
.detail-table {
  font-size: 13px;
  margin-top: -1px;
}
.amount-cell {
  font-variant-numeric: tabular-nums;
}
.amount-input {
  width: 100%;
}

/* 公式列：虚线下划线 + cursor:help */
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}

/* 统计栏 */
.stats-bar {
  display: flex;
  gap: 12px;
  margin-top: 12px;
  padding: 10px 0;
}

/* 编制提示 */
.compile-hint {
  margin-top: 16px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.compile-hint summary {
  cursor: pointer;
  font-weight: 500;
}
.compile-hint ul {
  padding-left: 20px;
  margin-top: 8px;
  line-height: 1.8;
}
</style>
