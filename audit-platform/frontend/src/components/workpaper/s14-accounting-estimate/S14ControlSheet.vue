<template>
  <div class="s14-control">
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>S14-2 了解与会计估计相关的控制</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiAssist"
            >AI辅助</el-button>
            <el-button
              size="small"
              @click="handleOpenReview('s14-2-control', '了解与会计估计相关的控制')"
            >复核</el-button>
          </div>
        </div>
      </template>

      <!-- 方法论上下文（琥珀色左边线） -->
      <div class="methodology-context">
        <p>《中国注册会计师审计准则第1321号》第14条：了解被审计单位与会计估计相关的内部控制，包括管理层对估计过程的监督、数据来源和假设的审查与批准机制、估计结果与实际结果的比较分析控制等。</p>
      </div>

      <el-table
        :data="controlItems"
        border
        style="width: 100%; font-size: 13px"
      >
        <el-table-column type="index" label="序号" width="60" align="center" />
        <el-table-column prop="controlArea" label="控制领域" width="160">
          <template #default="{ row }">
            <span class="category-text">{{ row.controlArea }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="controlPoint" label="控制要点" min-width="280">
          <template #default="{ row }">
            <span>{{ row.controlPoint }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="exists" label="是否存在" width="100" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.exists"
              size="small"
              placeholder="—"
              style="width: 80px"
            >
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="不确定" value="不确定" />
            </el-select>
            <span v-else>{{ row.exists || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="effectiveDesign" label="设计有效性" width="110" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.effectiveDesign"
              size="small"
              placeholder="—"
              style="width: 90px"
            >
              <el-option label="有效" value="有效" />
              <el-option label="无效" value="无效" />
              <el-option label="N/A" value="N/A" />
            </el-select>
            <span v-else>{{ row.effectiveDesign || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="了解情况说明" min-width="220">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.description"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              size="small"
              placeholder="填写了解情况"
            />
            <span v-else class="wrap-text">{{ row.description || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="ref" label="索引" width="100" align="center">
          <template #default="{ row }">
            <GtIndexChip v-if="row.ref" :value="row.ref" />
            <span v-else>—</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-section conclusion-card">
      <template #header>
        <div class="section-header">
          <span>审计结论</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiConclusion"
            >AI辅助</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-if="!isReadonly"
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="填写关于会计估计相关控制的审计结论"
      />
      <div v-else class="conclusion-text">{{ auditConclusion || '—' }}</div>
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-hints">
      <summary>编制提示</summary>
      <p>1. 了解管理层对会计估计过程的监督和审查机制。</p>
      <p>2. 了解管理层如何确保用于会计估计的数据的完整性和准确性。</p>
      <p>3. 了解职责分离情况——估计的编制者与审查者是否独立。</p>
      <p>4. 了解信息系统中与会计估计相关的自动化控制。</p>
      <p>5. 了解管理层如何将估计结果与后续实际结果进行比较分析。</p>
      <p>6. 评估上述控制的设计是否有效，并考虑是否需要测试控制的运行有效性。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * S14ControlSheet.vue — S14-2 了解与会计估计相关的控制
 *
 * 功能：
 * - 展示 S14-2 内部控制了解评价表（81×11 checklist 格式）
 * - 方法论上下文区块（琥珀色左边线）
 * - GtIndexChip 跨底稿引用
 * - 审计结论区 el-card + AI 按钮
 * - readonly 禁编辑
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 4.4
 * Requirements: 5.1
 */
import { ref, inject } from 'vue'
import { defineAsyncComponent } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'

const GtIndexChip = defineAsyncComponent(() => import('../GtIndexChip.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

// ─── 复核对话 ────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog')

function handleOpenReview(sectionId: string, label: string) {
  openReviewDialog?.(sectionId, label)
}

// ─── 控制评价项目（实际从 render-config 加载，此为骨架数据） ─────────────────

const controlItems = ref([
  {
    controlArea: '估计过程监督',
    controlPoint: '管理层是否建立了对会计估计过程进行监督的机制（包括使用模型的情况）？',
    exists: '是',
    effectiveDesign: '',
    description: '',
    ref: '',
  },
  {
    controlArea: '估计过程监督',
    controlPoint: '是否由具有胜任能力的人员编制会计估计，并由适当管理层审查？',
    exists: '是',
    effectiveDesign: '',
    description: '',
    ref: '',
  },
  {
    controlArea: '数据完整性',
    controlPoint: '管理层如何确保用于作出会计估计的数据的完整性？',
    exists: '是',
    effectiveDesign: '',
    description: '',
    ref: '',
  },
  {
    controlArea: '数据完整性',
    controlPoint: '是否存在对用于作出会计估计的外部数据来源进行验证的控制？',
    exists: '',
    effectiveDesign: '',
    description: '',
    ref: '',
  },
  {
    controlArea: '假设审查',
    controlPoint: '管理层如何审查和批准用于作出会计估计的重大假设？',
    exists: '是',
    effectiveDesign: '',
    description: '',
    ref: '',
  },
  {
    controlArea: '假设审查',
    controlPoint: '管理层是否定期评估假设是否仍然适当（包括是否应当变更假设）？',
    exists: '',
    effectiveDesign: '',
    description: '',
    ref: '',
  },
  {
    controlArea: '模型控制',
    controlPoint: '是否对用于作出会计估计的模型建立了适当的控制，包括模型的验证和更新？',
    exists: '',
    effectiveDesign: '',
    description: '',
    ref: '',
  },
  {
    controlArea: '职责分离',
    controlPoint: '会计估计的编制与审查职责是否恰当分离？',
    exists: '是',
    effectiveDesign: '',
    description: '',
    ref: '',
  },
  {
    controlArea: '信息系统',
    controlPoint: '信息系统中与会计估计相关的应用控制和一般控制是否有效？',
    exists: '',
    effectiveDesign: '',
    description: '',
    ref: 'C22',
  },
  {
    controlArea: '回顾性分析',
    controlPoint: '管理层是否将上期会计估计的结果与实际结果进行比较，并据此评估本期估计过程？',
    exists: '是',
    effectiveDesign: '',
    description: '',
    ref: '',
  },
  {
    controlArea: '治理层沟通',
    controlPoint: '管理层是否就重大会计估计事项与治理层进行沟通？',
    exists: '',
    effectiveDesign: '',
    description: '',
    ref: '',
  },
])

// ─── 审计结论 ────────────────────────────────────────────────────────────────

const auditConclusion = ref('')

// ─── AI 辅助 ─────────────────────────────────────────────────────────────────

function handleAiAssist() {
  // TODO: 调用 AI 辅助生成了解说明
}

function handleAiConclusion() {
  // TODO: 调用 AI 辅助生成审计结论
}
</script>

<style scoped>
.s14-control {
  padding: 12px;
}

.audit-section {
  margin-bottom: 16px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.methodology-context {
  margin-bottom: 16px;
  padding: 12px 16px;
  border-left: 4px solid #e6a23c;
  background-color: #fdf6ec;
  font-size: 13px;
  line-height: 1.6;
  color: #606266;
}

.category-text {
  font-size: 12px;
  color: #606266;
}

.wrap-text {
  white-space: pre-wrap;
  font-size: 13px;
}

.conclusion-card {
  margin-top: 16px;
}

.conclusion-text {
  white-space: pre-wrap;
  font-size: 13px;
  line-height: 1.6;
  color: #303133;
}

.edit-hints {
  margin-top: 16px;
  font-size: 12px;
  color: #909399;
}

.edit-hints summary {
  cursor: pointer;
  user-select: none;
}

.edit-hints p {
  margin: 4px 0;
  line-height: 1.5;
}
</style>
