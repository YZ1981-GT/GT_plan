<template>
  <div class="gt-wp-lifecycle">
    <!-- 两栏布局：左步骤导航 / 右内容区 -->
    <div class="gt-wp-lc-body">
      <!-- 左：步骤导航（紧凑） -->
      <div class="gt-wp-lc-stage-nav">
        <div class="gt-wp-lc-nav-title">审计生命周期</div>
        <div
          v-for="(s, i) in stages"
          :key="s.key"
          class="gt-wp-lc-nav-item"
          :class="{
            'is-current': i === currentIdx,
            'is-done': i < currentIdx || s.status === 'completed',
          }"
          @click="onStageClick(i)"
        >
          <span class="gt-wp-lc-nav-icon">
            <template v-if="i < currentIdx || s.status === 'completed'">✓</template>
            <template v-else>{{ i + 1 }}</template>
          </span>
          <div class="gt-wp-lc-nav-info">
            <div class="gt-wp-lc-nav-name">{{ s.label }}</div>
            <div class="gt-wp-lc-nav-progress">
              <el-progress
                :percentage="s.progress"
                :stroke-width="3"
                :show-text="false"
                :color="s.status === 'completed' ? '#67c23a' : '#6750A4'"
              />
              <span class="gt-wp-lc-nav-pct">{{ s.progress }}%</span>
            </div>
          </div>
        </div>
        <!-- 底部任务摘要 -->
        <div class="gt-wp-lc-nav-summary">
          <div class="gt-wp-lc-nav-summary__item" v-if="myTodos.length">
            <span class="gt-wp-lc-nav-summary__num">{{ myTodos.length }}</span>
            <span class="gt-wp-lc-nav-summary__label">待办任务</span>
          </div>
          <div class="gt-wp-lc-nav-summary__item gt-wp-lc-nav-summary__item--warn" v-if="overdueItems.length">
            <span class="gt-wp-lc-nav-summary__num">{{ overdueItems.length }}</span>
            <span class="gt-wp-lc-nav-summary__label">逾期项</span>
          </div>
        </div>
      </div>

      <!-- 右：阶段内容（宽） -->
      <div class="gt-wp-lc-content">
        <!-- 程序裁剪 -->
        <div v-if="currentKey === 'tailor'" class="gt-wp-lc-stage-content">
          <div class="gt-wp-lc-content-header">
            <h3 class="gt-wp-lc-h3">程序裁剪</h3>
            <el-tag size="small" :type="tailorStats.tailored > 0 ? 'success' : 'info'">
              {{ tailorStats.tailored }}/{{ tailorStats.total }} 已裁剪
            </el-tag>
            <el-button type="primary" size="small" @click="goToTailor" style="margin-left: auto">
              <el-icon style="margin-right: 4px"><Setting /></el-icon>配置裁剪
            </el-button>
          </div>
          <p class="gt-wp-lc-desc">合伙人/项目经理根据风险评估裁剪不适用的审计程序。未裁剪的循环底稿无法启动后续步骤。</p>

          <!-- 裁剪统计卡片（支持点击跳转） -->
          <div class="gt-wp-lc-tailor-grid">
            <div class="gt-wp-lc-tailor-stat gt-wp-lc-tailor-stat--clickable" @click="goToTailor">
              <div class="gt-wp-lc-tailor-stat__num">{{ tailorStats.total }}</div>
              <div class="gt-wp-lc-tailor-stat__label">总程序数</div>
            </div>
            <div class="gt-wp-lc-tailor-stat gt-wp-lc-tailor-stat--clickable" @click="goToTailor">
              <div class="gt-wp-lc-tailor-stat__num" style="color: var(--gt-color-success)">{{ tailorStats.tailored }}</div>
              <div class="gt-wp-lc-tailor-stat__label">已裁剪</div>
            </div>
            <div class="gt-wp-lc-tailor-stat gt-wp-lc-tailor-stat--clickable" @click="goToTailor">
              <div class="gt-wp-lc-tailor-stat__num" style="color: var(--gt-color-warning)">{{ tailorStats.total - tailorStats.tailored }}</div>
              <div class="gt-wp-lc-tailor-stat__label">保留执行</div>
            </div>
          </div>
        </div>

        <!-- 底稿生成 -->
        <div v-else-if="currentKey === 'generate'" class="gt-wp-lc-stage-content">
          <div class="gt-wp-lc-content-header">
            <h3 class="gt-wp-lc-h3">底稿生成</h3>
            <el-tag size="small" :type="generateStats.generated >= generateStats.expected ? 'success' : 'warning'">
              {{ generateStats.generated }}/{{ generateStats.expected }}
            </el-tag>
          </div>
          <p class="gt-wp-lc-desc">基于裁剪结果一键生成底稿、附注、报表，触发跨模块联动公式。</p>
          <div class="gt-wp-lc-action-row">
            <el-button
              type="primary"
              :loading="chainLoading"
              :disabled="generateStats.expected === 0"
              @click="onGenerateChain"
            >
              一键生成底稿+附注
            </el-button>
            <el-button @click="emit('refresh')">刷新</el-button>
          </div>
          <div v-if="recommendations.length" class="gt-wp-lc-card" style="margin-top: 12px">
            <h4 class="gt-wp-lc-h4">智能推荐</h4>
            <ul class="gt-wp-lc-rec-list">
              <li v-for="r in recommendations" :key="r.code">
                <el-tag size="small" type="info">{{ r.code }}</el-tag>
                <span class="gt-wp-lc-rec-name">{{ r.name }}</span>
              </li>
            </ul>
          </div>
        </div>

        <!-- 委派执行 -->
        <div v-else-if="currentKey === 'assign'" class="gt-wp-lc-stage-content">
          <div class="gt-wp-lc-content-header">
            <h3 class="gt-wp-lc-h3">委派执行</h3>
            <el-tag size="small" :type="assignStats.unassigned === 0 ? 'success' : 'warning'">
              {{ assignStats.assigned }}/{{ assignStats.total }} 已委派
            </el-tag>
          </div>
          <div class="gt-wp-lc-tailor-grid">
            <div class="gt-wp-lc-tailor-stat">
              <div class="gt-wp-lc-tailor-stat__num">{{ assignStats.total }}</div>
              <div class="gt-wp-lc-tailor-stat__label">总数</div>
            </div>
            <div class="gt-wp-lc-tailor-stat">
              <div class="gt-wp-lc-tailor-stat__num" style="color: var(--gt-color-success)">{{ assignStats.assigned }}</div>
              <div class="gt-wp-lc-tailor-stat__label">已委派</div>
            </div>
            <div class="gt-wp-lc-tailor-stat">
              <div class="gt-wp-lc-tailor-stat__num" style="color: var(--gt-color-warning)">{{ assignStats.unassigned }}</div>
              <div class="gt-wp-lc-tailor-stat__label">待委派</div>
            </div>
          </div>
          <p class="gt-wp-lc-desc">将底稿委派给具体审计员，未委派底稿不计入工作量分配。</p>
          <el-button type="primary" @click="emit('switch-view', 'matrix')">前往委派矩阵</el-button>
        </div>

        <!-- 编制 -->
        <div v-else-if="currentKey === 'compose'" class="gt-wp-lc-stage-content">
          <div class="gt-wp-lc-content-header">
            <h3 class="gt-wp-lc-h3">编制</h3>
            <el-tag size="small" :type="composeStats.percent === 100 ? 'success' : 'warning'">
              {{ composeStats.completed }}/{{ composeStats.total }}
            </el-tag>
          </div>
          <el-progress :percentage="composeStats.percent" :stroke-width="8" style="margin-bottom: 12px" />
          <div class="gt-wp-lc-filter-row">
            <el-radio-group v-model="composeFilter" size="small">
              <el-radio-button value="all">全部 ({{ composeStats.total }})</el-radio-button>
              <el-radio-button value="mine">我的 ({{ composeStats.mine }})</el-radio-button>
            </el-radio-group>
          </div>
          <div class="gt-wp-lc-list">
            <div
              v-for="w in filteredComposeList"
              :key="w.id"
              class="gt-wp-lc-list-item"
              @click="emit('open-workpaper', w.id)"
            >
              <span class="gt-wp-lc-li-code">{{ w.wp_code }}</span>
              <span class="gt-wp-lc-li-name">{{ w.wp_name }}</span>
              <el-tag size="small" :type="composeStatusType(w.status)">{{ composeStatusLabel(w.status) }}</el-tag>
            </div>
            <div v-if="filteredComposeList.length === 0" class="gt-wp-lc-empty">暂无编制中底稿</div>
          </div>
        </div>

        <!-- 复核 -->
        <div v-else-if="currentKey === 'review'" class="gt-wp-lc-stage-content">
          <div class="gt-wp-lc-content-header">
            <h3 class="gt-wp-lc-h3">复核</h3>
            <el-tag size="small" :type="reviewStats.pending > 0 ? 'warning' : 'success'">
              {{ reviewStats.pending }} 待复核
            </el-tag>
          </div>
          <p class="gt-wp-lc-desc">一级/二级复核流程，含批注、退回修改、强制通过等操作。</p>
          <el-button type="primary" @click="goToReviewWorkbench">前往复核工作台</el-button>
        </div>

        <!-- 归档 -->
        <div v-else-if="currentKey === 'archive'" class="gt-wp-lc-stage-content">
          <div class="gt-wp-lc-content-header">
            <h3 class="gt-wp-lc-h3">归档</h3>
            <el-tag size="small" :type="allGatesPassed ? 'success' : 'danger'">
              {{ allGatesPassed ? '条件满足' : '条件未满足' }}
            </el-tag>
          </div>
          <div class="gt-wp-lc-gate-list-wrap">
            <div v-for="g in archiveGates" :key="g.key" class="gt-wp-lc-gate-item">
              <span class="gt-wp-lc-gate-icon" :class="g.passed ? 'gt-success' : 'gt-warning'">
                {{ g.passed ? '✓' : '✗' }}
              </span>
              <span class="gt-wp-lc-gate-text">{{ g.label }}</span>
            </div>
          </div>
          <el-button
            type="primary"
            :disabled="!allGatesPassed"
            @click="goToArchive"
          >
            {{ allGatesPassed ? '执行归档' : '前置条件未满足' }}
          </el-button>
        </div>

        <!-- 我的待办任务（有待办时才显示面板） -->
        <div v-if="myTodos.length" class="gt-wp-lc-todo-panel">
          <div class="gt-wp-lc-todo-panel__header">
            <span class="gt-wp-lc-todo-panel__title">📋 我的待办</span>
            <el-tag size="small">{{ myTodos.length }}</el-tag>
          </div>
          <div class="gt-wp-lc-todo-panel__list">
            <div v-for="todo in myTodos.slice(0, 8)" :key="todo.id" class="gt-wp-lc-todo-panel__item"
              @click="emit('open-workpaper', todo.id)">
              <span class="gt-wp-lc-todo-panel__code">{{ todo.wp_code }}</span>
              <span class="gt-wp-lc-todo-panel__name">{{ todo.wp_name }}</span>
              <el-tag size="small" type="warning">{{ statusLabelShort(todo.status) }}</el-tag>
            </div>
          </div>
        </div>
        <!-- 无待办时的占位区（填充空白） -->
        <div v-else class="gt-wp-lc-todo-empty-placeholder">
          <div class="gt-wp-lc-todo-empty-placeholder__icon">✅</div>
          <div class="gt-wp-lc-todo-empty-placeholder__title">暂无待办任务</div>
          <div class="gt-wp-lc-todo-empty-placeholder__desc">当前阶段没有分配给您的底稿任务，可以查看其他阶段或协助团队成员</div>
        </div>

        <!-- 底部：逾期提醒（和当前步骤相关） -->
        <div v-if="overdueItems.length" class="gt-wp-lc-overdue-bar">
          <span class="gt-wp-lc-overdue-bar__icon">⚠️</span>
          <span class="gt-wp-lc-overdue-bar__text">{{ overdueItems.length }} 个底稿逾期</span>
          <div class="gt-wp-lc-overdue-bar__items">
            <span v-for="item in overdueItems.slice(0, 5)" :key="item.id" class="gt-wp-lc-overdue-bar__tag"
              @click="emit('open-workpaper', item.id)">
              {{ item.wp_code }} ({{ item.days }}天)
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Setting } from '@element-plus/icons-vue'
import http from '@/utils/http'
import { handleApiError } from '@/utils/errorHandler'
import { useAuthStore } from '@/stores/auth'

