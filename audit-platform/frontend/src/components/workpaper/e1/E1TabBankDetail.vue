<script setup lang="ts">
/**
 * E1TabBankDetail.vue — E1-3 银行存款及其他货币资金明细表 (双variant)
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.3
 *
 * 渲染：
 * - 顶部 el-segmented variant切换("仅人民币" / "人民币及外币")
 * - 三分组(存款本金/存放财务公司/其他货币资金) + group header + subtotal
 * - 每组内动态行增删
 * - 函证差异橙色高亮(hasConfirmDiff)
 * - GtIndexChip跳E0 询证函索引号
 * - el-skeleton加载占位
 *
 * Requirements: 2.1-2.6, 4.1-4.7
 */
import { ref, inject, toRef, computed, onMounted, type Ref } from 'vue'
import {
  useE1BankDetail,
  type BankDetailRow,
  type BankDetailVariant,
  type BankDetailGroup,
} from '../composables/useE1BankDetail'
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

// ─── Variant ─────────────────────────────────────────────────────────────────

const variant = ref<BankDetailVariant>('rmb')
const variantOptions = [
  { label: '仅人民币', value: 'rmb' },
  { label: '人民币及外币', value: 'multi' },
]

// Detect initial variant from sheetName
if (props.sheetName?.includes('人民币及外币')) {
  variant.value = 'multi'
}

// ─── Composable ──────────────────────────────────────────────────────────────

const options = {
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
  variant,
}

const {
  groupedRows,
  groupTotals,
  isLoading,
  addRow,
  removeRow,
  updateCell,
  hasConfirmDiff,
  GROUP_NAMES,
} = useE1BankDetail(options)

// ─── Groups ──────────────────────────────────────────────────────────────────

const groups: BankDetailGroup[] = ['principal', 'finance', 'other']

const totalRowCount = computed(() =>
  groups.reduce((sum, g) => sum + ((groupedRows.value?.[g]?.length) ?? 0), 0),
)

function getRowClass({ row }: { row: BankDetailRow }): string {
  if (hasConfirmDiff(row)) return 'e1-bank-confirm-diff'
  return ''
}

// ─── 审计说明 / 审计结论 ─────────────────────────────────────────────────────
// 对照源模板 E1-3「五、审计说明」「六、审计结论」。本组件 composable 无 AI 生成
// 能力，故使用纯 textarea（不臆造 AI 按钮）。

const NOTE_KEY = 'E1-bank-audit-note'
const CONCLUSION_KEY = 'E1-bank-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

onMounted(() => {
  const noteResp = props.allResponses.get(NOTE_KEY)
  if (noteResp?.remark) auditNote.value = noteResp.remark
  const concResp = props.allResponses.get(CONCLUSION_KEY)
  if (concResp?.remark) auditConclusion.value = concResp.remark
})

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  const item = { item_id: NOTE_KEY, conclusion: null, remark: val }
  props.allResponses.set(NOTE_KEY, item)
  void props.saveImmediate([item])
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  const item = { item_id: CONCLUSION_KEY, conclusion: null, remark: val }
  props.allResponses.set(CONCLUSION_KEY, item)
  void props.saveImmediate([item])
}
</script>

