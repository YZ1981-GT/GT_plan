<template>
  <div class="g10-procedure">
    <div class="toolbar">
      <GtVoucherSamplingEngine :project-id="projectId" :account-codes="[G10_ACCOUNT_CODE]" dialog-mode />
      <GtReviewTrigger section-id="G10A-procedure" />
    </div>
    <GCycleProcedureCutoffPanel
      :wp-id="wpId"
      :project-id="projectId"
      :account-code="G10_ACCOUNT_CODE"
      cycle="g10"
      :is-readonly="isReadonly"
    />
    <GtAProgramConsole
      v-if="programData"
      :wp-id="wpId"
      :project-id="projectId"
      sheet-name="G10A"
      :html-data="programData"
      :readonly="isReadonly"
    />
    <el-skeleton v-else-if="isLoading" :rows="6" animated />
    <el-empty v-else description="程序表加载失败" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import GtAProgramConsole from '../../GtAProgramConsole.vue'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GCycleProcedureCutoffPanel from '../../shared/GCycleProcedureCutoffPanel.vue'
import { G10_ACCOUNT_CODE } from '../../composables/g10Constants'
import { api } from '@/services/apiProxy'

const props = defineProps<{ htmlData?: any; wpId: string; projectId: string; isReadonly: boolean }>()

const isLoading = ref(true)
const programData = ref<any>(null)

onMounted(async () => {
  if (props.htmlData?.programs) {
    programData.value = props.htmlData
    isLoading.value = false
    return
  }
  try {
    const res = await api.get(`/api/workpapers/${props.wpId}/render-config`, {
      params: { force_component_type: 'g10-trading-financial-liabilities', sheet_name: '交易性金融负债实质性程序表G10A' },
      _silent: true,
    } as any)
    const d = res?.data ?? res
    programData.value = d?.sheets?.[0]?.html_data ?? d?.html_data ?? d
  } finally {
    isLoading.value = false
  }
})
</script>

<style scoped>
.g10-procedure { padding: 12px; font-size: 13px; }
.toolbar { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
</style>
