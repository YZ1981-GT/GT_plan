<template>
  <div class="gt-recycle-bin">
    <!-- 轻量标题栏（不用 GtPageHeader 的紫色横幅） -->
    <div class="gt-rb-header">
      <div class="gt-rb-title">
        <el-icon :size="20" style="color: #909399"><Delete /></el-icon>
        <h2>回收站</h2>
        <el-tag v-if="stats.total > 0" size="small" type="info" round>{{ stats.total }}</el-tag>
      </div>
      <div class="gt-rb-actions">
        <el-button
          v-if="stats.total > 0"
          type="danger"
          plain
          size="small"
          v-permission="'recycle:purge'"
          @click="confirmEmptyAll"
        >
          清空回收站
        </el-button>
      </div>
    </div>

    <!-- 超限警告 -->
    <el-alert
      v-if="stats.is_over_limit"
      type="error"
      :closable="false"
      show-icon
      style="margin-bottom: 12px"
      title="回收站已满"
      :description="`已存 ${stats.total} 条，超出上限 ${stats.limit} 条，请及时清理或恢复。`"
    />

    <!-- 类型筛选 Tab -->
    <div class="gt-rb-toolbar">
      <el-radio-group v-model="filterType" size="small" @change="onFilterChange">
        <el-radio-button value="">全部 ({{ stats.total }})</el-radio-button>
        <el-radio-button
          v-for="(info, key) in stats.by_type"
          :key="key"
          :value="key"
        >
          {{ info.label }} ({{ info.count }})
        </el-radio-button>
      </el-radio-group>
    </div>

    <!-- 列表 -->
    <el-table
      :data="items"
      size="small"
      v-loading="loading"
      style="width: 100%"
      :row-class-name="rowClassName"
      empty-text="回收站为空"
    >
      <el-table-column prop="type_label" label="类型" width="80" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="typeTagColor(row.type)" effect="plain">{{ row.type_label }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="名称" min-width="320" show-overflow-tooltip>
        <template #default="{ row }">
          <span class="gt-rb-name">{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="deleted_by_name" label="删除人" width="90" align="center" />
      <el-table-column prop="deleted_at" label="删除时间" width="150" sortable>
        <template #default="{ row }">
          <span class="gt-amt">{{ formatTime(row.deleted_at) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="剩余" width="70" align="center">
        <template #default="{ row }">
          <span :class="retentionClass(row.deleted_at)">{{ retentionDays(row.deleted_at) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="140" fixed="right" align="center">
        <template #default="{ row }">
          <el-button type="primary" size="small" link v-permission="'recycle:restore'" @click="restoreItem(row)">
            恢复
          </el-button>
          <el-button type="danger" size="small" link v-permission="'recycle:purge'" @click="confirmDelete(row)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div v-if="total > pageSize" class="gt-rb-pagination">
      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
        size="small"
        @current-change="loadItems"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { confirmDangerous } from '@/utils/confirm'
import {
  getRecycleBinStats, listRecycleBinItems,
  restoreRecycleBinItem, permanentDeleteItem, emptyRecycleBin,
} from '@/services/commonApi'
import { operationHistory } from '@/utils/operationHistory'
import { handleApiError } from '@/utils/errorHandler'

const loading = ref(false)
const items = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 50
const filterType = ref('')
const stats = reactive<{
  total: number
  limit: number
  is_over_limit: boolean
  by_type: Record<string, { label: string; count: number }>
}>({ total: 0, limit: 500, is_over_limit: false, by_type: {} })

async function loadStats() {
  try {
    const d = await getRecycleBinStats()
    stats.total = d.total
    stats.limit = d.limit
    stats.is_over_limit = d.is_over_limit
    stats.by_type = d.by_type || {}
  } catch { /* ignore */ }
}

async function loadItems() {
  loading.value = true
  try {
    const params: any = { page: page.value, page_size: pageSize }
    if (filterType.value) params.item_type = filterType.value
    const d = await listRecycleBinItems(params)
    items.value = d.items || []
    total.value = d.total || 0
  } catch { items.value = [] }
  finally { loading.value = false }
}

function onFilterChange() {
  page.value = 1
  loadItems()
}

async function restoreItem(row: any) {
  try {
    await restoreRecycleBinItem(`${row.type}/${row.id}`)
    ElMessage.success(`已恢复「${row.name}」`)
    await loadItems()
    await loadStats()
  } catch (e: any) {
    handleApiError(e, '恢复')
  }
}

async function confirmDelete(row: any) {
  try {
    await confirmDangerous(
      `永久删除「${row.name}」？此操作不可恢复。`,
      '永久删除',
    )
    await operationHistory.execute({
      description: `永久删除「${row.name}」`,
      execute: async () => {
        await permanentDeleteItem(`${row.type}/${row.id}`)
        await loadItems()
        await loadStats()
      },
      undo: async () => { throw new Error('不可撤销') },
    })
  } catch { /* cancelled */ }
}

async function confirmEmptyAll() {
  try {
    await confirmDangerous(
      `清空全部 ${stats.total} 条记录？此操作不可恢复。`,
      '清空回收站',
    )
    await operationHistory.execute({
      description: `清空回收站（${stats.total} 条）`,
      execute: async () => {
        await emptyRecycleBin()
        await loadItems()
        await loadStats()
      },
      undo: async () => { throw new Error('不可撤销') },
    })
  } catch { /* cancelled */ }
}

function formatTime(t: string | undefined) {
  if (!t) return '-'
  return new Date(t).toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  })
}

function retentionDays(deletedAt: string | undefined): string {
  if (!deletedAt) return '-'
  const remaining = 30 - Math.floor((Date.now() - new Date(deletedAt).getTime()) / 86400000)
  if (remaining <= 0) return '即将清理'
  return `${remaining}天`
}

function retentionClass(deletedAt: string | undefined): string {
  if (!deletedAt) return ''
  const remaining = 30 - Math.floor((Date.now() - new Date(deletedAt).getTime()) / 86400000)
  if (remaining <= 3) return 'gt-rb-retention--danger'
  if (remaining <= 7) return 'gt-rb-retention--warning'
  return ''
}

function typeTagColor(type: string): 'success' | 'warning' | 'info' | 'danger' {
  const m: Record<string, 'success' | 'warning' | 'info' | 'danger'> = {
    project: 'info', workpaper: 'success', attachment: 'info', adjustment: 'warning',
  }
  return m[type] || 'info'
}

function rowClassName({ row }: { row: any }): string {
  if (!row.deleted_at) return ''
  const remaining = 30 - Math.floor((Date.now() - new Date(row.deleted_at).getTime()) / 86400000)
  return remaining <= 3 ? 'gt-rb-row--expiring' : ''
}

onMounted(async () => {
  await loadStats()
  await loadItems()
})
</script>

<style scoped>
.gt-recycle-bin {
  padding: 20px 24px;
}

.gt-rb-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.gt-rb-title {
  display: flex;
  align-items: center;
  gap: 8px;
}
.gt-rb-title h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--gt-color-text, #303133);
}

.gt-rb-toolbar {
  margin-bottom: 12px;
}

.gt-rb-name {
  font-weight: 500;
  color: var(--gt-color-text, #303133);
}

.gt-rb-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.gt-rb-retention--danger {
  color: #f56c6c;
  font-weight: 600;
  font-size: 12px;
}
.gt-rb-retention--warning {
  color: #e6a23c;
  font-size: 12px;
}

:deep(.gt-rb-row--expiring) {
  background: #fef8f8 !important;
}
:deep(.gt-rb-row--expiring:hover > td) {
  background: #fef0f0 !important;
}
</style>