interface WpItem {
  id: string
  wp_code?: string
  wp_name?: string
  status: string
  review_status?: string
  assigned_to?: string | null
  reviewer?: string | null
  audit_cycle?: string
  wp_index_id?: string
}

const props = defineProps<{
  projectId: string
  workpapers: WpItem[]
  loading?: boolean
}>()

const emit = defineEmits<{
  'switch-view': [view: string]
  'open-workpaper': [wpId: string]
  'refresh': []
}>()

const router = useRouter()
const authStore = useAuthStore()

// 6 阶段定义
const stages = computed(() => [
  { key: 'tailor', label: '程序裁剪', shortLabel: '裁剪', status: tailorStatus.value, progress: tailorProgress.value },
  { key: 'generate', label: '底稿生成', shortLabel: '生成', status: generateStatus.value, progress: generateProgress.value },
  { key: 'assign', label: '委派执行', shortLabel: '委派', status: assignStatus.value, progress: assignProgress.value },
  { key: 'compose', label: '编制', shortLabel: '编制', status: composeStatus.value, progress: composeProgress.value },
  { key: 'review', label: '复核', shortLabel: '复核', status: reviewStatus.value, progress: reviewProgress.value },
  { key: 'archive', label: '归档', shortLabel: '归档', status: archiveStatus.value, progress: archiveProgress.value },
])

