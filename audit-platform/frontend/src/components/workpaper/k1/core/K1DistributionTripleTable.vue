<!-- K1-1 账龄/性质分布 — 宽表三区块（原值/坏账/净值） -->
<template>
  <div class="dist-triple">
    <p v-if="subTitle" class="sub-title">{{ subTitle }}</p>
    <p class="block-label">（一）原值</p>
    <K1AdjWideTable
      :rows="grossDisplay"
      :prefix="grossPrefix"
      :is-readonly="isReadonly"
      @field-change="onWideChange"
    />
    <p class="block-label mt-block">（二）坏账准备</p>
    <K1AdjWideTable
      :rows="provDisplay"
      :prefix="provPrefix"
      :is-readonly="isReadonly"
      @field-change="onWideChange"
    />
    <p class="block-label mt-block">（三）净值</p>
    <K1AdjWideTable
      :rows="netDisplay"
      :prefix="netPrefix"
      :is-readonly="true"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { K1AdjBlockSection, K1AdjRow } from '../../composables/useK1Adjudication'
import K1AdjWideTable from './K1AdjWideTable.vue'

const props = defineProps<{
  block: K1AdjBlockSection
  isReadonly: boolean
  grossPrefix: string
  provPrefix: string
  subTitle?: string
}>()

const emit = defineEmits<{
  (e: 'field-change', payload: { prefix: string; rowKey: string; field: string; value: string | number }): void
}>()

const netPrefix = computed(() => props.grossPrefix.replace('gross', 'net'))

function withSubtotal(rows: K1AdjRow[], sub: K1AdjRow): K1AdjRow[] {
  return [...rows, { ...sub, label: '小计' }]
}

const grossDisplay = computed(() => withSubtotal(props.block.grossRows, props.block.grossSubtotal))
const provDisplay = computed(() => withSubtotal(props.block.provisionRows, props.block.provisionSubtotal))
const netDisplay = computed(() => withSubtotal(props.block.netRows, props.block.netSubtotal))

function onWideChange(payload: { prefix: string; rowKey: string; field: string; value: string | number }) {
  if (payload.field === 'aje' || payload.field === 'rje') {
    emit('field-change', {
      prefix: payload.prefix,
      rowKey: payload.rowKey,
      field: payload.field,
      value: Number(payload.value) || 0,
    })
    return
  }
  emit('field-change', payload)
}
</script>

<style scoped>
.dist-triple { font-size: var(--wp-font-size, 13px); }
.sub-title { font-size: 12px; color: var(--el-text-color-secondary); margin: 0 0 8px; }
.block-label { font-size: 12px; font-weight: 600; margin: 0 0 6px; color: var(--el-text-color-regular); }
.mt-block { margin-top: 12px; }
</style>
