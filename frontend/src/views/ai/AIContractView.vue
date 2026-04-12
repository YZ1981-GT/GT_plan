<template>
  <AIContractAnalysis :project-id="currentProjectId" />
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AIContractAnalysis from '@/components/ai/AIContractAnalysis.vue'

const route = useRoute()
const currentProjectId = computed(() => route.query.project_id || localStorage.getItem('current_project_id') || '')
</script>
