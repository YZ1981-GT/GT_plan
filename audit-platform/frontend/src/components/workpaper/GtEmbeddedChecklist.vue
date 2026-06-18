<script setup lang="ts">
/** 嵌入核对表 — 按 checklist wp_code 拉模板 + 同 wp_id 填写数据 */
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '@/services/apiProxy'
import GtChecklistTable from './GtChecklistTable.vue'

const props = defineProps<{
  wpId: string
  checklistWpCode: string
  readonly?: boolean
}>()

const route = useRoute()
const htmlData = ref<{ template: unknown; responses: Record<string, unknown> } | null>(null)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const pid = route.params.projectId as string
    htmlData.value = await api.get(
      `/api/projects/${pid}/checklist-templates/${props.checklistWpCode}?wp_id=${props.wpId}`,
    )
  } finally {
    loading.value = false
  }
}

watch(() => props.checklistWpCode, load)
onMounted(load)
</script>

<template>
  <div v-loading="loading" class="embedded-checklist">
    <GtChecklistTable
      v-if="htmlData"
      :wp-id="wpId"
      :html-data="htmlData as any"
      :readonly="readonly"
    />
  </div>
</template>
