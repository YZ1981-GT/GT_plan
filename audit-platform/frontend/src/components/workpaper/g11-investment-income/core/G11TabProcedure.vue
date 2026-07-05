<template>
  <div class="g11-procedure">
    <div class="g11-proc-toolbar">
      <GtVoucherSamplingEngine :project-id="projectId" :account-codes="[G11_ACCOUNT_CODE]" dialog-mode />
      <GtReviewTrigger section-id="G11A-procedure" />
    </div>
    <GCycleProcedureCutoffPanel
      :wp-id="wpId"
      :project-id="projectId"
      :account-code="G11_ACCOUNT_CODE"
      cycle="g11"
      :is-readonly="isReadonly"
    />
    <GtAProgramConsole
      v-if="programData"
      :wp-id="wpId"
      :project-id="projectId"
      sheet-name="G11A"
      :html-data="programData"
      :readonly="isReadonly"
    />
    <div v-else-if="isLoading" class="loading-placeholder"><el-skeleton :rows="6" animated /></div>
    <el-empty v-else description="程序表数据加载失败" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import GtAProgramConsole from '../../GtAProgramConsole.vue'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GCycleProcedureCutoffPanel from '../../shared/GCycleProcedureCutoffPanel.vue'
import { G11_ACCOUNT_CODE } from '../../composables/g11Constants'
import { api } from '@/services/apiProxy'

const props = defineProps<{
  htmlData?: any
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const isLoading = ref(true)
const programData = ref<any>(null)

async function selfLoad() {
  if (props.htmlData?.programs || props.htmlData?.schema) {
    programData.value = props.htmlData
    isLoading.value = false
    return
  }
  if (!props.wpId) { isLoading.value = false; return }
  try {
    const res = await api.get(`/api/workpapers/${props.wpId}/render-config`, {
      params: { force_component_type: 'g11-investment-income', sheet_name: '投资收益实质性程序表G11A' },
      _silent: true,
    } as any)
    const data = res?.data ?? res
    programData.value = data?.html_data ?? data?.sheets?.[0]?.html_data ?? data
  } catch { /* fallback empty */ }
  finally { isLoading.value = false }
}

onMounted(() => void selfLoad())
</script>

<style scoped>
.g11-procedure { font-size: 13px; }
.g11-proc-toolbar { display: flex; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.loading-placeholder { padding: 16px; }
</style>
