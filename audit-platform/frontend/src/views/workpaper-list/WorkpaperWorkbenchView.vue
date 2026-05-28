<template>
  <div class="gt-wp-workbench-container">
    <!-- 工作台视图：按循环分组 + 进度追踪 + 批量操作 -->
    <div v-if="ctx.viewMode.value === 'workbench'" class="gt-wp-workbench-view">
      <!-- 循环进度卡片区 -->
      <div class="gt-wpb-progress-header">
        <span class="gt-wpb-progress-header__title">循环进度概览</span>
        <span v-if="workbenchCycleFilter.length" class="gt-wpb-progress-header__filter-tag">
          筛选：{{ workbenchCycleFilter.map(c => cycleNameMap[c] || c).join('、') }}
          <span class="gt-wpb-progress-header__clear" @click="workbenchCycleFilter = []">✕</span>
        </span>
        <el-button size="small" text @click="workbenchProgressCollapsed = !workbenchProgressCollapsed">
          {{ workbenchProgressCollapsed ? '展开 ▼' : '收起 ▲' }}
        </el-button>
      </div>
      <div v-show="!workbenchProgressCollapsed" class="gt-wpb-progress-summary">
        <div class="gt-wpb-prog-card" v-for="cycle in cycleSummary" :key="cycle.code"
          :class="{ 'is-active': workbenchCycleFilter.includes(cycle.code) }"
          @click="onWorkbenchCycleClick(cycle.code)">
          <div class="gt-wpb-prog-card__header">
            <span class="gt-wpb-prog-card__code">{{ cycle.code }}</span>
            <span class="gt-wpb-prog-card__name">{{ cycle.name }}</span>
          </div>
          <el-progress :percentage="cycle.percent" :stroke-width="6" :color="cycle.percent === 100 ? '#67c23a' : '#4b2d77'" />
          <div class="gt-wpb-prog-card__detail">{{ cycle.completed }}/{{ cycle.total }} 完成</div>
        </div>
      </div>
      <div class="gt-wpb-workbench-list">
        <el-table :data="pagedWorkbenchData" stripe border style="width: 100%; font-size: 13px" max-height="calc(100vh - 320px)" @row-click="onWorkbenchRowClick">
          <el-table-column prop="wp_code" label="编码" min-width="90" sortable resizable />
          <el-table-column prop="wp_name" label="底稿名称" min-width="220" show-overflow-tooltip resizable />
          <el-table-column prop="cycle_name" label="循环" min-width="110" show-overflow-tooltip resizable />
          <el-table-column prop="status_label" label="状态" min-width="90" resizable>
            <template #default="{ row }">
              <el-tag :type="row.status_type" size="small">{{ row.status_label }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="assignee_name" label="编制人" min-width="90" resizable />
          <el-table-column prop="step_progress" label="步骤进度" min-width="90" resizable>
            <template #default="{ row }">
              <span v-if="row.total_steps">{{ row.completed_steps || 0 }}/{{ row.total_steps }}</span>
              <span v-else class="gt-text-tertiary">—</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="130" fixed="right">
            <template #default="{ row }">
              <GtRowActions :actions="getWpRowActions(row)" :max-visible="2" @action="(key: string) => handleWpRowAction(key, row)" />
            </template>
          </el-table-column>
        </el-table>
        <div class="gt-pagination" v-if="wbTotal > wbPageSize" style="margin-top: 12px; display: flex; justify-content: flex-end;">
          <el-pagination v-model:current-page="wbPage" :page-size="wbPageSize" :total="wbTotal" layout="total, prev, pager, next" background small />
        </div>
      </div>
    </div>

    <!-- 用户手册视图 -->
    <div v-else-if="ctx.viewMode.value === 'guide'" class="gt-wp-guide-view">
      <div class="gt-wp-guide-view__nav">
        <el-button-group>
          <el-button :type="guideSection === 'overview' ? 'primary' : ''" size="small" @click="guideSection = 'overview'">体系总览</el-button>
          <el-button :type="guideSection === 'flow' ? 'primary' : ''" size="small" @click="guideSection = 'flow'">审计流程</el-button>
          <el-button :type="guideSection === 'relation' ? 'primary' : ''" size="small" @click="guideSection = 'relation'">底稿关系</el-button>
          <el-button :type="guideSection === 'cycles' ? 'primary' : ''" size="small" @click="guideSection = 'cycles'">循环详解</el-button>
        </el-button-group>
        <el-button v-if="guideBreadcrumb.length > 1" size="small" text @click="guideGoBack">
          ← 返回{{ guideBreadcrumb[guideBreadcrumb.length - 2] }}
        </el-button>
      </div>

      <!-- 体系总览 -->
      <div v-if="guideSection === 'overview'" class="gt-wp-guide-section">
        <h3 class="gt-wp-guide-section__title">底稿体系总览</h3>
        <p class="gt-wp-guide-section__desc">审计底稿按审计循环组织，每个循环包含多个底稿程序，覆盖从风险评估到完成阶段的全流程。</p>
        <div class="gt-wp-guide-overview-grid">
          <div class="gt-wp-guide-overview-card" v-for="cycle in guideOverviewData" :key="cycle.code" @click="guideJumpToCycle(cycle.code)">
            <div class="gt-wp-guide-overview-card__badge" :style="{ background: cycle.color }">{{ cycle.code }}</div>
            <div class="gt-wp-guide-overview-card__info">
              <div class="gt-wp-guide-overview-card__name">{{ cycle.name }}</div>
              <div class="gt-wp-guide-overview-card__meta">{{ cycle.count }} 个底稿 · {{ cycle.desc }}</div>
            </div>
            <span class="gt-wp-guide-overview-card__arrow">›</span>
          </div>
        </div>
      </div>

      <!-- 审计流程 -->
      <div v-if="guideSection === 'flow'" class="gt-wp-guide-section">
        <h3 class="gt-wp-guide-section__title">风险导向审计流程</h3>
        <div class="gt-wp-guide-flow-chart">
          <div class="gt-wp-guide-flow-step" v-for="(step, idx) in guideFlowSteps" :key="step.id">
            <div class="gt-wp-guide-flow-step__node" :style="{ borderColor: step.color }">
              <div class="gt-wp-guide-flow-step__icon">{{ step.icon }}</div>
              <div class="gt-wp-guide-flow-step__label">{{ step.label }}</div>
            </div>
            <div v-if="idx < guideFlowSteps.length - 1" class="gt-wp-guide-flow-step__arrow"><span>→</span></div>
          </div>
        </div>
      </div>

      <!-- 底稿关系 -->
      <div v-if="guideSection === 'relation'" class="gt-wp-guide-section">
        <h3 class="gt-wp-guide-section__title">底稿与报表、附注的数据关系</h3>
        <div class="gt-wp-guide-dataflow">
          <div class="gt-wp-guide-dataflow__chain">
            <div v-for="(step, idx) in guideDataFlowPaths" :key="idx" class="gt-wp-guide-dataflow__step">
              <div class="gt-wp-guide-dataflow__node">
                <span class="gt-wp-guide-dataflow__icon">{{ step.icon }}</span>
                <span class="gt-wp-guide-dataflow__name">{{ step.to }}</span>
              </div>
              <div v-if="idx < guideDataFlowPaths.length - 1" class="gt-wp-guide-dataflow__arrow">→</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 循环详解 -->
      <div v-if="guideSection === 'cycles'" class="gt-wp-guide-section">
        <h3 class="gt-wp-guide-section__title">审计循环详解</h3>
        <div class="gt-wp-guide-cycles-grid">
          <div class="gt-wp-guide-cycle-card" v-for="cycle in guideCycleDetails" :key="cycle.code"
            :class="{ 'is-active': guideFocusCycle === cycle.code }"
            @click="guideFocusCycle = guideFocusCycle === cycle.code ? '' : cycle.code">
            <div class="gt-wp-guide-cycle-card__header">
              <span class="gt-wp-guide-cycle-card__badge" :style="{ background: cycle.color }">{{ cycle.code }}</span>
              <span class="gt-wp-guide-cycle-card__name">{{ cycle.name }}</span>
              <span class="gt-wp-guide-cycle-card__count">{{ cycle.wps.length }} 个底稿</span>
            </div>
            <div v-if="guideFocusCycle === cycle.code" class="gt-wp-guide-cycle-card__body">
              <div class="gt-wp-guide-cycle-card__wp-list">
                <div v-for="wp in cycle.wps" :key="wp.code" class="gt-wp-guide-cycle-card__wp-item" @click.stop="onGuideWpClick(wp.code)">
                  <span class="gt-wp-guide-cycle-card__wp-code">{{ wp.code }}</span>
                  <span class="gt-wp-guide-cycle-card__wp-name">{{ wp.name }}</span>
                  <span class="gt-wp-guide-cycle-card__wp-arrow">→</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 列表视图（默认） -->
    <div v-else class="gt-wp-list-default">
      <el-table :data="pagedWorkbenchData" stripe border style="width: 100%; font-size: 13px" max-height="calc(100vh - 280px)" @row-click="onWorkbenchRowClick">
        <el-table-column prop="wp_code" label="编码" min-width="90" sortable resizable />
        <el-table-column prop="wp_name" label="底稿名称" min-width="220" show-overflow-tooltip resizable />
        <el-table-column prop="cycle_name" label="循环" min-width="110" show-overflow-tooltip resizable />
        <el-table-column prop="status_label" label="状态" min-width="90" resizable>
          <template #default="{ row }">
            <el-tag :type="row.status_type" size="small">{{ row.status_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="assignee_name" label="编制人" min-width="90" resizable />
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <GtRowActions :actions="getWpRowActions(row)" :max-visible="2" @action="(key: string) => handleWpRowAction(key, row)" />
          </template>
        </el-table-column>
      </el-table>
      <div class="gt-pagination" v-if="wbTotal > wbPageSize" style="margin-top: 12px; display: flex; justify-content: flex-end;">
        <el-pagination v-model:current-page="wbPage" :page-size="wbPageSize" :total="wbTotal" layout="total, prev, pager, next" background small />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * WorkpaperWorkbenchView — 工作台/列表/手册 三合一子 SFC
 * 从 WorkpaperList.vue 抽取 list/workbench/guide 三个 viewMode 的模板和私有逻辑
 * Requirements: 2.5, 3.5, 4.6, 5.1, 5.2
 */
import { inject, ref, computed, nextTick } from 'vue'
import { WP_LIST_CONTEXT_KEY } from '@/composables/useWorkpaperListContext'
import type { WpChildProps, WpChildEmits, MutatePayload } from '@/composables/useWorkpaperListContext'
import type { WpIndexItem, WorkpaperDetail } from '@/services/workpaperApi'
import { downloadWorkpaper } from '@/services/workpaperApi'
import GtRowActions from '@/components/common/GtRowActions.vue'
import type { RowAction } from '@/components/common/GtRowActions.vue'

defineOptions({ name: 'WorkpaperWorkbenchView' })

const props = defineProps<WpChildProps>()
const emit = defineEmits<WpChildEmits>()

const ctx = inject(WP_LIST_CONTEXT_KEY)
if (!ctx) throw new ReferenceError('WpListContext not provided — must be used inside WorkpaperList Shell')

// ─── 工作台私有状态 ─────────────────────────────────────────────────────────────
const workbenchProgressCollapsed = ref(false)
const workbenchCycleFilter = ref<string[]>([])
const wbPage = ref(1)
const wbPageSize = ref(50)

const COMPLETED_STATUSES = new Set(['review_passed', 'archived'])

const cycleNameMap: Record<string, string> = {
  A: '完成阶段', B: '计划阶段', C: '控制测试', D: '收入循环',
  E: '货币资金', F: '存货', G: '投资', H: '固定资产',
  I: '无形资产', J: '职工薪酬', K: '管理/费用', L: '债务',
  M: '权益', N: '税金', S: '特定项目',
}

const STATUS_LABELS: Record<string, { label: string; type: string }> = {
  draft: { label: '待编', type: 'info' },
  in_progress: { label: '编制中', type: 'warning' },
  edit_complete: { label: '已完成', type: 'primary' },
  pending_review: { label: '待复核', type: 'warning' },
  reviewed: { label: '已复核', type: 'success' },
  approved: { label: '已通过', type: 'success' },
}

// ─── 工作台 computed ─────────────────────────────────────────────────────────────
const filteredWpList = computed<WorkpaperDetail[]>(() => {
  return ctx.wpList.value.filter((w: WorkpaperDetail) => {
    const idx = ctx.wpIndex.value.find((i: WpIndexItem) => i.id === w.wp_index_id)
    if (ctx.filterCycle.value && !idx?.wp_code?.startsWith(ctx.filterCycle.value)) return false
    if (ctx.filterStatus.value && w.status !== ctx.filterStatus.value) return false
    if (ctx.filterAssignee.value && w.assigned_to !== ctx.filterAssignee.value) return false
    if (ctx.searchKeyword.value) {
      const kw = ctx.searchKeyword.value.toLowerCase()
      if (!w.wp_code?.toLowerCase().includes(kw) && !w.wp_name?.toLowerCase().includes(kw)) return false
    }
    return true
  })
})

const cycleSummary = computed(() => {
  const groups: Record<string, { total: number; completed: number }> = {}
  for (const w of ctx.wpList.value) {
    const idx = ctx.wpIndex.value.find((i: WpIndexItem) => i.id === w.wp_index_id)
    const code = idx?.wp_code || ''
    const cycleKey = code[0] || '?'
    if (!groups[cycleKey]) groups[cycleKey] = { total: 0, completed: 0 }
    groups[cycleKey].total += 1
    if (COMPLETED_STATUSES.has(w.status)) groups[cycleKey].completed += 1
  }
  return Object.entries(groups)
    .map(([code, g]) => ({
      code, name: cycleNameMap[code] || code,
      total: g.total, completed: g.completed,
      percent: g.total > 0 ? Math.round((g.completed / g.total) * 100) : 0,
    }))
    .sort((a, b) => a.code.localeCompare(b.code))
})

const workbenchTableData = computed(() => {
  return filteredWpList.value
    .filter((w: WorkpaperDetail) => {
      if (workbenchCycleFilter.value.length) {
        const idx = ctx.wpIndex.value.find((i: WpIndexItem) => i.id === w.wp_index_id)
        const code = idx?.wp_code || ''
        if (!workbenchCycleFilter.value.some(c => code.startsWith(c))) return false
      }
      return true
    })
    .map((w: WorkpaperDetail) => {
      const idx = ctx.wpIndex.value.find((i: WpIndexItem) => i.id === w.wp_index_id)
      const code = idx?.wp_code || ''
      const cycleKey = code[0] || '?'
      const statusInfo = STATUS_LABELS[w.status] || { label: w.status, type: 'info' }
      return {
        id: w.id, wp_code: code, wp_name: idx?.wp_name || '',
        cycle_name: cycleNameMap[cycleKey] || cycleKey,
        status: w.status, status_label: statusInfo.label, status_type: statusInfo.type,
        assignee_name: (w as any).assignee_name || '',
        total_steps: (w as any).total_steps || 0,
        completed_steps: (w as any).completed_steps || 0,
      }
    })
})

const wbTotal = computed(() => workbenchTableData.value.length)
const pagedWorkbenchData = computed(() => {
  const start = (wbPage.value - 1) * wbPageSize.value
  return workbenchTableData.value.slice(start, start + wbPageSize.value)
})

// ─── 工作台操作 ─────────────────────────────────────────────────────────────────
function onWorkbenchCycleClick(code: string) {
  const idx = workbenchCycleFilter.value.indexOf(code)
  if (idx >= 0) workbenchCycleFilter.value.splice(idx, 1)
  else workbenchCycleFilter.value.push(code)
}

function onWorkbenchRowClick(row: any) {
  if (row.id) emit('navigate', row.id)
}

function getWpRowActions(_row: any): RowAction[] {
  return [
    { key: 'edit', label: '编辑', priority: 1 },
    { key: 'download', label: '下载', priority: 2 },
    { key: 'assign', label: '委派', priority: 3 },
  ]
}

function handleWpRowAction(key: string, row: any) {
  switch (key) {
    case 'edit':
      if (row.id) emit('navigate', row.id)
      break
    case 'download':
      if (row.id) downloadWorkpaper(props.projectId, row.id)
      break
    case 'assign':
      emit('mutate', { action: 'assign', data: { wp_id: row.id, wp_code: row.wp_code } })
      break
  }
}

// ─── 手册视图私有状态 ─────────────────────────────────────────────────────────────
const guideSection = ref<'overview' | 'flow' | 'relation' | 'cycles'>('overview')
const guideBreadcrumb = ref<string[]>(['体系总览'])
const guideFocusCycle = ref('')

const guideOverviewData = [
  { code: 'A', name: '报表与调整', color: '#6750A4', count: 20, desc: '总括性程序、报表编制、调整分录' },
  { code: 'B', name: '风险评估', color: '#6750A4', count: 15, desc: '穿行测试、了解内控、风险识别' },
  { code: 'C', name: '控制测试', color: '#6750A4', count: 14, desc: '控制有效性测试、偏差评估' },
  { code: 'D', name: '销售收入', color: '#E8590C', count: 8, desc: '收入确认、应收账款、信用减值' },
  { code: 'E', name: '货币资金', color: '#E8590C', count: 7, desc: '银行存款、现金、银行函证' },
  { code: 'F', name: '采购存货', color: '#E8590C', count: 9, desc: '采购循环、存货计价、跌价准备' },
  { code: 'G', name: '投资', color: '#E8590C', count: 6, desc: '长期股权投资、金融资产分类' },
  { code: 'H', name: '固定资产', color: '#E8590C', count: 8, desc: '固定资产、在建工程、使用权资产' },
  { code: 'I', name: '无形资产', color: '#E8590C', count: 5, desc: '无形资产、商誉、开发支出' },
  { code: 'J', name: '职工薪酬', color: '#E8590C', count: 4, desc: '薪酬计提、股份支付' },
  { code: 'K', name: '管理费用', color: '#E8590C', count: 3, desc: '费用分析、跨循环减值汇总' },
  { code: 'L', name: '筹资', color: '#E8590C', count: 4, desc: '借款、债券、利息计算' },
  { code: 'M', name: '股东权益', color: '#E8590C', count: 3, desc: '权益变动、利润分配' },
  { code: 'N', name: '税费', color: '#E8590C', count: 3, desc: '所得税、递延税项' },
  { code: 'S', name: '专项程序', color: '#2E7D32', count: 5, desc: '持续经营、关联方、期后事项' },
]

const guideFlowSteps = [
  { id: 'plan', icon: '📋', label: '审计计划', color: '#6750A4' },
  { id: 'walkthrough', icon: '🔄', label: '穿行测试', color: '#7B1FA2' },
  { id: 'control', icon: '🔒', label: '控制测试', color: '#1976D2' },
  { id: 'substantive', icon: '🔍', label: '实质性程序', color: '#E8590C' },
  { id: 'complete', icon: '✅', label: '审计完成', color: '#2E7D32' },
]

const guideDataFlowPaths = [
  { from: '账套导入', to: '试算表', label: '客户 ERP 数据', icon: '📥' },
  { from: '试算表', to: '底稿', label: '科目余额取数', icon: '📊' },
  { from: '底稿', to: '调整分录', label: '发现错报', icon: '📋' },
  { from: '调整分录', to: '试算表', label: '更新审定数', icon: '✏️' },
  { from: '试算表', to: '报表', label: '生成报表', icon: '📑' },
  { from: '报表', to: '附注', label: '明细披露', icon: '📝' },
  { from: '报表+附注', to: '审计报告', label: '形成意见', icon: '📄' },
]

const guideCycleDetails = computed(() => {
  return guideOverviewData.map(cycle => {
    const wps = ctx.wpIndex.value
      .filter((w: WpIndexItem) => w.wp_code?.startsWith(cycle.code))
      .map((w: WpIndexItem) => ({ code: w.wp_code, name: w.wp_name }))
      .sort((a, b) => (a.code || '').localeCompare(b.code || ''))
    return { ...cycle, wps }
  })
})

function guideJumpToCycle(code: string) {
  guideBreadcrumb.value.push(guideSection.value === 'overview' ? '体系总览' : guideSection.value === 'flow' ? '审计流程' : '底稿关系')
  guideSection.value = 'cycles'
  guideFocusCycle.value = code
}

function guideGoBack() {
  guideBreadcrumb.value.pop()
  const prev = guideBreadcrumb.value[guideBreadcrumb.value.length - 1]
  if (prev === '体系总览') guideSection.value = 'overview'
  else if (prev === '审计流程') guideSection.value = 'flow'
  else if (prev === '底稿关系') guideSection.value = 'relation'
  else guideSection.value = 'overview'
}

function onGuideWpClick(wpCode: string) {
  ctx.viewMode.value = 'list'
  guideBreadcrumb.value = ['体系总览']
  nextTick(() => {
    const idx = ctx.wpIndex.value.find((i: WpIndexItem) => i.wp_code === wpCode)
    if (idx) ctx.selectedWpId.value = idx.id
  })
}
</script>

<style scoped>
.gt-wp-workbench-container {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
</style>
