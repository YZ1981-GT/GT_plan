<template>
  <div class="gt-audit-nav" :class="{ 'is-collapsed': collapsed }">
    <div class="gt-audit-nav-header" @click="toggleCollapsed">
      <span class="gt-audit-nav-title">
        <span class="gt-audit-nav-icon">🧭</span>
        审计导航图
      </span>
      <el-button text size="small">{{ collapsed ? '展开 ▼' : '折叠 ▲' }}</el-button>
    </div>

    <div v-show="!collapsed" class="gt-audit-nav-body">
      <!-- 2.4a 5 项认定卡片 -->
      <section class="gt-audit-nav-section">
        <h4 class="gt-audit-nav-section-title">📊 财务报表认定</h4>
        <div class="gt-audit-nav-assertions">
          <div
            v-for="a in assertionCards"
            :key="a.code"
            class="gt-assertion-card"
            :title="a.tip"
          >
            <div class="gt-assertion-card__head">
              <span class="gt-assertion-card__code">{{ a.code }}</span>
              <el-badge :value="a.count" :max="99" :hidden="!a.count" type="primary" class="gt-assertion-card__badge">
                <span class="gt-assertion-card__name">{{ a.name }}</span>
              </el-badge>
            </div>
          </div>
        </div>
      </section>

      <!-- 2.4b 风险评估摘要 -->
      <section class="gt-audit-nav-section">
        <h4 class="gt-audit-nav-section-title">⚠️ 风险评估</h4>
        <div v-if="prerequisiteStatus.loading.value" class="gt-audit-nav-loading">
          <el-icon class="is-loading"><Loading /></el-icon> 加载前置状态...
        </div>
        <div v-else class="gt-risk-summary">
          <div
            v-for="item in prerequisiteStatus.items.value"
            :key="item.wp_code"
            class="gt-risk-summary-row"
            :class="`is-${item.state}`"
          >
            <span class="gt-risk-summary-icon">{{ stateIcon(item.state) }}</span>
            <span class="gt-risk-summary-code">{{ item.wp_code }}</span>
            <span class="gt-risk-summary-name">{{ item.wp_name }}</span>
            <span v-if="item.risk_level" class="gt-risk-summary-level">
              {{ item.risk_level }}
            </span>
          </div>
        </div>
      </section>

      <!-- 2.4c 程序执行进度流程图 SVG -->
      <section class="gt-audit-nav-section">
        <h4 class="gt-audit-nav-section-title">📈 程序执行进度</h4>
        <svg class="gt-audit-nav-progress-svg" :viewBox="`0 0 600 90`" preserveAspectRatio="xMidYMid meet">
          <!-- 5 段流程：目标→风险→设计→执行→结论 -->
          <g v-for="(seg, idx) in progressSegments" :key="seg.key">
            <!-- 节点圆 -->
            <circle
              :cx="60 + idx * 120"
              :cy="45"
              :r="22"
              :fill="seg.color"
              stroke="#4b2d77"
              stroke-width="2"
            />
            <text
              :x="60 + idx * 120"
              :y="50"
              text-anchor="middle"
              fill="white"
              font-size="14"
              font-weight="bold"
            >{{ seg.icon }}</text>
            <!-- 节点标签 -->
            <text
              :x="60 + idx * 120"
              :y="82"
              text-anchor="middle"
              fill="#333"
              font-size="11"
            >{{ seg.label }}</text>
            <!-- 连接线（非最后一段） -->
            <line
              v-if="idx < progressSegments.length - 1"
              :x1="82 + idx * 120"
              :y1="45"
              :x2="38 + (idx + 1) * 120"
              :y2="45"
              stroke="#bbb"
              stroke-width="2"
              stroke-dasharray="4 2"
            />
          </g>
        </svg>
        <div class="gt-audit-nav-progress-legend">
          <span><span class="gt-dot" style="background: #67c23a"></span> 已完成</span>
          <span><span class="gt-dot" style="background: #e6a23c"></span> 进行中</span>
          <span><span class="gt-dot" style="background: #909399"></span> 未开始</span>
        </div>
      </section>

      <!-- 2.4e 程序适用性裁剪 tab -->
      <section class="gt-audit-nav-section">
        <h4 class="gt-audit-nav-section-title" style="cursor: pointer" @click="showTrimmingPanel = !showTrimmingPanel">
          ✂️ 程序适用性
          <el-button text size="small">{{ showTrimmingPanel ? '收起 ▲' : '展开 ▼' }}</el-button>
        </h4>
        <ProcedureTrimmingPanel
          v-if="showTrimmingPanel"
          :project-id="props.projectId"
          :wp-id="props.wpId"
          :sheet-key="resolvedSheetKey"
        />
      </section>

      <!-- 2.4f 裁剪汇总（合伙人/质控视角） -->
      <section v-if="canViewTrimSummary" class="gt-audit-nav-section">
        <h4 class="gt-audit-nav-section-title" style="cursor: pointer" @click="showTrimmingSummary = !showTrimmingSummary">
          📊 裁剪汇总（合伙人/质控）
          <el-button text size="small">{{ showTrimmingSummary ? '收起 ▲' : '展开 ▼' }}</el-button>
        </h4>
        <TrimmingSummaryPanel
          v-if="showTrimmingSummary"
          :fetch-summary-fn="trimSummaryFns.fetchSummary"
          :fetch-history-fn="trimSummaryFns.fetchHistory"
        />
      </section>

      <!-- 2.4d 关键风险提示 + 底稿间关系图 -->
      <section class="gt-audit-nav-section">
        <h4 class="gt-audit-nav-section-title">
          🤖 关键风险提示
          <el-button text size="small" :loading="aiLoading" @click="generateAiTip">✨ AI 检测</el-button>
        </h4>
        <div v-if="aiTipText" class="gt-ai-tip">
          {{ aiTipText }}
        </div>
        <div v-else class="gt-ai-tip-empty">
          点击"✨ AI 检测"基于 {{ wpCode || '当前底稿' }} 数据生成关键风险提示
        </div>
      </section>

      <section class="gt-audit-nav-section">
        <h4 class="gt-audit-nav-section-title">🔗 底稿间关系</h4>
        <div v-if="relationLoading" class="gt-audit-nav-loading">
          <el-icon class="is-loading"><Loading /></el-icon> 加载关系图...
        </div>
        <div v-else-if="!hasRelations" class="gt-audit-nav-empty">
          当前底稿（{{ wpCode }}）暂无跨底稿引用关系
        </div>
        <svg v-else class="gt-audit-nav-graph-svg" :viewBox="`0 0 600 ${graphHeight}`" preserveAspectRatio="xMidYMid meet">
          <g v-for="node in graphNodes" :key="node.id">
            <rect
              :x="node.x" :y="node.y"
              :width="node.w || 70" :height="22"
              rx="4" ry="4"
              :fill="node.color"
              stroke="#4b2d77"
              stroke-width="1"
            />
            <text
              :x="node.x + (node.w || 70) / 2"
              :y="node.y + 15"
              text-anchor="middle"
              fill="white"
              font-size="11"
            >{{ node.label }}</text>
          </g>
          <g v-for="(edge, idx) in graphEdges" :key="`edge-${idx}`">
            <line
              :x1="edge.x1" :y1="edge.y1" :x2="edge.x2" :y2="edge.y2"
              :stroke="edge.color || '#999'" stroke-width="1.5"
              :marker-end="`url(#arrow-${edge.color || 'gray'})`"
            />
          </g>
          <defs>
            <marker id="arrow-gray" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
              <polygon points="0 0, 6 3, 0 6" fill="#999" />
            </marker>
          </defs>
        </svg>
        <div v-if="hasRelations" class="gt-audit-nav-graph-legend">
          <span><span class="gt-graph-dot" style="background: #909399"></span> 上游（被本底稿依赖）</span>
          <span><span class="gt-graph-dot" style="background: #4b2d77"></span> 当前底稿</span>
          <span><span class="gt-graph-dot" style="background: #5e35b1"></span> 下游（依赖本底稿）</span>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * WorkpaperAuditNav — E1 审计导航图（Sprint 2 Task 2.4 + 2.4a-d）
 *
 * 锚定 requirements F1.4 + F0.1 + F5.6
 *
 * 5 个区块：
 * - 2.4a 5 项认定卡片（A 存在/B 完整性/C 权利义务/D 准确性/E 列报）+ 程序数 badge
 * - 2.4b 风险评估摘要（B23-2/B51-3/C3 通过 usePrerequisiteStatus）
 * - 2.4c 程序执行进度流程图 SVG（5 段节点+颜色联动）
 * - 2.4d 关键风险提示（LLM 异常检测）+ 底稿间关系图（SVG 节点链接图）
 */
