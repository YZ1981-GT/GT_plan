<template>
  <div class="gt-my-proc gt-fade-in">
    <GtPageHeader title="我的工作" variant="banner" icon="📋" :show-back="false">
      <template #subtitle>
        <span v-if="mainView === 'tasks' && page.pagination.total">
          共 {{ page.pagination.total }} 项 · {{ overdueCount }} 逾期
        </span>
      </template>
    </GtPageHeader>

    <!-- 两个独立身份视图分区（Req 11.10–11.13）：
         「我的程序任务」= 程序行执行人/操作复核人；「我的主编底稿」= 底稿主编。两者互不合成。 -->
    <div class="gt-proc-viewswitch">
      <el-radio-group v-model="mainView" size="default">
        <el-radio-button label="tasks">我的程序任务</el-radio-button>
        <el-radio-button label="lead">我的主编底稿</el-radio-button>
      </el-radio-group>
      <el-tooltip
        content="程序任务 = 你作为程序执行人/操作复核人的行任务；主编底稿 = 你作为底稿主编负责的整张底稿。两者是不同委派层，分开展示。"
        placement="top"
      >
        <span class="gt-proc-viewswitch__hint">ⓘ 两层委派分区</span>
      </el-tooltip>
    </div>

    <!-- ── 我的主编底稿（MyLeadWorkpapers 独立身份视图）── -->
    <div v-if="mainView === 'lead'" class="gt-proc-lead">
      <div class="gt-proc-lead__proj">
        <span class="gt-proc-lead__proj-label">项目</span>
        <el-select v-model="leadProjectId" placeholder="选择项目" filterable size="small" style="width: 260px">
          <el-option v-for="p in projectList" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
      </div>
      <MyLeadWorkpapers v-if="leadProjectId" :project-id="leadProjectId" />
      <GtEmpty v-else preset="no-data" title="请选择项目" description="选择项目后查看你主编的底稿" />
    </div>

    <!-- ── 我的程序任务（Row_Assignee / Operation_Reviewer）── -->
    <template v-else>
    <!-- 我执行的 / 我复核的 -->
    <div class="gt-proc-toolbar">
      <el-radio-group v-model="role" size="default" @change="onRoleChange">
        <el-radio-button label="assignee">我执行的</el-radio-button>
        <el-radio-button label="reviewer">我复核的</el-radio-button>
      </el-radio-group>

      <div class="gt-proc-filters">
        <el-select v-model="filters.cycle" placeholder="全部循环" clearable size="small"
          style="width: 150px" @change="reload">
          <el-option v-for="c in cycleOptions" :key="c" :label="cycleName(c)" :value="c" />
        </el-select>
        <el-select v-model="filters.workflowStatus" placeholder="全部状态" clearable size="small"
          style="width: 130px" @change="reload">
          <el-option v-for="(label, val) in WORKFLOW_LABELS" :key="val" :label="label" :value="val" />
        </el-select>
        <el-checkbox v-model="filters.overdueOnly" @change="reload">仅看逾期</el-checkbox>
        <el-button size="small" :icon="RefreshIcon" @click="reload">刷新</el-button>
      </div>
    </div>

    <GtEmpty v-if="!page.items.length && !loading" preset="no-data"
      :title="role === 'assignee' ? '暂无待执行的程序任务' : '暂无待复核的程序任务'"
      description="请联系项目经理委派，或调整筛选条件" />

    <div v-for="group in groupedTasks" :key="group.projectId" style="margin-bottom: 20px">
      <h3 class="gt-proc-group-title">
        {{ group.projectName }}
        <el-tag size="small" style="margin-left: 8px">{{ group.rows.length }} 项</el-tag>
      </h3>
      <el-table :data="group.rows" border size="small" stripe>
        <el-table-column prop="wp_code" label="底稿" width="90" />
        <el-table-column prop="audit_cycle_snapshot" label="循环" width="70" align="center">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.audit_cycle_snapshot }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="程序" min-width="240">
          <template #default="{ row }">
            <span>{{ row.program_no ? `${row.program_no}. ` : '' }}{{ row.procedure_text || row.sheet_name || row.definition_key }}</span>
          </template>
        </el-table-column>
        <el-table-column label="关联底稿" width="140" align="center">
          <template #default="{ row }">
            <el-button v-if="row.wp_id" link type="primary" size="small" @click="openDeepLink(row)">
              打开底稿
            </el-button>
            <el-tooltip v-else content="程序已委派，底稿尚未生成，生成后可执行" placement="top">
              <el-tag size="small" type="info" effect="plain">底稿尚未生成</el-tag>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="statusTagType(row.workflow_status)">
              {{ WORKFLOW_LABELS[row.workflow_status] || row.workflow_status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="截止" width="120" align="center">
          <template #default="{ row }">
            <span v-if="row.due_at" :class="{ 'gt-overdue': row.overdue }">
              {{ fmtDate(row.due_at) }}
              <el-tag v-if="row.overdue" size="small" type="danger" effect="dark" style="margin-left:4px">逾期</el-tag>
            </span>
            <span v-else style="color: var(--gt-color-text-placeholder)">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" align="center">
          <template #default="{ row }">
            <template v-for="action in rowActions(row)" :key="action.key">
              <el-button size="small" :type="action.type" link @click="runAction(row, action.key)">
                {{ action.label }}
              </el-button>
            </template>
            <span v-if="!rowActions(row).length" style="color: var(--gt-color-text-placeholder)">—</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-pagination v-if="page.pagination.total > page.pagination.page_size"
      layout="prev, pager, next, total" :total="page.pagination.total"
      :page-size="page.pagination.page_size" :current-page="page.pagination.page"
      style="margin-top: 16px; justify-content: flex-end" @current-change="onPageChange" />

    <!-- 提交复核对话框：执行说明 + 证据引用（Req 6.7 非空校验） -->
    <el-dialog v-model="submitDialog.visible" title="提交复核" width="520px">
      <el-form label-width="90px">
        <el-form-item label="执行说明" required>
          <el-input v-model="submitDialog.summary" type="textarea" :autosize="{ minRows: 4 }"
            placeholder="请说明本程序的执行过程与结论" />
        </el-form-item>
        <el-form-item label="证据引用" required>
          <el-input v-model="submitDialog.evidence"
            placeholder="填写底稿/附件索引，多个用逗号分隔，如 D2-1, 附件3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="submitDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="acting" @click="confirmSubmit">提交</el-button>
      </template>
    </el-dialog>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { onProcedureTaskRefresh } from '@/composables/useProcedureTaskSse'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh as RefreshIcon } from '@element-plus/icons-vue'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import GtEmpty from '@/components/common/GtEmpty.vue'
import MyLeadWorkpapers from '@/views/MyLeadWorkpapers.vue'
import {
  listMyProcedureRowTasks,
  transitionProcedureRowTask,
  listProjects,
  type ProcedureRowTaskItem,
  type ProcedureRowTaskPage,
  type ProcedureRowTaskTransition,
} from '@/services/commonApi'
import { handleApiError } from '@/utils/errorHandler'
import { isExternalNotFound, EXTERNAL_NOT_FOUND_MESSAGE } from '@/utils/visibilityAccess'

const router = useRouter()
const loading = ref(false)
const acting = ref(false)
const role = ref<'assignee' | 'reviewer'>('assignee')
const projectNames = ref<Record<string, string>>({})

// 两个独立身份视图分区（Req 11.10–11.13）
const mainView = ref<'tasks' | 'lead'>('tasks')
const leadProjectId = ref('')
const projectList = ref<{ id: string; name: string }[]>([])

const page = reactive<ProcedureRowTaskPage>({
  items: [],
  pagination: { page: 1, page_size: 20, total: 0, total_pages: 0 },
})

const filters = reactive<{ cycle: string; workflowStatus: string; overdueOnly: boolean }>({
  cycle: '',
  workflowStatus: '',
  overdueOnly: false,
})

const CYCLE_NAMES: Record<string, string> = {
  A: 'A 完成阶段', B: 'B 计划阶段', C: 'C 风险评估', D: 'D 销售循环', E: 'E 货币资金',
  F: 'F 存货循环', G: 'G 投资循环', H: 'H 固定资产', I: 'I 无形资产', J: 'J 薪酬循环',
  K: 'K 费用循环', L: 'L 债务循环', M: 'M 权益循环', N: 'N 税金循环', S: 'S 特殊事项', Q: 'Q 关联方',
}
const cycleOptions = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'S', 'Q']

