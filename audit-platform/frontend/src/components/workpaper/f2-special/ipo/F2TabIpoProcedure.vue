<template>
<div class="f2-ipo-procedure">
  <!-- 交叉索引 -->
  <div class="procedure-header">
    <div class="index-chips">
      <GtIndexChip wp-code="F2-61" label="F2-61" />
      <GtIndexChip wp-code="F2-62" label="F2-62" />
      <GtIndexChip wp-code="F2-63" label="F2-63" />
      <GtIndexChip wp-code="F2-64" label="F2-64" />
      <GtIndexChip wp-code="F2-65" label="F2-65" />
      <GtIndexChip wp-code="F2-68" label="F2-68" />
      <GtIndexChip wp-code="F2-70" label="F2-70" />
      <GtIndexChip wp-code="F2-72" label="F2-72" />
      <GtIndexChip wp-code="F2-1" label="F2-1" />
      <GtIndexChip wp-code="A1-13" label="A1-13" />
    </div>
  </div>

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
 * F2TabIpoProcedure.vue — F2-61A IPO存货程序表
 *
 * 复用 GtAProgramConsole（selfLoad: force_component_type=a-program-console）
 * 交叉索引：F2-61~F2-72关键sheet + F2-1 + A1-13
 *
 * Task: 8.1
 * Requirements: 1.1
 */
import { ref, onMounted } from 'vue'
import http from '@/utils/http'

// @ts-ignore
import GtIndexChip from '../../../GtIndexChip.vue'
// @ts-ignore
import GtAProgramConsole from '../../../GtAProgramConsole.vue'

const props = defineProps<{
  htmlData?: any
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const isLoading = ref(true)
const programData = ref<any>(null)

async function selfLoad() {
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
    const sheetData = renderData?.sheets?.[0]?.html_data ?? renderData
    programData.value = sheetData
  } catch (err) {
    console.warn('[F2TabIpoProcedure] selfLoad failed:', err)
  }

  isLoading.value = false
}

onMounted(selfLoad)
</script>

<style scoped>
.f2-ipo-procedure {
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
