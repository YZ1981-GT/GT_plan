<template>
  <div class="independence-signing">
    <el-tabs v-model="activeTab" type="border-card">
      <el-tab-pane label="签署进度" name="progress">
        <div class="signing-progress">
          <el-button type="primary" size="small" @click="initiateSigning" :loading="initiating">
            发起签署
          </el-button>
          <el-button size="small" @click="initiateCommittee" :loading="initiating">
            发起专委会签署(A17-7A)
          </el-button>
          <el-button size="small" @click="fetchProgress" :loading="loading">刷新</el-button>
        </div>

        <template v-if="progress">
          <el-progress
            :percentage="progress.total ? Math.round(progress.signed / progress.total * 100) : 0"
            :status="progress.complete ? 'success' : ''"
            style="margin: 16px 0"
          />
          <p>已签署 {{ progress.signed }} / {{ progress.total }} 人</p>

          <el-descriptions :column="1" border v-if="progress.signed_list?.length">
            <el-descriptions-item v-for="s in progress.signed_list" :key="s.user_id" :label="s.user_id">
              已签署于 {{ s.signed_at }}
            </el-descriptions-item>
          </el-descriptions>

          <div v-if="progress.pending?.length" style="margin-top: 12px">
            <p style="color: var(--el-color-warning)">待签署：</p>
            <el-tag v-for="p in progress.pending" :key="p.user_id" style="margin: 4px">
              {{ p.user_id }}
            </el-tag>
          </div>
        </template>
      </el-tab-pane>

      <el-tab-pane label="我的待办" name="my-tasks">
        <div v-if="myTasks.length === 0" class="no-tasks">暂无待签署任务</div>
        <el-table v-else :data="myTasks" class="gt-compact-table">
          <el-table-column prop="project_id" label="项目" min-width="200" />
          <el-table-column prop="template_code" label="模板" width="100" />
          <el-table-column prop="created_at" label="创建时间" width="180" />
          <el-table-column label="操作" width="100">
            <template #default="{ row }">
              <el-button type="primary" size="small" @click="signTask(row)">签署</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { apiProxy } from '@/utils/apiProxy'
import { ElMessage } from 'element-plus'

const props = defineProps<{
  projectId: string
  year: number
  userId: string
}>()

const activeTab = ref('progress')
const loading = ref(false)
const initiating = ref(false)
const progress = ref<any>(null)
const myTasks = ref<any[]>([])

async function fetchProgress() {
  loading.value = true
  try {
    progress.value = await apiProxy.get(
      `/api/projects/${props.projectId}/signing/${props.year}/progress?template_code=A17-7`
    )
  } finally {
    loading.value = false
  }
}

async function initiateSigning() {
  initiating.value = true
  try {
    await apiProxy.post(`/api/projects/${props.projectId}/signing/${props.year}/initiate?template_code=A17-7`)
    ElMessage.success('签署任务已发起')
    await fetchProgress()
  } finally {
    initiating.value = false
  }
}

async function initiateCommittee() {
  initiating.value = true
  try {
    await apiProxy.post(`/api/projects/${props.projectId}/signing/${props.year}/initiate?template_code=A17-7A`)
    ElMessage.success('专委会签署任务已发起')
  } finally {
    initiating.value = false
  }
}

async function fetchMyTasks() {
  myTasks.value = await apiProxy.get(`/api/my/signing-tasks?user_id=${props.userId}`)
}

async function signTask(task: any) {
  await apiProxy.post(
    `/api/projects/${task.project_id}/signing/${props.year}/sign?user_id=${props.userId}&template_code=${task.template_code}`
  )
  ElMessage.success('签署成功')
  await fetchMyTasks()
  await fetchProgress()
}

onMounted(() => {
  fetchProgress()
  fetchMyTasks()
})
</script>

<style scoped>
.signing-progress { display: flex; gap: 8px; margin-bottom: 12px; }
.no-tasks { color: var(--el-text-color-placeholder); padding: 24px; text-align: center; }
</style>