const WORKFLOW_LABELS: Record<string, string> = {
  unassigned: '未分配', assigned: '待确认', acknowledged: '已确认', in_progress: '进行中',
  submitted: '待复核', changes_requested: '已退回', reviewed: '已复核', cancelled: '已取消',
}

function cycleName(c: string) { return CYCLE_NAMES[c] || `${c} 循环` }

function statusTagType(status: string): string {
  switch (status) {
    case 'reviewed': return 'success'
    case 'submitted': return 'warning'
    case 'changes_requested': return 'danger'
    case 'cancelled': return 'info'
    case 'in_progress': return 'primary'
    default: return ''
  }
}

function fmtDate(iso: string): string {
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  } catch { return iso }
}

const overdueCount = computed(() => page.items.filter(t => t.overdue).length)

const groupedTasks = computed(() => {
  const groups: Record<string, ProcedureRowTaskItem[]> = {}
  for (const t of page.items) {
    if (!groups[t.project_id]) groups[t.project_id] = []
    groups[t.project_id].push(t)
  }
  return Object.entries(groups).map(([projectId, rows]) => ({
    projectId,
    projectName: projectNames.value[projectId] || `项目 ${projectId.slice(0, 8)}`,
    rows,
  }))
})

// 依 my_role + workflow_status 决定可用状态动作（调用 transition API，非 updateProcedureTrim）
function rowActions(row: ProcedureRowTaskItem): { key: string; label: string; type: string }[] {
  const acts: { key: string; label: string; type: string }[] = []
  if (row.applicability_status !== 'execute') return acts
  if (row.my_role === 'assignee') {
    if (row.workflow_status === 'assigned') acts.push({ key: 'acknowledge', label: '确认接收', type: 'primary' })
    else if (row.workflow_status === 'acknowledged') acts.push({ key: 'start', label: '开始执行', type: 'primary' })
    else if (row.workflow_status === 'changes_requested') acts.push({ key: 'start', label: '继续修改', type: 'warning' })
    else if (row.workflow_status === 'in_progress') acts.push({ key: 'submit', label: '提交复核', type: 'success' })
  } else if (row.my_role === 'reviewer') {
    if (row.workflow_status === 'submitted') {
      acts.push({ key: 'review', label: '复核通过', type: 'success' })
      acts.push({ key: 'request_changes', label: '退回', type: 'danger' })
    }
  }
  return acts
}

