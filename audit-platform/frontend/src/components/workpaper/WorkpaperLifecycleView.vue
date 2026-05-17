<template>
  <div class="gt-wp-lifecycle">
    <!-- 顶部 SVG 阶段流（6 圆 + 5 箭头） -->
    <div class="gt-wp-lc-flow">
      <svg :viewBox="`0 0 ${flowWidth} 90`" class="gt-wp-lc-svg" preserveAspectRatio="xMidYMid meet">
        <!-- 连接线 -->
        <g v-for="(s, i) in stages" :key="`line-${s.key}`">
          <line
            v-if="i < stages.length - 1"
            :x1="circleX(i) + 24"
            :y1="45"
            :x2="circleX(i + 1) - 24"
            :y2="45"
            :stroke="i < currentIdx ? 'var(--gt-color-success)' : 'var(--gt-color-border)'"
            stroke-width="2"
          />
          <polygon
            v-if="i < stages.length - 1"
            :points="`${circleX(i + 1) - 24},45 ${circleX(i + 1) - 30},41 ${circleX(i + 1) - 30},49`"
            :fill="i < currentIdx ? 'var(--gt-color-success)' : 'var(--gt-color-border)'"
          />
        </g>
        <!-- 阶段圆 -->
        <g
          v-for="(s, i) in stages"
          :key="s.key"
          class="gt-wp-lc-stage-circle"
          :class="{
            'gt-lc-current': i === currentIdx,
            'gt-lc-done': i < currentIdx || s.status === 'completed',
            'gt-lc-blocked': s.status === 'blocked',
          }"
          @click="onStageClick(i)"
        >
          <circle
            :cx="circleX(i)"
            :cy="45"
            :r="22"
            :fill="circleFill(i, s)"
            :stroke="circleStroke(i, s)"
            :stroke-width="i === currentIdx ? 3 : 2"
          />
          <text
            :x="circleX(i)"
            :y="51"
            text-anchor="middle"
            :fill="i === currentIdx ? 'var(--gt-color-text-inverse)' : (i < currentIdx || s.status === 'completed' ? 'var(--gt-color-text-inverse)' : 'var(--gt-color-text-secondary)')"
            font-size="14"
            font-weight="700"
          >
            <template v-if="i < currentIdx || s.status === 'completed'">✓</template>
            <template v-else>{{ i + 1 }}</template>
          </text>
          <text
            :x="circleX(i)"
            :y="82"
            text-anchor="middle"
            :fill="i === currentIdx ? 'var(--gt-color-primary)' : 'var(--gt-color-text-secondary)'"
            font-size="12"
            :font-weight="i === currentIdx ? 700 : 400"
          >
            {{ s.shortLabel }}
          </text>
        </g>
      </svg>
    </div>

    <!-- 三栏布局：左阶段列表 / 中阶段内容 / 右任务面板 -->
    <div class="gt-wp-lc-body">
      <!-- 左：阶段列表 -->
      <div class="gt-wp-lc-stage-list">
        <div
          v-for="(s, i) in stages"
          :key="s.key"
          class="gt-wp-lc-stage-item"
          :class="{ 'is-current': i === currentIdx }"
          @click="onStageClick(i)"
        >
          <span class="gt-wp-lc-stage-no">{{ i + 1 }}</span>
          <div class="gt-wp-lc-stage-info">
            <div class="gt-wp-lc-stage-name">{{ s.label }}</div>
            <div class="gt-wp-lc-stage-meta">
              <el-tag
                size="small"
                :type="statusTagType(s.status)"
              >
                {{ statusLabel(s.status) }}
              </el-tag>
              <span class="gt-wp-lc-stage-pct">{{ s.progress }}%</span>
            </div>
            <el-progress
              :percentage="s.progress"
              :stroke-width="4"
              :show-text="false"
              :color="s.status === 'completed' ? 'var(--gt-color-success)' : 'var(--gt-color-primary)'"
            />
          </div>
        </div>
      </div>

      <!-- 中：阶段内容 -->
      <div class="gt-wp-lc-content">
        <!-- 程序裁剪 -->
        <div v-if="currentKey === 'tailor'" class="gt-wp-lc-stage-content">
          <h3 class="gt-wp-lc-h3">1. 程序裁剪</h3>
          <div class="gt-wp-lc-card">
            <div class="gt-wp-lc-card-stat">
              <span class="gt-wp-lc-stat-num">{{ tailorStats.tailored }}</span>
              <span class="gt-wp-lc-stat-divider">/</span>
              <span class="gt-wp-lc-stat-total">{{ tailorStats.total }}</span>
              <span class="gt-wp-lc-stat-label">程序已裁剪</span>
            </div>
            <p class="gt-wp-lc-desc">合伙人/项目经理根据风险评估裁剪审计程序，未裁剪的循环底稿无法启动后续步骤。</p>
            <el-button type="primary" @click="goToTailor">前往裁剪页</el-button>
          </div>
        </div>

        <!-- 底稿生成 -->
        <div v-else-if="currentKey === 'generate'" class="gt-wp-lc-stage-content">
          <h3 class="gt-wp-lc-h3">2. 底稿生成</h3>
          <div class="gt-wp-lc-card">
            <div class="gt-wp-lc-card-stat">
              <span class="gt-wp-lc-stat-num">{{ generateStats.generated }}</span>
              <span class="gt-wp-lc-stat-divider">/</span>
              <span class="gt-wp-lc-stat-total">{{ generateStats.expected }}</span>
              <span class="gt-wp-lc-stat-label">底稿已生成</span>
            </div>
            <p class="gt-wp-lc-desc">基于裁剪结果一键生成底稿、附注、报表，触发跨模块联动公式。</p>
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
          <div v-if="recommendations.length" class="gt-wp-lc-card">
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
          <h3 class="gt-wp-lc-h3">3. 委派执行</h3>
          <div class="gt-wp-lc-card">
            <div class="gt-wp-lc-stat-row">
              <div class="gt-wp-lc-stat-cell">
                <div class="gt-wp-lc-stat-cell-num">{{ assignStats.total }}</div>
                <div class="gt-wp-lc-stat-cell-label">总数</div>
              </div>
              <div class="gt-wp-lc-stat-cell">
                <div class="gt-wp-lc-stat-cell-num gt-success">{{ assignStats.assigned }}</div>
                <div class="gt-wp-lc-stat-cell-label">已委派</div>
              </div>
              <div class="gt-wp-lc-stat-cell">
                <div class="gt-wp-lc-stat-cell-num gt-warning">{{ assignStats.unassigned }}</div>
                <div class="gt-wp-lc-stat-cell-label">待委派</div>
              </div>
            </div>
            <p class="gt-wp-lc-desc">将底稿委派给具体审计员，未委派底稿不计入工作量分配。</p>
            <el-button type="primary" @click="emit('switch-view', 'matrix')">前往委派矩阵</el-button>
          </div>
        </div>

        <!-- 编制 -->
        <div v-else-if="currentKey === 'compose'" class="gt-wp-lc-stage-content">
          <h3 class="gt-wp-lc-h3">4. 编制</h3>
          <div class="gt-wp-lc-card">
            <div class="gt-wp-lc-card-stat">
              <span class="gt-wp-lc-stat-num">{{ composeStats.completed }}</span>
              <span class="gt-wp-lc-stat-divider">/</span>
              <span class="gt-wp-lc-stat-total">{{ composeStats.total }}</span>
              <span class="gt-wp-lc-stat-label">底稿已完成编制</span>
            </div>
            <el-progress :percentage="composeStats.percent" :stroke-width="8" />
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
              <div v-if="filteredComposeList.length === 0" class="gt-wp-lc-empty">
                暂无编制中底稿
              </div>
            </div>
          </div>
        </div>

        <!-- 复核 -->
        <div v-else-if="currentKey === 'review'" class="gt-wp-lc-stage-content">
          <h3 class="gt-wp-lc-h3">5. 复核</h3>
          <div class="gt-wp-lc-card">
            <div class="gt-wp-lc-card-stat">
              <span class="gt-wp-lc-stat-num gt-warning">{{ reviewStats.pending }}</span>
              <span class="gt-wp-lc-stat-label">底稿待复核</span>
            </div>
            <p class="gt-wp-lc-desc">一级/二级复核流程，含批注、退回修改、强制通过等操作。</p>
            <el-button type="primary" @click="goToReviewWorkbench">前往复核工作台</el-button>
          </div>
        </div>

        <!-- 归档 -->
        <div v-else-if="currentKey === 'archive'" class="gt-wp-lc-stage-content">
          <h3 class="gt-wp-lc-h3">6. 归档</h3>
          <div class="gt-wp-lc-card">
            <h4 class="gt-wp-lc-h4">归档前置条件</h4>
            <ul class="gt-wp-lc-gate-list">
              <li v-for="g in archiveGates" :key="g.key" class="gt-wp-lc-gate-item">
                <span class="gt-wp-lc-gate-icon" :class="g.passed ? 'gt-success' : 'gt-warning'">
                  {{ g.passed ? '✓' : '✗' }}
                </span>
                <span class="gt-wp-lc-gate-text">{{ g.label }}</span>
              </li>
            </ul>
            <el-button
              type="primary"
              :disabled="!allGatesPassed"
              @click="goToArchive"
            >
              {{ allGatesPassed ? '执行归档' : '前置条件未满足' }}
            </el-button>
          </div>
        </div>
      </div>

      <!-- 右：任务面板 -->
      <div class="gt-wp-lc-right-panel">
        <h4 class="gt-wp-lc-h4">我的任务</h4>
        <div v-if="myTodos.length === 0" class="gt-wp-lc-empty">
          暂无待办任务
        </div>
        <div
          v-for="todo in myTodos"
          :key="todo.id"
          class="gt-wp-lc-todo-item"
          @click="emit('open-workpaper', todo.id)"
        >
          <div class="gt-wp-lc-todo-line">
            <span class="gt-wp-lc-todo-code">{{ todo.wp_code }}</span>
            <el-tag size="small" type="warning">
              {{ statusLabelShort(todo.status) }}
            </el-tag>
          </div>
          <div class="gt-wp-lc-todo-name">{{ todo.wp_name }}</div>
        </div>

        <h4 class="gt-wp-lc-h4" style="margin-top: 16px">逾期提醒</h4>
        <div v-if="overdueItems.length === 0" class="gt-wp-lc-empty">
          无逾期项
        </div>
        <div
          v-for="item in overdueItems"
          :key="`ov-${item.id}`"
          class="gt-wp-lc-todo-item gt-wp-lc-overdue"
          @click="emit('open-workpaper', item.id)"
        >
          <div class="gt-wp-lc-todo-line">
            <span class="gt-wp-lc-todo-code">{{ item.wp_code }}</span>
            <el-tag size="small" type="danger">{{ item.days }}天</el-tag>
          </div>
          <div class="gt-wp-lc-todo-name">{{ item.wp_name }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
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
.gt-wp-lifecycle {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: var(--gt-space-3);
}

.gt-wp-lc-flow {
  background: var(--gt-color-bg-white);
  border-radius: var(--gt-radius-md);
  box-shadow: var(--gt-shadow-sm);
  padding: var(--gt-space-3) var(--gt-space-4);
}

.gt-wp-lc-svg {
  width: 100%;
  height: 90px;
  overflow: visible;
}

.gt-wp-lc-stage-circle {
  cursor: pointer;
  transition: transform 0.15s;
}
.gt-wp-lc-stage-circle:hover {
  transform: scale(1.05);
  transform-origin: center;
}

.gt-wp-lc-body {
  display: flex;
  gap: var(--gt-space-3);
  flex: 1;
  min-height: 0;
}

.gt-wp-lc-stage-list {
  width: 200px;
  min-width: 200px;
  background: var(--gt-color-bg-white);
  border-radius: var(--gt-radius-md);
  box-shadow: var(--gt-shadow-sm);
  padding: var(--gt-space-3);
  overflow-y: auto;
}

.gt-wp-lc-stage-item {
  display: flex;
  gap: var(--gt-space-2);
  padding: var(--gt-space-2);
  border-radius: var(--gt-radius-sm);
  cursor: pointer;
  margin-bottom: var(--gt-space-2);
  transition: background 0.15s;
  border-left: 3px solid transparent;
}
.gt-wp-lc-stage-item:hover {
  background: var(--gt-color-primary-bg);
}
.gt-wp-lc-stage-item.is-current {
  background: var(--gt-color-primary-bg);
  border-left-color: var(--gt-color-primary);
}

.gt-wp-lc-stage-no {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 12px;
  background: var(--gt-color-primary);
  color: var(--gt-color-text-inverse);
  font-size: var(--gt-font-size-xs);
  font-weight: 700;
  flex-shrink: 0;
}

.gt-wp-lc-stage-info {
  flex: 1;
  min-width: 0;
}
.gt-wp-lc-stage-name {
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  color: var(--gt-color-text-primary);
  margin-bottom: 4px;
}
.gt-wp-lc-stage-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--gt-font-size-xs);
  margin-bottom: 4px;
}
.gt-wp-lc-stage-pct {
  color: var(--gt-color-text-tertiary);
}

