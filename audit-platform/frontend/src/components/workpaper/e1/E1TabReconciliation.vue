<script setup lang="ts">
/**
 * E1TabReconciliation.vue — E1-6 银行存款余额调节表
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.6
 *
 * 渲染：
 * - 每行 = 一个银行账户的调节
 * - 左侧：企业侧（账面余额 + 企收银未收 - 企付银未付 = 调节后企业余额）
 * - 右侧：银行侧（对账单余额 + 银收企未收 - 银付企未付 = 调节后银行余额）
 * - 底部：差异（红色 if ≠0）+ 差异原因textarea(required when diff≠0)
 * - 动态行增删
 * - el-skeleton加载占位
 *
 * Requirements: 6.1-6.5
 */
import { inject, toRef, onMounted, type Ref } from 'vue'
import {
  useE1Reconciliation,
  type ReconciliationRow,
} from '../composables/useE1Reconciliation'
import type { UseE1BaseOptions } from '../composables/useE1Adjudication'
import GtIndexChip from '../GtIndexChip.vue'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveImmediate: (items: any[]) => Promise<void>
  debouncedSave: (items: any[]) => Promise<void>
  isReadonly: boolean
  sheetName?: string
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

// ─── Composable ──────────────────────────────────────────────────────────────

const options: UseE1BaseOptions = {
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
}

const {
  rows,
  isLoading,
  hasDiff,
  isMissingReason,
  addRow,
  removeRow,
  updateCell,
} = useE1Reconciliation(options)
</script>

