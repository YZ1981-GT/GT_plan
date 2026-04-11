<template>
  <div class="data-import-panel">
    <h3>数据导入</h3>

    <!-- Upload Section -->
    <el-card class="import-upload-card" shadow="hover">
      <template #header>
        <span>上传数据文件</span>
      </template>

      <el-form :model="form" label-width="100px" size="default">
        <el-form-item label="数据源类型">
          <el-select v-model="form.sourceType" placeholder="选择数据源">
            <el-option label="通用模板" value="generic" />
            <el-option label="用友U8/T+" value="yonyou" />
            <el-option label="金蝶K3/KIS" value="kingdee" />
            <el-option label="SAP" value="sap" />
          </el-select>
        </el-form-item>

        <el-form-item label="数据类型">
          <el-select v-model="form.dataType" placeholder="选择数据类型">
            <el-option label="科目余额表" value="tb_balance" />
            <el-option label="序时账" value="tb_ledger" />
            <el-option label="辅助余额表" value="tb_aux_balance" />
            <el-option label="辅助明细账" value="tb_aux_ledger" />
          </el-select>
        </el-form-item>

        <el-form-item label="审计年度">
          <el-input-number v-model="form.year" :min="2000" :max="2099" />
        </el-form-item>

        <el-form-item label="选择文件">
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :limit="1"
            :on-change="handleFileChange"
            :on-remove="handleFileRemove"
            accept=".xlsx,.xls,.csv"
            drag
          >
            <el-icon class="el-icon--upload"><upload-filled /></el-icon>
            <div class="el-upload__text">
              拖拽文件到此处，或 <em>点击上传</em>
            </div>
            <template #tip>
              <div class="el-upload__tip">支持 Excel (.xlsx/.xls) 和 CSV (.csv) 格式</div>
            </template>
          </el-upload>
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            :loading="importing"
            :disabled="!selectedFile || !form.dataType"
            @click="startImport"
          >
            开始导入
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Progress Section -->
    <el-card v-if="currentProgress" class="import-progress-card" shadow="hover" style="margin-top: 16px">
      <template #header>
        <span>导入进度</span>
      </template>

      <div class="progress-info">
        <el-tag :type="statusTagType(currentProgress.status)" size="large">
          {{ statusLabel(currentProgress.status) }}
        </el-tag>
        <span style="margin-left: 12px">
          已处理 {{ currentProgress.records_processed }} 条记录
        </span>
        <span style="margin-left: 12px; color: #999">
          耗时 {{ currentProgress.elapsed_seconds.toFixed(1) }}s
        </span>
      </div>

      <el-progress
        :percentage="currentProgress.progress_percent"
        :status="progressStatus(currentProgress.status)"
        style="margin-top: 12px"
      />

      <div v-if="currentProgress.error_message" class="error-msg">
        <el-alert :title="currentProgress.error_message" type="error" show-icon :closable="false" />
      </div>

      <div v-if="currentProgress.validation_warnings.length" class="warnings" style="margin-top: 8px">
        <el-alert
          v-for="(w, i) in currentProgress.validation_warnings"
          :key="i"
          :title="w"
          type="warning"
          show-icon
          :closable="false"
          style="margin-top: 4px"
        />
      </div>
    </el-card>

    <!-- Batch List -->
    <el-card class="import-batches-card" shadow="hover" style="margin-top: 16px">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>导入批次</span>
          <el-button size="small" @click="loadBatches">刷新</el-button>
        </div>
      </template>

      <el-table :data="batches" stripe size="small" empty-text="暂无导入记录">
        <el-table-column prop="file_name" label="文件名" min-width="150" />
        <el-table-column prop="data_type" label="数据类型" width="120">
          <template #default="{ row }">
            {{ dataTypeLabel(row.data_type) }}
          </template>
        </el-table-column>
        <el-table-column prop="source_type" label="数据源" width="100" />
        <el-table-column prop="record_count" label="记录数" width="80" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="导入时间" width="160">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'completed'"
              type="danger"
              size="small"
              text
              @click="handleRollback(row.id)"
            >
              回滚
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import http from '@/utils/http'

const props = defineProps<{
  projectId: string
}>()

const form = reactive({
  sourceType: 'generic',
  dataType: '',
  year: new Date().getFullYear(),
})

const selectedFile = ref<File | null>(null)
const importing = ref(false)
const currentProgress = ref<any>(null)
const batches = ref<any[]>([])
const uploadRef = ref()

function handleFileChange(file: any) {
  selectedFile.value = file.raw
}

function handleFileRemove() {
  selectedFile.value = null
}

async function startImport() {
  if (!selectedFile.value || !form.dataType) return

  importing.value = true
  currentProgress.value = null

  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    formData.append('source_type', form.sourceType)
    formData.append('data_type', form.dataType)
    formData.append('year', String(form.year))

    const res = await http.post(
      `/api/projects/${props.projectId}/import`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    )

    const batch = res.data?.data || res.data
    ElMessage.success(`导入完成，共 ${batch.record_count} 条记录`)

    // Load progress
    await loadProgress(batch.id)
    await loadBatches()

    // Reset form
    selectedFile.value = null
    uploadRef.value?.clearFiles()
  } catch (err: any) {
    const msg = err.response?.data?.detail || err.response?.data?.message || '导入失败'
    ElMessage.error(msg)
  } finally {
    importing.value = false
  }
}

async function loadProgress(batchId: string) {
  try {
    const res = await http.get(
      `/api/projects/${props.projectId}/import/${batchId}/progress`
    )
    currentProgress.value = res.data?.data || res.data
  } catch {
    // ignore
  }
}

async function loadBatches() {
  try {
    const res = await http.get(
      `/api/projects/${props.projectId}/import/batches`
    )
    batches.value = res.data?.data || res.data || []
  } catch {
    batches.value = []
  }
}

async function handleRollback(batchId: string) {
  try {
    await ElMessageBox.confirm('确定要回滚此批次导入吗？所有导入的记录将被删除。', '确认回滚', {
      type: 'warning',
    })
    await http.post(`/api/projects/${props.projectId}/import/${batchId}/rollback`)
    ElMessage.success('回滚成功')
    await loadBatches()
  } catch {
    // cancelled or error
  }
}

function statusTagType(status: string) {
  const map: Record<string, string> = {
    pending: 'info',
    processing: 'warning',
    completed: 'success',
    failed: 'danger',
    rolled_back: 'info',
  }
  return map[status] || 'info'
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    pending: '待处理',
    processing: '处理中',
    completed: '已完成',
    failed: '失败',
    rolled_back: '已回滚',
  }
  return map[status] || status
}

function progressStatus(status: string) {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'exception'
  return undefined
}

function dataTypeLabel(dt: string) {
  const map: Record<string, string> = {
    tb_balance: '余额表',
    tb_ledger: '序时账',
    tb_aux_balance: '辅助余额表',
    tb_aux_ledger: '辅助明细账',
  }
  return map[dt] || dt
}

function formatDate(d: string) {
  if (!d) return ''
  return new Date(d).toLocaleString('zh-CN')
}

onMounted(() => {
  loadBatches()
})
</script>

<style scoped>
.data-import-panel {
  padding: 16px;
}
.error-msg {
  margin-top: 12px;
}
</style>