import { ref, computed, onMounted } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { useProcedureStatus } from '@/composables/useProcedureStatus'
import { usePrerequisiteStatus } from '@/composables/usePrerequisiteStatus'
import { useProcedureTrimming } from '@/composables/useProcedureTrimming'
import { usePermission } from '@/composables/usePermission'
import { resolveProcedureSheetKey } from '@/utils/resolveProcedureSheetKey'
import { api } from '@/services/apiProxy'
import ProcedureTrimmingPanel from './ProcedureTrimmingPanel.vue'
import TrimmingSummaryPanel from './TrimmingSummaryPanel.vue'

interface Props {
  projectId: string
  wpId: string
  wpCode?: string
  defaultCollapsed?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  wpCode: 'E1',
  defaultCollapsed: false,
})

const collapsed = ref(props.defaultCollapsed)
function toggleCollapsed() {
  collapsed.value = !collapsed.value
}

// 程序适用性裁剪面板显隐
const showTrimmingPanel = ref(false)

// 裁剪汇总面板显隐 + RBAC（仅 partner/qc/admin/manager 可见）
const showTrimmingSummary = ref(false)
const { role: currentRole } = usePermission()
const canViewTrimSummary = computed(() => {
  return ['admin', 'partner', 'qc', 'quality_control', 'manager', 'eqcr'].includes(currentRole.value)
})

