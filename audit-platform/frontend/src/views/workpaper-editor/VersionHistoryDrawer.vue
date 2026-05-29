<template>
  <el-drawer
    :model-value="visible"
    title="版本历史"
    direction="rtl"
    size="420px"
    @update:model-value="$emit('update:visible', $event)"
  >
    <!-- S-4 历史版本搜索 -->
    <VersionHistorySearch
      v-if="visible && wpId"
      :wp-id="wpId"
      style="margin-bottom: 16px"
      @jump="onVersionSearchJump"
    />
    <el-divider style="margin: 8px 0" />
    <div v-loading="versionLoading">
      <el-empty v-if="!versionLoading && versionList.length === 0" description="暂无历史版本" />
      <el-timeline v-else>
        <el-timeline-item
          v-for="v in versionList"
          :key="v.version || v.id"
          :timestamp="v.created_at ? v.created_at.slice(0, 19) : ''"
          placement="top"
        >
          <div style="font-weight: 600">v{{ v.version ?? v.file_version ?? '—' }}</div>
          <div v-if="v.note || v.description" style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); margin-top: 4px">
            {{ v.note || v.description }}
          </div>
          <div v-if="v.created_by_name || v.created_by" style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-top: 2px">
            {{ v.created_by_name || v.created_by }}
          </div>
        </el-timeline-item>
      </el-timeline>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { api as httpApi } from '@/services/apiProxy'
import { workpapers as P_wp } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import VersionHistorySearch from '@/components/workpaper/VersionHistorySearch.vue'

const props = defineProps<{
  wpId: string
  visible: boolean
}>()

const emit = defineEmits<{
  'update:visible': [val: boolean]
  'jump': [payload: { versionId: string; sheet: string; cellRef: string }]
}>()

// ─── 版本列表加载 ─────────────────────────────────────────────────────────────
const versionList = ref<any[]>([])
const versionLoading = ref(false)

async function loadVersionHistory() {
  if (!props.wpId) return
  versionLoading.value = true
  try {
    const data = await httpApi.get(P_wp.versions(props.wpId), {
      validateStatus: (s: number) => s < 600,
    })
    versionList.value = Array.isArray(data) ? data : (data?.versions || data?.items || [])
  } catch (e: any) {
    versionList.value = []
    handleApiError(e, '加载版本历史')
  } finally {
    versionLoading.value = false
  }
}

// 抽屉打开时自动加载版本列表
watch(() => props.visible, (val) => {
  if (val) loadVersionHistory()
})

// ─── 历史版本搜索跳转 ─────────────────────────────────────────────────────────
function onVersionSearchJump(payload: { versionId: string; sheet: string; cellRef: string }) {
  if (!payload.cellRef || !props.wpId) return
  emit('jump', payload)
  emit('update:visible', false)
}
</script>