<template>
  <div class="e1-tab-bank-detail">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表列示银行存款（科目1002）及其他货币资金（科目1012）明细，按存款本金、存放财务公司款项、其他货币资金三组归集。</p>
        <p>2. 灰色底纹列（期末余额/审定数/函证差异）为自动计算：期末余额=期初+增加-减少，函证差异=审定数-回函确认金额。</p>
        <p>3. 银行存款应实施函证程序，回函确认金额与审定数不一致时橙色高亮，须查明差异原因并在备注中说明。</p>
        <p>4. 询证函索引号点击可跳转 E0 函证底稿；外币账户须填列币种及资产负债表日汇率。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实银行存款及其他货币资金期末余额的存在、完整与准确，通过函证获取外部证据，评价受限资金披露的恰当性。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-segmented v-model="variant" :options="variantOptions" size="small" />
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:E1-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:E0" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ totalRowCount }} 行</el-tag>
      </div>
    </div>

    <el-skeleton :loading="isLoading" :rows="10" animated>
      <template #default>
        <div v-for="group in groups" :key="group" class="group-section">
          <!-- Group Header -->
          <div class="group-header">
            <span class="group-title">{{ GROUP_NAMES[group] }}</span>
            <el-button
              v-if="!isReadonly"
              type="primary"
              size="small"
              @click="addRow(group)"
            >
              + 新增行
            </el-button>
          </div>

          <!-- Group Table -->
          <el-table
            :data="groupedRows[group]"
            border
            size="small"
            :row-class-name="getRowClass"
            style="width: 100%"
          >
            <!-- 开户银行 -->
            <el-table-column label="开户银行" width="140">
              <template #default="{ row }">
                <el-input
                  :model-value="row.bankName"
                  :disabled="isReadonly"
                  size="small"
                  @change="(val: string) => updateCell(row.id, 'bankName', val)"
                />
              </template>
            </el-table-column>

            <!-- 银行账号 -->
            <el-table-column label="银行账号" width="160">
              <template #default="{ row }">
                <el-input
                  :model-value="row.accountNo"
                  :disabled="isReadonly"
                  size="small"
                  @change="(val: string) => updateCell(row.id, 'accountNo', val)"
                />
              </template>
            </el-table-column>

            <!-- 账户性质 -->
            <el-table-column label="账户性质" width="120">
              <template #default="{ row }">
                <el-input
                  :model-value="row.accountType"
                  :disabled="isReadonly"
                  size="small"
                  @change="(val: string) => updateCell(row.id, 'accountType', val)"
                />
              </template>
            </el-table-column>

            <!-- 外币列 (multi variant only) -->
            <template v-if="variant === 'multi'">
              <el-table-column label="币种" width="80">
                <template #default="{ row }">
                  <el-input
                    :model-value="row.fxCurrency"
                    :disabled="isReadonly"
                    size="small"
                    @change="(val: string) => updateCell(row.id, 'fxCurrency', val)"
                  />
                </template>
              </el-table-column>
              <el-table-column label="汇率" width="80" align="right">
                <template #default="{ row }">
                  <el-input-number
                    :model-value="row.fxRate"
                    :disabled="isReadonly"
                    :controls="false"
                    :precision="4"
                    size="small"
                    @change="(val: number | undefined) => updateCell(row.id, 'fxRate', val ?? 1)"
                  />
                </template>
              </el-table-column>
            </template>

            <!-- 期初余额 -->
            <el-table-column label="期初余额" width="120" align="right">
              <template #default="{ row }">
                <el-input-number
                  :model-value="row.opening"
                  :disabled="isReadonly"
                  :controls="false"
                  size="small"
                  @change="(val: number | undefined) => updateCell(row.id, 'opening', val ?? 0)"
                />
              </template>
            </el-table-column>

            <!-- 本期增加 -->
            <el-table-column label="本期增加" width="120" align="right">
              <template #default="{ row }">
                <el-input-number
                  :model-value="row.increase"
                  :disabled="isReadonly"
                  :controls="false"
                  size="small"
                  @change="(val: number | undefined) => updateCell(row.id, 'increase', val ?? 0)"
                />
              </template>
            </el-table-column>

            <!-- 本期减少 -->
            <el-table-column label="本期减少" width="120" align="right">
              <template #default="{ row }">
                <el-input-number
                  :model-value="row.decrease"
                  :disabled="isReadonly"
                  :controls="false"
                  size="small"
                  @change="(val: number | undefined) => updateCell(row.id, 'decrease', val ?? 0)"
                />
              </template>
            </el-table-column>

            <!-- 期末余额 (readonly) -->
            <el-table-column label="期末余额" width="120" align="right" class-name="auto-calc-col">
              <template #default="{ row }">
                <span class="readonly-val">{{ displayPrefs.fmtAmount(row.ending) }}</span>
              </template>
            </el-table-column>

            <!-- 账项调整 -->
            <el-table-column label="账项调整" width="120" align="right">
              <template #default="{ row }">
                <el-input-number
                  :model-value="row.adjustment"
                  :disabled="isReadonly"
                  :controls="false"
                  size="small"
                  @change="(val: number | undefined) => updateCell(row.id, 'adjustment', val ?? 0)"
                />
              </template>
            </el-table-column>

            <!-- 审定数 (readonly) -->
            <el-table-column label="审定数" width="120" align="right" class-name="auto-calc-col">
              <template #default="{ row }">
                <span class="readonly-val">{{ displayPrefs.fmtAmount(row.audited) }}</span>
              </template>
            </el-table-column>

            <!-- 回函确认金额 -->
            <el-table-column label="回函确认金额" width="130" align="right">
              <template #default="{ row }">
                <el-input-number
                  :model-value="row.confirmAmount"
                  :disabled="isReadonly"
                  :controls="false"
                  size="small"
                  @change="(val: number | undefined) => updateCell(row.id, 'confirmAmount', val ?? 0)"
                />
              </template>
            </el-table-column>

            <!-- 函证差异 (readonly) -->
            <el-table-column label="函证差异" width="110" align="right" class-name="auto-calc-col">
              <template #default="{ row }">
                <span :class="{ 'orange-text': hasConfirmDiff(row) }">
                  {{ displayPrefs.fmtAmount(row.confirmDiff) }}
                </span>
              </template>
            </el-table-column>

            <!-- 银行对账单余额 (源模板E1-3列) -->
            <el-table-column label="银行对账单余额" width="130" align="right">
              <template #default="{ row }">
                <el-input-number
                  :model-value="row.statementBalance"
                  :disabled="isReadonly"
                  :controls="false"
                  size="small"
                  @change="(val: number | undefined) => updateCell(row.id, 'statementBalance', val ?? 0)"
                />
              </template>
            </el-table-column>

            <!-- 是否受限 (源模板E1-3列：受限金额+受限原因) -->
            <el-table-column label="是否受限/受限说明" width="150">
              <template #default="{ row }">
                <el-input
                  :model-value="row.restrictedReason"
                  :disabled="isReadonly"
                  size="small"
                  placeholder="无受限则留空"
                  @change="(val: string) => updateCell(row.id, 'restrictedReason', val)"
                />
              </template>
            </el-table-column>

            <!-- 询证函索引号 -->
            <el-table-column label="询证函索引号" width="130">
              <template #default="{ row }">
                <GtIndexChip
                  v-if="row.confirmIndexNo"
                  value="wp:E0"
                  :context-project-id="projectId"
                  :context="`询证函索引号：${row.confirmIndexNo}`"
                />
                <el-input
                  v-else
                  :model-value="row.confirmIndexNo"
                  :disabled="isReadonly"
                  size="small"
                  placeholder="索引号"
                  @change="(val: string) => updateCell(row.id, 'confirmIndexNo', val)"
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

          <!-- Group Subtotal -->
          <div class="group-subtotal">
            <span>小计：</span>
            <span>期初 {{ displayPrefs.fmtAmount(groupTotals[group].opening) }}</span>
            <span>期末 {{ displayPrefs.fmtAmount(groupTotals[group].ending) }}</span>
            <span>审定 {{ displayPrefs.fmtAmount(groupTotals[group].audited) }}</span>
          </div>
        </div>

        <!-- 审计说明 -->
        <el-card shadow="never" class="audit-note-card">
          <template #header>
            <div class="card-header">
              <span>审计说明</span>
            </div>
          </template>
          <el-input
            type="textarea"
            :model-value="auditNote"
            :disabled="isReadonly"
            :autosize="{ minRows: 5 }"
            placeholder="填写审计说明：概述程序测试情况及结果、拟调整/未调整事项及其影响、审计范围受限情况及其影响..."
            @change="(val: string) => saveAuditNote(val)"
          />
        </el-card>

        <!-- 审计结论 -->
        <el-card shadow="never" class="audit-note-card">
          <template #header>
            <div class="card-header">
              <span>审计结论</span>
            </div>
          </template>
          <el-input
            type="textarea"
            :model-value="auditConclusion"
            :disabled="isReadonly"
            :autosize="{ minRows: 3 }"
            placeholder="填写审计结论：A.未见异常；B.除上述重大不符事项调整外，其余未见异常；C.存在重大未调整事项或审计范围受限，不可确认..."
            @change="(val: string) => saveAuditConclusion(val)"
          />
        </el-card>
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.e1-tab-bank-detail {
  padding: 12px 0;
}
.e1-tab-bank-detail :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.e1-tab-bank-detail :deep(.el-table .cell) {
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
.objective-alert {
  margin-bottom: 12px;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
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
:deep(.auto-calc-col) {
  background-color: #f5f7fa !important;
}
.group-section {
  margin-bottom: 20px;
}
.group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: #ecf5ff;
  border-radius: 4px;
  margin-bottom: 8px;
}
.group-title {
  font-weight: 700;
  color: #303133;
}
.group-subtotal {
  display: flex;
  gap: 16px;
  padding: 8px 12px;
  margin-top: 4px;
  background: #f5f7fa;
  border-radius: 4px;
  font-weight: 600;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}
.readonly-val {
  color: #909399;
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 2px;
}
.orange-text {
  color: #e6a23c;
  font-weight: 600;
}
.audit-note-card {
  margin-top: 16px;
}
.audit-note-card .card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
}

:deep(.e1-bank-confirm-diff) {
  background-color: #fdf6ec !important;
}
</style>