// 裁剪汇总数据源（复用 useProcedureTrimming 的 fetchSummary/fetchHistory）
const trimSummaryFns = useProcedureTrimming(props.projectId, props.wpId, '')

// F-F13 Task 3.7: 按 wp_code 路由程序状态数据源（E1→e1a / D2→d2a / D4→d4a / F2→f2a 等）
// H-F13 Task 3.6: 加 H 循环路由 H1→h1a / H2→h2a / H3→h3a / H8→h8a / H9→h9a

const resolvedSheetKey = resolveProcedureSheetKey(props.wpCode)

const procedureStatus = useProcedureStatus(
  props.projectId,
  props.wpId,
  resolvedSheetKey,
)
const prerequisiteStatus = usePrerequisiteStatus(props.projectId, props.wpCode)

// 2.4a 5 项认定卡片（按 wp_code cycle 派生科目类型描述 + procedure_status 动态计数）
const assertionTipsByCycle: Record<string, Record<string, string>> = {
  A: { A: '报表项目确实存在', B: '所有报表项目均已记录', C: '报表项目所有权归属清晰', D: '金额、计价、分摊准确', E: '财务报表披露恰当' },
  B: { A: '风险评估证据存在', B: '风险评估覆盖完整', C: '权利义务关系清晰', D: '风险评估准确', E: '风险披露恰当' },
  C: { A: '控制实际存在', B: '控制覆盖完整', C: '控制权责清晰', D: '控制有效性准确', E: '控制评价披露恰当' },
  D: { A: '应收/收入确实存在', B: '所有应收/收入均已记录', C: '应收账款所有权归属清晰', D: '金额、计价、分摊准确', E: '财务报表披露恰当' },
  E: { A: '货币资金确实存在', B: '所有货币资金均已记录', C: '货币资金所有权归属清晰', D: '金额、计价、分摊准确', E: '财务报表披露恰当' },
  F: { A: '存货/采购确实存在', B: '所有存货/采购均已记录', C: '存货所有权归属清晰', D: '金额、计价、分摊准确', E: '财务报表披露恰当' },
  G: { A: '投资确实存在', B: '所有投资均已记录', C: '投资所有权归属清晰', D: '金额、计价、分摊准确', E: '财务报表披露恰当' },
  H: { A: '固定资产/在建工程确实存在', B: '所有固定资产均已记录', C: '资产所有权归属清晰', D: '金额、折旧、减值准确', E: '财务报表披露恰当' },
  I: { A: '无形资产/商誉确实存在', B: '所有无形资产均已记录', C: '资产所有权归属清晰', D: '金额、摊销、减值准确', E: '财务报表披露恰当' },
  J: { A: '薪酬/股份支付确实发生', B: '所有薪酬均已计提', C: '薪酬权责清晰', D: '金额、计提、分摊准确', E: '财务报表披露恰当' },
  K: { A: '费用确实发生', B: '所有费用均已记录', C: '费用归属清晰', D: '金额、归集、分摊准确', E: '财务报表披露恰当' },
  L: { A: '借款/债券确实存在', B: '所有筹资交易均已记录', C: '筹资权责清晰', D: '金额、利息、摊余成本准确', E: '财务报表披露恰当' },
  M: { A: '权益项目确实存在', B: '所有权益变动均已记录', C: '权益所有权清晰', D: '金额、变动准确', E: '财务报表披露恰当' },
  N: { A: '税费确实存在', B: '所有税费均已计提', C: '税费权责清晰', D: '金额、计算、分摊准确', E: '财务报表披露恰当' },
  S: { A: '专项事项确实存在', B: '所有专项事项均已记录', C: '专项权责清晰', D: '金额、计量准确', E: '财务报表披露恰当' },
}

