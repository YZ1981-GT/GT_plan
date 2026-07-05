<script setup lang="ts">
/**
 * F2A — 存货实质性程序表（对齐 D4A；保留交叉索引与风险联动 toolbar 插槽）
 */
import { ref, onMounted, onBeforeUnmount } from 'vue'
import CycleProgramConsoleTab from '../../shared/CycleProgramConsoleTab.vue'
import { FH_CYCLE_PROCEDURE_SHEETS } from '../../composables/cycleProcedureSheets'
import GtIndexChip from '../../GtIndexChip.vue'

const cfg = FH_CYCLE_PROCEDURE_SHEETS.F2A

const props = defineProps<{
  htmlData?: any
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const riskStatus = ref<{ level: string; affectedAccounts?: string[] } | null>(null)

function onRiskUpdated(e: Event) {
  const detail = (e as CustomEvent).detail
  const inventoryAccounts = [
    '1401', '1402', '1403', '1404', '1405', '1406',
    '1407', '1408', '1409', '1410', '1411', '1412',
  ]
  const affected = detail?.affectedAccounts as string[] | undefined
  if (affected?.some((acc: string) => inventoryAccounts.includes(acc))) {
    riskStatus.value = {
      level: detail.riskLevel || 'medium',
      affectedAccounts: affected,
    }
  }
}

onMounted(() => {
  window.addEventListener('risk:updated', onRiskUpdated)
})

onBeforeUnmount(() => {
  window.removeEventListener('risk:updated', onRiskUpdated)
})
</script>

<template>
  <div class="f2-tab-procedure-wrap">
    <el-alert
      v-if="riskStatus"
      :type="riskStatus.level === 'high' ? 'error' : riskStatus.level === 'medium' ? 'warning' : 'info'"
      :title="`风险评估：${riskStatus.level === 'high' ? '高' : riskStatus.level === 'medium' ? '中' : '低'}风险`"
      :closable="false"
      show-icon
      class="f2-tab-procedure-wrap__risk"
    />

    <CycleProgramConsoleTab
      :html-data="htmlData"
      :wp-id="wpId"
      :project-id="projectId"
      :is-readonly="isReadonly"
      :sheet-code="cfg.sheetCode"
      :sheet-label="cfg.sheetLabel"
      root-class="f2-tab-procedure"
    >
      <template #toolbar>
        <div class="f2-tab-procedure__index-chips">
          <GtIndexChip wp-code="F2-1" label="F2-1" />
          <GtIndexChip wp-code="F2-2" label="F2-2" />
          <GtIndexChip wp-code="F2-14" label="F2-14" />
          <GtIndexChip wp-code="F2-16" label="F2-16" />
          <GtIndexChip wp-code="F2-18" label="F2-18" />
          <GtIndexChip wp-code="F2-33" label="F2-33" />
          <GtIndexChip wp-code="F2-34" label="F2-34" />
          <GtIndexChip wp-code="F2-35" label="F2-35" />
          <GtIndexChip wp-code="A1-1" label="A1-1" />
          <GtIndexChip wp-code="A1-13" label="A1-13" />
        </div>
      </template>
    </CycleProgramConsoleTab>
  </div>
</template>

<style scoped>
.f2-tab-procedure-wrap__risk {
  margin-bottom: 12px;
}

.f2-tab-procedure__index-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 6px;
}
</style>
