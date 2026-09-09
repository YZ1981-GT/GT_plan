<!--
  WorkpaperCapabilityShell — formula-toolbar Task 11/12.

  Unique owner of location/toolbar/dialog/capability/right-rail composition.
  Task 12: responsive tokens, Escape/scroll-lock/return-focus, structured errors.
-->
<template>
  <div
    ref="rootEl"
    class="wp-capability-shell"
    data-testid="workpaper-capability-shell"
    :data-viewport-band="viewportBand"
    :style="cssVars"
    @keydown="onKeydown"
  >
    <div
      v-if="shellError"
      class="wp-capability-shell__error"
      role="alert"
      :aria-label="shellError.zhMessage"
    >
      <strong>{{ shellError.zhMessage }}</strong>
      <span class="wp-capability-shell__error-code">{{ shellError.reasonCode }}</span>
    </div>

    <div class="wp-capability-shell__main">
      <slot />
    </div>

    <aside
      class="wp-capability-shell__rail-strip"
      :aria-label="SHELL_A11Y_NAMES['rail-trigger']"
    >
      <button
        v-for="rail in mountable"
        :key="rail.id"
        type="button"
        class="wp-capability-shell__trigger"
        :class="{ 'is-active': openId === rail.id }"
        :data-rail-id="rail.id"
        :aria-label="rail.a11yName"
        :aria-expanded="openId === rail.id"
        :title="rail.disabledReason || rail.a11yName"
        @click="onTrigger(rail.id, $event)"
      >
        <span class="wp-capability-shell__trigger-text">{{ rail.a11yName }}</span>
      </button>
    </aside>

    <aside
      v-if="openId === 'review'"
      class="wp-capability-shell__panel"
      :aria-label="SHELL_A11Y_NAMES['rail-panel']"
      tabindex="-1"
      ref="panelEl"
    >
      <slot name="review-panel" />
    </aside>

    <aside
      class="wp-capability-shell__panel"
      :class="{ 'is-collapsed': openId !== 'guidance' }"
      :aria-label="SHELL_A11Y_NAMES['rail-panel']"
      :hidden="openId !== 'guidance'"
      tabindex="-1"
    >
      <slot name="guidance-panel" />
    </aside>
  </div>
</template>

<script setup lang="ts">
import {
  computed,
  onBeforeUnmount,
  onMounted,
  provide,
  ref,
  watch,
  type Ref,
} from 'vue'

import type { CanonicalWorkpaperLocation } from '@/shared/contracts/gc0'
import type { GuidanceRailController } from '@/shell/guidance'
import type { WorkpaperCapabilitySnapshot } from '@/shell/formula/workpaperCapabilitySnapshot'
import {
  createAiAssistShellRail,
  createGuidanceShellRail,
  createReviewShellRail,
  getRightRailArbiter,
  type ShellRailAdapter,
  type ShellRailId,
} from '@/shell/formula/rightRailArbiter'
import {
  shellLayoutCssVars,
  type ShellLayoutTokens,
} from '@/shell/formula/shellLayoutTokens'
import {
  classifyShellViewport,
  resolveShellLayoutTokens,
} from '@/shell/formula/shellResponsiveLayout'
import {
  SHELL_A11Y_NAMES,
  acquireShellScrollLock,
  beginShellFocusSession,
  endShellFocusSession,
  handleShellEscapeKey,
  releaseShellScrollLock,
} from '@/shell/formula/shellA11y'
import {
  createShellStructuredError,
  type ShellStructuredError,
} from '@/shell/formula/shellStructuredError'
import { WORKPAPER_SHELL_ACTIVE_KEY } from '@/shell/formula/dshAssistBridge'

