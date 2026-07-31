<template>
  <WpDisclosureConsistencyPanel
    :results="results"
    :project-id="projectId"
    :default-expanded="defaultExpanded"
  />
</template>

<script setup lang="ts">
/**
 * @deprecated 面板已提升为平台共用
 * `shared/disclosure/WpDisclosureConsistencyPanel.vue`
 * （spec `n-cycle-tax-disclosure-alignment` Task 2.2）。
 *
 * 保留为**透传薄壳**让 N1 既有引用零回归；新代码请直接用 Wp 版本。
 * 🔴 薄壳必须逐个声明 prop（`v-bind="$props"` 只转发已声明的 prop）。
 */
import WpDisclosureConsistencyPanel from '../../shared/disclosure/WpDisclosureConsistencyPanel.vue'
import type { N1CheckResult } from '../../composables/n1DisclosureConsistency'

withDefaults(
  defineProps<{
    results: N1CheckResult[]
    projectId: string
    defaultExpanded?: boolean
  }>(),
  { defaultExpanded: false },
)
</script>
