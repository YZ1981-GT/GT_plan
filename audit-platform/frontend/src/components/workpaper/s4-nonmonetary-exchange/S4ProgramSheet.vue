<template>
  <div class="s4-program">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：判断交易是否适用非货币性资产交换准则、是否具有商业实质，复核以公允价值计量的交换损益与换入成本的确定是否正确，并确认非经常性损益披露充分。"
      style="margin-bottom: 16px"
    />

    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>非货币性资产交换审计程序 S4</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiAssist"
            >AI辅助</el-button>
            <el-button
              size="small"
              @click="handleOpenReview('s4-program', '审计程序')"
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
              @click="handleOpenReview('s4-program-conclusion', '审计结论')"
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
      <p>1. 获取非货币性资产交换的相关协议或合同，检查交换条款、对价方式及补价比例。</p>
      <p>2. 检查交换资产的公允价值确认是否合理，是否有活跃市场报价或可靠估值。</p>
      <p>3. 判断交换是否具有商业实质（参见 S4-2 商业实质判断表）。</p>
      <p>4. 复核会计处理是否符合《企业会计准则第7号——非货币性资产交换》的规定。</p>
      <p>5. 检查交换损益的计算是否正确（参见审定表 S4-1）。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * S4ProgramSheet.vue — 非货币性资产交换审计程序 S4
 *
 * 功能：
 * - 展示 S4 审计程序清单（checklist 格式）
 * - 支持适用性判断、执行人、结论填写
 * - GtIndexChip 跨底稿引用跳转（S4-1、S4-2 等）
 * - 审计结论区 el-card + AI 按钮
 * - readonly 禁编辑
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 4.1
 * Requirements: 1.5, 2.1
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
    procedure: '获取被审计单位与非货币性资产交换相关的交易协议或合同，了解交换的内容、条件和对价方式。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: '',
  },
  {
    procedure: '判断该交易是否属于非货币性资产交换准则的适用范围（排除与所有者或所有者以非所有者身份进行的交易等6项情形）。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: 'S4-2',
  },
  {
    procedure: '判断该非货币性资产交换是否具有商业实质（未来现金流量的风险、时间和金额是否显著不同）。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: 'S4-2',
  },
  {
    procedure: '确定换入资产和换出资产的公允价值是否能够可靠计量，核实公允价值的确定依据。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: 'S4-1',
  },
  {
    procedure: '复核以公允价值计量的非货币性资产交换中，换出资产损益（=换出公允价值-换出账面价值）的计算是否正确。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: 'S4-1',
  },
  {
    procedure: '复核换入资产入账成本（=换出公允价值+相关税费）的确定是否正确。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: 'S4-1',
  },
  {
    procedure: '检查涉及补价的交换中，补价比例是否小于25%（若超过则不属于非货币性资产交换）。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: '',
  },
  {
    procedure: '核查非货币性资产交换产生的损益是否正确在附注中披露为非经常性损益。',
    applicable: '是',
    executor: '',
    conclusion: '',
    ref: 'S17',
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
.s4-program {
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
