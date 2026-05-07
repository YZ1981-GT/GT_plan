<template>
  <div class="gt-confirmation-hub gt-fade-in">
    <GtPageHeader title="函证管理" :show-back="false" />
    <GtEmpty icon="📮" title="函证管理" description="该模块正在开发中，敬请期待" />
  </div>
</template>

<script setup lang="ts">
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import GtEmpty from '@/components/common/GtEmpty.vue'
</script>

<style scoped>
.gt-confirmation-hub {
  padding: var(--gt-space-4);
}
</style>
