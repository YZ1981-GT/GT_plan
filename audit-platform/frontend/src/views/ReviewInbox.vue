<template>
  <div class="review-inbox">
    <!-- 顶部横幅 -->
    <div class="gt-page-banner">
      <div class="gt-banner-content">
        <h2>📋 待复核收件箱</h2>
        <span class="gt-banner-sub">{{ isGlobal ? '跨项目' : projectName }} · 共 {{ total }} 个底稿待复核</span>
      </div>
      <div class="gt-banner-actions">
        <el-button :disabled="!selectedIds.length" type="success" @click="handleBatchApprove">
          ✅ 批量通过 ({{ selectedIds.length }})
        </el-button>
        <el-button :disabled="!selectedIds.length" type="warning" @click="showRejectDialog = true">
          ↩️ 批量退回 ({{ selectedIds.length }})
        </el-button>
      </div>
    </div>

    <!-- 表格 -->
    <el-table
      :data="items"
      v-loading="loading"
      @selection-change="onSelectionChange"
      stripe
      style="width: 100%"
      row-key="id"
    >
      <el-table-column type="selection" width="45" />
      <el-table-column label="项目" prop="project_name" width="160" v-if="isGlobal" />
      <el-table-column label="底稿编号" prop="wp_code" width="120" sortable />
      <el-table-column label="底稿名称" prop="wp_name" min-width="200" />
      <el-table-column label="审计循环" prop="audit_cycle" width="100" />
      <el-table-column label="复核状态" width="120">
        <template #default="{ row }">
          <el-tag :type="row.review_status === 'pending_level1' ? 'warning' : 'danger'" size="small">
            {{ row.review_status === 'pending_level1' ? '待一级复核' : '待二级复核' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="提交时间" width="160">
        <template #default="{ row }">
          {{ row.submitted_at ? new Date(row.submitted_at).toLocaleString('zh-CN') : '-' }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="goToWorkpaper(row)">查看</el-button>
          <el-button size="small" type="success" link @click="handleSingleApprove(row)">通过</el-button>
          <el-button size="small" type="warning" link @click="handleSingleReject(row)">退回</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="gt-pagination" v-if="total > pageSize">
      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="loadData"
      />
    </div>

    <!-- 退回原因弹窗 -->
    <el-dialog v-model="showRejectDialog" title="退回原因" width="480" append-to-body>
      <el-input v-model="rejectComment" type="textarea" :rows="3" placeholder="请输入退回原因（可选）" />
      <template #footer>
        <el-button @click="showRejectDialog = false">取消</el-button>
        <el-button type="warning" @click="handleBatchReject">确认退回</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { confirmBatch, confirmDangerous } from '@/utils/confirm'
import {
  getGlobalReviewInbox,
  getProjectReviewInbox,
  batchReview,
  type ReviewInboxItem,
} from '@/services/pmApi'

const route = useRoute()
const router = useRouter()

const projectId = computed(() => route.params.projectId as string | undefined)
const isGlobal = computed(() => !projectId.value)
const projectName = ref('')

const items = ref<ReviewInboxItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 50
const loading = ref(false)
const selectedIds = ref<string[]>([])
const showRejectDialog = ref(false)
const rejectComment = ref('')

function onSelectionChange(rows: ReviewInboxItem[]) {
  selectedIds.value = rows.map(r => r.id)
}

async function loadData() {
  loading.value = true
  try {
    const result = isGlobal.value
      ? await getGlobalReviewInbox(page.value, pageSize)
      : await getProjectReviewInbox(projectId.value!, page.value, pageSize)
    items.value = result.items || []
    total.value = result.total || 0
    if (items.value.length > 0 && !isGlobal.value) {
      projectName.value = items.value[0].project_name
    }
  } catch (e: any) {
    ElMessage.error('加载失败: ' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

function goToWorkpaper(row: ReviewInboxItem) {
  router.push({
    name: 'WorkpaperEditor',
    params: {
      projectId: row.project_id,
      wpId: row.id,
    },
  })
}

async function handleSingleApprove(row: ReviewInboxItem) {
  await confirmDangerous(`确认通过底稿 ${row.wp_code} ${row.wp_name}？`, '通过确认')
  await doBatchReview([row.id], 'approve', row.project_id)
}

async function handleSingleReject(row: ReviewInboxItem) {
  const { value } = await ElMessageBox.prompt('请输入退回原因（可选）', '退回底稿', { inputType: 'textarea' })
  await doBatchReview([row.id], 'reject', row.project_id, value || '')
}

async function handleBatchApprove() {
  if (!selectedIds.value.length) return
  await confirmBatch('通过', selectedIds.value.length)
  const pid = projectId.value || items.value[0]?.project_id
  if (!pid) return
  await doBatchReview(selectedIds.value, 'approve', pid)
}

async function handleBatchReject() {
  const pid = projectId.value || items.value[0]?.project_id
  if (!pid) return
  await doBatchReview(selectedIds.value, 'reject', pid, rejectComment.value)
  showRejectDialog.value = false
  rejectComment.value = ''
}

async function doBatchReview(ids: string[], action: 'approve' | 'reject', pid: string, comment = '') {
  try {
    const result = await batchReview(pid, ids, action, comment)
    const label = action === 'approve' ? '通过' : '退回'
    ElMessage.success(`${label}成功 ${result.succeeded_count} 个${result.skipped_count > 0 ? `，跳过 ${result.skipped_count} 个` : ''}`)
    await loadData()
  } catch (e: any) {
    ElMessage.error('操作失败: ' + (e.message || ''))
  }
}

onMounted(loadData)
</script>

<style scoped>
.review-inbox { padding: 0; }
</style>
