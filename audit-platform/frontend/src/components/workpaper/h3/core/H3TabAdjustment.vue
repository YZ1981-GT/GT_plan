<template>
  <div class="h3-tab-adjustment">
    <!-- 操作栏 -->
    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 新增调整分录</el-button>
      <el-button size="small" :disabled="!isBalanced" @click="publishAdjustment">发布至H3-1</el-button>
      <el-button size="small" @click="pushToA13()">推送A13</el-button>
      <el-dropdown size="small" class="export-dropdown">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item>导出模板</el-dropdown-item>
            <el-dropdown-item>导出数据</el-dropdown-item>
            <el-dropdown-item>导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <!-- 分录表 -->
    <el-table :data="rows" border size="small" class="audit-table">
      <el-table-column prop="seq" label="序号" width="55" align="center" />
      <el-table-column prop="description" label="调整事项说明" min-width="160">
        <template #default="{ row, $index }">
          <el-input v-model="row.description" size="small" :disabled="isReadonly" @change="updateCell($index, 'description', row.description)" />
        </template>
      </el-table-column>
      <el-table-column prop="entryType" label="类别" width="80" align="center">
        <template #default="{ row, $index }">
          <el-select v-model="row.entryType" size="small" :disabled="isReadonly" @change="updateCell($index, 'entryType', row.entryType)">
            <el-option label="AJE" value="AJE" />
            <el-option label="RJE" value="RJE" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column prop="accountCode" label="科目代码" width="90">
        <template #default="{ row, $index }">
          <el-input v-model="row.accountCode" size="small" :disabled="isReadonly" @change="updateCell($index, 'accountCode', row.accountCode)" />
        </template>
      </el-table-column>
      <el-table-column prop="accountName" label="科目名称" min-width="120">
        <template #default="{ row, $index }">
          <el-input v-model="row.accountName" size="small" :disabled="isReadonly" @change="updateCell($index, 'accountName', row.accountName)" />
        </template>
      </el-table-column>
      <el-table-column prop="summary" label="摘要" min-width="120">
        <template #default="{ row, $index }">
          <el-input v-model="row.summary" size="small" :disabled="isReadonly" @change="updateCell($index, 'summary', row.summary)" />
        </template>
      </el-table-column>
      <el-table-column prop="debitAmount" label="借方金额" min-width="110" align="right">
        <template #default="{ row, $index }">
          <el-input v-model.number="row.debitAmount" size="small" :disabled="isReadonly" @change="updateCell($index, 'debitAmount', row.debitAmount)" />
        </template>
      </el-table-column>
      <el-table-column prop="creditAmount" label="贷方金额" min-width="110" align="right">
        <template #default="{ row, $index }">
          <el-input v-model.number="row.creditAmount" size="small" :disabled="isReadonly" @change="updateCell($index, 'creditAmount', row.creditAmount)" />
        </template>
      </el-table-column>
      <el-table-column prop="indexRef" label="索引" width="80">
        <template #default="{ row, $index }">
          <el-input v-model="row.indexRef" size="small" :disabled="isReadonly" @change="updateCell($index, 'indexRef', row.indexRef)" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" align="center">
        <template #default="{ $index }">
          <el-button size="small" type="danger" text :disabled="isReadonly" @click="removeRow($index)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 借贷合计+平衡校验 -->
    <div class="balance-row">
      <span>借方合计：<b>{{ fmtNum(debitTotal) }}</b></span>
      <span>贷方合计：<b>{{ fmtNum(creditTotal) }}</b></span>
      <el-tag :type="isBalanced ? 'success' : 'danger'" size="small">
        {{ isBalanced ? '借贷平衡 ✓' : '借贷不平衡 ✗' }}
      </el-tag>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabAdjustment.vue — H3-3 调整分录
 * el-table 10列+借贷平衡+推送A13
 */
import { computed, inject, toRef } from 'vue'
import { useH3Adjustment } from '../../composables/useH3Adjustment'
import { useH3FormData } from '../../composables/useH3FormData'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const { getValue, setValue, saveImmediate } = useH3FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: computed(() => 'cost') as any,
})

const {
  rows, debitTotal, creditTotal, isBalanced, addRow, removeRow, updateCell, publishAdjustment, pushToA13,
} = useH3Adjustment({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  getValue, setValue, saveImmediate,
})

function fmtNum(v: number): string {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h3-tab-adjustment { padding: 16px; font-size: 13px; }
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.audit-table { font-size: 13px; }
.balance-row { display: flex; align-items: center; gap: 16px; margin-top: 12px; padding: 8px 12px; background: var(--el-fill-color-lighter); border-radius: 4px; }
.export-dropdown { margin-left: auto; }
</style>
