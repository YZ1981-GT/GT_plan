<template>
  <div class="gt-oplogs gt-fade-in">
    <GtPageHeader title="操作日志" :show-back="false">
      <div class="gt-oplogs-header-actions">
        <el-button :loading="loading" @click="fetchLogs">刷新</el-button>
      </div>
    </GtPageHeader>

    <!-- 筛选栏 -->
    <div class="gt-oplogs-filter">
      <el-date-picker
        v-model="timeRange"
        type="datetimerange"
        range-separator="至"
        start-placeholder="开始时间"
        end-placeholder="结束时间"
        value-format="YYYY-MM-DDTHH:mm:ss"
        style="width: 360px"
      />
      <el-select v-model="filterType" placeholder="全部类型" clearable style="width: 150px">
        <el-option v-for="opt in TYPE_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
      </el-select>
      <el-select v-model="filterDept" placeholder="全部部门" clearable filterable style="width: 170px">
        <el-option v-for="d in departments" :key="d.id" :label="d.name" :value="d.id" />
      </el-select>
      <el-input
        v-model="keyword"
        placeholder="搜索账号或人名"
        clearable
        style="width: 200px"
        :prefix-icon="Search"
        @keyup.enter="onSearch"
      />
      <el-button type="primary" @click="onSearch">查询</el-button>
      <span class="gt-oplogs-count">共 {{ total }} 条</span>
    </div>

    <!-- 日志表格 -->
    <el-card shadow="never" class="gt-oplogs-card">
      <el-table :data="rows" v-loading="loading" style="width: 100%" size="default">
        <el-table-column label="时间" width="170">
          <template #default="{ row }">
            <span style="color: var(--el-text-color-secondary)">{{ fmtDateTime(row.ts) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="typeTag(row.type)" size="small" effect="light">{{ typeLabel(row.type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="full_name" label="人名" min-width="100">
          <template #default="{ row }">
            <span>{{ row.full_name || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="username" label="账号" min-width="120">
          <template #default="{ row }">
            <span style="color: var(--el-text-color-secondary)">{{ row.username || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="dept_name" label="部门" min-width="110">
          <template #default="{ row }">
            <span style="color: var(--el-text-color-secondary)">{{ row.dept_name || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="detail" label="对象" min-width="120">
          <template #default="{ row }">
            <span style="color: var(--el-text-color-secondary)">{{ row.detail || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="ip" label="IP" width="140">
          <template #default="{ row }">
            <span class="gt-oplogs-ip">{{ row.ip || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        style="margin-top: 14px; justify-content: flex-end"
        @current-change="fetchLogs"
        @size-change="onPageSizeChange"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * 操作日志页（spec operation-log-and-last-login，仅 admin）
 *
 * 数据源 = GET /api/system/operation-logs（后端合并 sys_login_log 与 logs）。
 * 类型筛选与后端白名单同源：success/failed/locked/logout + create/update/delete。
 */
import { ref, onMounted } from 'vue'
import { Search } from '@element-plus/icons-vue'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import { api } from '@/services/apiProxy'
import { operationLogs } from '@/services/apiPaths/system'
import { listDepartments } from '@/services/commonApi'
import { fmtDateTime } from '@/utils/formatters'
import { handleApiError } from '@/utils/errorHandler'

const TYPE_OPTIONS = [
  { value: 'success', label: '登录成功' },
  { value: 'failed', label: '登录失败' },
  { value: 'locked', label: '账号锁定' },
  { value: 'logout', label: '登出' },
  { value: 'create', label: '新建' },
  { value: 'update', label: '更新' },
  { value: 'delete', label: '删除' },
] as const

const TYPE_LABEL: Record<string, string> = Object.fromEntries(TYPE_OPTIONS.map(o => [o.value, o.label]))

function typeLabel(t: string): string {
  return TYPE_LABEL[t] || t
}

function typeTag(t: string): 'success' | 'danger' | 'warning' | 'info' | 'primary' {
  if (t === 'success') return 'success'
  if (t === 'failed' || t === 'locked') return 'danger'
  if (t === 'logout') return 'info'
  if (t === 'delete') return 'warning'
  return 'primary'
}

const rows = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)

const timeRange = ref<[string, string] | null>(null)
const filterType = ref('')
const filterDept = ref('')
const keyword = ref('')

const departments = ref<any[]>([])

async function fetchLogs() {
  loading.value = true
  try {
    const params: Record<string, unknown> = {
      page: page.value,
      page_size: pageSize.value,
    }
    if (timeRange.value) {
      params.from = timeRange.value[0]
      params.to = timeRange.value[1]
    }
    if (filterType.value) params.type = filterType.value
    if (filterDept.value) params.dept_id = filterDept.value
    if (keyword.value.trim()) params.keyword = keyword.value.trim()
    const data = await api.get(operationLogs.list, { params, _dedupe: false } as any)
    rows.value = data?.items ?? []
    total.value = data?.total ?? 0
  } catch (e) {
    rows.value = []
    total.value = 0
    handleApiError(e, '加载操作日志失败')
  } finally {
    loading.value = false
  }
}

function onSearch() {
  page.value = 1
  fetchLogs()
}

function onPageSizeChange() {
  page.value = 1
  fetchLogs()
}

onMounted(() => {
  fetchLogs()
  listDepartments().then(list => { departments.value = list }).catch(() => { departments.value = [] })
})
</script>

<style scoped>
.gt-oplogs-filter {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.gt-oplogs-count {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.gt-oplogs-ip {
  font-family: monospace;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
