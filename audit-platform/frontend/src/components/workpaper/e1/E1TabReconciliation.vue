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

const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) =>
    v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

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
    <el-skeleton :loading="isLoading" :rows="8" animated>
      <template #default>
        <!-- Toolbar -->
        <div class="toolbar" v-if="!isReadonly">
          <el-button type="primary" size="small" @click="addRow">
            + 新增银行账户
          </el-button>
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
.toolbar {
  margin-bottom: 12px;
}
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
  font-size: 13px;
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
  font-size: 13px;
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
  font-size: 13px;
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
