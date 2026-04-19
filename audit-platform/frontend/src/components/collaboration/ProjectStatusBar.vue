<template>
  <div class="gt-project-status-bar">
    <div class="status-header">
      <span class="status-title">项目状态</span>
      <el-button
        size="small"
        text
        @click="showGateDialog = true"
        title="查看门控条件"
      >
        <el-icon><InfoFilled /></el-icon>
        门控条件
      </el-button>
    </div>

    <el-steps :active="currentStepIndex" finish-status="success" align-center>
      <el-step
        v-for="(step, index) in steps"
        :key="index"
        :title="step.label"
        :description="step.description"
        @click="onStepClick(step, index)"
      />
    </el-steps>

    <!-- 门控条件弹窗 -->
    <el-dialog append-to-body v-model="showGateDialog" title="门控条件检查" width="600px">
      <el-table :data="gateItems" stripe>
        <el-table-column prop="phase" label="阶段" width="150" />
        <el-table-column prop="condition" label="门控条件" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.passed ? 'success' : 'danger'" size="small">
              {{ row.passed ? '已满足' : '未满足' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button type="primary" @click="showGateDialog = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'

interface ProjectStatus {
  project_id: string
  current_phase: string
}

interface GateItem {
  phase: string
  condition: string
  passed: boolean
}

const props = defineProps<{
  projectStatus: ProjectStatus
}>()

const showGateDialog = ref(false)

const steps = [
  {
    key: 'planning',
    label: '计划编制',
    description: '审计计划与策略',
    nextGate: 'field_entry',
  },
  {
    key: 'field_entry',
    label: '外勤工作',
    description: '实质性程序执行',
    nextGate: 'review_draft',
  },
  {
    key: 'review_draft',
    label: '复核编制',
    description: '底稿自复与经理复核',
    nextGate: 'level_1_review',
  },
  {
    key: 'level_1_review',
    label: '一级复核',
    description: '经理级复核',
    nextGate: 'level_2_review',
  },
  {
    key: 'level_2_review',
    label: '二级复核',
    description: '合伙人级复核',
    nextGate: 'completed',
  },
  {
    key: 'completed',
    label: '完成',
    description: '报告签发与归档',
    nextGate: null,
  },
]

const currentStepIndex = computed(() => {
  const phase = props.projectStatus?.current_phase || 'planning'
  const index = steps.findIndex(s => s.key === phase)
  return index >= 0 ? index : 0
})

// 门控条件映射
const gateItems = computed((): GateItem[] => {
  const phase = props.projectStatus?.current_phase || 'planning'
  const items: GateItem[] = []

  if (['field_entry', 'review_draft', 'level_1_review'].includes(phase)) {
    items.push({
      phase: '外勤工作',
      condition: '审计计划已审批通过',
      passed: phase !== 'planning',
    })
  }
  if (['review_draft', 'level_1_review', 'level_2_review'].includes(phase)) {
    items.push({
      phase: '复核编制',
      condition: '所有底稿编制完成并自复',
      passed: phase === 'level_1_review' || phase === 'level_2_review',
    })
  }
  if (['level_1_review', 'level_2_review'].includes(phase)) {
    items.push({
      phase: '一级复核',
      condition: '经理已完成一级复核签字',
      passed: phase === 'level_2_review',
    })
  }
  if (phase === 'level_2_review') {
    items.push({
      phase: '二级复核',
      condition: '合伙人已完成二级复核签字',
      passed: false,
    })
  }
  if (phase === 'completed') {
    items.push({
      phase: '完成',
      condition: '审计报告已签发',
      passed: true,
    })
  }

  return items
})

function onStepClick(step: typeof steps[0], index: number) {
  // 只能前进到当前阶段的下一阶段或已完成的阶段
  if (index <= currentStepIndex.value) {
    return
  }
  // 提示用户不可跳过门控
  const gate = gateItems.value.find(g => g.phase === steps[index - 1]?.label)
  if (gate && !gate.passed) {
    return
  }
}
</script>

<style scoped>
.gt-project-status-bar {
  padding: 16px;
  background: #fff;
  border-radius: 4px;
}

.status-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.status-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.el-steps {
  margin-top: 8px;
}
</style>
