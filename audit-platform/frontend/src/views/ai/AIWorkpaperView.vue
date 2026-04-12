<template>
  <AIWorkpaperFill :project-id="currentProjectId" />
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AIWorkpaperFill from '@/components/ai/AIWorkpaperFill.vue'

const route = useRoute()
const currentProjectId = computed(() => route.params.projectId || null)
</script>
