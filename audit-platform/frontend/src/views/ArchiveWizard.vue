<!--
  ArchiveWizard — R1 需求 5 归档三步向导

  步骤 1：就绪检查（嵌入 GateReadinessPanel，拉 archive-readiness 数据）
  步骤 2：归档选项（推送到云端 / 清理本地数据 / scope 选择）
  步骤 3：确认执行 + 进度展示

  路由：/projects/:projectId/archive
        /projects/:projectId/archive/jobs/:jobId（直接进入进度视图）
-->
<template>
  <div class="gt-archive-wizard">
    <div class="gt-archive-wizard-header">
      <h2>项目归档向导</h2>
      <el-steps :active="currentStep" finish-status="success" align-center>
        <el-step title="就绪检查" description="确认归档条件" />
        <el-step title="归档选项" description="选择归档方式" />
        <el-step title="确认执行" description="开始归档" />
      </el-steps>
    </div>

    <div class="gt-archive-wizard-body">
      <!-- ═══ 步骤 1：就绪检查 ═══ -->
      <div v-if="currentStep === 0" class="gt-archive-step">
        <div class="gt-archive-step-desc">
          <el-icon><InfoFilled /></el-icon>
          <span>系统将检查项目是否满足归档条件，所有阻断项必须处理后才能继续。</span>
        </div>
        <GateReadinessPanel
          :data="readinessData"
          :loading="readinessLoading"
          :project-id="projectId"
          :on-refresh="fetchReadiness"
        />
        <div class="gt-archive-step-actions">
          <el-button @click="goBack">返回</el-button>
          <el-button
            type="primary"
            :disabled="!readinessData.ready"
            @click="currentStep = 1"
          >
            下一步
          </el-button>
        </div>
      </div>

      <!-- ═══ 步骤 2：归档选项 ═══ -->
      <div v-if="currentStep === 1" class="gt-archive-step">
        <div class="gt-archive-step-desc">
          <el-icon><Setting /></el-icon>
          <span>选择归档范围与附加操作。</span>
        </div>
        <el-form label-width="140px" class="gt-archive-options-form">
          <el-form-item label="归档范围">
            <el-radio-group v-model="archiveOptions.scope">
              <el-radio value="final">最终归档（Final）</el-radio>
              <el-radio value="interim">期中归档（Interim）</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="推送到云端">
            <el-switch v-model="archiveOptions.push_to_cloud" />
            <span class="gt-archive-option-hint">归档包上传至云端存储（推荐开启）</span>
          </el-form-item>
          <el-form-item label="清理本地数据">
            <el-switch v-model="archiveOptions.purge_local" />
            <span class="gt-archive-option-hint">归档完成后清理本地临时文件（不可逆）</span>
          </el-form-item>
        </el-form>
        <div class="gt-archive-step-actions">
          <el-button @click="currentStep = 0">上一步</el-button>
          <el-button type="primary" @click="currentStep = 2">下一步</el-button>
        </div>
      </div>

      <!-- ═══ 步骤 3：确认执行 ═══ -->
      <div v-if="currentStep === 2 && !isExecuting && !jobData" class="gt-archive-step">
        <div class="gt-archive-step-desc">
          <el-icon><WarningFilled /></el-icon>
          <span>请确认以下归档配置，点击"开始归档"后将不可中断。</span>
        </div>
        <el-descriptions :column="1" border class="gt-archive-confirm-desc">
          <el-descriptions-item label="归档范围">
            {{ archiveOptions.scope === 'final' ? '最终归档' : '期中归档' }}
          </el-descriptions-item>
          <el-descriptions-item label="推送到云端">
            {{ archiveOptions.push_to_cloud ? '是' : '否' }}
          </el-descriptions-item>
          <el-descriptions-item label="清理本地数据">
            {{ archiveOptions.purge_local ? '是' : '否' }}
          </el-descriptions-item>
          <el-descriptions-item label="就绪检查">
            <el-tag type="success" size="small">已通过</el-tag>
            <span v-if="readinessData.gate_eval_id" class="gt-archive-eval-id">
              ({{ readinessData.gate_eval_id.slice(0, 8) }}...)
            </span>
          </el-descriptions-item>
        </el-descriptions>
        <div class="gt-archive-step-actions">
          <el-button @click="currentStep = 1">上一步</el-button>
          <el-button
            type="danger"
            :loading="startingArchive"
            @click="handleStartArchive"
          >
            开始归档
          </el-button>
        </div>
      </div>

      <!-- ═══ 执行中：进度展示 ═══ -->
      <div v-if="isExecuting || jobData" class="gt-archive-step gt-archive-progress">
        <template v-if="jobData">
          <!-- 成功 -->
          <div v-if="jobData.status === 'succeeded'" class="gt-archive-result gt-archive-success">
            <el-result icon="success" title="归档完成" sub-title="项目已成功归档。">
              <template #extra>
                <el-button
                  v-if="jobData.output_url"
                  type="primary"
                  @click="handleDownload"
                >
                  下载归档包
                </el-button>
                <el-button @click="goBack">返回项目</el-button>
              </template>
            </el-result>
          </div>

          <!-- 失败 -->
          <div v-else-if="jobData.status === 'failed'" class="gt-archive-result gt-archive-failed">
            <el-result icon="error" title="归档失败">
              <template #sub-title>
                <div class="gt-archive-fail-detail">
                  <p v-if="jobData.failed_section">
                    <strong>失败章节：</strong>{{ jobData.failed_section }}
                  </p>
                  <p v-if="jobData.failed_reason">
                    <strong>失败原因：</strong>{{ jobData.failed_reason }}
                  </p>
                  <p v-if="jobData.last_succeeded_section">
                    <strong>最后成功章节：</strong>{{ jobData.last_succeeded_section }}
                  </p>
                </div>
              </template>
              <template #extra>
                <el-button type="primary" :loading="retrying" @click="handleRetry">
                  重试（从断点续传）
                </el-button>
                <el-button @click="goBack">返回项目</el-button>
              </template>
            </el-result>
          </div>

          <!-- 运行中 -->
          <div v-else class="gt-archive-running">
            <div class="gt-archive-running-header">
              <el-icon class="is-loading"><Loading /></el-icon>
              <span>归档进行中...</span>
            </div>
            <el-progress
              :percentage="progressPercent"
              :stroke-width="18"
              :text-inside="true"
              striped
              striped-flow
            />
            <div v-if="jobData.current_section" class="gt-archive-current-section">
              当前章节：{{ jobData.current_section }}
            </div>
            <!-- 章节级进度 -->
            <div v-if="jobData.sections && jobData.sections.length" class="gt-archive-sections">
              <div
                v-for="section in jobData.sections"
                :key="section.order"
                class="gt-archive-section-item"
                :class="`section-${section.status}`"
              >
                <el-icon v-if="section.status === 'succeeded'"><CircleCheck /></el-icon>
                <el-icon v-else-if="section.status === 'running'" class="is-loading"><Loading /></el-icon>
                <el-icon v-else-if="section.status === 'failed'"><CircleClose /></el-icon>
                <el-icon v-else><Clock /></el-icon>
                <span class="gt-archive-section-order">{{ section.order }}</span>
                <span class="gt-archive-section-name">{{ section.name }}</span>
              </div>
            </div>
          </div>
        </template>
        <template v-else>
          <div class="gt-archive-running">
            <div class="gt-archive-running-header">
              <el-icon class="is-loading"><Loading /></el-icon>
              <span>正在启动归档...</span>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  InfoFilled,
  Setting,
  WarningFilled,
  Loading,
  CircleCheck,
  CircleClose,
  Clock,
} from '@element-plus/icons-vue'
import GateReadinessPanel from '@/components/gate/GateReadinessPanel.vue'
import type { GateReadinessData } from '@/components/gate/GateReadinessPanel.vue'
import {
  getArchiveReadiness,
  startArchiveOrchestrate,
  getArchiveJob,
  retryArchiveJob,
} from '@/services/archiveApi'
import type { ArchiveJob } from '@/services/archiveApi'
import { showApiError } from '@/composables/useApiError'

