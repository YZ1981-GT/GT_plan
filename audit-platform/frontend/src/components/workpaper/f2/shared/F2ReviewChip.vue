<template>
  <el-button
    v-if="openReview"
    size="small"
    link
    type="primary"
    @click="openReview(sectionId)"
  >
    复核
  </el-button>
</template>

<script setup lang="ts">
import { inject } from 'vue'

defineProps<{ sectionId: string }>()

const openReview = inject<((sectionId: string) => void) | null>('openReviewDialog', null)
</script>
