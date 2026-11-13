<template>
  <div>
    <!-- No violation: GtAmountCell without :unit -->
    <GtAmountCell :value="row.amount" />
  </div>
</template>
<script setup lang="ts">
const row = { amount: 10000 }
</script>
