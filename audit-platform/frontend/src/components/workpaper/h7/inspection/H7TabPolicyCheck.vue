<template>
  <div class="h7-tab-policy-check">
    <el-empty description="H7-4 会计政策检查（CAS5） — 待实现" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
/** H7TabPolicyCheck — H7-4 会计政策 placeholder */
defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  measurementModel?: 'cost' | 'fair_value'
  isReadonly?: boolean
}>()
</script>