const assertionCards = computed(() => {
  const cyclePrefix = (props.wpCode || '').charAt(0).toUpperCase()
  const tips = assertionTipsByCycle[cyclePrefix] || assertionTipsByCycle.A
  const codes = [
    { code: 'A', name: '存在', tip: tips.A },
    { code: 'B', name: '完整性', tip: tips.B },
    { code: 'C', name: '权利义务', tip: tips.C },
    { code: 'D', name: '准确性', tip: tips.D },
    { code: 'E', name: '列报', tip: tips.E },
  ]
  // 按 procedure_status 中 assertions 字段统计每项程序数
  const counts: Record<string, number> = { A: 0, B: 0, C: 0, D: 0, E: 0 }
  for (const r of procedureStatus.rows.value) {
    if (r.status === 'not_applicable') continue
    for (const a of r.assertions || []) {
      if (counts[a] !== undefined) counts[a]++
    }
  }
  return codes.map((c) => ({ ...c, count: counts[c.code] || 0 }))
})

// 2.4b 风险状态图标
function stateIcon(state: string): string {
  switch (state) {
    case 'completed':
      return '✅'
    case 'in_progress':
      return '⏳'
    case 'pending':
      return '❌'
    default:
      return '—'
  }
}

// 2.4c 程序进度流程图（5 段节点 + 颜色联动）
const progressSegments = computed(() => {
  const total = procedureStatus.summary.value.total || 1
  const filled = procedureStatus.summary.value.filled
  const reviewed = procedureStatus.summary.value.reviewed
  const approved = procedureStatus.summary.value.approved

  const allDone = approved >= total
  const partial = reviewed > 0 || filled > 0
  const colorByStage = (done: boolean, partial: boolean) => {
    if (done) return '#67c23a'
    if (partial) return '#e6a23c'
    return '#909399'
  }

  return [
    { key: 'goal', icon: '🎯', label: '审计目标', color: '#67c23a' },
    { key: 'risk', icon: '⚠️', label: '风险识别', color: prerequisiteStatus.overall.value === 'ready' ? '#67c23a' : prerequisiteStatus.overall.value === 'partial' ? '#e6a23c' : '#909399' },
    { key: 'design', icon: '📋', label: '程序设计', color: total > 0 ? '#67c23a' : '#909399' },
    { key: 'exec', icon: '⚙️', label: '程序执行', color: colorByStage(reviewed >= total, partial) },
    { key: 'conclude', icon: '✅', label: '结论形成', color: colorByStage(allDone, approved > 0) },
  ]
})

