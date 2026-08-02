<template>
  <div class="wealth-dashboard">
    <el-collapse v-model="expanded">
      <el-collapse-item title="理财产品发函概览" name="overview">
        <div class="wealth-dashboard__cards">
          <div class="wealth-dashboard__card">
            <div class="wealth-dashboard__card-value">{{ metrics.total_count }}</div>
            <div class="wealth-dashboard__card-label">产品笔数</div>
          </div>
          <div class="wealth-dashboard__card wealth-dashboard__card--wide">
            <div class="wealth-dashboard__card-value">{{ fmt(metrics.net_value_total) }}</div>
            <div class="wealth-dashboard__card-label">
              发函金额合计
              <el-tooltip placement="top">
                <template #content>
                  源模板 E0-1 F 列 <code>SUMIFS(E0-6!$H:$H, …)</code><br />
                  按「索引号 + 产品名称」汇入「发函金额（原币）」
                </template>
                <el-icon :size="12"><QuestionFilled /></el-icon>
              </el-tooltip>
            </div>
          </div>
          <div
            class="wealth-dashboard__card"
            :class="{ 'wealth-dashboard__card--danger': metrics.missing_key_count > 0 }"
          >
            <div class="wealth-dashboard__card-value">{{ metrics.missing_key_count }}</div>
            <div class="wealth-dashboard__card-label">汇总键缺失</div>
          </div>
          <div
            class="wealth-dashboard__card"
            :class="{ 'wealth-dashboard__card--warn-bg': metrics.restricted_count > 0 }"
          >
            <div class="wealth-dashboard__card-value">{{ metrics.restricted_count }}</div>
            <div class="wealth-dashboard__card-label">受限笔数</div>
          </div>
          <div class="wealth-dashboard__card wealth-dashboard__card--wide">
            <div class="wealth-dashboard__card-value wealth-dashboard__card-value--warn">
              {{ fmt(metrics.restricted_amount) }}
            </div>
            <div class="wealth-dashboard__card-label">受限金额</div>
          </div>
          <div
            class="wealth-dashboard__card"
            :class="{ 'wealth-dashboard__card--warn-bg': metrics.matured_count > 0 }"
          >
            <div class="wealth-dashboard__card-value">{{ metrics.matured_count }}</div>
            <div class="wealth-dashboard__card-label">期末已到期</div>
          </div>
          <div class="wealth-dashboard__card">
            <div class="wealth-dashboard__card-value wealth-dashboard__card-value--muted">
              {{ metrics.closed_count }} / {{ metrics.open_count }}
            </div>
            <div class="wealth-dashboard__card-label">封闭式 / 开放式</div>
          </div>
        </div>
      </el-collapse-item>
    </el-collapse>

    <div v-if="alerts.length" class="wealth-dashboard__alerts">
      <el-alert
        v-for="(alert, idx) in alerts"
        :key="idx"
        :title="alert.title"
        :type="alert.type"
        :closable="false"
        show-icon
        class="wealth-dashboard__alert-item"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { QuestionFilled } from '@element-plus/icons-vue'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import type { WealthListMetrics } from './wealthListTypes'

const props = defineProps<{
  metrics: WealthListMetrics
}>()

const expanded = ref<string[]>(['overview'])

// 金额格式单一真源 = displayPrefs.fmtAmount（**store 成员，不是模块级导出**）。
// 必须在 setup 顶层取 store：写进函数体会静默失效（setup 作用域 composable 铁律）。
const displayPrefs = useDisplayPrefsStore()
function fmt(v: number): string {
  return displayPrefs.fmtAmount(v)
}

interface AlertItem {
  title: string
  type: 'warning' | 'error' | 'info' | 'success'
}

const alerts = computed<AlertItem[]>(() => {
  const list: AlertItem[] = []
  const m = props.metrics

  if (m.missing_key_count > 0) {
    list.push({
      type: 'error',
      title:
        `${m.missing_key_count} 笔缺「索引号」或「产品名称」——`
        + 'E0-1 的发函金额按「索引号 + 产品名称」两个键匹配本表，缺任一则该笔金额无法汇入 E0-1（显示为 0）。',
    })
  }

  if (m.matured_count > 0) {
    list.push({
      type: 'warning',
      title:
        `${m.matured_count} 笔「到期日」不晚于「报表截止日」——`
        + '请核实期末是否仍应列示为在持产品，或已到期兑付而应终止确认。',
    })
  }

  if (m.restricted_count > 0) {
    list.push({
      type: 'warning',
      title:
        `${m.restricted_count} 笔被用于担保或存在其他使用限制（合计 ${fmt(m.restricted_amount)}）——`
        + '应在受限资产相关披露中反映：计入其他货币资金的进 E1「受限制的货币资金明细」，'
        + '计入交易性金融资产等的进「所有权或使用权受到限制的资产」附注段。',
    })
  }

  if (m.zero_amount_count > 0 && m.total_count > 0) {
    list.push({
      type: 'info',
      title: `${m.zero_amount_count} 笔「产品净值」为空或 0，对应的 E0-1 发函金额将为 0。`,
    })
  }

  return list
})
</script>

<style scoped>
.wealth-dashboard__cards {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}

.wealth-dashboard__card {
  flex: 1;
  min-width: 96px;
  padding: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
  text-align: center;
}

.wealth-dashboard__card--wide {
  min-width: 150px;
  flex: 1.6;
}

.wealth-dashboard__card--danger {
  background: var(--el-color-danger-light-9);
  border: 1px solid var(--el-color-danger-light-5);
}

.wealth-dashboard__card--warn-bg {
  background: var(--el-color-warning-light-9);
  border: 1px solid var(--el-color-warning-light-5);
}

.wealth-dashboard__card-value {
  font-size: 20px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  color: var(--el-text-color-primary);
}

.wealth-dashboard__card-value--warn {
  color: var(--el-color-warning);
}

.wealth-dashboard__card-value--muted {
  color: var(--el-text-color-regular);
}

.wealth-dashboard__card-label {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 3px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}

.wealth-dashboard__alerts {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.wealth-dashboard__alert-item {
  margin: 0;
}

.wealth-dashboard__alert-item :deep(.el-alert__title) {
  font-size: 12px;
  line-height: 1.7;
}
</style>
