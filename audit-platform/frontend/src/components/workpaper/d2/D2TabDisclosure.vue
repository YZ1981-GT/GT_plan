<script setup lang="ts">
/**
 * D2TabDisclosure — D2 应收账款「附注披露」底稿页
 *
 * 结构与附注模块 五、5（上市）/ 八、5（国企）一致；表名/列头以
 * `composables/d2NoteSectionMap.ts` 为唯一真源，可整页（表格 + 说明文本）同步到附注。
 *
 * 本组件为薄壳：顶部版本切换 + 以 :key 挂载渲染体
 * （切换版本需重建，因持久化前缀 `D2-disc-{variant}-` 随之变化）。
 */
import { computed, ref, watch } from 'vue'
import type { D2DisclosureVariant } from '../composables/d2NoteSectionMap'
import type { ChecklistResponse } from '../composables/useD2FormData'
import D2DisclosureNoteBody from './D2DisclosureNoteBody.vue'

const props = withDefaults(defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly?: boolean
  /** 由主入口按当前 sheet 传入（附注国企 → soe），未传默认上市版 */
  variant?: D2DisclosureVariant
  applicableStandards?: string[] | null
}>(), { isReadonly: false, variant: 'listed', applicableStandards: null })

const activeVariant = ref<D2DisclosureVariant>(props.variant)

watch(() => props.variant, (v) => {
  if (v && v !== activeVariant.value) activeVariant.value = v
})

const variantOptions = computed(() => ([
  { label: '上市公司版（五、5）', value: 'listed' },
  { label: '国有企业版（八、5）', value: 'soe' },
]))
</script>

<template>
  <div class="d2-tab-disclosure">
    <div class="d2-tab-disclosure__switch">
      <span class="switch-label">披露版本：</span>
      <el-segmented
        :model-value="activeVariant"
        :options="variantOptions"
        size="small"
        @change="(v: D2DisclosureVariant) => (activeVariant = v)"
      />
    </div>

    <D2DisclosureNoteBody
      :key="activeVariant"
      :variant="activeVariant"
      :wp-id="props.wpId"
      :project-id="props.projectId"
      :all-responses="props.allResponses"
      :is-readonly="props.isReadonly"
      :applicable-standards="props.applicableStandards"
    />
  </div>
</template>

<style scoped>
.d2-tab-disclosure { font-size: 13px; }
.d2-tab-disclosure__switch { display: flex; align-items: center; gap: 8px; padding: 12px 12px 0; }
.switch-label { color: #606266; }
</style>
