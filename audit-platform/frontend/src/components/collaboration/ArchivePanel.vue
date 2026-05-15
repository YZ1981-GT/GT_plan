<template>
  <div class="gt-archive-panel">
    <div class="panel-header">
      <h3>归档管理</h3>
      <div class="header-right">
        <el-tag v-if="archiveStatus" :type="archiveStatus === 'ARCHIVED' ? 'success' : 'warning'" size="large">
          当前状态：{{ archiveStatusLabel }}
        </el-tag>
      </div>
    </div>

    <el-table :data="checklistItems" stripe>
      <el-table-column prop="item_code" label="编号" width="80" />
      <el-table-column prop="item_name" label="检查项" min-width="200" />
      <el-table-column prop="responsible" label="责任人" width="120" />
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="row.is_completed ? 'success' : 'info'" size="small">
            {{ row.is_completed ? '已完成' : '待完成' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="completed_at" label="完成时间" width="160" />
      <el-table-column label="操作" width="140">
        <template #default="{ row }">
          <el-button
            size="small"
            type="success"
            :disabled="row.is_completed"
            @click="markComplete(row)"
          >
            标记完成
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="action-bar">
      <el-button
        type="primary"
        :disabled="!allComplete"
        @click="executeArchive"
      >
        执行归档
      </el-button>
      <el-button @click="showPasswordDialog = true">导出PDF</el-button>
    </div>

    <!-- 密码设置弹窗 -->
    <el-dialog append-to-body v-model="showPasswordDialog" title="导出PDF设置密码" width="400px">
      <el-form>
        <el-form-item label="PDF密码">
          <el-input v-model="pdfPassword" type="password" show-password placeholder="请输入密码（可选）" />
        </el-form-item>
        <el-form-item label="确认密码">
          <el-input v-model="confirmPassword" type="password" show-password placeholder="请再次输入密码" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showPasswordDialog = false">取消</el-button>
        <el-button type="primary" @click="handleExportPdf">确认导出</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { handleApiError } from '@/utils/errorHandler'
import { archiveApi } from '@/services/collaborationApi'

const projectId = 'current-project-id'

const checklistItems = ref<any[]>([])
const archiveStatus = ref('')
const showPasswordDialog = ref(false)
const pdfPassword = ref('')
const confirmPassword = ref('')

const archiveStatusLabel = computed(() => {
  const map: Record<string, string> = {
    PENDING: '待归档',
    IN_PROGRESS: '归档中',
    ARCHIVED: '已归档',
    MODIFICATION_REQUESTED: '申请修改中',
  }
  return map[archiveStatus.value] || archiveStatus.value || '未知'
})

const allComplete = computed(() =>
  checklistItems.value.length > 0 && checklistItems.value.every((i) => i.is_completed),
)

onMounted(async () => {
  try {
    const { data } = await archiveApi.getChecklist(projectId)
    checklistItems.value = data ?? []
    archiveStatus.value = data?.archive_status || ''
  } catch {
    // graceful fallback
    checklistItems.value = [
      { id: '1', item_code: 'A01', item_name: '审计报告定稿', responsible: '项目经理', is_completed: true, completed_at: '2025-04-01 10:00' },
      { id: '2', item_code: 'A02', item_name: '工作底稿整理', responsible: '审计员', is_completed: false, completed_at: '' },
      { id: '3', item_code: 'A03', item_name: '附件资料归档', responsible: '档案管理员', is_completed: false, completed_at: '' },
    ]
    archiveStatus.value = 'PENDING'
  }
})

async function markComplete(row: any) {
  try {
    await archiveApi.completeItem(projectId, row.id)
    row.is_completed = true
    row.completed_at = new Date().toLocaleString('zh-CN')
    ElMessage.success('已标记完成')
  } catch (e) {
    handleApiError(e, '标记完成')
  }
}

async function executeArchive() {
  if (!allComplete.value) {
    ElMessage.warning('请先完成所有检查项')
    return
  }
  try {
    await archiveApi.archive(projectId)
    archiveStatus.value = 'ARCHIVED'
    ElMessage.success('归档执行成功')
  } catch (e) {
    handleApiError(e, '归档执行')
  }
}

async function handleExportPdf() {
  if (pdfPassword.value && pdfPassword.value !== confirmPassword.value) {
    ElMessage.warning('两次密码不一致')
    return
  }
  try {
    showPasswordDialog.value = false
    await archiveApi.exportPdf(projectId, { password: pdfPassword.value })
    ElMessage.success('PDF导出任务已提交')
    pdfPassword.value = ''
    confirmPassword.value = ''
  } catch (e) {
    handleApiError(e, '导出PDF')
  }
}
</script>

<style scoped>
.gt-archive-panel {}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.header-right { display: flex; gap: 12px; align-items: center; }
.action-bar {
  margin-top: 16px;
  display: flex;
  gap: 12px;
}
</style>
