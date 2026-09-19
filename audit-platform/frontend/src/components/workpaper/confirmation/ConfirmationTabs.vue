<template>
  <el-tabs
    type="card"
    :model-value="activeTab"
    @update:model-value="(v) => $emit('update:activeTab', v)"
  >
    <el-tab-pane label="全部" name="" />
    <el-tab-pane v-for="tab in tabs" :key="tab" :label="tab" :name="tab" />
  </el-tabs>
</template>

<script setup lang="ts">
defineProps<{
  tabs: string[]
  activeTab: string
}>()

defineEmits<{
  (e: 'update:activeTab', tab: string): void
}>()
</script>
