<template>
<div class="d5-procedure">
  <!-- 程序表工具栏 -->
  <div class="procedure-header">
    <div class="index-chips">
      <GtIndexChip wp-code="D5-1" label="D5-1" />
      <GtIndexChip wp-code="D5-2" label="D5-2" />
      <GtIndexChip wp-code="D1-6" label="D1-6" />
      <GtIndexChip wp-code="D2-13" label="D2-13" />
      <GtIndexChip wp-code="D0" label="D0" />
      <GtIndexChip wp-code="D1-7" label="D1-7" />
      <GtIndexChip wp-code="D1-10" label="D1-10" />
      <GtIndexChip wp-code="D5-4" label="D5-4" />
      <GtIndexChip wp-code="A1-1" label="A1-1" />
      <GtIndexChip wp-code="A1-15" label="A1-15" />
      <GtIndexChip wp-code="A1-16" label="A1-16" />
    </div>
  </div>

  <!-- 风险状态指示 -->
  <el-alert
    v-if="riskStatus"
    :type="riskStatus.level === 'high' ? 'error' : riskStatus.level === 'medium' ? 'warning' : 'info'"
    :title="`风险评估：${riskStatus.level === 'high' ? '高' : riskStatus.level === 'medium' ? '中' : '低'}风险`"
    :closable="false"
    show-icon
    style="margin-bottom: 12px"
  />

  <!-- 程序表主体：复用 GtAProgramConsole -->
  <div class="program-console-wrapper">
    <GtAProgramConsole
      v-if="programData"
      :wp-id="wpId"
      :project-id="projectId"
      :html-data="programData"
      :readonly="isReadonly"
    />
    <div v-else-if="isLoading" class="loading-placeholder">
      <el-skeleton :rows="6" animated />
    </div>
    <el-empty v-else description="程序表数据加载中..." />
  </div>
</div>
</template>

<script setup lang="ts">
/**
 * D5TabProcedure.vue — D5A 程序表
 *
 * 复用 GtAProgramConsole componentType（selfLoad：force_component_type=a-program-console）
 * GtIndexChip 11处交叉索引跳转
 * EventBus 监听 risk:updated 更新程序步骤状态
 *
 * Task: 12.1
 * Requirements: 9.1-9.6
 */
import { ref, onMounted, onBeforeUnmount } from 'vue'
import http from '@/utils/http'

// @ts-ignore - Components may not have type declarations
import GtIndexChip from '../GtIndexChip.vue'
// @ts-ignore
import GtAProgramConsole from '../GtAProgramConsole.vue'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

// ─── State ───────────────────────────────────────────────────────────────────

const isLoading = ref(true)
const programData = ref<any>(null)
const riskStatus = ref<{ level: string; affectedAccounts?: string[] } | null>(null)

// ─── selfLoad (force_component_type=a-program-console) ───────────────────────

async function selfLoad() {
  if (!props.wpId) {
    isLoading.value = false
    return
  }

  try {
    const res = await http.get(
      `/api/workpapers/${props.wpId}/render-config`,
      { params: { force_component_type: 'a-program-console' }, _silent: true } as any,
    )
    const renderData = res.data?.data ?? res.data
    // render-config 返回 { sheets: [{ html_data: {...} }] }
    const sheetData = renderData?.sheets?.[0]?.html_data ?? renderData
    programData.value = sheetData
  } catch (err) {
    console.warn('[D5TabProcedure] selfLoad render-config failed:', err)
  }

  isLoading.value = false
}

// ─── EventBus: risk:updated 监听 ─────────────────────────────────────────────

function onRiskUpdated(e: Event) {
  const detail = (e as CustomEvent).detail
  if (detail?.affectedAccounts?.includes('1124')) {
    riskStatus.value = {
      level: detail.riskLevel || 'medium',
      affectedAccounts: detail.affectedAccounts,
    }
  }
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  window.addEventListener('risk:updated', onRiskUpdated)
  await selfLoad()
})

onBeforeUnmount(() => {
  window.removeEventListener('risk:updated', onRiskUpdated)
})
</script>

<style scoped>
.d5-procedure {
  padding: 16px;
}

.procedure-header {
  margin-bottom: 12px;
}

.index-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 6px;
}

.program-console-wrapper {
  min-height: 300px;
}

.loading-placeholder {
  padding: 24px;
}
</style>
