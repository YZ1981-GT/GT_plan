<template>
  <div class="g7-tab-accounting-policy">
    <!-- Section 标题栏 -->
    <div class="section-head">
      <h3 class="sheet-title">G7-6 被投资公司会计政策一致性检查</h3>
      <div class="head-actions">
        <el-button size="small" @click="openReviewDialog('G7-6-accounting-policy')">💬复核</el-button>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实被投资单位会计政策与投资方是否一致，验证不一致事项的调整是否恰当，为权益法测算提供口径一致的基础数据。"
      class="objective-alert"
    />

    <!-- 方法论上下文（琥珀色左边线+浅黄背景） -->
    <div class="methodology-context">
      <p>CAS 会计政策一致性要求：</p>
      <p>• 投资方应以被投资方的会计政策与投资方一致为前提，对被投资方的财务报表进行调整</p>
      <p>• 被投资方采用的会计政策与投资方不一致的，应按投资方会计政策对被投资方财务报表进行调整</p>
      <p>• 调整后的金额需在 G7-14 权益法测算表"会计政策调整"列反映</p>
    </div>

    <!-- 工具栏：索引 chip + 行数 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G7-6" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <!-- 31行×7列问卷表格 -->
    <el-table
      :data="rows"
      border
      size="small"
      class="policy-table"
    >
      <!-- 序号 -->
      <el-table-column type="index" label="#" width="45" align="center" />

      <!-- 会计政策事项 -->
      <el-table-column label="会计政策事项" min-width="160" prop="policyItem">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            v-model="row.policyItem"
            size="small"
            placeholder="会计政策事项"
            @change="emitSave()"
          />
          <span v-else>{{ row.policyItem }}</span>
        </template>
      </el-table-column>

      <!-- 被投资方政策 -->
      <el-table-column label="被投资方政策" min-width="150">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            v-model="row.investeePolicy"
            size="small"
            placeholder="被投资方采用的政策"
            @change="emitSave()"
          />
          <span v-else>{{ row.investeePolicy }}</span>
        </template>
      </el-table-column>

      <!-- 投资方政策 -->
      <el-table-column label="投资方政策" min-width="150">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            v-model="row.investorPolicy"
            size="small"
            placeholder="投资方采用的政策"
            @change="emitSave()"
          />
          <span v-else>{{ row.investorPolicy }}</span>
        </template>
      </el-table-column>

      <!-- 是否一致（下拉） -->
      <el-table-column label="是否一致" width="120" align="center">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            v-model="row.isConsistent"
            size="small"
            placeholder="请选择"
            :class="{ 'consistency-empty': !row.isConsistent }"
            @change="emitSave()"
          >
            <el-option label="一致" value="一致" />
            <el-option label="不一致" value="不一致" />
            <el-option label="不适用" value="不适用" />
          </el-select>
          <el-tag
            v-else
            size="small"
            :type="consistencyTagType(row.isConsistent)"
          >{{ row.isConsistent || '—' }}</el-tag>
        </template>
      </el-table-column>

      <!-- 调整金额 -->
      <el-table-column label="调整金额" width="130" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            v-model="row.adjustmentAmount"
            size="small"
            :controls="false"
            :disabled="row.isConsistent !== '不一致'"
            style="width: 100%"
            @change="emitSave()"
          />
          <span v-else>{{ fmtAmount(row.adjustmentAmount) }}</span>
        </template>
      </el-table-column>

      <!-- 调整说明 -->
      <el-table-column label="调整说明" min-width="160">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            v-model="row.adjustmentNote"
            size="small"
            :disabled="row.isConsistent !== '不一致'"
            placeholder="调整原因说明"
            @change="emitSave()"
          />
          <span v-else>{{ row.adjustmentNote || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
        <template #default="{ $index }">
          <el-button
            size="small"
            type="danger"
            link
            @click="deleteRow($index)"
          >删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部操作栏 -->
    <div v-if="!isReadonly" class="bottom-actions">
      <el-button type="primary" size="small" @click="addRow">+ 添加政策事项</el-button>
      <el-button size="small" @click="handleSave">💾 保存</el-button>
    </div>

    <!-- 审计说明 -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <span>审计说明</span>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：可概述所执行程序、测试情况及结果，拟调整/未调整事项及其影响。"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <span>审计结论</span>
      </template>
      <el-input
        v-if="!isReadonly"
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="会计政策一致性检查结论..."
        @change="emitSave()"
      />
      <p v-else class="conclusion-text">{{ conclusion || '暂无结论' }}</p>
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表预置31项常见会计政策事项，可根据实际情况增删</p>
        <p>2. "是否一致"为必填项，保存时如有未选择的行将阻断提示</p>
        <p>3. 仅"不一致"时需填写调整金额和调整说明；"一致"或"不适用"时调整列禁用</p>
        <p>4. 调整金额汇总将反映在 G7-14 权益法测算表"会计政策调整"列</p>
        <p>5. 政策差异的调整应确保被投资方报表调整为与投资方一致的会计政策口径</p>
        <p>6. 参考CAS2长期股权投资准则第12条：应统一会计政策后计算</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G7TabAccountingPolicy — G7-6 被投资公司会计政策一致性检查（问卷式）
 *
 * 31行×7列：序号|会计政策事项|被投资方政策|投资方政策|是否一致(下拉)|调整金额|调整说明
 *
 * 功能：
 * - 预置31项常见会计政策事项（收入确认/存货计价/折旧/减值等）
 * - el-select 一致性下拉（一致/不一致/不适用）
 * - 保存校验：一致性未选择→阻断提示 ElMessage.error
 * - 不一致时调整金额+调整说明启用；一致/不适用时禁用
 * - 动态行增删
 * - 审计结论 el-card
 * - section标题栏右侧复核按钮(inject openReviewDialog)
 *
 * Spec: .kiro/specs/g7-long-term-equity-method/
 * Requirements: 3.2, 3.4
 */
import { reactive, ref, computed, inject, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { fmtAmount } from '@/utils/formatters'
import GtIndexChip from '../../GtIndexChip.vue'
import { useG7EquityMethodFormData } from '../../composables/useG7EquityMethodFormData'
import type { AccountingPolicyRow } from '../../composables/useG7EquityMethodFormData'

// ═══ Props ═══════════════════════════════════════════════════════════════════

const props = defineProps<{
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'save', data: { rows: AccountingPolicyRow[]; conclusion: string }): void
}>()

// ═══ Injections ═══════════════════════════════════════════════════════════════

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// ═══ 预置31项常见会计政策事项 ═══════════════════════════════════════════════

const DEFAULT_POLICY_ITEMS: string[] = [
  '收入确认政策',
  '存货计价方法',
  '固定资产折旧方法',
  '固定资产折旧年限',
  '固定资产残值率',
  '无形资产摊销方法',
  '无形资产摊销年限',
  '投资性房地产计量模式',
  '长期股权投资核算方法',
  '金融工具分类',
  '金融资产减值模型',
  '公允价值计量层次',
  '存货跌价准备计提',
  '应收款项坏账准备计提',
  '固定资产减值准备',
  '商誉减值测试',
  '资产减值损失确认',
  '借款费用资本化',
  '研发支出资本化',
  '政府补助会计处理',
  '所得税会计处理',
  '租赁会计处理',
  '外币折算方法',
  '合并报表范围确定',
  '关联方交易定价',
  '或有事项确认',
  '资产负债表日后事项',
  '会计估计变更',
  '前期差错更正',
  '职工薪酬确认',
  '股份支付计量',
]

// ═══ State ═══════════════════════════════════════════════════════════════════

const rows = reactive<AccountingPolicyRow[]>([])
const conclusion = ref('')
const isReadonly = computed(() => !!props.readonly)

// ═══ 审计说明持久化（checklist_responses，conclusion:null） ═══════════════════

const auditFormData = useG7EquityMethodFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const AUDIT_NOTE_KEY = 'G7-6-audit-note'
const auditNote = ref('')

function saveAuditNote(val: string): void {
  if (isReadonly.value) return
  auditNote.value = val
  auditFormData.debouncedSave(AUDIT_NOTE_KEY, { remark: val, conclusion: null })
}

onMounted(async () => {
  await auditFormData.load()
  const n = auditFormData.data.value.get(AUDIT_NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
})

// ═══ 动态行增删 ═══════════════════════════════════════════════════════════════

function addRow(): void {
  const newRow: AccountingPolicyRow = {
    id: `ap-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    seq: rows.length + 1,
    policyItem: '',
    investeePolicy: '',
    investorPolicy: '',
    isConsistent: '' as any,
    adjustmentAmount: 0,
    adjustmentNote: '',
  }
  rows.push(newRow)
  emitSave()
}

function deleteRow(index: number): void {
  rows.splice(index, 1)
  // 重排序号
  rows.forEach((r, i) => { r.seq = i + 1 })
  emitSave()
}

// ═══ 保存校验 ═══════════════════════════════════════════════════════════════

/**
 * 保存时校验：所有行的一致性字段必须已选择，否则阻断提示
 * @returns true=校验通过可保存；false=校验失败已提示
 */
function validateBeforeSave(): boolean {
  const emptyRows: number[] = []
  rows.forEach((row, idx) => {
    if (!row.isConsistent) {
      emptyRows.push(idx + 1)
    }
  })

  if (emptyRows.length > 0) {
    const rowNumbers = emptyRows.length <= 5
      ? emptyRows.join('、')
      : `${emptyRows.slice(0, 5).join('、')}等${emptyRows.length}行`
    ElMessage.error(`第 ${rowNumbers} 行"是否一致"尚未选择，请补充后再保存`)
    return false
  }
  return true
}

/**
 * 用户点击保存按钮
 */
function handleSave(): void {
  if (!validateBeforeSave()) return
  emitSave()
  ElMessage.success('会计政策一致性检查已保存')
}

// ═══ 保存 ═══════════════════════════════════════════════════════════════════

function emitSave(): void {
  emit('save', { rows: [...rows], conclusion: conclusion.value })
}

// ═══ 辅助函数 ═══════════════════════════════════════════════════════════════

function consistencyTagType(value: string): '' | 'success' | 'danger' | 'info' {
  switch (value) {
    case '一致': return 'success'
    case '不一致': return 'danger'
    case '不适用': return 'info'
    default: return ''
  }
}

// ═══ 数据水合 ═══════════════════════════════════════════════════════════════

function hydrateData(): void {
  const data = props.htmlData
  const policyData = data?.accountingPolicy ?? data?.accounting_policy ?? data

  const rawRows = policyData?.rows ?? []
  const rawConclusion = policyData?.conclusion ?? ''

  if (Array.isArray(rawRows) && rawRows.length > 0) {
    // 从已有数据恢复
    for (const r of rawRows) {
      rows.push({
        id: r.id ?? `ap-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        seq: r.seq ?? rows.length + 1,
        policyItem: r.policyItem ?? r.policy_item ?? '',
        investeePolicy: r.investeePolicy ?? r.investee_policy ?? '',
        investorPolicy: r.investorPolicy ?? r.investor_policy ?? '',
        isConsistent: r.isConsistent ?? r.is_consistent ?? '',
        adjustmentAmount: Number(r.adjustmentAmount ?? r.adjustment_amount ?? 0) || 0,
        adjustmentNote: r.adjustmentNote ?? r.adjustment_note ?? '',
      })
    }
  } else {
    // 预填31项默认政策事项
    for (let i = 0; i < DEFAULT_POLICY_ITEMS.length; i++) {
      rows.push({
        id: `ap-init-${i}`,
        seq: i + 1,
        policyItem: DEFAULT_POLICY_ITEMS[i],
        investeePolicy: '',
        investorPolicy: '',
        isConsistent: '' as any,
        adjustmentAmount: 0,
        adjustmentNote: '',
      })
    }
  }

  conclusion.value = rawConclusion
}

