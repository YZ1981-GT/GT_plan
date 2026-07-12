<script setup lang="ts">
/** F3TabAdjustment — F3-3 调整分录 | Task 6 (比照 D4TabAdjustment) */
import { toRef, inject, type Ref } from 'vue'
import { useF3Adjustment } from '../composables/useF3Adjustment'
import F3ImportExportToolbar from './F3ImportExportToolbar.vue'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const reloadWorkpaperData = inject<(() => void) | null>('reloadWorkpaperData', null)
function onImported() { reloadWorkpaperData?.() }

function fmt(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const { rows, debitTotal, creditTotal, balanceDiff, isBalanced, addRow, removeRow, updateCell } = useF3Adjustment({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})
</script>

<template>
  <div class="f3-tab-adjustment">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 记录应付票据（科目2201）相关的审计调整分录：AJE（账项调整，影响科目余额）/ RJE（重分类，仅影响报表列报）。</p>
        <p>2. 典型调整：已到期未兑付票据重分类至应付账款、带息票据补提应付利息、保证金存款重分类至其他货币资金/受限资产。</p>
        <p>3. 借贷合计必须平衡（借方合计=贷方合计），不平衡时下方提示红色。</p>
        <p>4. 确认后的调整分录同步更新 F3-1 审定表的账项调整/重分类列，并可推送至 A13 错报汇总。</p>
      </div>
    </details>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 新增分录</el-button>
      </div>
      <div class="toolbar-right">
        <F3ImportExportToolbar :wp-id="wpId" :project-id="projectId" sheet="F3-3" :disabled="isReadonly" @imported="onImported" />
        <span class="chip-wrap"><GtIndexChip value="wp:F3-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:A13" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <!-- 借贷平衡指示 -->
    <div class="balance-indicator" :class="{ unbalanced: !isBalanced }">
      <span class="balance-item">借方合计：<strong>{{ fmt(debitTotal) }}</strong></span>
      <span class="balance-item">贷方合计：<strong>{{ fmt(creditTotal) }}</strong></span>
      <el-tag v-if="isBalanced" type="success" size="small">借贷平衡</el-tag>
      <el-tag v-else type="danger" size="small">不平衡 差异 {{ fmt(balanceDiff) }}</el-tag>
    </div>

    <el-table :data="rows" border size="small" style="width: 100%">
      <el-table-column prop="seq" label="序号" width="60" />
      <el-table-column label="类型" width="90">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.entryType" size="small" @change="(v: string) => updateCell(row.rowId, 'entryType', v)">
            <el-option label="AJE" value="AJE" /><el-option label="RJE" value="RJE" />
          </el-select>
          <span v-else>{{ row.entryType }}</span>
        </template>
      </el-table-column>
      <el-table-column label="日期" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.date" size="small" @change="(v: string) => updateCell(row.rowId, 'date', v)" />
          <span v-else>{{ row.date }}</span>
        </template>
      </el-table-column>
      <el-table-column label="摘要" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.summary" size="small" @change="(v: string) => updateCell(row.rowId, 'summary', v)" />
          <span v-else>{{ row.summary }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目" width="100"><template #default="{ row }">{{ row.accountCode }}</template></el-table-column>
      <el-table-column label="借方" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.debitAmount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'debitAmount', v ?? 0)" />
          <span v-else>{{ fmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.creditAmount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'creditAmount', v ?? 0)" />
          <span v-else>{{ fmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60">
        <template #default="{ row }"><el-button link type="danger" size="small" :disabled="isReadonly" @click="removeRow(row.rowId)">删</el-button></template>
      </el-table-column>
    </el-table>

    <div class="balance-bar" :class="{ unbalanced: !isBalanced }">
      借方合计 {{ fmt(debitTotal) }} | 贷方合计 {{ fmt(creditTotal) }} | 差额 {{ fmt(balanceDiff) }}
      <span v-if="!isBalanced"> — 借贷不平衡</span>
    </div>
  </div>
</template>

<style scoped>
.f3-tab-adjustment {
  padding: 12px;
}
.f3-tab-adjustment :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.f3-tab-adjustment :deep(.el-table .cell) {
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
.balance-indicator {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  margin-bottom: 12px;
  font-size: var(--wp-font-size, 13px);
}
.balance-item { color: #606266; }
.balance-item strong { color: #303133; }
.balance-indicator.unbalanced .balance-item strong { color: #f56c6c; }
.balance-bar {
  margin-top: 8px;
  text-align: right;
  font-weight: 600;
}
.balance-bar.unbalanced { color: #f56c6c; }
</style>
