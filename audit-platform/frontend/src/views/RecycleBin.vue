<template>
  <div class="gt-recycle-bin">
    <GtPageHeader title="回收站" :show-back="false">
      <template #actions>
        <el-button
          type="danger"
          plain
          size="small"
          :disabled="stats.total === 0"
          @click="confirmEmptyAll"
        >
          <el-icon><Delete /></el-icon> 清空回收站
        </el-button>
      </template>
    </GtPageHeader>

    <!-- 统计卡片 -->
    <div class="gt-recycle-stats">
      <div class="gt-recycle-stat-card">
        <div class="gt-recycle-stat-num" :class="{ 'gt-recycle-stat-num--danger': stats.is_over_limit }">
          {{ stats.total }}
        </div>
        <div class="gt-recycle-stat-label">已删除项目</div>
      </div>
      <div class="gt-recycle-stat-card" v-for="(info, key) in stats.by_type" :key="key">
        <div class="gt-recycle-stat-num">{{ info.count }}</div>
        <div class="gt-recycle-stat-label">{{ info.label }}</div>
      </div>
    </div>

    <!-- 超限警告 -->
    <el-alert
      v-if="stats.is_over_limit"
      type="error"
      :closable="false"
      show-icon
      style="margin-bottom: 16px"
    >
      <template #title>回收站已超出上限（{{ stats.total }}/{{ stats.limit }}），请及时清理</template>
    </el-alert>

    <!-- 类型筛选 -->
    <div class="gt-recycle-toolbar">
      <el-radio-group v-model="filterType" size="small" @change="loadItems">
        <el-radio-button value="">全部</el-radio-button>
        <el-radio-button
          v-for="(info, key) in stats.by_type"
          :key="key"
          :value="key"
        >
          {{ info.label }} ({{ info.count }})
        </el-radio-button>
      </el-radio-group>
      <div style="flex: 1" />
      <el-tag type="info" size="small">{{ total }} 条记录</el-tag>
    </div>

    <!-- 列表 -->
    <el-table
      :data="items"
      stripe
      border
      size="small"
      v-loading="loading"
      empty-text="回收站为空，没有已删除的项目"
      style="width: 100%"
      :row-class-name="rowClassName"
    >
      <el-table-column prop="type_label" label="类型" width="100" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="typeTagColor(row.type)">{{ row.type_label }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="名称" min-width="300" show-overflow-tooltip>
        <template #default="{ row }">
          <span style="font-weight: 500">{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="deleted_by_name" label="删除人" width="100" />
      <el-table-column prop="deleted_at" label="删除时间" width="170" sortable>
        <template #default="{ row }">
          <span class="gt-amt">{{ formatTime(row.deleted_at) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="剩余保留" width="100" align="center">
        <template #default="{ row }">
          <span :class="retentionClass(row.deleted_at)">{{ retentionDays(row.deleted_at) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right" align="center">
        <template #default="{ row }">
          <el-button type="primary" size="small" text v-permission="'recycle:restore'" @click="restoreItem(row)">
            恢复
          </el-button>
          <el-button type="danger" size="small" text v-permission="'recycle:purge'" @click="confirmDelete(row)">
            永久删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div v-if="total > pageSize" class="gt-recycle-pagination">
      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="sizes, total, prev, pager, next, jumper"
        :page-sizes="[20, 50, 100]"
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

async function restoreItem(row: any) {
  try {
    await restoreRecycleBinItem(`${row.type}/${row.id}`)
    ElMessage.success(`${row.type_label}「${row.name}」已恢复`)
    await loadItems()
    await loadStats()
  } catch (e: any) {
    handleApiError(e, '恢复')
  }
}

async function confirmDelete(row: any) {
  try {
    await confirmDangerous(
      `确定要永久删除${row.type_label}「${row.name}」吗？此操作不可恢复。`,
      '永久删除',
    )
    await operationHistory.execute({
      description: `永久删除${row.type_label}「${row.name}」`,
      execute: async () => {
        await permanentDeleteItem(`${row.type}/${row.id}`)
        await loadItems()
        await loadStats()
      },
      undo: async () => {
        throw new Error('永久删除操作不可撤销')
      },
    })
  } catch { /* cancelled */ }
}

async function confirmEmptyAll() {
  try {
    await confirmDangerous(
      `确定要清空回收站中的所有 ${stats.total} 条记录吗？此操作不可恢复。`,
      '清空回收站',
    )
    await operationHistory.execute({
      description: `清空回收站（${stats.total} 条记录）`,
      execute: async () => {
        await emptyRecycleBin()
        await loadItems()
        await loadStats()
      },
      undo: async () => {
        throw new Error('清空回收站操作不可撤销')
      },
    })
  } catch { /* cancelled */ }
}

function formatTime(t: string | undefined) {
  if (!t) return '-'
  return new Date(t).toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

/** 计算剩余保留天数（默认 30 天自动清理） */
function retentionDays(deletedAt: string | undefined): string {
  if (!deletedAt) return '-'
  const deleted = new Date(deletedAt).getTime()
  const now = Date.now()
  const remaining = 30 - Math.floor((now - deleted) / 86400000)
  if (remaining <= 0) return '即将清理'
  return `${remaining} 天`
}

function retentionClass(deletedAt: string | undefined): string {
  if (!deletedAt) return ''
  const deleted = new Date(deletedAt).getTime()
  const remaining = 30 - Math.floor((Date.now() - deleted) / 86400000)
  if (remaining <= 3) return 'gt-retention--danger'
  if (remaining <= 7) return 'gt-retention--warning'
  return 'gt-retention--normal'
}

function typeTagColor(type: string): '' | 'success' | 'warning' | 'info' | 'danger' {
  const m: Record<string, '' | 'success' | 'warning' | 'info' | 'danger'> = {
    project: '',
    workpaper: 'success',
    attachment: 'info',
    adjustment: 'warning',
  }
  return m[type] || 'info'
}

function rowClassName({ row }: { row: any }): string {
  if (!row.deleted_at) return ''
  const remaining = 30 - Math.floor((Date.now() - new Date(row.deleted_at).getTime()) / 86400000)
  if (remaining <= 3) return 'gt-row--expiring'
  return ''
}

onMounted(async () => {
  await loadStats()
  await loadItems()
})
</script>

<style scoped>
.gt-recycle-bin {
  padding: var(--gt-space-4, 16px);
}

/* 统计卡片 */
.gt-recycle-stats {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.gt-recycle-stat-card {
  flex: 1;
  min-width: 100px;
  max-width: 160px;
  padding: 14px 16px;
  background: var(--gt-color-bg-white, #fff);
  border: 1px solid var(--gt-color-border-light, #ebeef5);
  border-radius: 8px;
  text-align: center;
  transition: box-shadow 0.2s;
}
.gt-recycle-stat-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.gt-recycle-stat-num {
  font-size: 22px;
  font-weight: 700;
  color: var(--gt-color-text, #303133);
  font-variant-numeric: tabular-nums;
}
.gt-recycle-stat-num--danger {
  color: var(--el-color-danger, #f56c6c);
}
.gt-recycle-stat-label {
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
  margin-top: 4px;
}

/* 工具栏 */
.gt-recycle-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

/* 分页 */
.gt-recycle-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

/* 保留天数颜色 */
.gt-retention--danger {
  color: var(--el-color-danger, #f56c6c);
  font-weight: 600;
}
.gt-retention--warning {
  color: var(--el-color-warning, #e6a23c);
}
.gt-retention--normal {
  color: var(--gt-color-text-tertiary, #909399);
}

/* 即将过期行高亮 */
:deep(.gt-row--expiring) {
  background: #fef0f0 !important;
}

/* 表格字号 */
:deep(.el-table .el-table__cell) {
  font-size: 13px;
}
</style>
