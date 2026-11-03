<!--
  QueryEntryBanner.vue — 高级查询弹窗的入口上下文横幅（advanced-query-linkage-closure 任务 46，design §4.3；ADR-AQL-20）

  显示本次查询是从哪个业务对象进来的、后端解析出的科目，以及切换数据源 / 返回上一查询 / 清除上下文三个动作。
  自己不发请求、不改查询状态：动作全部 emit 给宿主（弹窗），由 `useQueryEntry` 统一处理。
-->
<template>
  <div v-if="entry" class="gt-qeb" data-testid="query-entry-banner">
    <div class="gt-qeb-head">
      <span class="gt-qeb-icon" aria-hidden="true">📊</span>
      <span class="gt-qeb-label" data-testid="qeb-label">{{ entry.label }}</span>
      <el-tag v-if="depth > 1" size="small" type="info" data-testid="qeb-depth">第 {{ depth }} 层</el-tag>
    </div>

    <div v-if="accounts.length" class="gt-qeb-accounts" data-testid="qeb-accounts">
      <span class="gt-qeb-accounts-title">构成科目：</span>
      <el-tag v-for="code in accounts" :key="code" size="small" class="gt-qeb-account">{{ code }}</el-tag>
      <span v-if="accountsTruncated" class="gt-qeb-more">…（仅显示前 {{ accounts.length }} 个）</span>
    </div>

    <div class="gt-qeb-actions">
      <el-button
        v-for="item in entry.switches"
        :key="item.source"
        size="small"
        :type="item.source === entry.source ? 'primary' : 'default'"
        :disabled="item.source === entry.source"
        :aria-label="`切换到${item.label}`"
        :data-testid="`qeb-switch-${item.source}`"
        @click="emit('switch', item)"
      >
        {{ item.label }}
      </el-button>
      <el-button
        v-if="canGoBack"
        size="small"
        aria-label="返回上一查询"
        data-testid="qeb-back"
        @click="emit('back')"
      >
        ← 返回上一查询
      </el-button>
      <el-button
        size="small"
        text
        aria-label="清除入口上下文"
        data-testid="qeb-clear"
        @click="emit('clear')"
      >
        清除上下文
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import type { QueryEntryRequest, QueryEntrySwitch } from './queryEntryContext'

/** 后端 `meta.entry_accounts` 最多回显 50 个（`entry_accounts.MAX_ENTRY_ACCOUNTS`），到这个数就说明可能截断过 */
const ENTRY_ACCOUNTS_CAP = 50

const props = defineProps<{
  entry: QueryEntryRequest | null
  /** 本次结果的 `meta`：`entry_accounts` 由后端解析业务对象时写入 */
  meta?: Record<string, unknown> | null
  canGoBack?: boolean
  depth?: number
}>()

const emit = defineEmits<{
  switch: [item: QueryEntrySwitch]
  back: []
  clear: []
}>()

const accounts = computed<string[]>(() => {
  const raw = props.meta?.entry_accounts
  return Array.isArray(raw) ? raw.map((code) => String(code)).filter(Boolean) : []
})
const accountsTruncated = computed(() => accounts.value.length >= ENTRY_ACCOUNTS_CAP)
const depth = computed(() => props.depth ?? (props.entry ? 1 : 0))
const canGoBack = computed(() => props.canGoBack === true)
</script>

<style scoped>
.gt-qeb {
  margin-bottom: 8px;
  padding: 8px 12px;
  border: 1px solid var(--el-color-primary-light-7);
  border-left: 3px solid var(--el-color-primary);
  border-radius: 4px;
  background: var(--el-color-primary-light-9);
}

.gt-qeb-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.gt-qeb-label {
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.gt-qeb-accounts {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--el-text-color-regular);
}

.gt-qeb-account {
  font-family: var(--el-font-family-monospace, monospace);
}

.gt-qeb-more {
  color: var(--el-text-color-secondary);
}

.gt-qeb-actions {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
</style>
