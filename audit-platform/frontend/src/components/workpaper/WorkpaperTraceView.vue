<!--
  WorkpaperTraceView — 底稿溯源视图组件

  展示某底稿的上游来源和下游影响，从注册表读取 upstream/downstream 关系。
  点击可跳转到对应底稿。

  Foundation Kit Requirements: 5.2
-->
<template>
  <div class="wp-trace-view">
    <div class="wp-trace-view__title">溯源关系</div>

    <!-- 上游 -->
    <div v-if="upstreamEntries.length" class="wp-trace-view__section">
      <div class="wp-trace-view__label">上游来源</div>
      <div class="wp-trace-view__items">
        <el-tag
          v-for="item in upstreamEntries"
          :key="item.code"
          class="wp-trace-view__tag"
          effect="plain"
          @click="onNavigate(item.code)"
        >
          <span class="wp-trace-view__arrow">←</span>
          {{ item.code }} {{ item.name }}
        </el-tag>
      </div>
    </div>

    <!-- 当前 -->
    <div class="wp-trace-view__current">
      <el-tag type="primary" effect="dark">
        {{ wpCode }} {{ currentEntry?.name || '' }}
      </el-tag>
    </div>

    <!-- 下游 -->
    <div v-if="downstreamEntries.length" class="wp-trace-view__section">
      <div class="wp-trace-view__label">下游影响</div>
      <div class="wp-trace-view__items">
        <el-tag
          v-for="item in downstreamEntries"
          :key="item.code"
          class="wp-trace-view__tag wp-trace-view__tag--downstream"
          effect="plain"
          @click="onNavigate(item.code)"
        >
          {{ item.code }} {{ item.name }}
          <span class="wp-trace-view__arrow">→</span>
        </el-tag>
      </div>
    </div>

    <div v-if="!upstreamEntries.length && !downstreamEntries.length" class="wp-trace-view__empty">
      该底稿无上下游溯源关系
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useWorkpaperRegistry, type RegistryEntry } from '@/composables/useWorkpaperRegistry'
import { useWorkpaperNavigation } from '@/composables/useWorkpaperNavigation'

const props = defineProps<{
  wpCode: string
  projectId: string
  year?: number
}>()

const registry = useWorkpaperRegistry()
const { navigateToWorkpaper } = useWorkpaperNavigation()

onMounted(() => registry.load())

const currentEntry = computed<RegistryEntry | null>(() => registry.lookup(props.wpCode))

interface TraceItem {
  code: string
  name: string
}

const upstreamEntries = computed<TraceItem[]>(() => {
  const entry = currentEntry.value
  if (!entry?.upstream) return []
  return entry.upstream
    .map((code) => {
      const e = registry.lookup(code)
      return { code, name: e?.name || '' }
    })
    .filter((x) => x.name)
})

const downstreamEntries = computed<TraceItem[]>(() => {
  const entry = currentEntry.value
  if (!entry?.downstream) return []
  return entry.downstream
    .map((code) => {
      const e = registry.lookup(code)
      return { code, name: e?.name || '' }
    })
    .filter((x) => x.name)
})

function onNavigate(code: string) {
  void navigateToWorkpaper(code, props.projectId, props.year)
}
</script>

<style scoped>
.wp-trace-view {
  padding: 12px;
}

.wp-trace-view__title {
  font-weight: 600;
  font-size: 14px;
  color: var(--gt-color-primary, #4b2d77);
  margin-bottom: 12px;
}

.wp-trace-view__section {
  margin: 8px 0;
}

.wp-trace-view__label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

.wp-trace-view__items {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.wp-trace-view__tag {
  cursor: pointer;
}

.wp-trace-view__tag:hover {
  opacity: 0.8;
}

.wp-trace-view__arrow {
  margin: 0 2px;
  font-weight: 700;
}

.wp-trace-view__current {
  text-align: center;
  margin: 12px 0;
}

.wp-trace-view__empty {
  color: #c0c4cc;
  font-size: 13px;
  text-align: center;
  padding: 16px;
}
</style>
