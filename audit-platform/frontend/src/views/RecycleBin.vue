<template>
  <div class="gt-recycle-bin">
    <div class="gt-recycle-header">
      <h2>回收站</h2>
      <div class="gt-recycle-actions">
        <el-tag v-if="stats.is_over_limit" type="danger" size="large" effect="dark">
          已超出上限（{{ stats.total }}/{{ stats.limit }}），请清理
        </el-tag>
        <el-tag v-else type="info" size="large">
          {{ stats.total }} 条已删除记录
        </el-tag>
        <el-button
          type="danger"
          plain
          size="small"
          :disabled="stats.total === 0"
          @click="confirmEmptyAll"
        >
          <el-icon><Delete /></el-icon> 清空回收站
        </el-button>
      </div>
    </div>

    <!-- 类型筛选 -->
    <div class="gt-recycle-filters">
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
    </div>

    <!-- 列表 -->
    <el-table :data="items" stripe size="small" v-loading="loading" empty-text="回收站为空">
      <el-table-column prop="type_label" label="类型" width="100" />
      <el-table-column prop="name" label="名称" min-width="200" show-overflow-tooltip />
      <el-table-column prop="deleted_at" label="删除时间" width="170">
        <template #default="{ row }">
          {{ row.deleted_at ? new Date(row.deleted_at).toLocaleString('zh-CN') : '-' }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" size="small" text @click="restoreItem(row)">
            恢复
          </el-button>
          <el-button type="danger" size="small" text @click="confirmDelete(row)">
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
        layout="prev, pager, next"
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
    ElMessage.error(e.response?.data?.detail || '恢复失败')
  }
}

async function confirmDelete(row: any) {
  try {
    await confirmDangerous(
      `确定要永久删除${row.type_label}「${row.name}」吗？此操作不可恢复。`,
      '永久删除',
    )
    const cachedRow = JSON.parse(JSON.stringify(row))
    await operationHistory.execute({
      description: `永久删除${cachedRow.type_label}「${cachedRow.name}」`,
      execute: async () => {
        await permanentDeleteItem(`${row.type}/${row.id}`)
        await loadItems()
        await loadStats()
      },
      undo: async () => {
        // 永久删除后数据已从后端移除，无法撤销
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
        // 清空回收站后数据已全部移除，无法撤销
        throw new Error('清空回收站操作不可撤销')
      },
    })
  } catch { /* cancelled */ }
}

onMounted(async () => {
  await loadStats()
  await loadItems()
})
</script>

<style scoped>
.gt-recycle-bin {
  padding: var(--gt-space-5);
  max-width: 900px;
}
.gt-recycle-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--gt-space-4);
}
.gt-recycle-header h2 {
  font-size: var(--gt-font-size-xl);
  font-weight: 700;
  color: var(--gt-color-text);
  margin: 0;
}
.gt-recycle-actions {
  display: flex;
  align-items: center;
  gap: var(--gt-space-3);
}
.gt-recycle-filters {
  margin-bottom: var(--gt-space-3);
}
.gt-recycle-pagination {
  display: flex;
  justify-content: center;
  margin-top: var(--gt-space-4);
}
</style>
