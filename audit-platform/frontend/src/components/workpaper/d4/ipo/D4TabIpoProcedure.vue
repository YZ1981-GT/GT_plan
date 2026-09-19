<template>
<div class="d4-ipo-procedure">
  <!-- 程序表主体：复用 GtAProgramConsole -->
  <div class="program-console-wrapper">
    <GtAProgramConsole
      v-if="programData"
      :wp-id="wpId"
      :project-id="projectId"
      sheet-name="D4-22A"
      :html-data="programData"
      :schema="programData?.schema || { columns: [], rows: [] }"
      :readonly="isReadonly"
    />
    <div v-else-if="isLoading" class="loading-placeholder">
      <el-skeleton :rows="8" animated />
    </div>
    <el-empty v-else description="IPO程序表数据加载中..." />
  </div>
</div>
</template>

<script setup lang="ts">
/**
 * D4TabIpoProcedure — D4-22A IPO实质性程序表
 *
 * 包装组件：自行从 render-config 加载 D4-22A 的程序表数据，
 * 然后传给 GtAProgramConsole 渲染。
 * 解决聚合包内 GtAProgramConsole selfLoad 用父级wpId时
 * 只能拿到D4A（非D4-22A）数据的问题。
 */
import { ref, onMounted } from 'vue'
import http from '@/utils/http'
import GtAProgramConsole from '../../GtAProgramConsole.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const isLoading = ref(true)
const programData = ref<any>(null)

async function selfLoad() {
  if (!props.wpId) { isLoading.value = false; return }
  try {
    // 用 sheet_name 参数告诉后端要 D4-22A 的程序表
    const res = await http.get(
      `/api/workpapers/${props.wpId}/render-config`,
      { params: { force_component_type: 'a-program-console', sheet_name: 'D4-22A' }, _silent: true } as any,
    )
    const renderData = res.data?.data ?? res.data
    const sheetData = renderData?.sheets?.[0]?.html_data ?? renderData
    // 即使programs为空也设置programData（让GtAProgramConsole展示空态+新增按钮）
    programData.value = sheetData || { programs: [], schema: { columns: [], rows: [] } }
  } catch (err) {
    console.warn('[D4TabIpoProcedure] selfLoad failed:', err)
    // fallback: 给一个空的programData让组件渲染（用户可手动添加程序）
    programData.value = { programs: [], schema: { columns: [], rows: [] } }
  }
  isLoading.value = false
}

onMounted(() => { selfLoad() })
</script>

<style scoped>
.d4-ipo-procedure { padding: 0; }
.program-console-wrapper { min-height: 300px; }
.loading-placeholder { padding: 24px; }
</style>
