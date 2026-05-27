<!--
  StatusMachinePanel — 可解释状态机面板（spec global-refinement-v3 Task 10.3）
  =============================================================================
  展示当前状态 + 允许操作 ✓ + 不允许操作 ✗ + 原因 + 流转图。

  用法：
    <StatusMachinePanel ref="smPanelRef" :module="module" :instance-id="instanceId" />
    smPanelRef.value?.open()

  Props:
    module: string       业务模块类型（workpaper/adjustment/misstatement/report/disclosure）
    instanceId: string   实例 ID

  Expose:
    open(): void   打开面板
    close(): void  关闭面板
-->
<template>
  <el-drawer
    v-model="visible"
    title="ℹ️ 当前可操作"
    size="560px"
    :destroy-on-close="false"
    direction="rtl"
  >
    <div v-loading="loading" style="min-height: 200px">
      <template v-if="data">
        <!-- 当前状态 -->
        <div class="sm-status-row">
          <span class="sm-label">当前状态：</span>
          <el-tag type="primary" size="large">{{ data.current_status_zh }}</el-tag>
        </div>

        <!-- 允许的操作 -->
        <div class="sm-section" v-if="data.allowed.length > 0">
          <h4 class="sm-section-title">允许的操作</h4>
          <ul class="sm-list sm-allowed">
            <li v-for="a in data.allowed" :key="a.action" class="sm-item">
              <el-icon color="#67c23a"><i class="el-icon-check" /></el-icon>
              <span class="sm-check">✓</span>
              <span class="sm-action-label">{{ a.label_zh }}</span>
            </li>
          </ul>
        </div>

        <!-- 不允许的操作 -->
        <div class="sm-section" v-if="data.denied.length > 0">
          <h4 class="sm-section-title">不允许的操作</h4>
          <ul class="sm-list sm-denied">
            <li v-for="d in data.denied" :key="d.action" class="sm-item">
              <span class="sm-cross">✗</span>
              <span class="sm-action-label">{{ d.label_zh }}</span>
              <span class="sm-reason">— {{ d.reason_zh }}</span>
            </li>
          </ul>
        </div>

        <!-- 状态机流转图 -->
        <div class="sm-section" v-if="mermaidCode">
          <h4 class="sm-section-title">状态流转图</h4>
          <div class="sm-mermaid-container">
            <pre class="sm-mermaid-code">{{ mermaidCode }}</pre>
          </div>
        </div>
      </template>
      <el-empty v-else-if="!loading" description="暂无数据" />
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { api } from '@/services/apiProxy'

interface ActionDescriptor {
  action: string
  label_zh: string
  allowed: boolean
  reason_code: string | null
  reason_zh: string | null
}

interface StatusMachineData {
  current_status: string
  current_status_zh: string
  allowed: ActionDescriptor[]
  denied: ActionDescriptor[]
  transitions: Array<{ from: string; to: string; action: string; action_zh: string }>
}

const props = defineProps<{
  module: string
  instanceId: string
}>()

const visible = ref(false)
const loading = ref(false)
const data = ref<StatusMachineData | null>(null)

const mermaidCode = computed(() => {
  if (!data.value || !data.value.transitions.length) return ''
  const lines = ['stateDiagram-v2']
  for (const t of data.value.transitions) {
    lines.push(`  ${t.from} --> ${t.to} : ${t.action_zh}`)
  }
  // 当前状态高亮
  lines.push(`  classDef current fill:#4b2d77,color:#fff`)
  lines.push(`  class ${data.value.current_status} current`)
  return lines.join('\n')
})

async function open() {
  visible.value = true
  loading.value = true
  data.value = null
  try {
    const result: any = await api.get(
      `/api/${props.module}/${props.instanceId}/allowed-actions`,
    )
    data.value = result
  } catch (e: any) {
    console.error('[StatusMachinePanel] 加载失败:', e)
  } finally {
    loading.value = false
  }
}

function close() {
  visible.value = false
}

defineExpose({ open, close })
</script>

<style scoped>
.sm-status-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 20px;
}

.sm-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.sm-section {
  margin-bottom: 20px;
}

.sm-section-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--el-text-color-primary);
}

.sm-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.sm-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  font-size: 13px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.sm-item:last-child {
  border-bottom: none;
}

.sm-check {
  color: #67c23a;
  font-weight: 600;
}

.sm-cross {
  color: #f56c6c;
  font-weight: 600;
}

.sm-action-label {
  font-weight: 500;
}

.sm-reason {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.sm-mermaid-container {
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
  padding: 12px;
  overflow-x: auto;
}

.sm-mermaid-code {
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  margin: 0;
  color: var(--el-text-color-regular);
}
</style>
