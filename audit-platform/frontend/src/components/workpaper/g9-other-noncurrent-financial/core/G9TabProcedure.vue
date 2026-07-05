<template>
  <div class="g9-procedure" data-testid="g9-procedure">
    <div class="toolbar">
      <GtVoucherSamplingEngine :project-id="projectId" :account-codes="[G9_ACCOUNT_CODE]" dialog-mode />
      <GtReviewTrigger section-id="G9A-procedure" />
    </div>
    <GCycleProcedureCutoffPanel
      :wp-id="wpId"
      :project-id="projectId"
      :account-code="G9_ACCOUNT_CODE"
      cycle="g9"
      :is-readonly="isReadonly"
    />
    <GtAProgramConsole
      v-if="programData"
      :wp-id="wpId"
      :project-id="projectId"
      sheet-name="G9A"
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
import { G9_ACCOUNT_CODE } from '../../composables/g9Constants'
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
      params: { force_component_type: 'g9-other-noncurrent-financial', sheet_name: '其他非流动金融资产实质性程序表G9A' },
      _silent: true,
    } as any)
    programData.value = res?.data?.html_data ?? res?.html_data ?? res
  } finally {
    isLoading.value = false
  }
})
</script>

<style scoped>
.g9-procedure { font-size: 13px; }
.toolbar { display: flex; gap: 8px; margin-bottom: 8px; }
</style>
