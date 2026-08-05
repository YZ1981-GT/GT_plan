<script setup lang="ts">
/**
 * SendListConsistencyPanel — 受限勾稽 / E0-5 红线 / 完整性红线 紧凑展示面板
 *
 * 对齐 H1DisclosureConsistencyPanel / D1DisclosureConsistencyPanel 范式：
 * 紧凑单行 bar + 可折叠明细 + 规则 tooltip
 */
import { computed } from 'vue'
import type { ConsistencyItem } from './sendListConsistency'

const props = defineProps<{
  items: ConsistencyItem[]
  title?: string
}>()

const errorCount = computed(() => props.items.filter(i => i.level === 'error').length)
const warningCount = computed(() => props.items.filter(i => i.level === 'warning').length)
const okCount = computed(() => props.items.filter(i => i.level === 'ok').length)
const skipCount = computed(() => props.items.filter(i => i.level === 'skip').length)

const barType = computed(() => {
  if (errorCount.value > 0) return 'danger'
  if (warningCount.value > 0) return 'warning'
  if (skipCount.value > 0 && okCount.value === 0) return 'info'
  return 'success'
})

const barText = computed(() => {
  const parts: string[] = []
  if (errorCount.value) parts.push(`异常 ${errorCount.value}`)
  if (warningCount.value) parts.push(`提示 ${warningCount.value}`)
  if (okCount.value) parts.push(`通过 ${okCount.value}`)
  if (skipCount.value) parts.push(`跳过 ${skipCount.value}`)
  return parts.join(' · ') || '暂无可比对数据'
})

function levelTag(level: string) {
  switch (level) {
    case 'error': return 'danger'
    case 'warning': return 'warning'
    case 'ok': return 'success'
    default: return 'info'
  }
}
function levelLabel(level: string) {
  switch (level) {
    case 'error': return '异常'
    case 'warning': return '提示'
    case 'ok': return '通过'
    case 'skip': return '跳过'
    default: return level
  }
}
</script>

<template>
  <div class="send-list-consistency-panel" v-if="items.length > 0">
    <el-collapse>
      <el-collapse-item>
        <template #title>
          <div class="consistency-bar">
            <el-tag :type="barType" size="small" effect="dark" style="margin-right: 8px">
              {{ title || '勾稽校验' }}
            </el-tag>
            <span class="bar-text">{{ barText }}</span>
          </div>
        </template>

        <div class="consistency-detail">
          <div
            v-for="item in items"
            :key="item.id"
            class="consistency-item"
          >
            <el-tag :type="levelTag(item.level)" size="small" style="margin-right: 8px">
              {{ levelLabel(item.level) }}
            </el-tag>
            <el-tooltip :content="item.rule" placement="top">
              <span class="item-label">{{ item.label }}</span>
            </el-tooltip>
            <span v-if="item.refs?.length" class="item-refs">
              {{ item.refs.join(' · ') }}
            </span>
          </div>
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<style scoped>
.send-list-consistency-panel {
  margin: 12px 0;
}
.consistency-bar {
  display: flex;
  align-items: center;
}
.bar-text {
  font-size: 12px;
  color: #606266;
}
.consistency-detail {
  padding: 8px 0;
}
.consistency-item {
  display: flex;
  align-items: center;
  padding: 4px 0;
  font-size: 12px;
}
.item-label {
  flex: 1;
  color: #303133;
}
.item-refs {
  margin-left: 12px;
  color: #909399;
  font-size: 11px;
}
</style>
