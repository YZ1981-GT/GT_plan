<template>
  <div class="gt-consol-trial-view">
    <div class="section-header">
      <el-button @click="onCheck" :loading="checkLoading">一致性校验</el-button>
      <el-button @click="onRecalc" :loading="recalcLoading">全量重算</el-button>
    </div>

    <el-alert
      v-if="store.consistencyResult"
      :type="store.consistencyResult.is_balanced ? 'success' : 'warning'"
      :title="store.consistencyResult.is_balanced ? '数据一致' : `借贷不平衡，差额: ${store.consistencyResult.difference}`"
      show-icon
      style="margin-bottom: 12px"
    />

    <el-table
      :data="store.consolTrial"
      v-loading="store.loading"
      border
      stripe
      size="small"
      max-height="600"
    >
      <el-table-column prop="entity_name" label="子公司" width="160" fixed />
      <el-table-column prop="account_code" label="科目代码" width="120" />
      <el-table-column prop="account_name" label="科目名称" min-width="160" />
      <el-table-column prop="local_amount" label="本地金额" width="140" align="right">
        <template #default="{ row }">{{ formatNum(row.local_amount) }}</template>
      </el-table-column>
      <el-table-column prop="currency" label="币种" width="80" />
      <el-table-column prop="exchange_rate" label="汇率" width="100" align="right" />
      <el-table-column prop="consolidation_amount" label="折算金额" width="140" align="right">
        <template #default="{ row }">{{ formatNum(row.consolidation_amount) }}</template>
      </el-table-column>
      <el-table-column prop="consolidation_adjustment" label="合并调整" width="140" align="right">
        <template #default="{ row }">
          <el-input-number
            v-model="row.consolidation_adjustment"
            :precision="2"
            size="small"
            controls-position="right"
            @change="onAdjChange(row)"
          />
        </template>
      </el-table-column>
      <el-table-column prop="final_amount" label="最终金额" width="140" align="right">
        <template #default="{ row }">{{ formatNum(row.final_amount) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="80" fixed="right">
        <template #default="{ row }">
          <el-button type="danger" size="small" text @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useConsolidationStore } from '@/stores/consolidation'
import { updateConsolTrialRow, deleteConsolTrialRow, recalcConsolTrial, checkConsolTrialConsistency } from '@/services/consolidationApi'
import type { ConsolTrialRow } from '@/services/consolidationApi'

const props = defineProps<{ projectId: string; year: number }>()
const store = useConsolidationStore()
const checkLoading = ref(false)
const recalcLoading = ref(false)

function formatNum(v: string | null) {
  if (!v) return '—'
  const n = Number(v)
  return isNaN(n) ? v : n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function onAdjChange(row: ConsolTrialRow) {
  try {
    await updateConsolTrialRow(row.id, props.projectId, { consolidation_adjustment: row.consolidation_adjustment })
    ElMessage.success('保存成功')
  } catch {
    ElMessage.error('保存失败')
  }
}

async function onDelete(row: ConsolTrialRow) {
  try {
    await deleteConsolTrialRow(row.id, props.projectId)
    store.consolTrial = store.consolTrial.filter(r => r.id !== row.id)
    ElMessage.success('删除成功')
  } catch {
    ElMessage.error('删除失败')
  }
}

async function onCheck() {
  checkLoading.value = true
  try {
    store.consistencyResult = await checkConsolTrialConsistency(props.projectId, props.year)
  } finally {
    checkLoading.value = false
  }
}

async function onRecalc() {
  recalcLoading.value = true
  try {
    store.consolTrial = await recalcConsolTrial(props.projectId, props.year)
    ElMessage.success('重算完成')
  } finally {
    recalcLoading.value = false
  }
}

onMounted(() => store.fetchConsolTrial(props.projectId, props.year))
</script>

<style scoped>
.gt-consol-trial-view {
  display: flex;
  flex-direction: column;
  gap: var(--gt-space-3);
}
.section-header {
  display: flex;
  gap: var(--gt-space-2);
}
</style>
