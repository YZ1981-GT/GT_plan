<template>
  <div class="s6-program">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：依据会计监管风险提示第9号，识别与核实大股东及关联方资金占用和违规担保，评价披露充分性及对审计报告意见类型的影响。"
      style="margin-bottom: 16px"
    />

    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>对大股东及关联方资金占用和违规担保情况审核程序S6</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiAssist"
            >AI辅助</el-button>
            <el-button
              size="small"
              @click="handleOpenReview('s6-program', '资金占用和违规担保审核程序')"
            >复核</el-button>
          </div>
        </div>
      </template>

      <!-- 方法论上下文（琥珀色左边线） -->
      <div class="methodology-context">
        <p>本程序表依据《会计监管风险提示第9号——上市公司控股股东资金占用及其审计》制定，覆盖资金占用的识别、核实、披露和审计报告影响评价等关键审计程序。</p>
      </div>

      <el-table
        :data="programSteps"
        border
        style="width: 100%; font-size: 13px"
        max-height="600"
      >
        <el-table-column type="index" label="序号" width="60" align="center" />
        <el-table-column prop="category" label="程序类别" width="140">
          <template #default="{ row }">
            <span class="category-text">{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="procedure" label="审核程序" min-width="360">
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
              @click="handleOpenReview('s6-program-conclusion', '审核程序审计结论')"
            >复核</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-if="!isReadonly"
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="填写关于资金占用和违规担保审核的审计结论"
      />
      <div v-else class="conclusion-text">{{ auditConclusion || '—' }}</div>
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-hints">
      <summary>编制提示</summary>
      <p>1. 识别大股东及关联方是否存在经营性/非经营性资金占用。</p>
      <p>2. 核实资金往来的商业实质，区分正常经营往来与非经营性资金占用。</p>
      <p>3. 识别是否存在为控股股东及关联方提供的违规担保。</p>
      <p>4. 评估资金占用/违规担保对财务报表的影响及披露充分性。</p>
      <p>5. 考虑资金占用/违规担保对审计报告的影响（是否需要非标意见）。</p>
      <p>6. 参照会计监管风险提示第9号的相关要求执行程序。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * S6ProgramSheet.vue — 对大股东及关联方资金占用和违规担保情况审核程序S6
 *
 * 功能：
 * - 展示 S6 大型审核程序表（143×9 checklist 格式）
 * - 方法论上下文区块（琥珀色左边线）
 * - GtIndexChip 跨底稿引用跳转
 * - max-height 600 可滚动（程序表 143 行较长）
 * - 审计结论区 el-card + AI 按钮
 * - readonly 禁编辑
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 4.4
 * Requirements: 6.1, 6.2
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

// ─── 审核程序步骤（实际从 render-config 加载，此为骨架数据 — 实际 143 行） ──

const programSteps = ref([
  {
    category: '了解与识别',
    procedure: '了解公司与控股股东及关联方之间的股权关系、资金往来安排和历史交易情况。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: '',
  },
  {
    category: '了解与识别',
    procedure: '获取公司关联方清单及关联关系图谱，确认关联方的完整性。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: 'B10',
  },
  {
    category: '了解与识别',
    procedure: '了解公司与控股股东之间是否存在资金归集/统一调配安排（资金池）。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: '',
  },
  {
    category: '了解与识别',
    procedure: '识别可能存在资金占用的科目（其他应收款、预付账款、长期应收款等）。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: 'K1',
  },
  {
    category: '核实资金占用',
    procedure: '获取报告期内公司与控股股东及关联方的资金往来明细。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: '',
  },
  {
    category: '核实资金占用',
    procedure: '逐笔核实大额资金往来的商业实质，区分正常经营性往来与非经营性资金占用。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: '',
  },
  {
    category: '核实资金占用',
    procedure: '检查是否存在通过第三方中转的隐性资金占用（穿透核查关联方关系链）。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: '',
  },
  {
    category: '核实资金占用',
    procedure: '检查期末应收控股股东及关联方款项的账龄和回收情况。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: '',
  },
  {
    category: '核实担保',
    procedure: '获取公司对外担保清单，识别为控股股东及关联方提供的担保。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: '',
  },
  {
    category: '核实担保',
    procedure: '检查担保是否经过合规审批（股东大会/董事会决议）。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: '',
  },
  {
    category: '核实担保',
    procedure: '评估违规担保的风险敞口及或有负债的计量。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: 'K5',
  },
  {
    category: '披露评价',
    procedure: '评价公司是否已在财务报表附注中充分披露资金占用和违规担保情况。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: '',
  },
  {
    category: '披露评价',
    procedure: '评价资金占用/违规担保事项是否需要在年报其他部分单独披露。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: '',
  },
  {
    category: '审计影响',
    procedure: '评估资金占用/违规担保对持续经营能力的影响。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: 'B50',
  },
  {
    category: '审计影响',
    procedure: '考虑是否需要就资金占用/违规担保事项出具非标准审计意见（保留/否定/无法表示）。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: '',
  },
  {
    category: '审计影响',
    procedure: '评估是否存在舞弊风险（控股股东通过资金占用侵占公司资产）。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: 'B22',
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
.s6-program {
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
