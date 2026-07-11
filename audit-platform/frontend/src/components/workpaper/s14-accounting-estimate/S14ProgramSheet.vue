<template>
  <div class="s14-program">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>审计目标</template>
      <div class="audit-objective-text">
        了解与会计估计相关的环境与内部控制，识别和评估会计估计的重大错报风险并设计实施应对程序，评价管理层会计估计的合理性、是否存在管理层偏向，以及相关披露是否符合适用的财务报告编制基础（CAS 1321）。
      </div>
    </el-alert>

    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>S14 会计估计和相关披露程序表</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiAssist"
            >AI辅助</el-button>
            <el-button
              size="small"
              @click="handleOpenReview('s14-program', '会计估计程序表')"
            >复核</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="programSteps"
        border
        style="width: 100%; font-size: 13px"
      >
        <el-table-column type="index" label="序号" width="60" align="center" />
        <el-table-column prop="category" label="类别" width="120">
          <template #default="{ row }">
            <span class="category-text">{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="procedure" label="审计程序" min-width="320">
          <template #default="{ row }">
            <span>{{ row.procedure }}</span>
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
        <el-table-column prop="checkMethod" label="核查方式" width="120" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.checkMethod"
              size="small"
              placeholder="—"
              style="width: 100px"
            >
              <el-option label="检查" value="检查" />
              <el-option label="询问" value="询问" />
              <el-option label="观察" value="观察" />
              <el-option label="函证" value="函证" />
              <el-option label="重新计算" value="重新计算" />
              <el-option label="重新执行" value="重新执行" />
              <el-option label="分析程序" value="分析程序" />
            </el-select>
            <span v-else>{{ row.checkMethod || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="executor" label="执行人" width="100" align="center">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.executor"
              size="small"
              placeholder="—"
            />
            <span v-else>{{ row.executor || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="conclusion" label="执行情况说明" min-width="220">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.conclusion"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              size="small"
              placeholder="填写执行情况"
            />
            <span v-else>{{ row.conclusion || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="ref" label="审计程序索引" width="120" align="center">
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
            <el-button
              size="small"
              @click="handleOpenReview('s14-program-conclusion', '审计结论')"
            >复核</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-if="!isReadonly"
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="填写审计结论"
      />
      <div v-else class="conclusion-text">{{ auditConclusion || '—' }}</div>
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-hints">
      <summary>编制提示</summary>
      <p>1. 识别被审计单位涉及的会计估计项目（如公允价值计量、资产减值、预计负债等）。</p>
      <p>2. 了解被审计单位及其环境中与会计估计相关的方面（参见 S14-1）。</p>
      <p>3. 了解与会计估计相关的内部控制（参见 S14-2）。</p>
      <p>4. 识别和评估会计估计相关的重大错报风险（参见 B10 风险评估）。</p>
      <p>5. 根据评估的风险采取应对措施（参见 S14-3）。</p>
      <p>6. 评价管理层是否存在偏向的迹象（参见 S14-4）。</p>
      <p>7. 评价会计估计相关披露是否符合适用的财务报告编制基础。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * S14ProgramSheet.vue — S14 会计估计和相关披露程序表
 *
 * 功能：
 * - 展示 S14 程序表（67×9 checklist 格式）
 * - 保留列结构：是否适用 / 核查方式 / 执行人 / 执行情况说明 / 审计程序索引（Req 5.2）
 * - GtIndexChip 引用 B10/B22/B40 等风险评估底稿（Req 5.3）
 * - 审计结论区 el-card + AI 按钮
 * - readonly 禁编辑
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 4.4
 * Requirements: 5.1, 5.2, 5.3
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

// ─── 审计程序步骤（实际从 render-config 加载，此为骨架数据） ─────────────────

const programSteps = ref([
  {
    category: '了解环境',
    procedure: '了解被审计单位的行业特征、监管环境和其他与会计估计相关的外部因素。',
    applicable: '是',
    checkMethod: '询问',
    executor: '',
    conclusion: '',
    ref: 'S14-1',
  },
  {
    category: '了解环境',
    procedure: '了解管理层如何识别需要作出会计估计的交易、事项和情况。',
    applicable: '是',
    checkMethod: '询问',
    executor: '',
    conclusion: '',
    ref: 'S14-1',
  },
  {
    category: '了解环境',
    procedure: '了解管理层用于作出会计估计的方法，包括适用的模型和重大假设。',
    applicable: '是',
    checkMethod: '检查',
    executor: '',
    conclusion: '',
    ref: 'S14-1',
  },
  {
    category: '了解控制',
    procedure: '了解与会计估计相关的内部控制，包括管理层如何确定估计的完整性。',
    applicable: '是',
    checkMethod: '询问',
    executor: '',
    conclusion: '',
    ref: 'S14-2',
  },
  {
    category: '了解控制',
    procedure: '了解管理层对会计估计相关数据和假设的审查和批准控制。',
    applicable: '是',
    checkMethod: '检查',
    executor: '',
    conclusion: '',
    ref: 'S14-2',
  },
  {
    category: '风险评估',
    procedure: '评估会计估计是否具有高度估计不确定性，并确定是否为特别风险。',
    applicable: '是',
    checkMethod: '分析程序',
    executor: '',
    conclusion: '',
    ref: 'B10',
  },
  {
    category: '风险评估',
    procedure: '对已识别的特别风险，获取充分、适当的审计证据以评估管理层的假设合理性。',
    applicable: '是',
    checkMethod: '检查',
    executor: '',
    conclusion: '',
    ref: 'B22',
  },
  {
    category: '应对风险',
    procedure: '实施审计程序以应对评估的会计估计相关重大错报风险。',
    applicable: '是',
    checkMethod: '重新计算',
    executor: '',
    conclusion: '',
    ref: 'S14-3',
  },
  {
    category: '应对风险',
    procedure: '检验管理层作出会计估计的过程（包括方法、模型、数据来源和重大假设）。',
    applicable: '是',
    checkMethod: '重新执行',
    executor: '',
    conclusion: '',
    ref: 'S14-3',
  },
  {
    category: '应对风险',
    procedure: '确定截至审计报告日发生的事项是否为会计估计提供了审计证据。',
    applicable: '是',
    checkMethod: '检查',
    executor: '',
    conclusion: '',
    ref: 'B40',
  },
  {
    category: '管理层偏向',
    procedure: '评价管理层在会计估计中是否存在偏向的迹象。',
    applicable: '是',
    checkMethod: '分析程序',
    executor: '',
    conclusion: '',
    ref: 'S14-4',
  },
  {
    category: '披露评价',
    procedure: '评价与会计估计相关的披露是否符合适用的财务报告编制基础的要求。',
    applicable: '是',
    checkMethod: '检查',
    executor: '',
    conclusion: '',
    ref: '',
  },
])

// ─── 审计结论 ────────────────────────────────────────────────────────────────

const auditConclusion = ref('')

// ─── AI 辅助 ─────────────────────────────────────────────────────────────────

function handleAiAssist() {
  // TODO: 调用 AI 辅助生成执行说明
}

function handleAiConclusion() {
  // TODO: 调用 AI 辅助生成审计结论
}
</script>

<style scoped>
.s14-program {
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

.category-text {
  font-size: 12px;
  color: #606266;
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
