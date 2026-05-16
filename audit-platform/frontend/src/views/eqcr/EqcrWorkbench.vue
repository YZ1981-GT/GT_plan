<template>
  <div class="eqcr-workbench">
    <GtPageHeader title="EQCR 工作台" :show-back="false">
      <template #actions>
        <el-radio-group
          v-model="progressFilter"
          size="small"
          style="margin-right: 12px"
        >
          <el-radio-button value="all">全部</el-radio-button>
          <el-radio-button value="not_started">未开始</el-radio-button>
          <el-radio-button value="in_progress">进行中</el-radio-button>
          <el-radio-button value="approved">已同意</el-radio-button>
          <el-radio-button value="disagree">有异议</el-radio-button>
        </el-radio-group>
        <el-button size="small" :loading="loading" @click="load">刷新</el-button>
      </template>
    </GtPageHeader>

    <!-- 空态 -->
    <el-empty
      v-if="!loading && cards.length === 0"
      description="您当前没有被委派为 EQCR 的项目"
      style="margin-top: 48px"
    >
      <template #image>
        <div style="font-size: 48px /* allow-px: special */">🕊️</div>
      </template>
    </el-empty>

    <!-- 过滤后空态（有项目但都被筛掉） -->
    <el-empty
      v-else-if="!loading && filteredCards.length === 0"
      description="当前筛选条件下没有项目"
      style="margin-top: 32px"
    />

    <!-- 项目卡片网格 -->
    <el-row v-else v-loading="loading" :gutter="16" class="eqcr-cards-row">
      <el-col
        v-for="card in filteredCards"
        :key="card.project_id"
        :xs="24"
        :sm="12"
        :md="8"
        :lg="8"
        :xl="6"
      >
        <el-card
          shadow="hover"
          class="eqcr-card"
          :class="{ 'eqcr-card--urgent': isUrgent(card) }"
          @click="onCardClick(card)"
        >
          <!-- 头部：项目名 + 客户 -->
          <div class="eqcr-card__header">
            <div class="eqcr-card__project-name" :title="card.project_name">
              {{ card.project_name }}
            </div>
            <div class="eqcr-card__client" :title="card.client_name || ''">
              客户：{{ card.client_name || '—' }}
            </div>
          </div>

          <!-- 签字日 + 距签字天数 -->
          <div class="eqcr-card__row">
            <span class="eqcr-card__label">签字日</span>
            <span class="eqcr-card__value">
              {{ card.signing_date || '未设定' }}
            </span>
            <el-tag
              v-if="card.days_to_signing !== null"
              :type="daysTagType(card.days_to_signing)"
              size="small"
              effect="light"
              style="margin-left: 6px"
            >
              {{ daysLabel(card.days_to_signing) }}
            </el-tag>
          </div>

          <!-- 我的 EQCR 进度 -->
          <div class="eqcr-card__row">
            <span class="eqcr-card__label">我的进度</span>
            <el-tag
              :type="progressTagType(card.my_progress)"
              size="small"
              effect="light"
            >
              {{ progressLabel(card.my_progress) }}
            </el-tag>
          </div>

          <!-- 判断事项计数 -->
          <div class="eqcr-card__row">
            <span class="eqcr-card__label">判断事项</span>
            <el-tag type="success" size="small" effect="plain">
              已复核 {{ card.judgment_counts.reviewed }}
            </el-tag>
            <el-tag
              :type="card.judgment_counts.unreviewed > 0 ? 'warning' : 'info'"
              size="small"
              effect="plain"
              style="margin-left: 6px"
            >
              未复核 {{ card.judgment_counts.unreviewed }}
            </el-tag>
          </div>

          <!-- 报告状态 -->
          <div v-if="card.report_status" class="eqcr-card__footer">
            <el-tag
              :type="reportStatusTagType(card.report_status)"
              size="small"
              effect="dark"
            >
              {{ reportStatusLabel(card.report_status) }}
            </el-tag>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 年度独立性声明弹窗（需求 12） -->
    <EqcrAnnualDeclarationDialog
      v-model="showDeclarationDialog"
      @submitted="onDeclarationSubmitted"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  eqcrApi,
  type EqcrProgress,
  type EqcrProjectCard,
  type ReportStatusValue,
} from '@/services/eqcrService'
import EqcrAnnualDeclarationDialog from '@/components/eqcr/EqcrAnnualDeclarationDialog.vue'
import api from '@/services/apiProxy'
import { eqcr as P_eqcr } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'

const router = useRouter()

const loading = ref(false)
const cards = ref<EqcrProjectCard[]>([])
const progressFilter = ref<'all' | EqcrProgress>('all')
const showDeclarationDialog = ref(false)
/** 本年度声明完成前禁止展示项目数据（真实阻断，非仅弹窗） */
const declarationOk = ref(false)

// ─── 年度独立性声明检查（需求 12） ─────────────────────────────────────────

async function checkAnnualDeclaration(): Promise<boolean> {
  try {
    const data = await api.get(P_eqcr.independence.check)
    declarationOk.value = !!data?.has_declaration
    if (!declarationOk.value) {
      showDeclarationDialog.value = true
    }
    return declarationOk.value
  } catch {
    // 端点异常时按"未声明"处理，阻断访问（防止前端降级绕过声明要求）
    declarationOk.value = false
    showDeclarationDialog.value = true
    return false
  }
}