<template>
  <div class="e1-tab-reconciliation">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表对每个银行账户编制余额调节表，验证企业账面余额与银行对账单余额的一致性。</p>
        <p>2. 企业侧：账面余额 + 企收银未收 − 企付银未付 = 调节后企业余额；银行侧：对账单余额 + 银收企未收 − 银付企未付 = 调节后银行余额。</p>
        <p>3. 调节后双方余额应相等，差异≠0时红色高亮并须填写差异原因（必填），关注未达账项与舞弊迹象。</p>
        <p>4. 调节表数据应与 E1-3 银行存款明细及银行函证回函核对一致。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：通过银行存款余额调节表验证账面余额的准确与完整，识别未达账项及异常调节事项，评价截止认定的恰当性。"
      class="objective-alert"
    />

    <el-skeleton :loading="isLoading" :rows="8" animated>
      <template #default>
        <!-- 工具栏 -->
        <div class="tab-toolbar">
          <div class="toolbar-left">
            <el-button v-if="!isReadonly" type="primary" size="small" @click="addRow">
              + 新增银行账户
            </el-button>
          </div>
          <div class="toolbar-right">
            <span class="chip-wrap"><GtIndexChip value="wp:E1-3" :context-project-id="projectId" /></span>
            <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
          </div>
        </div>

        <!-- Reconciliation Cards -->
        <div class="recon-list">
          <div
            v-for="row in rows"
            :key="row.id"
            class="recon-card"
            :class="{ 'recon-card-error': hasDiff(row) }"
          >
            <!-- Card Header -->
            <div class="recon-header">
              <div class="recon-bank-info">
                <el-input
                  :model-value="row.bankName"
                  :disabled="isReadonly"
                  size="small"
                  placeholder="开户银行"
                  style="width: 200px"
                  @change="(val: string) => updateCell(row.id, 'bankName', val)"
                />
                <el-input
                  :model-value="row.accountNo"
                  :disabled="isReadonly"
                  size="small"
                  placeholder="银行账号"
                  style="width: 200px"
                  @change="(val: string) => updateCell(row.id, 'accountNo', val)"
                />
              </div>
              <el-button
                v-if="!isReadonly"
                type="danger"
                text
                size="small"
                @click="removeRow(row.id)"
              >
                删除
              </el-button>
            </div>

            <!-- Reconciliation Body: two columns -->
            <div class="recon-body">
              <!-- 企业侧 -->
              <div class="recon-side">
                <div class="side-title">企业侧</div>
                <div class="side-row">
                  <span class="side-label">企业账面余额</span>
                  <el-input-number
                    :model-value="row.bookBalance"
                    :disabled="isReadonly"
                    :controls="false"
                    size="small"
                    @change="(val: number | undefined) => updateCell(row.id, 'bookBalance', val ?? 0)"
                  />
                </div>
                <div class="side-row">
                  <span class="side-label">+ 企收银未收</span>
                  <el-input-number
                    :model-value="row.bankReceived"
                    :disabled="isReadonly"
                    :controls="false"
                    size="small"
                    @change="(val: number | undefined) => updateCell(row.id, 'bankReceived', val ?? 0)"
                  />
                </div>
                <div class="side-row">
                  <span class="side-label">- 企付银未付</span>
                  <el-input-number
                    :model-value="row.bankPaid"
                    :disabled="isReadonly"
                    :controls="false"
                    size="small"
                    @change="(val: number | undefined) => updateCell(row.id, 'bankPaid', val ?? 0)"
                  />
                </div>
                <div class="side-row side-result">
                  <span class="side-label">= 调节后企业余额</span>
                  <span class="side-computed">{{ displayPrefs.fmtAmount(row.reconciledBook) }}</span>
                </div>
              </div>

              <!-- 银行侧 -->
              <div class="recon-side">
                <div class="side-title">银行侧</div>
                <div class="side-row">
                  <span class="side-label">银行对账单余额</span>
                  <el-input-number
                    :model-value="row.statementBalance"
                    :disabled="isReadonly"
                    :controls="false"
                    size="small"
                    @change="(val: number | undefined) => updateCell(row.id, 'statementBalance', val ?? 0)"
                  />
                </div>
                <div class="side-row">
                  <span class="side-label">+ 银收企未收</span>
                  <el-input-number
                    :model-value="row.companyReceived"
                    :disabled="isReadonly"
                    :controls="false"
                    size="small"
                    @change="(val: number | undefined) => updateCell(row.id, 'companyReceived', val ?? 0)"
                  />
                </div>
                <div class="side-row">
                  <span class="side-label">- 银付企未付</span>
                  <el-input-number
                    :model-value="row.companyPaid"
                    :disabled="isReadonly"
                    :controls="false"
                    size="small"
                    @change="(val: number | undefined) => updateCell(row.id, 'companyPaid', val ?? 0)"
                  />
                </div>
                <div class="side-row side-result">
                  <span class="side-label">= 调节后银行余额</span>
                  <span class="side-computed">{{ displayPrefs.fmtAmount(row.reconciledStatement) }}</span>
                </div>
              </div>
            </div>

            <!-- Difference -->
            <div class="recon-diff" :class="{ 'diff-error': hasDiff(row) }">
              <span class="diff-label">差异：</span>
              <span class="diff-value">{{ displayPrefs.fmtAmount(row.diff) }}</span>
              <span v-if="!hasDiff(row)" class="diff-ok">✓ 一致</span>
              <span v-else class="diff-warn">⚠ 存在差异</span>
            </div>

            <!-- Difference Reason (required when diff ≠ 0) -->
            <div v-if="hasDiff(row)" class="recon-reason">
              <label class="reason-label">
                差异原因 <span class="required-mark">*</span>
              </label>
              <el-input
                type="textarea"
                :model-value="row.diffReason"
                :disabled="isReadonly"
                :autosize="{ minRows: 2, maxRows: 4 }"
                :class="{ 'missing-reason': isMissingReason(row) }"
                placeholder="请填写差异原因（必填）"
                @change="(val: string) => updateCell(row.id, 'diffReason', val)"
              />
              <span v-if="isMissingReason(row)" class="reason-hint">差异≠0时必须填写原因</span>
            </div>
          </div>
        </div>
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.e1-tab-reconciliation {
  padding: 12px 0;
}
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p {
  margin: 2px 0;
}
.objective-alert {
  margin-bottom: 12px;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.chip-wrap { display: inline-flex; align-items: center; }
.recon-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.recon-card {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 16px;
  background: #fff;
  transition: border-color 0.2s;
}
.recon-card-error {
  border-color: #f56c6c;
  background: #fef0f0;
}
.recon-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.recon-bank-info {
  display: flex;
  gap: 8px;
}
.recon-body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  margin-bottom: 12px;
}
.recon-side {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 12px;
  background: #fafafa;
}
.side-title {
  font-weight: 700;
  font-size: var(--wp-font-size, 13px);
  color: #303133;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid #ebeef5;
}
.side-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.side-label {
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  min-width: 130px;
}
.side-result {
  padding-top: 8px;
  border-top: 1px solid #dcdfe6;
  margin-top: 4px;
}
.side-computed {
  font-weight: 700;
  color: #303133;
  font-size: 14px;
}
.recon-diff {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #f0f9eb;
  border-radius: 4px;
}
.recon-diff.diff-error {
  background: #fef0f0;
}
.diff-label {
  font-weight: 600;
  color: #303133;
}
.diff-value {
  font-weight: 700;
  font-size: 14px;
}
.diff-ok {
  color: #67c23a;
  font-weight: 600;
}
.diff-warn {
  color: #f56c6c;
  font-weight: 600;
}
.recon-reason {
  margin-top: 12px;
}
.reason-label {
  font-weight: 600;
  font-size: var(--wp-font-size, 13px);
  color: #303133;
  display: block;
  margin-bottom: 4px;
}
.required-mark {
  color: #f56c6c;
}
.reason-hint {
  color: #f56c6c;
  font-size: 12px;
  margin-top: 4px;
  display: block;
}
:deep(.missing-reason .el-textarea__inner) {
  border-color: #f56c6c !important;
}
</style>
