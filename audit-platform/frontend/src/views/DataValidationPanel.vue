<template>
  <div class="data-validation-panel">
    <div class="panel-header">
      <h3>数据校验</h3>
      <el-button type="primary" :loading="loading" @click="runValidation">运行校验</el-button>
      <el-button @click="exportFindings" :disabled="!findings.length">导出</el-button>
    </div>

    <el-tabs v-model="activeTab">
      <el-tab-pane label="数据一致性" name="consistency">
        <ValidationList :findings="consistencyFindings" @fix="handleFix" />
      </el-tab-pane>
      <el-tab-pane label="数据完整性" name="completeness">
        <ValidationList :findings="completenessFindings" @fix="handleFix" />
      </el-tab-pane>
    </el-tabs>

    <div v-if="summary" class="summary-bar">
      <el-tag type="danger">高: {{ summary.high }}</el-tag>
      <el-tag type="warning">中: {{ summary.medium }}</el-tag>
      <el-tag type="info">低: {{ summary.low }}</el-tag>
      <span class="total">共 {{ summary.total }} 项</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import ValidationList from '../components/common/ValidationList.vue'
import http from '../utils/http'

const props = defineProps<{ projectId: string }>()

const loading = ref(false)
const activeTab = ref('consistency')
const findings = ref<any[]>([])
const summary = ref<any>(null)

const consistencyFindings = computed(() =>
  findings.value.filter(f => f.check_type.includes('consistency') || f.check_type.includes('balance'))
)
const completenessFindings = computed(() =>
  findings.value.filter(f => f.check_type.includes('required') || f.check_type.includes('format') || f.check_type.includes('range') || f.check_type.includes('logic'))
)

async function runValidation() {
  loading.value = true
  try {
    const { data: res } = await http.post(`/api/projects/${props.projectId}/data-validation`)
    findings.value = res.findings || []
    summary.value = { total: res.total, ...res.by_severity }
    ElMessage.success(`校验完成，发现 ${res.total} 项问题`)
  } catch (e: any) {
    ElMessage.error('校验失败: ' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

async function handleFix(findingIds: string[]) {
  try {
    await http.post(`/api/projects/${props.projectId}/data-validation/fix`, findingIds)
    ElMessage.success('修复完成')
    await runValidation()
  } catch (e: any) {
    ElMessage.error('修复失败')
  }
}

async function exportFindings() {
  window.open(`/api/projects/${props.projectId}/data-validation/export?format=csv`, '_blank')
}
</script>

<style scoped>
.data-validation-panel { padding: 16px; }
.panel-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.panel-header h3 { flex: 1; margin: 0; }
.summary-bar { display: flex; gap: 8px; align-items: center; margin-top: 16px; }
.total { color: #666; font-size: 13px; }
</style>