function reqId(): string {
  const c: any = (globalThis as any).crypto
  if (c?.randomUUID) return c.randomUUID()
  return `req-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function buildTransition(row: ProcedureRowTaskItem, action: string, extra: Partial<ProcedureRowTaskTransition> = {}): ProcedureRowTaskTransition {
  const body: ProcedureRowTaskTransition = {
    action: action as ProcedureRowTaskTransition['action'],
    request_id: reqId(),
    expected_lock_version: row.lock_version,
    ...extra,
  }
  // acknowledge 额外校验 assignment_version（重新确认门槛）
  if (action === 'acknowledge') body.expected_assignment_version = row.assignment_version
  return body
}

const submitDialog = reactive<{ visible: boolean; summary: string; evidence: string; row: ProcedureRowTaskItem | null }>({
  visible: false, summary: '', evidence: '', row: null,
})

async function runAction(row: ProcedureRowTaskItem, action: string) {
  if (action === 'submit') {
    submitDialog.row = row
    submitDialog.summary = ''
    submitDialog.evidence = ''
    submitDialog.visible = true
    return
  }
  if (action === 'request_changes') {
    try {
      const { value } = await ElMessageBox.prompt('请填写退回原因', '退回修改', {
        inputType: 'textarea',
        inputValidator: (v: string) => (v && v.trim().length >= 1) || '退回原因必填',
      })
      await doTransition(row, buildTransition(row, 'request_changes', { reason: value.trim() }))
    } catch { /* 用户取消 */ }
    return
  }
  if (action === 'review') {
    try {
      await ElMessageBox.confirm('确认本程序一级复核通过？', '复核通过', { type: 'success' })
      await doTransition(row, buildTransition(row, 'review'))
    } catch { /* 取消 */ }
    return
  }
  // acknowledge / start：直接转换
  await doTransition(row, buildTransition(row, action))
}

async function confirmSubmit() {
  const row = submitDialog.row
  if (!row) return
  const summary = submitDialog.summary.trim()
  const evidence = submitDialog.evidence.split(',').map(s => s.trim()).filter(Boolean)
  if (!summary) { ElMessage.warning('执行说明必填'); return }
  if (!evidence.length) { ElMessage.warning('证据引用必填'); return }
  const ok = await doTransition(row, buildTransition(row, 'submit', {
    execution_summary: summary,
    evidence_snapshot: evidence,
  }))
  if (ok) submitDialog.visible = false
}

async function doTransition(row: ProcedureRowTaskItem, body: ProcedureRowTaskTransition): Promise<boolean> {
  acting.value = true
  try {
    await transitionProcedureRowTask(row.project_id, row.task_id, body)
    ElMessage.success('操作成功')
    await loadTasks()
    return true
  } catch (e: any) {
    // 409（版本/状态冲突）需刷新后重试
    if (e?.response?.status === 409) {
      ElMessage.warning('任务状态已变化，请刷新后重试')
      await loadTasks()
    } else if (isExternalNotFound(e)) {
      // 任务不再可见/不存在（撤权、跨项目、越权）：统一占位文案 + 刷新清理陈旧行（Req 12.7）
      ElMessage.warning(EXTERNAL_NOT_FOUND_MESSAGE)
      await loadTasks()
    } else {
      handleApiError(e, '操作')
    }
    return false
  } finally {
    acting.value = false
  }
}

// 深链：有 wp_id 才构造链接，携带 task_id + sheet_key + definition_key（Req 9.6）
function openDeepLink(row: ProcedureRowTaskItem) {
  if (!row.wp_id) return
  router.push({
    path: `/projects/${row.project_id}/workpapers`,
    query: {
      wp: row.wp_id,
      task_id: row.task_id,
      sheet_key: row.sheet_key,
      definition_key: row.definition_key,
    },
  })
}

function onRoleChange() { reload() }
function onPageChange(p: number) { loadTasks(p) }
function reload() { loadTasks(1) }

async function loadTasks(targetPage?: number) {
  loading.value = true
  try {
    const res = await listMyProcedureRowTasks({
      role: role.value,
      cycle: filters.cycle || undefined,
      workflowStatus: filters.workflowStatus || undefined,
      overdueOnly: filters.overdueOnly || undefined,
      page: targetPage ?? page.pagination.page,
      pageSize: page.pagination.page_size,
    })
    page.items = res?.items || []
    page.pagination = res?.pagination || { page: 1, page_size: 20, total: 0, total_pages: 0 }
  } catch (e: any) {
    handleApiError(e, '加载')
  } finally {
    loading.value = false
  }
}

async function loadProjectNames() {
  try {
    const projects = await listProjects()
    const map: Record<string, string> = {}
    const opts: { id: string; name: string }[] = []
    for (const p of projects) {
      const pid = p.id || p.project_id
      const name = p.project_name || p.client_name || p.name || ''
      map[pid] = name
      if (pid) opts.push({ id: pid, name: name || `项目 ${String(pid).slice(0, 8)}` })
    }
    projectNames.value = map
    projectList.value = opts
    // 主编底稿视图默认选中第一个项目
    if (!leadProjectId.value && opts.length) leadProjectId.value = opts[0].id
  } catch { /* 项目名映射失败不阻断任务列表 */ }
}

// Task 11 / Req 10.6：收到新程序任务 SSE 事件（event_id 幂等去重后）重新拉取任务列表，
// 即使 SSE 丢失/重复也通过 API 拉取收敛（不把 SSE payload 当状态真源）。
let disposeSse: (() => void) | null = null

onMounted(async () => {
  await Promise.all([loadProjectNames(), loadTasks(1)])
  disposeSse = onProcedureTaskRefresh(() => { loadTasks() })
})

onUnmounted(() => {
  if (disposeSse) disposeSse()
})
</script>

<style scoped>
.gt-my-proc { padding: 0; }
.gt-proc-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  flex-wrap: wrap; gap: 12px; margin-bottom: 16px;
}
.gt-proc-filters { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.gt-proc-viewswitch {
  display: flex; align-items: center; gap: 12px; margin-bottom: 16px;
}
.gt-proc-viewswitch__hint {
  font-size: 12px; color: var(--gt-color-text-tertiary); cursor: help;
}
.gt-proc-lead { margin-top: 4px; }
.gt-proc-lead__proj {
  display: flex; align-items: center; gap: 10px; margin-bottom: 14px;
}
.gt-proc-lead__proj-label {
  font-size: 13px; color: var(--gt-color-text-secondary);
}
.gt-proc-group-title {
  font-size: var(--gt-font-size-base); color: var(--gt-color-primary); margin-bottom: 8px;
}
.gt-overdue { color: var(--gt-color-danger, #f56c6c); font-weight: 600; }
.gt-page-banner {
  display: flex; justify-content: space-between; align-items: center;
  padding: 20px 24px; margin-bottom: 16px;
  background: linear-gradient(135deg, var(--gt-color-primary, #4b2d77) 0%, #6b4d97 100%);
  border-radius: 8px; color: var(--gt-color-text-inverse);
}
</style>
