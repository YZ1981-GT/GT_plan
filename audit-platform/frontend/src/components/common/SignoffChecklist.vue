<template>
  <!--
    SignoffChecklist — 合伙人签发一致性清单组件（P2-2）
    =============================================================================
    Requirements: 5.1, 5.2, 5.3
    - P2-2.1 签发页显示一致性清单
    - P2-2.2 blocking 项阻断签发
    - P2-2.3 warning 项允许合伙人显式确认
    - P2-2.4 确认动作记录审计日志
  -->
  <div class="gt-signoff-checklist">
    <!-- 标题区 -->
    <div class="gt-signoff-checklist__header">
      <h3 class="gt-signoff-checklist__title">签发一致性清单</h3>
      <el-button
        text
        size="small"
        :loading="loading"
        @click="handleRefresh"
      >
        刷新清单
      </el-button>
    </div>

    <!-- 加载态 -->
    <div v-if="loading" class="gt-signoff-checklist__loading">
      <el-icon class="is-loading"><Loading /></el-icon>
      <span>正在检查一致性...</span>
    </div>

    <!-- 错误态 -->
    <div v-else-if="error" class="gt-signoff-checklist__error">
      <el-alert type="error" :closable="false" :title="error" />
    </div>

    <!-- 清单内容 -->
    <template v-else-if="checklist">
      <!-- 汇总状态 -->
      <div class="gt-signoff-checklist__summary">
        <el-tag v-if="blockingItems.length" type="danger" effect="dark" size="large">
          {{ blockingItems.length }} 项阻断
        </el-tag>
        <el-tag v-if="warningItems.length" type="warning" effect="dark" size="large">
          {{ warningItems.length }} 项警告
        </el-tag>
        <el-tag v-if="infoItems.length" type="info" size="large">
          {{ infoItems.length }} 项信息
        </el-tag>
        <el-tag v-if="canSignoff" type="success" effect="dark" size="large">
          可签发
        </el-tag>
      </div>

      <!-- Blocking 区域 -->
      <div v-if="blockingItems.length" class="gt-signoff-checklist__section gt-signoff-checklist__section--blocking">
        <h4 class="gt-signoff-checklist__section-title gt-signoff-checklist__section-title--blocking">
          <el-icon><CircleCloseFilled /></el-icon>
          阻断项（必须解决后方可签发）
        </h4>
        <div
          v-for="(item, idx) in blockingItems"
          :key="`blocking-${idx}`"
          class="gt-signoff-checklist__item gt-signoff-checklist__item--blocking"
        >
          <div class="gt-signoff-checklist__item-content">
            <el-tag size="small" type="danger">{{ getCategoryLabel(item.category) }}</el-tag>
            <span class="gt-signoff-checklist__item-message">{{ item.message }}</span>
          </div>
          <el-button
            v-if="item.route"
            type="primary"
            text
            size="small"
            @click="handleJump(item)"
          >
            跳转定位
          </el-button>
        </div>
      </div>

      <!-- Warning 区域 -->
      <div v-if="warningItems.length" class="gt-signoff-checklist__section gt-signoff-checklist__section--warning">
        <h4 class="gt-signoff-checklist__section-title gt-signoff-checklist__section-title--warning">
          <el-icon><WarningFilled /></el-icon>
          警告项（需合伙人确认后签发）
        </h4>
        <div
          v-for="(item, idx) in warningItems"
          :key="`warning-${idx}`"
          class="gt-signoff-checklist__item gt-signoff-checklist__item--warning"
        >
          <div class="gt-signoff-checklist__item-content">
            <el-tag size="small" type="warning">{{ getCategoryLabel(item.category) }}</el-tag>
            <span class="gt-signoff-checklist__item-message">{{ item.message }}</span>
          </div>
          <div class="gt-signoff-checklist__item-actions">
            <el-button
              v-if="item.route"
              text
              size="small"
              @click="handleJump(item)"
            >
              查看
            </el-button>
            <el-button
              v-if="!isItemConfirmed(item)"
              type="warning"
              size="small"
              @click="handleConfirmWarning(item)"
            >
              确认放行
            </el-button>
            <el-tag v-else type="success" size="small" effect="plain">
              已确认
            </el-tag>
          </div>
        </div>
        <!-- 批量确认 -->
        <div v-if="!allWarningsConfirmed" class="gt-signoff-checklist__batch-confirm">
          <el-button
            type="warning"
            @click="handleConfirmAll"
          >
            批量确认所有警告项
          </el-button>
        </div>
      </div>

      <!-- Info 区域 -->
      <div v-if="infoItems.length" class="gt-signoff-checklist__section gt-signoff-checklist__section--info">
        <h4 class="gt-signoff-checklist__section-title gt-signoff-checklist__section-title--info">
          <el-icon><InfoFilled /></el-icon>
          信息项
        </h4>
        <div
          v-for="(item, idx) in infoItems"
          :key="`info-${idx}`"
          class="gt-signoff-checklist__item gt-signoff-checklist__item--info"
        >
          <div class="gt-signoff-checklist__item-content">
            <el-tag size="small" type="info">{{ getCategoryLabel(item.category) }}</el-tag>
            <span class="gt-signoff-checklist__item-message">{{ item.message }}</span>
          </div>
          <el-button
            v-if="item.route"
            text
            size="small"
            @click="handleJump(item)"
          >
            查看
          </el-button>
        </div>
      </div>

      <!-- 签发按钮区 -->
      <div class="gt-signoff-checklist__footer">
        <el-button
          type="primary"
          size="large"
          :disabled="!canSignoff"
          @click="$emit('signoff')"
        >
          {{ canSignoff ? '确认签发' : '存在阻断项，无法签发' }}
        </el-button>
      </div>
    </template>

    <!-- 空态 -->
    <div v-else class="gt-signoff-checklist__empty">
      <el-empty description="点击刷新获取一致性清单" :image-size="64" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  Loading,
  CircleCloseFilled,
  WarningFilled,
  InfoFilled,
} from '@element-plus/icons-vue'
import { useSignoffChecklist } from '@/composables/useSignoffChecklist'
import type { CheckItem } from '@/composables/useSignoffChecklist'

