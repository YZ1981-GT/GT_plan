<!--
  WpDecisionTracePanel — render-config decision_trace 只读消费者（调试侧栏）
-->
<template>
  <div class="gt-wp-decision-trace">
    <div v-if="!rows.length" class="gt-wp-side-placeholder">暂无裁决轨迹</div>
    <ul v-else class="gt-wp-decision-trace__list">
      <li
        v-for="(item, idx) in rows"
        :key="`${item.sheet_key}-${idx}`"
        class="gt-wp-decision-trace__item"
      >
        <div class="gt-wp-decision-trace__sheet">{{ item.sheet_key }}</div>
        <div class="gt-wp-decision-trace__meta">
          <span>{{ item.chosen_component_type }}</span>
          <span>· {{ item.winning_source }}</span>
          <span v-if="item.override_hit">· override</span>
          <span v-if="item.redirect_applied">· redirect</span>
        </div>
        <div
          v-if="item.fallback_reason"
          class="gt-wp-decision-trace__fallback"
        >
          {{ item.fallback_reason }}
        </div>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { RenderDecisionWire } from '@/types/renderConfig'

const props = defineProps<{
  trace: RenderDecisionWire[] | null | undefined
}>()

const rows = computed(() => props.trace ?? [])
</script>

<style scoped>
.gt-wp-decision-trace {
  min-height: 80px;
}
.gt-wp-decision-trace__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--gt-space-2);
}
.gt-wp-decision-trace__item {
  padding: var(--gt-space-2) var(--gt-space-3);
  border-bottom: 1px solid var(--gt-color-border-light);
}
.gt-wp-decision-trace__sheet {
  font-family: monospace;
  font-size: var(--gt-font-size-xs);
  font-weight: 600;
  color: var(--gt-color-text);
}
.gt-wp-decision-trace__meta {
  margin-top: 2px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary);
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.gt-wp-decision-trace__fallback {
  margin-top: 4px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
}
.gt-wp-side-placeholder {
  padding: var(--gt-space-8);
  text-align: center;
  color: var(--gt-color-text-tertiary);
  font-size: var(--gt-font-size-sm);
}
</style>
