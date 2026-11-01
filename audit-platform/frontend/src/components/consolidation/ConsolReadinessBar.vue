<template>
  <div v-if="domains.length" class="gt-readiness-bar" data-testid="consol-readiness-bar">
    <span
      v-for="d in domains" :key="d.domain"
      class="gt-readiness-chip"
      :class="`gt-readiness-chip--${d.status}`"
      :title="d.blockers.length ? d.blockers.join('\n') : d.label"
    >
      <span class="gt-readiness-dot" />
      {{ d.label }}
    </span>
    <span v-if="overallBlockers.length" class="gt-readiness-summary gt-readiness-summary--blocked">
      {{ overallBlockers.length }} 项待处理
    </span>
    <span v-else class="gt-readiness-summary gt-readiness-summary--ready">
      全部就绪
    </span>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, computed } from 'vue'
import { api } from '@/services/apiProxy'
import { consolidation as P } from '@/services/apiPaths'

interface DomainItem {
  domain: string
  label: string
  status: string
  facts: Record<string, unknown>
  blockers: string[]
}

const props = defineProps<{
  projectId: string
  year: number | null
}>()

const domains = ref<DomainItem[]>([])
const overallBlockers = computed(() => domains.value.flatMap(d => d.status === 'not_ready' ? d.blockers : []))

async function load() {
  if (!props.projectId || !props.year) { domains.value = []; return }
  try {
    const data = await api.get(P.readiness(props.projectId, props.year), { _silent: true } as any) as any
    domains.value = Array.isArray(data?.domains) ? data.domains : []
  } catch {
    domains.value = []
  }
}

onMounted(load)
watch([() => props.projectId, () => props.year], load)

defineExpose({ load })
</script>

<style scoped>
.gt-readiness-bar {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  padding: 4px 8px; font-size: var(--gt-font-size-xs);
}
.gt-readiness-chip {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 2px 8px; border-radius: 10px;
  background: var(--gt-color-bg-elevated, #faf9fd);
  color: var(--gt-color-text-secondary);
  cursor: help;
}
.gt-readiness-dot {
  width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
}
.gt-readiness-chip--ready .gt-readiness-dot { background: var(--gt-color-success, #67c23a); }
.gt-readiness-chip--not_ready .gt-readiness-dot { background: var(--gt-color-danger, #f56c6c); }
.gt-readiness-chip--warning .gt-readiness-dot { background: var(--gt-color-warning, #e6a23c); }
.gt-readiness-chip--unknown .gt-readiness-dot { background: var(--gt-color-text-placeholder, #c0c4cc); }
.gt-readiness-chip--not_applicable .gt-readiness-dot { background: var(--gt-color-text-placeholder, #c0c4cc); }
.gt-readiness-summary { font-weight: 600; margin-left: auto; }
.gt-readiness-summary--blocked { color: var(--gt-color-danger); }
.gt-readiness-summary--ready { color: var(--gt-color-success); }
</style>
