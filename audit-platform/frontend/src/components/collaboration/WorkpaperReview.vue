<template>
  <div class="gt-workpaper-review">
    <div class="wp-header">
      <h3>工作底稿复核状态</h3>
    </div>
    <el-table :data="workpapers" stripe>
      <el-table-column prop="id" label="ID" width="200" />
      <el-table-column prop="title" label="标题" />
      <el-table-column label="复核状态" width="200">
        <template #default="{ row }">
          <div class="review-levels">
            <el-tag v-for="l in 3" :key="l" :type="getReviewTagType(row, l)" size="small">
              {{ getReviewStatus(row, l) }}
            </el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-button size="small" @click="viewReviews(row)">查看</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { reviewApi } from '@/services/collaborationApi'

const workpapers = ref<any[]>([])

onMounted(async () => {
  // Load workpapers with review info
})

function getReviewStatus(row: any, level: number) {
  // return status for each level
  return '待复核'
}

function getReviewTagType(row: any, level: number) {
  const status = getReviewStatus(row, level)
  if (status === '已批准') return 'success'
  if (status === '已驳回') return 'danger'
  return 'info'
}

async function viewReviews(row: any) {
  try {
    const { data } = await reviewApi.list(row.id)
    console.log('reviews', data)
  } catch (e) {
    console.error(e)
  }
}
</script>

<style scoped>
.gt-workpaper-review {}
.wp-header { margin-bottom: 16px; }
.review-levels { display: flex; gap: 4px; }
</style>