const route = useRoute()
const router = useRouter()

const projectId = computed(() => route.params.projectId as string)
const jobIdFromRoute = computed(() => route.params.jobId as string | undefined)

// ── 步骤控制 ──────────────────────────────────────────────────────────────
const currentStep = ref(0)

// ── 就绪检查 ──────────────────────────────────────────────────────────────
const readinessLoading = ref(false)
const readinessData = ref<GateReadinessData>({
  ready: false,
  groups: [],
  gate_eval_id: null,
  expires_at: null,
})

async function fetchReadiness() {
  readinessLoading.value = true
  try {
    const data = await getArchiveReadiness(projectId.value)
    readinessData.value = data
  } catch (err: any) {
    ElMessage.error(err?.message || '获取归档就绪检查失败')
  } finally {
    readinessLoading.value = false
  }
}

// ── 归档选项 ──────────────────────────────────────────────────────────────
const archiveOptions = ref({
  scope: 'final' as 'final' | 'interim',
  push_to_cloud: true,
  purge_local: false,
})

// ── 执行状态 ──────────────────────────────────────────────────────────────
const isExecuting = ref(false)
const startingArchive = ref(false)
const retrying = ref(false)
const jobData = ref<ArchiveJob | null>(null)
let pollTimer: ReturnType<typeof setInterval> | null = null

const progressPercent = computed(() => {
  if (!jobData.value) return 0
  const sections = jobData.value.sections
  if (!sections || sections.length === 0) {
    // 无章节信息时按状态估算
    if (jobData.value.status === 'queued') return 5
    if (jobData.value.status === 'running') return 50
    if (jobData.value.status === 'succeeded') return 100
    return 0
  }
  const done = sections.filter(s => s.status === 'succeeded').length
  return Math.round((done / sections.length) * 100)
})

