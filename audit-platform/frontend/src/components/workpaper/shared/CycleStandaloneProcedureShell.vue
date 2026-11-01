<script setup lang="ts">
/**
 * 无科目主入口的循环 *A 程序表壳 — 双模式 + CycleTabProcedure（对齐 D4A）
 * 由 GtCycleAProgramRouter 在 sheet 命中 cycleProcedureSheets 时挂载。
 */
import { computed, defineAsyncComponent, toRef } from 'vue'
import GtEntrySyncCapabilityNotice from '../sync/GtEntrySyncCapabilityNotice.vue'
import { useEntrySyncReadiness } from '../sync/useEntrySyncReadiness'
import CycleTabProcedure from './CycleTabProcedure.vue'
import { useCycleHtmlOoDualMode } from '../composables/useCycleHtmlOoDualMode'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('../GtOnlyOfficeSheet.vue'))

const props = defineProps<{
  wpId: string
  projectId?: string
  sheetName: string
  sheetCode: string
  htmlData?: any
  readonly?: boolean
}>()

const dualMode = useCycleHtmlOoDualMode({
  wpId: toRef(props, 'wpId'),
  storagePrefix: `cycle-proc-${props.sheetCode}:`,
})

const projectId = computed(() => props.projectId || '')
/**
 * 同步能力单源（spec workpaper-html-onlyoffice-bidirectional-writeback-closure
 * · task 3.5 / AC 1.4）：模式开关的可见性来自 entry 级三层事实，不由本宿主判断。
 *
 * 🔴 `SYNC_ENTRY_ID` 取自 `sync/workpaperSyncManifest.generated.ts` 里 `hostPath`
 * 指向本文件的那条 entry（manifest 是 entry 身份的生成真源）。它在这里是个字面量，
 * 所以由 `sync/__tests__/entrySyncHostWiringContract.spec.ts` 钉住两边一致 ——
 * 否则宿主与真源会各自漂移。
 *
 * 🔴 声明位置在 setup 末尾是**有意**的：`useEntrySyncReadiness` 内部
 * `watch(..., { immediate: true })` 会在 setup 期立即读下面三个 getter，放在
 * `props` 之前会让 `props` 落在 TDZ 里（运行时 ReferenceError，静态门看不出来）。
 */
const SYNC_ENTRY_ID = 'xlsx/shared/cycle-standalone-procedure-shell'
const cycleStandaloneProcedureShellEntrySync = useEntrySyncReadiness({
  projectId: () => String(props.projectId ?? ''),
  wpId: () => String(props.wpId ?? ''),
  entryId: () => SYNC_ENTRY_ID,
})

</script>

<template>
  <div class="cycle-standalone-procedure">
    <div class="cycle-standalone-procedure__toolbar">
      <el-segmented
        v-if="cycleStandaloneProcedureShellEntrySync.presentation.value.showModeSwitch"
        :model-value="dualMode.currentMode.value"
        :options="dualMode.modeOptions"
        size="small"
        @change="dualMode.onModeChange"
      />
      <!--
        能力披露（spec task 3.5 / AC 1.5）：上面的模式开关一旦被同步能力单源藏起来，
        这里必须讲清楚「为什么没有在线编辑」+ 可操作的下一步。只隐藏开关不给原因，
        比显示一个打不开的假开关更糟。entry id 与开关的门用**同一个**表达式。
      -->
      <GtEntrySyncCapabilityNotice :entry-id="SYNC_ENTRY_ID" />
      <el-tag v-if="!dualMode.isOoAvailable.value" size="small" type="warning">OO不可用</el-tag>
    </div>

    <GtOnlyOfficeSheet
      v-if="dualMode.currentMode.value === 'onlyoffice'"
      :wp-id="wpId"
      :project-id="projectId"
      :sheet-name="sheetName"
      :readonly="readonly"
      style="height: calc(100vh - 180px)"
    />

    <CycleTabProcedure
      v-else
      :sheet-code="sheetCode"
      :html-data="htmlData"
      :wp-id="wpId"
      :project-id="projectId"
      :readonly="readonly"
    />
  </div>
</template>

<style scoped>
.cycle-standalone-procedure {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.cycle-standalone-procedure__toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
</style>
