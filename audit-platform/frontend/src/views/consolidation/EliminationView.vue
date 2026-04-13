<template>
  <div class="gt-elimination-view">
    <el-tabs v-model="activeSubTab" class="gt-tabs">
      <!-- 抵消分录列表 -->
      <el-tab-pane label="分录列表" name="list">
        <EliminationList :project-id="projectId" />
      </el-tab-pane>

      <!-- 合并试算表（抵消分录关联） -->
      <el-tab-pane label="合并试算表" name="trial">
        <ConsolTrialBalance
          :project-id="projectId"
          :period="year"
          @entry-click="onTrialEntryClick"
        />
      </el-tab-pane>
    </el-tabs>

    <!-- 抵消分录详情弹窗（从试算表点击抵消列触发） -->
    <el-dialog
      v-model="detailVisible"
      title="抵消分录明细"
      width="900px"
      class="gt-dialog"
    >
      <div v-if="selectedTrialRow" class="detail-content">
        <div class="detail-header">
          <span class="detail-label">科目：</span>
          <span class="detail-value">{{ selectedTrialRow.account_code }} {{ selectedTrialRow.account_name }}</span>
        </div>
        <div class="detail-header">
          <span class="detail-label">合并抵消金额：</span>
          <span class="detail-value elimination-amount">
            {{ formatNum(selectedTrialRow.consol_elimination) }}
          </span>
        </div>

        <el-table
          v-if="selectedTrialRow.elimination_details?.length"
          :data="selectedTrialRow.elimination_details"
          border
          stripe
          size="small"
          max-height="300"
        >
          <el-table-column prop="entry_no" label="分录编号" width="140" />
          <el-table-column prop="entry_type" label="类型" width="120">
            <template #default="{ row }">
              {{ entryTypeLabel(row.entry_type) }}
            </template>
          </el-table-column>
          <el-table-column label="借方" align="right" width="140">
            <template #default="{ row }">
              <span class="debit" v-if="row.debit">{{ formatNum(row.debit) }}</span>
              <span v-else class="zero">—</span>
            </template>
          </el-table-column>
          <el-table-column label="贷方" align="right" width="140">
            <template #default="{ row }">
              <span class="credit" v-if="row.credit">{{ formatNum(row.credit) }}</span>
              <span v-else class="zero">—</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100" align="center">
            <template #default="{ row }">
              <el-button type="primary" size="small" text @click="onViewEntry(row.entry_id)">
                查看详情
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <div v-else class="no-detail">该科目暂无抵消分录明细</div>
      </div>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
        <el-button type="primary" @click="onCreateElimination">新建抵消分录</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import EliminationList from '@/components/consolidation/EliminationList.vue'
import ConsolTrialBalance from '@/components/consolidation/ConsolTrialBalance.vue'
import type { ConsolTrialBalanceEntry } from '@/services/consolidationApi'

const props = defineProps<{
  projectId: string
  year: number
}>()

const activeSubTab = ref('list')
const detailVisible = ref(false)
const selectedTrialRow = ref<ConsolTrialBalanceEntry | null>(null)

function formatNum(v: number) {
  if (!v && v !== 0) return '—'
  const sign = v < 0 ? '-' : ''
  return sign + Math.abs(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function entryTypeLabel(type: string) {
  const map: Record<string, string> = {
    investment: '投资类',
    ar_ap: '往来类',
    transaction: '交易类',
    internal_income: '内部收入类',
    other: '其他',
  }
  return map[type] || type
}

function onTrialEntryClick(row: ConsolTrialBalanceEntry) {
  selectedTrialRow.value = row
  detailVisible.value = true
}

function onViewEntry(entryId: string) {
  // 切换到分录列表 tab
  activeSubTab.value = 'list'
  detailVisible.value = false
  ElMessage.info(`查看分录 ID: ${entryId}`)
  // 可以通过路由或事件传递需要打开的 entry
}

function onCreateElimination() {
  activeSubTab.value = 'list'
  detailVisible.value = false
  ElMessage.info('请在分录列表中新建抵消分录')
}
</script>

<style scoped>
.gt-elimination-view {
  display: flex;
  flex-direction: column;
  gap: var(--gt-space-3);
}

.detail-content {
  display: flex;
  flex-direction: column;
  gap: var(--gt-space-3);
}

.detail-header {
  display: flex;
  align-items: center;
  gap: var(--gt-space-2);
  font-size: 14px;
}

.detail-label {
  font-weight: 600;
  color: var(--gt-color-text-secondary);
}

.detail-value {
  color: var(--gt-color-text);
}

.elimination-amount {
  font-size: 16px;
  font-weight: 700;
  color: var(--gt-color-primary);
}

.no-detail {
  color: var(--gt-color-text-tertiary);
  font-size: var(--gt-font-size-base);
  padding: var(--gt-space-6);
  text-align: center;
  background: #f8f7fc;
  border-radius: var(--gt-radius-sm);
}

.debit { color: var(--gt-color-coral, #FF5149); }
.credit { color: var(--gt-color-teal, #0094B3); }
.zero { color: var(--gt-color-text-tertiary); }

.gt-tabs :deep(.el-tabs__item) {
  font-weight: 500;
}

.gt-dialog :deep(.el-dialog__header) {
  background: var(--gt-color-primary);
  color: #fff;
}
</style>
