<template>
  <div>
    <span>{{ value.toFixed(2) }}</span>
    <span>{{ new Decimal(amount).toString() }}</span>
  </div>
</template>
<script setup lang="ts">
const value = 100
const amount = 200
</script>
