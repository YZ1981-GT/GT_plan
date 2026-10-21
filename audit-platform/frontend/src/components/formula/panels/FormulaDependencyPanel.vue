<!-- 公式依赖关系面板（从 FormulaManagerDialog 提取；spec formula-settings-wiring-closure T11）。
     优化建议 #3：增加可视化依赖图（upstream → 目标 → downstream），纯 CSS/SVG 实现无额外依赖。 -->
<template>
  <div v-if="visible && data" class="gt-fm-dep-panel" style="margin-top: 8px; padding: 10px; border: 1px solid var(--gt-color-border, #ebeef5); border-radius: 6px; background: var(--gt-bg-page, #fafafa);">
    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
      <span style="font-size: 13px; font-weight: 600;">📊 依赖关系</span>
      <span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary);">{{ data.formula || '（无公式）' }}</span>
      <span style="flex: 1;" />
      <el-radio-group v-model="viewMode" size="small">
        <el-radio-button value="graph">图形</el-radio-button>
        <el-radio-button value="list">列表</el-radio-button>
      </el-radio-group>
      <el-button size="small" link @click="visible = false">关闭</el-button>
    </div>
    <div v-if="data.unavailable_domains?.length" style="font-size: 11px; color: var(--gt-color-warning); margin-bottom: 6px;">
      ⚠ 以下域未列入：{{ data.unavailable_domains.map((d: any) => d.label).join('、') }}
    </div>

    <!-- 图形模式：upstream → 目标 → downstream -->
    <div v-if="viewMode === 'graph'" class="gt-dep-graph">
      <!-- 上游列 -->
      <div class="gt-dep-col gt-dep-col--upstream">
        <div class="gt-dep-col-title">⬆ 引用了（{{ upstreamNodes.length }}）</div>
        <div v-if="!upstreamNodes.length" class="gt-dep-empty">无上游</div>
        <div v-for="(node, i) in upstreamNodes" :key="node.addr_id" class="gt-dep-node"
          :class="`gt-dep-node--${node.type}`" :data-index="i">
          <span class="gt-dep-node-type">{{ typeLabel(node.type) }}</span>
          <span class="gt-dep-node-label" :title="node.label">{{ node.label }}</span>
        </div>
      </div>

      <!-- 连线区域（SVG） -->
      <svg ref="svgRef" class="gt-dep-svg gt-dep-svg--left" :viewBox="`0 0 60 ${svgHeight}`" preserveAspectRatio="none">
        <path v-for="(p, i) in leftPaths" :key="i" :d="p" class="gt-dep-line gt-dep-line--upstream" />
      </svg>

      <!-- 中心目标节点 -->
      <div class="gt-dep-center" ref="centerRef">
        <div class="gt-dep-target">
          <div class="gt-dep-target-label">{{ data.addr_id }}</div>
          <div v-if="data.formula" class="gt-dep-target-formula">{{ data.formula }}</div>
        </div>
      </div>

      <!-- 连线区域（SVG） -->
      <svg class="gt-dep-svg gt-dep-svg--right" :viewBox="`0 0 60 ${svgHeight}`" preserveAspectRatio="none">
        <path v-for="(p, i) in rightPaths" :key="i" :d="p" class="gt-dep-line gt-dep-line--downstream" />
      </svg>

      <!-- 下游列 -->
      <div class="gt-dep-col gt-dep-col--downstream">
        <div class="gt-dep-col-title">⬇ 被引用（{{ downstreamNodes.length }}{{ data.downstream_total > 200 ? `，共 ${data.downstream_total}` : '' }}）</div>
        <div v-if="!downstreamNodes.length" class="gt-dep-empty">无下游</div>
        <div v-for="(node, i) in downstreamNodes" :key="node.addr_id" class="gt-dep-node"
          :class="`gt-dep-node--${node.type}`" :data-index="i">
          <span class="gt-dep-node-type">{{ typeLabel(node.type) }}</span>
          <span class="gt-dep-node-label" :title="node.label">{{ node.label }}</span>
        </div>
      </div>
    </div>

    <!-- 列表模式（保留原有展示） -->
    <div v-else style="display: flex; gap: 16px;">
      <div style="flex: 1;">
        <div style="font-size: 12px; font-weight: 600; margin-bottom: 4px; color: var(--gt-color-text-secondary);">⬆ 引用了（{{ data.upstream?.length ?? 0 }}）</div>
        <div v-for="dep in data.upstream" :key="dep.addr_id" style="font-size: 11px; padding: 3px 0; border-bottom: 1px solid #f0f0f0;">
          <el-tag size="small" effect="plain" :type="typeTag(dep.type)">{{ typeLabel(dep.type) }}</el-tag>
          <span style="margin-left: 4px;">{{ dep.label }}</span>
        </div>
        <div v-if="!data.upstream?.length" style="font-size: 11px; color: var(--gt-color-text-placeholder);">无上游依赖</div>
      </div>
      <div style="flex: 1;">
        <div style="font-size: 12px; font-weight: 600; margin-bottom: 4px; color: var(--gt-color-text-secondary);">⬇ 被引用（{{ data.downstream?.length ?? 0 }}{{ data.downstream_total > 200 ? `，共 ${data.downstream_total}` : '' }}）</div>
        <div v-for="dep in data.downstream" :key="dep.addr_id" style="font-size: 11px; padding: 3px 0; border-bottom: 1px solid #f0f0f0;">
          <el-tag size="small" effect="plain" :type="typeTag(dep.type)">{{ typeLabel(dep.type) }}</el-tag>
          <span style="margin-left: 4px;">{{ dep.label }}</span>
        </div>
        <div v-if="!data.downstream?.length" style="font-size: 11px; color: var(--gt-color-text-placeholder);">无下游引用</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import api from '@/services/apiProxy'

