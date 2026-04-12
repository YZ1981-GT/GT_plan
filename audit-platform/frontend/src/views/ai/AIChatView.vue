<template>
  <AIChatPanel :project-id="currentProjectId" />
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AIChatPanel from '@/components/ai/AIChatPanel.vue'

const route = useRoute()
const currentProjectId = computed(() => route.params.projectId || null)
</script>
