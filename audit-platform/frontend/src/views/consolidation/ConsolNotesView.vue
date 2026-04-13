<template>
  <div class="gt-consol-notes-view">
    <!-- 顶部工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <!-- 期间选择 -->
        <el-date-picker
          v-model="period"
          type="month"
          format="YYYY-MM"
          value-format="YYYY-MM"
          placeholder="选择期间"
          style="width: 140px"
          @change="loadAllNotes"
        />

        <!-- 编辑模式切换 -->
        <el-radio-group v-model="editMode" size="default">
          <el-radio-button value="preview">预览</el-radio-button>
          <el-radio-button value="edit">编辑</el-radio-button>
        </el-radio-group>
      </div>

      <div class="toolbar-right">
        <!-- 导出按钮 -->
        <el-dropdown @command="onExport" trigger="click">
          <el-button type="primary" plain>
            <el-icon><Download /></el-icon> 导出
            <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="excel">
                <el-icon><Document /></el-icon> 下载 Excel
              </el-dropdown-item>
              <el-dropdown-item command="pdf">
                <el-icon><Reading /></el-icon> 下载 PDF
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>

        <el-button :loading="loading" @click="loadAllNotes" plain>
          <el-icon><Refresh /></el-icon> 刷新
        </el-button>
      </div>
    </div>

    <!-- 附注内容区域 -->
    <div class="notes-content" v-loading="loading">
      <el-collapse v-model="activeNames" accordion class="notes-collapse">

        <!-- 1. 合并范围附注 -->
        <el-collapse-item name="scope" title="合并范围">
          <template #title>
            <span class="collapse-title">
              <el-icon><FolderOpened /></el-icon> 合并范围
            </span>
          </template>
          <div class="section-content">
            <div class="section-toolbar" v-if="editMode === 'edit'">
              <el-button size="small" type="primary" plain @click="onAddScope">
                <el-icon><Plus /></el-icon> 添加
              </el-button>
            </div>
            <el-table
              :data="consolScope"
              border
              stripe
              size="small"
              max-height="320"
              :header-cell-style="headerCellStyle"
            >
              <el-table-column prop="seq" label="序号" width="60" align="center" />
              <el-table-column prop="company_name" label="子公司名称" min-width="160" />
              <el-table-column prop="shareholding" label="持股比例" width="100" align="center">
                <template #default="{ row }">{{ row.shareholding }}%</template>
              </el-table-column>
              <el-table-column prop="voting_rights" label="表决权比例" width="100" align="center">
                <template #default="{ row }">{{ row.voting_rights }}%</template>
              </el-table-column>
              <el-table-column prop="is_included" label="是否纳入合并" width="110" align="center">
                <template #default="{ row }">
                  <el-tag :type="row.is_included ? 'success' : 'danger'" size="small">
                    {{ row.is_included ? '是' : '否' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="inclusion_date" label="纳入日期" width="110" />
              <el-table-column prop="exit_date" label="退出日期" width="110">
                <template #default="{ row }">{{ row.exit_date || '—' }}</template>
              </el-table-column>
              <el-table-column prop="notes" label="备注" min-width="120" />
            </el-table>
          </div>
        </el-collapse-item>

        <!-- 2. 主要子公司信息附注 -->
        <el-collapse-item name="subsidiaries" title="主要子公司信息">
          <template #title>
            <span class="collapse-title">
              <el-icon><OfficeBuilding /></el-icon> 主要子公司信息
            </span>
          </template>
          <div class="section-content">
            <el-table
              :data="subsidiaries"
              border
              stripe
              size="small"
              max-height="360"
              :header-cell-style="headerCellStyle"
            >
              <el-table-column prop="company_name" label="子公司名称" min-width="160" />
              <el-table-column prop="registration_place" label="注册地" min-width="120" />
              <el-table-column prop="business_nature" label="业务性质" width="120" />
              <el-table-column prop="registered_capital" label="注册资本" width="120" align="right">
                <template #default="{ row }"><span class="amount">{{ formatNum(row.registered_capital) }}</span></template>
              </el-table-column>
              <el-table-column prop="paid_capital" label="实收资本" width="120" align="right">
                <template #default="{ row }"><span class="amount">{{ formatNum(row.paid_capital) }}</span></template>
              </el-table-column>
              <el-table-column prop="shareholding" label="持股比例" width="90" align="center">
                <template #default="{ row }">{{ row.shareholding }}%</template>
              </el-table-column>
              <el-table-column prop="minority_equity_end" label="期末少数股东权益" width="150" align="right">
                <template #default="{ row }"><span class="amount">{{ formatNum(row.minority_equity_end) }}</span></template>
              </el-table-column>
            </el-table>
          </div>
        </el-collapse-item>

        <!-- 3. 商誉附注 -->
        <el-collapse-item name="goodwill" title="商誉">
          <template #title>
            <span class="collapse-title">
              <el-icon><Coin /></el-icon> 商誉
            </span>
          </template>
          <div class="section-content">
            <div class="section-info" v-if="goodwill.length">
              <p class="info-text">
                <el-icon><InfoFilled /></el-icon>
                商誉 = 合并成本 - 可辨认净资产公允价值 × 母公司持股比例
              </p>
            </div>
            <el-table
              :data="goodwill"
              border
              stripe
              size="small"
              max-height="320"
              :header-cell-style="headerCellStyle"
            >
              <el-table-column prop="acquiree" label="被收购方" min-width="160" />
              <el-table-column prop="opening_balance" label="期初余额" width="140" align="right">
                <template #default="{ row }"><span class="amount">{{ formatNum(row.opening_balance) }}</span></template>
              </el-table-column>
              <el-table-column prop="current_increase" label="本期增加" width="140" align="right">
                <template #default="{ row }"><span class="amount positive">{{ formatSignedNum(row.current_increase) }}</span></template>
              </el-table-column>
              <el-table-column prop="current_decrease" label="本期减少" width="140" align="right">
                <template #default="{ row }"><span class="amount negative">{{ formatSignedNum(row.current_decrease) }}</span></template>
              </el-table-column>
              <el-table-column prop="current_impairment" label="本期计提减值" width="140" align="right">
                <template #default="{ row }"><span class="amount negative">{{ formatSignedNum(row.current_impairment) }}</span></template>
              </el-table-column>
              <el-table-column prop="closing_balance" label="期末余额" width="140" align="right">
                <template #default="{ row }"><span class="amount bold">{{ formatNum(row.closing_balance) }}</span></template>
              </el-table-column>
            </el-table>
            <!-- 商誉合计行 -->
            <div class="table-summary" v-if="goodwill.length">
              <span class="summary-label">合计</span>
              <span class="summary-cell"><span class="amount">{{ formatNum(totalGoodwill.opening) }}</span></span>
              <span class="summary-cell"><span class="amount positive">{{ formatSignedNum(totalGoodwill.increase) }}</span></span>
              <span class="summary-cell"><span class="amount negative">{{ formatSignedNum(totalGoodwill.decrease) }}</span></span>
              <span class="summary-cell"><span class="amount negative">{{ formatSignedNum(totalGoodwill.impairment) }}</span></span>
              <span class="summary-cell"><span class="amount bold">{{ formatNum(totalGoodwill.closing) }}</span></span>
            </div>
          </div>
        </el-collapse-item>

        <!-- 4. 少数股东权益附注 -->
        <el-collapse-item name="minority_interest" title="少数股东权益">
          <template #title>
            <span class="collapse-title">
              <el-icon><User /></el-icon> 少数股东权益
            </span>
          </template>
          <div class="section-content">
            <el-table
              :data="minorityInterest"
              border
              stripe
              size="small"
              max-height="360"
              :header-cell-style="headerCellStyle"
            >
              <el-table-column prop="subsidiary_name" label="子公司名称" min-width="160" />
              <el-table-column prop="opening_balance" label="期初余额" width="130" align="right">
                <template #default="{ row }"><span class="amount">{{ formatNum(row.opening_balance) }}</span></template>
              </el-table-column>
              <el-table-column prop="share_of_profit" label="享有的净利润" width="130" align="right">
                <template #default="{ row }">
                  <span class="amount" :class="getChangeClass(row.share_of_profit)">
                    {{ formatSignedNum(row.share_of_profit) }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column prop="share_of_loss" label="承担的净亏损" width="130" align="right">
                <template #default="{ row }"><span class="amount negative">{{ formatSignedNum(row.share_of_loss) }}</span></template>
              </el-table-column>
              <el-table-column prop="dividends_paid" label="宣告分配的股利" width="130" align="right">
                <template #default="{ row }"><span class="amount negative">{{ formatSignedNum(row.dividends_paid) }}</span></template>
              </el-table-column>
              <el-table-column prop="other_changes" label="其他变动" width="120" align="right">
                <template #default="{ row }"><span class="amount">{{ formatSignedNum(row.other_changes) }}</span></template>
              </el-table-column>
              <el-table-column prop="closing_balance" label="期末余额" width="130" align="right">
                <template #default="{ row }"><span class="amount bold">{{ formatNum(row.closing_balance) }}</span></template>
              </el-table-column>
            </el-table>
          </div>
        </el-collapse-item>

        <!-- 5. 内部交易附注 -->
        <el-collapse-item name="internal_trade" title="内部交易">
          <template #title>
            <span class="collapse-title">
              <el-icon><Goods /></el-icon> 内部交易
            </span>
          </template>
          <div class="section-content">
            <h4 class="sub-title">内部交易汇总表</h4>
            <el-table
              :data="internalTrades"
              border
              stripe
              size="small"
              max-height="260"
              :header-cell-style="headerCellStyle"
            >
              <el-table-column prop="trade_type" label="类型" width="120" />
              <el-table-column prop="trade_amount" label="交易金额" width="160" align="right">
                <template #default="{ row }"><span class="amount">{{ formatNum(row.trade_amount) }}</span></template>
              </el-table-column>
              <el-table-column prop="elimination_amount" label="抵消金额" width="160" align="right">
                <template #default="{ row }"><span class="amount negative">{{ formatNum(row.elimination_amount) }}</span></template>
              </el-table-column>
            </el-table>

            <h4 class="sub-title" style="margin-top: 16px;">内部往来余额表</h4>
            <el-table
              :data="internalArAp"
              border
              stripe
              size="small"
              max-height="260"
              :header-cell-style="headerCellStyle"
            >
              <el-table-column prop="arap_type" label="往来类型" width="120">
                <template #default="{ row }">
                  {{ row.arap_type === 'ar' ? '应收账款' : row.arap_type === 'ap' ? '应付账款' : row.arap_type }}
                </template>
              </el-table-column>
              <el-table-column prop="debit_balance" label="借方余额" width="160" align="right">
                <template #default="{ row }"><span class="amount">{{ formatNum(row.debit_balance) }}</span></template>
              </el-table-column>
              <el-table-column prop="credit_balance" label="贷方余额" width="160" align="right">
                <template #default="{ row }"><span class="amount">{{ formatNum(row.credit_balance) }}</span></template>
              </el-table-column>
              <el-table-column prop="after_elimination" label="抵消后余额" width="160" align="right">
                <template #default="{ row }"><span class="amount bold">{{ formatNum(row.after_elimination) }}</span></template>
              </el-table-column>
            </el-table>
          </div>
        </el-collapse-item>

        <!-- 6. 外币折算附注 -->
        <el-collapse-item name="forex" title="外币折算">
          <template #title>
            <span class="collapse-title">
              <el-icon><Currency /></el-icon> 外币折算
            </span>
          </template>
          <div class="section-content">
            <div class="section-info">
              <p class="info-text">
                <el-icon><InfoFilled /></el-icon>
                境外子公司报表折算方法：资产负债表资产和负债项目采用报表折算汇率，利润表项目采用收入费用平均汇率
              </p>
            </div>
            <el-table
              :data="forexTranslation"
              border
              stripe
              size="small"
              max-height="320"
              :header-cell-style="headerCellStyle"
            >
              <el-table-column prop="currency" label="币种" width="100" />
              <el-table-column prop="statement_rate" label="报表折算汇率" width="150" align="right">
                <template #default="{ row }"><span class="amount">{{ row.statement_rate || '—' }}</span></template>
              </el-table-column>
              <el-table-column prop="income_expense_avg_rate" label="收入费用平均汇率" width="160" align="right">
                <template #default="{ row }"><span class="amount">{{ row.income_expense_avg_rate || '—' }}</span></template>
              </el-table-column>
              <el-table-column prop="translation_diff" label="折算差额" width="150" align="right">
                <template #default="{ row }">
                  <span class="amount" :class="getChangeClass(row.translation_diff)">
                    {{ formatSignedNum(row.translation_diff) }}
                  </span>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-collapse-item>

        <!-- 7. 其他重要事项 -->
        <el-collapse-item name="other" title="其他重要事项">
          <template #title>
            <span class="collapse-title">
              <el-icon><Document /></el-icon> 其他重要事项
            </span>
          </template>
          <div class="section-content">
            <template v-if="editMode === 'edit'">
              <el-input
                v-model="otherMatters"
                type="textarea"
                :rows="8"
                placeholder="请输入其他重要事项说明..."
                @blur="onSaveOtherMatters"
              />
              <div class="save-hint">
                <el-button size="small" type="primary" @click="onSaveOtherMatters" :loading="saving">
                  <el-icon><Select /></el-icon> 保存
                </el-button>
                <span class="hint-text">离开编辑模式时内容自动保存</span>
              </div>
            </template>
            <template v-else>
              <div class="other-matters-display">
                <pre class="other-matters-text">{{ otherMatters || '暂无其他重要事项' }}</pre>
              </div>
            </template>
          </div>
        </el-collapse-item>

      </el-collapse>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Refresh,
  Download,
  ArrowDown,
  Document,
  Reading,
  FolderOpened,
  OfficeBuilding,
  Coin,
  User,
  Goods,
  Currency,
  InfoFilled,
  Plus,
  Select,
} from '@element-plus/icons-vue'
import {
  getConsolScopeNotes,
  getSubsidiaryNotes,
  getGoodwillNotes,
  getMinorityInterestNotes,
  getInternalTradeNotes,
  getForexTranslationNotes,
  saveConsolNotes,
  downloadConsolNotesExcel,
  downloadConsolNotesPDF,
  type ConsolScopeNote,
  type SubsidiaryNote,
  type GoodwillNote,
  type MinorityInterestNote,
  type InternalTradeNote,
  type InternalArApNote,
  type ForexTranslationNote,
} from '@/services/consolidationApi'

// ─── Props & Emits ────────────────────────────────────────────────────────────
const props = defineProps<{
  projectId: string
  period?: string
}>()

// ─── State ────────────────────────────────────────────────────────────────────
const loading = ref(false)
const exporting = ref(false)
const saving = ref(false)
const period = ref(props.period || new Date().toISOString().slice(0, 7))
const editMode = ref<'preview' | 'edit'>('preview')
const activeNames = ref<string[]>(['scope'])

// 附注数据
const consolScope = ref<ConsolScopeNote[]>([])
const subsidiaries = ref<SubsidiaryNote[]>([])
const goodwill = ref<GoodwillNote[]>([])
const minorityInterest = ref<MinorityInterestNote[]>([])
const internalTrades = ref<InternalTradeNote[]>([])
const internalArAp = ref<InternalArApNote[]>([])
const forexTranslation = ref<ForexTranslationNote[]>([])
const otherMatters = ref('')

// ─── Computed ─────────────────────────────────────────────────────────────────
const headerCellStyle = computed(() => ({
  background: 'var(--gt-color-primary, #4b2d77)',
  color: '#fff',
  fontWeight: '600',
  fontSize: '13px',
}))

const totalGoodwill = computed(() => {
  const sum = (arr: GoodwillNote[], key: keyof GoodwillNote) =>
    arr.reduce((acc, r) => acc + (parseFloat(String(r[key]) || '0') || 0), 0)
  return {
    opening: sum(goodwill.value, 'opening_balance'),
    increase: sum(goodwill.value, 'current_increase'),
    decrease: sum(goodwill.value, 'current_decrease'),
    impairment: sum(goodwill.value, 'current_impairment'),
    closing: sum(goodwill.value, 'closing_balance'),
  }
})

// ─── Methods ───────────────────────────────────────────────────────────────────
function formatNum(val: string | number | undefined): string {
  if (val === undefined || val === null || val === '') return '—'
  const num = typeof val === 'string' ? parseFloat(val) : val
  if (isNaN(num)) return '—'
  return num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatSignedNum(val: string | number | undefined): string {
  if (val === undefined || val === null || val === '') return '—'
  const num = typeof val === 'string' ? parseFloat(val) : val
  if (isNaN(num)) return '—'
  const sign = num >= 0 ? '+' : ''
  return sign + num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function getChangeClass(val: string | number | undefined): string {
  if (val === undefined || val === null || val === '') return ''
  const num = typeof val === 'string' ? parseFloat(val) : val
  if (isNaN(num)) return ''
  if (num > 0) return 'positive'
  if (num < 0) return 'negative'
  return ''
}

// ─── Data Loading ─────────────────────────────────────────────────────────────
async function loadAllNotes() {
  loading.value = true
  try {
    const [scope, subs, gw, mi, tradeNotes, fx] = await Promise.all([
      getConsolScopeNotes(props.projectId, period.value),
      getSubsidiaryNotes(props.projectId, period.value),
      getGoodwillNotes(props.projectId, period.value),
      getMinorityInterestNotes(props.projectId, period.value),
      getInternalTradeNotes(props.projectId, period.value),
      getForexTranslationNotes(props.projectId, period.value),
    ])
    consolScope.value = scope
    subsidiaries.value = subs
    goodwill.value = gw
    minorityInterest.value = mi
    internalTrades.value = tradeNotes.trades
    internalArAp.value = tradeNotes.arap
    forexTranslation.value = fx
  } catch (e: any) {
    ElMessage.error(e?.message || '加载附注数据失败')
  } finally {
    loading.value = false
  }
}

async function onSaveOtherMatters() {
  saving.value = true
  try {
    await saveConsolNotes(props.projectId, period.value, { other_matters: otherMatters.value } as any)
    ElMessage.success('保存成功')
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function onAddScope() {
  // 添加新的合并范围行（空行占位，具体编辑逻辑由父组件处理）
  consolScope.value.push({
    seq: consolScope.value.length + 1,
    company_name: '',
    shareholding: '',
    voting_rights: '',
    is_included: true,
    inclusion_date: period.value + '-01',
    notes: '',
  })
  ElMessage.info('已添加空行，请填写内容后保存')
}

async function onExport(command: 'excel' | 'pdf') {
  exporting.value = true
  try {
    let url: string
    if (command === 'excel') {
      url = await downloadConsolNotesExcel(props.projectId, period.value)
      ElMessage.success('Excel 导出任务已提交')
    } else {
      url = await downloadConsolNotesPDF(props.projectId, period.value)
      ElMessage.success('PDF 导出任务已提交')
    }
    if (url) {
      const a = document.createElement('a')
      a.href = url
      a.download = ''
      a.click()
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '导出失败')
  } finally {
    exporting.value = false
  }
}

// ─── Lifecycle ─────────────────────────────────────────────────────────────────
onMounted(() => {
  loadAllNotes()
})

watch(() => props.projectId, () => {
  if (props.projectId) loadAllNotes()
})

watch(() => props.period, (val) => {
  if (val) {
    period.value = val
    loadAllNotes()
  }
})
</script>

<style scoped>
.gt-consol-notes-view {
  display: flex;
  flex-direction: column;
  gap: var(--gt-space-4, 12px);
  padding: var(--gt-space-4, 12px);
  height: 100%;
  box-sizing: border-box;
}

/* 工具栏 */
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--gt-space-3, 8px);
  padding: var(--gt-space-3, 8px) var(--gt-space-4, 12px);
  background: var(--gt-color-primary-light, #A06DFF);
  border-radius: var(--gt-radius-md, 8px);
  box-shadow: var(--gt-shadow-sm, 0 1px 3px rgba(75,45,119,0.075));
}

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: var(--gt-space-3, 8px);
  flex-wrap: wrap;
}

/* 附注内容 */
.notes-content {
  flex: 1;
  overflow: auto;
}

/* 手风琴样式 */
.notes-collapse {
  border-radius: var(--gt-radius-md, 8px);
  overflow: hidden;
}

.notes-collapse :deep(.el-collapse-item__header) {
  background: var(--gt-color-primary, #4b2d77);
  color: #fff;
  font-weight: 600;
  font-size: 14px;
  padding: 0 16px;
  height: 44px;
  line-height: 44px;
  border-bottom: 1px solid var(--gt-color-primary-dark, #2B1D4D);
}

.notes-collapse :deep(.el-collapse-item__wrap) {
  border-bottom: 1px solid #e8e0f0;
}

.notes-collapse :deep(.el-collapse-item__content) {
  padding: 0;
}

.collapse-title {
  display: flex;
  align-items: center;
  gap: var(--gt-space-2, 6px);
}

.collapse-title .el-icon {
  font-size: 16px;
}

/* 区块内容 */
.section-content {
  padding: var(--gt-space-4, 12px);
}

.section-toolbar {
  margin-bottom: var(--gt-space-3, 8px);
}

.sub-title {
  margin: 0 0 var(--gt-space-3, 8px);
  font-size: 13px;
  font-weight: 600;
  color: var(--gt-color-primary, #4b2d77);
  padding-left: var(--gt-space-2, 6px);
  border-left: 3px solid var(--gt-color-primary, #4b2d77);
}

.section-info {
  margin-bottom: var(--gt-space-3, 8px);
}

.info-text {
  display: flex;
  align-items: center;
  gap: var(--gt-space-2, 6px);
  margin: 0;
  font-size: 12px;
  color: #666;
  background: #f5f0ff;
  padding: var(--gt-space-2, 6px) var(--gt-space-3, 8px);
  border-radius: var(--gt-radius-sm, 4px);
}

.info-text .el-icon {
  color: var(--gt-color-teal, #0094B3);
}

/* 金额样式 */
.amount {
  font-family: 'Helvetica Neue', Arial, sans-serif;
  font-size: 13px;
}

.amount.bold {
  font-weight: 700;
}

.amount.positive {
  color: var(--gt-color-success, #28A745);
}

.amount.negative {
  color: var(--gt-color-coral, #FF5149);
}

/* 合计行 */
.table-summary {
  display: flex;
  align-items: center;
  padding: var(--gt-space-2, 6px) var(--gt-space-3, 8px);
  background: #f5f0ff;
  border-top: 1px solid #e8e0f0;
  font-size: 13px;
  font-weight: 600;
}

.summary-label {
  flex: 0 0 160px;
  color: var(--gt-color-primary, #4b2d77);
}

.summary-cell {
  flex: 1;
  text-align: right;
  padding-right: var(--gt-space-3, 8px);
}

/* 其他重要事项 */
.other-matters-display {
  background: #fafafa;
  border-radius: var(--gt-radius-sm, 4px);
  padding: var(--gt-space-4, 12px);
  min-height: 120px;
}

.other-matters-text {
  margin: 0;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.8;
  white-space: pre-wrap;
  color: #333;
}

.save-hint {
  display: flex;
  align-items: center;
  gap: var(--gt-space-3, 8px);
  margin-top: var(--gt-space-3, 8px);
}

.hint-text {
  font-size: 12px;
  color: #999;
}
</style>