// 2.4d 关键风险提示（LLM）
const aiLoading = ref(false)
const aiTipText = ref('')

async function generateAiTip() {
  aiLoading.value = true
  try {
    const data: any = await api.post(
      `/api/workpapers/${props.wpId}/ai/variance-analysis`,
      { wp_code: props.wpCode, scope: 'auto_detect' },
    )
    aiTipText.value = data?.text || data?.summary || '无明显异常'
  } catch (err: any) {
    aiTipText.value = '生成失败：' + (err?.message || '未知错误')
  } finally {
    aiLoading.value = false
  }
}

// 2.4d 底稿间关系图（动态：从后端 /relation-graph API 加载）
interface RelationNode {
  code: string
  name: string
  description?: string
  severity?: string
  exists?: boolean
}
const relationLoading = ref(false)
const upstreamNodes = ref<RelationNode[]>([])
const downstreamNodes = ref<RelationNode[]>([])

const hasRelations = computed(() => upstreamNodes.value.length > 0 || downstreamNodes.value.length > 0)

const graphHeight = computed(() => {
  const maxRows = Math.max(upstreamNodes.value.length, downstreamNodes.value.length, 1)
  return Math.max(120, 30 + maxRows * 35)
})

const graphNodes = computed(() => {
  const nodes: any[] = []
  // 上游（左侧）
  upstreamNodes.value.forEach((n, i) => {
    nodes.push({
      id: `up-${n.code}`,
      label: n.code,
      x: 20, y: 15 + i * 35,
      color: n.exists ? '#909399' : '#bbb',
    })
  })
  // 当前底稿（中心）
  const centerY = (graphHeight.value - 22) / 2
  nodes.push({
    id: 'current',
    label: props.wpCode,
    x: 230, y: centerY,
    w: 140, color: '#4b2d77',
  })
  // 下游（右侧）
  downstreamNodes.value.forEach((n, i) => {
    nodes.push({
      id: `down-${n.code}`,
      label: n.code,
      x: 430, y: 15 + i * 35,
      color: n.exists ? '#5e35b1' : '#bbb',
    })
  })
  return nodes
})

const graphEdges = computed(() => {
  const edges: any[] = []
  const centerY = (graphHeight.value - 22) / 2 + 11
  // 上游 → 当前
  upstreamNodes.value.forEach((_, i) => {
    edges.push({
      x1: 90, y1: 15 + i * 35 + 11,
      x2: 230, y2: centerY,
      color: 'gray',
    })
  })
  // 当前 → 下游
  downstreamNodes.value.forEach((_, i) => {
    edges.push({
      x1: 370, y1: centerY,
      x2: 430, y2: 15 + i * 35 + 11,
      color: 'gray',
    })
  })
  return edges
})

async function loadRelationGraph() {
  if (!props.wpId) return
  relationLoading.value = true
  try {
    const { default: http } = await import('@/utils/http')
    const { data } = await http.get(`/api/projects/${props.projectId}/working-papers/${props.wpId}/relation-graph`)
    upstreamNodes.value = data?.upstream || []
    downstreamNodes.value = data?.downstream || []
  } catch (e) {
    console.warn('[WorkpaperAuditNav] 加载关系图失败:', e)
    upstreamNodes.value = []
    downstreamNodes.value = []
  } finally {
    relationLoading.value = false
  }
}

onMounted(() => {
  // 子 composable 已自动加载，此处仅占位
  loadRelationGraph()
})
</script>