const currentIdx = ref(0)
const currentKey = computed(() => stages.value[currentIdx.value]?.key || 'tailor')

// SVG 流图布局
const flowWidth = 720
function circleX(i: number): number {
  const left = 60
  const right = flowWidth - 60
  return left + ((right - left) / (stages.value.length - 1)) * i
}

function circleFill(i: number, s: any): string {
  if (s.status === 'blocked') return 'var(--gt-color-coral)'
  if (i < currentIdx.value || s.status === 'completed') return 'var(--gt-color-success)'
  if (i === currentIdx.value) return 'var(--gt-color-primary)'
  return 'var(--gt-color-bg-white)'
}

function circleStroke(i: number, s: any): string {
  if (s.status === 'blocked') return 'var(--gt-color-coral)'
  if (i === currentIdx.value) return 'var(--gt-color-primary)'
  if (i < currentIdx.value || s.status === 'completed') return 'var(--gt-color-success)'
  return 'var(--gt-color-border)'
}

const STATUS_LABEL_MAP: Record<string, string> = {
  not_started: '待开始',
  in_progress: '进行中',
  completed: '已完成',
  blocked: '阻塞',
}

function statusLabel(status: string): string {
  return STATUS_LABEL_MAP[status] || status
}

const STATUS_SHORT_MAP: Record<string, string> = {
  draft: '待编',
  in_progress: '编制中',
  edit_complete: '已完成',
  pending_review: '待复核',
}

