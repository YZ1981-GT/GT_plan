<!--
  ProcedureReviewPanel.vue — 程序行一级复核面板（Task 14 / Design F5）

  Feature: procedure-delegation-notification / 需求 5.7-5.8、8.1-8.8

  在程序控制台复用对话 UI：
  - 展示对话消息（稳定排序）、IssueTicket 未解决数与问题单列表；
  - 当前参与者可发消息 / 关闭问题单；历史只读参与者显示“历史只读”标识且禁写（需求 8.5-8.6）；
  - 高阶复核（业务合伙人 / QC / EQCR）在独立只读区域展示，**不与一级 reviewed 合并**，
    明确一级 reviewed 不豁免/削弱高阶复核门槛（需求 5.7-5.8 / P18）。

  数据源：Task 13 后端端点（getProcedureConversation / postProcedureMessage / closeProcedureIssue）。
  本面板不直接改任务 workflow_status（状态机唯一入口是 transition API，由控制台/任务页调用）。
-->
<template>
  <div class="gt-proc-review-panel">
    <!-- 顶部：定位 + 访问级别 -->
    <div class="gt-proc-review-panel__head">
      <div class="gt-proc-review-panel__title">
        <span>程序行一级复核</span>
        <el-tag size="small" effect="plain" type="info">{{ ROLE_TERMS.operationReviewer }}</el-tag>
        <el-tag v-if="view?.readonly" size="small" type="warning" effect="dark">历史只读</el-tag>
      </div>
      <el-tag
        size="small"
        :type="openIssueCount > 0 ? 'danger' : 'success'"
        effect="plain"
      >
        未解决问题单 {{ openIssueCount }}
      </el-tag>
    </div>

    <!-- 一级复核 vs 高阶复核职责边界说明（需求 5.7-5.8） -->
    <el-alert type="info" :closable="false" class="gt-proc-review-panel__scope">
      <template #title>
        <span style="font-size:12px">
          本面板仅处理程序行一级复核（{{ ROLE_TERMS.operationReviewer }}）。一级“已复核”不代表、不豁免
          {{ ROLE_TERMS.highOrderReviewer }} 的高阶复核；高阶复核门槛不受本面板影响。
        </span>
      </template>
    </el-alert>

    <!-- 高阶复核只读区域（独立展示，不与一级 reviewed 合并） -->
    <div class="gt-proc-review-panel__high-order">
      <div class="gt-proc-review-panel__section-label">{{ ROLE_TERMS.highOrderReviewer }}（高阶复核，只读）</div>
      <div v-if="highOrderReviews && highOrderReviews.length" class="gt-proc-review-panel__high-order-rows">
        <div v-for="(h, idx) in highOrderReviews" :key="idx" class="gt-proc-review-panel__high-order-row">
          <el-tag size="small" effect="plain">{{ h.role_label }}</el-tag>
          <span>{{ h.reviewer_name || '—' }}</span>
          <el-tag size="small" :type="h.status === 'approved' ? 'success' : 'info'" effect="plain">
            {{ h.status_label || h.status || '未开始' }}
          </el-tag>
        </div>
      </div>
      <div v-else class="gt-proc-review-panel__muted">
        高阶复核状态由底稿/项目层机制维护，此处仅提示与一级复核相互独立。
      </div>
    </div>

    <el-divider style="margin:10px 0" />

    <!-- 未解决问题单列表 -->
    <div class="gt-proc-review-panel__section-label">退回问题单（IssueTicket）</div>
    <div v-if="loading" class="gt-proc-review-panel__muted">加载中…</div>
    <div v-else-if="!issues.length" class="gt-proc-review-panel__muted">暂无退回问题单</div>
    <div v-else class="gt-proc-review-panel__issues">
      <div v-for="issue in issues" :key="issue.id" class="gt-proc-review-panel__issue">
        <el-tag size="small" :type="issue.status === 'closed' ? 'success' : 'danger'" effect="plain">
          {{ issue.status === 'closed' ? '已关闭' : '未解决' }}
        </el-tag>
        <span class="gt-proc-review-panel__issue-title">{{ issue.title }}</span>
        <el-button
          v-if="canWrite && issue.status !== 'closed'"
          size="small" text type="primary"
          :loading="acting"
          @click="onCloseIssue(issue.id)"
        >关闭</el-button>
      </div>
    </div>

    <el-divider style="margin:10px 0" />

    <!-- 对话消息 -->
    <div class="gt-proc-review-panel__section-label">复核对话</div>
    <div class="gt-proc-review-panel__messages">
      <div v-if="!messages.length" class="gt-proc-review-panel__muted">暂无消息</div>
      <div v-for="m in messages" :key="m.id" class="gt-proc-review-panel__msg">
        <div class="gt-proc-review-panel__msg-meta">
          <span>{{ staffOrUserName(m.sender_id) }}</span>
          <span class="gt-proc-review-panel__msg-time">{{ fmtTime(m.created_at) }}</span>
        </div>
        <div class="gt-proc-review-panel__msg-body">{{ m.content }}</div>
      </div>
    </div>

    <!-- 发消息（仅当前参与者可写） -->
    <div v-if="canWrite" class="gt-proc-review-panel__composer">
      <el-input
        v-model="draft"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 5 }"
        placeholder="填写复核意见/回复（1–5000 字符）"
        maxlength="5000"
      />
      <el-button
        type="primary" size="small" :loading="acting"
        :disabled="!draft.trim()"
        style="margin-top:6px"
        @click="onSend"
      >发送</el-button>
    </div>
    <div v-else class="gt-proc-review-panel__muted" style="margin-top:8px">
      仅当前参与者（{{ ROLE_TERMS.procedureAssignee }}/{{ ROLE_TERMS.operationReviewer }}/委派人）可发消息与关闭问题单。
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getProcedureConversation,
  postProcedureMessage,
  closeProcedureIssue,
  type ProcedureConversationView,
} from '@/services/commonApi'
import { handleApiError } from '@/utils/errorHandler'
import { ROLE_TERMS } from '@/components/workpaper/composables/procedureConsoleOverlay'

