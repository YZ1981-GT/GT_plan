<template>
  <div class="g5-procedure">
    <div class="g5-proc-toolbar">
      <GtVoucherSamplingEngine :project-id="projectId" :account-codes="[G5_ACCOUNT_CODE]" dialog-mode />
      <el-button size="small" :disabled="isReadonly || cutoffLoading" @click="runCutoffExtract">
        {{ cutoffLoading ? '提取中…' : '截止自动提取' }}
      </el-button>
      <GtReviewTrigger section-id="G5A-procedure" />
    </div>

    <GtAProgramConsole
      v-if="programData"
      :wp-id="wpId"
      :project-id="projectId"
      sheet-name="G5A"
      :html-data="programData"
      :readonly="isReadonly"
    />
    <div v-else-if="isLoading" class="loading-placeholder"><el-skeleton :rows="6" animated /></div>
    <el-empty v-else description="程序表数据加载失败" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import GtAProgramConsole from '../../GtAProgramConsole.vue'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import { G5_ACCOUNT_CODE } from '../../composables/g5Constants'
import { api } from '@/services/apiProxy'

const props = defineProps<{
  htmlData?: any
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const isReadonly = computed(() => !!props.readonly)
const isLoading = ref(true)
const cutoffLoading = ref(false)
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
      params: { force_component_type: 'a-program-console', sheet_name: '长期应收款审计程序表G5A' },
      _silent: true,
    } as any)
    const renderData = res?.data ?? res
    const sheets = renderData?.sheets ?? renderData?.data?.sheets ?? []
    const hit = sheets.find((s: any) => /G5A/i.test(s.sheet_name || s.name || ''))
    programData.value = hit?.html_data ?? sheets[0]?.html_data ?? renderData
  } catch (err) {
    console.warn('[G5TabProcedure] selfLoad failed:', err)
  } finally {
    isLoading.value = false
  }
}

async function runCutoffExtract() {
  cutoffLoading.value = true
  try {
    await api.post('/api/cutoff-sampling/extract', {
      project_id: props.projectId,
      account_code: G5_ACCOUNT_CODE,
      days: 5,
    }, { _silent: true } as any)
    ElMessage.success('截止样本已提取')
  } catch {
    ElMessage.warning('截止提取失败，请检查序时账数据')
  } finally {
    cutoffLoading.value = false
  }
}

onMounted(selfLoad)
</script>

<style scoped>
.g5-procedure { padding: 12px; font-size: 13px; }
.g5-proc-toolbar { display: flex; gap: 8px; margin-bottom: 12px; align-items: center; flex-wrap: wrap; }
.loading-placeholder { padding: 24px; }
</style>