function statusLabelShort(s: string): string {
  return STATUS_SHORT_MAP[s] || s
}

const STATUS_TAG_MAP: Record<string, 'info' | 'primary' | 'success' | 'warning' | 'danger'> = {
  not_started: 'info',
  in_progress: 'warning',
  completed: 'success',
  blocked: 'danger',
}

function statusTagType(status: string): 'info' | 'primary' | 'success' | 'warning' | 'danger' {
  return STATUS_TAG_MAP[status] || 'info'
}

function onStageClick(i: number) {
  currentIdx.value = i
}

// ════════════════════════════════════════════════════════════
// 阶段 1：程序裁剪
// ════════════════════════════════════════════════════════════
const tailorStats = ref({ tailored: 0, total: 0 })

async function loadTailorStats() {
  try {
    const data: any = await http.get(`/api/projects/${props.projectId}/procedures/summary`, {
      validateStatus: (s: number) => s < 600,
    }).then(r => r.data)
    if (data && typeof data === 'object') {
      tailorStats.value = {
        tailored: Number(data.tailored_count || data.completed || 0),
        total: Number(data.total_count || data.total || 0),
      }
    }
  } catch {
    tailorStats.value = { tailored: 0, total: 0 }
  }
}

const tailorProgress = computed(() => {
  const t = tailorStats.value.total
  return t > 0 ? Math.round((tailorStats.value.tailored / t) * 100) : 0
})

const tailorStatus = computed<string>(() => {
  if (tailorStats.value.total === 0) return 'not_started'
  if (tailorStats.value.tailored >= tailorStats.value.total) return 'completed'
  return tailorStats.value.tailored > 0 ? 'in_progress' : 'not_started'
})

function goToTailor() {
  router.push(`/projects/${props.projectId}/procedures`)
}

// ════════════════════════════════════════════════════════════
// 阶段 2：底稿生成
// ════════════════════════════════════════════════════════════
const generateStats = computed(() => ({
  generated: props.workpapers.length,
  expected: Math.max(props.workpapers.length, tailorStats.value.total || props.workpapers.length),
}))

const generateProgress = computed(() => {
  const e = generateStats.value.expected
  return e > 0 ? Math.round((generateStats.value.generated / e) * 100) : 0
})

const generateStatus = computed<string>(() => {
  if (generateStats.value.generated === 0) return 'not_started'
  if (generateStats.value.generated >= generateStats.value.expected) return 'completed'
  return 'in_progress'
})

const recommendations = ref<Array<{ code: string; name: string }>>([])

