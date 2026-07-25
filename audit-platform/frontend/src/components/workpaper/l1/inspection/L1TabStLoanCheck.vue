<template>
  <div class="l1-tab-st-loan-check">
    <!-- ═══ 返回目录 + 标题 ═══ -->
    <div class="check-header">
      <div class="check-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">
          ← 返回目录
        </el-button>
        <h3 class="check-title">L1-9 短期借款检查表</h3>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>检查表目标：</strong>
        系统性检查短期借款各项审计要点，逐项确认检查结果并记录备注。
        完成全部检查后撰写审计结论。各检查项目结果与明细表L1-2/利息测算L1-5联动验证。
      </div>
    </div>

    <!-- ═══ 核对清单表格 ═══ -->
    <el-table
      :data="checklistItems"
      border
      size="small"
      style="width: 100%"
      max-height="480"
    >
      <el-table-column type="index" label="#" width="42" align="center" />

      <el-table-column prop="category" label="项目" min-width="100">
        <template #default="{ row }">
          <span class="category-text">{{ row.category }}</span>
        </template>
      </el-table-column>

      <el-table-column prop="content" label="检查内容" min-width="240">
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
            @change="(val: string) => handleResultChange($index, val)"
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
            @input="(val: string) => handleRemarkChange($index, val)"
          />
          <span v-else>{{ row.remark || '-' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 检查统计 ═══ -->
    <div class="check-summary">
      <span class="summary-item pass">符合：{{ passCount }}</span>
      <span class="summary-item fail">不符合：{{ failCount }}</span>
      <span class="summary-item na">不适用：{{ naCount }}</span>
      <span class="summary-item pending">待确认：{{ pendingCount }}</span>
    </div>

    <!-- ═══ 审计结论区 ═══ -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <div class="conclusion-header">
          <span>审计结论</span>
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
        :autosize="{ minRows: 4, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="根据上述检查结果，对短期借款审计结论如下..."
        @input="handleConclusionInput"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l1-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>检查方法</strong>：逐项确认各检查要点的符合性</li>
        <li><strong>结果选项</strong>：符合/不符合/不适用/待确认</li>
        <li><strong>不符合处理</strong>：发现不符合项应在备注中说明原因及后续措施</li>
        <li><strong>结论撰写</strong>：综合全部检查结果撰写总体审计结论</li>
        <li><strong>关联底稿</strong>：检查项与明细表L1-2、利息测算L1-5等底稿数据对应</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L1TabStLoanCheck — L1-9 短期借款检查表
 *
 * 核对清单：多项检查条目，每项含项目/检查内容/检查结果/备注
 * 审计结论区：el-card包裹，textarea + AI辅助
 * 简单表结构（不需要区段Tab，列数≤15）
 *
 * Spec: .kiro/specs/l1-short-term-loans/
 * Task: 4.6
 * Requirements: 7.3-7.4
 */
import { computed, inject, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { useL1FormData, ChecklistItem } from '@/composables/useL1FormData'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

// ─── Inject formData ─────────────────────────────────────────────────────────

const formData = inject<ReturnType<typeof useL1FormData>>('l1FormData')!

// ─── Checklist definition ────────────────────────────────────────────────────

interface CheckItem {
  category: string
  content: string
  result: string
  remark: string
}

/** 预定义检查项目（基于源模板L1-9结构） */
const DEFAULT_CHECK_ITEMS: Omit<CheckItem, 'result' | 'remark'>[] = [
  { category: '账面核对', content: '短期借款明细账与总账是否一致' },
  { category: '账面核对', content: '短期借款明细合计与审定表期末余额是否一致' },
  { category: '合同核对', content: '各笔借款是否均有合同支持，合同要素是否完整' },
  { category: '合同核对', content: '合同利率与账面计息利率是否一致' },
  { category: '合同核对', content: '合同金额与账面借款余额是否一致' },
  { category: '征信核对', content: '征信报告余额与账面余额是否一致（差异已说明）' },
  { category: '利息测算', content: '测算利息与账载利息差异是否在合理范围内' },
  { category: '利息测算', content: '计息期间、利率是否与合同一致' },
  { category: '逾期检查', content: '是否存在逾期贷款（已识别并评估风险）' },
  { category: '担保检查', content: '抵质押资产权属是否已验证' },
  { category: '担保检查', content: '担保价值是否充分覆盖借款金额' },
  { category: '披露检查', content: '短期借款附注披露信息是否完整准确' },
]

// ─── State ───────────────────────────────────────────────────────────────────

const checklistItems = ref<CheckItem[]>([])
const conclusion = ref('')

// ─── Computed stats ──────────────────────────────────────────────────────────

const passCount = computed(() => checklistItems.value.filter(i => i.result === '符合').length)
const failCount = computed(() => checklistItems.value.filter(i => i.result === '不符合').length)
const naCount = computed(() => checklistItems.value.filter(i => i.result === '不适用').length)
const pendingCount = computed(() => checklistItems.value.filter(i => !i.result || i.result === '待确认').length)

// ─── Load ────────────────────────────────────────────────────────────────────

function loadFromFormData(): void {
  // Initialize from defaults then overlay saved data
  const items: CheckItem[] = DEFAULT_CHECK_ITEMS.map(d => ({
    ...d,
    result: '',
    remark: '',
  }))

  // Try to load saved results from checklist_responses
  // 🔴 用 getItemsByPrefix 从原始 responses 恢复，不能用 serializeAll()
  //    （其仅含结构化 sheet 字段，不含 L1-chk-* → 刷新后检查结果丢失）。
  try {
    const allItems = formData.getItemsByPrefix('L1-chk-')
    for (const item of allItems) {
      // Pattern: L1-chk-{n}-result or L1-chk-{n}-remark
      const match = item.item_id.match(/^L1-chk-(\d+)-(result|remark)$/)
      if (!match) continue
      const idx = parseInt(match[1], 10) - 1
      const field = match[2] as 'result' | 'remark'
      if (idx >= 0 && idx < items.length) {
        items[idx][field] = item.remark || item.conclusion || ''
      }
    }

    // Load conclusion
    const conItem = allItems.find(i => i.item_id === 'L1-chk-conclusion')
    if (conItem) {
      conclusion.value = conItem.remark || conItem.conclusion || ''
    }
  } catch {
    // First load - use defaults
  }

  checklistItems.value = items
}

onMounted(() => {
  loadFromFormData()
})

// ─── Event handlers ──────────────────────────────────────────────────────────

function handleResultChange(index: number, val: string): void {
  checklistItems.value[index].result = val
  const n = index + 1
  formData.saveImmediate([{
    item_id: `L1-chk-${n}-result`,
    conclusion: null,
    remark: val || null,
  }])
}

function handleRemarkChange(index: number, val: string): void {
  checklistItems.value[index].remark = val
  const n = index + 1
  formData.debounceSave([{
    item_id: `L1-chk-${n}-remark`,
    conclusion: null,
    remark: val || null,
  }])
}

function handleConclusionInput(val: string): void {
  conclusion.value = val
  formData.debounceSave([{
    item_id: 'L1-chk-conclusion',
    conclusion: null,
    remark: val || null,
  }])
}

async function handleAiConclusion(): Promise<void> {
  try {
    // 🔴 /ai/generate-text 的 context 类型是 dict[str,str]，值必须为字符串（否则 422）
    const context: Record<string, string> = {
      检查项总数: String(checklistItems.value.length),
      符合: String(passCount.value),
      不符合: String(failCount.value),
      不适用: String(naCount.value),
      待确认: String(pendingCount.value),
      不符合事项: checklistItems.value
        .filter(i => i.result === '不符合')
        .map(i => `${i.content}（${i.remark || '无备注'}）`)
        .join('；'),
    }
    const res = await (await import('@/utils/http')).default.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'st-loan-check-conclusion',
      prompt: '请基于短期借款检查表各项检查结果，生成审计结论（包含符合情况、不符合事项及整体判断）',
      context,
    })
    const content = res.data?.data?.content
    if (content) {
      conclusion.value = content
      handleConclusionInput(content)
    }
  } catch {
    ElMessage.info('AI辅助暂不可用，请手动撰写结论')
  }
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
.l1-tab-st-loan-check {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 头部 ─── */
.check-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.check-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.check-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

/* ─── 方法论上下文（琥珀色） ─── */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 14px;
  font-size: var(--wp-font-size, 13px);
  color: #5a4e3a;
  line-height: 1.6;
}

.methodology-text strong {
  color: #b88230;
}

/* ─── 表格统一13px字体 ─── */
:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}

:deep(.el-table th .cell) {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}

/* ─── 分类文字加粗 ─── */
.category-text {
  font-weight: 600;
  color: #409eff;
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
.check-summary {
  display: flex;
  gap: 20px;
  margin-top: 14px;
  padding: 10px 16px;
  background: #f5f7fa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
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
.conclusion-card {
  margin-top: 16px;
}

.conclusion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
}

/* ─── 编制提示折叠 ─── */
.l1-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.l1-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.l1-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
