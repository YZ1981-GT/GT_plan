<template>
  <span
    class="gt-measure-cell"
    :class="cssClass"
    :data-gt-value="rawValue"
    :data-measure-kind="kind || 'unknown'"
    :data-ratio-scale="ratioScale || undefined"
    @click="onClick"
  >{{ formatted }}</span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { formatMeasure, measureRawValue, measureSupportsHighlight } from '@/utils/displayMeasure'
import type { DisplayMeasureKind, RatioScale } from '@/types/displayMeasure'

const props = withDefaults(defineProps<{
  value: unknown
  kind?: DisplayMeasureKind | null
  ratioScale?: RatioScale | null
  priorValue?: unknown
  clickable?: boolean
}>(), { kind: null, ratioScale: null, priorValue: undefined, clickable: false })

const emit = defineEmits<{ click: [value: unknown] }>()
const prefs = useDisplayPrefsStore()

const formatted = computed(() => formatMeasure(props.value, {
  amountUnit: prefs.amountUnit,
  decimals: prefs.decimals,
  showZero: prefs.showZero,
  kind: props.kind,
  ratioScale: props.ratioScale,
}))
const rawValue = computed(() => props.kind === 'text' ? String(props.value ?? '') : measureRawValue(props.value))
const cssClass = computed(() => {
  const classes: string[] = []
  const number = Number(props.value)
  if (props.clickable) classes.push('gt-measure-cell--clickable')
  if (props.kind !== 'text' && prefs.negativeRed && Number.isFinite(number) && number < 0) {
    classes.push('gt-amount--negative')
  }
  if (measureSupportsHighlight(props.kind)) {
    classes.push(...prefs.amountClass(props.value, props.priorValue).split(' ').filter(Boolean))
  }
  return classes
})
function onClick(): void {
  if (props.clickable) emit('click', props.value)
}
</script>

<style scoped>
.gt-measure-cell {
  display: inline-block;
  padding: 2px 8px;
  white-space: nowrap;
  color: var(--gt-color-text-regular);
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  font-size: inherit;
}
.gt-measure-cell--clickable { cursor: pointer; color: var(--gt-color-text-primary); font-weight: 500; }
.gt-measure-cell--clickable:hover { color: var(--gt-color-primary, #4b2d77); }
</style>
