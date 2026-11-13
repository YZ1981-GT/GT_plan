<template>
  <el-table :data="data">
    <el-table-column prop="name" label="名称" align="left">
      <template #default="{ row }">
        {{ row.name }}
      </template>
    </el-table-column>
  </el-table>
</template>
<script setup lang="ts">
const data = []
</script>
