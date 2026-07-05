<template>
  <div class="g5-adjustment">
    <!-- 借贷平衡提示 -->
    <div v-if="!adj.isBalanced.value" class="balance-alert">
      <el-alert type="error" :closable="false">
        借贷不平衡！差额：{{ fmt(adj.balanceDiff.value) }}
      </el-alert>
    </div>

    <div class="toolbar">
      <el-button size="small" type="primary" plain @click="adj.addEntry()" :disabled="props.readonly">
        + 新增分录
      </el-button>
      <span class="totals">
        借方合计: {{ fmt(adj.debitTotal.value) }} | 贷方合计: {{ fmt(adj.creditTotal.value) }}
      </span>
    </div>

    <el-table :data="adj.entries.value" border stripe style="width: 100%; font-size: 13px" :height="420">
      <el-table-column type="index" label="序号" width="50" />
      <el-table-column prop="entryType" label="类型" width="70">
        <template #default="{ row }">
          <el-select v-model="row.entryType" size="small" :disabled="props.readonly">
            <el-option label="AJE" value="AJE" />
            <el-option label="RJE" value="RJE" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column prop="date" label="日期" width="100">
        <template #default="{ row }">
          <el-input v-model="row.date" size="small" :disabled="props.readonly" />
        </template>
      </el-table-column>
      <el-table-column prop="summary" label="摘要" min-width="120">
        <template #default="{ row }">
          <el-input v-model="row.summary" size="small" :disabled="props.readonly" />
        </template>
      </el-table-column>
      <el-table-column prop="accountCode" label="科目代码" width="80" />
      <el-table-column prop="accountName" label="科目名称" min-width="100" />
      <el-table-column prop="debitAmount" label="借方金额" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.debitAmount" size="small" :controls="false" :disabled="props.readonly" />
        </template>
      </el-table-column>
      <el-table-column prop="creditAmount" label="贷方金额" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.creditAmount" size="small" :controls="false" :disabled="props.readonly" />
        </template>
      </el-table-column>
      <el-table-column prop="preparedBy" label="编制人" width="80" />
      <el-table-column prop="remark" label="备注" min-width="80" />
      <el-table-column label="操作" width="60" v-if="!props.readonly">
        <template #default="{ row }">
          <el-button size="small" type="danger" link @click="adj.removeEntry(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { useG5Adjustment } from '../../composables/useG5Adjustment'

const props = defineProps<{
  htmlData?: any
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const adj = useG5Adjustment()

function fmt(v: number): string {
  return v?.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) ?? '-'
}
</script>

<style scoped>
.g5-adjustment { font-size: 13px; }
.balance-alert { margin-bottom: 8px; }
.toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.totals { font-size: 12px; color: #606266; margin-left: auto; }
</style>
