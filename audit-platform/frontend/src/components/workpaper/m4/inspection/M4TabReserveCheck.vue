<template>
  <div class="m4-tab-reserve-check">
    <!-- ═══ 标题 + 操作栏 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M4-4 资本公积检查表</h3>
        <el-tag type="success" effect="dark" size="small" class="equity-badge">
          权益类·贷方余额
        </el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>资本公积检查要点：</strong>
        ①抽查本期资本公积变动凭证（增加=贷方：溢价/股份支付/外币折算；减少=借方：转增/弥补）。
        ②检查覆盖率 = 检查金额合计 ÷ 本期发生额。
        ③核对J3股份支付权益结算确认金额与账面其他资本公积增加是否一致（差异>阈值红色高亮）。
        ④M2外币出资折算差异核对。
      </div>
    </div>

    <!-- ═══ Section 1: 凭证抽查核对（动态行表格） ═══ -->
    <el-card shadow="never" class="check-card">
      <template #header>
        <div class="card-header">
          <span>凭证抽查核对</span>
          <div class="card-header-right">
            <el-button size="small" :disabled="isReadonly" type="primary" @click="handleAddVoucherRow">
              <el-icon><Plus /></el-icon> 新增
            </el-button>
            <el-button size="small" @click="handleAI('voucher-check')">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
          </div>
        </div>
      </template>

      <el-table :data="check.computedVoucherRows.value" border size="small" style="width: 100%">
        <el-table-column type="index" label="#" width="45" align="center" />
        <el-table-column label="凭证日期" min-width="110">
          <template #default="{ row, $index }">
            <el-date-picker
              v-if="!isReadonly"
              :model-value="row.voucherDate"
              type="date"
              size="small"
              value-format="YYYY-MM-DD"
              placeholder="日期"
              style="width: 100%"
              @change="(val: string) => check.updateVoucherRow($index, 'voucherDate', val || '')"
            />
            <span v-else>{{ row.voucherDate || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证编号" min-width="110">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.voucherNo"
              size="small"
              placeholder="凭证号"
              @change="(val: string) => check.updateVoucherRow($index, 'voucherNo', val)"
            />
            <span v-else>{{ row.voucherNo || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="业务内容" min-width="140">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.summary"
              size="small"
              placeholder="摘要"
              @change="(val: string) => check.updateVoucherRow($index, 'summary', val)"
            />
            <span v-else>{{ row.summary || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="对方科目" min-width="120">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.accountName"
              size="small"
              placeholder="对方科目"
              @change="(val: string) => check.updateVoucherRow($index, 'accountName', val)"
            />
            <span v-else>{{ row.accountName || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="借方金额" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.debitAmount"
              :controls="false"
              :min="0"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => check.updateVoucherRow($index, 'debitAmount', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="贷方金额" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.creditAmount"
              :controls="false"
              :min="0"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => check.updateVoucherRow($index, 'creditAmount', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="检查金额" min-width="110" align="right">
          <template #header>
            <el-tooltip content="检查金额 = max(借方, 贷方)" placement="top">
              <span class="formula-col-header">检查金额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.checkAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核对结果" width="90" align="center">
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.checkResult"
              size="small"
              placeholder="—"
              @change="(val: string) => check.updateVoucherRow($index, 'checkResult', val)"
            >
              <el-option label="√ 一致" value="√" />
              <el-option label="× 差异" value="×" />
              <el-option label="? 存疑" value="?" />
            </el-select>
            <el-tag v-else :type="row.checkResult === '√' ? 'success' : row.checkResult === '×' ? 'danger' : 'info'" size="small">
              {{ row.checkResult || '—' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="120">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.diffNote"
              size="small"
              placeholder="差异说明"
              @change="(val: string) => check.updateVoucherRow($index, 'diffNote', val)"
            />
            <span v-else>{{ row.diffNote || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="60" align="center">
          <template #default="{ $index }">
            <el-button type="danger" text size="small" @click="check.removeVoucherRow($index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 检查金额合计 + 检查覆盖率 -->
      <div class="ratio-bar">
        <span>检查金额合计：<strong class="formula-value">{{ fmtAmount(check.totalCheckAmount.value) }}</strong></span>
        <el-divider direction="vertical" />
        <span>本期发生额：<strong>{{ fmtAmount(check.checkRatio.value.periodAmount) }}</strong></span>
        <el-divider direction="vertical" />
        <span>
          检查覆盖率：
          <el-tag
            :type="coverageTagType"
            size="small"
            effect="dark"
          >
            {{ check.checkRatio.value.ratio !== null ? (check.checkRatio.value.ratio * 100).toFixed(1) + '%' : '—' }}
          </el-tag>
        </span>
      </div>
    </el-card>

    <!-- ═══ Section 2: J3 股份支付确认差异核对 ═══ -->
    <el-card shadow="never" class="check-card">
      <template #header>
        <div class="card-header">
          <span>J3 股份支付确认差异核对</span>
          <div class="card-header-right">
            <GtIndexChip value="J3" label="→J3股份支付" />
            <el-button size="small" @click="handleAI('share-based')">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
          </div>
        </div>
      </template>

      <!-- J3股份支付未就绪提示 -->
      <el-alert
        v-if="check.j3EquitySettled.value === 0 && check.bookedOtherIncrease.value === 0"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
      >
        待J3股份支付确认（EventBus 'j3:equity-settled' 尚未接收到数据）
      </el-alert>

      <div class="share-based-grid">
        <div class="share-based-item">
          <div class="share-based-label">J3确认金额</div>
          <div class="share-based-value">
            <el-input-number
              v-if="!isReadonly"
              :model-value="check.j3EquitySettled.value"
              :controls="false"
              size="small"
              style="width: 160px"
              @change="(val: number | undefined) => check.setJ3EquitySettled(val ?? 0)"
            />
            <span v-else class="formula-value">{{ fmtAmount(check.j3EquitySettled.value) }}</span>
          </div>
        </div>
        <div class="share-based-item">
          <div class="share-based-label">账面其他资本公积增加</div>
          <div class="share-based-value">
            <el-input-number
              v-if="!isReadonly"
              :model-value="check.bookedOtherIncrease.value"
              :controls="false"
              size="small"
              style="width: 160px"
              @change="(val: number | undefined) => check.setBookedOtherIncrease(val ?? 0)"
            />
            <span v-else class="formula-value">{{ fmtAmount(check.bookedOtherIncrease.value) }}</span>
          </div>
        </div>
        <div class="share-based-item">
          <div class="share-based-label">确认差异</div>
          <div class="share-based-value">
            <span :class="['diff-value', !check.shareBasedCheck.value.isConsistent ? 'diff-danger' : 'diff-ok']">
              {{ fmtAmount(check.shareBasedCheck.value.diff) }}
            </span>
            <el-tag
              :type="check.shareBasedCheck.value.isConsistent ? 'success' : 'danger'"
              size="small"
              style="margin-left: 8px"
            >
              {{ check.shareBasedCheck.value.isConsistent ? '差异在容忍范围内' : '差异超阈值！' }}
            </el-tag>
          </div>
        </div>
      </div>
    </el-card>

    <!-- ═══ Section 3: 核对清单 ═══ -->
    <el-card shadow="never" class="check-card">
      <template #header>
        <div class="card-header">
          <span>核对清单</span>
          <el-button size="small" @click="handleAI('checklist')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>

      <div class="checklist-section">
        <div v-for="(item, idx) in check.checklist.value" :key="idx" class="checklist-item">
          <span class="checklist-index">{{ item.index }}.</span>
          <span class="checklist-text">{{ item.item }}</span>
          <el-radio-group
            v-if="!isReadonly"
            :model-value="item.passed"
            size="small"
            @change="(val: boolean | null) => check.updateChecklistItem(idx, 'passed', val)"
          >
            <el-radio-button :value="true">通过</el-radio-button>
            <el-radio-button :value="false">不通过</el-radio-button>
          </el-radio-group>
          <el-tag v-else :type="item.passed === true ? 'success' : item.passed === false ? 'danger' : 'info'" size="small">
            {{ item.passed === true ? '通过' : item.passed === false ? '不通过' : '待核' }}
          </el-tag>
        </div>
      </div>
    </el-card>

    <!-- ═══ Section 4: 审计结论区（el-card包裹） ═══ -->
    <el-card shadow="never" class="check-card conclusion-card">
      <template #header>
        <div class="card-header">
          <span>审计结论</span>
          <el-button size="small" @click="handleAI('conclusion')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>

      <el-input
        :model-value="check.conclusion.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="根据凭证抽查及股份支付核对结果，填写资本公积审计结论..."
        @change="(val: string) => check.setConclusion(val)"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="m4-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>资本公积（4002）为<strong>权益类贷方科目</strong>：期末 = 期初 + 贷方（增加） − 借方（减少）</li>
        <li><strong>凭证抽查</strong>：关注增加凭证（溢价/股份支付/外币折算-贷方）和减少凭证（转增/弥补-借方）</li>
        <li><strong>检查覆盖率</strong> = 检查金额合计 ÷ 本期发生额（贷方增加+借方减少合计）</li>
        <li><strong>J3股份支付核对</strong>：确认差异 = J3确认金额 − 账面其他资本公积增加；差异>100元红色高亮</li>
        <li>M2外币出资折算差异应计入资本溢价区块</li>
        <li>检查结果支持：√一致 / ×差异 / ?存疑 三种标记</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M4TabReserveCheck — M4-4 资本公积检查表（核对清单+结论区+AI辅助）
 *
 * Spec: .kiro/specs/m4-capital-reserve/
 * Task: 4.4
 * Requirements: 5.1-5.2
 *
 * 功能：
 * - 凭证抽查核对表（动态行 el-table）
 * - 检查覆盖率 = 检查金额合计 / 本期发生额
 * - J3股份支付确认差异展示（差异红色高亮 if > threshold）
 * - 核对清单（radio-button 通过/不通过）
 * - 审计结论区（el-card, textarea + AI button）
 * - 每个文本section标题行右侧AI辅助按钮
 * - 复核按钮（inject openReviewDialog）
 * - 编制提示 details 折叠底部
 *
 * 科目：4002 资本公积（**贷方/权益类！**）
 * 检查关注：增加凭证（贷方：溢价/股份支付/外币折算）+ 减少凭证（借方：转增/弥补）
 */
import { computed, inject, onMounted, defineAsyncComponent } from 'vue'
import { Plus, MagicStick, Check } from '@element-plus/icons-vue'
import { useM4FormData } from '../../composables/useM4FormData'
import { useM4ReserveCheck } from '../../composables/useM4ReserveCheck'

const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<((sectionId: string, sectionLabel?: string) => void) | null>(
  'openReviewDialog',
  null,
)

// ─── FormData + Composables ──────────────────────────────────────────────────

const formData = useM4FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const check = useM4ReserveCheck(formData)

// ─── Init checklist items ────────────────────────────────────────────────────

function _initChecklist() {
  if (check.checklist.value.length === 0) {
    check.checklist.value = [
      { index: 1, item: '资本溢价增加是否有出资证明/验资报告/银行进账单支持', passed: null, note: '' },
      { index: 2, item: '资本溢价减少(转增)是否经股东会/董事会决议批准', passed: null, note: '' },
      { index: 3, item: '其他资本公积增加(股份支付)是否与J3确认金额一致', passed: null, note: '' },
      { index: 4, item: '其他资本公积增加(外币折算)是否与M2折算差额一致', passed: null, note: '' },
      { index: 5, item: '资本公积变动记账方向是否正确(增加=贷方, 减少=借方)', passed: null, note: '' },
      { index: 6, item: '期末余额与试算表(4002)是否一致', passed: null, note: '' },
      { index: 7, item: '资本公积明细分类(溢价/其他)是否准确', passed: null, note: '' },
      { index: 8, item: '本期资本公积变动是否在附注中正确披露', passed: null, note: '' },
    ]
  }
}

// ─── Computed: 覆盖率Tag类型 ────────────────────────────────────────────────

const coverageTagType = computed(() => {
  const ratio = check.checkRatio.value.ratio
  if (ratio === null) return 'info'
  if (ratio >= 0.8) return 'success'
  if (ratio >= 0.5) return 'warning'
  return 'danger'
})

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleAddVoucherRow() {
  check.addVoucherRow()
}

function handleAI(_section: string) {
  /* AI辅助待集成 */
}

function handleReview() {
  openReviewDialog?.('M4-4-reserve-check', '资本公积检查表')
}

// ─── Format helpers ──────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── Restore from responses ──────────────────────────────────────────────────

function _restoreData() {
  // 恢复凭证行
  const voucherData = formData.allResponses.value.get('M4-4-voucher-all')
  if (voucherData?.remark) {
    try {
      const parsed = JSON.parse(voucherData.remark)
      if (Array.isArray(parsed)) check.voucherRows.value = parsed
    } catch { /* ignore */ }
  }

  // 恢复清单
  const checklistData = formData.allResponses.value.get('M4-4-checklist-all')
  if (checklistData?.remark) {
    try {
      const parsed = JSON.parse(checklistData.remark)
      if (Array.isArray(parsed) && parsed.length > 0) check.checklist.value = parsed
    } catch { /* ignore */ }
  }

  // 恢复结论
  const conclusionData = formData.allResponses.value.get('M4-4-conclusion')
  if (conclusionData?.remark) check.conclusion.value = conclusionData.remark

  // 恢复本期发生额
  const periodData = formData.allResponses.value.get('M4-4-period-occurrence')
  if (periodData?.remark) {
    try {
      check.setPeriodOccurrence(Number(JSON.parse(periodData.remark)) || 0)
    } catch { /* ignore */ }
  }

  // 恢复J3联动值
  const j3Data = formData.allResponses.value.get('M4-4-j3-equity-settled')
  if (j3Data?.remark) {
    try {
      check.setJ3EquitySettled(Number(JSON.parse(j3Data.remark)) || 0)
    } catch { /* ignore */ }
  }

  // 恢复账面其他资本公积增加
  const bookedData = formData.allResponses.value.get('M4-4-booked-other-increase')
  if (bookedData?.remark) {
    try {
      check.setBookedOtherIncrease(Number(JSON.parse(bookedData.remark)) || 0)
    } catch { /* ignore */ }
  }
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  _restoreData()
  _initChecklist()
})
</script>

<style scoped>
.m4-tab-reserve-check {
  padding: 12px;
  font-size: 13px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}

.section-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.equity-badge {
  font-weight: 600;
}

.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 12px 16px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
}

.methodology-text {
  font-size: 13px;
  color: #6b5900;
  line-height: 1.6;
}

.check-card {
  margin-bottom: 16px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
  color: #303133;
}

.card-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.formula-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
}

.formula-value {
  color: #409eff;
  font-weight: 500;
}

:deep(.el-table) {
  font-size: 13px;
}

.ratio-bar {
  margin-top: 10px;
  padding: 10px 14px;
  background: #f0f9eb;
  border-radius: 4px;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

/* ─── J3 股份支付核对区域 ──── */
.share-based-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 16px;
  padding: 12px 0;
}

.share-based-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.share-based-label {
  font-size: 12px;
  color: #909399;
  font-weight: 500;
}

.share-based-value {
  display: flex;
  align-items: center;
}

.diff-value {
  font-size: 16px;
  font-weight: 700;
}

.diff-danger {
  color: #f56c6c;
}

.diff-ok {
  color: #67c23a;
}

/* ─── 核对清单 ──── */
.checklist-section {
  margin-bottom: 8px;
}

.checklist-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid #f2f6fc;
}

.checklist-index {
  font-weight: 600;
  color: #303133;
  min-width: 20px;
}

.checklist-text {
  flex: 1;
  color: #606266;
}

/* ─── 审计结论 ──── */
.conclusion-card :deep(.el-card__body) {
  padding-top: 12px;
}

/* ─── 编制提示 ──── */
.m4-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 13px;
  color: #606266;
}

.m4-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
}

.m4-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
