<script setup lang="ts">
/**
 * 循环底稿程序表（*A）统一壳 — 复用 GtAProgramConsole 中控台样式
 */
import { computed, toRef } from 'vue'
import GtAProgramConsole from '../GtAProgramConsole.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import { useCycleProcedureConsole } from '../composables/useCycleProcedureConsole'

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: any
  isReadonly?: boolean
  readonly?: boolean
  sheetCode: string
  sheetLabel: string
  reviewSectionId: string
  rootClass?: string
}>()

const isReadonly = computed(() => props.isReadonly ?? props.readonly ?? false)

const { isLoading, programData } = useCycleProcedureConsole({
  wpId: toRef(props, 'wpId'),
  htmlData: toRef(props, 'htmlData'),
  sheetLabel: props.sheetLabel,
  sheetCode: props.sheetCode,
})
</script>

<template>
  <div :class="rootClass ?? 'cycle-program-console-tab'">
    <div class="cycle-proc-toolbar">
      <slot name="toolbar" />
      <GtReviewTrigger :section-id="reviewSectionId" />
    </div>

    <GtAProgramConsole
      v-if="programData"
      :wp-id="wpId"
      :project-id="projectId"
      :sheet-name="sheetCode"
      :html-data="programData"
      :readonly="isReadonly"
    />
    <div v-else-if="isLoading" class="loading-placeholder">
      <el-skeleton :rows="6" animated />
    </div>
    <el-empty v-else description="程序表数据加载失败" />
  </div>
</template>

<style scoped>
.cycle-program-console-tab,
.d1-tab-procedure,
.d2-tab-procedure,
.d3-tab-procedure,
.d4-tab-procedure,
.d5-tab-procedure,
.d6-tab-procedure,
.d7-tab-procedure {
  padding: 12px;
  font-size: 13px;
}

.cycle-proc-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.loading-placeholder {
  padding: 24px;
}
</style>
