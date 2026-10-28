import { ref, computed } from 'vue'
import { api } from '@/services/apiProxy'

interface StepMapping {
  step_order: number
  step_name: string
  target_sheets: string[]
  match_level: string
}

interface StepMappingResponse {
  wp_code: string
  primary_code: string
  wp_name: string
  has_template: boolean
  available_sheets: string[]
  steps: StepMapping[]
}

export function useStepMapping(wpId: string) {
  const data = ref<StepMappingResponse | null>(null)
  const loading = ref(false)
  const currentStepIndex = ref(0)

  const currentStep = computed(() => {
    if (!data.value?.steps?.length) return null
    return data.value.steps[currentStepIndex.value] || null
  })

  const currentTargetSheets = computed(() => {
    return currentStep.value?.target_sheets || []
  })

  const totalSteps = computed(() => data.value?.steps?.length || 0)

  async function loadMapping() {
    if (!wpId) return
    loading.value = true
    try {
      // 步骤导航是辅助信息：失败（含无权 / 不存在的底稿 404）只记日志，不弹全局提示（spec procedure-chain-hardening-and-java-contracts R10）
      const res = await api.get(`/api/workpapers/${wpId}/step-mapping`, { _silent: true } as any)
      data.value = res as StepMappingResponse
    } catch (e) {
      console.warn('Failed to load step mapping:', e)
    } finally {
      loading.value = false
    }
  }

  function nextStep() {
    if (currentStepIndex.value < totalSteps.value - 1) {
      currentStepIndex.value++
    }
  }

  function prevStep() {
    if (currentStepIndex.value > 0) {
      currentStepIndex.value--
    }
  }

  function goToStep(index: number) {
    if (index >= 0 && index < totalSteps.value) {
      currentStepIndex.value = index
    }
  }

  return {
    data,
    loading,
    currentStepIndex,
    currentStep,
    currentTargetSheets,
    totalSteps,
    loadMapping,
    nextStep,
    prevStep,
    goToStep,
  }
}
