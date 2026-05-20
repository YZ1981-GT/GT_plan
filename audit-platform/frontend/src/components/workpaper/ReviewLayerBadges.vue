<template>
  <div class="gt-review-badges">
    <el-tooltip
      v-for="layer in layers"
      :key="layer.code"
      :content="`${layer.label}: ${stateLabel(layer.state)}`"
      placement="bottom"
    >
      <span class="gt-review-badge" :class="`is-${layer.state}`" @click="onClick(layer)">
        <span class="gt-review-badge-code">{{ layer.code }}</span>
        <span class="gt-review-badge-icon">{{ stateIcon(layer.state) }}</span>
      </span>
    </el-tooltip>
  </div>
</template>

<script setup lang="ts">
/**
 * ReviewLayerBadges — 5 层复核体系状态 badge（Sprint 2 Task 2.18）
 *
 * L1 现场负责人 / L2 项目经理 / L3 签字合伙人 / L4 质量复核合伙人 /
 * L5 质控部 / 专委会 / IT 审计 / 税务专家
 */
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'

interface Props {
  projectId: string
  wpId: string
  wpCode?: string
}
const props = defineProps<Props>()
const router = useRouter()

type ReviewState = 'pending' | 'in_progress' | 'completed' | 'issues'

interface LayerInfo {
  code: string
  label: string
  state: ReviewState
  template_wp?: string
}

const layers = ref<LayerInfo[]>([
  { code: 'L1', label: '现场负责人', state: 'pending', template_wp: 'A21-1' },
  { code: 'L2', label: '项目经理', state: 'pending', template_wp: 'A22-1' },
  { code: 'L3', label: '签字合伙人', state: 'pending', template_wp: 'A23-1' },
  { code: 'L4', label: '质量复核合伙人', state: 'pending', template_wp: 'A24-1' },
  { code: 'L5', label: '质控部', state: 'pending', template_wp: 'A25-1' },
  { code: '专', label: '专委会', state: 'pending', template_wp: 'A26-1' },
  { code: 'IT', label: 'IT 审计', state: 'pending', template_wp: 'A27-1' },
  { code: '税', label: '税务专家', state: 'pending', template_wp: 'A28' },
])

function stateIcon(s: ReviewState): string {
  return { completed: '✅', in_progress: '⏳', issues: '❌', pending: '·' }[s]
}
function stateLabel(s: ReviewState): string {
  return { completed: '已完成', in_progress: '进行中', issues: '有疑问', pending: '未开始' }[s]
}

async function loadStatus() {
  try {
    const data: any = await api.get('/api/review-records', {
      params: {
        project_id: props.projectId,
        target_wp: props.wpCode || '',
      },
    })
    const items = Array.isArray(data) ? data : data?.items || []
    const stateMap: Record<string, ReviewState> = {}
    for (const r of items) {
      const layer = r.review_layer || ''
      if (!stateMap[layer]) stateMap[layer] = 'pending'
      const isOpen = r.status === 'open'
      const isResolved = r.status === 'resolved' || r.status === 'closed'
      if (isOpen) stateMap[layer] = 'issues'
      else if (isResolved && stateMap[layer] !== 'issues') stateMap[layer] = 'completed'
    }
    for (const layer of layers.value) {
      const layerKey = layer.code.toLowerCase().replace('专', 'committee').replace('it', 'it').replace('税', 'tax')
      const state = stateMap[layerKey] || stateMap[layer.code] || 'pending'
      layer.state = state
    }
  } catch {
    /* 静默 */
  }
}

function onClick(layer: LayerInfo) {
  if (!layer.template_wp) return
  // E1 Sprint 2 Task 2.20: 跳转到对应复核模板底稿
  router.push({
    name: 'WorkpaperList',
    params: { projectId: props.projectId },
    query: { highlight: layer.template_wp, source_wp: props.wpCode || '' },
  })
}

onMounted(() => {
  loadStatus()
  eventBus.on('review-record:resolved', loadStatus)
})

watch(() => [props.projectId, props.wpCode], loadStatus)
</script>

<style scoped>
.gt-review-badges {
  display: flex;
  gap: 3px;
  align-items: center;
  margin-right: 6px;
  padding: 0 4px;
  border-right: 1px solid var(--gt-color-border-lighter, #ebeef5);
}
.gt-review-badge {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 2px 5px;
  border-radius: 3px;
  font-size: 11px;
  background: var(--gt-color-bg-page, #f5f5f5);
  cursor: pointer;
  transition: background 0.15s;
}
.gt-review-badge:hover {
  background: var(--gt-color-bg-elevated, #eee);
}
.gt-review-badge.is-completed {
  background: rgba(103, 194, 58, 0.15);
  color: var(--gt-color-success, #67c23a);
}
.gt-review-badge.is-in_progress {
  background: rgba(230, 162, 60, 0.15);
  color: var(--gt-color-warning, #e6a23c);
}
.gt-review-badge.is-issues {
  background: rgba(245, 108, 108, 0.15);
  color: var(--gt-color-danger, #f56c6c);
}
.gt-review-badge-code {
  font-weight: 600;
}
.gt-review-badge-icon {
  font-size: 10px;
}
</style>
