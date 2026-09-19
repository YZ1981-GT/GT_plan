<!--
  TraceDrawer.vue — 统一溯源抽屉组件

  Feature: platform-global-hardening
  Requirements: 8.1, 8.2

  对任意金额展示「四表→报表→审定→底稿→调整→附注」完整溯源链，
  每一跳可点击跳转到对应底稿/单元格/调整分录。

  使用 Element Plus el-drawer（右侧 480px）+ 自定义 timeline UI。
-->
<template>
  <el-drawer
    v-model="drawerVisible"
    title="金额溯源链"
    direction="rtl"
    size="480px"
    :close-on-click-modal="true"
    :append-to-body="true"
    class="trace-drawer"
  >
    <template #header>
      <div class="trace-drawer__header">
        <span class="trace-drawer__title">金额溯源链</span>
        <el-tag v-if="targetAddr" size="small" effect="plain" type="info">
          {{ targetAddr }}
        </el-tag>
      </div>
    </template>

    <!-- 目标金额信息 -->
    <div v-if="targetValue !== null && targetValue !== undefined" class="trace-drawer__target">
      <span class="trace-drawer__target-label">目标金额</span>
      <span class="trace-drawer__target-value">{{ formatAmount(targetValue) }}</span>
    </div>

    <!-- 加载状态 -->
    <el-skeleton v-if="loading && chain.length === 0" :rows="6" animated />

    <!-- 错误 -->
    <el-alert
      v-else-if="error"
      :title="error"
      type="error"
      :closable="false"
      show-icon
      style="margin-bottom: 16px"
    />

    <!-- 溯源 timeline -->
    <div v-else-if="chain.length > 0" v-loading="loading" class="trace-drawer__timeline">
      <div
        v-for="(node, idx) in chain"
        :key="node.type"
        class="trace-node"
        :class="{ 'trace-node--active': idx === activeIndex }"
      >
        <!-- 连接线（首个节点不显示） -->
        <div class="trace-node__connector">
          <div class="trace-node__dot" :class="`trace-node__dot--${node.type}`" />
          <div v-if="idx < chain.length - 1" class="trace-node__line" />
        </div>

        <!-- 节点内容 -->
        <div class="trace-node__content" @click="onNodeClick(node, idx)">
          <div class="trace-node__header">
            <el-tag
              :type="getNodeTagType(node.type)"
              size="small"
              effect="dark"
              class="trace-node__type-tag"
            >
              {{ node.label }}
            </el-tag>
            <span v-if="node.reachable" class="trace-node__jump-hint">
              <el-icon><Right /></el-icon>
            </span>
          </div>

          <div class="trace-node__desc">{{ node.description }}</div>

          <div v-if="node.amount !== null && node.amount !== undefined" class="trace-node__amount">
            {{ formatAmount(node.amount) }}
          </div>

          <!-- 跳转箭头 -->
          <div v-if="idx < chain.length - 1" class="trace-node__arrow">
            ↓
          </div>
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <el-empty v-else description="暂无溯源数据" :image-size="80" />

    <!-- 底部操作 -->
    <template #footer>
      <el-button @click="drawerVisible = false">关闭</el-button>
      <el-button type="primary" :loading="loading" @click="reload">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
/**
 * Feature: platform-global-hardening
 */
import { computed, ref, toRef } from 'vue'
import { Right, Refresh } from '@element-plus/icons-vue'
import { useTraceData, type TraceNode } from './useTraceData'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

// ─── Props / Emits ───
const props = defineProps<{
  /** v-model 控制抽屉显示 */
  visible: boolean
  /** 目标金额 */
  targetValue: number | null
  /** 目标地址（addr_id 或坐标） */
  targetAddr: string
  /** 项目 ID */
  projectId: string
}>()

const emit = defineEmits<{
  /** v-model:visible 更新 */
  'update:visible': [val: boolean]
  /** 节点跳转事件 */
  'navigate': [payload: { type: TraceNode['type']; target: string }]
}>()

// ─── State ───
const activeIndex = ref(-1)
const displayPrefs = useDisplayPrefsStore()

// ─── Drawer visibility (v-model) ───
const drawerVisible = computed<boolean>({
  get: () => props.visible,
  set: (val) => emit('update:visible', val),
})

