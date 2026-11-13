<template>
  <div>
    <span>{{ fmtDate(row.created_at) }}</span>
  </div>
</template>
<script setup lang="ts">
import { fmtDate } from '@/utils/formatters'
const row = { created_at: '2025-01-01' }
</script>
