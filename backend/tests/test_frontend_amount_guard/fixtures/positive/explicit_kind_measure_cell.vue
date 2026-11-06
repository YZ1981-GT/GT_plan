<template>
  <div>
    <!-- Explicit kind via GtMeasureCell: NOT a candidate -->
    <GtMeasureCell kind="ratio" :value="0.2" ratio-scale="fraction" />
    <GtMeasureCell :kind="col.measureKind" :value="row.qty" />
  </div>
</template>
<script setup lang="ts">
const col = { measureKind: 'quantity' }
const row = { qty: 100 }
</script>
