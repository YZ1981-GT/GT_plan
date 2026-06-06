<template>
  <div v-if="visible" class="draft-watermark" aria-hidden="true">
    <span class="draft-watermark__text">草稿 DRAFT</span>
  </div>
</template>

<script setup lang="ts">
defineProps<{ visible: boolean }>()
</script>

<style scoped>
.draft-watermark {
  position: absolute;
  inset: 0;
  pointer-events: none;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2;
  overflow: hidden;
}
.draft-watermark__text {
  font-size: 72px;
  font-weight: 700;
  color: rgba(200, 0, 0, 0.12);
  transform: rotate(-30deg);
  user-select: none;
  white-space: nowrap;
}
</style>
