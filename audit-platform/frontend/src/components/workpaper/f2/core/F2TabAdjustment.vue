<script setup lang="ts">
/** F2TabAdjustment — F2-14 调整分录 | Task 15.4 */
import { toRef, inject, type Ref } from 'vue'
import { useF2Adjustment } from '../../composables/useF2Adjustment'
import type { ChecklistResponse } from '../../composables/useF2FormData'
import GtIndexChip from '../../GtIndexChip.vue'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
import F2ReviewChip from '../shared/F2ReviewChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
async function onImported() { await reloadWorkpaperData?.() }

function fmt(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const {
  rows, debitTotal, creditTotal, balanceDiff, isBalanced, accountOptions,
  addRow, removeRow, updateCell, publishAdjustments,
} = useF2Adjustment({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})
</script>

<template>
  <div class="f2-tab-adjustment">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 记录存货相关的审计调整分录：AJE（账项调整，影响科目余额）/ RJE（重分类调整，仅影响列报）。</p>
        <p>2. 借贷合计必须平衡（借方合计 = 贷方合计），不平衡时无法同步。</p>
        <p>3. 确认后的分录自动联动回写 F2-1 审定表的账项调整列。</p>
        <p>4. 依《企业会计准则第 1 号——存货》，跌价准备计提/转回、成本结转差错等均通过本表调整。</p>
      </div>
    </details>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 新增分录</el-button>
        <el-button size="small" :disabled="isReadonly" @click="publishAdjustments">同步至审定表</el-button>
        <F2ReviewChip section-id="F2-14-adjustment" />
      </div>
      <div class="toolbar-right">
        <CycleImportExportDropdown
          :wp-id="wpId"
          api-prefix="f2"
          sheet="F2-14"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:F2-1" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <el-table :data="rows" border size="small" style="font-size:13px">
      <el-table-column prop="seq" label="序号" width="55" />
      <el-table-column label="调整事项说明" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.summary" size="small" @change="(v: string) => updateCell(row.rowId, 'summary', v)" />
          <span v-else>{{ row.summary }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目编码" width="100">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.accountCode" size="small" filterable
            @change="(v: string) => updateCell(row.rowId, 'accountCode', v)">
            <el-option v-for="a in accountOptions" :key="a.code" :label="a.code" :value="a.code" />
          </el-select>
          <span v-else>{{ row.accountCode }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目名称" width="130">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.accountName" size="small" filterable
            @change="(v: string) => updateCell(row.rowId, 'accountName', v)">
            <el-option v-for="a in accountOptions" :key="a.name" :label="a.name" :value="a.name" />
          </el-select>
          <span v-else>{{ row.accountName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="借方" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.debitAmount" :controls="false" size="small" style="width:100%"
            @change="(v: number) => updateCell(row.rowId, 'debitAmount', v ?? 0)" />
          <span v-else>{{ fmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.creditAmount" :controls="false" size="small" style="width:100%"
            @change="(v: number) => updateCell(row.rowId, 'creditAmount', v ?? 0)" />
          <span v-else>{{ fmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="90">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.entryType" size="small" @change="(v: string) => updateCell(row.rowId, 'entryType', v)">
            <el-option label="AJE" value="AJE" /><el-option label="RJE" value="RJE" />
          </el-select>
          <span v-else>{{ row.entryType }}</span>
        </template>
      </el-table-column>
      <el-table-column label="索引" width="80">
        <template #default="{ row }">
          <GtIndexChip v-if="row.indexRef" :value="row.indexRef" :context-project-id="projectId" />
          <el-input v-else-if="!isReadonly" :model-value="row.indexRef" size="small" @change="(v: string) => updateCell(row.rowId, 'indexRef', v)" />
        </template>
      </el-table-column>
      <el-table-column label="附注项目" width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.noteItem" size="small" @change="(v: string) => updateCell(row.rowId, 'noteItem', v)" />
          <span v-else>{{ row.noteItem }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="55">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="balance-bar" :class="{ unbalanced: !isBalanced }">
      借方合计 {{ fmt(debitTotal) }} | 贷方合计 {{ fmt(creditTotal) }} | 差额 {{ fmt(balanceDiff) }}
      <span v-if="!isBalanced"> — 借贷不平衡</span>
    </div>
  </div>
</template>

<style scoped>
.f2-tab-adjustment { font-size: var(--wp-font-size, 13px); padding: 12px; }
.f2-tab-adjustment :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f2-tab-adjustment :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.balance-bar { margin-top: 8px; text-align: right; font-weight: 600; }
.balance-bar.unbalanced { color: #f56c6c; }
</style>