function onDeclarationSubmitted() {
  declarationOk.value = true
  showDeclarationDialog.value = false
  // 声明完成后再加载工作台数据
  load()
}

// ─── 载入 ─────────────────────────────────────────────────────────────────

async function load() {
  if (!declarationOk.value) {
    // 声明未完成：不拉取项目数据
    cards.value = []
    return
  }
  loading.value = true
  try {
    cards.value = await eqcrApi.listMyProjects()
  } catch (err: any) {
    handleApiError(err, '加载 EQCR 项目')
    cards.value = []
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  const ok = await checkAnnualDeclaration()
  if (ok) await load()
})

// ─── 筛选 + 汇总 ──────────────────────────────────────────────────────────

const filteredCards = computed<EqcrProjectCard[]>(() => {
  if (progressFilter.value === 'all') return cards.value
  return cards.value.filter((c) => c.my_progress === progressFilter.value)
})

const summary = computed(() => {
  let upcoming = 0
  let disagree = 0
  for (const c of cards.value) {
    if (c.days_to_signing !== null && c.days_to_signing <= 7) upcoming += 1
    if (c.my_progress === 'disagree') disagree += 1
  }
  return { upcoming, disagree }
})

// ─── 跳转 ─────────────────────────────────────────────────────────────────

function onCardClick(card: EqcrProjectCard) {
  // Task 6 将注册 /eqcr/projects/:projectId 路由对应 EqcrProjectView.vue；
  // 本任务只负责跳转，目标路由缺失时由 router 404 守卫处理。
  router.push(`/eqcr/projects/${card.project_id}`)
}

// ─── 视觉辅助 ─────────────────────────────────────────────────────────────

function isUrgent(card: EqcrProjectCard): boolean {
  return (
    card.days_to_signing !== null &&
    card.days_to_signing <= 7 &&
    card.my_progress !== 'approved'
  )
}

function daysTagType(days: number): 'danger' | 'warning' | 'info' {
  if (days <= 7) return 'danger'
  if (days <= 30) return 'warning'
  return 'info'
}

function daysLabel(days: number): string {
  if (days < 0) return `已逾期 ${Math.abs(days)} 天`
  if (days === 0) return '今日签字'
  return `距签字 ${days} 天`
}

const PROGRESS_META: Record<
  EqcrProgress,
  { label: string; type: 'info' | 'warning' | 'success' | 'danger' }
> = {
  not_started: { label: '未开始', type: 'info' },
  in_progress: { label: '进行中', type: 'warning' },
  approved: { label: '已同意', type: 'success' },
  disagree: { label: '有异议', type: 'danger' },
}

function progressLabel(p: EqcrProgress): string {
  return PROGRESS_META[p]?.label ?? p
}
function progressTagType(
  p: EqcrProgress,
): 'info' | 'warning' | 'success' | 'danger' {
  return PROGRESS_META[p]?.type ?? 'info'
}

const REPORT_STATUS_META: Record<
  ReportStatusValue,
  { label: string; type: 'info' | 'warning' | 'success' | 'primary' | 'danger' }
> = {
  draft: { label: '报告草稿', type: 'info' },
  review: { label: '报告审阅中', type: 'warning' },
  eqcr_approved: { label: 'EQCR 已通过', type: 'primary' },
  final: { label: '报告已定稿', type: 'success' },
}

function reportStatusLabel(s: ReportStatusValue): string {
  return REPORT_STATUS_META[s]?.label ?? s
}
function reportStatusTagType(
  s: ReportStatusValue,
): 'info' | 'warning' | 'success' | 'primary' | 'danger' {
  return REPORT_STATUS_META[s]?.type ?? 'info'
}
</script>

<style scoped>
.eqcr-workbench {
  padding: 0;
}

.eqcr-cards-row {
  margin-top: 16px;
}

.eqcr-card {
  margin-bottom: 16px;
  cursor: pointer;
  transition: transform var(--gt-transition-fast), box-shadow var(--gt-transition-fast);
  border-radius: var(--gt-radius-md);
}
.eqcr-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--gt-shadow-md);
}
.eqcr-card--urgent {
  border-left: 4px solid var(--el-color-danger);
}

.eqcr-card__header {
  margin-bottom: 10px;
}
.eqcr-card__project-name {
  font-size: var(--gt-font-size-md);
  font-weight: 600;
  color: var(--gt-color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.eqcr-card__client {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.eqcr-card__row {
  display: flex;
  align-items: center;
  margin-top: 8px;
  font-size: var(--gt-font-size-sm);
  flex-wrap: wrap;
  gap: 4px 0;
}
.eqcr-card__label {
  color: var(--gt-color-text-secondary);
  width: 70px;
  flex-shrink: 0;
}
.eqcr-card__value {
  color: var(--gt-color-text);
  margin-right: 4px;
}
.eqcr-card__footer {
  margin-top: 12px;
  padding-top: 8px;
  border-top: 1px dashed var(--gt-color-border-light);
  display: flex;
  justify-content: flex-end;
}
</style>
