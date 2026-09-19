<template>
  <div
    class="chat-context-inspector"
    role="region"
    aria-label="上下文信息面板"
  >
    <!-- 折叠标题 -->
    <button
      class="chat-context-inspector__toggle"
      :aria-expanded="expanded"
      aria-controls="context-inspector-content"
      @click="expanded = !expanded"
    >
      <el-icon aria-hidden="true" class="chat-context-inspector__chevron" :class="{ 'is-expanded': expanded }">
        <ArrowRight />
      </el-icon>
      <span class="chat-context-inspector__title">上下文</span>
      <span v-if="manifestSummary" class="chat-context-inspector__summary">
        {{ manifestSummary }}
      </span>
    </button>

    <!-- 展开内容 -->
    <div
      v-show="expanded"
      id="context-inspector-content"
      class="chat-context-inspector__content"
    >
      <!-- 无数据提示 -->
      <div
        v-if="!manifest || manifest.length === 0"
        class="chat-context-inspector__empty"
        role="status"
      >
        <span>暂无上下文信息</span>
      </div>

      <!-- Manifest 列表 -->
      <ul v-else class="chat-context-inspector__list" role="list" aria-label="上下文清单">
        <li
          v-for="(item, idx) in manifest"
          :key="idx"
          class="chat-context-inspector__item"
          :class="[`is-${item.decision}`]"
        >
          <!-- 决策状态图标 -->
          <span
            class="chat-context-inspector__decision"
            :title="getDecisionLabel(item.decision)"
            aria-hidden="true"
          >
            {{ getDecisionIcon(item.decision) }}
          </span>

          <!-- 标签+来源 -->
          <div class="chat-context-inspector__item-info">
            <span class="chat-context-inspector__item-label">
              {{ item.label }}
            </span>
            <span class="chat-context-inspector__item-meta">
              {{ getSourceTypeLabel(item.source_type) }}
              <template v-if="item.version">
                · v{{ item.version }}
              </template>
              <template v-if="item.is_stale">
                <el-tag size="small" type="warning" effect="plain" class="chat-context-inspector__stale-tag">
                  已过期
                </el-tag>
              </template>
            </span>
            <!-- 决策原因 -->
            <span v-if="item.reason_code && item.decision !== 'included'" class="chat-context-inspector__item-reason">
              {{ getReasonLabel(item.reason_code, item.decision) }}
            </span>
          </div>

          <!-- Token 估计 -->
          <span class="chat-context-inspector__item-tokens" :title="`约 ${item.token_estimate} 个 token`">
            {{ formatTokens(item.token_estimate) }}
          </span>

          <!-- 跳转按钮（jump_route 存在且 re-auth in target page — Req 5.9） -->
          <button
            v-if="item.jump_route"
            class="chat-context-inspector__jump"
            :aria-label="`跳转到 ${item.label}`"
            :title="`查看「${item.label}」`"
            @click="handleJump(item)"
          >
            <el-icon aria-hidden="true"><Right /></el-icon>
          </button>
        </li>
      </ul>

      <!-- 预算汇总 -->
      <div v-if="budgetInfo" class="chat-context-inspector__budget" role="status" aria-label="Token 预算">
        <span>
          已使用 {{ budgetInfo.used }} / {{ budgetInfo.total }} tokens
        </span>
        <div class="chat-context-inspector__budget-bar">
          <div
            class="chat-context-inspector__budget-fill"
            :style="{ width: budgetInfo.percentage + '%' }"
            :class="{ 'is-warning': budgetInfo.percentage > 80 }"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * ChatContextInspector — 展示 Context Manifest
 *
 * 从 `context_ready` 事件读取 manifest，展示 included/trimmed/denied/unavailable 的资源，
 * 以及 version、stale、token estimate 和 jump route（点击时在目标页面再次鉴权 — Req 5.9）。
 *
 * 不把客户端 label 当权威 —— manifest 的 label 来自服务端 context_ready 事件。
 *
 * Feature: dsh-agent-panel-integration / Task 15
 * Validates: Requirements 5.7, 5.9
 * Properties: 12, 13
 */
