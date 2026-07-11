<template>
  <div class="s3-policy-error">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：区分会计政策变更、前期差错更正与会计估计变更三类事项，评价追溯调整（追溯重述）处理的恰当性，并识别应标注为非经常性损益的项目。"
      style="margin-bottom: 16px"
    />

    <!-- 三类事项选择器（Req 6.2）：会计政策变更 / 前期差错更正 / 会计估计变更 -->
    <div class="event-type-selector">
      <span class="selector-label">事项类型：</span>
      <el-radio-group
        v-model="currentEventType"
        :disabled="isReadonly"
        size="default"
      >
        <el-radio-button value="policy-change">会计政策变更</el-radio-button>
        <el-radio-button value="prior-error">前期差错更正</el-radio-button>
        <el-radio-button value="estimate-change">会计估计变更</el-radio-button>
      </el-radio-group>
    </div>

    <!-- 方法论上下文区 -->
    <div class="methodology-context">
      <div class="context-content">
        <p v-if="currentEventType === 'policy-change'">
          会计政策变更是指企业对相同的交易或者事项由原来采用的会计政策改用另一会计政策的行为。
          追溯调整法：视同该政策一直被采用，调整发现当期的期初留存收益和其他相关项目。
        </p>
        <p v-else-if="currentEventType === 'prior-error'">
          前期差错更正：对前期财务报表中的差错予以更正。重大前期差错应采用追溯重述法，
          视同该差错在前期已经得到更正，调整有关前期的比较财务报表。
        </p>
        <p v-else>
          会计估计变更：由于资产和负债的当前状况及预期经济利益和义务发生了变化，
          从而对资产或负债的账面价值或者资产的定期消耗金额进行调整。采用未来适用法。
        </p>
      </div>
    </div>

    <!-- 审计程序内容 -->
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>{{ sectionTitle }}</span>
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

      <!-- 事项明细表 -->
      <el-table
        :data="eventItems"
        border
        stripe
        style="width: 100%; font-size: 13px"
      >
        <el-table-column type="index" label="序号" width="60" />
        <el-table-column prop="description" label="变更/差错事项说明" min-width="240">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.description"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              placeholder="请描述事项内容..."
            />
            <span v-else>{{ row.description }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="retroAdjustment" label="追溯调整金额" min-width="140" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.retroAdjustment"
              :precision="2"
              :controls="false"
              style="width: 120px"
            />
            <span v-else>{{ fmt(row.retroAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="非经常性损益" width="130" align="center">
          <template #header>
            <span>非经常性损益</span>
            <GtIndexChip value="B22" style="margin-left: 4px" />
          </template>
          <template #default="{ row }">
            <el-checkbox
              v-model="row.isNonRecurring"
              :disabled="isReadonly"
            />
            <el-tag v-if="row.isNonRecurring" type="warning" size="small" class="non-recurring-tag">
              非经常性
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="auditConclusion" label="审计结论" min-width="200">
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
        <el-button size="small" type="primary" plain @click="addEventItem">
          + 新增事项
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
      <p>S3-1 会计政策变更和前期差错更正审计程序。请选择事项类型后录入具体变更/差错事项。</p>
      <p>属于非经常性损益范畴的事项需勾选标注（Req 6.4），如会计政策变更/非货币性资产交换/债务重组损益等。</p>
      <p>追溯调整记录（Req 6.3）：针对每类事项分别记录追溯调整。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * GtS3PolicyError.vue — S3-1 会计政策变更和前期差错更正
 *
 * 核心功能：
 * - 三类事项区分（Req 6.2）：会计政策变更 / 前期差错更正 / 会计估计变更
 * - 追溯调整记录（Req 6.3）
 * - 非经常性损益标注（Req 6.4）
 *
 * Requirements: 6.2, 6.3, 6.4
 */
import { ref, computed, inject, defineAsyncComponent } from 'vue'
import { ElMessageBox } from 'element-plus'
import { fmtAmount } from '@/utils/formatters'

const GtIndexChip = defineAsyncComponent(() => import('../GtIndexChip.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<(sectionId: string, label?: string) => void>('openReviewDialog')

function fmt(val: number | null | undefined): string {
  return fmtAmount(val, 2)
}

// ─── 三类事项选择器 ──────────────────────────────────────────────────────────

type EventType = 'policy-change' | 'prior-error' | 'estimate-change'
const currentEventType = ref<EventType>('policy-change')

const sectionTitle = computed(() => {
  switch (currentEventType.value) {
    case 'policy-change': return '会计政策变更审计程序 S3-1'
    case 'prior-error': return '前期差错更正审计程序 S3-1'
    case 'estimate-change': return '会计估计变更审计程序 S3-1'
    default: return '审计程序 S3-1'
  }
})

// ─── 事项明细 ────────────────────────────────────────────────────────────────

interface EventItem {
  id: string
  description: string
  retroAdjustment: number
  isNonRecurring: boolean
  auditConclusion: string
  eventType: EventType
}

const eventItems = ref<EventItem[]>([
  {
    id: '1',
    description: '',
    retroAdjustment: 0,
    isNonRecurring: false,
    auditConclusion: '',
    eventType: 'policy-change',
  },
])

const conclusion = ref('')

async function addEventItem() {
  const { value: name } = await ElMessageBox.prompt('请输入事项名称', '新增事项', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    inputPlaceholder: '事项名称...',
  })
  if (name) {
    eventItems.value.push({
      id: String(Date.now()),
      description: name,
      retroAdjustment: 0,
      isNonRecurring: false,
      auditConclusion: '',
      eventType: currentEventType.value,
    })
  }
}

function handleSave() {
  // TODO: 保存事项数据
}

function handleReview() {
  openReviewDialog?.('s3-policy-error', '会计政策变更和前期差错更正 S3-1')
}
</script>

<style scoped>
.s3-policy-error {
  padding: 12px;
}
.event-type-selector {
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.selector-label {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
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
  font-size: 13px;
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
.non-recurring-tag {
  margin-left: 4px;
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
