<template>
  <el-alert v-if="items.length" type="warning" show-icon :closable="false" class="gt-client-booked-banner">
    <template #title>
      <strong>本底稿涉及 {{ items.length }} 笔客户已入账调整</strong>
    </template>
    <div>请检查审定表、明细调整列和调整页签，确保不再重复计入；发布审定数时系统会再次要求逐组确认。</div>
    <div class="gt-client-booked-banner__items">
      <el-tag v-for="item in items" :key="item.entry_group_id" size="small" type="warning">
        {{ item.adjustment_no || item.entry_group_id.slice(0, 8) }} · {{ (item.account_codes || []).join('、') }}
      </el-tag>
    </div>
  </el-alert>
  <el-alert v-else-if="error" type="error" show-icon :closable="false" class="gt-client-booked-banner">
    <template #title>
      <span>读取客户已入账调整提示失败。</span>
      <el-button text size="small" type="primary" @click="load">重试</el-button>
    </template>
  </el-alert>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { api } from '@/services/apiProxy'

const props = defineProps<{ wpId: string }>()
const items = ref<Array<{ entry_group_id: string; adjustment_no?: string; account_codes?: string[] }>>([])
const error = ref(false)
let epoch = 0

async function load(): Promise<void> {
  const id = props.wpId
  if (!id) { items.value = []; return }
  const request = ++epoch
  error.value = false
  try {
    const data = await api.get(`/api/workpapers/${id}/client-booked-adjustments`, { _silent: true } as any)
    if (request !== epoch || id !== props.wpId) return
    items.value = Array.isArray(data?.items) ? data.items : []
  } catch {
    if (request !== epoch || id !== props.wpId) return
    error.value = true
  }
}

watch(() => props.wpId, () => { void load() }, { immediate: true })
</script>

<style scoped>
.gt-client-booked-banner { margin-bottom: 8px; }
.gt-client-booked-banner__items { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
</style>
