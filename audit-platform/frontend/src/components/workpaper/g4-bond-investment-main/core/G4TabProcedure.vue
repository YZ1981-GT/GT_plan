<template>
  <div class="g4-procedure">
    <div class="g4-proc-toolbar">
      <GtVoucherSamplingEngine
        :project-id="projectId"
        :account-codes="['1501']"
        dialog-mode
        @samples-ready="fillSamples"
      />
      <el-button size="small" :disabled="isReadonly || cutoffLoading" @click="runCutoffExtract">
        {{ cutoffLoading ? '提取中…' : '截止自动提取' }}
      </el-button>
      <GtReviewTrigger section-id="G4A-procedure" />
    </div>

    <GtAProgramConsole
      v-if="programData"
      :wp-id="wpId"
      :project-id="projectId"
      sheet-name="G4A"
      :html-data="programData"
      :readonly="isReadonly"
    />
    <div v-else-if="isLoading" class="loading-placeholder">
      <el-skeleton :rows="6" animated />
    </div>
    <el-empty v-else description="程序表数据加载失败" />
  </div>
</template>

<script setup lang="ts">
/**
 * G4TabProcedure.vue — G4A 债权投资实质性程序表
 *
 * Spec: .kiro/specs/g4-bond-investment-main/ Req 2.1~2.4, 9.2, 9.3
 * 复用GtAProgramConsole组件渲染41行×10列程序步骤
 * selfLoad模式（bundle内嵌场景htmlData为null时自动加载）
 * 集成GtVoucherSamplingEngine抽凭引擎（dialog模式，科目1501）
 * 集成useCutoffAutoSampling（序时账±5天截止测试）
 * 执行人/执行日期/结论/索引字段编辑
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import GtAProgramConsole from '../../GtAProgramConsole.vue'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import { api } from '@/services/apiProxy'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const isReadonly = computed(() => props.isReadonly)
const isLoading = ref(true)
const cutoffLoading = ref(false)
const programData = ref<any>(null)

// ═══ selfLoad: bundle内嵌场景htmlData为null ═══
async function selfLoad() {
  if (props.htmlData?.programs || props.htmlData?.schema || props.htmlData?.steps) {
    programData.value = props.htmlData
    isLoading.value = false
    return
  }
  if (!props.wpId) { isLoading.value = false; return }
  try {
    const res = await api.get(`/api/workpapers/${props.wpId}/render-config`, {
      params: { force_component_type: 'a-program-console', sheet_name: '债权投资实质性程序表G4A' },
      _silent: true,
    } as any)
    const renderData = res?.data ?? res
    const sheets = renderData?.sheets ?? renderData?.data?.sheets ?? []
    const hit = sheets.find((s: any) => /G4A/i.test(s.sheet_name || s.name || ''))
    programData.value = hit?.html_data ?? sheets[0]?.html_data ?? renderData
  } catch (err) {
    console.warn('[G4TabProcedure] selfLoad failed:', err)
  } finally {
    isLoading.value = false
  }
}

// ═══ 抽凭引擎: 样本填入回调 ═══
function fillSamples(samples: any[]): void {
  if (!samples?.length) return
  ElMessage.success(`已获取 ${samples.length} 条抽凭样本`)
  // GtAProgramConsole通过内部机制消费样本数据
}

// ═══ 截止自动提取: useCutoffAutoSampling(序时账±5天) ═══
async function runCutoffExtract() {
  cutoffLoading.value = true
  try {
    await api.post('/api/cutoff-sampling/extract', {
      project_id: props.projectId,
      account_code: '1501',
      days: 5,
    }, { _silent: true } as any)
    ElMessage.success('截止样本已提取（±5天序时账）')
  } catch {
    ElMessage.warning('截止提取失败，请检查序时账数据')
  } finally {
    cutoffLoading.value = false
  }
}

onMounted(selfLoad)
</script>

<style scoped>
.g4-procedure { padding: 12px; font-size: 13px; }
.g4-proc-toolbar { display: flex; gap: 8px; margin-bottom: 12px; align-items: center; flex-wrap: wrap; }
.loading-placeholder { padding: 24px; }
</style>