export interface SignoffChecklistProps {
  projectId: string
  year?: number
  userId?: string
  autoLoad?: boolean
}

const props = withDefaults(defineProps<SignoffChecklistProps>(), {
  year: undefined,
  userId: '',
  autoLoad: true,
})

const emit = defineEmits<{
  signoff: []
  jump: [route: string]
}>()

const router = useRouter()

const {
  loading,
  error,
  checklist,
  blockingItems,
  warningItems,
  infoItems,
  allWarningsConfirmed,
  canSignoff,
  warningConfirmations,
  fetchChecklist,
  confirmWarning,
  confirmAllWarnings,
} = useSignoffChecklist(props.projectId)

// ─── Category labels ──────────────────────────────────────────────────

const CATEGORY_LABELS: Record<string, string> = {
  trial_balance: '试算表',
  adjustment: '调整分录',
  workpaper: '底稿',
  note: '附注',
  report: '报告',
  ai_content: 'AI 内容',
}

function getCategoryLabel(category: string): string {
  return CATEGORY_LABELS[category] || category
}

// ─── Actions ──────────────────────────────────────────────────────────

function handleRefresh() {
  fetchChecklist(props.year)
}

function handleJump(item: CheckItem) {
  if (!item.route) return
  emit('jump', item.route)
  router.push(item.route)
}

function isItemConfirmed(item: CheckItem): boolean {
  const globalIdx = checklist.value?.items.indexOf(item) ?? -1
  return warningConfirmations.value.has(globalIdx)
}

function handleConfirmWarning(item: CheckItem) {
  const globalIdx = checklist.value?.items.indexOf(item) ?? -1
  if (globalIdx >= 0) {
    confirmWarning(globalIdx, props.userId)
  }
}

function handleConfirmAll() {
  confirmAllWarnings(props.userId)
}

// ─── Lifecycle ────────────────────────────────────────────────────────

onMounted(() => {
  if (props.autoLoad) {
    fetchChecklist(props.year)
  }
})
</script>

<style scoped>
.gt-signoff-checklist {
  padding: 16px;
}

.gt-signoff-checklist__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.gt-signoff-checklist__title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--gt-text-primary, #1a1a1a);
}

.gt-signoff-checklist__loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 24px 0;
  color: var(--gt-text-secondary, #999);
}

.gt-signoff-checklist__loading .is-loading {
  animation: rotating 1.5s linear infinite;
}

.gt-signoff-checklist__summary {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.gt-signoff-checklist__section {
  margin-bottom: 20px;
  border-radius: 8px;
  padding: 12px 16px;
}

.gt-signoff-checklist__section--blocking {
  background: #fef0f0;
  border: 1px solid #fab6b6;
}

.gt-signoff-checklist__section--warning {
  background: #fdf6ec;
  border: 1px solid #f3d19e;
}

.gt-signoff-checklist__section--info {
  background: #f4f4f5;
  border: 1px solid #d3d4d6;
}

.gt-signoff-checklist__section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
}

.gt-signoff-checklist__section-title--blocking {
  color: #f56c6c;
}

.gt-signoff-checklist__section-title--warning {
  color: #e6a23c;
}

.gt-signoff-checklist__section-title--info {
  color: #909399;
}

.gt-signoff-checklist__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  gap: 8px;
}

.gt-signoff-checklist__item:last-child {
  border-bottom: none;
}

.gt-signoff-checklist__item-content {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.gt-signoff-checklist__item-message {
  font-size: 13px;
  color: var(--gt-text-primary, #1a1a1a);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gt-signoff-checklist__item-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.gt-signoff-checklist__batch-confirm {
  margin-top: 12px;
  text-align: right;
}

.gt-signoff-checklist__footer {
  margin-top: 24px;
  text-align: center;
}

.gt-signoff-checklist__empty {
  padding: 40px 0;
  text-align: center;
}

@keyframes rotating {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
