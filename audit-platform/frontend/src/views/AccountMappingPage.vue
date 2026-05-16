<template>
  <div class="gt-mapping-page gt-fade-in">
    <GtPageHeader title="科目映射" @back="$router.push(`/projects/${projectId}/trial-balance`)">
      <template #actions>
        <el-button type="primary" :loading="autoMatchLoading" @click="onAutoMatch">
          🔄 自动匹配
        </el-button>
        <el-button @click="fetchData" :loading="loading">刷新</el-button>
      </template>
    </GtPageHeader>

    <!-- 完成率进度条 -->
    <div class="gt-mapping-summary">
      <div class="gt-mapping-summary__rate">
        <span class="gt-mapping-summary__label">映射完成率</span>
        <el-progress
          :percentage="completionRate"
          :stroke-width="16"
          :format="(pct: number) => `${pct.toFixed(1)}%`"
          :color="completionRate >= 80 ? '#67c23a' : completionRate >= 50 ? '#e6a23c' : '#f56c6c'"
          style="width: 300px; display: inline-flex; margin: 0 16px"
        />
        <span class="gt-mapping-summary__stats">
          已映射 {{ mappedCount }} / {{ totalCount }} 个科目
        </span>
      </div>
    </div>

    <!-- 映射列表 -->
    <el-table
      :data="filteredMappings"
      v-loading="loading"
      stripe
      border
      style="width: 100%"
      max-height="calc(100vh - 260px)"
      :default-sort="{ prop: 'original_account_code', order: 'ascending' }"
    >
      <el-table-column prop="original_account_code" label="客户科目编码" width="160" sortable>
        <template #default="{ row }">
          <span class="gt-amt">{{ row.original_account_code }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="original_account_name" label="客户科目名称" min-width="180" />
      <el-table-column prop="standard_account_code" label="标准科目编码" width="160" sortable>
        <template #default="{ row }">
          <span class="gt-amt">{{ row.standard_account_code || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="standard_account_name" label="标准科目名称" min-width="180">
        <template #default="{ row }">
          {{ row.standard_account_name || '—' }}
        </template>
      </el-table-column>
      <el-table-column prop="match_method" label="映射方式" width="120" align="center">
        <template #default="{ row }">
          <el-tag
            :type="row.match_method === 'auto' ? 'success' : row.match_method === 'manual' ? 'warning' : 'info'"
            size="small"
          >
            {{ row.match_method === 'auto' ? '自动' : row.match_method === 'manual' ? '手动' : row.match_method || '未映射' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100" align="center" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="onEdit(row)">编辑</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 手动编辑对话框 -->
    <el-dialog v-model="editDialogVisible" title="编辑科目映射" width="500px" destroy-on-close>
      <el-form :model="editForm" label-width="120px">
        <el-form-item label="客户科目编码">
          <el-input :model-value="editForm.original_account_code" disabled />
        </el-form-item>
        <el-form-item label="客户科目名称">
          <el-input :model-value="editForm.original_account_name" disabled />
        </el-form-item>
        <el-form-item label="标准科目编码">
          <el-input v-model="editForm.standard_account_code" placeholder="输入标准科目编码" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saveLoading" @click="onSaveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { accountMapping } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import GtPageHeader from '@/components/common/GtPageHeader.vue'

const route = useRoute()
const projectId = computed(() => route.params.projectId as string || route.params.id as string)

const loading = ref(false)
const autoMatchLoading = ref(false)
const saveLoading = ref(false)
const mappings = ref<any[]>([])
const completionRate = ref(0)
const totalCount = ref(0)
const mappedCount = ref(0)

const editDialogVisible = ref(false)
const editForm = ref({
  id: '',
  original_account_code: '',
  original_account_name: '',
  standard_account_code: '',
})

const filteredMappings = computed(() => mappings.value)

async function fetchData() {
  loading.value = true
  try {
    const [listData, rateData] = await Promise.all([
      api.get(accountMapping.list(projectId.value)),
      api.get(accountMapping.completionRate(projectId.value)),
    ])

    // Process list
    const list = Array.isArray(listData) ? listData : (listData?.data || listData?.items || [])
    mappings.value = list

    // Process completion rate
    const rate = rateData?.data || rateData
    if (rate) {
      completionRate.value = typeof rate.completion_rate === 'number'
        ? rate.completion_rate
        : typeof rate.rate === 'number'
          ? rate.rate
          : 0
      totalCount.value = rate.total_client || rate.total || list.length
      mappedCount.value = rate.mapped || rate.matched || Math.round(list.length * completionRate.value / 100)
    }
  } catch (e: any) {
    handleApiError(e, '获取映射数据失败')
  } finally {
    loading.value = false
  }
}

async function onAutoMatch() {
  autoMatchLoading.value = true
  try {
    const result = await api.post(accountMapping.autoMatch(projectId.value))
    const data = result?.data || result
    ElMessage.success(`自动匹配完成：已匹配 ${data?.saved || data?.matched || 0} 个科目`)
    await fetchData()
  } catch (e: any) {
    handleApiError(e, '自动匹配失败')
  } finally {
    autoMatchLoading.value = false
  }
}

function onEdit(row: any) {
  editForm.value = {
    id: row.id || '',
    original_account_code: row.original_account_code || '',
    original_account_name: row.original_account_name || '',
    standard_account_code: row.standard_account_code || '',
  }
  editDialogVisible.value = true
}

async function onSaveEdit() {
  if (!editForm.value.standard_account_code) {
    ElMessage.warning('请输入标准科目编码')
    return
  }
  saveLoading.value = true
  try {
    if (editForm.value.id) {
      // Update existing mapping
      await api.put(accountMapping.detail(projectId.value, editForm.value.id), {
        standard_account_code: editForm.value.standard_account_code,
      })
    } else {
      // Create new mapping
      await api.post(accountMapping.create(projectId.value), {
        original_account_code: editForm.value.original_account_code,
        standard_account_code: editForm.value.standard_account_code,
      })
    }
    ElMessage.success('映射保存成功')
    editDialogVisible.value = false
    await fetchData()
  } catch (e: any) {
    handleApiError(e, '保存映射失败')
  } finally {
    saveLoading.value = false
  }
}

onMounted(() => {
  fetchData()
})
</script>

<style scoped>
.gt-mapping-page {
  padding: 0 16px 16px;
}

.gt-mapping-summary {
  margin: 12px 0;
  padding: 12px 16px;
  background: var(--gt-color-bg);
  border-radius: 8px;
  display: flex;
  align-items: center;
}

.gt-mapping-summary__rate {
  display: flex;
  align-items: center;
  gap: 8px;
}

.gt-mapping-summary__label {
  font-weight: 600;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-primary);
  white-space: nowrap;
}

.gt-mapping-summary__stats {
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-regular);
  white-space: nowrap;
}
</style>
