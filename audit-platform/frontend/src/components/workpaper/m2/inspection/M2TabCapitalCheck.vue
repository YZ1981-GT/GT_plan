<template>
  <div class="m2-tab-capital-check">
    <!-- ═══ 标题 + 操作栏 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M2-5 实收资本（股本）检查表</h3>
        <el-tag :type="isAllChecked ? 'success' : 'info'" size="small">
          检查进度 {{ completionRate }}%
        </el-tag>
        <el-tag v-if="failedCount > 0" type="danger" size="small">{{ failedCount }}项未通过</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddVerifyRow">
          <el-icon><Plus /></el-icon> 新增出资人
        </el-button>
        <el-button size="small" @click="handleAI('capital-check')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>验资核对（实收资本核心程序）：</strong>
        实收资本的存在与准确性认定依赖验资核对：将账面实缴出资与验资报告金额逐一对比。
        验资差异 = 实缴出资 − 验资金额；出资到位率 = 实缴出资 / 认缴出资。
        |差异| > {{ VERIFY_DIFF_THRESHOLD }} 元红色高亮；到位率 &lt; 100% 黄色提示认缴未实缴风险。
      </div>
    </div>

    <!-- ═══ Section 1: 验资核对表格 ═══ -->
    <el-card shadow="never" class="check-card">
      <template #header>
        <div class="card-header">
          <span>验资核对表</span>
          <el-button size="small" @click="handleAI('verify-table')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>

      <el-table :data="computedVerifyRows" border size="small" style="width: 100%" highlight-current-row>
        <el-table-column type="index" label="#" width="50" align="center" />

        <!-- 出资人 -->
        <el-table-column prop="investorName" label="出资人" min-width="140">
          <template #default="{ row }">
            <span>{{ row.investorName || '—' }}</span>
          </template>
        </el-table-column>

        <!-- 认缴出资 -->
        <el-table-column label="认缴出资" width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.subscribedAmount"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => updateVerifyRow($index, 'subscribedAmount', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.subscribedAmount) }}</span>
          </template>
        </el-table-column>

        <!-- 实缴出资 -->
        <el-table-column label="实缴出资" width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.paidAmount"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => updateVerifyRow($index, 'paidAmount', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.paidAmount) }}</span>
          </template>
        </el-table-column>

        <!-- 验资金额 -->
        <el-table-column label="验资金额" width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.verifiedAmount"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => updateVerifyRow($index, 'verifiedAmount', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.verifiedAmount) }}</span>
          </template>
        </el-table-column>

        <!-- 验资差异（公式列） -->
        <el-table-column label="验资差异" width="120" align="right">
          <template #header>
            <el-tooltip content="公式: 实缴出资 − 验资金额" placement="top">
              <span class="formula-col-header">验资差异</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span
              class="formula-value"
              :class="{ 'diff-alert-red': isDiffOverThreshold(row.verifyDiff) }"
            >
              {{ fmtAmount(row.verifyDiff) }}
            </span>
          </template>
        </el-table-column>

        <!-- 出资到位率（公式列） -->
        <el-table-column label="出资到位率" width="110" align="center">
          <template #header>
            <el-tooltip content="公式: 实缴出资 / 认缴出资" placement="top">
              <span class="formula-col-header">到位率</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span
              class="formula-value"
              :class="{
                'rate-alert-yellow': isPaidInRateBelowFull(row.paidInRate),
                'rate-ok': row.paidInRate >= 1.0,
              }"
            >
              {{ fmtPercent(row.paidInRate) }}
            </span>
          </template>
        </el-table-column>

        <!-- 验资机构 -->
        <el-table-column label="验资机构" min-width="140">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.verifyOrg"
              size="small"
              placeholder="验资机构名称"
              @change="(val: string) => updateVerifyRow($index, 'verifyOrg', val)"
            />
            <span v-else>{{ row.verifyOrg || '—' }}</span>
          </template>
        </el-table-column>

        <!-- 操作列 -->
        <el-table-column v-if="!isReadonly" label="操作" width="70" align="center">
          <template #default="{ $index }">
            <el-popconfirm title="确认删除该出资人？" @confirm="removeVerifyRow($index)">
              <template #reference>
                <el-button type="danger" text size="small">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <!-- 合计行 -->
      <div class="summary-bar">
        <span>认缴合计：<strong>{{ fmtAmount(totalSubscribed) }}</strong></span>
        <span>实缴合计：<strong>{{ fmtAmount(totalPaid) }}</strong></span>
        <span>验资合计：<strong>{{ fmtAmount(totalVerified) }}</strong></span>
        <span>差异合计：<strong :class="{ 'diff-alert-red': isDiffOverThreshold(totalVerifyDiff) }">{{ fmtAmount(totalVerifyDiff) }}</strong></span>
        <span>整体到位率：<strong :class="{ 'rate-alert-yellow': isPaidInRateBelowFull(overallPaidInRate) }">{{ fmtPercent(overallPaidInRate) }}</strong></span>
      </div>
    </el-card>

    <!-- ═══ Section 2: 核对清单（8项） ═══ -->
    <el-card shadow="never" class="check-card">
      <template #header>
        <div class="card-header">
          <span>核对清单</span>
          <el-progress :percentage="completionRate" :stroke-width="6" style="width: 120px" />
          <el-button size="small" @click="handleAI('checklist')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>

      <div class="checklist-items">
        <div
          v-for="item in checkItems"
          :key="item.id"
          class="checklist-row"
        >
          <div class="checklist-row-header">
            <span class="checklist-title">{{ item.title }}</span>
            <el-radio-group
              v-model="item.status"
              size="small"
              :disabled="isReadonly"
              @change="updateCheckStatus(item.id, item.status)"
            >
              <el-radio-button
                v-for="opt in CHECK_STATUS_OPTIONS"
                :key="opt.value"
                :value="opt.value"
              >
                {{ opt.label }}
              </el-radio-button>
            </el-radio-group>
          </div>
          <el-input
            v-if="item.status === 'fail' || item.remark"
            v-model="item.remark"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 3 }"
            :readonly="isReadonly"
            placeholder="检查说明/问题描述..."
            size="small"
            class="checklist-remark"
            @change="updateCheckRemark(item.id, item.remark)"
          />
        </div>
      </div>
    </el-card>

    <!-- ═══ Section 3: 审计结论区 ═══ -->
    <el-card shadow="never" class="check-card conclusion-card">
      <template #header>
        <div class="card-header">
          <span>审计结论</span>
          <el-button size="small" @click="handleAI('conclusion')">
            <el-icon><MagicStick /></el-icon> AI辅助结论
          </el-button>
        </div>
      </template>

      <el-form label-position="top" size="small">
        <el-form-item label="审计发现摘要">
          <el-input
            v-model="conclusion.findings"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 8 }"
            :readonly="isReadonly"
            placeholder="汇总审计发现：验资核对结果/异常差异/到位率不足等事项..."
            @change="updateConclusion('findings', conclusion.findings)"
          />
        </el-form-item>
        <el-form-item label="最终结论">
          <el-input
            v-model="conclusion.conclusion"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
            :readonly="isReadonly"
            placeholder="实收资本（股本）科目审计结论..."
            @change="updateConclusion('conclusion', conclusion.conclusion)"
          />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="编制人">
              <el-input
                v-model="conclusion.preparedBy"
                :readonly="isReadonly"
                placeholder="编制人"
                @change="updateConclusion('preparedBy', conclusion.preparedBy)"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="结论日期">
              <el-date-picker
                v-model="conclusion.conclusionDate"
                type="date"
                :disabled="isReadonly"
                placeholder="选择日期"
                value-format="YYYY-MM-DD"
                style="width: 100%"
                @change="updateConclusion('conclusionDate', conclusion.conclusionDate)"
              />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <!-- ═══ AI辅助sections ═══ -->
    <el-card
      v-for="section in aiSections"
      :key="section.sectionId"
      shadow="never"
      class="check-card ai-section"
    >
      <template #header>
        <div class="card-header">
          <span>{{ section.title }}</span>
          <el-button
            size="small"
            :loading="section.isGenerating"
            @click="handleAI(section.sectionId)"
          >
            <el-icon><MagicStick /></el-icon> {{ section.isGenerating ? '生成中...' : 'AI生成' }}
          </el-button>
        </div>
      </template>
      <el-input
        v-model="section.content"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :readonly="isReadonly"
        :placeholder="`${section.title}分析内容...`"
        @change="updateAiSectionContent(section.sectionId, section.content)"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>验资核对是实收资本审计的核心程序（ISA 505）</li>
        <li>逐一核对各出资人实缴出资与验资报告金额</li>
        <li>验资差异 = 实缴出资 − 验资金额（正差异：账面>验资需查明）</li>
        <li>出资到位率 = 实缴出资 / 认缴出资（&lt;100%关注公司法出资期限）</li>
        <li>差异超{{ VERIFY_DIFF_THRESHOLD }}元红色高亮，到位率&lt;100%黄色提示</li>
        <li>核对清单8项：真实性/完整性/准确性/时效性/非货币/减资/工商/披露</li>
        <li>全部核对完成后填写审计结论</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M2TabCapitalCheck — M2-5 实收资本（股本）检查表（含验资核对）
 *
 * Spec: .kiro/specs/m2-paid-in-capital/
 * Task: 4.5
 * Requirements: 5.1-5.5
 *
 * 功能：
 * - 验资核对表格: 出资人|认缴|实缴|验资金额|差异[公式]|出资到位率[公式]|验资机构
 * - 公式: calcVerifyDiff(实缴-验资), calcPaidInRate(实缴/认缴)
 * - 红色高亮|差异>阈值, 黄色提示|到位率<100%
 * - 核对清单 (8 check items with status radio: pass/fail/pending/na)
 * - 审计结论区 (el-card包裹)
 * - 5个AI辅助 section buttons
 * - Uses useM2CapitalCheck + useM2VerifyEngine + useM2FormData
 */