<style scoped>
.gt-audit-nav {
  border: 1px solid var(--gt-color-border-light, #e4e7ed);
  border-radius: 6px;
  background: var(--gt-color-bg-white, #fff);
  margin-bottom: 8px;
  overflow: hidden;
}
.gt-audit-nav.is-collapsed {
  background: var(--gt-color-bg-page, #f5f5f5);
}
.gt-audit-nav-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px;
  background: linear-gradient(90deg, var(--gt-color-primary, #4b2d77), #6c4ca8);
  color: white;
  cursor: pointer;
  user-select: none;
}
.gt-audit-nav-header :deep(.el-button) {
  color: white;
}
.gt-audit-nav-title {
  font-size: 13px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 6px;
}
.gt-audit-nav-icon {
  font-size: 16px;
}
.gt-audit-nav-body {
  padding: 8px 10px 12px;
}
.gt-audit-nav-section {
  margin-bottom: 12px;
}
.gt-audit-nav-section:last-child {
  margin-bottom: 0;
}
.gt-audit-nav-section-title {
  margin: 0 0 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--gt-color-text-primary, #333);
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.gt-audit-nav-loading {
  font-size: 12px;
  color: var(--gt-color-text-secondary, #909399);
}
.gt-audit-nav-assertions {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(70px, 1fr));
  gap: 4px;
}
.gt-assertion-card {
  border: 1px solid var(--gt-color-border-light, #e4e7ed);
  border-radius: 4px;
  padding: 4px 6px;
  background: var(--gt-color-bg-white, #fff);
  text-align: center;
}
.gt-assertion-card__head {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.gt-assertion-card__code {
  font-size: 11px;
  font-weight: bold;
  color: var(--gt-color-primary, #4b2d77);
}
.gt-assertion-card__name {
  font-size: 11px;
  color: var(--gt-color-text-secondary, #606266);
}
.gt-risk-summary {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.gt-risk-summary-row {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  padding: 3px 6px;
  border-radius: 4px;
  background: var(--gt-color-bg-page, #f5f5f5);
}
.gt-risk-summary-row.is-completed {
  background: rgba(103, 194, 58, 0.08);
}
.gt-risk-summary-row.is-in_progress {
  background: rgba(230, 162, 60, 0.08);
}
.gt-risk-summary-row.is-pending {
  background: rgba(245, 108, 108, 0.08);
}
.gt-risk-summary-icon {
  font-size: 14px;
}
.gt-risk-summary-code {
  font-weight: 600;
  font-size: 11px;
  color: var(--gt-color-text-primary, #333);
  min-width: 42px;
}
.gt-risk-summary-name {
  flex: 1;
  color: var(--gt-color-text-regular, #606266);
}
.gt-risk-summary-level {
  font-size: 11px;
  color: var(--gt-color-danger, #f56c6c);
  font-weight: 600;
}
.gt-audit-nav-progress-svg,
.gt-audit-nav-graph-svg {
  width: 100%;
  height: auto;
  max-height: 240px;
  display: block;
  background: var(--gt-color-bg-white, #fff);
  border: 1px solid var(--gt-color-border-light, #e4e7ed);
  border-radius: 4px;
  padding: 4px 0;
}
.gt-audit-nav-empty {
  padding: 16px; text-align: center; color: var(--gt-color-text-tertiary, #909399);
  font-size: 12px; background: var(--gt-color-bg, #fafafa); border-radius: 4px;
}
.gt-audit-nav-graph-legend {
  display: flex; gap: 16px; flex-wrap: wrap; margin-top: 8px;
  font-size: 11px; color: var(--gt-color-text-secondary, #909399);
}
.gt-graph-dot {
  display: inline-block; width: 10px; height: 10px; border-radius: 2px; vertical-align: middle; margin-right: 4px;
}
.gt-audit-nav-progress-legend {
  display: flex;
  gap: 10px;
  font-size: 11px;
  color: var(--gt-color-text-secondary, #909399);
  margin-top: 4px;
  justify-content: center;
}
.gt-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 3px;
  vertical-align: middle;
}
.gt-ai-tip {
  font-size: 12px;
  color: var(--gt-color-text-regular, #606266);
  background: var(--gt-color-bg-page, #f5f5f5);
  padding: 6px 8px;
  border-left: 3px solid var(--gt-color-primary, #4b2d77);
  border-radius: 3px;
  white-space: pre-wrap;
}
.gt-ai-tip-empty {
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
  font-style: italic;
}
</style>
