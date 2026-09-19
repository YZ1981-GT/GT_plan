<!--
  WorkpaperPrimaryCapabilitiesHost — purple-toolbar primary named outlet (Task 5).

  Mount after AI助手 and before 金额单位. Registers with ToolbarOutletArbiter.
  CSS classes are styling only; the real capability is the named slot + data attribute.
-->
<template>
  <span
    ref="outletEl"
    class="gt-page-capabilities-primary-host"
    data-toolbar-outlet="page-capabilities-primary"
    data-testid="page-capabilities-primary"
  >
    <slot name="page-capabilities-primary" />
  </span>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { PRIMARY_OUTLET_SLOT } from '@/shell/formula/outletSlots'
import {
  getToolbarOutletArbiter,
} from '@/shell/formula/toolbarOutletArbiter'

const props = defineProps<{
  hostInstanceId: string
  ownerEpoch: number
}>()

const outletEl = ref<HTMLElement | null>(null)
const arbiter = getToolbarOutletArbiter()

function register(): void {
  const el = outletEl.value
  if (!el) return
  arbiter.beginCycle(props.ownerEpoch)
  arbiter.register({
    hostInstanceId: props.hostInstanceId,
    ownerEpoch: props.ownerEpoch,
    kind: 'primary',
    outletElement: el,
    namedSlot: PRIMARY_OUTLET_SLOT,
  })
  arbiter.settle()
}

onMounted(register)
watch(() => props.ownerEpoch, register)

onBeforeUnmount(() => {
  arbiter.unregister(props.hostInstanceId, props.ownerEpoch)
})
</script>

<style scoped>
.gt-page-capabilities-primary-host {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
</style>
