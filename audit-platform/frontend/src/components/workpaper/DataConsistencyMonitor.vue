<template>
  <div class="consistency-monitor">
    <h3>数据一致性监控</h3>
    <el-table :data="items" stripe size="small" max-height="400">
      <el-table-column prop="wp_code" label="底稿编号" width="100" />
      <el-table-column prop="wp_name" label="底稿名称" min-width="120" show-overflow-tooltip />
      <el-table-column label="底稿审定数" width="130" align="right">
        <template #default="{ row }">{{ fmt(row.wp_amount) }}</template>
      </el-table-column>
      <el-table-column label="试算表审定数" width="130" align="right">
        <template #default="{ row }">{{ fmt(row.tb_amount) }}</template>
      </el-table-column>
      <el-table-column label="差异" width="120" align="right">
        <template #default="{ row }">
          <span :class="{ 'text-danger': Math.abs(row.diff) > 0.01 }">{{ fmt(row.diff) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.consistent ? 'success' : 'danger'" size="small">
            {{ row.consistent ? '一致' : '差异' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100" align="center">
        <template #default="{ row }">
          <el-button v-if="!row.consistent" size="small" type="primary" link @click="$emit('refresh', row.wp_id)">
            刷新
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    <div class="summary">
      共 {{ items.length }} 张底稿，{{ inconsistentCount }} 张存在差异
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { fmtAmount } from '@/utils/formatters'

const props = defineProps<{ items: Array<{
  wp_id: string; wp_code: string; wp_name: string;
  wp_amount: number | null; tb_amount: number | null;
  diff: number; consistent: boolean;
}> }>()

defineEmits<{ (e: 'refresh', wpId: string): void }>()

const inconsistentCount = computed(() => props.items.filter(i => !i.consistent).length)
const fmt = fmtAmount
</script>

<style scoped>
.consistency-monitor { padding: 12px; }
.text-danger { color: var(--el-color-danger); font-weight: 600; }
.summary { margin-top: 8px; font-size: var(--gt-font-size-xs); color: var(--el-text-color-secondary); }
</style>
