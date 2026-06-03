<!--
  GtWpPreparationHeader.vue — workpaper 级编制信息表头（所有 sheet 共享、可折叠）
  GET /api/workpapers/{wpId}/preparation-info（7 字段，无 accounting_period）
-->
<template>
  <div class="gt-wp-prep" :class="{ 'is-collapsed': collapsed }">
    <div class="gt-wp-prep__bar" @click="collapsed = !collapsed">
      <span class="gt-wp-prep__title">编制信息</span>
      <span class="gt-wp-prep__summary" v-if="collapsed">{{ summaryText }}</span>
      <el-button
        class="gt-wp-prep__toggle"
        link
        type="primary"
        size="small"
        @click.stop="collapsed = !collapsed"
      >
        {{ collapsed ? '展开' : '收起' }}
      </el-button>
    </div>
    <div v-show="!collapsed" class="gt-wp-prep__body" v-loading="loading">
      <el-descriptions :column="4" border size="small" class="gt-wp-prep__desc">
        <el-descriptions-item label="被审计单位">{{ field('entity_name') }}</el-descriptions-item>
        <el-descriptions-item label="截止日">{{ field('period_end') }}</el-descriptions-item>
        <el-descriptions-item label="编制人">{{ field('preparer') }}</el-descriptions-item>
        <el-descriptions-item label="编制时间">{{ field('prep_date') }}</el-descriptions-item>
        <el-descriptions-item label="复核人">{{ field('reviewer') }}</el-descriptions-item>
        <el-descriptions-item label="复核日期">{{ field('review_date') }}</el-descriptions-item>
        <el-descriptions-item label="索引号" :span="2">{{ field('index_no') }}</el-descriptions-item>
      </el-descriptions>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { api } from '@/services/apiProxy'

interface PreparationInfo {
  entity_name?: string
  period_end?: string
  preparer?: string
  prep_date?: string
  reviewer?: string
  review_date?: string
  index_no?: string
}

const props = defineProps<{
  wpId: string
  readonly?: boolean
}>()

const collapsed = ref(false)
const loading = ref(false)
const info = ref<PreparationInfo>({})

function field(key: keyof PreparationInfo): string {
  const v = info.value[key]
  return v != null && String(v).trim() !== '' ? String(v) : '—'
}

const summaryText = computed(() => {
  const parts = [field('entity_name'), field('index_no')].filter(p => p !== '—')
  return parts.length ? parts.join(' · ') : '—'
})

async function load() {
  if (!props.wpId) return
  loading.value = true
  try {
    const data = await api.get<PreparationInfo>(`/api/workpapers/${props.wpId}/preparation-info`)
    info.value = data ?? {}
  } catch {
    info.value = {}
  } finally {
    loading.value = false
  }
}

watch(() => props.wpId, (id) => {
  if (id) load()
}, { immediate: true })
</script>

<style scoped>
.gt-wp-prep {
  margin: 0 0 8px;
  border: 1px solid var(--gt-color-border-purple-light, #d8b8ee);
  border-radius: 6px;
  background: var(--gt-color-primary-bg, #f4f0fa);
  overflow: hidden;
}
.gt-wp-prep.is-collapsed {
  min-height: 36px;
}
.gt-wp-prep__bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  cursor: pointer;
  user-select: none;
}
.gt-wp-prep__title {
  font-weight: 600;
  font-size: 13px;
  color: var(--gt-color-primary, #4b2d77);
}
.gt-wp-prep__summary {
  flex: 1;
  font-size: 12px;
  color: var(--gt-color-text-secondary, #606266);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.gt-wp-prep__toggle {
  margin-left: auto;
}
.gt-wp-prep__body {
  padding: 0 12px 10px;
}
:deep(.gt-wp-prep__desc .el-descriptions__title) {
  color: var(--gt-color-primary, #4b2d77);
}
:deep(.gt-wp-prep__desc .el-descriptions__label) {
  color: var(--gt-color-primary, #4b2d77);
  background: var(--gt-color-primary-bg, #f4f0fa);
}
:deep(.gt-wp-prep__toggle.el-button.is-link) {
  color: var(--gt-color-primary, #4b2d77);
}
:deep(.el-tag) {
  --el-tag-text-color: var(--gt-color-primary, #4b2d77);
  --el-tag-bg-color: var(--gt-color-primary-bg, #f4f0fa);
  --el-tag-border-color: var(--gt-color-border-purple-light, #d8b8ee);
}
</style>
