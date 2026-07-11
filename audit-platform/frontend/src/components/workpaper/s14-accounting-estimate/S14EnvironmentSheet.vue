<template>
  <div class="s14-environment">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>审计目标</template>
      <div class="audit-objective-text">
        了解被审计单位及其环境中与会计估计相关的方面，包括行业与监管状况、会计估计的性质、管理层作出估计的方法、重大假设与数据来源，以及上期估计的回顾性复核，为识别和评估重大错报风险奠定基础（CAS 1321）。
      </div>
    </el-alert>

    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>S14-1 了解被审计单位及其环境（会计估计相关）</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiAssist"
            >AI辅助</el-button>
            <el-button
              size="small"
              @click="handleOpenReview('s14-1-environment', '了解被审计单位及其环境')"
            >复核</el-button>
          </div>
        </div>
      </template>

      <!-- 方法论上下文（琥珀色左边线） -->
      <div class="methodology-context">
        <p>《中国注册会计师审计准则第1321号——审计会计估计和相关披露》第12条：注册会计师应当了解被审计单位及其环境，包括被审计单位的内部控制。了解内容包括适用的财务报告编制基础的要求、行业状况及监管环境、被审计单位的性质等。</p>
      </div>

      <el-table
        :data="evaluationItems"
        border
        style="width: 100%; font-size: 13px"
      >
        <el-table-column type="index" label="序号" width="60" align="center" />
        <el-table-column prop="category" label="了解方面" width="160">
          <template #default="{ row }">
            <span class="category-text">{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="question" label="评价要点" min-width="280">
          <template #default="{ row }">
            <span>{{ row.question }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="applicable" label="是否适用" width="100" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.applicable"
              size="small"
              placeholder="—"
              style="width: 80px"
            >
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="N/A" value="N/A" />
            </el-select>
            <span v-else>{{ row.applicable || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="evaluation" label="评价情况" min-width="220">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.evaluation"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              size="small"
              placeholder="填写评价情况"
            />
            <span v-else class="wrap-text">{{ row.evaluation || '—' }}</span>
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
        placeholder="填写关于了解被审计单位环境的审计结论"
      />
      <div v-else class="conclusion-text">{{ auditConclusion || '—' }}</div>
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-hints">
      <summary>编制提示</summary>
      <p>1. 了解被审计单位的行业特征及监管环境对会计估计的影响。</p>
      <p>2. 了解管理层如何识别需要作出会计估计的交易、事项和情况。</p>
      <p>3. 了解管理层用于作出会计估计的方法及其是否发生变化。</p>
      <p>4. 了解被审计单位是否利用专家作出会计估计。</p>
      <p>5. 了解上期会计估计的结果或其后续重新估计的结果。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * S14EnvironmentSheet.vue — S14-1 了解被审计单位及其环境（会计估计相关）
 *
 * 功能：
 * - 展示 S14-1 了解环境评价表（35×11 checklist 格式）
 * - 方法论上下文区块（琥珀色左边线）
 * - GtIndexChip 跨底稿引用
 * - 审计结论区 el-card + AI 按钮
 * - readonly 禁编辑
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 4.4
 * Requirements: 5.1, 5.3
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

// ─── 评价项目（实际从 render-config 加载，此为骨架数据） ─────────────────────

const evaluationItems = ref([
  {
    category: '行业状况',
    question: '被审计单位所处行业对会计估计有何特殊要求（如金融工具估值、保险精算）？',
    applicable: '是',
    evaluation: '',
    ref: 'B10',
  },
  {
    category: '行业状况',
    question: '行业监管环境是否对会计估计的方法或假设施加了限制？',
    applicable: '是',
    evaluation: '',
    ref: '',
  },
  {
    category: '会计估计性质',
    question: '被审计单位涉及哪些类型的会计估计（如公允价值、资产减值、预计负债、折旧）？',
    applicable: '是',
    evaluation: '',
    ref: '',
  },
  {
    category: '会计估计性质',
    question: '管理层如何识别财务报表中需要作出会计估计的交易、事项和情况？',
    applicable: '是',
    evaluation: '',
    ref: '',
  },
  {
    category: '估计方法',
    question: '管理层用于作出会计估计的方法是否与上期一致？如有变化，原因是什么？',
    applicable: '是',
    evaluation: '',
    ref: '',
  },
  {
    category: '估计方法',
    question: '管理层是否使用了模型来作出会计估计？模型的复杂程度如何？',
    applicable: '是',
    evaluation: '',
    ref: '',
  },
  {
    category: '重大假设',
    question: '管理层在作出会计估计时使用了哪些重大假设？这些假设是否合理？',
    applicable: '是',
    evaluation: '',
    ref: 'B22',
  },
  {
    category: '数据来源',
    question: '管理层用于作出会计估计的数据来源是否可靠、相关和充分？',
    applicable: '是',
    evaluation: '',
    ref: '',
  },
  {
    category: '上期估计',
    question: '上期会计估计的结果或后续重新估计的结果是否存在重大差异（回顾性复核）？',
    applicable: '是',
    evaluation: '',
    ref: 'B40',
  },
  {
    category: '利用专家',
    question: '管理层在作出会计估计时是否利用了管理层的专家？',
    applicable: '是',
    evaluation: '',
    ref: 'S12',
  },
])

// ─── 审计结论 ────────────────────────────────────────────────────────────────

const auditConclusion = ref('')

// ─── AI 辅助 ─────────────────────────────────────────────────────────────────

function handleAiAssist() {
  // TODO: 调用 AI 辅助生成评价说明
}

function handleAiConclusion() {
  // TODO: 调用 AI 辅助生成审计结论
}
</script>

<style scoped>
.s14-environment {
  padding: 12px;
}

.audit-objective {
  margin-bottom: 12px;
}

.audit-objective-text {
  font-size: 13px;
  line-height: 1.6;
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
