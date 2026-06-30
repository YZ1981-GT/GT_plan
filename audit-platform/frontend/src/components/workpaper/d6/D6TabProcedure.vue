<template>
<div class="d6-tab-procedure">
  <!-- 加载状态 -->
  <el-skeleton v-if="isLoading" :rows="6" animated />

  <template v-else>
    <!-- 编制提示 -->
    <details class="editing-hints">
      <summary>📋 编制提示</summary>
      <div class="hints-content">
        <p>本程序表列示D6合同资产底稿全部实质性程序步骤。</p>
        <p>请逐项执行审计程序，完成后标记状态并填写执行情况说明。</p>
        <p>ECL减值测算步骤（D6-7+D6-8）需重点关注预期信用损失率的合理性。</p>
        <p>函证程序（D0）需确认合同资产余额的真实性和完整性。</p>
      </div>
    </details>

    <!-- 索引跳转区 -->
    <div class="index-chips-bar">
      <span class="chip-label">相关底稿：</span>
      <GtIndexChip wp-code="D6-1" label="D6-1 审定表" />
      <GtIndexChip wp-code="D6-2" label="D6-2 明细表" />
      <GtIndexChip wp-code="D6-3" label="D6-3 减值明细" />
      <GtIndexChip wp-code="D6-5" label="D6-5 关联方" />
      <GtIndexChip wp-code="D6-6" label="D6-6 检查表" />
      <GtIndexChip wp-code="D6-7" label="D6-7 减值政策" />
      <GtIndexChip wp-code="D6-8" label="D6-8 ECL测算" />
      <GtIndexChip wp-code="D6-9" label="D6-9 转回核销" />
      <GtIndexChip wp-code="D0" label="D0 函证" />
      <GtIndexChip wp-code="D4" label="D4 营业收入" />
      <GtIndexChip wp-code="A1-1" label="A1-1" />
      <GtIndexChip wp-code="A1-15" label="A1-15" />
      <GtIndexChip wp-code="A1-16" label="A1-16" />
    </div>

    <!-- 程序表主体：复用 GtAProgramConsole -->
    <component
      :is="programConsole"
      v-if="programData"
      :wp-id="wpId"
      :project-id="projectId"
      :html-data="programData"
      :readonly="isReadonly"
    />

    <el-empty v-else description="暂无程序表数据，请刷新或检查底稿配置" />
  </template>
</div>
</template>

<script setup lang="ts">
/**
 * D6TabProcedure.vue — 实质性程序表 D6A
 *
 * 复用 GtAProgramConsole componentType（selfLoad: force_component_type=a-program-console）
 * GtIndexChip跳转：D6-1~D6-9 / D0 / D4 / A1-1 / A1-15 / A1-16
 * EventBus 监听 risk:updated → 更新程序步骤状态
 * 特别标注 ECL 步骤（D6-7+D6-8）和函证步骤（D0）
 *
 * Task: 15.1
 * Requirements: 18.1-18.6
 */
import { ref, onMounted, onUnmounted, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const programConsole = defineAsyncComponent(() => import('../GtAProgramConsole.vue'))

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

// ─── State ───────────────────────────────────────────────────────────────────

const isLoading = ref(false)
const programData = ref<any>(null)

// ─── Self Load ───────────────────────────────────────────────────────────────

async function loadProgramData() {
  isLoading.value = true
  try {
    const res = await http.get(`/api/workpapers/${props.wpId}/render-config`, {
      params: { force_component_type: 'a-program-console' },
    })
    const data = res.data?.data || res.data
    programData.value = data?.sheets?.[0]?.html_data || data
  } catch (err) {
    console.error('[D6TabProcedure] loadProgramData failed:', err)
  } finally {
    isLoading.value = false
  }
}

// ─── EventBus: risk:updated ──────────────────────────────────────────────────

function onRiskUpdated(payload: any) {
  if (!payload?.affectedAccounts) return
  const accounts: string[] = payload.affectedAccounts
  if (accounts.includes('1402') || accounts.includes('合同资产')) {
    // Reload to reflect updated risk-driven program steps
    loadProgramData()
  }
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  loadProgramData()
  eventBus.on('risk:updated' as any, onRiskUpdated)
})

onUnmounted(() => {
  eventBus.off('risk:updated' as any, onRiskUpdated)
})
</script>

<style scoped>
.d6-tab-procedure {
  padding: 16px;
}

.editing-hints {
  margin-bottom: 16px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 0;
}

.editing-hints summary {
  padding: 10px 14px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  color: #409eff;
}

.hints-content {
  padding: 0 14px 12px;
  font-size: 13px;
  color: #606266;
  line-height: 1.8;
  white-space: pre-wrap;
}

.hints-content p {
  margin: 0 0 4px;
}

.index-chips-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  padding: 10px 12px;
  background: #f5f7fa;
  border-radius: 6px;
  margin-bottom: 16px;
}

.chip-label {
  font-size: 13px;
  color: #909399;
  margin-right: 4px;
}
</style>
