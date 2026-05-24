<!--
  SnapshotStalenessChip — snapshot 过期警告 chip

  根据 source + saved_at 选择 chip 变体：
  - source=univer_snapshot && saved_at > 30 天 → 橙色 "⚠ 数据可能过时（XX 天前保存）"
  - source=univer_snapshot && saved_at ≤ 30 天 → 不显示
  - source=xlsx_recomputed → 蓝色 "⚙ 重算结果"
  - source=xlsx_cache → 灰色 "📋 模板数据"
  - saved_at 缺失 → 灰色 "数据时间未知"

  Validates: Requirements 10.1, 10.2, 10.4, 10.5
  Feature: advanced-query-enhancements-p1p2, Property 21: Staleness chip variant selection
-->
<template>
  <div v-if="chipVariant" class="gt-staleness-chip-wrap">
    <el-tag
      :type="chipVariant.type"
      :effect="chipVariant.effect"
      size="small"
      round
      class="gt-staleness-chip"
      @click="onChipClick"
      style="cursor: pointer"
    >
      {{ chipVariant.label }}
    </el-tag>

    <!-- 点击弹窗：精确时间 + 最后编辑人 + 立即重算 -->
    <el-dialog
      v-model="detailVisible"
      title="数据快照详情"
      width="400px"
      append-to-body
      destroy-on-close
    >
      <div class="gt-staleness-detail">
        <p v-if="savedAt"><strong>保存时间：</strong>{{ formatDateTime(savedAt) }}</p>
        <p v-else><strong>保存时间：</strong>未知</p>
        <p v-if="lastEditor"><strong>最后编辑人：</strong>{{ lastEditor }}</p>
        <p v-if="daysAgo !== null"><strong>距今：</strong>{{ daysAgo }} 天</p>
      </div>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
        <el-button type="primary" @click="onRecompute">立即重算</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

export interface StalenessChipProps {
  source: string
  savedAt?: string | null
  lastEditor?: string | null
}

const props = defineProps<StalenessChipProps>()
const emit = defineEmits<{
  recompute: []
}>()

const detailVisible = ref(false)

const daysAgo = computed(() => {
  if (!props.savedAt) return null
  const saved = new Date(props.savedAt)
  if (isNaN(saved.getTime())) return null
  const now = new Date()
  return Math.floor((now.getTime() - saved.getTime()) / (1000 * 60 * 60 * 24))
})

export interface ChipVariant {
  type: 'warning' | 'info' | '' | 'primary'
  effect: 'light' | 'plain' | 'dark'
  label: string
}

const chipVariant = computed<ChipVariant | null>(() => {
  return getChipVariant(props.source, props.savedAt ?? null)
})

function onChipClick() {
  detailVisible.value = true
}

function onRecompute() {
  detailVisible.value = false
  emit('recompute')
}

function formatDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return iso
  }
}
</script>

<script lang="ts">
/**
 * 纯函数：根据 source + saved_at 计算 chip 变体。
 * 导出供测试使用。
 */
export function getChipVariant(
  source: string,
  savedAt: string | null
): { type: 'warning' | 'info' | '' | 'primary'; effect: 'light' | 'plain' | 'dark'; label: string } | null {
  if (source === 'xlsx_recomputed') {
    return { type: 'primary', effect: 'light', label: '⚙ 重算结果' }
  }
  if (source === 'xlsx_cache') {
    return { type: 'info', effect: 'plain', label: '📋 模板数据' }
  }
  // univer_snapshot or other sources
  if (!savedAt) {
    return { type: 'info', effect: 'plain', label: '数据时间未知' }
  }
  const saved = new Date(savedAt)
  if (isNaN(saved.getTime())) {
    return { type: 'info', effect: 'plain', label: '数据时间未知' }
  }
  const now = new Date()
  const daysDiff = Math.floor((now.getTime() - saved.getTime()) / (1000 * 60 * 60 * 24))
  if (daysDiff > 30) {
    return { type: 'warning', effect: 'light', label: `⚠ 数据可能过时（${daysDiff} 天前保存）` }
  }
  // ≤ 30 days → no chip
  return null
}
</script>

<style scoped>
.gt-staleness-chip-wrap {
  display: inline-flex;
  align-items: center;
  margin-bottom: 8px;
}
.gt-staleness-chip {
  cursor: pointer;
}
.gt-staleness-detail p {
  margin: 8px 0;
  font-size: 14px;
}
</style>
