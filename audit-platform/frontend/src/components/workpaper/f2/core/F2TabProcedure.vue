<template>
<div class="f2-procedure">
  <!-- 程序表工具栏 -->
  <div class="procedure-header">
    <div class="index-chips">
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
    <el-empty v-else description="程序表数据加载失败" />
  </div>
</div>
</template>

<script setup lang="ts">
/**
 * F2TabProcedure.vue — F2A 程序表
 *
 * 复用 GtAProgramConsole componentType（selfLoad：force_component_type=a-program-console）
 * GtIndexChip 交叉索引跳转（F2-1/F2-2/F2-14/F2-16/F2-18/F2-33~35/A1-1/A1-13）
 * EventBus 监听 risk:updated 更新风险状态
 *
 * Task: 15.1
 * Requirements: 1.1
 */
import { ref, onMounted, onBeforeUnmount } from 'vue'
import http from '@/utils/http'

// @ts-ignore - Components may not have type declarations
import GtIndexChip from '../../GtIndexChip.vue'
// @ts-ignore
import GtAProgramConsole from '../../GtAProgramConsole.vue'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  htmlData?: any
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
  // 如果外部已传入 htmlData 且包含有效程序数据则直接使用
  if (props.htmlData?.programs || props.htmlData?.schema) {
    programData.value = props.htmlData
    isLoading.value = false
    return
  }

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
    console.warn('[F2TabProcedure] selfLoad render-config failed:', err)
  }

  isLoading.value = false
}

// ─── EventBus: risk:updated 监听（存货科目组 1401~1412）─────────────────────

function onRiskUpdated(e: Event) {
  const detail = (e as CustomEvent).detail
  // 存货科目组 1401~1412
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
.f2-procedure {
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