const props = withDefaults(defineProps<{
  ownerEpoch: number
  capabilityEpoch: number
  snapshot: WorkpaperCapabilitySnapshot
  location: CanonicalWorkpaperLocation | null
  guidanceController: GuidanceRailController
  reviewHasDraft?: boolean
  openReview?: () => void | Promise<void>
  closeReview?: (options: { preserveDraft: boolean }) => void | Promise<void>
  openDsh?: () => void | Promise<void>
  closeDsh?: (options: { preserveDraft: boolean }) => void | Promise<void>
  layoutTokens?: ShellLayoutTokens
  shellError?: ShellStructuredError | null
}>(), {
  reviewHasDraft: false,
  openReview: async () => undefined,
  closeReview: async () => undefined,
  openDsh: async () => undefined,
  closeDsh: async () => undefined,
  shellError: null,
})

const arbiter = getRightRailArbiter()
const mountable = ref<ShellRailAdapter[]>([])
const openId = ref<ShellRailId | null>(null)
const rootEl = ref<HTMLElement | null>(null)
const viewportWidth = ref(typeof window !== 'undefined' ? window.innerWidth : 1440)
const shellActive: Ref<boolean> = ref(true)
provide(WORKPAPER_SHELL_ACTIVE_KEY, shellActive)

const viewportBand = computed(() => classifyShellViewport(viewportWidth.value))
const resolvedTokens = computed(() =>
  props.layoutTokens
    ?? resolveShellLayoutTokens({ viewportWidthPx: viewportWidth.value }),
)

function refreshView(): void {
  mountable.value = arbiter.mountableTriggers()
  const s = arbiter.getOpenState()
  openId.value = s.status === 'open' ? s.id : null
}

function syncRails(): void {
  arbiter.setEpochs({
    ownerEpoch: props.ownerEpoch,
    capabilityEpoch: props.capabilityEpoch,
  })
  arbiter.register(createReviewShellRail({
    ownerEpoch: props.ownerEpoch,
    capabilityEpoch: props.capabilityEpoch,
    snapshot: props.snapshot,
    hasDraft: props.reviewHasDraft,
    open: () => props.openReview?.(),
    close: (opts) => props.closeReview?.(opts),
  }))
  const guidance = createGuidanceShellRail({
    ownerEpoch: props.ownerEpoch,
    capabilityEpoch: props.capabilityEpoch,
    snapshot: props.snapshot,
    location: props.location,
    controller: props.guidanceController,
  })
  if (guidance) arbiter.register(guidance)
  else arbiter.unregister('guidance')
  arbiter.register(createAiAssistShellRail({
    ownerEpoch: props.ownerEpoch,
    capabilityEpoch: props.capabilityEpoch,
    snapshot: props.snapshot,
    openDsh: () => props.openDsh?.(),
    closeDsh: (opts) => props.closeDsh?.(opts),
  }))
  refreshView()
}

watch(
  () => [
    props.ownerEpoch,
    props.capabilityEpoch,
    props.snapshot,
    props.location,
    props.guidanceController,
    props.reviewHasDraft,
  ],
  syncRails,
  { immediate: true, deep: true },
)

watch(
  () => props.guidanceController.isOpen,
  (isOpen) => {
    if (!isOpen && openId.value === 'guidance') {
      arbiter.acknowledgeExternalClose('guidance')
      refreshView()
      teardownPanelA11y()
    }
  },
)

function onViewportResize(): void {
  viewportWidth.value = window.innerWidth
}

onMounted(() => {
  window.addEventListener('resize', onViewportResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onViewportResize)
  teardownPanelA11y()
  arbiter.unregister('review')
  arbiter.unregister('guidance')
  arbiter.unregister('ai-assist')
  shellActive.value = false
})

const cssVars = computed(() =>
  shellLayoutCssVars(
    resolvedTokens.value,
    openId.value === 'guidance' || openId.value === 'review',
  ),
)

let lastTrigger: HTMLElement | null = null
const PANEL_TRAP = 'wp-shell-rail-panel'

function setupPanelA11y(trigger: HTMLElement | null): void {
  lastTrigger = trigger
  beginShellFocusSession({ trapId: PANEL_TRAP, returnTarget: trigger })
  acquireShellScrollLock()
}

function teardownPanelA11y(): void {
  endShellFocusSession(PANEL_TRAP)
  releaseShellScrollLock()
  lastTrigger = null
}

