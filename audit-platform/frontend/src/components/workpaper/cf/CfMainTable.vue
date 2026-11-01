<template>
  <div class="cf-main-table">
    <el-button type="primary" size="small" :loading="loading" @click="fetchData">刷新逆算</el-button>
    <el-table v-if="items.length" :data="items" class="gt-compact-table" style="margin-top: 12px">
      <el-table-column prop="section" label="活动" width="80">
        <template #default="{ row }">
          {{ sectionLabel(row.section) }}
        </template>
      </el-table-column>
      <el-table-column prop="item" label="项目" min-width="200" />
      <el-table-column prop="row_code" label="行号" width="90" />
      <el-table-column prop="reported" label="报表值" align="right" width="130" />
      <el-table-column prop="calculated" label="逆算值" align="right" width="130">
        <template #default="{ row }">
          {{ row.calculated !== null ? row.calculated : '—' }}
        </template>
      </el-table-column>
      <el-table-column prop="difference" label="差异" align="right" width="130">
        <template #default="{ row }">
          <span :class="{ 'cf-diff-warn': row.difference !== null && !row.pass }">
            {{ row.difference !== null ? row.difference : '—' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.calculated !== null" :type="row.pass ? 'success' : 'danger'" size="small">
            {{ row.pass ? '通过' : '异常' }}
          </el-tag>
          <el-tag v-else type="info" size="small">人工</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="含税容差" width="80" align="center">
        <template #default="{ row }">
          <el-icon v-if="row.has_vat_tolerance" color="var(--el-color-warning)"><WarningFilled /></el-icon>
        </template>
      </el-table-column>
      <el-table-column label="差异说明" min-width="160">
        <template #default="{ row }">
          <el-input
            v-if="row.difference !== null && !row.pass"
            v-model="row._explanation"
            size="small"
            placeholder="填写差异原因"
            @blur="saveExplanation(row)"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="110" align="center">
        <template #default="{ row }">
          <el-button
            v-if="row.difference !== null && !row.pass"
            type="primary"
            link
            size="small"
            @click="createAdjustment(row)"
          >创建调整</el-button>
        </template>
      </el-table-column>
    </el-table>
    <AdjustmentEntryDialog
      ref="entryDialogRef"
      :project-id="projectId"
      :year="year"
      :account-options="accountOptions"
      :accounts-ready="accountsReady"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { WarningFilled } from '@element-plus/icons-vue'
import AdjustmentEntryDialog from '@/components/adjustment/AdjustmentEntryDialog.vue'
import { getAccountDropdown, type AccountOption } from '@/services/auditPlatformApi'
import { apiProxy } from '@/utils/apiProxy'

const props = defineProps<{ projectId: string; year: number }>()
const loading = ref(false)
const items = ref<any[]>([])
const accountOptions = ref<AccountOption[]>([])
const accountsReady = ref(false)
const entryDialogRef = ref<InstanceType<typeof AdjustmentEntryDialog> | null>(null)

function sectionLabel(s: string) {
  const map: Record<string, string> = { operating: '经营', investing: '投资', financing: '筹资' }
  return map[s] || s
}

async function fetchData() {
  loading.value = true
  try {
    items.value = await apiProxy.get(`/api/projects/${props.projectId}/cf-verification/${props.year}/main-table`)
    // Initialize explanation field
    items.value.forEach((item: any) => { item._explanation = item._explanation || '' })
  } finally {
    loading.value = false
  }
}

async function fetchAccountOptions() {
  accountsReady.value = false
  try {
    accountOptions.value = await getAccountDropdown(props.projectId, undefined, props.year)
    accountsReady.value = true
  } catch {
    accountOptions.value = []
  }
}

async function saveExplanation(row: any) {
  if (!row._explanation) return
  await apiProxy.post(`/api/projects/${props.projectId}/cf-verification/${props.year}/explanation`, {
    check_type: 'main_table',
    item_code: row.row_code,
    explanation: row._explanation,
  })
}

function createAdjustment(row: any) {
  entryDialogRef.value?.openCreate({
    description: `现金流量表核查差异：${row.item}（${row.row_code}）`,
    problems: [
      `来源：现金流量表核查；差异金额 ${row.difference} 仅供核查。请手工选择完整借贷科目和方向，系统不会自动推断。`,
    ],
  })
}

onMounted(async () => {
  await Promise.all([fetchData(), fetchAccountOptions()])
})
</script>

<style scoped>
.cf-diff-warn { color: var(--el-color-danger); font-weight: bold; }
</style>
