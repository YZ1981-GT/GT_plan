<template>
  <div>
    <!-- Violation b: amount formatter applied to a quantity field -->
    <GtAmountCell :value="row.quantity" />
  </div>
</template>
<script setup lang="ts">
const row = { quantity: 500 }
</script>