async function handleStartArchive() {
  startingArchive.value = true
  isExecuting.value = true
  try {
    const resp = await startArchiveOrchestrate(projectId.value, {
      scope: archiveOptions.value.scope,
      push_to_cloud: archiveOptions.value.push_to_cloud,
      purge_local: archiveOptions.value.purge_local,
      gate_eval_id: readinessData.value.gate_eval_id || undefined,
    })
    // 更新路由到 job 视图
    router.replace({
      path: `/projects/${projectId.value}/archive/jobs/${resp.archive_job_id}`,
    })
    startPolling(resp.archive_job_id)
  } catch (err: any) {
    isExecuting.value = false
    // R1 Bug Fix 8: 使用 showApiError 统一处理
    showApiError(err)
  } finally {
    startingArchive.value = false
  }
}

async function handleRetry() {
  if (!jobData.value) return
  retrying.value = true
  try {
    const resp = await retryArchiveJob(projectId.value, jobData.value.id)
    jobData.value = resp
    startPolling(resp.id)
  } catch (err: any) {
    ElMessage.error(err?.message || '重试失败')
  } finally {
    retrying.value = false
  }
}

function startPolling(jobId: string) {
  stopPolling()
  pollJob(jobId)
  pollTimer = setInterval(() => pollJob(jobId), 3000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function pollJob(jobId: string) {
  try {
    const data = await getArchiveJob(projectId.value, jobId)
    jobData.value = data
    // 终态停止轮询
    if (data.status === 'succeeded' || data.status === 'failed') {
      stopPolling()
      if (data.status === 'succeeded') {
        ElMessage.success('归档完成！')
      }
    }
  } catch (err: any) {
    // 网络错误不停止轮询，等下次重试
    console.warn('[ArchiveWizard] poll error:', err)
  }
}

function handleDownload() {
  if (jobData.value?.output_url) {
    window.open(jobData.value.output_url, '_blank')
  }
}

function goBack() {
  router.push({ name: 'ProjectDashboard', params: { projectId: projectId.value } })
}

// ── 生命周期 ──────────────────────────────────────────────────────────────
onMounted(async () => {
  // 如果路由带 jobId，直接进入进度视图
  if (jobIdFromRoute.value) {
    isExecuting.value = true
    currentStep.value = 2
    startPolling(jobIdFromRoute.value)
  } else {
    // 正常流程：先拉就绪检查
    await fetchReadiness()
  }
})

onBeforeUnmount(() => {
  stopPolling()
})
</script>

<style scoped>
.gt-archive-wizard {
  max-width: 900px;
  margin: 0 auto;
  padding: 24px;
}

.gt-archive-wizard-header {
  margin-bottom: 32px;
}

.gt-archive-wizard-header h2 {
  text-align: center;
  margin-bottom: 24px;
  font-size: 20px;
  color: var(--gt-color-text-primary, #303133);
}

.gt-archive-step {
  min-height: 300px;
}

.gt-archive-step-desc {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 20px;
  padding: 12px 16px;
  background: #f4f4f5;
  border-radius: 6px;
  font-size: 14px;
  color: var(--gt-color-text-secondary, #606266);
}

.gt-archive-step-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid #ebeef5;
}

/* ── 选项表单 ── */
.gt-archive-options-form {
  max-width: 600px;
  margin: 0 auto;
}

.gt-archive-option-hint {
  margin-left: 12px;
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
}

/* ── 确认描述 ── */
.gt-archive-confirm-desc {
  max-width: 600px;
  margin: 0 auto;
}

.gt-archive-eval-id {
  margin-left: 8px;
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
  font-family: var(--gt-font-family-mono, Consolas, monospace);
}

/* ── 进度展示 ── */
.gt-archive-progress {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.gt-archive-running {
  width: 100%;
  max-width: 600px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.gt-archive-running-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 500;
  color: var(--gt-color-text-primary, #303133);
}

.gt-archive-current-section {
  text-align: center;
  font-size: 13px;
  color: var(--gt-color-text-secondary, #606266);
}

.gt-archive-sections {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
  padding: 12px;
  background: #fafafa;
  border-radius: 6px;
}

.gt-archive-section-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 4px;
  font-size: 13px;
}

.gt-archive-section-item.section-succeeded {
  color: #67c23a;
}

.gt-archive-section-item.section-running {
  color: #409eff;
  font-weight: 500;
}

.gt-archive-section-item.section-failed {
  color: #f56c6c;
}

.gt-archive-section-item.section-pending,
.gt-archive-section-item.section-skipped {
  color: #909399;
}

.gt-archive-section-order {
  font-family: var(--gt-font-family-mono, Consolas, monospace);
  font-size: 12px;
  min-width: 24px;
}

.gt-archive-section-name {
  flex: 1;
}

/* ── 结果 ── */
.gt-archive-result {
  width: 100%;
}

.gt-archive-fail-detail {
  text-align: left;
  max-width: 500px;
  margin: 0 auto;
}

.gt-archive-fail-detail p {
  margin: 4px 0;
  font-size: 13px;
  color: var(--gt-color-text-secondary, #606266);
}
</style>
