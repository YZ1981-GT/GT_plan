<template>
  <div class="related-party-disclosure-panel">
    <!-- 标题栏 -->
    <div class="related-party-disclosure-panel__header">
      <h3 class="related-party-disclosure-panel__title">关联方披露专项</h3>
      <el-tag v-if="tieoutDiffCount > 0" type="warning" size="small">
        {{ tieoutDiffCount }} 项差异
      </el-tag>
    </div>

    <!-- Tab 区域 -->
    <el-tabs v-model="activeTab" class="related-party-disclosure-panel__tabs">
      <!-- 主体 -->
      <el-tab-pane label="主体" name="parties">
        <el-empty v-if="parties.length === 0" description="暂无关联方主体" />
        <el-table v-else :data="parties" size="small" stripe>
          <el-table-column prop="party_name" label="关联方名称" min-width="120" />
          <el-table-column prop="relationship_type" label="关系类型" width="100" />
          <el-table-column prop="relationship_description" label="关系说明" min-width="150" />
        </el-table>
      </el-tab-pane>

      <!-- 交易 -->
      <el-tab-pane label="交易" name="transactions">
        <el-empty v-if="transactions.length === 0" description="暂无关联方交易" />
        <el-table v-else :data="transactions" size="small" stripe>
          <el-table-column prop="party_id" label="关联方" width="100" />
          <el-table-column prop="transaction_type" label="交易类型" width="100" />
          <el-table-column prop="current_amount" label="本期发生额" width="130" align="right" />
          <el-table-column prop="prior_amount" label="上期发生额" width="130" align="right" />
        </el-table>
      </el-tab-pane>

      <!-- 余额 -->
      <el-tab-pane label="余额" name="balances">
        <el-empty v-if="balances.length === 0" description="暂无关联方余额" />
        <el-table v-else :data="balances" size="small" stripe>
          <el-table-column prop="party_id" label="关联方" width="100" />
          <el-table-column prop="balance_type" label="余额类型" width="100">
            <template #default="{ row }">
              {{ row.balance_type === 'receivable' ? '应收' : '应付' }}
            </template>
          </el-table-column>
          <el-table-column prop="closing_balance" label="期末余额" width="130" align="right" />
          <el-table-column prop="opening_balance" label="期初余额" width="130" align="right" />
        </el-table>
      </el-tab-pane>

      <!-- 证据 -->
      <el-tab-pane label="证据" name="evidences">
        <el-empty v-if="evidences.length === 0" description="暂无证据信息" />
        <el-table v-else :data="evidences" size="small" stripe>
          <el-table-column prop="party_id" label="关联方" width="100" />
          <el-table-column label="已函证" width="80" align="center">
            <template #default="{ row }">
              <span :class="row.has_confirmation ? 'evidence-yes' : 'evidence-no'">
                {{ row.has_confirmation ? '是' : '否' }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="有附件" width="80" align="center">
            <template #default="{ row }">
              <span :class="row.has_attachment ? 'evidence-yes' : 'evidence-no'">
                {{ row.has_attachment ? '是' : '否' }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="confirmation_status" label="函证状态" width="100">
            <template #default="{ row }">
              {{ confirmationStatusLabel(row.confirmation_status) }}
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- Tie-out 差异 -->
      <el-tab-pane label="差异" name="tieout">
        <el-empty v-if="tieoutResults.length === 0" description="暂无 tie-out 结果" />
        <el-table v-else :data="tieoutResults" size="small" stripe>
          <el-table-column prop="rule_description" label="规则" min-width="200" />
          <el-table-column prop="note_total" label="附注合计" width="130" align="right" />
          <el-table-column prop="report_amount" label="报表金额" width="130" align="right" />
          <el-table-column prop="difference" label="差异" width="130" align="right">
            <template #default="{ row }">
              <span :class="{ 'tieout-diff': !row.is_balanced }">
                {{ row.difference }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag :type="row.is_balanced ? 'success' : 'danger'" size="small">
                {{ row.is_balanced ? '平衡' : '差异' }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

export interface RelatedParty {
  party_id: string
  party_name: string
  relationship_type: string
  relationship_description: string
}

export interface RelatedPartyTransaction {
  party_id: string
  transaction_type: string
  current_amount: string | number
  prior_amount: string | number
}

export interface RelatedPartyBalance {
  party_id: string
  balance_type: string
  closing_balance: string | number
  opening_balance: string | number
}

export interface RelatedPartyEvidence {
  party_id: string
  has_confirmation: boolean
  has_attachment: boolean
  confirmation_status: string
}

export interface TieoutResult {
  rule_description: string
  note_total: string | number
  report_amount: string | number
  difference: string | number
  is_balanced: boolean
}

interface Props {
  parties: RelatedParty[]
  transactions: RelatedPartyTransaction[]
  balances: RelatedPartyBalance[]
  evidences: RelatedPartyEvidence[]
  tieoutResults: TieoutResult[]
}

const props = defineProps<Props>()

const activeTab = ref<string>('parties')

const tieoutDiffCount = computed(() => {
  return props.tieoutResults.filter(t => !t.is_balanced).length
})

function confirmationStatusLabel(status: string): string {
  const map: Record<string, string> = {
    not_sent: '未发函',
    sent: '已发函',
    received: '已回函',
    confirmed: '已确认',
  }
  return map[status] || status
}
</script>

<style scoped>
.related-party-disclosure-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.related-party-disclosure-panel__header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--gt-color-border-purple-light, #d8b8ee);
}

.related-party-disclosure-panel__title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--gt-color-primary, #4b2d77);
}

.related-party-disclosure-panel__tabs {
  flex: 1;
  overflow: hidden;
}

.evidence-yes {
  color: #67c23a;
  font-weight: 500;
}

.evidence-no {
  color: #f56c6c;
  font-weight: 500;
}

.tieout-diff {
  color: #f56c6c;
  font-weight: 600;
}
</style>
