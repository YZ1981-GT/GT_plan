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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { WarningFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { apiProxy } from '@/utils/apiProxy'

const props = defineProps<{ projectId: string; year: number }>()
const loading = ref(false)
const items = ref<any[]>([])

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

async function saveExplanation(row: any) {
  if (!row._explanation) return
  await apiProxy.post(`/api/projects/${props.projectId}/cf-verification/${props.year}/explanation`, {
    check_type: 'main_table',
    item_code: row.row_code,
    explanation: row._explanation,
  })
}

async function createAdjustment(row: any) {
  try {
    const res = await apiProxy.post(`/api/projects/${props.projectId}/cf-verification/${props.year}/create-adjustment`, {
      item_code: row.row_code,
      difference: row.difference,
      description: `CF核查差异调整 ${row.item}`,
    })
    if (res.success) {
      ElMessage.success(`已创建 CF 调整分录 ${res.adjustment_no}`)
    } else {
      ElMessage.warning(res.error || '创建失败')
    }
  } catch {
    ElMessage.error('创建调整分录失败')
  }
}

onMounted(fetchData)
</script>

<style scoped>
.cf-diff-warn { color: var(--el-color-danger); font-weight: bold; }
</style>
