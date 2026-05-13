<template>
  <div class="integrity-panel">
    <div class="panel-header">
      <h4>取证包完整性校验</h4>
      <el-button size="small" @click="loadData" :loading="loading">校验</el-button>
    </div>

    <div v-if="result">
      <!-- 总体状态 -->
      <el-alert
        :type="result.check_status === 'passed' ? 'success' : 'error'"
        :closable="false"
        show-icon
        style="margin-bottom:12px"
      >
        <template #title>
          {{ result.check_status === 'passed' ? '校验通过' : '校验失败' }}
          <span v-if="result.mismatched_files?.length">（{{ result.mismatched_files.length }} 个文件不匹配）</span>
        </template>
      </el-alert>

      <!-- manifest hash -->
      <div class="manifest-hash" v-if="result.manifest_hash">
        <span class="hash-label">manifest_hash:</span>
        <code>{{ result.manifest_hash }}</code>
      </div>

      <!-- 文件列表 -->
      <el-table :data="result.file_checks || []" size="small" border style="margin-top:8px">
        <el-table-column prop="file_path" label="文件路径" min-width="300" show-overflow-tooltip />
        <el-table-column label="SHA-256" width="180">
          <template #default="{ row }">
            <code class="hash-short" :title="row.expected_sha256 || row.sha256">
              {{ (row.expected_sha256 || row.sha256)?.substring(0, 16) }}...
            </code>
          </template>
        </el-table-column>
        <el-table-column prop="check_status" label="状态" width="80" align="center">
          <template #default="{ row }">
            <span v-if="row.check_status === 'passed'" class="status-passed">✓</span>
            <span v-else class="status-failed">✗</span>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { handleApiError } from '@/utils/errorHandler'
import { checkExportIntegrity } from '@/services/governanceApi'

const props = defineProps<{ exportId: string }>()

const loading = ref(false)
const result = ref<any>(null)

async function loadData() {
  loading.value = true
  try {
    result.value = await checkExportIntegrity(props.exportId)
  } catch (e) { handleApiError(e, '完整性校验失败') }
  finally { loading.value = false }
}
</script>

<style scoped>
.integrity-panel { padding: 16px; }
.panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.manifest-hash { font-size: 12px; color: #666; }
.hash-label { margin-right: 4px; }
.hash-short { font-size: 11px; color: #999; }
.status-passed { color: var(--el-color-success); font-size: 16px; font-weight: 600; }
.status-failed { color: var(--el-color-danger); font-size: 16px; font-weight: 600; }
</style>