async function onTrigger(id: ShellRailId, event?: MouseEvent): Promise<void> {
  const triggerEl = (event?.currentTarget as HTMLElement | null) ?? null
  const open = arbiter.getOpenState()
  if (open.status === 'open' && open.id === id) {
    await arbiter.requestClose(id, { preserveDraft: true })
    refreshView()
    teardownPanelA11y()
    return
  }
  await arbiter.requestOpen(id)
  refreshView()
  if (id === 'ai-assist') {
    // DSH owns its own focus/scroll; do not dual-trap.
    teardownPanelA11y()
    return
  }
  setupPanelA11y(triggerEl)
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Escape') return
  const open = arbiter.getOpenState()
  if (open.status === 'open') {
    void arbiter.requestClose(open.id, { preserveDraft: true }).then(() => {
      refreshView()
      teardownPanelA11y()
    })
    event.preventDefault()
    event.stopPropagation()
    return
  }
  handleShellEscapeKey(event)
}

// Expose for tests / parent error injection helpers
defineExpose({
  createShellStructuredError,
  viewportBand,
  resolvedTokens,
})
</script>

<style scoped>
.wp-capability-shell {
  position: relative;
  display: flex;
  flex: 1;
  min-width: 0;
  min-height: 0;
  height: 100%;
}

.wp-capability-shell__error {
  position: absolute;
  top: 8px;
  left: 12px;
  right: 48px;
  z-index: calc(var(--wp-shell-rail-z, 120) + 2);
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 12px;
  border: 1px solid #f56c6c;
  border-radius: 6px;
  background: #fef0f0;
  color: #c45656;
  font-size: 13px;
}

.wp-capability-shell__error-code {
  margin-left: auto;
  font-size: 11px;
  opacity: 0.8;
}

.wp-capability-shell__main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  padding-right: var(--wp-shell-content-inset-right, 0);
}

.wp-capability-shell__rail-strip {
  position: absolute;
  top: var(--wp-shell-rail-top, 96px);
  right: var(--wp-shell-rail-right, 0);
  z-index: var(--wp-shell-rail-z, 120);
  display: flex;
  flex-direction: column;
  gap: var(--wp-shell-rail-gap, 8px);
  pointer-events: none;
}

.wp-capability-shell__trigger {
  pointer-events: auto;
  writing-mode: vertical-rl;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 12px 6px;
  border: 1px solid var(--gt-border-light, #d8b8ee);
  border-right: none;
  border-radius: 8px 0 0 8px;
  background: var(--gt-bg-light, #f4f0fa);
  color: var(--gt-primary, #4b2d77);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
}

.wp-capability-shell__trigger:focus-visible {
  outline: 2px solid var(--gt-primary, #4b2d77);
  outline-offset: 2px;
}

.wp-capability-shell__trigger.is-active {
  background: var(--gt-border-light, #d8b8ee);
}

.wp-capability-shell__trigger[data-rail-id='review'] {
  background: #fff7e6;
  border-color: #ffd591;
  color: #d46b08;
}

.wp-capability-shell__trigger[data-rail-id='ai-assist'] {
  background: #f0f5ff;
  border-color: #adc6ff;
  color: #1d39c4;
}

.wp-capability-shell__trigger-text {
  letter-spacing: 2px;
}

.wp-capability-shell__panel {
  flex: 0 0 var(--wp-shell-panel-width, 380px);
  width: var(--wp-shell-panel-width, 380px);
  min-width: 320px;
  height: 100%;
  border-left: 1px solid var(--gt-border-light, #d8b8ee);
  background: #fff;
  overflow: hidden;
  z-index: calc(var(--wp-shell-rail-z, 120) + 1);
}

.wp-capability-shell__panel.is-collapsed {
  display: none;
  flex: 0;
  width: 0;
  min-width: 0;
  border: 0;
}

@media (min-width: 1280px) {
  .wp-capability-shell { --wp-shell-viewport: 1280; }
}
@media (min-width: 1440px) {
  .wp-capability-shell { --wp-shell-viewport: 1440; }
}
@media (min-width: 1920px) {
  .wp-capability-shell { --wp-shell-viewport: 1920; }
}
</style>