.gt-wp-lc-content {
  flex: 1;
  background: var(--gt-color-bg-white);
  border-radius: var(--gt-radius-md);
  box-shadow: var(--gt-shadow-sm);
  padding: var(--gt-space-4);
  overflow-y: auto;
}

.gt-wp-lc-stage-content {
  display: flex;
  flex-direction: column;
  gap: var(--gt-space-3);
}

.gt-wp-lc-h3 {
  margin: 0;
  font-size: var(--gt-font-size-lg);
  color: var(--gt-color-primary);
  font-weight: 700;
}
.gt-wp-lc-h4 {
  margin: 0 0 var(--gt-space-2);
  font-size: var(--gt-font-size-md);
  color: var(--gt-color-text-primary);
  font-weight: 600;
}

.gt-wp-lc-card {
  background: var(--gt-color-bg);
  border: 1px solid var(--gt-color-border-light);
  border-radius: var(--gt-radius-sm);
  padding: var(--gt-space-3);
}

.gt-wp-lc-card-stat {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: var(--gt-space-2);
}
.gt-wp-lc-stat-num {
  font-size: var(--gt-font-size-3xl);
  font-weight: 700;
  color: var(--gt-color-primary);
}
.gt-wp-lc-stat-divider {
  color: var(--gt-color-text-tertiary);
}
.gt-wp-lc-stat-total {
  font-size: var(--gt-font-size-xl);
  color: var(--gt-color-text-secondary);
}
.gt-wp-lc-stat-label {
  margin-left: 8px;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-secondary);
}

