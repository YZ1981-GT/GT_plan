<!--
  G4TabReversalWriteOff.vue — G4-12 减值准备转回（收回）、核销检查表（20列 → 2区段Tab）

  2区段Tab切换（el-segmented）：
  - Tab1: 转回（收回）检查(10列): 序号|单位名称|转回原因|收回方式|原确定坏账准备依据|收回或转回金额|收回前累计计提|合理性分析|是否合理|索引
  - Tab2: 核销检查(10列): 序号|单位名称|核销性质|核销金额|核销原因|核销程序|是否关联交易|合理性分析|是否合理|索引

  区段间行同步：切换Tab保持activeRowIndex
  Tab1: 转回金额 > 累计计提 → 红色高亮 + 校验错误
  Tab2: 关联交易 = true → 橙色底色高亮
  各Tab底部合计行（转回金额合计 / 核销金额合计）

  Spec: .kiro/specs/g4-bond-investment-ecl/ Task 8.2
  Requirements: 5.1~5.9, 11.2, 11.5, 11.8
-->
<template>
  <div class="g4-reversal-writeoff">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计目标：确认债权投资减值准备转回（收回）与核销的依据充分、程序合规，转回不超过累计计提，关注核销中的关联交易。"
      style="margin-bottom: 12px"
    />
    <!-- 顶部工具栏 -->
    <div class="section-head">
      <h3 class="sheet-title">G4-12 减值准备转回（收回）、核销检查表</h3>
      <div class="head-actions">
        <el-segmented v-model="rw.activeTab.value" :options="segmentOptions" size="small" />
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          + 新增行
        </el-button>
        <el-button size="small" @click="openReviewDialog('G4-12-reversal-writeoff')">💬复核</el-button>
      </div>
    </div>

    <!-- 单表格 + v-if列组切换（避免Tab切换闪烁） -->
    <el-table
      :data="activeDisplayRows"
      border
      size="small"
      max-height="520"
      highlight-current-row
      row-key="id"
      :row-class-name="activeRowClassName"
      class="reversal-table"
      @current-change="onCurrentChange"
    >
      <!-- 序号列（始终显示） -->
      <el-table-column label="序号" width="55" align="center" fixed>
        <template #default="{ row }">
          <template v-if="row._isTotal">
            <span class="total-label">合计</span>
          </template>
          <template v-else>{{ row.seq }}</template>
        </template>
      </el-table-column>

      <!-- 单位名称（始终显示作为锚定列） -->
      <el-table-column label="单位名称" min-width="120" fixed>
        <template #default="{ row }">
          <template v-if="row._isTotal" />
          <span v-else>{{ row.unitName }}</span>
        </template>
      </el-table-column>

      <!-- ═══ Tab1: 转回（收回）检查列 ═══ -->
      <template v-if="rw.activeTab.value === 'tab1'">
        <el-table-column label="转回原因" min-width="130">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input v-if="!isReadonly" v-model="row.reversalReason" size="small" />
              <span v-else>{{ row.reversalReason }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="收回方式" min-width="110">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input v-if="!isReadonly" v-model="row.recoveryMethod" size="small" />
              <span v-else>{{ row.recoveryMethod }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="原确定坏账准备依据" min-width="150">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input v-if="!isReadonly" v-model="row.originalBasis" size="small" type="textarea"
                :autosize="{ minRows: 1, maxRows: 3 }" />
              <span v-else>{{ row.originalBasis }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="收回或转回金额" min-width="130" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal">
              <span class="total-num">{{ fmtNum(rw.reversalSummary.value.totalReversalAmount) }}</span>
            </template>
            <template v-else>
              <el-input-number v-if="!isReadonly" v-model="row.reversalAmount" size="small"
                :controls="false" class="compact-num" />
              <span v-else>{{ fmtNum(row.reversalAmount) }}</span>
              <!-- 校验错误提示 -->
              <div v-if="rw.getReversalError(row)" class="validation-error">
                {{ rw.getReversalError(row) }}
              </div>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="收回前累计计提" min-width="130" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal">
              <span class="total-num">{{ fmtNum(rw.reversalSummary.value.totalAccumulatedProvision) }}</span>
            </template>
            <template v-else>
              <el-input-number v-if="!isReadonly" v-model="row.accumulatedProvision" size="small"
                :controls="false" class="compact-num" />
              <span v-else>{{ fmtNum(row.accumulatedProvision) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="合理性分析" min-width="160">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input v-if="!isReadonly" v-model="row.reasonAnalysis" size="small" type="textarea"
                :autosize="{ minRows: 1, maxRows: 3 }" />
              <span v-else>{{ row.reasonAnalysis }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="是否合理" width="100" align="center">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-select v-if="!isReadonly" v-model="row.isReasonable" size="small" style="width: 80px">
                <el-option label="合理" value="合理" />
                <el-option label="不合理" value="不合理" />
              </el-select>
              <span v-else>{{ row.isReasonable }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="索引" width="100">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <GtIndexChip v-if="row.indexRef" :value="row.indexRef" />
              <el-input v-else-if="!isReadonly" v-model="row.indexRef" size="small" placeholder="索引" />
            </template>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ Tab2: 核销检查列 ═══ -->
      <template v-if="rw.activeTab.value === 'tab2'">
        <el-table-column label="核销性质" width="100" align="center">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-select v-if="!isReadonly" v-model="row.writeOffType" size="small" style="width: 80px">
                <el-option label="到期" value="到期" />
                <el-option label="逾期" value="逾期" />
                <el-option label="其他" value="其他" />
              </el-select>
              <span v-else>{{ row.writeOffType }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="核销金额" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal">
              <span class="total-num">{{ fmtNum(rw.writeOffSummary.value.totalWriteOffAmount) }}</span>
            </template>
            <template v-else>
              <el-input-number v-if="!isReadonly" v-model="row.writeOffAmount" size="small"
                :controls="false" class="compact-num" />
              <span v-else>{{ fmtNum(row.writeOffAmount) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="核销原因" min-width="140">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input v-if="!isReadonly" v-model="row.writeOffReason" size="small" type="textarea"
                :autosize="{ minRows: 1, maxRows: 3 }" />
              <span v-else>{{ row.writeOffReason }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="核销程序" min-width="140">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input v-if="!isReadonly" v-model="row.writeOffProcedure" size="small" type="textarea"
                :autosize="{ minRows: 1, maxRows: 3 }" />
              <span v-else>{{ row.writeOffProcedure }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="是否关联交易" width="110" align="center">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-switch v-if="!isReadonly" v-model="row.isRelatedParty" size="small"
                active-text="是" inactive-text="否" />
              <el-tag v-else :type="row.isRelatedParty ? 'warning' : 'info'" size="small">
                {{ row.isRelatedParty ? '是' : '否' }}
              </el-tag>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="合理性分析" min-width="160">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input v-if="!isReadonly" v-model="row.reasonAnalysis" size="small" type="textarea"
                :autosize="{ minRows: 1, maxRows: 3 }" />
              <span v-else>{{ row.reasonAnalysis }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="是否合理" width="100" align="center">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-select v-if="!isReadonly" v-model="row.isReasonable" size="small" style="width: 80px">
                <el-option label="合理" value="合理" />
                <el-option label="不合理" value="不合理" />
              </el-select>
              <span v-else>{{ row.isReasonable }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="索引" width="100">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <GtIndexChip v-if="row.indexRef" :value="row.indexRef" />
              <el-input v-else-if="!isReadonly" v-model="row.indexRef" size="small" placeholder="索引" />
            </template>
          </template>
        </el-table-column>
      </template>

      <!-- 操作列（删除） -->
      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-popconfirm v-if="!row._isTotal" title="确认删除？"
            @confirm="handleDeleteRow(row.id)">
            <template #reference>
              <el-icon class="delete-icon"><Delete /></el-icon>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部审计结论 -->
    <el-card class="conclusion-card" shadow="never">
      <div class="conclusion-header">
        <span class="conclusion-title">审计结论</span>
        <el-button size="small" type="primary" link :disabled="isReadonly" @click="handleAiConclusion">
          🤖 AI生成
        </el-button>
      </div>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请输入转回核销检查的审计结论..."
        :disabled="isReadonly"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>转回金额不得超过收回前累计计提金额（超出将红色高亮提示）</li>
        <li>核销需关注是否为关联交易（关联交易行将橙色高亮提示）</li>
        <li>核销性质：到期核销 / 逾期核销 / 其他原因核销</li>
        <li>核销程序应记录审批流程及相关文件</li>
        <li>转回原因应说明原减值事由是否已消除</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G4TabReversalWriteOff.vue — G4-12 减值准备转回核销检查表（2区段Tab）
 *
 * - el-segmented 切换 Tab1(转回检查) / Tab2(核销检查)
 * - Tab1: 转回金额 > 累计计提 → 红色高亮 + 校验错误信息
 * - Tab2: 关联交易行橙色底色高亮
 * - 各Tab底部合计行
 * - Tab切换行同步（activeRowIndex）
 * - 动态行增删（ElMessageBox.prompt输入单位名称）
 * - GtIndexChip索引列跳转
 */
import { ref, computed, inject, onMounted } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useG4EclReversalWriteOff } from '../../composables/useG4EclReversalWriteOff'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const rw = useG4EclReversalWriteOff()
const conclusion = ref('')

// ─── 区段Tab选项 ─────────────────────────────────────────────────────────────

const segmentOptions = [
  { label: '转回（收回）检查', value: 'tab1' },
  { label: '核销检查', value: 'tab2' },
]

// ─── 统一显示行（单表格方案 — 避免Tab切换闪烁） ─────────────────────────────

interface DisplayRow {
  id: string
  seq: number
  unitName: string
  _isTotal?: boolean
  // Tab1 转回字段
  reversalReason?: string
  recoveryMethod?: string
  originalBasis?: string
  reversalAmount?: number
  accumulatedProvision?: number
  // Tab2 核销字段
  writeOffType?: string
  writeOffAmount?: number
  writeOffReason?: string
  writeOffProcedure?: string
  isRelatedParty?: boolean
  // 共用字段
  reasonAnalysis?: string
  isReasonable?: string
  indexRef?: string
}

const activeDisplayRows = computed<DisplayRow[]>(() => {
  if (rw.activeTab.value === 'tab1') {
    const result: DisplayRow[] = [...rw.reversals.value as DisplayRow[]]
    result.push({
      id: '__total__',
      seq: 0,
      unitName: '',
      reversalAmount: rw.reversalSummary.value.totalReversalAmount,
      accumulatedProvision: rw.reversalSummary.value.totalAccumulatedProvision,
      _isTotal: true,
    })
    return result
  } else {
    const result: DisplayRow[] = [...rw.writeOffs.value as DisplayRow[]]
    result.push({
      id: '__total__',
      seq: 0,
      unitName: '',
      writeOffAmount: rw.writeOffSummary.value.totalWriteOffAmount,
      _isTotal: true,
    })
    return result
  }
})

// ─── 行同步（activeRowIndex 跨Tab保持） ─────────────────────────────────────

function onCurrentChange(row: DisplayRow | null) {
  if (!row || row._isTotal) return
  if (rw.activeTab.value === 'tab1') {
    const idx = rw.reversals.value.findIndex(r => r.id === row.id)
    if (idx >= 0) rw.activeRowIndex.value = idx
  } else {
    const idx = rw.writeOffs.value.findIndex(r => r.id === row.id)
    if (idx >= 0) rw.activeRowIndex.value = idx
  }
}

// ─── 行样式（Tab1转回校验红色 / Tab2关联交易橙色） ──────────────────────────

function activeRowClassName({ row }: { row: DisplayRow }): string {
  if (row._isTotal) return 'row-total'
  if (rw.activeTab.value === 'tab1') {
    if (!rw.isRowValid(row as any)) return 'row-invalid'
  } else {
    if (rw.isRelatedPartyRow(row as any)) return 'row-related-party'
  }
  return ''
}

// ─── 统一删除行处理 ─────────────────────────────────────────────────────────

function handleDeleteRow(rowId: string): void {
  if (rw.activeTab.value === 'tab1') {
    rw.removeReversalRow(rowId)
  } else {
    rw.removeWriteOffRow(rowId)
  }
}

// ─── 动态行增删 ─────────────────────────────────────────────────────────────

async function handleAddRow() {
  if (rw.activeTab.value === 'tab1') {
    await rw.addReversalRow()
  } else {
    await rw.addWriteOffRow()
  }
}

// ─── AI生成审计结论 ─────────────────────────────────────────────────────────

function handleAiConclusion() {
  ElMessage.info('AI生成审计结论功能将在AI模块完成后启用')
}

// ─── 数字格式化 ─────────────────────────────────────────────────────────────

function fmtNum(v: unknown): string {
  if (v === 0) return '0.00'
  if (typeof v === 'number') {
    return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(v ?? '')
}

// ─── 数据加载 ───────────────────────────────────────────────────────────────

onMounted(() => {
  if (props.htmlData?.reversalWriteOff) {
    const data = props.htmlData.reversalWriteOff
    rw.loadData({
      reversals: data.reversals,
      writeOffs: data.writeOffs,
    })
    if (data.conclusion) conclusion.value = data.conclusion
  }
})

// ─── 暴露序列化接口供父组件保存使用 ─────────────────────────────────────────

defineExpose({
  toJSON: () => ({
    ...rw.toJSON(),
    conclusion: conclusion.value,
  }),
})
</script>

<style scoped>
.g4-reversal-writeoff {
  padding: 12px;
  font-size: 13px;
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.sheet-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 表格 */
.reversal-table {
  font-size: 13px;
}

.compact-num {
  width: 100%;
}

.compact-num :deep(.el-input__inner) {
  text-align: right;
}

/* 转回校验错误：红色高亮行 */
:deep(.row-invalid) {
  background-color: #fef0f0 !important;
}
:deep(.row-invalid td) {
  background-color: #fef0f0 !important;
}

.validation-error {
  color: #f56c6c;
  font-size: 11px;
  margin-top: 2px;
  line-height: 1.2;
}

/* 关联交易行：橙色高亮 */
:deep(.row-related-party) {
  background-color: #fdf6ec !important;
}
:deep(.row-related-party td) {
  background-color: #fdf6ec !important;
}

/* 合计行 */
:deep(.row-total) {
  background-color: #ecf5ff !important;
  font-weight: 700;
}
:deep(.row-total td) {
  background-color: #ecf5ff !important;
}

.total-label {
  color: #409eff;
  font-weight: 700;
}

.total-num {
  font-weight: 700;
  color: #303133;
}

/* 删除图标 */
.delete-icon {
  cursor: pointer;
  color: #909399;
  transition: color 0.2s;
}
.delete-icon:hover {
  color: #f56c6c;
}

/* 审计结论卡片 */
.conclusion-card {
  margin-top: 16px;
}

.conclusion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.conclusion-title {
  font-weight: 600;
  font-size: 14px;
}

/* 编制提示 */
.prep-hint {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
}
.prep-hint summary {
  cursor: pointer;
  font-weight: 500;
}
.prep-hint ul {
  margin: 8px 0 0;
  padding-left: 18px;
}
.prep-hint li {
  margin-bottom: 4px;
}
</style>
