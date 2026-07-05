<template>

  <div class="g14-procedure">

    <div class="g14-proc-toolbar">

      <GtVoucherSamplingEngine

        :project-id="projectId"

        :account-codes="[G14_ACCOUNT_CODE]"

        dialog-mode

      />

      <GtReviewTrigger section-id="G14A-procedure" />

    </div>



    <GCycleProcedureCutoffPanel
      :wp-id="wpId"
      :project-id="projectId"
      :account-code="G14_ACCOUNT_CODE"
      cycle="g14"
      :is-readonly="isReadonly"
    />



    <GtAProgramConsole

      v-if="programData"

      :wp-id="wpId"

      :project-id="projectId"

      sheet-name="G14A"

      :html-data="programData"

      :readonly="isReadonly"

    />

    <div v-else-if="isLoading" class="loading-placeholder"><el-skeleton :rows="6" animated /></div>

    <el-empty v-else description="程序表数据加载失败" />

  </div>

</template>



<script setup lang="ts">

import { ref, onMounted } from 'vue'

import GtAProgramConsole from '../GtAProgramConsole.vue'

import GtVoucherSamplingEngine from '../voucher-sampling/GtVoucherSamplingEngine.vue'

import GtReviewTrigger from '../GtReviewTrigger.vue'

import GCycleProcedureCutoffPanel from '../shared/GCycleProcedureCutoffPanel.vue'

import { G14_ACCOUNT_CODE } from '../composables/g14Constants'

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

  if (!props.wpId) {

    isLoading.value = false

    return

  }

  try {

    const res = await api.get(`/api/workpapers/${props.wpId}/render-config`, {

      params: { force_component_type: 'a-program-console', sheet_name: '信用减值损失审计程序表G14A' },

      _silent: true,

    } as any)

    const renderData = res?.data ?? res

    const sheets = renderData?.sheets ?? renderData?.data?.sheets ?? []

    const hit = sheets.find((s: any) => /G14A/i.test(s.sheet_name || s.name || ''))

    programData.value = hit?.html_data ?? sheets[0]?.html_data ?? renderData

  } catch (err) {

    console.warn('[G14TabProcedure] selfLoad failed:', err)

  } finally {

    isLoading.value = false

  }

}



onMounted(selfLoad)

</script>



<style scoped>

.g14-procedure { padding: 12px; font-size: 13px; }

.g14-proc-toolbar { display: flex; gap: 8px; margin-bottom: 12px; align-items: center; flex-wrap: wrap; }

.loading-placeholder { padding: 24px; }

</style>


