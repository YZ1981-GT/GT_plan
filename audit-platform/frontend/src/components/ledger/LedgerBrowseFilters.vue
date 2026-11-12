<template>
  <el-input
    :model-value="keyword"
    clearable
    size="small"
    :placeholder="placeholder"
    style="width: 220px"
    @update:model-value="emit('update:keyword', $event)"
    @keyup.enter="emit('search')"
    @clear="emit('search')"
  />
  <el-select
    :model-value="amountDir"
    size="small"
    style="width: 110px"
    @update:model-value="emit('update:amountDir', $event)"
    @change="emit('search')"
  >
    <el-option label="借贷全部" value="all" />
    <el-option label="仅借方" value="debit" />
    <el-option label="仅贷方" value="credit" />
  </el-select>
</template>

<script setup lang="ts">
/** 序时账 / 辅助明细账共用的关键字 + 借贷方向筛选（改动后由父组件重新查询） */
defineProps<{
  keyword: string
  amountDir: 'all' | 'debit' | 'credit'
  placeholder: string
}>()
const emit = defineEmits<{
  (e: 'update:keyword', v: string): void
  (e: 'update:amountDir', v: 'all' | 'debit' | 'credit'): void
  (e: 'search'): void
}>()
</script>
