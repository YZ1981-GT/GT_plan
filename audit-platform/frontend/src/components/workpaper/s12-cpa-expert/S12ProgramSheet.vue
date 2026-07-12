<template>
  <div class="s12-program">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>审计目标</template>
      <div class="audit-objective-text">
        确定审计工作中是否需要利用注册会计师的专家的工作；评价专家的胜任能力、专业素质和客观性，以及专家工作对实现审计目的的恰当性，从而为相关审计事项获取充分、适当的审计证据（CAS 1421）。
      </div>
    </el-alert>

    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>S12 利用专家的工作程序表</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiAssist"
            >AI辅助</el-button>
            <el-button
              size="small"
              @click="handleOpenReview('s12-program', '利用专家的工作程序表')"
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
        <el-table-column prop="procedure" label="审计程序" min-width="360">
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
              @change="saveRows"
            >
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="N/A" value="N/A" />
            </el-select>
            <span v-else>{{ row.applicable || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="executor" label="执行人" width="100" align="center">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.executor"
              size="small"
              placeholder="—"
              @change="saveRows"
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
              @change="saveRows"
            />
            <span v-else>{{ row.conclusion || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="ref" label="索引号" width="100" align="center">
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
              @click="handleOpenReview('s12-program-conclusion', '审计结论')"
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
        @change="saveConclusion"
      />
      <div v-else class="conclusion-text">{{ auditConclusion || '—' }}</div>
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-hints">
      <summary>编制提示</summary>
      <p>1. 确定是否需要利用注册会计师的专家的工作（如资产评估、精算、工程造价等领域）。</p>
      <p>2. 评价专家的胜任能力、专业素质和客观性（参见 S12-1）。</p>
      <p>3. 了解专家的专长领域，确认其专业知识与审计相关事项匹配（参见 S12-2）。</p>
      <p>4. 就专家工作的性质、范围和目标与专家达成一致。</p>
      <p>5. 评价专家工作的恰当性（参见 S12-3），包括：假设和方法、源数据、结论与审计证据的一致性。</p>
      <p>6. 根据被评价对象（通用/股份支付/金融工具公允价值）选择对应评价子表。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * S12ProgramSheet.vue — S12 利用专家的工作程序表
 *
 * 功能：
 * - 展示 S12 审计程序清单（checklist 格式，60×11）
 * - 保留列结构：是否适用 / 执行人 / 执行情况说明 / 索引号（Req 4.5）
 * - GtIndexChip 跨底稿引用跳转
 * - 审计结论区 el-card + AI 按钮
 * - readonly 禁编辑
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 4.3
 * Requirements: 4.1, 4.5
 */
import { ref, inject } from 'vue'
import { defineAsyncComponent } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useSExpertPersist } from '../composables/useSExpertPersist'

const GtIndexChip = defineAsyncComponent(() => import('../GtIndexChip.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  /** 主入口透传的持久化快照（已解包纯 Map） */
  allResponses?: Map<string, any>
}>()

// ─── 复核对话 ────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog')

function handleOpenReview(sectionId: string, label: string) {
  openReviewDialog?.(sectionId, label)
}

// ─── 审计程序步骤（骨架数据，seed 时从 responses 覆盖） ─────────────────

const programSteps = ref([
  {
    category: '决定是否利用',
    procedure: '确定审计工作中是否存在需要利用注册会计师的专家工作的领域（如资产评估、精算、工程造价、税务、法律等）。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: '',
  },
  {
    category: '决定是否利用',
    procedure: '评估被审计单位会计估计或其他事项的复杂程度，判断是否需要专家提供专业知识。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: '',
  },
  {
    category: '评价胜任能力',
    procedure: '评价专家的胜任能力、专业素质和客观性，包括其学历、资质、执业经验。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: 'S12-1',
  },
  {
    category: '评价客观性',
    procedure: '评价专家与被审计单位是否存在利益关系或其他可能影响客观性的情形。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: 'S12-1-1',
  },
  {
    category: '了解专长领域',
    procedure: '了解专家的专长领域，确认其专业知识与审计目标中相关事项的匹配程度。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: 'S12-2',
  },
  {
    category: '协商工作范围',
    procedure: '就专家工作的性质、范围和目标达成一致意见，明确双方责任。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: '',
  },
  {
    category: '协商工作范围',
    procedure: '与专家沟通需使用的假设和方法，确认其适当性。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: '',
  },
  {
    category: '评价恰当性',
    procedure: '评价专家工作的恰当性——结论是否与审计证据一致、假设和方法是否合理。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: 'S12-3',
  },
  {
    category: '评价恰当性',
    procedure: '获取并检查注册会计师的专家出具的报告。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: 'S12-3-1',
  },
  {
    category: '评价恰当性',
    procedure: '根据被评价对象（通用/股份支付/金融工具公允价值）完成对应的专家工作评价。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: 'S12-3-2',
  },
])

// ─── 审计结论 ────────────────────────────────────────────────────────────────

const auditConclusion = ref('')

// ─── 持久化接线（load + save） ────────────────────────────────────────────────

const ROWS_ID = 'S12-program-rows'
const CONCLUSION_ID = 'S12-program-conclusion'

const { seedOnMount, save } = useSExpertPersist(() => props.allResponses)
seedOnMount([
  { itemId: ROWS_ID, ref: programSteps },
  { itemId: CONCLUSION_ID, ref: auditConclusion },
])

function saveRows(): void {
  save(ROWS_ID, programSteps.value)
}

function saveConclusion(): void {
  save(CONCLUSION_ID, auditConclusion.value)
}

// ─── AI 辅助 ─────────────────────────────────────────────────────────────────

function handleAiAssist() {
  // TODO: 调用 AI 辅助生成执行说明
}

function handleAiConclusion() {
  // TODO: 调用 AI 辅助生成审计结论
}
</script>

<style scoped>
.s12-program {
  padding: 12px;
}

.audit-objective {
  margin-bottom: 12px;
}

.audit-objective-text {
  font-size: var(--wp-font-size, 13px);
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
  font-size: var(--wp-font-size, 13px);
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
