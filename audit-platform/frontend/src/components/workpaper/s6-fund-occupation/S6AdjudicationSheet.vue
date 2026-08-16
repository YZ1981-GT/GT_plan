<template>
  <div class="s6-adjudication">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：汇总大股东及关联方资金占用与违规担保情况，确认占用/担保金额的完整、准确，评估对财务报表及审计意见的影响。"
      style="margin-bottom: 16px"
    />

    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>审定表S6-1 — 大股东及关联方资金占用和违规担保情况汇总</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiAssist"
            >AI辅助</el-button>
            <el-button
              size="small"
              @click="handleOpenReview('s6-1-adjudication', '审定表S6-1')"
            >复核</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="adjudicationRows"
        border
        show-summary
        :summary-method="getSummary"
        style="width: 100%; font-size: 13px"
      >
        <el-table-column type="index" label="序号" width="60" align="center" />
        <el-table-column prop="category" label="类别" width="160">
          <template #default="{ row }">
            <span>{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="relatedParty" label="关联方名称" min-width="180">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.relatedParty"
              size="small"
              placeholder="输入关联方"
            />
            <span v-else>{{ row.relatedParty || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="occupationAmount" label="资金占用金额(元)" width="160" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              v-model="row.occupationAmount"
              size="small"
              style="width: 140px"
            />
            <span v-else>{{ fmt(row.occupationAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="guaranteeAmount" label="违规担保金额(元)" width="160" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              v-model="row.guaranteeAmount"
              size="small"
              style="width: 140px"
            />
            <span v-else>{{ fmt(row.guaranteeAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="auditedAmount" label="审定金额(元)" width="160" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              v-model="row.auditedAmount"
              size="small"
              style="width: 140px"
            />
            <span v-else>{{ fmt(row.auditedAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="note" label="备注" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.note"
              size="small"
              placeholder="—"
            />
            <span v-else>{{ row.note || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 保存按钮 -->
      <div v-if="!isReadonly" class="save-bar">
        <el-button type="primary" size="small" @click="handleSave">保存并回写试算表</el-button>
      </div>
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
        placeholder="填写关于大股东及关联方资金占用和违规担保情况的审计结论"
      />
      <div v-else class="conclusion-text">{{ auditConclusion || '—' }}</div>
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-hints">
      <summary>编制提示</summary>
      <p>1. 审定表汇总大股东及关联方对上市公司的资金占用情况。</p>
      <p>2. 汇总对外违规担保的金额（含为控股股东及关联方提供的担保）。</p>
      <p>3. 审定金额将回写试算表相关科目（v2 正数口径）。</p>
      <p>4. 参照会计监管风险提示第9号执行审核程序。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../shared/WpAmountInput.vue'
/**
 * S6AdjudicationSheet.vue — 审定表S6-1 大股东及关联方资金占用/违规担保汇总
 *
 * 功能：
 * - 展示审定表（25×7 格式），汇总资金占用/违规担保金额
 * - 支持 TB 回写（Req 6.3）
 * - 合计行（show-summary）
 * - 审计结论区 el-card + AI 按钮
 * - readonly 禁编辑
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 4.4
 * Requirements: 6.1, 6.3
 */
import { ref, inject } from 'vue'
import { defineAsyncComponent } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { fmtAmount } from '@/utils/formatters'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save'): void
}>()

// ─── 复核对话 ────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog')

function handleOpenReview(sectionId: string, label: string) {
  openReviewDialog?.(sectionId, label)
}

// ─── 金额格式化 ──────────────────────────────────────────────────────────────

function fmt(val: number | null | undefined): string {
  return fmtAmount(val, 2)
}

// ─── 审定表数据（实际从 render-config 加载，此为骨架数据） ───────────────────

const adjudicationRows = ref([
  {
    category: '经营性资金占用',
    relatedParty: '',
    occupationAmount: null as number | null,
    guaranteeAmount: null as number | null,
    auditedAmount: null as number | null,
    note: '',
  },
  {
    category: '非经营性资金占用',
    relatedParty: '',
    occupationAmount: null as number | null,
    guaranteeAmount: null as number | null,
    auditedAmount: null as number | null,
    note: '',
  },
  {
    category: '为控股股东提供担保',
    relatedParty: '',
    occupationAmount: null as number | null,
    guaranteeAmount: null as number | null,
    auditedAmount: null as number | null,
    note: '',
  },
  {
    category: '为关联方提供担保',
    relatedParty: '',
    occupationAmount: null as number | null,
    guaranteeAmount: null as number | null,
    auditedAmount: null as number | null,
    note: '',
  },
  {
    category: '其他违规担保',
    relatedParty: '',
    occupationAmount: null as number | null,
    guaranteeAmount: null as number | null,
    auditedAmount: null as number | null,
    note: '',
  },
])

// ─── 合计方法 ────────────────────────────────────────────────────────────────

function getSummary({ columns, data }: any) {
  const sums: string[] = []
  columns.forEach((col: any, index: number) => {
    if (index === 0) {
      sums[index] = ''
      return
    }
    if (index === 1) {
      sums[index] = '合计'
      return
    }
    if (['occupationAmount', 'guaranteeAmount', 'auditedAmount'].includes(col.property)) {
      const total = data.reduce((acc: number, row: any) => {
        const val = Number(row[col.property])
        return acc + (isNaN(val) ? 0 : val)
      }, 0)
      sums[index] = fmt(total)
    } else {
      sums[index] = ''
    }
  })
  return sums
}

// ─── 审计结论 ────────────────────────────────────────────────────────────────

const auditConclusion = ref('')

// ─── 保存 + TB 回写 ─────────────────────────────────────────────────────────

function handleSave() {
  emit('save')
}

// ─── AI 辅助 ─────────────────────────────────────────────────────────────────

function handleAiAssist() {
  // TODO: 调用 AI 辅助
}

function handleAiConclusion() {
  // TODO: 调用 AI 辅助生成审计结论
}
</script>

<style scoped>
.s6-adjudication {
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

.save-bar {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
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
