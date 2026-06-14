<!--
  TrialBalanceFullView — TB 完整视图（简洁/完整切换）

  完整模式显示：未审+AJE+RJE+其他=审定 分列；简洁模式仅显示未审+审定。
  Requirements: 1.1, 1.5
-->
<template>
  <div class="tb-full-view">
    <div class="tb-full-view__toolbar">
      <el-switch v-model="fullMode" active-text="完整视图" inactive-text="简洁" />
      <el-tag v-if="balanceCheck" :type="balanceCheck.balanced ? 'success' : 'danger'" size="small">
        {{ balanceCheck.balanced ? '试算平衡 ✓' : `差额 ${balanceCheck.difference}` }}
      </el-tag>
    </div>

    <el-table :data="rows" border class="gt-compact-table" max-height="600">
      <el-table-column prop="account_code" label="科目编码" width="100" />
      <el-table-column prop="account_name" label="科目名称" min-width="150" />
      <el-table-column prop="unadjusted" label="未审数" width="120" align="right" />
      <el-table-column v-if="fullMode" prop="aje_adjustment" label="AJE调整" width="110" align="right" />
      <el-table-column v-if="fullMode" prop="rje_adjustment" label="RJE调整" width="110" align="right" />
      <el-table-column v-if="fullMode" prop="other_adjustment" label="其他调整" width="110" align="right" />
      <el-table-column prop="audited" label="审定数" width="120" align="right" />
      <el-table-column v-if="fullMode" prop="balance_ok" label="平衡" width="60" align="center">
        <template #default="{ row }">
          <span :class="row.balance_ok ? 'text-success' : 'text-danger'">
            {{ row.balance_ok ? '✓' : '✗' }}
          </span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/services/apiProxy'

const props = defineProps<{
  projectId: string
  year: number
}>()

const fullMode = ref(false)
const rows = ref<any[]>([])
const balanceCheck = ref<any>(null)

async function loadData() {
  try {
    const [view, check] = await Promise.all([
      api.get(`/api/workpapers/${props.projectId}/${props.year}/full-tb`),
      api.get(`/api/workpapers/${props.projectId}/${props.year}/tb-balance-check`),
    ])
    rows.value = view as any[]
    balanceCheck.value = check
  } catch { /* 降级 */ }
}

onMounted(loadData)

defineExpose({ loadData, fullMode })
</script>

<style scoped>
.tb-full-view__toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.text-success { color: #67c23a; }
.text-danger { color: #f56c6c; }
</style>