async function loadRecommendations() {
  try {
    const data: any = await http.get(`/api/projects/${props.projectId}/ai/recommend-workpapers`, {
      validateStatus: (s: number) => s < 600,
    }).then(r => r.data)
    if (Array.isArray(data?.recommendations)) {
      recommendations.value = data.recommendations.slice(0, 5).map((r: any) => ({
        code: r.wp_code || r.code || '',
        name: r.wp_name || r.name || '',
      }))
    }
  } catch {
    recommendations.value = []
  }
}

const chainLoading = ref(false)
async function onGenerateChain() {
  chainLoading.value = true
  try {
    await http.post(
      `/api/projects/${props.projectId}/workflow/execute-full-chain`,
      { force: true },
      { timeout: 120000 },
    )
    ElMessage.success('已生成底稿+附注，正在刷新...')
    emit('refresh')
  } catch (e: any) {
    handleApiError(e, '一键生成')
  } finally {
    chainLoading.value = false
  }
}

// ════════════════════════════════════════════════════════════
// 阶段 3：委派执行
// ════════════════════════════════════════════════════════════
const assignStats = computed(() => {
  const total = props.workpapers.length
  const assigned = props.workpapers.filter(w => !!w.assigned_to).length
  return { total, assigned, unassigned: total - assigned }
})

const assignProgress = computed(() => {
  const t = assignStats.value.total
  return t > 0 ? Math.round((assignStats.value.assigned / t) * 100) : 0
})

const assignStatus = computed<string>(() => {
  if (assignStats.value.total === 0) return 'not_started'
  if (assignStats.value.assigned >= assignStats.value.total) return 'completed'
  return assignStats.value.assigned > 0 ? 'in_progress' : 'not_started'
})

// ════════════════════════════════════════════════════════════
// 阶段 4：编制
// ════════════════════════════════════════════════════════════
const COMPOSE_DONE = new Set(['edit_complete', 'pending_review', 'reviewed', 'review_passed', 'archived'])
const composeFilter = ref<'all' | 'mine'>('all')

const composeStats = computed(() => {
  const total = props.workpapers.length
  const completed = props.workpapers.filter(w => COMPOSE_DONE.has(w.status)).length
  const mine = props.workpapers.filter(w => w.assigned_to === authStore.userId).length
  return {
    total,
    completed,
    mine,
    percent: total > 0 ? Math.round((completed / total) * 100) : 0,
  }
})

const composeProgress = computed(() => composeStats.value.percent)

const composeStatus = computed<string>(() => {
  if (composeStats.value.total === 0) return 'not_started'
  if (composeStats.value.completed >= composeStats.value.total) return 'completed'
  return composeStats.value.completed > 0 ? 'in_progress' : 'not_started'
})

const filteredComposeList = computed(() => {
  const list = composeFilter.value === 'mine'
    ? props.workpapers.filter(w => w.assigned_to === authStore.userId)
    : props.workpapers
  return list.slice(0, 30)
})

const COMPOSE_LABEL_MAP: Record<string, string> = {
  draft: '待编',
  in_progress: '编制中',
  edit_complete: '已完成',
  pending_review: '待复核',
}

function composeStatusLabel(s: string): string {
  return COMPOSE_LABEL_MAP[s] || s
}

function composeStatusType(s: string): 'info' | 'success' | 'warning' | 'primary' {
  if (COMPOSE_DONE.has(s)) return 'success'
  if (s === 'in_progress') return 'warning'
  return 'info'
}

// ════════════════════════════════════════════════════════════
// 阶段 5：复核
// ════════════════════════════════════════════════════════════
const REVIEW_PENDING = new Set(['pending_review', 'pending_level1', 'pending_level2', 'level1_in_progress', 'level2_in_progress'])
const REVIEW_DONE = new Set(['reviewed', 'review_passed', 'archived', 'level1_passed', 'level2_passed'])

const reviewStats = computed(() => {
  const total = props.workpapers.length
  const pending = props.workpapers.filter(w =>
    REVIEW_PENDING.has(w.review_status || w.status)
  ).length
  const done = props.workpapers.filter(w =>
    REVIEW_DONE.has(w.review_status || w.status)
  ).length
  return { total, pending, done }
})

const reviewProgress = computed(() => {
  const t = reviewStats.value.total
  return t > 0 ? Math.round((reviewStats.value.done / t) * 100) : 0
})