// ═══ 生命周期 ═══════════════════════════════════════════════════════════════

onMounted(() => {
  hydrateData()
})
</script>

<style scoped>
.g7-tab-accounting-policy {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}
.objective-alert {
  margin-bottom: 12px;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.tab-toolbar .toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.tab-toolbar .chip-wrap {
  display: inline-flex;
  align-items: center;
}

/* Section 标题栏 */
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
}

/* 方法论上下文区域 */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  margin-bottom: 12px;
  border-radius: 0 4px 4px 0;
  font-size: 12px;
  color: #606266;
  line-height: 1.6;
}
.methodology-context p {
  margin: 2px 0;
}

/* 表格 */
.policy-table {
  margin-bottom: 12px;
}

/* 一致性未选时边框提示 */
:deep(.consistency-empty .el-input__wrapper) {
  box-shadow: 0 0 0 1px #f56c6c inset;
}

/* 底部操作栏 */
.bottom-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  padding: 8px 0;
}

/* 审计结论卡片 */
.conclusion-card {
  margin-top: 16px;
}
.conclusion-card :deep(.el-card__header) {
  padding: 10px 16px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}
.conclusion-text {
  margin: 0;
  color: #606266;
  white-space: pre-wrap;
}

/* 编制提示 */
.guidance-details {
  margin-top: 16px;
  padding: 8px 12px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  font-size: 12px;
  color: #606266;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
}
.guidance-content p {
  margin: 4px 0;
}
</style>
