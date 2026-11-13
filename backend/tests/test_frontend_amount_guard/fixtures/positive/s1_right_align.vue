<template>
  <el-table :data="data">
    <el-table-column prop="account_name" label="科目名称" />
    <el-table-column prop="amount" label="金额" align="right">
      <template #default="{ row }">
        {{ row.amount }}
      </template>
    </el-table-column>
  </el-table>
</template>
<script setup lang="ts">
const data = []
</script>
