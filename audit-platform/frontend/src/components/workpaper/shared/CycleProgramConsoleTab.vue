<script setup lang="ts">

/**

 * 循环底稿程序表（*A）统一壳 — 对齐 D4A：仅 GtAProgramConsole，无复核/抽凭 toolbar

 */

import { computed, toRef } from 'vue'

import GtAProgramConsole from '../GtAProgramConsole.vue'

import { useCycleProcedureConsole } from '../composables/useCycleProcedureConsole'



const props = defineProps<{

  wpId: string

  projectId: string

  htmlData?: any

  isReadonly?: boolean

  readonly?: boolean

  sheetCode: string

  sheetLabel: string

  /** @deprecated 复核在底稿页眉统一入口，程序控制台不再展示 */

  reviewSectionId?: string

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

    <div v-if="$slots.toolbar" class="cycle-proc-toolbar">

      <slot name="toolbar" />

    </div>



    <GtAProgramConsole

      v-if="programData"

      :wp-id="wpId"

      :project-id="projectId"

      :sheet-name="sheetCode"

      :html-data="programData"

      :readonly="isReadonly"

      cycle-sheet-mode

      hide-categories

    />

    <div v-else-if="isLoading" class="loading-placeholder">

      <el-skeleton :rows="6" animated />

    </div>

    <el-empty v-else description="程序表数据加载失败" />

  </div>

</template>



<style scoped>

.cycle-program-console-tab,

[class*='-tab-procedure'] {

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


