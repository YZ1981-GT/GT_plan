<template>
  <div class="sampling-panel">
    <el-tabs v-model="activeTab">
      <!-- 抽样配置 Tab -->
      <el-tab-pane label="抽样配置" name="configs">
        <div class="toolbar">
          <el-button type="primary" size="small" @click="showConfigDialog = true">
            新建配置
          </el-button>
        </div>
        <el-table :data="configs" stripe size="small" style="width: 100%">
          <el-table-column prop="config_name" label="配置名称" min-width="120" />
          <el-table-column prop="sampling_type" label="抽样类型" width="100">
            <template #default="{ row }">
              {{ row.sampling_type === 'statistical' ? '统计抽样' : '非统计抽样' }}
            </template>
          </el-table-column>
          <el-table-column prop="sampling_method" label="抽样方法" width="100">
            <template #default="{ row }">
              {{ methodLabel(row.sampling_method) }}
            </template>
          </el-table-column>
          <el-table-column prop="applicable_scenario" label="适用场景" width="100">
            <template #default="{ row }">
              {{ row.applicable_scenario === 'control_test' ? '控制测试' : '实质性测试' }}
            </template>
          </el-table-column>
          <el-table-column prop="calculated_sample_size" label="样本量" width="80" />
          <el-table-column label="操作" width="80">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="editConfig(row)">
                编辑
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 抽样记录 Tab -->
      <el-tab-pane label="抽样记录" name="records">
        <div class="toolbar">
          <el-button type="primary" size="small" @click="showRecordDialog = true">
            新建记录
          </el-button>
        </div>
        <el-table :data="records" stripe size="small" style="width: 100%">
          <el-table-column prop="sampling_purpose" label="抽样目的" min-width="150" />
          <el-table-column prop="population_description" label="总体描述" min-width="150" />
          <el-table-column prop="sample_size" label="样本量" width="80" />
          <el-table-column prop="deviations_found" label="偏差数" width="70" />
          <el-table-column label="错报金额" width="100">
            <template #default="{ row }">
              {{ row.misstatements_found != null ? Number(row.misstatements_found).toLocaleString() : '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="conclusion" label="结论" min-width="120" />
          <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="editRecord(row)">编辑</el-button>
              <el-button link type="warning" size="small" @click="musEvaluate(row)">MUS评价</el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- MUS评价结果 -->
        <div v-if="musResult" class="mus-result">
          <el-divider content-position="left">MUS评价结果</el-divider>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="推断错报">
              {{ Number(musResult.projected_misstatement).toLocaleString() }}
            </el-descriptions-item>
            <el-descriptions-item label="错报上限">
              {{ Number(musResult.upper_misstatement_limit).toLocaleString() }}
            </el-descriptions-item>
          </el-descriptions>
          <el-table v-if="musResult.details?.length" :data="musResult.details" size="small" style="margin-top: 8px">
            <el-table-column prop="book_value" label="账面价值" width="120" />
            <el-table-column prop="misstatement_amount" label="错报金额" width="120" />
            <el-table-column prop="tainting_factor" label="污染因子" width="100" />
            <el-table-column prop="projected_misstatement" label="推断错报" width="120" />
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 新建/编辑配置对话框 -->
    <el-dialog
      v-model="showConfigDialog"
      :title="editingConfig ? '编辑抽样配置' : '新建抽样配置'"
      width="560px"
    >
      <el-form :model="configForm" label-width="120px" size="small">
        <el-form-item label="配置名称" required>
          <el-input v-model="configForm.config_name" />
        </el-form-item>
        <el-form-item label="抽样类型">
          <el-select v-model="configForm.sampling_type" style="width: 100%">
            <el-option label="统计抽样" value="statistical" />
            <el-option label="非统计抽样" value="non_statistical" />
          </el-select>
        </el-form-item>
        <el-form-item label="抽样方法">
          <el-select v-model="configForm.sampling_method" style="width: 100%">
            <el-option label="货币单元抽样(MUS)" value="mus" />
            <el-option label="属性抽样" value="attribute" />
            <el-option label="随机抽样" value="random" />
            <el-option label="系统抽样" value="systematic" />
            <el-option label="分层抽样" value="stratified" />
          </el-select>
        </el-form-item>
        <el-form-item label="适用场景">
          <el-select v-model="configForm.applicable_scenario" style="width: 100%">
            <el-option label="控制测试" value="control_test" />
            <el-option label="实质性测试" value="substantive_test" />
          </el-select>
        </el-form-item>
        <el-form-item label="置信水平">
          <el-select v-model="configForm.confidence_level" style="width: 100%">
            <el-option :label="'90%'" :value="0.90" />
            <el-option :label="'95%'" :value="0.95" />
            <el-option :label="'99%'" :value="0.99" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="configForm.sampling_method === 'attribute'" label="可容忍偏差率">
          <el-input-number v-model="configForm.tolerable_deviation_rate" :min="0" :max="1" :step="0.01" :precision="4" style="width: 100%" />
        </el-form-item>
        <el-form-item v-if="configForm.sampling_method === 'attribute'" label="预期偏差率">
          <el-input-number v-model="configForm.expected_deviation_rate" :min="0" :max="1" :step="0.01" :precision="4" style="width: 100%" />
        </el-form-item>
        <el-form-item v-if="configForm.sampling_method === 'mus'" label="可容忍错报">
          <el-input-number v-model="configForm.tolerable_misstatement" :min="0" :step="1000" style="width: 100%" />
        </el-form-item>
        <el-form-item v-if="configForm.sampling_method === 'mus'" label="总体金额">
          <el-input-number v-model="configForm.population_amount" :min="0" :step="10000" style="width: 100%" />
        </el-form-item>
        <el-form-item label="总体数量">
          <el-input-number v-model="configForm.population_count" :min="0" style="width: 100%" />
        </el-form-item>
        <el-form-item v-if="calculatedSize !== null" label="计算样本量">
          <el-tag type="success" size="large">{{ calculatedSize }}</el-tag>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button size="small" @click="previewSampleSize">计算样本量</el-button>
        <el-button size="small" @click="showConfigDialog = false">取消</el-button>
        <el-button type="primary" size="small" @click="saveConfig">保存</el-button>
      </template>
    </el-dialog>

    <!-- 新建/编辑记录对话框 -->
    <el-dialog
      v-model="showRecordDialog"
      :title="editingRecord ? '编辑抽样记录' : '新建抽样记录'"
      width="560px"
    >
      <el-form :model="recordForm" label-width="120px" size="small">
        <el-form-item label="抽样目的" required>
          <el-input v-model="recordForm.sampling_purpose" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="总体描述" required>
          <el-input v-model="recordForm.population_description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="总体金额">
          <el-input-number v-model="recordForm.population_total_amount" :min="0" :step="10000" style="width: 100%" />
        </el-form-item>
        <el-form-item label="总体数量">
          <el-input-number v-model="recordForm.population_total_count" :min="0" style="width: 100%" />
        </el-form-item>
        <el-form-item label="样本量" required>
          <el-input-number v-model="recordForm.sample_size" :min="1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="抽样方法说明">
          <el-input v-model="recordForm.sampling_method_description" />
        </el-form-item>
        <el-form-item label="偏差数">
          <el-input-number v-model="recordForm.deviations_found" :min="0" style="width: 100%" />
        </el-form-item>
        <el-form-item label="错报金额">
          <el-input-number v-model="recordForm.misstatements_found" :min="0" :step="100" style="width: 100%" />
        </el-form-item>
        <el-form-item label="结论">
          <el-input v-model="recordForm.conclusion" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button size="small" @click="showRecordDialog = false">取消</el-button>
        <el-button type="primary" size="small" @click="saveRecord">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  listSamplingConfigs,
  createSamplingConfig,
  updateSamplingConfig,
  calculateSampleSize,
  listSamplingRecords,
  createSamplingRecord,
  updateSamplingRecord,
  musSamplingEvaluate,
} from '@/services/workpaperApi'

const props = defineProps<{
  projectId: string
  workingPaperId?: string
}>()

const activeTab = ref('configs')

// --- Config state ---
const configs = ref<any[]>([])
const showConfigDialog = ref(false)
const editingConfig = ref<any>(null)
const calculatedSize = ref<number | null>(null)
const configForm = ref({
  config_name: '',
  sampling_type: 'statistical',
  sampling_method: 'random',
  applicable_scenario: 'substantive_test',
  confidence_level: 0.95 as number | null,
  expected_deviation_rate: null as number | null,
  tolerable_deviation_rate: null as number | null,
  tolerable_misstatement: null as number | null,
  population_amount: null as number | null,
  population_count: null as number | null,
})

// --- Record state ---
const records = ref<any[]>([])
const showRecordDialog = ref(false)
const editingRecord = ref<any>(null)
const musResult = ref<any>(null)
const recordForm = ref({
  sampling_purpose: '',
  population_description: '',
  population_total_amount: null as number | null,
  population_total_count: null as number | null,
  sample_size: 30,
  sampling_method_description: '',
  deviations_found: null as number | null,
  misstatements_found: null as number | null,
  conclusion: '',
})

const methodLabel = (m: string) => {
  const map: Record<string, string> = {
    mus: 'MUS', attribute: '属性抽样', random: '随机抽样',
    systematic: '系统抽样', stratified: '分层抽样',
  }
  return map[m] || m
}

async function loadConfigs() {
  try { configs.value = await listSamplingConfigs(props.projectId) } catch { /* ignore */ }
}

async function loadRecords() {
  try { records.value = await listSamplingRecords(props.projectId, props.workingPaperId) } catch { /* ignore */ }
}

function editConfig(row: any) {
  editingConfig.value = row
  Object.assign(configForm.value, row)
  calculatedSize.value = row.calculated_sample_size
  showConfigDialog.value = true
}

function editRecord(row: any) {
  editingRecord.value = row
  Object.assign(recordForm.value, row)
  showRecordDialog.value = true
}

async function previewSampleSize() {
  try {
    const res = await calculateSampleSize(props.projectId, {
      method: configForm.value.sampling_method,
      ...configForm.value,
    })
    calculatedSize.value = res.calculated_size
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '计算失败')
  }
}