const reviewStatus = computed<string>(() => {
  if (reviewStats.value.total === 0) return 'not_started'
  if (reviewStats.value.done >= reviewStats.value.total) return 'completed'
  return reviewStats.value.pending > 0 || reviewStats.value.done > 0 ? 'in_progress' : 'not_started'
})

function goToReviewWorkbench() {
  router.push({
    name: 'ReviewInbox',
    params: { projectId: props.projectId },
  })
}

// ════════════════════════════════════════════════════════════
// 阶段 6：归档
// ════════════════════════════════════════════════════════════
const archiveGates = computed(() => [
  {
    key: 'all_reviewed',
    label: '全部底稿复核通过',
    passed: reviewStats.value.total > 0 && reviewStats.value.done === reviewStats.value.total,
  },
  {
    key: 'no_pending',
    label: '无待处理批注',
    passed: reviewStats.value.pending === 0,
  },
  {
    key: 'all_assigned',
    label: '全部底稿已委派',
    passed: assignStats.value.unassigned === 0 && assignStats.value.total > 0,
  },
  {
    key: 'tailored',
    label: '程序裁剪已完成',
    passed: tailorStatus.value === 'completed',
  },
])

const allGatesPassed = computed(() => archiveGates.value.every(g => g.passed))

const archiveProgress = computed(() => {
  const passed = archiveGates.value.filter(g => g.passed).length
  return Math.round((passed / archiveGates.value.length) * 100)
})

const archiveStatus = computed<string>(() => {
  if (allGatesPassed.value) return 'completed'
  if (reviewStats.value.done > 0) return 'in_progress'
  return 'not_started'
})

function goToArchive() {
  router.push(`/projects/${props.projectId}/archive`)
}

// ════════════════════════════════════════════════════════════
// 右侧任务面板
// ════════════════════════════════════════════════════════════
const myTodos = computed(() => {
  const myId = authStore.userId
  if (!myId) return []
  return props.workpapers
    .filter(w => w.assigned_to === myId && !COMPOSE_DONE.has(w.status))
    .slice(0, 10)
    .map(w => ({
      id: w.id,
      wp_code: w.wp_code || '',
      wp_name: w.wp_name || '',
      status: w.status,
    }))
})

const overdueItems = ref<Array<{ id: string; wp_code: string; wp_name: string; days: number }>>([])

async function loadOverdue() {
  try {
    const data: any = await http.get(`/api/projects/${props.projectId}/workpapers/overdue`, {
      validateStatus: (s: number) => s < 600,
    }).then(r => r.data)
    const items = data?.items || data?.overdue || (Array.isArray(data) ? data : [])
    overdueItems.value = items.slice(0, 5).map((it: any) => ({
      id: it.id || it.wp_id,
      wp_code: it.wp_code || '',
      wp_name: it.wp_name || '',
      days: Number(it.overdue_days || it.days || 0),
    }))
  } catch {
    overdueItems.value = []
  }
}

function autoSelectStage() {
  const order = stages.value
  for (let i = 0; i < order.length; i++) {
    if (order[i].status !== 'completed') {
      currentIdx.value = i
      return
    }
  }
  currentIdx.value = order.length - 1
}

onMounted(async () => {
  await Promise.all([loadTailorStats(), loadRecommendations(), loadOverdue()])
  autoSelectStage()
})
</script>

<style scoped>
.gt-wp-lifecycle { display: flex; flex-direction: column; height: 100%; }

.gt-wp-lc-body { display: flex; gap: 16px; flex: 1; min-height: 0; }

