<template>
  <div class="l3-tab-lt-loan-check">
    <!-- ═══ 返回目录 + 标题 + 操作栏 ═══ -->
    <div class="l3-check-header">
      <div class="l3-check-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">
          ← 返回目录
        </el-button>
        <h3 class="l3-check-title">L3-9 长期借款检查表</h3>
      </div>
      <div class="l3-check-header-right">
        <!-- AI辅助 -->
        <el-button size="small" @click="$emit('ai-assist', 'L3-9')">AI</el-button>
        <!-- 复核 -->
        <el-button size="small" @click="$emit('open-review', 'L3-9')">复核</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色） ═══ -->
    <div class="l3-methodology-context">
      <div class="l3-methodology-text">
        <strong>检查表目标：</strong>
        系统性检查长期借款各项审计要点，逐项确认检查结果并记录备注。
        完成全部检查后撰写审计结论。关注一年内到期重分类、利息测算联动L2/L8、
        征信完整性、逾期风险及抵质押有效性。
      </div>
    </div>

    <!-- ═══ 核对清单：账面核对 ═══ -->
    <el-card class="l3-section-card" shadow="never">
      <template #header>
        <div class="l3-section-header">
          <span class="l3-section-title">一、账面核对</span>
          <el-button
            v-if="!isReadonly"
            size="small"
            type="warning"
            plain
            @click="$emit('ai-assist', 'L3-9-account')"
          >
            AI 辅助
          </el-button>
        </div>
      </template>
      <el-table :data="accountCheckItems" border size="small" style="width: 100%">
        <el-table-column type="index" label="#" width="42" align="center" />
        <el-table-column prop="content" label="检查内容" min-width="280">
          <template #default="{ row }">
            <span>{{ row.content }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="result" label="检查结果" min-width="120" align="center">
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.result"
              size="small"
              placeholder="选择"
              @change="(val: string) => handleResultChange('account', $index, val)"
            >
              <el-option label="符合" value="符合" />
              <el-option label="不符合" value="不符合" />
              <el-option label="不适用" value="不适用" />
              <el-option label="待确认" value="待确认" />
            </el-select>
            <span v-else :class="getResultClass(row.result)">{{ row.result || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="200">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.remark"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              size="small"
              placeholder="填写备注..."
              @input="(val: string) => handleRemarkChange('account', $index, val)"
            />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 核对清单：合同与利息检查 ═══ -->
    <el-card class="l3-section-card" shadow="never">
      <template #header>
        <div class="l3-section-header">
          <span class="l3-section-title">二、合同与利息检查</span>
          <el-button
            v-if="!isReadonly"
            size="small"
            type="warning"
            plain
            @click="$emit('ai-assist', 'L3-9-contract')"
          >
            AI 辅助
          </el-button>
        </div>
      </template>
      <el-table :data="contractCheckItems" border size="small" style="width: 100%">
        <el-table-column type="index" label="#" width="42" align="center" />
        <el-table-column prop="content" label="检查内容" min-width="280">
          <template #default="{ row }">
            <span>{{ row.content }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="result" label="检查结果" min-width="120" align="center">
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.result"
              size="small"
              placeholder="选择"
              @change="(val: string) => handleResultChange('contract', $index, val)"
            >
              <el-option label="符合" value="符合" />
              <el-option label="不符合" value="不符合" />
              <el-option label="不适用" value="不适用" />
              <el-option label="待确认" value="待确认" />
            </el-select>
            <span v-else :class="getResultClass(row.result)">{{ row.result || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="200">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.remark"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              size="small"
              placeholder="填写备注..."
              @input="(val: string) => handleRemarkChange('contract', $index, val)"
            />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 核对清单：风险与担保检查 ═══ -->
    <el-card class="l3-section-card" shadow="never">
      <template #header>
        <div class="l3-section-header">
          <span class="l3-section-title">三、风险与担保检查</span>
          <el-button
            v-if="!isReadonly"
            size="small"
            type="warning"
            plain
            @click="$emit('ai-assist', 'L3-9-risk')"
          >
            AI 辅助
          </el-button>
        </div>
      </template>
      <el-table :data="riskCheckItems" border size="small" style="width: 100%">
        <el-table-column type="index" label="#" width="42" align="center" />
        <el-table-column prop="content" label="检查内容" min-width="280">
          <template #default="{ row }">
            <span>{{ row.content }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="result" label="检查结果" min-width="120" align="center">
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.result"
              size="small"
              placeholder="选择"
              @change="(val: string) => handleResultChange('risk', $index, val)"
            >
              <el-option label="符合" value="符合" />
              <el-option label="不符合" value="不符合" />
              <el-option label="不适用" value="不适用" />
              <el-option label="待确认" value="待确认" />
            </el-select>
            <span v-else :class="getResultClass(row.result)">{{ row.result || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="200">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.remark"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              size="small"
              placeholder="填写备注..."
              @input="(val: string) => handleRemarkChange('risk', $index, val)"
            />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 核对清单：披露与分类检查 ═══ -->
    <el-card class="l3-section-card" shadow="never">
      <template #header>
        <div class="l3-section-header">
          <span class="l3-section-title">四、披露与分类检查</span>
          <el-button
            v-if="!isReadonly"
            size="small"
            type="warning"
            plain
            @click="$emit('ai-assist', 'L3-9-disclosure')"
          >
            AI 辅助
          </el-button>
        </div>
      </template>
      <el-table :data="disclosureCheckItems" border size="small" style="width: 100%">
        <el-table-column type="index" label="#" width="42" align="center" />
        <el-table-column prop="content" label="检查内容" min-width="280">
          <template #default="{ row }">
            <span>{{ row.content }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="result" label="检查结果" min-width="120" align="center">
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.result"
              size="small"
              placeholder="选择"
              @change="(val: string) => handleResultChange('disclosure', $index, val)"
            >
              <el-option label="符合" value="符合" />
              <el-option label="不符合" value="不符合" />
              <el-option label="不适用" value="不适用" />
              <el-option label="待确认" value="待确认" />
            </el-select>
            <span v-else :class="getResultClass(row.result)">{{ row.result || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="200">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.remark"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              size="small"
              placeholder="填写备注..."
              @input="(val: string) => handleRemarkChange('disclosure', $index, val)"
            />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 检查统计 ═══ -->
    <div class="l3-check-summary">
      <span class="summary-item pass">符合：{{ passCount }}</span>
      <span class="summary-item fail">不符合：{{ failCount }}</span>
      <span class="summary-item na">不适用：{{ naCount }}</span>
      <span class="summary-item pending">待确认：{{ pendingCount }}</span>
    </div>

    <!-- ═══ 审计结论区 ═══ -->
    <el-card class="l3-conclusion-card" shadow="never">
      <template #header>
        <div class="l3-section-header">
          <span class="l3-section-title">审计结论</span>
          <el-button
            v-if="!isReadonly"
            size="small"
            type="warning"
            plain
            @click="handleAiConclusion"
          >
            AI 辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 12 }"
        :disabled="isReadonly"
        placeholder="根据上述检查结果，对长期借款审计结论如下..."
        @input="handleConclusionInput"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l3-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>检查方法</strong>：逐项确认各检查要点的符合性</li>
        <li><strong>结果选项</strong>：符合/不符合/不适用/待确认</li>
        <li><strong>不符合处理</strong>：发现不符合项应在备注中说明原因及后续措施</li>
        <li><strong>长期借款特有</strong>：关注一年内到期重分类是否正确、利息测算与L2/L8是否一致</li>
        <li><strong>结论撰写</strong>：综合全部检查结果撰写总体审计结论</li>
        <li><strong>关联底稿</strong>：检查项与明细表L3-2、利息测算L3-5、合同检查L3-6等底稿数据对应</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L3TabLtLoanCheck — L3-9 长期借款检查表
 *
 * 核对清单 + 审计结论区（el-card包裹）。
 * 4个section：账面核对/合同与利息/风险与担保/披露与分类。
 * 每个section标题行右侧放AI辅助按钮。
 * Checklist items: checkbox/select/text inputs。
 * 结论区: textarea autosize + AI按钮。
 *
 * Spec: .kiro/specs/l3-long-term-loans/
 * Task: 4.6
 * Requirements: 8.3-8.4
 */
import { computed, inject, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { useL3FormData } from '@/components/workpaper/composables/useL3FormData'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

defineEmits<{
  (e: 'navigate', sheetName: string): void
  (e: 'ai-assist', section: string): void
  (e: 'open-review', section: string): void
}>()

// ─── Inject formData ─────────────────────────────────────────────────────────

const formData = inject<ReturnType<typeof useL3FormData>>('l3FormData')!

// ─── Checklist definitions ───────────────────────────────────────────────────

interface CheckItem {
  content: string
  result: string
  remark: string
}

/** Section 1: 账面核对 */
const ACCOUNT_ITEMS: string[] = [
  '长期借款明细账与总账是否一致',
  '长期借款明细合计与审定表L3-1期末余额是否一致',
  '期末余额=期初+本期借入(贷方)-本期归还(借方)，负债类公式是否成立',
  '一年内到期的长期借款是否已正确识别并重分类',
]

/** Section 2: 合同与利息 */
const CONTRACT_ITEMS: string[] = [
  '各笔长期借款是否均有合同支持，合同要素是否完整',
  '合同利率与账面计息利率是否一致',
  '合同金额与账面借款余额是否一致',
  '合同到期日与系统记录是否一致',
  '测算利息与账载利息差异是否在合理范围内（联动L3-5）',
  '计息期间、利率是否与合同约定一致',
  '利息测算结果与L2应付利息/L8财务费用是否匹配',
]

/** Section 3: 风险与担保 */
const RISK_ITEMS: string[] = [
  '征信报告余额与账面余额是否一致（联动L3-4）',
  '是否存在逾期贷款（已识别并评估风险，联动L3-7）',
  '逾期贷款是否已适当披露',
  '抵质押资产权属是否已验证（联动L3-8）',
  '担保价值是否充分覆盖借款金额',
  '是否存在违反借款合同限制性条款的情况',
]

/** Section 4: 披露与分类 */
const DISCLOSURE_ITEMS: string[] = [
  '长期借款附注披露信息是否完整准确',
  '一年内到期非流动负债重分类是否正确反映',
  '借款利率、币种、担保方式是否完整披露',
  '是否存在需特别说明的借款事项（展期/减免/逾期等）',
]

// ─── State ───────────────────────────────────────────────────────────────────

const accountCheckItems = ref<CheckItem[]>([])
const contractCheckItems = ref<CheckItem[]>([])
const riskCheckItems = ref<CheckItem[]>([])
const disclosureCheckItems = ref<CheckItem[]>([])
const conclusion = ref('')

// ─── All items flat for stats ────────────────────────────────────────────────

const allCheckItems = computed(() => [
  ...accountCheckItems.value,
  ...contractCheckItems.value,
  ...riskCheckItems.value,
  ...disclosureCheckItems.value,
])

const passCount = computed(() => allCheckItems.value.filter(i => i.result === '符合').length)
const failCount = computed(() => allCheckItems.value.filter(i => i.result === '不符合').length)
const naCount = computed(() => allCheckItems.value.filter(i => i.result === '不适用').length)
const pendingCount = computed(() => allCheckItems.value.filter(i => !i.result || i.result === '待确认').length)

// ─── Section map for persistence ─────────────────────────────────────────────

type SectionKey = 'account' | 'contract' | 'risk' | 'disclosure'

const sectionRefs: Record<SectionKey, { items: typeof accountCheckItems; defaults: string[] }> = {
  account: { items: accountCheckItems, defaults: ACCOUNT_ITEMS },
  contract: { items: contractCheckItems, defaults: CONTRACT_ITEMS },
  risk: { items: riskCheckItems, defaults: RISK_ITEMS },
  disclosure: { items: disclosureCheckItems, defaults: DISCLOSURE_ITEMS },
}

// ─── Load ────────────────────────────────────────────────────────────────────

function loadFromFormData(): void {
  const map = formData.allResponses.value

  for (const [section, { items: itemsRef, defaults }] of Object.entries(sectionRefs) as [SectionKey, typeof sectionRefs[SectionKey]][]) {
    const loaded: CheckItem[] = defaults.map(content => ({ content, result: '', remark: '' }))

    for (const [itemId, resp] of map.entries()) {
      const pattern = new RegExp(`^L3-chk-${section}-(\\d+)-(result|remark)$`)
      const match = itemId.match(pattern)
      if (!match) continue
      const idx = parseInt(match[1], 10) - 1
      const field = match[2] as 'result' | 'remark'
      if (idx >= 0 && idx < loaded.length) {
        loaded[idx][field] = resp.remark || resp.conclusion || ''
      }
    }

    itemsRef.value = loaded
  }

  // Load conclusion
  const conResp = map.get('L3-chk-conclusion')
  if (conResp) {
    conclusion.value = conResp.remark || conResp.conclusion || ''
  }
}

onMounted(() => {
  loadFromFormData()
})

// ─── Event handlers ──────────────────────────────────────────────────────────

function handleResultChange(section: SectionKey, index: number, val: string): void {
  sectionRefs[section].items.value[index].result = val
  const n = index + 1
  formData.saveField(`L3-chk-${section}-${n}-result`, { remark: val || undefined })
}

function handleRemarkChange(section: SectionKey, index: number, val: string): void {
  sectionRefs[section].items.value[index].remark = val
  const n = index + 1
  formData.debouncedSave(`L3-chk-${section}-${n}-remark`, { remark: val || undefined })
}

function handleConclusionInput(val: string): void {
  conclusion.value = val
  formData.debouncedSave('L3-chk-conclusion', { remark: val || undefined })
}

async function handleAiConclusion(): Promise<void> {
  ElMessageBox.alert('AI辅助结论生成功能即将上线', '提示')
}

// ─── Result styling ──────────────────────────────────────────────────────────

function getResultClass(result: string): string {
  switch (result) {
    case '符合': return 'result-pass'
    case '不符合': return 'result-fail'
    case '不适用': return 'result-na'
    default: return 'result-pending'
  }
}
</script>

<style scoped>
.l3-tab-lt-loan-check {
  padding: 12px;
  font-size: 13px;
}

/* ─── 头部 ─── */
.l3-check-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.l3-check-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.l3-check-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.l3-check-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

/* ─── 方法论上下文（琥珀色） ─── */
.l3-methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 14px;
  font-size: 13px;
  color: #5a4e3a;
  line-height: 1.6;
}

.l3-methodology-text strong {
  color: #b88230;
}

/* ─── Section卡片 ─── */
.l3-section-card {
  margin-bottom: 16px;
}

.l3-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.l3-section-title {
  font-weight: 600;
  font-size: 14px;
  color: #303133;
}

/* ─── 表格统一13px字体 ─── */
:deep(.el-table) {
  font-size: 13px;
}

:deep(.el-table th .cell) {
  font-size: 13px;
  font-weight: 600;
}

/* ─── 检查结果样式 ─── */
.result-pass {
  color: #67c23a;
  font-weight: 600;
}

.result-fail {
  color: #f56c6c;
  font-weight: 600;
}

.result-na {
  color: #909399;
}

.result-pending {
  color: #e6a23c;
}

/* ─── 检查统计 ─── */
.l3-check-summary {
  display: flex;
  gap: 20px;
  margin: 14px 0;
  padding: 10px 16px;
  background: #f5f7fa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 13px;
}

.summary-item {
  font-weight: 600;
}

.summary-item.pass {
  color: #67c23a;
}

.summary-item.fail {
  color: #f56c6c;
}

.summary-item.na {
  color: #909399;
}

.summary-item.pending {
  color: #e6a23c;
}

/* ─── 结论卡片 ─── */
.l3-conclusion-card {
  margin-top: 16px;
}

/* ─── 编制提示折叠 ─── */
.l3-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 13px;
  color: #606266;
}

.l3-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.l3-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
