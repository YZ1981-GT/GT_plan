<script setup lang="ts">
/**
 * MetricsTab — 证据治理可观测性指标（useEvidenceMetrics，全局前缀，无 project/year）
 *
 * Spec: attachment-ocr-ai-evidence-governance-hardening (R12/R16)
 */
import { onMounted, computed } from 'vue'
import { useEvidenceMetrics } from '@/composables/useEvidenceMetrics'

const { loading, error, metrics, loadMetrics } = useEvidenceMetrics()

/** 把顶层数值型指标扁平化为表格行 */
const metricRows = computed(() => {
  const m = metrics.value
  if (!m) return []
  const rows: Array<{ key: string; value: string }> = []
  const walk = (obj: any, prefix: string) => {
    for (const [k, v] of Object.entries(obj || {})) {
      const key = prefix ? `${prefix}.${k}` : k
      if (v !== null && typeof v === 'object' && !Array.isArray(v)) {
        walk(v, key)
      } else {
        rows.push({ key, value: Array.isArray(v) ? `[${v.length} 项]` : String(v) })
      }
    }
  }
  walk(m, '')
  return rows
})
</script>

<template>
  <div class="evgov-tab">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="进程级低基数治理指标 + 近期告警聚合：上传/边界/引用/OCR 排队与失败/AI 覆盖/引用可定位/stale 账龄/门禁绕过/归档校验失败/背压等（仅 admin/manager/partner）。"
      style="margin-bottom: 12px"
    />

    <div class="toolbar">
      <el-button type="primary" :loading="loading" @click="loadMetrics">加载指标</el-button>
    </div>

    <el-alert v-if="error" type="error" :title="error" show-icon :closable="true" style="margin-bottom: 12px" />

    <el-table v-if="metricRows.length" :data="metricRows" size="small" border stripe max-height="520">
      <el-table-column prop="key" label="指标" min-width="280" />
      <el-table-column prop="value" label="值" min-width="160" />
    </el-table>
    <el-empty v-else-if="!loading" description="点击上方按钮加载治理指标" />
  </div>
</template>

<style scoped>
.evgov-tab { padding: 4px 0; }
.toolbar { margin-bottom: 8px; }
</style>
