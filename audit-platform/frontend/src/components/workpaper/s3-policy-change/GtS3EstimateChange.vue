<template>
  <div class="s3-estimate-change">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：评价会计估计变更的理由是否充分、采用未来适用法处理是否恰当，确认对当期及未来期间影响的计量与披露准确。"
      style="margin-bottom: 16px"
    />

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <div class="context-content">
        <p>
          会计估计变更：由于资产和负债的当前状况及预期经济利益和义务发生了变化，
          从而对资产或负债的账面价值或者资产的定期消耗金额进行调整。
          会计估计变更采用<strong>未来适用法</strong>处理，不调整前期比较报表。
        </p>
      </div>
    </div>

    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>会计估计变更审计程序 S3-2</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              type="primary"
              @click="handleSave"
            >保存</el-button>
            <el-button size="small" @click="handleReview">复核</el-button>
          </div>
        </div>
      </template>

      <!-- 估计变更事项明细 -->
      <el-table
        :data="estimateItems"
        border
        stripe
        style="width: 100%; font-size: 13px"
      >
        <el-table-column type="index" label="序号" width="60" />
        <el-table-column prop="estimateItem" label="会计估计变更事项" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.estimateItem"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              placeholder="变更事项描述..."
            />
            <span v-else>{{ row.estimateItem }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="变更理由" min-width="180">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.reason"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              placeholder="变更理由..."
            />
            <span v-else>{{ row.reason }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="currentImpact" label="对本期的影响金额" min-width="140" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.currentImpact"
              :precision="2"
              :controls="false"
              style="width: 120px"
            />
            <span v-else>{{ fmt(row.currentImpact) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="futureImpact" label="对未来期间的影响" min-width="140" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.futureImpact"
              :precision="2"
              :controls="false"
              style="width: 120px"
            />
            <span v-else>{{ fmt(row.futureImpact) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="非经常性损益" width="130" align="center">
          <template #default="{ row }">
            <el-checkbox v-model="row.isNonRecurring" :disabled="isReadonly" />
            <el-tag v-if="row.isNonRecurring" type="warning" size="small">非经常性</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="auditConclusion" label="审计结论" min-width="180">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.auditConclusion"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              placeholder="审计结论..."
            />
            <span v-else>{{ row.auditConclusion }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 新增行 -->
      <div v-if="!isReadonly" class="add-row-action">
        <el-button size="small" type="primary" plain @click="addItem">
          + 新增估计变更事项
        </el-button>
      </div>
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <span>审计结论</span>
      </template>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="请填写审计结论..."
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-hints">
      <summary>编制提示</summary>
      <p>S3-2 会计估计变更审计程序。会计估计变更采用未来适用法，需披露变更内容、理由及对当期和未来期间的影响。</p>
      <p>属于非经常性损益范畴的估计变更事项需标注。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * GtS3EstimateChange.vue — S3-2 会计估计变更审计程序
 *
 * 功能：
 * - 会计估计变更事项记录
 * - 未来适用法（不追溯调整）
 * - 对本期/未来期间影响金额
 * - 非经常性损益标注
 */
import { ref, inject } from 'vue'
import { ElMessageBox } from 'element-plus'
import { fmtAmount } from '@/utils/formatters'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<(sectionId: string, label?: string) => void>('openReviewDialog')

function fmt(val: number | null | undefined): string {
  return fmtAmount(val, 2)
}

interface EstimateItem {
  id: string
  estimateItem: string
  reason: string
  currentImpact: number
  futureImpact: number
  isNonRecurring: boolean
  auditConclusion: string
}

const estimateItems = ref<EstimateItem[]>([
  {
    id: '1',
    estimateItem: '',
    reason: '',
    currentImpact: 0,
    futureImpact: 0,
    isNonRecurring: false,
    auditConclusion: '',
  },
])

const conclusion = ref('')

async function addItem() {
  const { value: name } = await ElMessageBox.prompt('请输入估计变更事项名称', '新增事项', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    inputPlaceholder: '事项名称...',
  })
  if (name) {
    estimateItems.value.push({
      id: String(Date.now()),
      estimateItem: name,
      reason: '',
      currentImpact: 0,
      futureImpact: 0,
      isNonRecurring: false,
      auditConclusion: '',
    })
  }
}

function handleSave() {
  // TODO: 保存数据
}

function handleReview() {
  openReviewDialog?.('s3-estimate-change', '会计估计变更审计程序 S3-2')
}
</script>

<style scoped>
.s3-estimate-change {
  padding: 12px;
}
.methodology-context {
  margin-bottom: 16px;
  padding: 12px 16px;
  border-left: 3px solid #e6a23c;
  background-color: #fdf6ec;
  border-radius: 4px;
}
.methodology-context .context-content p {
  margin: 0;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
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
.add-row-action {
  margin-top: 12px;
}
.conclusion-card {
  margin-top: 16px;
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
</style>
