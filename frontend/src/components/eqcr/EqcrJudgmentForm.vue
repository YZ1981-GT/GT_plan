<template>
  <div class="eqcr-judgment-form">
    <el-tabs v-model="activeTab" type="border-card">
      <el-tab-pane
        v-for="dim in dimensions"
        :key="dim.key"
        :name="dim.key"
        :label="dim.label"
      >
        <template #label>
          <span :class="{ 'fail-tab': dim.conclusion === 'fail' }">
            {{ dim.label }}
            <el-icon v-if="dim.conclusion === 'fail'" color="#F56C6C"><WarningFilled /></el-icon>
          </span>
        </template>

        <el-form :disabled="props.readonly" label-position="top">
          <el-form-item label="结论">
            <el-select
              v-model="dim.conclusion"
              placeholder="请选择结论"
              :class="{ 'fail-select': dim.conclusion === 'fail' }"
            >
              <el-option label="通过 (Pass)" value="pass" />
              <el-option label="保留意见 (Qualified)" value="qualified" />
              <el-option label="不通过 (Fail)" value="fail" />
            </el-select>
          </el-form-item>

          <el-form-item label="判断依据">
            <el-input
              v-model="dim.rationale"
              type="textarea"
              :rows="4"
              placeholder="请输入判断依据..."
            />
          </el-form-item>

          <el-form-item label="引用底稿">
            <el-select
              v-model="dim.referenced_wps"
              multiple
              filterable
              allow-create
              placeholder="选择或输入底稿编号"
            >
              <el-option
                v-for="wp in availableWps"
                :key="wp"
                :label="wp"
                :value="wp"
              />
            </el-select>
          </el-form-item>

          <el-form-item label="风险等级">
            <el-radio-group v-model="dim.risk_level">
              <el-radio value="high">高</el-radio>
              <el-radio value="medium">中</el-radio>
              <el-radio value="low">低</el-radio>
            </el-radio-group>
          </el-form-item>
        </el-form>
      </el-tab-pane>
    </el-tabs>

    <div v-if="!props.readonly" class="form-actions">
      <el-button
        type="primary"
        :disabled="!allDimensionsFilled"
        @click="handleSubmit"
      >
        提交判断
      </el-button>
      <span v-if="!allDimensionsFilled" class="hint-text">
        请填写全部 5 个维度的结论后提交
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { WarningFilled } from '@element-plus/icons-vue'
import axios from 'axios'
import { handleApiError } from '@/utils/errorHandler'

interface JudgmentDimension {
  key: string
  label: string
  conclusion: 'pass' | 'qualified' | 'fail' | ''
  rationale: string
  referenced_wps: string[]
  risk_level: 'high' | 'medium' | 'low'
}

interface Props {
  projectId: string
  readonly?: boolean
}

interface Emits {
  (e: 'submitted', judgment: { dimensions: JudgmentDimension[]; canSign: boolean }): void
}

const props = withDefaults(defineProps<Props>(), {
  readonly: false,
})

const emit = defineEmits<Emits>()

const activeTab = ref('material_misstatement')
const availableWps = ref<string[]>([])

const dimensions = ref<JudgmentDimension[]>([
  { key: 'material_misstatement', label: '重大错报', conclusion: '', rationale: '', referenced_wps: [], risk_level: 'medium' },
  { key: 'going_concern', label: '持续经营', conclusion: '', rationale: '', referenced_wps: [], risk_level: 'medium' },
  { key: 'key_audit_matters', label: '关键审计事项', conclusion: '', rationale: '', referenced_wps: [], risk_level: 'medium' },
  { key: 'other_information', label: '其他信息', conclusion: '', rationale: '', referenced_wps: [], risk_level: 'medium' },
  { key: 'audit_report', label: '审计报告', conclusion: '', rationale: '', referenced_wps: [], risk_level: 'medium' },
])

const allDimensionsFilled = computed(() => {
  return dimensions.value.every(d => d.conclusion !== '')
})

onMounted(async () => {
  await loadExistingJudgment()
})

async function loadExistingJudgment() {
  try {
    const res = await axios.get(`/api/projects/${props.projectId}/eqcr-judgment`)
    if (res.data?.judgment?.dimensions) {
      const existing = res.data.judgment.dimensions
      for (const dim of existing) {
        const target = dimensions.value.find(d => d.key === dim.key)
        if (target) {
          target.conclusion = dim.conclusion || ''
          target.rationale = dim.rationale || ''
          target.referenced_wps = dim.referenced_wps || []
          target.risk_level = dim.risk_level || 'medium'
        }
      }
    }
  } catch {
    // No existing judgment
  }
}

async function handleSubmit() {
  if (!allDimensionsFilled.value) {
    ElMessage.warning('请填写全部 5 个维度的结论')
    return
  }

  try {
    const payload = {
      dimensions: dimensions.value.map(d => ({
        key: d.key,
        conclusion: d.conclusion,
        rationale: d.rationale,
        referenced_wps: d.referenced_wps,
        risk_level: d.risk_level,
      })),
    }

    const res = await axios.post(
      `/api/projects/${props.projectId}/eqcr-judgment`,
      payload,
    )

    const canSign = res.data.can_sign
    ElMessage.success(canSign ? '判断已提交，可以签字' : '判断已提交，存在不通过维度，无法签字')
    emit('submitted', { dimensions: dimensions.value, canSign })
  } catch (err: any) {
    handleApiError(err, '提交判断')
  }
}
</script>

<style scoped>
.eqcr-judgment-form {
  padding: 16px;
}

.fail-tab {
  color: #F56C6C;
  font-weight: 600;
}

.fail-select :deep(.el-input__wrapper) {
  border-color: #F56C6C;
  box-shadow: 0 0 0 1px #F56C6C inset;
}

.form-actions {
  margin-top: 20px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.hint-text {
  color: #909399;
  font-size: 13px;
}
</style>
