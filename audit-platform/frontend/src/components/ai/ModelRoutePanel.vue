<template>
  <section class="route-panel" aria-label="调用路由">
    <header class="route-head">
      <span class="route-title">调用路由</span>
      <span class="route-sub">本机优先，本机不可用时自动使用已启用的服务器模型</span>
      <span v-if="checkedAt" class="route-time">检测于 {{ fmtDateTime(checkedAt) }}</span>
    </header>
    <el-skeleton v-if="loading && !routes.length" :rows="3" animated />
    <ul v-else class="route-list">
      <li v-for="route in routes" :key="route.kind" class="route-row" :data-kind="route.kind">
        <div class="route-kind">
          <span>{{ route.label }}</span>
          <el-tag v-if="route.policy === 'single'" size="small" type="info" effect="plain">单模型，不跨模型兜底</el-tag>
        </div>
        <div class="route-chain">
          <span v-if="route.error" class="route-error">{{ route.error }}</span>
          <template v-else-if="route.candidates.length">
            <template v-for="(slot, index) in chainOf(route)" :key="slot.key">
              <span v-if="index > 0" class="route-arrow" aria-hidden="true">→</span>
              <span v-if="slot.candidate" class="route-candidate" :class="slot.candidate.status" :title="slot.candidate.reason">
                <span class="dot" aria-hidden="true" />
                <span class="where">{{ DEPLOYMENT_LABEL[slot.candidate.deployment] }}</span>
                <span class="name">{{ candidateName(slot.candidate) }}</span>
                <span class="reason">{{ statusText(slot.candidate) }}</span>
              </span>
              <span v-else class="route-candidate empty">
                <span class="where">{{ DEPLOYMENT_LABEL[slot.deployment] }}</span>
                <span class="reason">未启用</span>
              </span>
            </template>
          </template>
          <span v-else class="muted">{{ emptyText(route) }}</span>
        </div>
        <div class="route-effective" :class="effectiveClass(route)">当前生效：{{ effectiveText(route) }}</div>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import type { AIRoute } from '@/services/aiModelApi'
import { fmtDateTime } from '@/utils/formatters'
import {
  DEPLOYMENT_LABELS as DEPLOYMENT_LABEL,
  candidateName, chainOf, effectiveClass, effectiveText, emptyText, statusText,
} from './modelRouteView'

withDefaults(defineProps<{
  routes: AIRoute[]
  loading?: boolean
  checkedAt?: string | null
}>(), { loading: false, checkedAt: null })
</script>

<style scoped>
.route-panel {
  margin-bottom: var(--gt-space-4); padding: var(--gt-space-3) var(--gt-space-4);
  border: 1px solid var(--gt-color-border-light); border-radius: var(--gt-radius-md); background: var(--gt-color-bg);
}
.route-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--gt-space-2); margin-bottom: var(--gt-space-2); }
.route-title { font-weight: 600; color: var(--gt-color-text); }
.route-sub, .route-time { color: var(--gt-color-text-secondary); font-size: var(--gt-font-size-xs); }
.route-time { margin-left: auto; }
.route-list { list-style: none; margin: 0; padding: 0; }
.route-row {
  display: grid; grid-template-columns: 170px minmax(0, 1fr) minmax(220px, max-content); align-items: center; gap: var(--gt-space-3);
  padding: 8px 0; border-top: 1px dashed var(--gt-color-border-light); font-size: var(--gt-font-size-sm);
}
.route-row:first-child { border-top: none; }
.route-kind { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; font-weight: 500; color: var(--gt-color-text); }
.route-chain { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; min-width: 0; }
.route-arrow { color: var(--gt-color-text-secondary); }
.route-candidate {
  display: inline-flex; align-items: center; gap: 6px; max-width: 100%; padding: 2px 10px;
  border: 1px solid var(--gt-color-border-light); border-radius: 12px; background: var(--gt-color-bg-white, #fff);
}
.route-candidate .where { color: var(--gt-color-text-secondary); font-size: var(--gt-font-size-xs); }
.route-candidate .name { font-weight: 500; color: var(--gt-color-text); white-space: nowrap; }
.route-candidate .reason {
  overflow: hidden; max-width: 360px; color: var(--gt-color-text-secondary);
  font-size: var(--gt-font-size-xs); text-overflow: ellipsis; white-space: nowrap;
}
.route-candidate .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--gt-color-text-secondary); flex: none; }
.route-candidate.available { border-color: var(--gt-color-success); }
.route-candidate.available .dot { background: var(--gt-color-success); }
.route-candidate.unavailable { border-color: var(--gt-color-coral); }
.route-candidate.unavailable .dot { background: var(--gt-color-coral); }
.route-candidate.empty { border-style: dashed; }
.route-effective { font-weight: 500; }
.route-effective.ok { color: var(--gt-color-success); }
.route-effective.err, .route-error { color: var(--gt-color-coral); }
.route-effective.unknown, .muted { color: var(--gt-color-text-secondary); }
</style>