// ─── 溯源链数据 ───
const { chain, loading, error, reload } = useTraceData(
  toRef(props, 'projectId'),
  toRef(props, 'targetAddr'),
  toRef(props, 'targetValue'),
)

// ─── Methods ───
function formatAmount(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  // 优先使用全局 displayPrefs 格式化
  if (displayPrefs?.fmtAmount) {
    return displayPrefs.fmtAmount(value)
  }
  return value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function getNodeTagType(type: TraceNode['type']): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
  const typeMap: Record<TraceNode['type'], 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
    raw_data: 'info',
    report: 'primary',
    audited: 'success',
    workpaper: 'warning',
    adjustment: 'danger',
    note: 'info',
  }
  return typeMap[type] ?? 'info'
}

function onNodeClick(node: TraceNode, idx: number) {
  if (!node.reachable) return
  activeIndex.value = idx
  emit('navigate', { type: node.type, target: node.target })
}
</script>

<style scoped>
.trace-drawer__header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.trace-drawer__title {
  font-size: 16px;
  font-weight: 600;
  color: var(--gt-color-text-primary, #303133);
}

.trace-drawer__target {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  margin-bottom: 16px;
  background: var(--gt-color-bg-page, #f5f7fa);
  border-radius: 6px;
  border: 1px solid var(--gt-color-border-light, #ebeef5);
}

.trace-drawer__target-label {
  font-size: 13px;
  color: var(--gt-color-text-secondary, #606266);
}

.trace-drawer__target-value {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 18px;
  font-weight: 600;
  color: var(--gt-color-primary, #6750a4);
}

/* ─── Timeline ─── */
.trace-drawer__timeline {
  display: flex;
  flex-direction: column;
  gap: 0;
  padding: 0 4px;
}

.trace-node {
  display: flex;
  gap: 16px;
  position: relative;
}

.trace-node__connector {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 24px;
  flex-shrink: 0;
}

.trace-node__dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 2px solid;
  background: #fff;
  z-index: 1;
  margin-top: 6px;
}

.trace-node__dot--raw_data {
  border-color: #909399;
  background: #909399;
}
.trace-node__dot--report {
  border-color: #409eff;
  background: #409eff;
}
.trace-node__dot--audited {
  border-color: #67c23a;
  background: #67c23a;
}
.trace-node__dot--workpaper {
  border-color: #e6a23c;
  background: #e6a23c;
}
.trace-node__dot--adjustment {
  border-color: #f56c6c;
  background: #f56c6c;
}
.trace-node__dot--note {
  border-color: #909399;
  background: #909399;
}

.trace-node__line {
  width: 2px;
  flex: 1;
  min-height: 20px;
  background: var(--gt-color-border, #dcdfe6);
}

.trace-node__content {
  flex: 1;
  padding: 8px 12px;
  margin-bottom: 8px;
  border: 1px solid var(--gt-color-border-light, #ebeef5);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
  background: #fff;
}

.trace-node__content:hover {
  border-color: var(--gt-color-primary, #6750a4);
  box-shadow: 0 2px 8px rgba(103, 80, 164, 0.08);
}

.trace-node--active .trace-node__content {
  border-color: var(--gt-color-primary, #6750a4);
  background: var(--gt-color-primary-light-9, #f5f0ff);
}

.trace-node__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}

.trace-node__type-tag {
  font-size: 11px;
}

.trace-node__jump-hint {
  color: var(--gt-color-text-placeholder, #c0c4cc);
  font-size: 14px;
  transition: color 0.2s;
}

.trace-node__content:hover .trace-node__jump-hint {
  color: var(--gt-color-primary, #6750a4);
}

.trace-node__desc {
  font-size: var(--wp-font-size, 13px);
  color: var(--gt-color-text-regular, #606266);
  margin-bottom: 4px;
}

.trace-node__amount {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: var(--wp-font-size, 13px);
  color: var(--gt-color-text-primary, #303133);
  font-weight: 500;
}

.trace-node__arrow {
  text-align: center;
  color: var(--gt-color-text-placeholder, #c0c4cc);
  font-size: 12px;
  margin-top: 4px;
  display: none; /* 箭头改用连接线表示 */
}
</style>
