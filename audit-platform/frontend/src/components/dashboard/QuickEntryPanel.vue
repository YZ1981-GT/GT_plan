<template>
  <div class="quick-entry-panel">
    <div class="quick-entry-cards">
      <div
        v-for="entry in entries"
        :key="entry.wpCode"
        class="quick-entry-card"
        :class="{ 'quick-entry-card--disabled': !entry.exists }"
        @click="handleClick(entry)"
      >
        <el-tooltip
          :content="entry.exists ? '' : '未创建'"
          :disabled="entry.exists"
          placement="top"
        >
          <div class="quick-entry-card-inner">
            <div class="quick-entry-card-icon">
              <el-icon :size="24">
                <component :is="entry.icon" />
              </el-icon>
            </div>
            <div class="quick-entry-card-content">
              <div class="quick-entry-card-title">{{ entry.label }}</div>
              <div class="quick-entry-card-code">{{ entry.wpCode }}</div>
            </div>
            <div class="quick-entry-card-status">
              <el-tag
                :type="getStatusTagType(entry.status)"
                size="small"
                effect="plain"
              >
                {{ entry.status }}
              </el-tag>
            </div>
          </div>
        </el-tooltip>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Stamp, Connection, Warning } from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()

/** 底稿状态类型 */
type WpStatus = '未创建' | '未开始' | '进行中' | '已完成' | '已复核'

interface QuickEntry {
  wpCode: string
  label: string
  icon: typeof Stamp | typeof Connection | typeof Warning
  status: WpStatus
  exists: boolean
}

/**
 * 三个固定快速入口卡片
 * 默认状态为"未创建"，后续可通过 props 或 API 数据更新
 */
const entries = reactive<QuickEntry[]>([
  {
    wpCode: 'B15',
    label: '重要性水平',
    icon: Stamp,
    status: '未创建',
    exists: false,
  },
  {
    wpCode: 'A15',
    label: '持续经营',
    icon: Connection,
    status: '未创建',
    exists: false,
  },
  {
    wpCode: 'B50-4',
    label: '特别风险',
    icon: Warning,
    status: '未创建',
    exists: false,
  },
])

/**
 * 根据状态返回 el-tag 类型
 */
function getStatusTagType(status: WpStatus): 'success' | 'warning' | 'danger' | 'info' {
  switch (status) {
    case '已完成':
    case '已复核':
      return 'success'
    case '进行中':
      return 'warning'
    case '未开始':
      return 'info'
    case '未创建':
    default:
      return 'info'
  }
}

/**
 * 点击卡片 → 跳转到对应底稿编辑器
 * 底稿不存在时不响应点击
 */
function handleClick(entry: QuickEntry) {
  if (!entry.exists) return
  const projectId = route.params.projectId as string
  router.push({
    name: 'WorkpaperEditor',
    params: { projectId, wpId: entry.wpCode },
  })
}
</script>

<style scoped>
.quick-entry-panel {
  width: 100%;
}

.quick-entry-cards {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.quick-entry-card {
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter, #ebeef5);
  transition: all 0.2s;
  cursor: pointer;
}

.quick-entry-card:hover:not(.quick-entry-card--disabled) {
  border-color: var(--el-color-primary-light-5, #a370d8);
  box-shadow: 0 2px 8px rgba(75, 45, 119, 0.08);
}

.quick-entry-card--disabled {
  opacity: 0.5;
  cursor: not-allowed;
  background-color: var(--el-fill-color-lighter, #f5f7fa);
}

.quick-entry-card-inner {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
}

.quick-entry-card-icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 8px;
  background-color: rgba(75, 45, 119, 0.06);
  color: var(--el-color-primary, #4b2d77);
}

.quick-entry-card--disabled .quick-entry-card-icon {
  background-color: var(--el-fill-color, #f0f2f5);
  color: var(--el-text-color-placeholder, #a8abb2);
}

.quick-entry-card-content {
  flex: 1;
  min-width: 0;
}

.quick-entry-card-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-primary, #303133);
  line-height: 1.4;
}

.quick-entry-card--disabled .quick-entry-card-title {
  color: var(--el-text-color-placeholder, #a8abb2);
}

.quick-entry-card-code {
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
  margin-top: 2px;
}

.quick-entry-card-status {
  flex-shrink: 0;
}
</style>
