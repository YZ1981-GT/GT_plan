<template>
  <div class="s5-program">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：识别债务重组方式，分别从债权人与债务人视角复核重组损益计算，评价损益确认时点是否恰当（不得提前确认），并确认非经常性损益披露充分。"
      style="margin-bottom: 16px"
    />

    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>债务重组审计程序 S5</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiAssist"
            >AI辅助</el-button>
            <el-button
              size="small"
              @click="handleOpenReview('s5-program', '审计程序')"
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
              @click="handleOpenReview('s5-program-conclusion', '审计结论')"
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
      <p>1. 获取债务重组相关协议或合同，检查重组方式、条款、生效条件及各方权利义务。</p>
      <p>2. 区分以资产清偿债务、将债务转为权益工具、修改其他条款等不同重组方式。</p>
      <p>3. 分别从债权人和债务人两个视角审核重组损益的计算是否正确（参见审定表 S5-1）。</p>
      <p>4. 判断损益确认时点是否恰当——不得在重大不确定性消除前提前确认收益（参见 S5-2）。</p>
      <p>5. 核查债务重组产生的损益是否在附注中披露为非经常性损益。</p>
      <p>6. 对于破产重整中的债务重组，关注法院裁定书、债权人会议决议等法律文书。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * S5ProgramSheet.vue — 债务重组审计程序 S5
 *
 * 功能：
 * - 展示 S5 审计程序清单（checklist 格式）
 * - 支持适用性判断、执行人、结论填写
 * - GtIndexChip 跨底稿引用跳转（S5-1、S5-2、S17 等）
 * - 审计结论区 el-card + AI 按钮
 * - readonly 禁编辑
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 4.2
 * Requirements: 1.5, 3.1
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

// ─── 审计程序步骤（实际从 render-config 加载） ───────────────────────────────

const programSteps = ref([
  {
    procedure: '获取被审计单位与债务重组相关的协议、合同、法院裁定书或债权人会议决议等法律文书，了解重组方式和条款。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: '',
  },
  {
    procedure: '识别债务重组方式（以资产清偿债务/将债务转为权益工具/修改其他条款/以上方式的组合），确认适用的会计处理方法。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: '',
  },
  {
    procedure: '从债权人角度：核实债权原账面价值、债权原公允价值、收到资产/权益工具公允价值，复核重组损益计算。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: 'S5-1',
  },
  {
    procedure: '从债务人角度：核实所清偿债务账面价值、转让资产账面价值、权益工具公允价值，复核重组损益计算。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: 'S5-1',
  },
  {
    procedure: '判断债务重组损益确认时点是否恰当——是否在协议生效/破产重整完成/债务豁免条件满足后确认。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: 'S5-2',
  },
  {
    procedure: '检查是否存在提前确认债务重组收益的情况（特别关注破产重整或方案实施的重大不确定性）。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: 'S5-2',
  },
  {
    procedure: '核查涉及或有应付金额/或有应收金额的债务重组，相关金额是否按准则规定处理。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: '',
  },
  {
    procedure: '检查债务重组涉及的公允价值是否有可靠依据（活跃市场报价/评估报告/现金流量折现等）。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: '',
  },
  {
    procedure: '核查债务重组损益是否正确在附注中披露为非经常性损益。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: 'S17',
  },
  {
    procedure: '检查关联方之间的债务重组是否单独披露，是否存在利润操纵的迹象。',
    applicable: '是',
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
.s5-program {
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
