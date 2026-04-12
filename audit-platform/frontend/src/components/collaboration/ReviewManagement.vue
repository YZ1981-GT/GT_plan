<template>
  <div class="review-management">
    <div class="review-header">
      <h3>复核管理</h3>
    </div>
    <el-tabs v-model="reviewTab">
      <el-tab-pane label="我的待复核" name="pending">
        <el-table :data="pendingReviews" stripe>
          <el-table-column prop="workpaper_id" label="工作底稿ID" />
          <el-table-column prop="review_level" label="复核级别">
            <template #default="{ row }">
              {{ levelName(row.review_level) }}
            </template>
          </el-table-column>
          <el-table-column prop="review_status" label="状态" />
          <el-table-column label="操作" width="200">
            <template #default="{ row }">
              <el-button size="small" type="success" @click="startReview(row)">开始复核</el-button>
              <el-button size="small" @click="viewDetail(row)">查看</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
      <el-tab-pane label="复核历史" name="history">
        <el-table :data="completedReviews" stripe>
          <el-table-column prop="workpaper_id" label="工作底稿ID" />
          <el-table-column prop="review_level" label="复核级别" />
          <el-table-column prop="review_status" label="状态" />
          <el-table-column prop="updated_at" label="完成时间" />
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="showReviewDialog" title="复核详情" width="600px">
      <div v-if="currentReview">
        <p><strong>复核级别：</strong>{{ levelName(currentReview.review_level) }}</p>
        <p><strong>状态：</strong>{{ currentReview.review_status }}</p>
        <el-divider />
        <h4>复核意见</h4>
        <el-input v-model="reviewComments" type="textarea" :rows="4" placeholder="填写复核意见" />
      </div>
      <template #footer>
        <el-button @click="showReviewDialog = false">取消</el-button>
        <el-button type="success" @click="approveReview">批准通过</el-button>
        <el-button type="danger" @click="showRejectDialog = true">驳回</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showRejectDialog" title="驳回复核" width="400px">
      <el-form>
        <el-form-item label="驳回原因" required>
          <el-input v-model="rejectComments" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showRejectDialog = false">取消</el-button>
        <el-button type="danger" @click="confirmReject">确认驳回</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { reviewApi } from '@/services/collaborationApi'

const reviewTab = ref('pending')
const pendingReviews = ref<any[]>([])
const completedReviews = ref<any[]>([])
const showReviewDialog = ref(false)
const showRejectDialog = ref(false)
const currentReview = ref<any>(null)
const reviewComments = ref('')
const rejectComments = ref('')

const LEVEL_NAMES: Record<number, string> = {
  1: '审计员自复核',
  2: '经理复核',
  3: '合伙人复核',
}

function levelName(level: number) {
  return LEVEL_NAMES[level] || `Level ${level}`
}

onMounted(async () => {
  try {
    const { data } = await reviewApi.pending()
    pendingReviews.value = data
  } catch (e) {
    console.error(e)
  }
})

function viewDetail(row: any) {
  currentReview.value = row
  showReviewDialog.value = true
}

async function startReview(row: any) {
  try {
    await reviewApi.start(row.id)
    ElMessage.success('复核已开始')
  } catch (e) {
    ElMessage.error('操作失败')
  }
}

async function approveReview() {
  if (!currentReview.value) return
  try {
    await reviewApi.approve(currentReview.value.id, { comments: reviewComments.value })
    ElMessage.success('复核已批准')
    showReviewDialog.value = false
    pendingReviews.value = pendingReviews.value.filter(r => r.id !== currentReview.value.id)
  } catch (e) {
    ElMessage.error('操作失败')
  }
}

async function confirmReject() {
  if (!rejectComments.value) {
    ElMessage.warning('请填写驳回原因')
    return
  }
  if (!currentReview.value) return
  try {
    await reviewApi.reject(currentReview.value.id, { comments: rejectComments.value })
    ElMessage.success('复核已驳回')
    showRejectDialog.value = false
    showReviewDialog.value = false
    pendingReviews.value = pendingReviews.value.filter(r => r.id !== currentReview.value.id)
  } catch (e) {
    ElMessage.error('操作失败')
  }
}
</script>

<style scoped>
.review-management {}
.review-header { margin-bottom: 16px; }
</style>
