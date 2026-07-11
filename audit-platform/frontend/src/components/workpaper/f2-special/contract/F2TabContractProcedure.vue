<template>
<div class="f2-contract-procedure">
  <!-- 编制提示 -->
  <details class="guidance-details">
    <summary>📋 编制提示</summary>
    <div class="guidance-content">
      <p>1. 本程序表按 CAS14 号列示合同履约成本的实质性审计程序，逐条执行并记录结论、索引。</p>
      <p>2. 关注合同履约成本的资本化条件（直接相关、增加未来资源、预期收回）与摊销、减值处理。</p>
      <p>3. 检查凭证真实性、计量准确性与期间归属，结合抽凭（F2-56）与减值测算（F2-57）交叉复核。</p>
      <p>4. 程序执行结论应回填底稿目录（F2-1）并向报表层（A1-13）传递。</p>
    </div>
  </details>

  <!-- 审计目标 -->
  <el-alert type="info" :closable="false" show-icon class="objective-alert">
    <template #title>审计目标：确认合同履约成本的确认、计量、摊销及减值符合 CAS14 号要求，期末余额真实、完整、准确。</template>
  </el-alert>

  <!-- 交叉索引 -->
  <div class="procedure-header">
    <div class="index-chips">
      <GtIndexChip value="wp:F2-55" :context-project-id="projectId" />
      <GtIndexChip value="wp:F2-56" :context-project-id="projectId" />
      <GtIndexChip value="wp:F2-57" :context-project-id="projectId" />
      <GtIndexChip value="wp:F2-58" :context-project-id="projectId" />
      <GtIndexChip value="wp:F2-1" :context-project-id="projectId" />
      <GtIndexChip value="wp:A1-13" :context-project-id="projectId" />
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
 * F2TabContractProcedure.vue — F2-55A 合同履约成本实质性程序表
 *
 * 复用 GtAProgramConsole（selfLoad: force_component_type=a-program-console）
 * 交叉索引：F2-55~F2-58 + F2-1 + A1-13
 *
 * Task: 7.1
 * Requirements: 1.1
 */
import { ref, onMounted } from 'vue'
import http from '@/utils/http'

import GtIndexChip from '../../GtIndexChip.vue'
import GtAProgramConsole from '../../GtAProgramConsole.vue'

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
    console.warn('[F2TabContractProcedure] selfLoad failed:', err)
  }

  isLoading.value = false
}

onMounted(selfLoad)
</script>

<style scoped>
.f2-contract-procedure {
  padding: 16px;
}

.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }

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
