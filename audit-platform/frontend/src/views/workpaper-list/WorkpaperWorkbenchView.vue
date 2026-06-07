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
          <div class="gt-wp-guide-overview-card" v-for="cycle in guideOverviewData" :key="cycle.code"
            @click="guideJumpToCycle(cycle.code)">
            <div class="gt-wp-guide-overview-card__badge" :style="{ background: cycle.color }">{{ cycle.code }}</div>
            <div class="gt-wp-guide-overview-card__info">
              <div class="gt-wp-guide-overview-card__name">{{ cycle.name }}</div>
              <div class="gt-wp-guide-overview-card__meta">{{ cycle.count }} 个底稿 · {{ cycle.desc }}</div>
            </div>
            <span class="gt-wp-guide-overview-card__arrow">›</span>
          </div>
        </div>
        <div class="gt-wp-guide-legend">
          <span class="gt-wp-guide-legend__item"><span class="gt-wp-guide-legend__dot" style="background:#6750A4"></span>风险评估与控制</span>
          <span class="gt-wp-guide-legend__item"><span class="gt-wp-guide-legend__dot" style="background:#E8590C"></span>实质性程序</span>
          <span class="gt-wp-guide-legend__item"><span class="gt-wp-guide-legend__dot" style="background:#2E7D32"></span>完成与专项</span>
        </div>
      </div>

      <!-- 审计流程 -->
      <div v-if="guideSection === 'flow'" class="gt-wp-guide-section">
        <h3 class="gt-wp-guide-section__title">风险导向审计流程</h3>
        <p class="gt-wp-guide-section__desc">现代审计采用风险导向方法：先识别风险，再针对性设计审计程序。每个阶段的结论直接影响下一阶段的范围和深度。</p>

        <!-- 流程图 -->
        <div class="gt-wp-guide-flow-chart">
          <div class="gt-wp-guide-flow-step" v-for="(step, idx) in guideFlowSteps" :key="step.id">
            <div class="gt-wp-guide-flow-step__node" :style="{ borderColor: step.color }">
              <div class="gt-wp-guide-flow-step__icon">{{ step.icon }}</div>
              <div class="gt-wp-guide-flow-step__label">{{ step.label }}</div>
              <div class="gt-wp-guide-flow-step__sub">{{ step.sub }}</div>
            </div>
            <div v-if="idx < guideFlowSteps.length - 1" class="gt-wp-guide-flow-step__arrow">
              <span class="gt-wp-guide-flow-arrow-text">{{ step.nextStageLink ? '▸' : '' }}</span>
              <span>→</span>
            </div>
          </div>
        </div>

        <!-- 各阶段详解 -->
        <div class="gt-wp-guide-flow-detail">
          <div class="gt-wp-guide-flow-detail__item" v-for="step in guideFlowSteps" :key="step.id">
            <div class="gt-wp-guide-flow-detail__header">
              <span class="gt-wp-guide-flow-detail__badge" :style="{ background: step.color }">{{ step.icon }}</span>
              <span class="gt-wp-guide-flow-detail__name">{{ step.label }}</span>
              <span class="gt-wp-guide-flow-detail__sub-tag">{{ step.sub }}</span>
            </div>

            <!-- 风险导向要点 -->
            <div class="gt-wp-guide-flow-risk">
              <span class="gt-wp-guide-flow-risk__icon">⚡</span>
              <span class="gt-wp-guide-flow-risk__text">风险导向要点：{{ step.riskFocus }}</span>
            </div>

            <div class="gt-wp-guide-flow-detail__desc">{{ step.detail }}</div>

            <!-- 关键工作 -->
            <div class="gt-wp-guide-flow-actions">
              <div class="gt-wp-guide-flow-actions__title">关键工作：</div>
              <div class="gt-wp-guide-flow-actions__list">
                <div v-for="(action, ai) in step.keyActions" :key="ai" class="gt-wp-guide-flow-actions__item">
                  <span class="gt-wp-guide-flow-actions__bullet">{{ ai + 1 }}</span>
                  <span>{{ action }}</span>
                </div>
              </div>
            </div>

            <!-- 关联底稿 -->
            <div class="gt-wp-guide-flow-wps">
              <div class="gt-wp-guide-flow-wps__title">📎 关联底稿：</div>
              <div class="gt-wp-guide-flow-wps__list">
                <div v-for="wp in step.wpLinks" :key="wp.code" class="gt-wp-guide-flow-wps__item"
                  @click="onGuideWpClick(wp.code)">
                  <span class="gt-wp-guide-flow-wps__code">{{ wp.code }}</span>
                  <span class="gt-wp-guide-flow-wps__name">{{ wp.name }}</span>
                  <span class="gt-wp-guide-flow-wps__rel">{{ wp.relation }}</span>
                </div>
              </div>
            </div>

            <!-- 产出循环 -->
            <div class="gt-wp-guide-flow-detail__outputs">
              产出循环：<span v-for="o in step.outputs" :key="o" class="gt-wp-guide-flow-detail__output-tag"
                @click="guideJumpToCycle(o)">{{ o }}</span>
            </div>

            <!-- 阶段衔接 -->
            <div v-if="step.nextStageLink" class="gt-wp-guide-flow-next">
              ➡️ {{ step.nextStageLink }}
            </div>
          </div>
        </div>
      </div>

      <!-- 底稿关系 -->
      <div v-if="guideSection === 'relation'" class="gt-wp-guide-section">
        <h3 class="gt-wp-guide-section__title">底稿与报表、附注的数据关系</h3>
        <p class="gt-wp-guide-section__desc">审计工作产出物之间存在严密的数据流转关系，理解这些关系是高效完成审计的基础。</p>

        <!-- 数据流转主线 -->
        <div class="gt-wp-guide-dataflow">
          <div class="gt-wp-guide-dataflow__title">📐 数据流转主线</div>
          <div class="gt-wp-guide-dataflow__chain">
            <div v-for="(step, idx) in guideDataFlowPaths" :key="idx" class="gt-wp-guide-dataflow__step">
              <div class="gt-wp-guide-dataflow__node">
                <span class="gt-wp-guide-dataflow__icon">{{ step.icon }}</span>
                <span class="gt-wp-guide-dataflow__name">{{ step.to }}</span>
              </div>
              <div v-if="idx < guideDataFlowPaths.length - 1" class="gt-wp-guide-dataflow__arrow">
                <span class="gt-wp-guide-dataflow__arrow-label">{{ guideDataFlowPaths[idx + 1]?.label }}</span>
                <span class="gt-wp-guide-dataflow__arrow-icon">→</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 模块关系详解 -->
        <div class="gt-wp-guide-modules">
          <div class="gt-wp-guide-modules__title">🔗 模块间关系详解</div>
          <div class="gt-wp-guide-modules__grid">
            <div v-for="rel in guideFullRelations" :key="rel.id" class="gt-wp-guide-module-card">
              <div class="gt-wp-guide-module-card__header">
                <span class="gt-wp-guide-module-card__icon" :style="{ background: rel.color }">{{ rel.icon }}</span>
                <span class="gt-wp-guide-module-card__name">{{ rel.name }}</span>
              </div>
              <div class="gt-wp-guide-module-card__desc">{{ rel.desc }}</div>
              <div class="gt-wp-guide-module-card__connections">
                <div v-for="(conn, ci) in rel.connections" :key="ci" class="gt-wp-guide-module-card__conn">
                  <span class="gt-wp-guide-module-card__conn-dir" :class="conn.direction === 'out' ? 'is-out' : 'is-in'">
                    {{ conn.direction === 'out' ? '→' : '←' }}
                  </span>
                  <span class="gt-wp-guide-module-card__conn-to">{{ conn.to }}</span>
                  <span class="gt-wp-guide-module-card__conn-label">{{ conn.label }}</span>
                  <span class="gt-wp-guide-module-card__conn-style" :class="conn.style === 'solid' ? 'is-auto' : 'is-manual'">
                    {{ conn.style === 'solid' ? '自动' : '引用' }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 关键说明 -->
        <div class="gt-wp-guide-relation-notes">
          <div class="gt-wp-guide-relation-notes__title">💡 关键说明</div>
          <div class="gt-wp-guide-relation-notes__list">
            <div class="gt-wp-guide-relation-notes__item">
              <strong>试算表 → 报表</strong>：审定数按科目映射规则自动汇总到报表行，映射关系在「试算表 → 映射规则」中配置
            </div>
            <div class="gt-wp-guide-relation-notes__item">
              <strong>报表 → 附注</strong>：附注各章节引用报表对应行的金额，报表数据变动时附注自动同步
            </div>
            <div class="gt-wp-guide-relation-notes__item">
              <strong>底稿 → 调整分录</strong>：各循环底稿发现的错报通过 AJE/RJE 反映，调整分录更新试算表后报表自动重算
            </div>
            <div class="gt-wp-guide-relation-notes__item">
              <strong>底稿 → 附注</strong>：部分附注数据（如固定资产变动表、借款明细）直接引用底稿中的分析结果
            </div>
            <div class="gt-wp-guide-relation-notes__item">
              <strong>闭环验证</strong>：报表金额 = 试算表审定数汇总 = 未审数 + AJE + RJE，系统自动校验一致性
            </div>
          </div>
        </div>

        <div class="gt-wp-guide-relation-legend">
          <div class="gt-wp-guide-relation-legend__item">
            <span class="gt-wp-guide-relation-legend__dot" style="background: var(--gt-color-primary)"></span>
            <span>自动取数（系统联动）</span>
          </div>
          <div class="gt-wp-guide-relation-legend__item">
            <span class="gt-wp-guide-relation-legend__dot" style="background: var(--gt-color-text-tertiary)"></span>
            <span>交叉引用（人工核对）</span>
          </div>
        </div>
      </div>

      <!-- 循环详解 -->
      <div v-if="guideSection === 'cycles'" class="gt-wp-guide-section">
        <h3 class="gt-wp-guide-section__title">审计循环详解</h3>
        <p class="gt-wp-guide-section__desc">点击循环卡片查看核心底稿、工作内容和关联关系。</p>
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
              <div class="gt-wp-guide-cycle-card__desc">{{ cycle.desc }}</div>

              <!-- 核心底稿 -->
              <div v-if="cycle.coreWps?.length" class="gt-wp-guide-cycle-core">
                <div class="gt-wp-guide-cycle-core__title">📌 核心底稿</div>
                <div class="gt-wp-guide-cycle-core__list">
                  <div v-for="cw in cycle.coreWps" :key="cw.code" class="gt-wp-guide-cycle-core__item"
                    @click.stop="onGuideWpClick(cw.code)">
                    <div class="gt-wp-guide-cycle-core__item-header">
                      <span class="gt-wp-guide-cycle-core__code">{{ cw.code }}</span>
                      <span class="gt-wp-guide-cycle-core__name">{{ cw.name }}</span>
                      <el-tag size="small" :type="cw.role === '总控台' ? 'danger' : cw.role === '核心' ? 'warning' : 'info'">{{ cw.role }}</el-tag>
                    </div>
                    <div class="gt-wp-guide-cycle-core__detail">{{ cw.detail }}</div>
                  </div>
                </div>
              </div>

              <!-- 关联循环 -->
              <div v-if="cycle.relatedTo?.length" class="gt-wp-guide-cycle-rel">
                <div class="gt-wp-guide-cycle-rel__title">🔗 关联循环</div>
                <div class="gt-wp-guide-cycle-rel__desc">{{ cycle.relDesc }}</div>
                <div class="gt-wp-guide-cycle-rel__tags">
                  <span v-for="r in cycle.relatedTo" :key="r" class="gt-wp-guide-cycle-rel__tag"
                    @click.stop="guideFocusCycle = r">{{ r }} {{ guideOverviewData.find(g => g.code === r)?.name }}</span>
                </div>
              </div>

              <!-- 完整底稿清单 -->
              <div v-if="cycle.wps.length" class="gt-wp-guide-cycle-wplist">
                <div class="gt-wp-guide-cycle-wplist__title">📋 完整底稿清单（{{ cycle.wps.length }}）</div>
                <div class="gt-wp-guide-cycle-card__wp-list">
                  <div v-for="wp in cycle.wps" :key="wp.code" class="gt-wp-guide-cycle-card__wp-item"
                    @click.stop="onGuideWpClick(wp.code)">
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

const _ctx = inject(WP_LIST_CONTEXT_KEY)
if (!_ctx) throw new ReferenceError('WpListContext not provided — must be used inside WorkpaperList Shell')
const ctx = _ctx

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

const guideOverviewMeta = [
  { code: 'A', name: '报表与调整', color: '#6750A4', count: 20, desc: '总括性程序、报表编制、调整分录',
    coreWps: [
      { code: 'A1', name: '财务报告程序表', role: '总控台', detail: '汇总各循环审计结论，形成整体审计意见的依据' },
      { code: 'A2', name: '调整分录汇总表', role: '枢纽', detail: '归集 D~N 各循环的 AJE/RJE，更新试算表审定数' },
      { code: 'A10', name: '与治理层沟通程序', role: '沟通', detail: '记录与管理层/治理层的关键沟通事项' },
    ],
    relatedTo: ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N'],
    relDesc: '接收各循环调整分录 → 汇总到试算表 → 生成报表' },
  { code: 'B', name: '风险评估', color: '#6750A4', count: 15, desc: '穿行测试、了解内控、风险识别',
    coreWps: [
      { code: 'B1', name: '了解被审计单位', role: '总控台', detail: '记录行业环境、经营模式、内控体系的了解过程' },
      { code: 'B2', name: '重大错报风险评估', role: '核心', detail: '识别财务报表层面和认定层面的重大错报风险' },
      { code: 'B3', name: '重要性水平确定', role: '基准', detail: '确定整体重要性、实际执行重要性、明显微小错报临界值' },
    ],
    relatedTo: ['C', 'D', 'E', 'F'],
    relDesc: '风险评估结果 → 决定控制测试范围 → 指导实质性程序设计' },
  { code: 'C', name: '控制测试', color: '#6750A4', count: 14, desc: '控制有效性测试、偏差评估',
    coreWps: [
      { code: 'C1', name: '控制测试总表', role: '总控台', detail: '汇总各业务循环关键控制的测试结论' },
      { code: 'C2', name: '穿行测试记录', role: '验证', detail: '对每个关键控制执行穿行测试，确认控制设计有效' },
      { code: 'C3', name: '控制偏差评估', role: '结论', detail: '评估控制偏差对审计策略的影响，决定是否信赖控制' },
    ],
    relatedTo: ['B', 'D', 'E', 'F'],
    relDesc: '依据 B 风险评估 → 测试关键控制 → 影响 D~N 实质性程序范围' },
  { code: 'D', name: '销售收入', color: '#E8590C', count: 8, desc: '收入确认、应收账款、信用减值',
    coreWps: [
      { code: 'D1', name: '应收票据', role: '核心', detail: '应收票据审计程序、账龄分析、贴现背书检查、坏账准备' },
      { code: 'D2', name: '应收账款', role: '核心', detail: '应收账款实质性程序、函证、坏账/ECL、账龄分析' },
      { code: 'D4', name: '营业收入/收入审定', role: '测试', detail: '收入确认测试、截止测试、收入审定表' },
    ],
    relatedTo: ['A', 'E', 'F', 'N'],
    relDesc: '从 TB 取应收/收入余额 → 函证+截止测试 → 调整分录回写 A2' },
  { code: 'E', name: '货币资金', color: '#E8590C', count: 7, desc: '银行存款、现金、银行函证',
    coreWps: [
      { code: 'E1', name: '货币资金总控台', role: '总控台', detail: '统筹银行存款函证、现金盘点、银行余额调节' },
      { code: 'E2', name: '银行存款函证', role: '核心', detail: '向银行发函确认余额，核对银行回函与账面差异' },
      { code: 'E3', name: '银行余额调节表', role: '调节', detail: '编制调节表，核实未达账项的真实性和完整性' },
    ],
    relatedTo: ['A', 'D', 'L'],
    relDesc: '从 TB 取银行/现金余额 → 函证+调节 → 与 D 收入回款/L 借款收付交叉验证' },
  { code: 'F', name: '采购存货', color: '#E8590C', count: 9, desc: '采购循环、存货计价、跌价准备',
    coreWps: [
      { code: 'F1', name: '采购存货总控台', role: '总控台', detail: '统筹存货监盘、计价测试、跌价准备计算' },
      { code: 'F2', name: '存货明细表', role: '核心', detail: '编制存货余额明细，执行计价测试和跌价准备复核' },
      { code: 'F3', name: '存货监盘记录', role: '实证', detail: '记录存货监盘过程、盘点差异及处理结论' },
    ],
    relatedTo: ['A', 'D', 'K'],
    relDesc: '从 TB 取存货/应付余额 → 监盘+计价 → 与 D 成本配比/K 费用归集交叉验证' },
  { code: 'G', name: '投资', color: '#E8590C', count: 6, desc: '长期股权投资、金融资产分类',
    coreWps: [
      { code: 'G1', name: '投资循环总控台', role: '总控台', detail: '统筹长投权益法核算、金融资产分类、公允价值计量' },
      { code: 'G2', name: '长期股权投资明细', role: '核心', detail: '验证投资成本、权益法调整、减值测试' },
    ],
    relatedTo: ['A', 'H', 'M'],
    relDesc: '从 TB 取投资余额 → 权益法/公允价值 → 与 M 权益变动/H 资产联动' },
  { code: 'H', name: '固定资产', color: '#E8590C', count: 8, desc: '固定资产、在建工程、使用权资产',
    coreWps: [
      { code: 'H1', name: '固定资产总控台', role: '总控台', detail: '统筹折旧重算、减值测试、在建工程转固' },
      { code: 'H2', name: '固定资产明细表', role: '核心', detail: '编制固定资产增减变动表，复核折旧计算准确性' },
      { code: 'H8', name: '使用权资产', role: '专项', detail: '新租赁准则下使用权资产确认和租赁负债计量' },
    ],
    relatedTo: ['A', 'K', 'L'],
    relDesc: '从 TB 取固定资产余额 → 折旧重算+减值 → 折旧费用归入 K/租赁负债归入 L' },
  { code: 'I', name: '无形资产', color: '#E8590C', count: 5, desc: '无形资产、商誉、开发支出',
    coreWps: [
      { code: 'I1', name: '无形资产总控台', role: '总控台', detail: '统筹摊销重算、商誉减值、研发支出资本化判断' },
      { code: 'I2', name: '无形资产明细表', role: '核心', detail: '编制无形资产增减变动表，复核摊销和减值' },
    ],
    relatedTo: ['A', 'K'],
    relDesc: '从 TB 取无形资产余额 → 摊销重算+商誉减值 → 摊销费用归入 K' },
  { code: 'J', name: '职工薪酬', color: '#E8590C', count: 4, desc: '薪酬计提、股份支付',
    coreWps: [
      { code: 'J1', name: '薪酬循环总控台', role: '总控台', detail: '统筹工资计提测试、社保核对、股份支付计量' },
      { code: 'J2', name: '薪酬计提测试', role: '核心', detail: '验证 12 个月工资计提的完整性和准确性' },
    ],
    relatedTo: ['A', 'K', 'N'],
    relDesc: '从 TB 取薪酬余额 → 计提测试 → 费用归入 K/个税归入 N' },
  { code: 'K', name: '管理费用', color: '#E8590C', count: 3, desc: '费用分析、跨循环减值汇总',
    coreWps: [
      { code: 'K1', name: '费用分析总控台', role: '总控台', detail: '汇总各循环费用类科目，执行 YoY 波动分析' },
      { code: 'K2', name: '跨循环减值汇总', role: '汇总', detail: '归集 D~I 各循环的减值/跌价准备，验证总额合理性' },
    ],
    relatedTo: ['A', 'D', 'F', 'H', 'I', 'J'],
    relDesc: '归集各循环费用和减值 → YoY 分析 → 异常波动追查到源循环' },
  { code: 'L', name: '筹资', color: '#E8590C', count: 4, desc: '借款、债券、利息计算',
    coreWps: [
      { code: 'L1', name: '筹资循环总控台', role: '总控台', detail: '统筹借款函证、利息重算、摊余成本计量' },
      { code: 'L2', name: '借款明细表', role: '核心', detail: '编制借款增减变动表，验证利息计算和期限分类' },
    ],
    relatedTo: ['A', 'E', 'H'],
    relDesc: '从 TB 取借款余额 → 函证+利息重算 → 与 E 银行流水/H 租赁负债交叉验证' },
  { code: 'M', name: '股东权益', color: '#E8590C', count: 3, desc: '权益变动、利润分配',
    coreWps: [
      { code: 'M1', name: '权益变动总控台', role: '总控台', detail: '编制权益变动表，验证利润分配和资本变动' },
      { code: 'M2', name: '权益变动明细', role: '核心', detail: '核对实收资本、资本公积、盈余公积、未分配利润变动' },
    ],
    relatedTo: ['A', 'G', 'N'],
    relDesc: '从 TB 取权益余额 → 变动核对 → 与 G 投资/N 所得税利润分配联动' },
  { code: 'N', name: '税费', color: '#E8590C', count: 3, desc: '所得税、递延税项',
    coreWps: [
      { code: 'N1', name: '税费循环总控台', role: '总控台', detail: '统筹所得税计算、递延税项确认、税费完整性' },
      { code: 'N2', name: '所得税计算表', role: '核心', detail: '编制应纳税所得额调整表，验证当期和递延所得税' },
    ],
    relatedTo: ['A', 'D', 'H', 'I', 'M'],
    relDesc: '从 TB 取税费余额 → 所得税重算 → 暂时性差异来源于 D~M 各循环' },
  { code: 'S', name: '专项程序', color: '#2E7D32', count: 5, desc: '持续经营、关联方、期后事项',
    coreWps: [
      { code: 'S1', name: '持续经营评估', role: '专项', detail: '评估被审计单位持续经营能力，识别重大不确定性' },
      { code: 'S2', name: '关联方交易', role: '专项', detail: '识别关联方关系，验证关联交易的公允性和披露完整性' },
      { code: 'S3', name: '期后事项', role: '专项', detail: '检查资产负债表日后事项，判断调整/非调整事项' },
    ],
    relatedTo: ['A', 'B'],
    relDesc: '独立于业务循环的特定审计程序 → 结论影响 A 审计报告意见' },
]

// 体系总览：count 用真实 wpIndex 计算（与循环详解一致，不再用硬编码假数字）
const guideOverviewData = computed(() =>
  guideOverviewMeta.map(cycle => ({
    ...cycle,
    count: ctx.wpIndex.value.filter((w: WpIndexItem) => w.wp_code?.startsWith(cycle.code)).length,
  }))
)

const guideFlowSteps = [
  { id: 'plan', icon: '📋', label: '审计计划', sub: '风险识别与策略制定', color: '#6750A4',
    detail: '风险导向审计的起点。了解被审计单位及其环境（行业、经营模式、治理结构），识别和评估重大错报风险，确定重要性水平（整体重要性→实际执行重要性→明显微小错报临界值），制定总体审计策略和具体审计计划。',
    riskFocus: '识别哪些领域可能存在重大错报风险，决定后续审计资源的分配方向',
    keyActions: [
      '了解被审计单位及其环境（行业风险、经营风险、财务风险）',
      '识别和评估重大错报风险（报表层面 + 认定层面）',
      '确定重要性水平（计算基准、百分比、最终金额）',
      '制定审计策略（综合方案 vs 实质性方案）',
      '编制审计计划（人员分工、时间安排、重点领域）',
    ],
    wpLinks: [
      { code: 'A1', name: '财务报告程序表', relation: '记录审计策略和总体计划' },
      { code: 'B1', name: '了解被审计单位', relation: '记录对单位环境的了解过程' },
      { code: 'B2', name: '重大错报风险评估', relation: '识别报表和认定层面风险' },
      { code: 'B3', name: '重要性水平确定', relation: '计算并记录三级重要性' },
    ],
    outputs: ['A', 'B'],
    nextStageLink: '风险评估结果直接决定→穿行测试的范围和重点' },
  { id: 'walkthrough', icon: '🔄', label: '穿行测试', sub: '验证控制设计有效性', color: '#7B1FA2',
    detail: '风险导向审计的第二步。针对计划阶段识别的关键业务流程，选取一笔完整交易从发起到记录全程追踪，验证内部控制是否按设计运行。穿行测试是控制测试的前提——只有设计有效的控制才值得进一步测试执行有效性。',
    riskFocus: '验证"纸面上的控制"是否真正落地执行，筛选出值得信赖的控制点',
    keyActions: [
      '选取关键业务流程（收入、采购、资金、薪酬等）',
      '每个流程选取一笔完整交易从头到尾追踪',
      '观察每个控制节点是否按设计执行（审批、核对、复核）',
      '记录控制设计缺陷（如缺少审批环节、职责未分离）',
      '评估控制设计有效性，决定哪些控制进入控制测试',
    ],
    wpLinks: [
      { code: 'B4', name: '穿行测试-收入循环', relation: '追踪一笔销售从合同→发货→开票→收款' },
      { code: 'B5', name: '穿行测试-采购循环', relation: '追踪一笔采购从请购→审批→验收→付款' },
      { code: 'B6', name: '穿行测试-资金循环', relation: '追踪一笔付款从申请→审批→支付→记账' },
      { code: 'C1', name: '控制测试总表', relation: '穿行测试结论→决定控制测试范围' },
    ],
    outputs: ['B', 'C'],
    nextStageLink: '穿行测试确认设计有效的控制→进入控制测试验证执行有效性' },
  { id: 'control', icon: '🔒', label: '控制测试', sub: '测试控制执行有效性', color: '#1976D2',
    detail: '风险导向审计的关键环节。对穿行测试确认设计有效的关键控制，扩大样本量测试其在整个审计期间是否一贯有效执行。控制测试结果直接影响实质性程序的性质、时间和范围——控制有效则可减少细节测试量。',
    riskFocus: '控制可信赖程度决定实质性程序的范围：控制越有效→细节测试越少',
    keyActions: [
      '确定测试样本量（基于控制频率：日常控制 25 笔、周控制 5 笔、月控制 2 笔）',
      '执行控制测试（检查审批签字、核对记录、系统日志）',
      '记录控制偏差（未执行/执行不当/延迟执行）',
      '评估偏差影响（个别偏差 vs 系统性失效）',
      '形成控制结论（可信赖/部分信赖/不可信赖）→调整实质性程序',
    ],
    wpLinks: [
      { code: 'C1', name: '控制测试总表', relation: '汇总各循环控制测试结论' },
      { code: 'C2', name: '穿行测试记录', relation: '穿行测试→控制测试的衔接依据' },
      { code: 'C3', name: '控制偏差评估', relation: '评估偏差对审计策略的影响' },
    ],
    outputs: ['C'],
    nextStageLink: '控制测试结论→决定实质性程序的范围和深度' },
  { id: 'substantive', icon: '🔍', label: '实质性程序', sub: '获取充分适当审计证据', color: '#E8590C',
    detail: '风险导向审计的核心执行阶段。针对各业务循环（D~N）执行细节测试和实质性分析程序，直接验证财务报表金额和披露的正确性。实质性程序的范围由前三个阶段的风险评估和控制测试结论决定——高风险领域+控制不可信赖=扩大测试范围。',
    riskFocus: '高风险认定（如收入完整性、资产存在性）必须执行更多细节测试，不能仅靠分析程序',
    keyActions: [
      '细节测试：函证（银行/应收/应付）、监盘（存货/现金）、重新计算（折旧/利息/税费）',
      '实质性分析程序：YoY 波动分析、毛利率趋势、费用率合理性',
      '截止测试：验证交易记录在正确期间（收入/成本跨期）',
      '编制审计调整分录（AJE/RJE）修正发现的错报',
      '评估未更正错报的汇总影响是否超过重要性',
    ],
    wpLinks: [
      { code: 'D1', name: '收入循环总控台', relation: '统筹收入确认+应收账款+信用减值' },
      { code: 'E1', name: '货币资金总控台', relation: '统筹银行函证+余额调节+现金盘点' },
      { code: 'F1', name: '采购存货总控台', relation: '统筹存货监盘+计价+跌价准备' },
      { code: 'H1', name: '固定资产总控台', relation: '统筹折旧重算+减值+在建转固' },
      { code: 'A2', name: '调整分录汇总表', relation: '归集各循环 AJE/RJE 更新试算表' },
    ],
    outputs: ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N'],
    nextStageLink: '各循环审计结论+调整分录→汇总到完成阶段形成审计意见' },
  { id: 'complete', icon: '✅', label: '审计完成', sub: '汇总结论与出具报告', color: '#2E7D32',
    detail: '风险导向审计的收尾阶段。汇总全部审计发现，评价未更正错报的汇总影响，执行期后事项审查和持续经营评估，复核底稿质量，形成审计意见并出具审计报告。',
    riskFocus: '最终评估：汇总错报是否超过重要性？是否存在影响审计意见的重大事项？',
    keyActions: [
      '汇总未更正错报，评估对报表整体的影响',
      '执行期后事项审查（资产负债表日→报告日之间的重大事项）',
      '评估持续经营假设的适当性',
      '获取管理层声明书',
      '复核底稿质量（项目质量控制复核 EQCR）',
      '形成审计意见（无保留/保留/否定/无法表示）',
      '出具审计报告',
    ],
    wpLinks: [
      { code: 'A1', name: '财务报告程序表', relation: '汇总审计结论，记录意见形成过程' },
      { code: 'A2', name: '调整分录汇总表', relation: '最终确认所有 AJE/RJE 的影响' },
      { code: 'S1', name: '持续经营评估', relation: '评估持续经营能力和重大不确定性' },
      { code: 'S2', name: '关联方交易', relation: '确认关联方披露的完整性' },
      { code: 'S3', name: '期后事项', relation: '检查报告日前的重大事项' },
    ],
    outputs: ['A', 'S'],
    nextStageLink: '' },
]

const guideRelations = [
  { target: 'D', label: '销售收入', desc: '从 TB 取应收/收入余额 → 编制明细表' },
  { target: 'E', label: '货币资金', desc: '从 TB 取银行/现金余额 → 函证核对' },
  { target: 'F', label: '采购存货', desc: '从 TB 取存货/应付余额 → 计价测试' },
  { target: 'H', label: '固定资产', desc: '从 TB 取固定资产余额 → 折旧重算' },
  { target: 'N', label: '税费', desc: '从 TB 取税费余额 → 所得税计算' },
  { target: 'A', label: '报表调整', desc: '各循环调整分录 → 汇总到试算表' },
]

// 底稿与报表/附注/试算表的完整关系图数据
const guideFullRelations = [
  { id: 'tb', name: '试算表', icon: '📊', color: '#6750A4', type: 'center',
    desc: '审计工作的数据枢纽，汇总所有科目的未审数、调整数、审定数',
    connections: [
      { to: '底稿', direction: 'out', label: '提供科目余额', style: 'solid' },
      { to: '调整分录', direction: 'in', label: '接收 AJE/RJE', style: 'solid' },
      { to: '报表', direction: 'out', label: '审定数生成报表', style: 'solid' },
    ] },
  { id: 'wp', name: '底稿 (D~N)', icon: '📋', color: '#E8590C', type: 'node',
    desc: '各业务循环的实质性程序底稿，执行细节测试获取审计证据',
    connections: [
      { to: '试算表', direction: 'in', label: '取数（科目余额）', style: 'solid' },
      { to: '调整分录', direction: 'out', label: '发现错报→建议调整', style: 'solid' },
      { to: '附注', direction: 'out', label: '提供披露数据', style: 'dashed' },
    ] },
  { id: 'adj', name: '调整分录', icon: '✏️', color: '#D32F2F', type: 'node',
    desc: 'AJE（审计调整）和 RJE（重分类），修正报表错报',
    connections: [
      { to: '试算表', direction: 'out', label: '更新审定数', style: 'solid' },
      { to: '报表', direction: 'out', label: '影响报表金额', style: 'solid' },
    ] },
  { id: 'report', name: '财务报表', icon: '📑', color: '#1976D2', type: 'node',
    desc: '资产负债表、利润表、现金流量表等，由试算表审定数自动生成',
    connections: [
      { to: '附注', direction: 'out', label: '报表行→附注明细', style: 'solid' },
      { to: '审计报告', direction: 'out', label: '支撑审计意见', style: 'dashed' },
    ] },
  { id: 'note', name: '附注', icon: '📝', color: '#2E7D32', type: 'node',
    desc: '财务报表附注，对报表项目的详细说明和补充披露',
    connections: [
      { to: '报表', direction: 'in', label: '引用报表金额', style: 'solid' },
      { to: '底稿', direction: 'in', label: '引用底稿数据', style: 'dashed' },
    ] },
  { id: 'opinion', name: '审计报告', icon: '📄', color: '#455A64', type: 'endpoint',
    desc: '最终产出物，基于全部审计证据形成审计意见',
    connections: [
      { to: '报表', direction: 'in', label: '对报表发表意见', style: 'solid' },
      { to: '底稿', direction: 'in', label: '底稿支撑结论', style: 'dashed' },
    ] },
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
  return guideOverviewData.value.map(cycle => {
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

/* ─── 工作台视图容器 ─── */
.gt-wp-workbench-view {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

/* ─── 循环进度概览：标题行 ─── */
.gt-wpb-progress-header {
  display: flex;
  align-items: center;
  gap: var(--gt-space-sm, 8px);
  padding: 4px 2px 10px;
}
.gt-wpb-progress-header__title {
  font-size: var(--gt-font-size-md, 14px);
  font-weight: 600;
  color: var(--gt-color-text-primary, #303133);
}
.gt-wpb-progress-header__filter-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: var(--gt-font-size-xs, 11px);
  color: var(--gt-color-primary, #4b2d77);
  background: var(--gt-color-primary-light, #f0ecf7);
  border-radius: 10px;
  padding: 2px 10px;
}
.gt-wpb-progress-header__clear {
  cursor: pointer;
  font-weight: 700;
  opacity: 0.6;
}
.gt-wpb-progress-header__clear:hover { opacity: 1; }

/* ─── 循环进度卡片网格 ─── */
.gt-wpb-progress-summary {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
  padding: 2px 2px 16px;
}
.gt-wpb-prog-card {
  background: var(--el-bg-color, #fff);
  border: 1px solid var(--gt-color-border-lighter, #ebeef5);
  border-radius: 10px;
  padding: 14px 16px;
  cursor: pointer;
  transition: box-shadow 0.18s ease, border-color 0.18s ease, transform 0.18s ease;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}
.gt-wpb-prog-card:hover {
  border-color: var(--gt-color-primary, #4b2d77);
  box-shadow: 0 4px 14px rgba(75, 45, 119, 0.12);
  transform: translateY(-2px);
}
.gt-wpb-prog-card.is-active {
  border-color: var(--gt-color-primary, #4b2d77);
  background: var(--gt-color-primary-light, #f0ecf7);
  box-shadow: 0 0 0 1px var(--gt-color-primary, #4b2d77) inset;
}
.gt-wpb-prog-card__header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.gt-wpb-prog-card__code {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 26px;
  height: 26px;
  padding: 0 6px;
  font-size: var(--gt-font-size-sm, 12px);
  font-weight: 700;
  color: #fff;
  background: var(--gt-color-primary, #4b2d77);
  border-radius: 6px;
}
.gt-wpb-prog-card__name {
  font-size: var(--gt-font-size-base, 13px);
  font-weight: 600;
  color: var(--gt-color-text-primary, #303133);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.gt-wpb-prog-card__detail {
  margin-top: 8px;
  font-size: var(--gt-font-size-xs, 11px);
  color: var(--gt-color-text-secondary, #909399);
  text-align: right;
}

/* ─── 工作台底稿列表 ─── */
.gt-wpb-workbench-list {
  flex: 1;
  min-height: 0;
}
.gt-wpb-workbench-list :deep(.el-table) {
  border-radius: 8px;
  overflow: hidden;
}
.gt-wpb-workbench-list :deep(.el-table__row) {
  cursor: pointer;
}

/* ─── 默认列表视图 ─── */
.gt-wp-list-default {
  flex: 1;
  min-height: 0;
}
.gt-wp-list-default :deep(.el-table) {
  border-radius: 8px;
  overflow: hidden;
}
.gt-wp-list-default :deep(.el-table__row) {
  cursor: pointer;
}

/* ─── 手册视图样式（从 18344aca 恢复） ─── */
.gt-wp-guide-view {
  flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 16px;
  background: var(--gt-color-bg-white); border-radius: var(--gt-radius-md);
  box-shadow: var(--gt-shadow-sm); padding: 20px 24px; overflow-y: auto;
}
.gt-wp-guide-view__nav {
  display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px;
  padding-bottom: 12px; border-bottom: 1px solid var(--gt-color-border-light, #f0f0f0);
}
.gt-wp-guide-section { }
.gt-wp-guide-section__title {
  margin: 0 0 6px; font-size: 16px; font-weight: 600; color: var(--gt-color-text-primary);
}
.gt-wp-guide-section__desc {
  margin: 0 0 20px; font-size: 13px; color: var(--gt-color-text-tertiary); line-height: 1.6;
}

/* 体系总览网格 */
.gt-wp-guide-overview-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 10px;
}
.gt-wp-guide-overview-card {
  display: flex; align-items: center; gap: 12px; padding: 12px 14px;
  border: 1px solid var(--gt-color-border-light, #f0f0f0); border-radius: 10px;
  cursor: pointer; transition: all 0.15s;
}
.gt-wp-guide-overview-card:hover {
  background: var(--gt-color-primary-bg, #f8f5ff); border-color: var(--gt-color-primary);
}
.gt-wp-guide-overview-card__badge {
  min-width: 32px; height: 32px; display: flex; align-items: center; justify-content: center;
  border-radius: 8px; font-size: 14px; font-weight: 700; color: #fff;
}
.gt-wp-guide-overview-card__info { flex: 1; min-width: 0; }
.gt-wp-guide-overview-card__name { font-size: 14px; font-weight: 600; color: var(--gt-color-text-primary); }
.gt-wp-guide-overview-card__meta { font-size: 12px; color: var(--gt-color-text-tertiary); margin-top: 2px; }
.gt-wp-guide-overview-card__arrow { font-size: 18px; color: var(--gt-color-text-placeholder); }
.gt-wp-guide-legend {
  display: flex; gap: 16px; margin-top: 16px; padding-top: 12px;
  border-top: 1px solid var(--gt-color-border-light, #f0f0f0);
}
.gt-wp-guide-legend__item { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--gt-color-text-secondary); }
.gt-wp-guide-legend__dot { width: 10px; height: 10px; border-radius: 3px; }

/* 审计流程图 */
.gt-wp-guide-flow-chart {
  display: flex; align-items: flex-start; gap: 0; flex-wrap: wrap; justify-content: center;
  padding: 20px 0; margin-bottom: 20px;
}
.gt-wp-guide-flow-step { display: flex; align-items: center; }
.gt-wp-guide-flow-step__node {
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  padding: 16px 20px; border: 2px solid; border-radius: 12px;
  background: var(--gt-color-bg-white); min-width: 120px; text-align: center;
}
.gt-wp-guide-flow-step__icon { font-size: 24px; }
.gt-wp-guide-flow-step__label { font-size: 13px; font-weight: 600; color: var(--gt-color-text-primary); }
.gt-wp-guide-flow-step__sub { font-size: 11px; color: var(--gt-color-text-tertiary); }
.gt-wp-guide-flow-step__arrow { font-size: 20px; color: var(--gt-color-text-placeholder); margin: 0 8px; }

/* 流程详情 */
.gt-wp-guide-flow-detail { display: flex; flex-direction: column; gap: 12px; }
.gt-wp-guide-flow-detail__item {
  padding: 12px 16px; border-radius: 8px; border: 1px solid var(--gt-color-border-light, #f0f0f0);
}
.gt-wp-guide-flow-detail__header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.gt-wp-guide-flow-detail__badge {
  width: 28px; height: 28px; display: flex; align-items: center; justify-content: center;
  border-radius: 6px; font-size: 14px;
}
.gt-wp-guide-flow-detail__name { font-size: 14px; font-weight: 600; color: var(--gt-color-text-primary); }
.gt-wp-guide-flow-detail__sub-tag {
  font-size: 11px; color: var(--gt-color-text-tertiary); padding: 2px 8px;
  background: var(--gt-color-bg, #fafafa); border-radius: 4px;
}
.gt-wp-guide-flow-detail__desc { font-size: 13px; color: var(--gt-color-text-secondary); margin-bottom: 12px; line-height: 1.6; }

/* 风险导向要点 */
.gt-wp-guide-flow-risk {
  display: flex; align-items: flex-start; gap: 6px; margin-bottom: 10px;
  padding: 8px 12px; background: #fff8e1; border-radius: 6px; border-left: 3px solid #f9a825;
}
.gt-wp-guide-flow-risk__icon { flex-shrink: 0; }
.gt-wp-guide-flow-risk__text { font-size: 12px; color: #e65100; line-height: 1.5; font-weight: 500; }

/* 关键工作列表 */
.gt-wp-guide-flow-actions { margin-bottom: 12px; }
.gt-wp-guide-flow-actions__title { font-size: 12px; font-weight: 600; color: var(--gt-color-text-primary); margin-bottom: 6px; }
.gt-wp-guide-flow-actions__list { display: flex; flex-direction: column; gap: 4px; }
.gt-wp-guide-flow-actions__item {
  display: flex; align-items: flex-start; gap: 8px; font-size: 12px; color: var(--gt-color-text-secondary); line-height: 1.5;
}
.gt-wp-guide-flow-actions__bullet {
  flex-shrink: 0; width: 18px; height: 18px; display: flex; align-items: center; justify-content: center;
  border-radius: 50%; background: var(--gt-color-primary-bg, #f0ebff); color: var(--gt-color-primary);
  font-size: 10px; font-weight: 700;
}

/* 关联底稿 */
.gt-wp-guide-flow-wps { margin-bottom: 10px; }
.gt-wp-guide-flow-wps__title { font-size: 12px; font-weight: 600; color: var(--gt-color-text-primary); margin-bottom: 6px; }
.gt-wp-guide-flow-wps__list { display: flex; flex-direction: column; gap: 4px; }
.gt-wp-guide-flow-wps__item {
  display: flex; align-items: center; gap: 8px; padding: 6px 10px;
  border-radius: 6px; border: 1px solid var(--gt-color-border-light, #f0f0f0);
  cursor: pointer; transition: all 0.15s; font-size: 12px;
}
.gt-wp-guide-flow-wps__item:hover { background: var(--gt-color-primary-bg, #f8f5ff); border-color: var(--gt-color-primary); }
.gt-wp-guide-flow-wps__code { font-weight: 700; color: var(--gt-color-primary); min-width: 36px; }
.gt-wp-guide-flow-wps__name { font-weight: 600; color: var(--gt-color-text-primary); min-width: 120px; }
.gt-wp-guide-flow-wps__rel { flex: 1; color: var(--gt-color-text-tertiary); }

/* 阶段衔接提示 */
.gt-wp-guide-flow-next {
  font-size: 12px; color: var(--gt-color-primary); font-weight: 500;
  padding: 6px 10px; background: var(--gt-color-primary-bg, #f8f5ff);
  border-radius: 6px; margin-top: 4px;
}
.gt-wp-guide-flow-arrow-text { font-size: 10px; color: var(--gt-color-text-tertiary); }
.gt-wp-guide-flow-detail__outputs { font-size: 12px; color: var(--gt-color-text-tertiary); }
.gt-wp-guide-flow-detail__output-tag {
  display: inline-block; padding: 2px 8px; margin: 2px 4px; border-radius: 4px;
  background: var(--gt-color-primary-bg, #f8f5ff); color: var(--gt-color-primary);
  font-weight: 600; cursor: pointer; transition: background 0.15s;
}
.gt-wp-guide-flow-detail__output-tag:hover { background: var(--gt-color-primary); color: #fff; }

/* 底稿关系图 - 数据流转主线 */
.gt-wp-guide-dataflow {
  margin-bottom: 24px; padding: 16px; background: var(--gt-color-bg, #fafafa); border-radius: 12px;
}
.gt-wp-guide-dataflow__title { font-size: 14px; font-weight: 600; color: var(--gt-color-text-primary); margin-bottom: 12px; }
.gt-wp-guide-dataflow__chain {
  display: flex; align-items: center; gap: 0; overflow-x: auto; padding: 8px 0;
}
.gt-wp-guide-dataflow__step { display: flex; align-items: center; }
.gt-wp-guide-dataflow__node {
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  padding: 10px 14px; background: var(--gt-color-bg-white); border-radius: 10px;
  border: 1px solid var(--gt-color-border-light, #e8e8e8); min-width: 70px;
}
.gt-wp-guide-dataflow__icon { font-size: 20px; }
.gt-wp-guide-dataflow__name { font-size: 11px; font-weight: 600; color: var(--gt-color-text-primary); white-space: nowrap; }
.gt-wp-guide-dataflow__arrow {
  display: flex; flex-direction: column; align-items: center; gap: 2px; margin: 0 6px;
}
.gt-wp-guide-dataflow__arrow-label { font-size: 10px; color: var(--gt-color-text-tertiary); white-space: nowrap; }
.gt-wp-guide-dataflow__arrow-icon { font-size: 16px; color: var(--gt-color-primary); }

/* 模块关系详解 */
.gt-wp-guide-modules { margin-bottom: 20px; }
.gt-wp-guide-modules__title { font-size: 14px; font-weight: 600; color: var(--gt-color-text-primary); margin-bottom: 12px; }
.gt-wp-guide-modules__grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px;
}
.gt-wp-guide-module-card {
  padding: 14px 16px; border: 1px solid var(--gt-color-border-light, #f0f0f0);
  border-radius: 10px; transition: border-color 0.15s;
}
.gt-wp-guide-module-card:hover { border-color: var(--gt-color-primary); }
.gt-wp-guide-module-card__header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.gt-wp-guide-module-card__icon {
  width: 32px; height: 32px; display: flex; align-items: center; justify-content: center;
  border-radius: 8px; font-size: 16px;
}
.gt-wp-guide-module-card__name { font-size: 14px; font-weight: 600; color: var(--gt-color-text-primary); }
.gt-wp-guide-module-card__desc { font-size: 12px; color: var(--gt-color-text-secondary); margin-bottom: 10px; line-height: 1.5; }
.gt-wp-guide-module-card__connections { display: flex; flex-direction: column; gap: 4px; }
.gt-wp-guide-module-card__conn {
  display: flex; align-items: center; gap: 6px; font-size: 12px;
  padding: 4px 8px; border-radius: 4px; background: var(--gt-color-bg, #fafafa);
}
.gt-wp-guide-module-card__conn-dir { font-weight: 700; font-size: 14px; }
.gt-wp-guide-module-card__conn-dir.is-out { color: var(--gt-color-primary); }
.gt-wp-guide-module-card__conn-dir.is-in { color: var(--gt-color-success); }
.gt-wp-guide-module-card__conn-to { font-weight: 600; color: var(--gt-color-text-primary); }
.gt-wp-guide-module-card__conn-label { flex: 1; color: var(--gt-color-text-secondary); }
.gt-wp-guide-module-card__conn-style {
  padding: 1px 6px; border-radius: 3px; font-size: 10px; font-weight: 600;
}
.gt-wp-guide-module-card__conn-style.is-auto { background: #e8f5e9; color: #2e7d32; }
.gt-wp-guide-module-card__conn-style.is-manual { background: #fff3e0; color: #e65100; }

/* 关键说明 */
.gt-wp-guide-relation-notes { margin-bottom: 16px; }
.gt-wp-guide-relation-notes__title { font-size: 14px; font-weight: 600; color: var(--gt-color-text-primary); margin-bottom: 10px; }
.gt-wp-guide-relation-notes__list { display: flex; flex-direction: column; gap: 8px; }
.gt-wp-guide-relation-notes__item {
  font-size: 13px; color: var(--gt-color-text-secondary); line-height: 1.6;
  padding: 8px 12px; border-radius: 6px; background: var(--gt-color-bg, #fafafa);
  border-left: 3px solid var(--gt-color-primary);
}
.gt-wp-guide-relation-notes__item strong { color: var(--gt-color-text-primary); }

.gt-wp-guide-relation-legend { display: flex; gap: 20px; margin-top: 12px; }
.gt-wp-guide-relation-legend__item { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--gt-color-text-secondary); }
.gt-wp-guide-relation-legend__dot { width: 10px; height: 10px; border-radius: 3px; }

/* 循环详解 */
.gt-wp-guide-cycles-grid { display: flex; flex-direction: column; gap: 8px; }
.gt-wp-guide-cycle-card {
  border: 1px solid var(--gt-color-border-light, #f0f0f0); border-radius: 10px;
  overflow: hidden; cursor: pointer; transition: all 0.15s;
}
.gt-wp-guide-cycle-card:hover { border-color: var(--gt-color-primary); }
.gt-wp-guide-cycle-card.is-active { border-color: var(--gt-color-primary); background: var(--gt-color-primary-bg, #faf8ff); }
.gt-wp-guide-cycle-card__header {
  display: flex; align-items: center; gap: 10px; padding: 12px 16px;
}
.gt-wp-guide-cycle-card__badge {
  min-width: 28px; height: 28px; display: flex; align-items: center; justify-content: center;
  border-radius: 6px; font-size: 13px; font-weight: 700; color: #fff;
}
.gt-wp-guide-cycle-card__name { flex: 1; font-size: 14px; font-weight: 600; color: var(--gt-color-text-primary); }
.gt-wp-guide-cycle-card__count { font-size: 12px; color: var(--gt-color-text-tertiary); }
.gt-wp-guide-cycle-card__body { padding: 0 16px 14px; }
.gt-wp-guide-cycle-card__desc { font-size: 13px; color: var(--gt-color-text-secondary); margin-bottom: 10px; }
.gt-wp-guide-cycle-card__wp-list { display: flex; flex-direction: column; gap: 4px; }
.gt-wp-guide-cycle-card__wp-item {
  display: flex; align-items: center; gap: 8px; padding: 6px 10px;
  border-radius: 6px; transition: background 0.15s;
}
.gt-wp-guide-cycle-card__wp-item:hover { background: var(--gt-color-bg-white); }
.gt-wp-guide-cycle-card__wp-code { font-size: 12px; font-weight: 600; color: var(--gt-color-primary); min-width: 50px; }
.gt-wp-guide-cycle-card__wp-name { flex: 1; font-size: 13px; color: var(--gt-color-text-primary); }
.gt-wp-guide-cycle-card__wp-arrow { font-size: 14px; color: var(--gt-color-text-placeholder); }

/* 核心底稿区块 */
.gt-wp-guide-cycle-core { margin-bottom: 14px; }
.gt-wp-guide-cycle-core__title {
  font-size: 13px; font-weight: 600; color: var(--gt-color-text-primary); margin-bottom: 8px;
}
.gt-wp-guide-cycle-core__list { display: flex; flex-direction: column; gap: 8px; }
.gt-wp-guide-cycle-core__item {
  padding: 10px 12px; border-radius: 8px; border: 1px solid var(--gt-color-border-light, #f0f0f0);
  cursor: pointer; transition: all 0.15s;
}
.gt-wp-guide-cycle-core__item:hover { background: var(--gt-color-bg-white); border-color: var(--gt-color-primary); }
.gt-wp-guide-cycle-core__item-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.gt-wp-guide-cycle-core__code { font-size: 13px; font-weight: 700; color: var(--gt-color-primary); }
.gt-wp-guide-cycle-core__name { font-size: 13px; font-weight: 600; color: var(--gt-color-text-primary); flex: 1; }
.gt-wp-guide-cycle-core__detail { font-size: 12px; color: var(--gt-color-text-secondary); line-height: 1.5; }

/* 关联循环区块 */
.gt-wp-guide-cycle-rel { margin-bottom: 14px; }
.gt-wp-guide-cycle-rel__title {
  font-size: 13px; font-weight: 600; color: var(--gt-color-text-primary); margin-bottom: 4px;
}
.gt-wp-guide-cycle-rel__desc {
  font-size: 12px; color: var(--gt-color-text-secondary); margin-bottom: 8px; line-height: 1.5;
}
.gt-wp-guide-cycle-rel__tags { display: flex; flex-wrap: wrap; gap: 6px; }
.gt-wp-guide-cycle-rel__tag {
  display: inline-block; padding: 4px 10px; border-radius: 6px;
  background: var(--gt-color-primary-bg, #f8f5ff); color: var(--gt-color-primary);
  font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.15s;
}
.gt-wp-guide-cycle-rel__tag:hover { background: var(--gt-color-primary); color: #fff; }

/* 完整底稿清单区块 */
.gt-wp-guide-cycle-wplist { }
.gt-wp-guide-cycle-wplist__title {
  font-size: 13px; font-weight: 600; color: var(--gt-color-text-primary); margin-bottom: 8px;
}

/* 列表视图分页 */
.gt-pagination { margin-top: 12px; display: flex; justify-content: flex-end; }
</style>