.gt-wp-lc-stat-row {
  display: flex;
  justify-content: space-around;
  margin-bottom: var(--gt-space-3);
}
.gt-wp-lc-stat-cell {
  text-align: center;
}
.gt-wp-lc-stat-cell-num {
  font-size: var(--gt-font-size-2xl);
  font-weight: 700;
  color: var(--gt-color-primary);
}
.gt-wp-lc-stat-cell-num.gt-success {
  color: var(--gt-color-success);
}
.gt-wp-lc-stat-cell-num.gt-warning {
  color: var(--gt-color-wheat);
}
.gt-wp-lc-stat-cell-label {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
  margin-top: 4px;
}

.gt-wp-lc-desc {
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-secondary);
  margin: var(--gt-space-2) 0;
  line-height: 1.6;
}

.gt-wp-lc-rec-list {
  list-style: none;
  padding: 0;
  margin: 0;
}
.gt-wp-lc-rec-list li {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  font-size: var(--gt-font-size-sm);
}
.gt-wp-lc-rec-name {
  color: var(--gt-color-text-primary);
}

.gt-wp-lc-filter-row {
  margin: var(--gt-space-2) 0;
}

.gt-wp-lc-list {
  max-height: 320px;
  overflow-y: auto;
}
.gt-wp-lc-list-item {
  display: flex;
  align-items: center;
  gap: var(--gt-space-2);
  padding: var(--gt-space-2);
  border-radius: var(--gt-radius-sm);
  cursor: pointer;
  border-bottom: 1px solid var(--gt-color-border-light);
  transition: background 0.15s;
}
.gt-wp-lc-list-item:hover {
  background: var(--gt-color-primary-bg);
}
.gt-wp-lc-li-code {
  font-weight: 600;
  color: var(--gt-color-primary);
  min-width: 50px;
}
.gt-wp-lc-li-name {
  flex: 1;
  color: var(--gt-color-text-primary);
  font-size: var(--gt-font-size-sm);
}