/* 左侧步骤导航 */
.gt-wp-lc-stage-nav {
  width: 220px; min-width: 220px; background: var(--gt-color-bg-white);
  border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  padding: 16px 12px; display: flex; flex-direction: column; gap: 4px; overflow-y: auto;
}
.gt-wp-lc-nav-title {
  font-size: 14px; font-weight: 700; color: var(--gt-color-text-primary);
  padding: 0 8px 12px; border-bottom: 1px solid var(--gt-color-border-light, #f0f0f0);
  margin-bottom: 8px;
}
.gt-wp-lc-nav-item {
  display: flex; align-items: center; gap: 10px; padding: 10px 8px;
  border-radius: 8px; cursor: pointer; transition: all 0.15s;
  border-left: 3px solid transparent;
}
.gt-wp-lc-nav-item:hover { background: var(--gt-color-bg, #fafafa); }
.gt-wp-lc-nav-item.is-current {
  background: var(--gt-color-primary-bg, #f0ebff); border-left-color: var(--gt-color-primary);
}
.gt-wp-lc-nav-item.is-done .gt-wp-lc-nav-icon { background: var(--gt-color-success); }
.gt-wp-lc-nav-icon {
  width: 26px; height: 26px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  background: var(--gt-color-primary); color: #fff; font-size: 12px; font-weight: 700; flex-shrink: 0;
}
.gt-wp-lc-nav-info { flex: 1; min-width: 0; }
.gt-wp-lc-nav-name { font-size: 13px; font-weight: 600; color: var(--gt-color-text-primary); margin-bottom: 4px; }
.gt-wp-lc-nav-progress { display: flex; align-items: center; gap: 8px; }
.gt-wp-lc-nav-pct { font-size: 11px; color: var(--gt-color-text-tertiary); white-space: nowrap; }

/* 底部任务摘要 */
.gt-wp-lc-nav-summary {
  margin-top: auto; padding-top: 12px; border-top: 1px solid var(--gt-color-border-light, #f0f0f0);
  display: flex; gap: 12px; justify-content: center;
}
.gt-wp-lc-nav-summary__item { text-align: center; }
.gt-wp-lc-nav-summary__num { display: block; font-size: 18px; font-weight: 700; color: var(--gt-color-primary); }
.gt-wp-lc-nav-summary__label { font-size: 11px; color: var(--gt-color-text-tertiary); }
.gt-wp-lc-nav-summary__item--warn .gt-wp-lc-nav-summary__num { color: var(--gt-color-coral); }

/* 右侧内容区 */
.gt-wp-lc-content {
  flex: 1; background: var(--gt-color-bg-white); border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04); padding: 24px; overflow-y: auto;
  display: flex; flex-direction: column;
}
.gt-wp-lc-stage-content { display: flex; flex-direction: column; gap: 16px; }
.gt-wp-lc-content-header { display: flex; align-items: center; gap: 12px; }
.gt-wp-lc-h3 { margin: 0; font-size: 18px; color: var(--gt-color-primary); font-weight: 700; }
.gt-wp-lc-h4 { margin: 0 0 8px; font-size: 14px; color: var(--gt-color-text-primary); font-weight: 600; }
.gt-wp-lc-desc { font-size: 13px; color: var(--gt-color-text-secondary); line-height: 1.6; margin: 0; }
.gt-wp-lc-action-row { display: flex; gap: 8px; }

/* 裁剪/委派统计网格 */
.gt-wp-lc-tailor-grid {
  display: flex; gap: 16px; padding: 16px; background: var(--gt-color-bg, #fafafa);
  border-radius: 10px; border: 1px solid var(--gt-color-border-light, #f0f0f0);
}
.gt-wp-lc-tailor-stat { flex: 1; text-align: center; }
.gt-wp-lc-tailor-stat--clickable { cursor: pointer; border-radius: 8px; padding: 12px 8px; transition: all 0.15s; }
.gt-wp-lc-tailor-stat--clickable:hover { background: rgba(103, 80, 164, 0.06); }
.gt-wp-lc-tailor-stat--action { display: flex; align-items: center; justify-content: center; }
.gt-wp-lc-tailor-stat__num { font-size: 28px; font-weight: 800; color: var(--gt-color-primary); line-height: 1.2; }
.gt-wp-lc-tailor-stat__label { font-size: 12px; color: var(--gt-color-text-tertiary); margin-top: 4px; }

/* 卡片 */
.gt-wp-lc-card {
  background: var(--gt-color-bg, #fafafa); border: 1px solid var(--gt-color-border-light, #f0f0f0);
  border-radius: 10px; padding: 16px;
}
.gt-wp-lc-rec-list { list-style: none; padding: 0; margin: 0; }
.gt-wp-lc-rec-list li { display: flex; align-items: center; gap: 6px; padding: 4px 0; font-size: 13px; }
.gt-wp-lc-rec-name { color: var(--gt-color-text-primary); }
.gt-wp-lc-filter-row { margin-bottom: 12px; }

/* 底稿列表 */
.gt-wp-lc-list { max-height: 360px; overflow-y: auto; }
.gt-wp-lc-list-item {
  display: flex; align-items: center; gap: 8px; padding: 8px 10px;
  border-radius: 6px; cursor: pointer; border-bottom: 1px solid var(--gt-color-border-light, #f0f0f0);
  transition: background 0.15s;
}
.gt-wp-lc-list-item:hover { background: var(--gt-color-primary-bg, #f8f5ff); }
.gt-wp-lc-li-code { font-weight: 600; color: var(--gt-color-primary); min-width: 50px; font-size: 13px; }
.gt-wp-lc-li-name { flex: 1; color: var(--gt-color-text-primary); font-size: 13px; }
.gt-wp-lc-empty { text-align: center; color: var(--gt-color-text-tertiary); font-size: 13px; padding: 24px; }

/* 归档门禁 */
.gt-wp-lc-gate-list-wrap { display: flex; flex-direction: column; gap: 6px; margin-bottom: 16px; }
.gt-wp-lc-gate-item {
  display: flex; align-items: center; gap: 10px; padding: 8px 12px;
  border-radius: 6px; background: var(--gt-color-bg, #fafafa); font-size: 13px;
}
.gt-wp-lc-gate-icon {
  width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  font-weight: 700; font-size: 12px;
}
.gt-wp-lc-gate-icon.gt-success { background: var(--gt-color-success); color: #fff; }
.gt-wp-lc-gate-icon.gt-warning { background: var(--gt-color-coral); color: #fff; }
.gt-wp-lc-gate-text { color: var(--gt-color-text-primary); }

/* 我的待办面板 */
.gt-wp-lc-todo-panel {
  margin-top: 24px; padding: 16px 20px; background: linear-gradient(135deg, #f8f5ff 0%, #f0ebff 100%);
  border-radius: 12px; border: 1px solid rgba(103, 80, 164, 0.12);
  max-width: 600px; margin-left: auto; margin-right: auto;
}
.gt-wp-lc-todo-panel--empty {
  display: flex; align-items: center; justify-content: center; padding: 24px;
  background: var(--gt-color-bg, #fafafa); border-color: var(--gt-color-border-light, #f0f0f0);
}
.gt-wp-lc-todo-panel__empty-text { font-size: 13px; color: var(--gt-color-text-tertiary); }
.gt-wp-lc-todo-panel__header {
  display: flex; align-items: center; gap: 8px; margin-bottom: 12px;
  padding-bottom: 10px; border-bottom: 1px solid rgba(103, 80, 164, 0.1);
}
.gt-wp-lc-todo-panel__title { font-size: 14px; font-weight: 600; color: var(--gt-color-primary); }
.gt-wp-lc-todo-panel__list { display: flex; flex-direction: column; gap: 6px; }
.gt-wp-lc-todo-panel__item {
  display: flex; align-items: center; gap: 8px; padding: 8px 12px;
  border-radius: 8px; cursor: pointer; transition: all 0.15s;
  background: rgba(255,255,255,0.7); border: 1px solid rgba(103, 80, 164, 0.08);
}
.gt-wp-lc-todo-panel__item:hover { background: #fff; border-color: var(--gt-color-primary); box-shadow: 0 2px 8px rgba(103, 80, 164, 0.1); }
.gt-wp-lc-todo-panel__code { font-size: 12px; font-weight: 700; color: var(--gt-color-primary); min-width: 40px; }
.gt-wp-lc-todo-panel__name { flex: 1; font-size: 13px; color: var(--gt-color-text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* 无待办占位区 */
.gt-wp-lc-todo-empty-placeholder {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  margin-top: 16px; padding: 60px; text-align: center;
  background: var(--gt-color-bg, #fafafa); border-radius: 12px;
  border: 1px dashed var(--gt-color-border-light, #e0e0e0);
}
.gt-wp-lc-todo-empty-placeholder__icon { font-size: 32px; margin-bottom: 10px; opacity: 0.6; }
.gt-wp-lc-todo-empty-placeholder__title { font-size: 14px; font-weight: 600; color: var(--gt-color-text-tertiary); margin-bottom: 4px; }
.gt-wp-lc-todo-empty-placeholder__desc { font-size: 12px; color: var(--gt-color-text-placeholder); max-width:300px; line-height: 1.5; }

/* 逾期提醒条 */
.gt-wp-lc-overdue-bar {
  margin-top: auto; padding: 12px 16px; background: #fff8e1; border-radius: 8px;
  border: 1px solid #ffe082; display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}
.gt-wp-lc-overdue-bar__icon { font-size: 16px; }
.gt-wp-lc-overdue-bar__text { font-size: 13px; font-weight: 600; color: #e65100; }
.gt-wp-lc-overdue-bar__items { display: flex; gap: 6px; flex-wrap: wrap; }
.gt-wp-lc-overdue-bar__tag {
  padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;
  background: #fff3e0; color: #e65100; cursor: pointer;
}
.gt-wp-lc-overdue-bar__tag:hover { background: #ffe0b2; }
</style>
