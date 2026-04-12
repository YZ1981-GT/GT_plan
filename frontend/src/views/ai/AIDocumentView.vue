<template>
  <AIDocumentOCR :project-id="currentProjectId" />
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AIDocumentOCR from '@/components/ai/AIDocumentOCR.vue'

const route = useRoute()
const currentProjectId = computed(() => route.query.project_id || localStorage.getItem('current_project_id') || '')
</script>