async function saveConfig() {
  try {
    if (editingConfig.value) {
      await updateSamplingConfig(props.projectId, editingConfig.value.id, configForm.value)
    } else {
      await createSamplingConfig(props.projectId, configForm.value)
    }
    showConfigDialog.value = false
    editingConfig.value = null
    calculatedSize.value = null
    await loadConfigs()
    ElMessage.success('保存成功')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  }
}

async function saveRecord() {
  try {
    if (editingRecord.value) {
      await updateSamplingRecord(props.projectId, editingRecord.value.id, recordForm.value)
    } else {
      await createSamplingRecord(props.projectId, recordForm.value)
    }
    showRecordDialog.value = false
    editingRecord.value = null
    await loadRecords()
    ElMessage.success('保存成功')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  }
}

async function musEvaluate(row: any) {
  // Simple prompt for MUS details — in production this would be a proper form
  const details = [{ book_value: 10000, misstatement_amount: 500 }]
  try {
    musResult.value = await musSamplingEvaluate(props.projectId, row.id, details)
    await loadRecords()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || 'MUS评价失败')
  }
}

onMounted(() => {
  loadConfigs()
  loadRecords()
})
</script>

<style scoped>
.sampling-panel { padding: 8px; }
.toolbar { margin-bottom: 12px; }
.mus-result { margin-top: 16px; }
</style>
