<template>
  <div class="going-concern-panel">
    <h3>持续经营评估</h3>

    <el-tabs v-model="activeTab">
      <!-- Tab 1: 风险指标检查清单 -->
      <el-tab-pane label="风险指标检查清单" name="indicators">
        <div class="indicator-header">
          <span>完成进度：{{ completionRate }}%</span>
          <el-progress :percentage="completionRate" :stroke-width="10" style="width: 200px" />
        </div>

        <div v-for="group in groupedIndicators" :key="group.category" class="indicator-group">
          <h4 class="group-title">{{ group.category }}</h4>
          <el-table :data="group.items" stripe size="small">
            <el-table-column prop="item_code" label="编号" width="80" />
            <el-table-column prop="description" label="检查项" min-width="240" />
            <el-table-column label="状态" width="120">
              <template #default="{ row }">
                <el-switch
                  v-model="row.is_completed"
                  :disabled="readonly"
                  active-text="通过"
                  inactive-text="待检"
                  @change="handleIndicatorChange(row)"
                />
              </template>
            </el-table-column>
            <el-table-column label="备注" min-width="160">
              <template #default="{ row }">
                <el-input
                  v-if="!readonly"
                  v-model="row.notes"
                  size="small"
                  placeholder="备注"
                  @blur="saveIndicator(row)"
                />
                <span v-else>{{ row.notes }}</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <!-- Tab 2: 评价记录 -->
      <el-tab-pane label="评价记录" name="evaluations">
        <div class="eval-actions">
          <el-button type="primary" @click="showEvalDialog = true">新建评价</el-button>
        </div>

        <el-table :data="evaluations" stripe>
          <el-table-column prop="created_at" label="评价时间" width="160" />
          <el-table-column prop="conclusion_type" label="结论类型" width="180">
            <template #default="{ row }">
              <el-tag :type="conclusionTagType(row.conclusion_type)">
                {{ conclusionLabel(row.conclusion_type) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="management_evaluation" label="管理层评价" min-width="200" show-overflow-tooltip />
          <el-table-column prop="auditor_evaluation" label="审计师评价" min-width="200" show-overflow-tooltip />
          <el-table-column prop="report_impact" label="报告影响" min-width="160" show-overflow-tooltip />
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 新建评价弹窗 -->
    <el-dialog v-model="showEvalDialog" title="新建持续经营评价" width="650px">
      <el-form :model="evalForm" label-width="130px">
        <el-form-item label="管理层评价" required>
          <el-input
            v-model="evalForm.management_evaluation"
            type="textarea"
            :rows="3"
            placeholder="管理层对持续经营能力的评价"
          />
        </el-form-item>
        <el-form-item label="审计师评价" required>
          <el-input
            v-model="evalForm.auditor_evaluation"
            type="textarea"
            :rows="3"
            placeholder="审计师对持续经营能力的独立评价"
          />
        </el-form-item>
        <el-form-item label="结论类型" required>
          <el-select v-model="evalForm.conclusion_type" placeholder="请选择结论" style="width: 100%">
            <el-option label="无重大不确定性" value="NO_ISSUES" />
            <el-option label="存在缓解因素" value="MITIGATING_FACTORS" />
            <el-option label="存在重大不确定性" value="GOING_CONCERN_UNCERTAINTY" />
            <el-option label="持续经营存在重大疑虑" value="ADVERSE" />
          </el-select>
        </el-form-item>
        <el-form-item label="对报告的影响">
          <el-input
            v-model="evalForm.report_impact"
            type="textarea"
            :rows="3"
            placeholder="对审计报告的影响说明"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEvalDialog = false">取消</el-button>
        <el-button type="primary" @click="handleCreateEval">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { goingConcernApi } from '@/services/collaborationApi'

const projectId = 'current-project-id'
const gcId = ref('')

const activeTab = ref('indicators')
const showEvalDialog = ref(false)
const readonly = ref(false)

const indicators = ref<any[]>([])
const evaluations = ref<any[]>([])

const evalForm = ref({
  management_evaluation: '',
  auditor_evaluation: '',
  conclusion_type: '',
  report_impact: '',
})

const completionRate = computed(() => {
  if (indicators.value.length === 0) return 0
  const done = indicators.value.filter((i) => i.is_completed).length
  return Math.round((done / indicators.value.length) * 100)
})

const groupedIndicators = computed(() => {
  const groups: Record<string, any[]> = {}
  indicators.value.forEach((i) => {
    const cat = i.category || '未分类'
    if (!groups[cat]) groups[cat] = []
    groups[cat].push(i)
  })
  return Object.entries(groups).map(([category, items]) => ({ category, items }))
})

const conclusionLabel = (t: string) => {
  const map: Record<string, string> = {
    NO_ISSUES: '无重大不确定性',
    MITIGATING_FACTORS: '存在缓解因素',
    GOING_CONCERN_UNCERTAINTY: '存在重大不确定性',
    ADVERSE: '持续经营存在重大疑虑',
  }
  return map[t] || t
}

const conclusionTagType = (t: string) => {
  const map: Record<string, string> = {
    NO_ISSUES: 'success',
    MITIGATING_FACTORS: 'warning',
    GOING_CONCERN_UNCERTAINTY: 'danger',
    ADVERSE: 'danger',
  }
  return map[t] || 'info'
}

onMounted(async () => {
  try {
    // Initialize if needed
    await goingConcernApi.init(projectId)
    const evalData = await goingConcernApi.getEvaluation(projectId)
    evaluations.value = evalData?.data ? [evalData.data] : []
    if (evalData?.data?.id) {
      gcId.value = evalData.data.id
      const { data: indData } = await goingConcernApi.getIndicators(projectId, gcId.value)
      indicators.value = indData ?? []
    }
  } catch {
    // graceful fallback
    indicators.value = [
      { id: '1', item_code: 'GC01', category: '财务指标', description: '资产负债率超过80%', is_completed: false, notes: '' },
      { id: '2', item_code: 'GC02', category: '财务指标', description: '连续两年亏损', is_completed: true, notes: '2024年已扭亏' },
      { id: '3', item_code: 'GC03', category: '经营指标', description: '主要客户流失超过30%', is_completed: false, notes: '' },
    ]
    evaluations.value = []
  }
})

async function handleIndicatorChange(row: any) {
  await saveIndicator(row)
}

async function saveIndicator(row: any) {
  try {
    await goingConcernApi.updateIndicator(projectId, gcId.value || '0', row.id, {
      is_completed: row.is_completed,
      notes: row.notes,
    })
  } catch {
    // graceful fallback
  }
}

async function handleCreateEval() {
  if (!evalForm.value.management_evaluation || !evalForm.value.auditor_evaluation || !evalForm.value.conclusion_type) {
    ElMessage.warning('请填写必填项')
    return
  }
  try {
    const { data } = await goingConcernApi.createEvaluation(projectId, evalForm.value)
    evaluations.value.unshift(data)
    ElMessage.success('评价已创建')
    showEvalDialog.value = false
    evalForm.value = { management_evaluation: '', auditor_evaluation: '', conclusion_type: '', report_impact: '' }
  } catch {
    ElMessage.error('创建失败')
  }
}
</script>

<style scoped>
.going-concern-panel {}
.indicator-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  color: #606266;
  font-size: 14px;
}
.indicator-group { margin-bottom: 20px; }
.group-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
  border-left: 3px solid #409EFF;
  padding-left: 8px;
}
.eval-actions { margin-bottom: 12px; }
</style>
