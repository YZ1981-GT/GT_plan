<template>
  <div>
    <span>{{ name }}</span>
    <span>{{ status.toString() }}</span>
  </div>
</template>
<script setup lang="ts">
const name = 'test'
const status = 'active'
</script>
