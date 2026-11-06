<template>
  <div>
    <span>{{ fmtAmount(row.balance) }}</span>
  </div>
</template>
<script setup lang="ts">
import { fmtAmount } from '@/utils/formatters'
const row = { balance: 10000 }
</script>
