<script setup lang="ts">
/**
 * E1TabAdjustment.vue — E1-5 调整分录汇总
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.5
 *
 * 渲染：
 * - el-table 动态行：调整事项 | 类别(el-select) | 报表项目 | 科目名称 |
 *   附注项目 | 借方 | 贷方 | 索引 | 备注
 * - 底部：借方合计 / 贷方合计 / 平衡状态(✓绿/✗红+差额)
 * - 动态行增删
 * - "推送至A2"按钮
 * - el-skeleton加载占位
 *
 * Requirements: 5.1-5.5
 */
import { inject, toRef, onMounted, type Ref } from 'vue'
import {
  useE1Adjustment,
  type AdjustmentRow,
  type AdjustmentCategory,
} from '../composables/useE1Adjustment'
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
  totalDebit,
  totalCredit,
  balanceDiff,
  balanced,
  isLoading,
  addRow,
  removeRow,
  updateCell,
  pushToA2,
} = useE1Adjustment(options)

// ─── Constants ───────────────────────────────────────────────────────────────

const categoryOptions: AdjustmentCategory[] = ['报表调整', '账项调整', '其他']
</script>

<template>
  <div class="e1-tab-adjustment">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表汇总货币资金相关的调整分录（账项调整AJE/报表调整RJE）。</p>
        <p>2. 借方合计必须等于贷方合计，平衡时显示"✓ 平衡"，不平衡时显示差额并须查明原因。</p>
        <p>3. 类别选择"账项调整"影响科目余额并回写审定数；"报表调整"仅影响报表列报。</p>
        <p>4. 确认后可点击"推送至A2"将调整分录汇总至未审计报表调整底稿。</p>
      </div>
    </details>

    <el-skeleton :loading="isLoading" :rows="8" animated>
      <template #default>
        <!-- 工具栏 -->
        <div class="tab-toolbar">
          <div class="toolbar-left">
            <el-button v-if="!isReadonly" type="primary" size="small" @click="addRow">
              + 新增行
            </el-button>
            <el-button v-if="!isReadonly" type="warning" size="small" @click="pushToA2">
              推送至A2
            </el-button>
          </div>
          <div class="toolbar-right">
            <span class="chip-wrap"><GtIndexChip value="wp:A2" :context-project-id="projectId" /></span>
            <span class="chip-wrap"><GtIndexChip value="wp:E1-1" :context-project-id="projectId" /></span>
            <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
          </div>
        </div>

        <el-table :data="rows" border stripe size="small" style="width: 100%" max-height="500">
          <!-- 调整事项 -->
          <el-table-column label="调整事项" min-width="160">
            <template #default="{ row }">
              <el-input
                :model-value="row.description"
                :disabled="isReadonly"
                size="small"
                placeholder="调整事项说明"
                @change="(val: string) => updateCell(row.id, 'description', val)"
              />
            </template>
          </el-table-column>

          <!-- 类别 -->
          <el-table-column label="类别" width="120">
            <template #default="{ row }">
              <el-select
                :model-value="row.category"
                :disabled="isReadonly"
                size="small"
                @change="(val: string) => updateCell(row.id, 'category', val)"
              >
                <el-option
                  v-for="cat in categoryOptions"
                  :key="cat"
                  :label="cat"
                  :value="cat"
                />
              </el-select>
            </template>
          </el-table-column>

          <!-- 报表项目 -->
          <el-table-column label="报表项目" width="130">
            <template #default="{ row }">
              <el-input
                :model-value="row.reportItem"
                :disabled="isReadonly"
                size="small"
                @change="(val: string) => updateCell(row.id, 'reportItem', val)"
              />
            </template>
          </el-table-column>

          <!-- 科目名称 -->
          <el-table-column label="科目名称" width="130">
            <template #default="{ row }">
              <el-input
                :model-value="row.accountName"
                :disabled="isReadonly"
                size="small"
                @change="(val: string) => updateCell(row.id, 'accountName', val)"
              />
            </template>
          </el-table-column>

          <!-- 附注项目 -->
          <el-table-column label="附注项目" width="120">
            <template #default="{ row }">
              <el-input
                :model-value="row.noteItem"
                :disabled="isReadonly"
                size="small"
                @change="(val: string) => updateCell(row.id, 'noteItem', val)"
              />
            </template>
          </el-table-column>

          <!-- 借方 -->
          <el-table-column label="借方" width="120" align="right">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.debit"
                :disabled="isReadonly"
                :controls="false"
                size="small"
                @change="(val: number | undefined) => updateCell(row.id, 'debit', val ?? 0)"
              />
            </template>
          </el-table-column>

          <!-- 贷方 -->
          <el-table-column label="贷方" width="120" align="right">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.credit"
                :disabled="isReadonly"
                :controls="false"
                size="small"
                @change="(val: number | undefined) => updateCell(row.id, 'credit', val ?? 0)"
              />
            </template>
          </el-table-column>

          <!-- 索引 -->
          <el-table-column label="索引" width="100">
            <template #default="{ row }">
              <el-input
                :model-value="row.indexNo"
                :disabled="isReadonly"
                size="small"
                @change="(val: string) => updateCell(row.id, 'indexNo', val)"
              />
            </template>
          </el-table-column>

          <!-- 备注 -->
          <el-table-column label="备注" min-width="120">
            <template #default="{ row }">
              <el-input
                :model-value="row.note"
                :disabled="isReadonly"
                size="small"
                @change="(val: string) => updateCell(row.id, 'note', val)"
              />
            </template>
          </el-table-column>

          <!-- 操作 -->
          <el-table-column v-if="!isReadonly" label="操作" width="70" fixed="right" align="center">
            <template #default="{ row }">
              <el-button type="danger" text size="small" @click="removeRow(row.id)">
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- Balance Summary -->
        <div class="balance-summary">
          <div class="balance-item">
            <span class="balance-label">借方合计：</span>
            <span class="balance-val">{{ displayPrefs.fmtAmount(totalDebit) }}</span>
          </div>
          <div class="balance-item">
            <span class="balance-label">贷方合计：</span>
            <span class="balance-val">{{ displayPrefs.fmtAmount(totalCredit) }}</span>
          </div>
          <div class="balance-item">
            <span class="balance-label">平衡状态：</span>
            <span v-if="balanced" class="balance-ok">✓ 平衡</span>
            <span v-else class="balance-err">
              ✗ 不平衡（差额：{{ displayPrefs.fmtAmount(balanceDiff) }}）
            </span>
          </div>
        </div>
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.e1-tab-adjustment {
  padding: 12px 0;
}
.e1-tab-adjustment :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.e1-tab-adjustment :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
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
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
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
.balance-summary {
  display: flex;
  gap: 24px;
  padding: 12px;
  margin-top: 12px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  align-items: center;
  flex-wrap: wrap;
}
.balance-item {
  display: flex;
  align-items: center;
  gap: 4px;
}
.balance-label {
  font-weight: 600;
  color: #303133;
  font-size: var(--wp-font-size, 13px);
}
.balance-val {
  font-weight: 600;
  color: #606266;
  font-size: var(--wp-font-size, 13px);
}
.balance-ok {
  color: #67c23a;
  font-weight: 700;
  font-size: 14px;
}
.balance-err {
  color: #f56c6c;
  font-weight: 700;
  font-size: 14px;
}
</style>
