<script setup lang="ts">
defineProps<{ wpCode: string; wpId?: string; projectId?: string }>()
defineEmits<{ (e: 'save'): void; (e: 'completed'): void }>()
</script>
<template>
  <div class="wp-popup-stub"><p>WpPopupChecklist（待实现）</p></div>
</template>
<style scoped>.wp-popup-stub { padding: 16px; }</style>
