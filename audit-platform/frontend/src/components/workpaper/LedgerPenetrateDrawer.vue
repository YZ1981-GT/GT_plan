<template>
  <el-drawer
    v-model="visible"
    title="🔍 序时账穿透结果"
    direction="rtl"
    size="65%"
    :before-close="handleClose"
    class="ledger-penetrate-drawer"
  >
    <!-- 查询参数摘要 -->
    <div class="penetrate-params-bar" v-if="queryParams">
      <el-descriptions :column="3" size="small" border>
        <el-descriptions-item label="目标金额">
          {{ formatAmount(queryParams.amount) }}
        </el-descriptions-item>
        <el-descriptions-item label="容差">
          ± {{ queryParams.tolerance }}
        </el-descriptions-item>
        <el-descriptions-item label="单元格">
          {{ queryParams.cellRef || '—' }}
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="drawer-loading">
      <el-icon class="is-loading" :size="32"><Loading /></el-icon>
      <p>正在穿透查询...</p>
    </div>

    <!-- 错误 -->
    <div v-else-if="error" class="drawer-error">
      <el-empty :description="error" />
    </div>

    <!-- 空结果 -->
    <div v-else-if="!resultData || resultData.matches.length === 0" class="drawer-empty">
      <el-empty description="未找到匹配凭证，可调整容差或科目范围">
        <template #default>
          <div class="empty-params" v-if="resultData?.params">
            <p class="empty-hint">当前查询参数：</p>
            <el-descriptions :column="2" size="small" border>
              <el-descriptions-item label="年度">{{ resultData.params.year }}</el-descriptions-item>
              <el-descriptions-item label="金额">{{ resultData.params.amount }}</el-descriptions-item>
              <el-descriptions-item label="容差">{{ resultData.params.tolerance }}</el-descriptions-item>
              <el-descriptions-item label="科目" v-if="resultData.params.account_code">
                {{ resultData.params.account_code }}
              </el-descriptions-item>
              <el-descriptions-item label="起始日期" v-if="resultData.params.date_from">
                {{ resultData.params.date_from }}
              </el-descriptions-item>
              <el-descriptions-item label="截止日期" v-if="resultData.params.date_to">
                {{ resultData.params.date_to }}
              </el-descriptions-item>
            </el-descriptions>
          </div>
        </template>
      </el-empty>
    </div>

    <!-- 结果展示 -->
    <div v-else class="penetrate-results">
      <!-- 截断提示 -->
      <el-alert
        v-if="resultData.truncated"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
      >
        结果过多（超过 200 条），请增加过滤条件以缩小范围
      </el-alert>

      <!-- 结果统计 -->
      <div class="result-summary">
        <span>共匹配 <strong>{{ resultData.total_count }}</strong> 条凭证</span>
        <el-button
          type="primary"
          size="small"
          @click="onExportToAttachment"
          :loading="exporting"
        >
          📎 导出穿透结果到附件
        </el-button>
      </div>

      <!-- 按策略层级展示 -->
      <el-collapse v-model="expandedStrategies" class="strategy-collapse">
        <el-collapse-item
          v-for="group in resultData.matches"
          :key="group.strategy"
          :name="group.strategy"
        >
          <template #title>
            <div class="strategy-header">
              <el-tag :type="strategyTagType(group.strategy)" size="small">
                {{ strategyLabel(group.strategy) }}
              </el-tag>
              <span class="strategy-count">{{ group.items.length }} 条</span>
            </div>
          </template>

          <el-table
            :data="group.items"
            size="small"
            stripe
            border
            style="width: 100%"
            max-height="400"
          >
            <el-table-column prop="voucher_date" label="日期" width="110" />
            <el-table-column prop="voucher_no" label="凭证号" width="100" />
            <el-table-column prop="account_code" label="科目编码" width="110" />
            <el-table-column prop="account_name" label="科目名称" width="140" />
            <el-table-column prop="debit_amount" label="借方金额" width="120" align="right">
              <template #default="{ row }">
                {{ row.debit_amount ? formatAmount(row.debit_amount) : '' }}
              </template>
            </el-table-column>
            <el-table-column prop="credit_amount" label="贷方金额" width="120" align="right">
              <template #default="{ row }">
                {{ row.credit_amount ? formatAmount(row.credit_amount) : '' }}
              </template>
            </el-table-column>
            <el-table-column prop="summary" label="摘要" min-width="180" show-overflow-tooltip />
            <el-table-column prop="counterpart_account" label="对方科目" width="120" show-overflow-tooltip />
          </el-table>
        </el-collapse-item>
      </el-collapse>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'

interface LedgerItem {
  id: string
  voucher_date: string
  voucher_no: string
  account_code: string
  account_name: string
  debit_amount: number | null
  credit_amount: number | null
  summary: string
  counterpart_account: string | null
}

interface StrategyGroup {
  strategy: 'exact' | 'tolerance' | 'code+amount' | 'summary'
  items: LedgerItem[]
}

interface PenetrateResult {
  matches: StrategyGroup[]
  total_count: number
  truncated?: boolean
  message?: string
  params?: {
    year: number
    amount: number
    tolerance: number
    account_code?: string | null
    date_from?: string | null
    date_to?: string | null
    summary_keyword?: string | null
  }
}

interface QueryParams {
  amount: number
  tolerance: number
  cellRef: string
  year?: number
  account_code?: string
  date_from?: string
  date_to?: string
  summary_keyword?: string
}