import { ref, computed } from 'vue'
import { ArrowRight, Right } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { MENTION_TYPE_LABELS, type MentionType } from '@/composables/useAiMention'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Context Manifest item（服务端 context_ready 返回） */
export interface ContextManifestItem {
  source_type: string
  source_id: string
  label: string
  decision: 'included' | 'trimmed' | 'denied' | 'unavailable'
  reason_code: string | null
  token_estimate: number
  version: string | null
  is_stale: boolean
  jump_route: string | null
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

const props = defineProps<{
  /** context_ready 事件中的 manifest 数组 */
  manifest: ContextManifestItem[] | null
  /** 整体 token 预算（可选） */
  tokenBudget?: number
}>()

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const expanded = ref(false)
const router = useRouter()

// ---------------------------------------------------------------------------
// Computed
// ---------------------------------------------------------------------------

/** 摘要统计 */
const manifestSummary = computed<string>(() => {
  if (!props.manifest || props.manifest.length === 0) return ''
  const included = props.manifest.filter((m) => m.decision === 'included').length
  const trimmed = props.manifest.filter((m) => m.decision === 'trimmed').length
  const denied = props.manifest.filter((m) => m.decision === 'denied').length
  const unavailable = props.manifest.filter((m) => m.decision === 'unavailable').length

  const parts: string[] = []
  if (included > 0) parts.push(`${included} 项纳入`)
  if (trimmed > 0) parts.push(`${trimmed} 项裁剪`)
  if (denied > 0) parts.push(`${denied} 项拒绝`)
  if (unavailable > 0) parts.push(`${unavailable} 项不可用`)
  return parts.join('，')
})

/** 预算信息 */
const budgetInfo = computed(() => {
  if (!props.manifest || props.manifest.length === 0) return null
  const used = props.manifest
    .filter((m) => m.decision === 'included' || m.decision === 'trimmed')
    .reduce((sum, m) => sum + (m.token_estimate || 0), 0)
  const total = props.tokenBudget || 0
  if (total <= 0) return null
  return {
    used,
    total,
    percentage: Math.min(100, Math.round((used / total) * 100)),
  }
})

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getDecisionIcon(decision: string): string {
  switch (decision) {
    case 'included': return '✅'
    case 'trimmed': return '✂️'
    case 'denied': return '🚫'
    case 'unavailable': return '⚠️'
    default: return '❓'
  }
}

function getDecisionLabel(decision: string): string {
  switch (decision) {
    case 'included': return '已纳入上下文'
    case 'trimmed': return '已裁剪（部分纳入）'
    case 'denied': return '无权访问'
    case 'unavailable': return '暂不可用'
    default: return '未知状态'
  }
}

function getSourceTypeLabel(sourceType: string): string {
  return MENTION_TYPE_LABELS[sourceType as MentionType] ?? sourceType
}

function getReasonLabel(code: string, decision: string): string {
  const reasons: Record<string, string> = {
    budget_exceeded: 'Token 预算不足',
    access_denied: '无访问权限',
    not_found: '资源不存在',
    service_unavailable: '服务不可用',
    embedding_unavailable: '语义服务不可用',
    timeout: '加载超时',
    empty_content: '内容为空',
    stale: '数据已过期',
  }
  if (reasons[code]) return reasons[code]
  if (decision === 'denied') return '无权访问'
  if (decision === 'unavailable') return '暂不可用'
  return code
}

function formatTokens(count: number): string {
  if (count <= 0) return ''
  if (count >= 1000) return `${(count / 1000).toFixed(1)}k`
  return String(count)
}

// ---------------------------------------------------------------------------
// Jump — Req 5.9: 点击 jump_route 在目标页面再次鉴权
// ---------------------------------------------------------------------------

function handleJump(item: ContextManifestItem) {
  if (!item.jump_route) return
  // 使用 router.push 导航到目标页面（目标页面自身会执行权限校验）
  try {
    router.push(item.jump_route)
  } catch {
    // 无效路由静默忽略
    window.open(item.jump_route, '_blank')
  }
}
</script>

<style scoped>
.chat-context-inspector {
  border: 1px solid var(--el-border-color-lighter, #ebeef5);
  border-radius: 6px;
  background: var(--el-bg-color, #fff);
  overflow: hidden;
}

.chat-context-inspector__toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 8px 12px;
  border: none;
  background: var(--el-fill-color-lighter, #fafcff);
  cursor: pointer;
  font-size: 12px;
  text-align: left;
  color: var(--el-text-color-regular, #606266);
  transition: background 0.15s;
}

.chat-context-inspector__toggle:hover {
  background: var(--el-fill-color-light, #f2f6fc);
}

.chat-context-inspector__toggle:focus-visible {
  outline: 2px solid var(--el-color-primary, #409eff);
  outline-offset: -2px;
}

.chat-context-inspector__chevron {
  transition: transform 0.2s;
  font-size: 12px;
}

.chat-context-inspector__chevron.is-expanded {
  transform: rotate(90deg);
}

.chat-context-inspector__title {
  font-weight: 500;
}

.chat-context-inspector__summary {
  margin-left: auto;
  color: var(--el-text-color-secondary, #909399);
  font-size: 11px;
}

.chat-context-inspector__content {
  border-top: 1px solid var(--el-border-color-extra-light, #f2f6fc);
}

.chat-context-inspector__empty {
  padding: 16px 12px;
  text-align: center;
  color: var(--el-text-color-placeholder, #a8abb2);
  font-size: 12px;
}

.chat-context-inspector__list {
  list-style: none;
  margin: 0;
  padding: 4px 0;
  max-height: 200px;
  overflow-y: auto;
}

.chat-context-inspector__item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 12px;
  font-size: 12px;
  border-bottom: 1px solid var(--el-border-color-extra-light, #f2f6fc);
}

.chat-context-inspector__item:last-child {
  border-bottom: none;
}

.chat-context-inspector__item.is-denied,
.chat-context-inspector__item.is-unavailable {
  opacity: 0.7;
}

.chat-context-inspector__item.is-trimmed {
  background: var(--el-color-warning-light-9, #fdf6ec);
}

.chat-context-inspector__decision {
  flex-shrink: 0;
  font-size: 14px;
  line-height: 1;
  margin-top: 2px;
}

.chat-context-inspector__item-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.chat-context-inspector__item-label {
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--el-text-color-primary, #303133);
}

.chat-context-inspector__item-meta {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--el-text-color-secondary, #909399);
  font-size: 11px;
}

.chat-context-inspector__stale-tag {
  font-size: 10px;
  padding: 0 4px;
  height: 16px;
  line-height: 16px;
}

.chat-context-inspector__item-reason {
  font-size: 11px;
  color: var(--el-text-color-placeholder, #a8abb2);
  font-style: italic;
}

.chat-context-inspector__item-tokens {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--el-text-color-secondary, #909399);
  font-variant-numeric: tabular-nums;
  margin-top: 2px;
}

.chat-context-inspector__jump {
  flex-shrink: 0;
  border: none;
  background: none;
  cursor: pointer;
  color: var(--el-color-primary, #409eff);
  padding: 2px;
  border-radius: 4px;
  margin-top: 1px;
}

.chat-context-inspector__jump:hover {
  background: var(--el-color-primary-light-9, #ecf5ff);
}

.chat-context-inspector__jump:focus-visible {
  outline: 2px solid var(--el-color-primary, #409eff);
  outline-offset: 1px;
}

/* Budget bar */
.chat-context-inspector__budget {
  padding: 8px 12px;
  border-top: 1px solid var(--el-border-color-extra-light, #f2f6fc);
  font-size: 11px;
  color: var(--el-text-color-secondary, #909399);
}

.chat-context-inspector__budget-bar {
  height: 4px;
  margin-top: 4px;
  border-radius: 2px;
  background: var(--el-fill-color, #f0f2f5);
  overflow: hidden;
}

.chat-context-inspector__budget-fill {
  height: 100%;
  border-radius: 2px;
  background: var(--el-color-primary, #409eff);
  transition: width 0.3s ease;
}

.chat-context-inspector__budget-fill.is-warning {
  background: var(--el-color-warning, #e6a23c);
}

@media (prefers-reduced-motion: reduce) {
  .chat-context-inspector__chevron {
    transition: none;
  }
  .chat-context-inspector__budget-fill {
    transition: none;
  }
}
</style>