const props = defineProps<{ projectId?: string }>()

const visible = ref(false)
const data = ref<any>(null)
const loading = ref(false)
const viewMode = ref<'graph' | 'list'>('graph')
const svgRef = ref<SVGSVGElement | null>(null)
const centerRef = ref<HTMLElement | null>(null)

const NODE_HEIGHT = 32
const NODE_GAP = 6
const TITLE_HEIGHT = 24

const upstreamNodes = computed(() => (data.value?.upstream || []) as any[])
const downstreamNodes = computed(() => (data.value?.downstream || []) as any[])

const svgHeight = computed(() => {
  const maxNodes = Math.max(upstreamNodes.value.length, downstreamNodes.value.length, 1)
  return TITLE_HEIGHT + maxNodes * (NODE_HEIGHT + NODE_GAP) + 20
})

/** 计算从上游节点到中心的贝塞尔曲线路径 */
const leftPaths = computed(() => {
  const count = upstreamNodes.value.length
  if (!count) return []
  const centerY = svgHeight.value / 2
  return upstreamNodes.value.map((_, i) => {
    const y = TITLE_HEIGHT + i * (NODE_HEIGHT + NODE_GAP) + NODE_HEIGHT / 2
    return `M 0 ${y} C 30 ${y}, 30 ${centerY}, 60 ${centerY}`
  })
})

/** 计算从中心到下游节点的贝塞尔曲线路径 */
const rightPaths = computed(() => {
  const count = downstreamNodes.value.length
  if (!count) return []
  const centerY = svgHeight.value / 2
  return downstreamNodes.value.map((_, i) => {
    const y = TITLE_HEIGHT + i * (NODE_HEIGHT + NODE_GAP) + NODE_HEIGHT / 2
    return `M 0 ${centerY} C 30 ${centerY}, 30 ${y}, 60 ${y}`
  })
})

async function load(addrId: string) {
  if (!props.projectId || !addrId) return
  loading.value = true
  visible.value = true
  try {
    data.value = await api.get(`/api/projects/${props.projectId}/formula-settings/dependencies`, { params: { addr_id: addrId } }) as any
  } catch { data.value = null }
  finally { loading.value = false }
}

function typeTag(t: string) {
  const m: Record<string, string> = { trial_balance: 'success', report: 'primary', workpaper: 'warning', note: 'info' }
  return m[t] || 'info'
}
function typeLabel(t: string) {
  const m: Record<string, string> = { trial_balance: 'TB', report: '报表', workpaper: '底稿', note: '附注', prior: '上期', cross_check: '表间审核', adjustment: '调整' }
  return m[t] || t
}

defineExpose({ load, visible })
</script>

<style scoped>
/* 依赖图布局：五列（upstream | 连线 | 目标 | 连线 | downstream） */
.gt-dep-graph {
  display: flex;
  align-items: flex-start;
  gap: 0;
  min-height: 120px;
  overflow-x: auto;
}
.gt-dep-col {
  flex: 1;
  min-width: 160px;
  max-width: 260px;
}
.gt-dep-col-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--gt-color-text-secondary);
  margin-bottom: 6px;
  height: 18px;
}
.gt-dep-empty {
  font-size: 11px;
  color: var(--gt-color-text-placeholder);
  padding: 8px 0;
}
.gt-dep-center {
  flex: 0 0 200px;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 80px;
}
.gt-dep-target {
  background: var(--gt-color-primary-light, #ecf5ff);
  border: 2px solid var(--gt-color-primary, #409eff);
  border-radius: 8px;
  padding: 10px 14px;
  text-align: center;
  max-width: 200px;
}
.gt-dep-target-label {
  font-size: 12px;
  font-weight: 700;
  color: var(--gt-color-primary-dark, #1d3557);
  word-break: break-all;
}
.gt-dep-target-formula {
  font-size: 10px;
  color: var(--gt-color-text-tertiary);
  margin-top: 4px;
  max-height: 48px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: monospace;
}
.gt-dep-node {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  margin-bottom: 4px;
  border-radius: 4px;
  font-size: 11px;
  border: 1px solid #e4e7ed;
  background: #fff;
  height: 28px;
  box-sizing: border-box;
}
.gt-dep-node--trial_balance { border-left: 3px solid var(--gt-color-success, #67c23a); }
.gt-dep-node--report { border-left: 3px solid var(--gt-color-primary, #409eff); }
.gt-dep-node--workpaper { border-left: 3px solid var(--gt-color-warning, #e6a23c); }
.gt-dep-node--note { border-left: 3px solid var(--gt-color-info, #909399); }
.gt-dep-node--prior { border-left: 3px solid #b37feb; }
.gt-dep-node--adjustment { border-left: 3px solid #ff7875; }
.gt-dep-node--cross_check { border-left: 3px solid #36cfc9; }
.gt-dep-node-type {
  font-size: 10px;
  font-weight: 600;
  color: var(--gt-color-text-tertiary);
  white-space: nowrap;
  min-width: 28px;
}
.gt-dep-node-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.gt-dep-svg {
  flex: 0 0 60px;
  width: 60px;
}
.gt-dep-line {
  fill: none;
  stroke-width: 1.5;
}
.gt-dep-line--upstream {
  stroke: var(--gt-color-success, #67c23a);
  opacity: 0.5;
}
.gt-dep-line--downstream {
  stroke: var(--gt-color-primary, #409eff);
  opacity: 0.5;
}
</style>
