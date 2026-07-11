<template>
  <div class="h1-tab-dep-alloc">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="obj-alert">
      <template #title>审计目标：验证H1-12测算的折旧总额已按使用部门合理分配至制造费用(D5)/管理费用(K8)/销售费用(K9)，分配合计与折旧总额一致。</template>
    </el-alert>

    <div class="methodology-context">
      <p>折旧费用分配：将H1-12测算的折旧总额按使用部门分配到制造费用(D5)、管理费用(K8)、销售费用(K9)等科目。分配比例基于部门折旧占比自动计算。</p>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>H1-13 折旧费用分配表 <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag></span>
          <div class="title-actions">
            <el-button size="small" type="primary" @click="handleAddRow" :disabled="isReadonly">+ 新增</el-button>
            <el-button size="small" type="default" link @click="handleReview('H1-13')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="rows" border stripe size="small" class="alloc-table">
        <el-table-column type="index" width="40" />
        <el-table-column prop="department" label="使用部门" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.department" size="small" @change="onCellChange(row, 'department', row.department)" />
            <span v-else>{{ row.department }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="expenseAccount" label="费用科目" width="130">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.expenseAccount" size="small" @change="onCellChange(row, 'expenseAccount', row.expenseAccount)">
              <el-option label="制造费用" value="制造费用" />
              <el-option label="管理费用" value="管理费用" />
              <el-option label="销售费用" value="销售费用" />
            </el-select>
            <span v-else>{{ row.expenseAccount }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="depAmount" label="折旧金额" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.depAmount" :controls="false" size="small"
              @change="onCellChange(row, 'depAmount', row.depAmount)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.depAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="分配比例%" width="90" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="分配比例=本行折旧÷折旧合计×100%">{{ row.allocRate != null ? row.allocRate.toFixed(2) + '%' : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="allocToManufacture" label="制造费用(D5)" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.allocToManufacture" :controls="false" size="small"
              @change="onCellChange(row, 'allocToManufacture', row.allocToManufacture)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.allocToManufacture) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="allocToAdmin" label="管理费用(K8)" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.allocToAdmin" :controls="false" size="small"
              @change="onCellChange(row, 'allocToAdmin', row.allocToAdmin)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.allocToAdmin) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="allocToSales" label="销售费用(K9)" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.allocToSales" :controls="false" size="small"
              @change="onCellChange(row, 'allocToSales', row.allocToSales)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.allocToSales) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="bookAmount" label="账面金额" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.bookAmount" :controls="false" size="small"
              @change="onCellChange(row, 'bookAmount', row.bookAmount)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.bookAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异" width="100" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': Math.abs(row.difference) > 0.01 }]" title="差异=分配合计-账面">
              {{ fmtAmt(row.difference) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="onCellChange(row, 'remark', row.remark)" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="removeRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 合计 -->
      <div class="totals-bar">
        <span>折旧金额合计: <b class="amount-cell">{{ fmtAmt(totalDepAmount) }}</b></span>
        <span>制造费用: <b class="amount-cell">{{ fmtAmt(totalManufacture) }}</b></span>
        <span>管理费用: <b class="amount-cell">{{ fmtAmt(totalAdmin) }}</b></span>
        <span>销售费用: <b class="amount-cell">{{ fmtAmt(totalSales) }}</b></span>
        <span>差异合计: <b :class="['amount-cell', { 'error-amount': Math.abs(totalDifference) > 0.01 }]">{{ fmtAmt(totalDifference) }}</b></span>
      </div>

      <!-- 核对行 -->
      <div class="verify-row">
        <el-table :data="reconciliationRows" size="small" border>
          <el-table-column prop="label" label="核对项" min-width="160" />
          <el-table-column label="测算/分配数" width="140" align="right">
            <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.calculated) }}</span></template>
          </el-table-column>
          <el-table-column label="对方底稿数" width="140" align="right">
            <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.book) }}</span></template>
          </el-table-column>
          <el-table-column label="差异" width="130" align="right">
            <template #default="{ row }">
              <span :class="['amount-cell', { 'error-amount': Math.abs(row.difference) > 0.01 }]">{{ fmtAmt(row.difference) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="跳转" width="90" align="center">
            <template #default="{ row }">
              <GtIndexChip v-if="row.targetWpCode" :value="row.targetWpCode" @click="navigateTo(row.targetWpCode)" />
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计结论</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="publishAllocated" :disabled="isReadonly">📤 发布折旧分配</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" />
    </el-card>

    <div class="jump-targets">
      <span style="font-size:12px;color:var(--el-text-color-secondary)">跳转目标:</span>
      <GtIndexChip value="D5" @click="navigateTo('D5')" />
      <GtIndexChip value="K8" @click="navigateTo('K8')" />
      <GtIndexChip value="K9" @click="navigateTo('K9')" />
    </div>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>分配比例=本行折旧÷折旧合计（自动），分配金额合计应=折旧总额</li>
        <li>制造费用→D5营业成本，管理费用→K8管理费用，销售费用→K9销售费用</li>
        <li>差异=（制造+管理+销售）-账面金额，差异>0.01红色高亮</li>
        <li>核对行验证分配是否与H1-12测算一致</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H1TabDepreciationAlloc.vue — H1-13 折旧费用分配表
 * Task 6.7: 折旧分配跨底稿联动
 * - publish 'h1:depreciation-allocated' event
 * - GtIndexChip 跳转 D5/K8/K9
 */
import { ref, computed, inject, toRef } from 'vue'
import { useH1DepreciationAlloc, type AllocRow } from '../../composables/useH1DepreciationAlloc'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const emit = defineEmits<{ (e: 'navigate-sheet', sheetName: string): void }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const conclusion = ref('')

const {
  rows,
  totalDepAmount,
  totalManufacture,
  totalAdmin,
  totalSales,
  totalDifference,
  reconciliationRows,
  updateCell,
  addRow,
  removeRow,
  publishAllocated,
} = useH1DepreciationAlloc(toRef(props, 'wpId'), toRef(props, 'projectId'), allResponsesRef as any, {
  onPublishEvent(event: string, payload: any) {
    // 6.7 — publish 'h1:depreciation-allocated'
    console.log('[H1-13] publish', event, payload)
  },
})

function handleAddRow() { addRow() }
function onCellChange(row: AllocRow, field: keyof AllocRow, value: any) { updateCell(row.rowId, field, value) }
function navigateTo(wpCode: string) { emit('navigate-sheet', wpCode) }
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-dep-alloc { padding: 16px; font-size: 13px; }
.obj-alert { margin-bottom: 12px; }
.methodology-context { border-left: 3px solid var(--el-color-warning); background: #fffbe6; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 12px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.alloc-table { font-size: 13px; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.totals-bar { display: flex; flex-wrap: wrap; gap: 20px; padding: 10px 12px; margin-top: 12px; background: var(--el-fill-color-light); border-radius: 4px; }
.verify-row { margin-top: 16px; }
.note-card { margin-top: 12px; }
.jump-targets { display: flex; align-items: center; gap: 8px; margin-top: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