const props = defineProps<{
  projectId: string
  wpId: string
}>()

const visible = ref(false)
const loading = ref(false)
const error = ref<string | null>(null)
const exporting = ref(false)
const resultData = ref<PenetrateResult | null>(null)
const queryParams = ref<QueryParams | null>(null)
const expandedStrategies = ref<string[]>([])

/** 打开抽屉并执行穿透查询 */
async function open(amount: number, cellRef: string) {
  visible.value = true
  loading.value = true
  error.value = null
  resultData.value = null

  // 默认使用当前年度
  const currentYear = new Date().getFullYear()

  queryParams.value = {
    amount,
    tolerance: 0.01,
    cellRef,
    year: currentYear,
  }

  try {
    const params: Record<string, any> = {
      year: currentYear,
      amount,
      tolerance: 0.01,
    }

    const data = await api.get<PenetrateResult>(
      `/api/projects/${props.projectId}/ledger/penetrate-by-amount`,
      { params, validateStatus: (s: number) => s < 600 },
    )

    // 检查是否返回了错误
    if (!data || (data as any)?.detail) {
      error.value = (data as any)?.detail || '查询失败'
      return
    }

    resultData.value = data

    // 默认展开所有策略组
    if (data.matches?.length) {
      expandedStrategies.value = data.matches.map(g => g.strategy)
    }
  } catch (err: any) {
    error.value = '穿透查询失败: ' + (err?.message || '未知错误')
  } finally {
    loading.value = false
  }
}

/** 导出穿透结果到附件 */
async function onExportToAttachment() {
  if (!resultData.value || resultData.value.matches.length === 0) return

  exporting.value = true
  try {
    // 构建导出内容（CSV 格式）
    const csvContent = buildCsvContent(resultData.value)
    const blob = new Blob(['\uFEFF' + csvContent], { type: 'text/csv;charset=utf-8' })

    // 创建 FormData 上传
    const formData = new FormData()
    const fileName = `穿透结果_${queryParams.value?.cellRef || ''}_${queryParams.value?.amount || ''}.csv`
    formData.append('file', blob, fileName)
    formData.append('wp_id', props.wpId)
    formData.append('type', 'evidence')
    formData.append('description', `序时账穿透结果 - 金额 ${queryParams.value?.amount}，单元格 ${queryParams.value?.cellRef}`)

    await api.post(
      `/api/projects/${props.projectId}/attachments/upload`,
      formData,
    )

    ElMessage.success('穿透结果已导出为附件并关联到当前底稿')
  } catch (err: any) {
    ElMessage.error('导出失败: ' + (err?.message || '未知错误'))
  } finally {
    exporting.value = false
  }
}

/** 构建 CSV 内容 */
function buildCsvContent(data: PenetrateResult): string {
  const lines: string[] = []

  // 标题行
  lines.push(`序时账穿透结果 - 目标金额: ${queryParams.value?.amount}, 单元格: ${queryParams.value?.cellRef}`)
  lines.push(`查询时间: ${new Date().toLocaleString('zh-CN')}`)
  lines.push('')

  // 表头
  lines.push('策略,日期,凭证号,科目编码,科目名称,借方金额,贷方金额,摘要,对方科目')

  // 数据行
  for (const group of data.matches) {
    for (const item of group.items) {
      const row = [
        strategyLabel(group.strategy),
        item.voucher_date || '',
        item.voucher_no || '',
        item.account_code || '',
        item.account_name || '',
        item.debit_amount != null ? String(item.debit_amount) : '',
        item.credit_amount != null ? String(item.credit_amount) : '',
        (item.summary || '').replace(/,/g, '，'),  // 避免 CSV 逗号冲突
        (item.counterpart_account || '').replace(/,/g, '，'),
      ]
      lines.push(row.join(','))
    }
  }

  if (data.truncated) {
    lines.push('')
    lines.push('注意: 结果已截断（超过 200 条），请增加过滤条件')
  }

  return lines.join('\n')
}

function handleClose(done: () => void) {
  done()
}

function formatAmount(amount: number | null | undefined): string {
  if (amount == null) return '—'
  return Number(amount).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function strategyLabel(strategy: string): string {
  const map: Record<string, string> = {
    exact: '精确匹配',
    tolerance: '容差匹配',
    'code+amount': '科目+金额',
    summary: '摘要关键词',
  }
  return map[strategy] || strategy
}

function strategyTagType(strategy: string): 'success' | 'warning' | 'info' | 'primary' | 'danger' | undefined {
  const map: Record<string, 'success' | 'warning' | 'info' | 'primary' | 'danger' | undefined> = {
    exact: 'success',
    tolerance: 'warning',
    'code+amount': undefined,
    summary: 'info',
  }
  return map[strategy] || 'info'
}

// 暴露 open 方法供父组件调用
defineExpose({ open })
</script>

<style scoped>
.ledger-penetrate-drawer :deep(.el-drawer__header) {
  margin-bottom: 0;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.penetrate-params-bar {
  margin-bottom: 16px;
}

.drawer-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 300px;
  gap: 12px;
  color: #999;
}

.drawer-error {
  padding: 40px 20px;
}

.drawer-empty {
  padding: 40px 20px;
}

.empty-params {
  margin-top: 16px;
  text-align: left;
}

.empty-hint {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}

.penetrate-results {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.result-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
  font-size: 14px;
}

.strategy-collapse {
  border: none;
}

.strategy-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.strategy-count {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
