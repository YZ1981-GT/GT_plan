<template>
  <div class="gt-confirmation-hub gt-fade-in">
    <GtPageHeader title="函证管理" :show-back="false" />
    <GtEmpty preset="developing" />
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