interface HighOrderReview {
  role_label: string
  reviewer_name?: string
  status?: string
  status_label?: string
}

const props = defineProps<{
  projectId: string
  taskId: string
  /** 可选：staff_id/user_id → 显示名映射（发送人展示）。 */
  nameMap?: Record<string, string>
  /** 可选：高阶复核只读状态（业务合伙人/QC/EQCR），由底稿/项目层机制提供。 */
  highOrderReviews?: HighOrderReview[]
}>()

const loading = ref(false)
const acting = ref(false)
const view = ref<ProcedureConversationView | null>(null)
const draft = ref('')

const messages = computed(() => view.value?.messages || [])
const issues = computed(() => view.value?.issues || [])
const openIssueCount = computed(() => view.value?.open_issue_count ?? 0)
// 历史只读参与者禁写；当前参与者（access != history_readonly 且 != none）可写。
const canWrite = computed(() => {
  const a = view.value?.access
  return !!a && a !== 'history_readonly' && a !== 'none'
})

function staffOrUserName(id: string | null | undefined): string {
  if (!id) return '—'
  return props.nameMap?.[id] || id.slice(0, 8)
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return ''
  try {
    const s = /Z|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : `${iso}Z`
    const d = new Date(s)
    if (Number.isNaN(d.getTime())) return iso
    const p = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
  } catch { return iso }
}

async function load() {
  if (!props.projectId || !props.taskId) return
  loading.value = true
  try {
    view.value = await getProcedureConversation(props.projectId, props.taskId)
  } catch (e: any) {
    handleApiError(e, '加载复核对话')
  } finally {
    loading.value = false
  }
}

async function onSend() {
  const text = draft.value.trim()
  if (!text) return
  acting.value = true
  try {
    await postProcedureMessage(props.projectId, props.taskId, text)
    draft.value = ''
    await load()
  } catch (e: any) {
    handleApiError(e, '发送消息')
  } finally {
    acting.value = false
  }
}

async function onCloseIssue(issueId: string) {
  acting.value = true
  try {
    await closeProcedureIssue(props.projectId, props.taskId, issueId)
    ElMessage.success('问题单已关闭')
    await load()
  } catch (e: any) {
    handleApiError(e, '关闭问题单')
  } finally {
    acting.value = false
  }
}

watch(() => [props.projectId, props.taskId], () => load())
onMounted(load)

defineExpose({ reload: load })
</script>

<style scoped>
.gt-proc-review-panel { padding: 4px 2px; font-size: 13px; }
.gt-proc-review-panel__head {
  display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;
}
.gt-proc-review-panel__title { display: flex; align-items: center; gap: 8px; font-weight: 600; }
.gt-proc-review-panel__scope { margin-bottom: 10px; }
.gt-proc-review-panel__section-label {
  font-size: 12px; font-weight: 600; color: var(--gt-color-text-secondary, #666); margin-bottom: 6px;
}
.gt-proc-review-panel__high-order {
  padding: 8px 10px; background: var(--gt-color-bg, #fafafa); border-radius: 6px;
  border: 1px dashed var(--gt-color-border-light, #e4e4e4);
}
.gt-proc-review-panel__high-order-rows { display: flex; flex-direction: column; gap: 6px; }
.gt-proc-review-panel__high-order-row { display: flex; align-items: center; gap: 8px; }
.gt-proc-review-panel__muted { color: var(--gt-color-text-placeholder, #aaa); font-size: 12px; }
.gt-proc-review-panel__issues { display: flex; flex-direction: column; gap: 6px; }
.gt-proc-review-panel__issue { display: flex; align-items: center; gap: 8px; }
.gt-proc-review-panel__issue-title { flex: 1; }
.gt-proc-review-panel__messages {
  max-height: 240px; overflow-y: auto; display: flex; flex-direction: column; gap: 8px;
  padding: 4px 0;
}
.gt-proc-review-panel__msg {
  padding: 6px 8px; background: var(--gt-color-bg-white, #fff);
  border: 1px solid var(--gt-color-border-light, #f0f0f0); border-radius: 6px;
}
.gt-proc-review-panel__msg-meta {
  display: flex; justify-content: space-between; font-size: 12px;
  color: var(--gt-color-text-tertiary, #999); margin-bottom: 2px;
}
.gt-proc-review-panel__msg-body { white-space: pre-wrap; line-height: 1.5; }
.gt-proc-review-panel__composer { margin-top: 10px; }
</style>