.gt-wp-lc-empty {
  text-align: center;
  color: var(--gt-color-text-tertiary);
  font-size: var(--gt-font-size-sm);
  padding: var(--gt-space-4);
}

.gt-wp-lc-gate-list {
  list-style: none;
  padding: 0;
  margin: 0 0 var(--gt-space-3);
}
.gt-wp-lc-gate-item {
  display: flex;
  align-items: center;
  gap: var(--gt-space-2);
  padding: var(--gt-space-2);
  border-bottom: 1px solid var(--gt-color-border-light);
  font-size: var(--gt-font-size-sm);
}
.gt-wp-lc-gate-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 11px;
  font-weight: 700;
}
.gt-wp-lc-gate-icon.gt-success {
  background: var(--gt-color-success);
  color: var(--gt-color-text-inverse);
}
.gt-wp-lc-gate-icon.gt-warning {
  background: var(--gt-color-coral);
  color: var(--gt-color-text-inverse);
}

.gt-wp-lc-right-panel {
  width: 240px;
  min-width: 240px;
  background: var(--gt-color-bg-white);
  border-radius: var(--gt-radius-md);
  box-shadow: var(--gt-shadow-sm);
  padding: var(--gt-space-3);
  overflow-y: auto;
}

.gt-wp-lc-todo-item {
  padding: var(--gt-space-2);
  border-radius: var(--gt-radius-sm);
  background: var(--gt-color-bg);
  margin-bottom: var(--gt-space-2);
  cursor: pointer;
  border-left: 3px solid var(--gt-color-primary);
  transition: background 0.15s;
}
.gt-wp-lc-todo-item:hover {
  background: var(--gt-color-primary-bg);
}
.gt-wp-lc-todo-item.gt-wp-lc-overdue {
  border-left-color: var(--gt-color-coral);
}
.gt-wp-lc-todo-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}
.gt-wp-lc-todo-code {
  font-weight: 600;
  color: var(--gt-color-primary);
  font-size: var(--gt-font-size-sm);
}
.gt-wp-lc-todo-name {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
