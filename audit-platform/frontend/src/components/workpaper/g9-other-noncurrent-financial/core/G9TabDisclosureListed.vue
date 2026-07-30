<template>
  <!-- 审计目标/编制提示/金额表 由 G9TabDisclosureBase 按 variant=listed 统一渲染 -->
  <G9TabDisclosureBase variant="listed" v-bind="$props" @imported="emit('imported')" />
</template>

<script setup lang="ts">
import G9TabDisclosureBase from './G9TabDisclosureBase.vue'
import type { ChecklistResponse } from '../../composables/useF1FormData'

// 🔴 projectId / applicableStandards 必须在薄壳上声明：`v-bind="$props"` 只转发
//    **已声明**的 prop，漏声明会让 Base 的同步按钮永久 disabled（props.projectId=undefined）
defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId?: string
  applicableStandards?: string[]
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()
</script>
