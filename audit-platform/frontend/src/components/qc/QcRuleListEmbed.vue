<!--
  QcRuleListEmbed — QC 规则库嵌入组件 [R7-S3-03]
  在 QC 工作台 Tab 内嵌入规则列表（只读 + 跳转编辑）
-->
<template>
  <div class="qc-embed-panel">
    <div class="qc-embed-header">
      <span>规则库（{{ rules.length }} 条）</span>
      <el-button size="small" text type="primary" @click="$router.push('/qc/rules')">前往完整页面 →</el-button>
    </div>
    <el-table :data="rules" v-loading="loading" stripe size="small" max-height="500">
      <el-table-column prop="rule_code" label="编号" width="100" />
      <el-table-column prop="rule_name" label="名称" min-width="200" />
      <el-table-column prop="severity" label="级别" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.severity === 'blocking' ? 'danger' : row.severity === 'warning' ? 'warning' : 'info'" size="small">
            {{ row.severity }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="enabled" label="启用" width="70" align="center">
        <template #default="{ row }">{{ row.enabled ? '✅' : '—' }}</template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/services/apiProxy'
import { qcRules } from '@/services/apiPaths'

const rules = ref<any[]>([])
const loading = ref(false)

onMounted(async () => {
  loading.value = true
  try {
    const data = await api.get(qcRules.list)
    rules.value = Array.isArray(data) ? data : data?.items || []
  } catch { /* ignore */ }
  finally { loading.value = false }
})
</script>

<style scoped>
.qc-embed-panel { padding: var(--gt-space-2) 0; }
.qc-embed-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-3); font-weight: 600; }
</style>
