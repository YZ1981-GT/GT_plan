<template>
  <div class="f2-sheet-toolbar">
    <slot />
    <CycleImportExportDropdown
      v-if="wpId && showImportExport"
      :wp-id="wpId"
      :api-prefix="apiPrefix"
      :sheet="sheet"
      :disabled="disabled"
      @imported="onImported"
    />
    <el-button
      v-if="aiSection && wpId"
      size="small"
      type="primary"
      plain
      :disabled="disabled || !aiAvailable"
      :loading="aiLoading"
      @click="runAi"
    >
      AI 生成
    </el-button>
    <F2ReviewChip v-if="reviewSection" :section-id="reviewSection" />
  </div>
</template>

<script setup lang="ts">
import { computed, inject, toRef, type Ref } from 'vue'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
import F2ReviewChip from './F2ReviewChip.vue'
import { useF2AiGenerate, type F2AiSection } from '../../composables/useF2AiGenerate'
import { useF2ValuationAiGenerate, type F2ValAiSection } from '../../composables/useF2ValuationAiGenerate'
import { useF2SpecialAiGenerate, type F2SpeAiSection } from '../../composables/useF2SpecialAiGenerate'
import { useF2StocktakeAiGenerate, type F2StAiSection } from '../../composables/useF2StocktakeAiGenerate'

const props = withDefaults(defineProps<{
  wpId?: string
  apiPrefix: 'f2-val' | 'f2-spe' | 'f2' | 'f2-st'
  sheet: string
  disabled?: boolean
  aiSection?: F2AiSection | F2ValAiSection | F2SpeAiSection | F2StAiSection
  existingContent?: string
  relatedContext?: Record<string, unknown>
  aiTitle?: string
  reviewSection?: string
  showImportExport?: boolean
  projectId?: string
}>(), {
  showImportExport: true,
})

const emit = defineEmits<{ aiFilled: [text: string]; imported: [] }>()

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)

async function onImported() {
  await reloadWorkpaperData?.()
  emit('imported')
}

const wpIdRef = toRef(() => props.wpId || '') as Ref<string>
const mainAi = useF2AiGenerate(wpIdRef)
const valAi = useF2ValuationAiGenerate(wpIdRef)
const speAi = useF2SpecialAiGenerate(wpIdRef)
const stAi = useF2StocktakeAiGenerate({
  wpId: wpIdRef,
  projectId: toRef(() => props.projectId || '') as Ref<string>,
})

const aiAvailable = computed(() => {
  if (props.apiPrefix === 'f2') return mainAi.aiAvailable.value
  if (props.apiPrefix === 'f2-spe') return speAi.aiAvailable.value
  if (props.apiPrefix === 'f2-st') return stAi.aiAvailable.value
  return valAi.aiAvailable.value
})

const aiLoading = computed(() => {
  if (props.apiPrefix === 'f2') return mainAi.loading.value
  if (props.apiPrefix === 'f2-spe') return speAi.loading.value
  if (props.apiPrefix === 'f2-st') return stAi.loading.value
  return valAi.loading.value
})

async function runAi() {
  if (!props.aiSection) return
  let text: string | null = null
  if (props.apiPrefix === 'f2') {
    text = await mainAi.generateAndConfirm(
      props.aiSection as F2AiSection,
      props.existingContent || '',
      props.relatedContext || {},
      props.aiTitle || 'AI 生成',
    )
  } else if (props.apiPrefix === 'f2-spe') {
    text = await speAi.generateAndConfirm(
      props.aiSection as F2SpeAiSection,
      props.existingContent || '',
      props.relatedContext || {},
      props.aiTitle || 'AI 生成',
    )
  } else if (props.apiPrefix === 'f2-st') {
    text = await stAi.generateAndConfirm(
      props.aiSection as F2StAiSection,
      props.existingContent || '',
      props.relatedContext || {},
      props.aiTitle || 'AI 生成',
    )
  } else {
    text = await valAi.generateAndConfirm(
      props.aiSection as F2ValAiSection,
      props.existingContent || '',
      props.relatedContext || {},
      props.aiTitle || 'AI 生成',
    )
  }
  if (text) emit('aiFilled', text)
}
</script>

<style scoped>
.f2-sheet-toolbar { display: inline-flex; gap: 8px; align-items: center; flex-wrap: wrap; }
</style>
