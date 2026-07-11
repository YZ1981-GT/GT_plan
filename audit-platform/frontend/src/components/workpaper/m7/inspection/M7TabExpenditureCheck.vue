<template>
  <div class="m7-tab-expenditure-check">
    <!-- ═══ 标题 + 操作栏 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M7-5 专项储备支出检查表</h3>
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

    <!-- ═══ 蓝色渐变引导区 ═══ -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step">
          <span class="guide-num">①</span>
          <span class="guide-text">逐笔录入资本性/费用性支出凭证</span>
        </div>
        <div class="guide-step">
          <span class="guide-num">②</span>
          <span class="guide-text">核对支持性文件与业务内容一致性</span>
        </div>
        <div class="guide-step">
          <span class="guide-num">③</span>
          <span class="guide-text">检查资本化支出H1固定资产联动折旧</span>
        </div>
        <div class="guide-step">
          <span class="guide-num">④</span>
          <span class="guide-text">完成核对清单并填写审计结论</span>
        </div>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色左边线） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>费用化 vs 资本化会计处理说明：</strong>
        ①<strong>费用性支出</strong>：直接冲减专项储备（借：专项储备 贷：银行存款等），不形成资产。
        ②<strong>资本性支出</strong>：形成固定资产（借：固定资产 贷：在建工程/银行存款），
        同时全额计提折旧冲减专项储备（借：专项储备 贷：累计折旧），联动H1固定资产底稿。
        ③核查要点：支出是否属于安全生产规定范围、凭证完整性、资本化条件是否满足、折旧是否已全额计提。
      </div>
    </div>

    <!-- ═══ Section 1: 资本性支出检查 ═══ -->
    <el-card shadow="never" class="check-card">
      <template #header>
        <div class="card-header">
          <span class="card-title-text">资本性支出检查</span>
          <div class="card-header-right">
            <el-tag size="small" type="warning" effect="plain">
              {{ capitalRows.length }} 笔 · {{ fmtAmount(capitalTotal) }}
            </el-tag>
            <el-button v-if="!isReadonly" size="small" type="primary" plain @click="addRow('capital')">
              + 新增
            </el-button>
            <el-button size="small" @click="handleAI('capital')">
              <el-icon><MagicStick /></el-icon> AI辅助
            </el-button>
            <el-button size="small" @click="openReviewDialog?.('M7-5-capital', '资本性支出检查')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="capitalRows" size="small" border style="width: 100%" max-height="400">
        <el-table-column label="日期" width="110" fixed>
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" :model-value="row.date" size="small" placeholder="YYYY-MM-DD"
              @change="(v: string) => updateRow('capital', $index, 'date', v)" />
            <span v-else>{{ row.date || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证编号" width="100">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small" placeholder="记-XXX"
              @change="(v: string) => updateRow('capital', $index, 'voucherNo', v)" />
            <span v-else>{{ row.voucherNo || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="业务内容" min-width="140">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" :model-value="row.content" size="small" placeholder="安全设备购置等"
              @change="(v: string) => updateRow('capital', $index, 'content', v)" />
            <span v-else>{{ row.content || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="对方科目" width="120">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" :model-value="row.counterAccount" size="small" placeholder="固定资产等"
              @change="(v: string) => updateRow('capital', $index, 'counterAccount', v)" />
            <span v-else>{{ row.counterAccount || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.amount" size="small" :controls="false"
              :precision="2" style="width: 100%"
              @change="(v: number) => updateRow('capital', $index, 'amount', v ?? 0)" />
            <span v-else>{{ fmtAmount(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="支持性文件" width="100">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" :model-value="row.supportDoc" size="small" placeholder="📎"
              @change="(v: string) => updateRow('capital', $index, 'supportDoc', v)" />
            <span v-else>{{ row.supportDoc || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否属规定范围" width="120" align="center">
          <template #default="{ row, $index }">
            <el-select v-if="!isReadonly" :model-value="row.isInScope" size="small" placeholder="—"
              @change="(v: string) => updateRow('capital', $index, 'isInScope', v)">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
            <el-tag v-else :type="row.isInScope === '是' ? 'success' : row.isInScope === '否' ? 'danger' : 'info'" size="small">
              {{ row.isInScope || '—' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="对应固定资产是否已全额计提折旧" width="180" align="center">
          <template #default="{ row, $index }">
            <el-select v-if="!isReadonly" :model-value="row.depreciationFull" size="small" placeholder="—"
              @change="(v: string) => updateRow('capital', $index, 'depreciationFull', v)">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="不适用" value="不适用" />
            </el-select>
            <el-tag v-else :type="row.depreciationFull === '是' ? 'success' : row.depreciationFull === '否' ? 'danger' : 'info'" size="small">
              {{ row.depreciationFull || '—' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="100" align="center">
          <template #default="{ row }">
            <GtIndexChip v-if="row.indexRef" :value="row.indexRef" :context-project-id="projectId" />
            <span v-else class="index-placeholder">H1</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
          <template #default="{ $index }">
            <el-button type="danger" text size="small" @click="removeRow('capital', $index)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section 2: 费用性支出检查 ═══ -->
    <el-card shadow="never" class="check-card">
      <template #header>
        <div class="card-header">
          <span class="card-title-text">费用性支出检查</span>
          <div class="card-header-right">
            <el-tag size="small" type="info" effect="plain">
              {{ expenseRows.length }} 笔 · {{ fmtAmount(expenseTotal) }}
            </el-tag>
            <el-button v-if="!isReadonly" size="small" type="primary" plain @click="addRow('expense')">
              + 新增
            </el-button>
            <el-button size="small" @click="handleAI('expense')">
              <el-icon><MagicStick /></el-icon> AI辅助
            </el-button>
            <el-button size="small" @click="openReviewDialog?.('M7-5-expense', '费用性支出检查')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="expenseRows" size="small" border style="width: 100%" max-height="400">
        <el-table-column label="日期" width="110" fixed>
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" :model-value="row.date" size="small" placeholder="YYYY-MM-DD"
              @change="(v: string) => updateRow('expense', $index, 'date', v)" />
            <span v-else>{{ row.date || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证编号" width="100">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small" placeholder="记-XXX"
              @change="(v: string) => updateRow('expense', $index, 'voucherNo', v)" />
            <span v-else>{{ row.voucherNo || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="业务内容" min-width="140">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" :model-value="row.content" size="small" placeholder="安全培训费等"
              @change="(v: string) => updateRow('expense', $index, 'content', v)" />
            <span v-else>{{ row.content || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="对方科目" width="120">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" :model-value="row.counterAccount" size="small" placeholder="银行存款等"
              @change="(v: string) => updateRow('expense', $index, 'counterAccount', v)" />
            <span v-else>{{ row.counterAccount || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.amount" size="small" :controls="false"
              :precision="2" style="width: 100%"
              @change="(v: number) => updateRow('expense', $index, 'amount', v ?? 0)" />
            <span v-else>{{ fmtAmount(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="支持性文件" width="100">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" :model-value="row.supportDoc" size="small" placeholder="📎"
              @change="(v: string) => updateRow('expense', $index, 'supportDoc', v)" />
            <span v-else>{{ row.supportDoc || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核对项" width="100" align="center">
          <template #default="{ row, $index }">
            <el-select v-if="!isReadonly" :model-value="row.checkResult" size="small" placeholder="—"
              @change="(v: string) => updateRow('expense', $index, 'checkResult', v)">
              <el-option label="相符" value="相符" />
              <el-option label="不符" value="不符" />
            </el-select>
            <el-tag v-else :type="row.checkResult === '相符' ? 'success' : row.checkResult === '不符' ? 'danger' : 'info'" size="small">
              {{ row.checkResult || '—' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="是否属规定范围" width="120" align="center">
          <template #default="{ row, $index }">
            <el-select v-if="!isReadonly" :model-value="row.isInScope" size="small" placeholder="—"
              @change="(v: string) => updateRow('expense', $index, 'isInScope', v)">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
            <el-tag v-else :type="row.isInScope === '是' ? 'success' : row.isInScope === '否' ? 'danger' : 'info'" size="small">
              {{ row.isInScope || '—' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="100" align="center">
          <template #default="{ row }">
            <GtIndexChip v-if="row.indexRef" :value="row.indexRef" :context-project-id="projectId" />
            <span v-else class="index-placeholder">—</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
          <template #default="{ $index }">
            <el-button type="danger" text size="small" @click="removeRow('expense', $index)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 检查比例核算区 ═══ -->
    <el-card shadow="never" class="check-card">
      <template #header>
        <div class="card-header">
          <span class="card-title-text">检查比例核算</span>
          <div class="card-header-right">
            <el-button size="small" @click="handleAI('ratio')">
              <el-icon><MagicStick /></el-icon> AI辅助
            </el-button>
          </div>
        </div>
      </template>

      <el-table :data="ratioSummary" size="small" border>
        <el-table-column prop="category" label="类别" width="140" />
        <el-table-column label="账面使用金额" width="150" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="来源：M7-2明细表-本期使用合计">{{ fmtAmount(row.bookAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="检查金额" width="150" align="right">
          <template #default="{ row }">{{ fmtAmount(row.checkAmount) }}</template>
        </el-table-column>
        <el-table-column label="检查比例" width="120" align="right">
          <template #default="{ row }">
            <span :class="['ratio-cell', { 'ratio-warning': row.ratio < 0.5 }]">{{ fmtPercent(row.ratio) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 核对清单 ═══ -->
    <el-card shadow="never" class="check-card">
      <template #header>
        <div class="card-header">
          <span class="card-title-text">核对清单</span>
          <div class="card-header-right">
            <el-button size="small" @click="handleAI('checklist')">
              <el-icon><MagicStick /></el-icon> AI辅助
            </el-button>
            <el-button size="small" @click="openReviewDialog?.('M7-5-checklist', '核对清单')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <div class="checklist-section">
        <div v-for="(item, idx) in checklist" :key="idx" class="checklist-item">
          <span class="checklist-index">{{ idx + 1 }}.</span>
          <span class="checklist-text">{{ item.label }}</span>
          <el-radio-group
            v-if="!isReadonly"
            :model-value="item.passed"
            size="small"
            @change="(val: boolean | null) => updateChecklistItem(idx, val)"
          >
            <el-radio-button :value="true">通过</el-radio-button>
            <el-radio-button :value="false">不通过</el-radio-button>
          </el-radio-group>
          <el-tag
            v-else
            :type="item.passed === true ? 'success' : item.passed === false ? 'danger' : 'info'"
            size="small"
          >
            {{ item.passed === true ? '通过' : item.passed === false ? '不通过' : '待核' }}
          </el-tag>
        </div>
      </div>

      <!-- 不通过项备注 -->
      <div v-if="failedItems.length > 0" class="failed-notes">
        <el-divider content-position="left">不通过项说明</el-divider>
        <div v-for="fi in failedItems" :key="fi.idx" class="failed-note-item">
          <span class="failed-note-label">{{ fi.idx + 1 }}. {{ fi.label }}：</span>
          <el-input
            :model-value="fi.note"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 4 }"
            :disabled="isReadonly"
            placeholder="说明不通过原因..."
            @change="(val: string) => updateChecklistNote(fi.idx, val)"
          />
        </div>
      </div>
    </el-card>

    <!-- ═══ 审计结论区 ═══ -->
    <el-card shadow="never" class="check-card conclusion-card">
      <template #header>
        <div class="card-header">
          <span class="card-title-text">审计结论</span>
          <div class="card-header-right">
            <el-button size="small" @click="handleAI('conclusion')">
              <el-icon><MagicStick /></el-icon> AI辅助
            </el-button>
            <el-button size="small" @click="openReviewDialog?.('M7-5-conclusion', '审计结论')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-input
        :model-value="conclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="根据上述支出检查结果，填写专项储备支出审计结论..."
        @change="(val: string) => setConclusion(val)"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="m7-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>专项储备（4201）为<strong>权益类贷方科目</strong>：期末 = 期初 + 贷方（计提） − 借方（使用支出）</li>
        <li><strong>费用性支出</strong>：安全培训费、安全评价检测费等直接冲减专项储备</li>
        <li><strong>资本性支出</strong>：安全设备购置等形成固定资产，同时全额计提折旧冲减专项储备</li>
        <li>资本性支出检查须联动H1固定资产底稿，确认折旧是否已全额计提</li>
        <li>支出范围参照《企业安全生产费用提取和使用管理办法》</li>
        <li>检查比例建议覆盖账面使用金额的80%以上</li>
        <li>审定数应与M7-1审定表、M7-2明细表一致</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M7TabExpenditureCheck — M7-5 专项储备支出检查表
 *
 * Spec: .kiro/specs/m7-special-reserve/
 * Task: 4.5
 * Requirements: 5.1-5.3
 *
 * 功能：
 * - 区分费用性支出（直接冲减专项储备）vs 资本性支出（形成固定资产+全额折旧冲减）
 * - 两大检查区块（资本性+费用性）各带 el-table
 * - 资本性支出额外列："对应固定资产是否已全额计提折旧"
 * - GtIndexChip 联动 H1 固定资产底稿
 * - 检查比例核算区（账面使用/检查金额/检查比例）
 * - 核对清单（checkbox + 通过/不通过）
 * - 审计结论区（el-card包裹）
 * - 每个文本section标题行右侧AI辅助按钮
 * - 方法论上下文琥珀块（费用化vs资本化会计处理说明）
 * - 蓝色渐变引导区（4步骤）
 * - Font 13px
 * - useM7FormData 持久化
 * - 复核按钮（inject openReviewDialog）
 *
 * 科目：4201 专项储备（**贷方/权益类！**）
 * 使用支出在借方减少：费用化直接冲减 / 资本化转固定资产同时冲减
 */
import { computed, inject, onMounted, reactive, ref } from 'vue'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { useM7FormData } from '../../composables/useM7FormData'
import GtIndexChip from '../../GtIndexChip.vue'

// ─── Types ───────────────────────────────────────────────────────────────────

interface ExpenditureRow {
  date: string
  voucherNo: string
  content: string
  counterAccount: string
  amount: number
  supportDoc: string
  checkResult: string
  isInScope: string
  indexRef: string
  depreciationFull: string // capital only
}

interface ChecklistItem {
  label: string
  passed: boolean | null
  note: string
}

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<((sectionId: string, sectionLabel?: string) => void) | null>(
  'openReviewDialog',
  null,
)

// ─── FormData ────────────────────────────────────────────────────────────────

const formData = useM7FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── State ───────────────────────────────────────────────────────────────────

const capitalRows = ref<ExpenditureRow[]>([])
const expenseRows = ref<ExpenditureRow[]>([])
const conclusion = ref('')

// ─── 核对清单 ────────────────────────────────────────────────────────────────

const DEFAULT_CHECKLIST: ChecklistItem[] = [
  { label: '支出凭证附件完整（合同/发票/验收单/审批单）', passed: null, note: '' },
  { label: '支出项目属于安全生产规定范围', passed: null, note: '' },
  { label: '费用性支出会计分录正确（借：专项储备 贷：银行存款/应付账款）', passed: null, note: '' },
  { label: '资本性支出已确认为固定资产（联动H1）', passed: null, note: '' },
  { label: '资本性支出对应固定资产已全额计提折旧冲减专项储备', passed: null, note: '' },
  { label: '支出金额与明细表M7-2一致', passed: null, note: '' },
  { label: '无超范围或违规使用专项储备的情况', passed: null, note: '' },
]

const checklist = reactive<ChecklistItem[]>([...DEFAULT_CHECKLIST.map(c => ({ ...c }))])

// ─── Computed ────────────────────────────────────────────────────────────────

const capitalTotal = computed(() => capitalRows.value.reduce((s, r) => s + (r.amount || 0), 0))
const expenseTotal = computed(() => expenseRows.value.reduce((s, r) => s + (r.amount || 0), 0))

const failedItems = computed(() =>
  checklist
    .map((item, idx) => ({ ...item, idx }))
    .filter(item => item.passed === false),
)

/** 检查比例核算数据 */
const ratioSummary = computed(() => {
  // 账面使用金额从 formData 获取（M7-2明细表的使用合计）
  const bookCapital = Number(formData.getField('5', 'book-capital-usage') ?? 0)
  const bookExpense = Number(formData.getField('5', 'book-expense-usage') ?? 0)
  return [
    {
      category: '资本性支出',
      bookAmount: bookCapital || capitalTotal.value,
      checkAmount: capitalTotal.value,
      ratio: (bookCapital || capitalTotal.value) > 0
        ? capitalTotal.value / (bookCapital || capitalTotal.value)
        : 0,
    },
    {
      category: '费用性支出',
      bookAmount: bookExpense || expenseTotal.value,
      checkAmount: expenseTotal.value,
      ratio: (bookExpense || expenseTotal.value) > 0
        ? expenseTotal.value / (bookExpense || expenseTotal.value)
        : 0,
    },
    {
      category: '合计',
      bookAmount: (bookCapital || capitalTotal.value) + (bookExpense || expenseTotal.value),
      checkAmount: capitalTotal.value + expenseTotal.value,
      ratio: ((bookCapital || capitalTotal.value) + (bookExpense || expenseTotal.value)) > 0
        ? (capitalTotal.value + expenseTotal.value) / ((bookCapital || capitalTotal.value) + (bookExpense || expenseTotal.value))
        : 0,
    },
  ]
})

// ─── Row Actions ─────────────────────────────────────────────────────────────

function _emptyRow(): ExpenditureRow {
  return {
    date: '', voucherNo: '', content: '', counterAccount: '',
    amount: 0, supportDoc: '', checkResult: '', isInScope: '',
    indexRef: '', depreciationFull: '',
  }
}

function addRow(type: 'capital' | 'expense') {
  const row = _emptyRow()
  if (type === 'capital') {
    row.indexRef = 'H1'
    capitalRows.value.push(row)
  } else {
    expenseRows.value.push(row)
  }
  _saveRows()
}

function removeRow(type: 'capital' | 'expense', idx: number) {
  if (type === 'capital') {
    capitalRows.value.splice(idx, 1)
  } else {
    expenseRows.value.splice(idx, 1)
  }
  _saveRows()
}

function updateRow(type: 'capital' | 'expense', idx: number, field: keyof ExpenditureRow, val: any) {
  const rows = type === 'capital' ? capitalRows.value : expenseRows.value
  if (rows[idx]) {
    ;(rows[idx] as any)[field] = val
    _saveRows()
  }
}

// ─── Checklist Actions ───────────────────────────────────────────────────────

function updateChecklistItem(idx: number, val: boolean | null) {
  checklist[idx].passed = val
  _saveChecklist()
}

function updateChecklistNote(idx: number, val: string) {
  checklist[idx].note = val
  _saveChecklist()
}

function setConclusion(val: string) {
  conclusion.value = val
  formData.debouncedSave('M7-5-conclusion', { remark: val || null })
}

// ─── Persistence ─────────────────────────────────────────────────────────────

function _saveRows() {
  const data = {
    capital: capitalRows.value,
    expense: expenseRows.value,
  }
  formData.saveField('M7-5-expenditure-rows', { conclusion: JSON.stringify(data) })
}

function _saveChecklist() {
  const data = checklist.map(item => ({
    label: item.label,
    passed: item.passed,
    note: item.note,
  }))
  formData.saveField('M7-5-checklist-all', { remark: JSON.stringify(data) })
}

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleAI(_section: string) {
  /* AI辅助待集成（Phase 6/7） */
}

function handleReview() {
  openReviewDialog?.('M7-5-expenditure-check', '专项储备支出检查表')
}

// ─── Formatters ──────────────────────────────────────────────────────────────

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '—'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(ratio: number): string {
  if (!ratio) return '—'
  return `${(ratio * 100).toFixed(1)}%`
}

// ─── Restore ─────────────────────────────────────────────────────────────────

function _restoreData() {
  // 恢复检查行
  const rowsData = formData.getField('5', 'expenditure-rows')
  if (rowsData && typeof rowsData === 'object') {
    if (Array.isArray(rowsData.capital)) capitalRows.value = rowsData.capital
    if (Array.isArray(rowsData.expense)) expenseRows.value = rowsData.expense
  }

  // 恢复清单
  const checklistData = formData.allResponses.value.get('M7-5-checklist-all')
  if (checklistData?.remark) {
    try {
      const parsed = JSON.parse(checklistData.remark)
      if (Array.isArray(parsed) && parsed.length > 0) {
        for (let i = 0; i < checklist.length && i < parsed.length; i++) {
          checklist[i].passed = parsed[i].passed ?? null
          checklist[i].note = parsed[i].note ?? ''
        }
      }
    } catch { /* ignore */ }
  }

  // 恢复结论
  const conclusionData = formData.allResponses.value.get('M7-5-conclusion')
  if (conclusionData?.remark) conclusion.value = conclusionData.remark
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  _restoreData()
})
</script>

<style scoped>
.m7-tab-expenditure-check {
  padding: 12px;
  font-size: 13px;
}

/* ─── Header ──── */
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

/* ─── 蓝色渐变引导区 ──── */
.guide-area {
  background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%);
  border-radius: 8px;
  padding: 14px 18px;
  margin-bottom: 16px;
  border: 1px solid #b3d8fd;
}

.guide-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.guide-step {
  display: flex;
  align-items: center;
  gap: 8px;
}

.guide-num {
  font-weight: 700;
  color: #1a73e8;
  font-size: 14px;
}

.guide-text {
  color: #1a4f7a;
  font-size: 13px;
}

/* ─── 方法论上下文（琥珀色） ──── */
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

/* ─── Card / Table ──── */
.check-card {
  margin-bottom: 16px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}

.card-title-text {
  font-weight: 600;
  color: #303133;
  font-size: 14px;
}

.card-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ─── 公式列标记 ──── */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding: 1px 4px;
  background: #ecf5ff;
  border-radius: 2px;
}

/* ─── 比例 ──── */
.ratio-cell {
  font-weight: 600;
}

.ratio-warning {
  color: #e6a23c;
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

.checklist-item:last-child {
  border-bottom: none;
}

.checklist-index {
  font-weight: 600;
  color: #303133;
  min-width: 20px;
}

.checklist-text {
  flex: 1;
  color: #606266;
  line-height: 1.5;
}

/* ─── 不通过项 ──── */
.failed-notes {
  margin-top: 12px;
}

.failed-note-item {
  margin-bottom: 10px;
}

.failed-note-label {
  font-size: 12px;
  color: #f56c6c;
  font-weight: 500;
  display: block;
  margin-bottom: 4px;
}

/* ─── 结论 ──── */
.conclusion-card :deep(.el-card__body) {
  padding-top: 12px;
}

/* ─── 索引占位 ──── */
.index-placeholder {
  color: #c0c4cc;
  font-size: 12px;
}

/* ─── 编制提示 ──── */
.m7-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 13px;
  color: #606266;
}

.m7-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
}

.m7-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