import { computed, inject, onMounted } from 'vue'
import { Plus, MagicStick, Check } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import { useM2FormData } from '../../composables/useM2FormData'
import {
  useM2CapitalCheck,
  CHECK_STATUS_OPTIONS,
  VERIFY_DIFF_THRESHOLD,
} from '../../composables/useM2CapitalCheck'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── Composables ─────────────────────────────────────────────────────────────

const formData = useM2FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const {
  computedVerifyRows,
  totalSubscribed,
  totalPaid,
  totalVerified,
  totalVerifyDiff,
  overallPaidInRate,
  isDiffOverThreshold,
  isPaidInRateBelowFull,
  addVerifyRow,
  removeVerifyRow,
  updateVerifyRow,
  checkItems,
  completionRate,
  isAllChecked,
  failedCount,
  updateCheckStatus,
  updateCheckRemark,
  aiSections,
  updateAiSectionContent,
  conclusion,
  updateConclusion,
} = useM2CapitalCheck(formData)

// ─── Handlers ────────────────────────────────────────────────────────────────

async function handleAddVerifyRow(): Promise<void> {
  try {
    const { value: name } = await ElMessageBox.prompt(
      '请输入出资人名称',
      '新增出资人',
      { confirmButtonText: '确定', cancelButtonText: '取消', inputPlaceholder: '如：张三 / ABC公司' },
    )
    if (!name?.trim()) return
    addVerifyRow(name.trim())
  } catch {
    // 用户取消
  }
}

function handleAI(_section: string): void { /* AI辅助待集成 */ }
function handleReview(): void { openReviewDialog?.('M2-5-capital-check', '实收资本检查表') }

// ─── Format ──────────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return `${(val * 100).toFixed(1)}%`
}

// ─── Init ────────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
})
</script>

<style scoped>
.m2-tab-capital-check { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }
.check-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.diff-alert-red { color: #f56c6c !important; font-weight: 700; }
.rate-alert-yellow { color: #e6a23c !important; font-weight: 600; }
.rate-ok { color: #67c23a; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.summary-bar { display: flex; gap: 20px; padding: 10px 16px; margin-top: 12px; background: #f5f7fa; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; flex-wrap: wrap; }
.checklist-items { display: flex; flex-direction: column; gap: 12px; }
.checklist-row { border: 1px solid #ebeef5; border-radius: 6px; padding: 10px 14px; }
.checklist-row-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.checklist-title { font-size: var(--wp-font-size, 13px); font-weight: 500; color: #303133; }
.checklist-remark { margin-top: 8px; }
.conclusion-card :deep(.el-form-item__label) { font-weight: 500; color: #303133; }
.ai-section { opacity: 0.9; }
.m2-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.m2-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.m2-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
