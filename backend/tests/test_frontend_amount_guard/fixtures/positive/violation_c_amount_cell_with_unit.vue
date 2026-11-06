<template>
  <div>
    <!-- Violation c: GtAmountCell with :unit binding -->
    <GtAmountCell :value="row.amount" :unit="noteUnit" />
  </div>
</template>
<script setup lang="ts">
const row = { amount: 10000 }
const noteUnit = 'wan'
</script>
