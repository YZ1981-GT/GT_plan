<template>
  <WorkpaperAIFill :project-id="currentProjectId" />
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import WorkpaperAIFill from '@/components/ai/WorkpaperAIFill.vue'

const route = useRoute()
const currentProjectId = computed(() => route.params.projectId || null)
</script>
