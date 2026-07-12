<template>
  <div class="s10-internal-control">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：了解并评价环境事项相关的内部控制设计与运行有效性，识别环境合规、环境负债确认与披露相关的重大错报风险。"
      style="margin-bottom: 16px"
    />

    <!-- ═══ 内部控制调查表 S10-2（环境事项相关） ═══ -->
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>内部控制调查表 S10-2 — 环境事项相关</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              type="primary"
              :loading="saving"
              @click="handleSave"
            >保存</el-button>
            <el-button size="small" @click="handleOpenReview('s10-internal-control', '内控调查表S10-2')">
              复核
            </el-button>
            <el-button v-if="!isReadonly" size="small" @click="handleAiAssist">
              🤖 AI辅助
            </el-button>
          </div>
        </div>
      </template>

      <!-- 编制提示（折叠） -->
      <details class="compile-hint">
        <summary>编制提示</summary>
        <div class="methodology-context">
          <p>本调查表用于了解被审计单位与环境事项相关的内部控制设计与运行情况。</p>
          <p>审计人员应针对每项控制活动评价其设计有效性（"是"/"弱"/"否"/"不适用"），并记录相关审计证据。</p>
          <p>对于评价为"弱"或"否"的项目，应进一步分析控制缺陷对财务报表的潜在影响（如环境负债低估、或有事项未披露等）。</p>
        </div>
      </details>

      <!-- 调查表表格 -->
      <el-table
        :data="checklistRows"
        border
        size="small"
        style="width: 100%; font-size: 13px"
        row-key="id"
        :cell-class-name="cellClassName"
      >
        <!-- 序号列 -->
        <el-table-column type="index" label="序号" width="55" align="center" />

        <!-- 控制项目/内容描述 -->
        <el-table-column prop="controlItem" label="控制活动/调查事项" min-width="300">
          <template #default="{ row }">
            <span class="control-item-text">{{ row.controlItem }}</span>
          </template>
        </el-table-column>

        <!-- 评价：是/弱/否/不适用 — 四选一 radio -->
        <el-table-column label="是" width="60" align="center">
          <template #default="{ row }">
            <el-radio
              v-model="row.rating"
              label="yes"
              :disabled="isReadonly"
              @change="onRatingChange(row)"
            >&nbsp;</el-radio>
          </template>
        </el-table-column>
        <el-table-column label="弱" width="60" align="center">
          <template #default="{ row }">
            <el-radio
              v-model="row.rating"
              label="weak"
              :disabled="isReadonly"
              @change="onRatingChange(row)"
            >&nbsp;</el-radio>
          </template>
        </el-table-column>
        <el-table-column label="否" width="60" align="center">
          <template #default="{ row }">
            <el-radio
              v-model="row.rating"
              label="no"
              :disabled="isReadonly"
              @change="onRatingChange(row)"
            >&nbsp;</el-radio>
          </template>
        </el-table-column>
        <el-table-column label="不适用" width="80" align="center">
          <template #default="{ row }">
            <el-radio
              v-model="row.rating"
              label="na"
              :disabled="isReadonly"
              @change="onRatingChange(row)"
            >&nbsp;</el-radio>
          </template>
        </el-table-column>

        <!-- 备注/审计证据 -->
        <el-table-column prop="evidence" label="备注/审计证据" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.evidence"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              placeholder="记录审计证据或备注"
              @change="markDirty"
            />
            <span v-else>{{ row.evidence || '—' }}</span>
          </template>
        </el-table-column>

        <!-- 索引号 -->
        <el-table-column prop="indexRef" label="索引号" width="100" align="center">
          <template #default="{ row }">
            <GtIndexChip v-if="row.indexRef" :value="row.indexRef" />
            <span v-else class="text-placeholder">—</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 汇总统计 -->
      <div class="control-summary">
        <el-tag type="success" size="small">是：{{ ratingCounts.yes }}</el-tag>
        <el-tag type="warning" size="small">弱：{{ ratingCounts.weak }}</el-tag>
        <el-tag type="danger" size="small">否：{{ ratingCounts.no }}</el-tag>
        <el-tag type="info" size="small">不适用：{{ ratingCounts.na }}</el-tag>
        <el-tag size="small">未评价：{{ ratingCounts.pending }}</el-tag>
      </div>
    </el-card>

    <!-- ═══ 审计结论区 ═══ -->
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>内控调查结论</span>
          <div class="header-actions">
            <el-button v-if="!isReadonly" size="small" @click="handleAiConclusion">🤖 AI辅助</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="根据上述内部控制调查结果，对环境事项相关内部控制的整体评价..."
        @change="markDirty"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * S10InternalControlSheet.vue — S10-2 环境事项相关内部控制调查表
 *
 * 功能：
 * - 64×8 检查表结构，每行一个控制活动评价项
 * - 四选一评价（是/弱/否/不适用）使用 radio 点选交互
 * - 备注/审计证据列支持文本输入
 * - 索引号使用 GtIndexChip 呈现跨底稿引用
 * - 汇总统计（各评价等级计数）
 * - readonly 禁止编辑
 * - 13px 字体 + AI 辅助按钮
 *
 * 环境内控检查要点：排放监测、废物处理、环境合规、污染防治、
 * 环境应急响应、环保投入管理等。
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 5.2
 * Requirements: 7.2, 7.3
 */
import { ref, computed, inject, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

// ─── 组件导入 ────────────────────────────────────────────────────────────────

import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

// ─── 复核对话 inject ─────────────────────────────────────────────────────────

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>(
  'openReviewDialog',
  () => {}
)

function handleOpenReview(sectionId: string, sectionLabel: string) {
  openReviewDialog(sectionId, sectionLabel)
}

// ─── 数据模型 ────────────────────────────────────────────────────────────────

interface ChecklistRow {
  id: string
  controlItem: string
  rating: '' | 'yes' | 'weak' | 'no' | 'na'
  evidence: string
  indexRef: string
}

const checklistRows = ref<ChecklistRow[]>([])
const conclusion = ref('')
const saving = ref(false)
const isDirty = ref(false)

// ─── S10-2 默认检查项目（环境事项内部控制典型检查事项） ─────────────────────

const DEFAULT_CHECKLIST_ITEMS = [
  '被审计单位是否建立了环境管理体系（如 ISO 14001）并有效运行',
  '是否设有专门的环境管理部门或指定环境管理责任人',
  '是否定期进行污染物排放监测（废气、废水、噪声等），并保留监测记录',
  '废水排放是否安装在线监控设施并与环保部门联网',
  '废气排放是否安装烟气在线监测系统（CEMS）并定期校准维护',
  '固体废物（一般工业固废和危险废物）的产生、贮存、运输、处置是否建立台账管理',
  '危险废物是否交由具备资质的单位处理，并签订委托处置协议',
  '是否建立环境事故应急预案并定期组织演练',
  '环保设施（污水处理站、除尘设备、脱硫脱硝装置等）是否正常运行并定期维护',
  '是否按期缴纳排污许可证规定的排放费/环境保护税',
  '环保投入（设备更新、技术改造、修复治理等）是否纳入年度预算管理',
  '是否定期开展环境影响评价或环境风险评估',
  '新建、改扩建项目是否完成环境影响评价审批和竣工环保验收（"三同时"制度）',
  '是否建立环境合规性自查制度，定期检查各环保法规、标准的执行情况',
  '环境相关的行政处罚、诉讼、纠纷是否及时上报管理层并记录',
  '对环境负债（场地修复义务、弃置费用等）是否建立了识别和计量机制',
  '碳排放配额和碳交易（如适用）是否有完善的管理控制和会计核算',
  '环境信息披露（年报/ESG 报告）的编制流程是否受内部控制覆盖',
]

// ─── 评价统计 ────────────────────────────────────────────────────────────────

const ratingCounts = computed(() => {
  const counts = { yes: 0, weak: 0, no: 0, na: 0, pending: 0 }
  for (const row of checklistRows.value) {
    if (row.rating === 'yes') counts.yes++
    else if (row.rating === 'weak') counts.weak++
    else if (row.rating === 'no') counts.no++
    else if (row.rating === 'na') counts.na++
    else counts.pending++
  }
  return counts
})

// ─── 事件处理 ────────────────────────────────────────────────────────────────

function onRatingChange(_row: ChecklistRow) {
  markDirty()
}

function markDirty() {
  isDirty.value = true
}

function cellClassName({ column }: any) {
  if (['是', '弱', '否', '不适用'].includes(column.label)) {
    return 'rating-cell'
  }
  return ''
}

// ─── AI 辅助 ─────────────────────────────────────────────────────────────────

function handleAiAssist() {
  ElMessage.info('AI辅助功能开发中，将基于被审计单位的行业特征和环境风险自动推荐关注要点')
}

function handleAiConclusion() {
  ElMessage.info('AI将根据评价结果自动生成内控调查结论')
}

// ─── 保存 ────────────────────────────────────────────────────────────────────

async function handleSave() {
  if (saving.value) return
  saving.value = true
  try {
    const payload = {
      checklist_rows: checklistRows.value.map(r => ({
        id: r.id,
        control_item: r.controlItem,
        rating: r.rating,
        evidence: r.evidence,
        index_ref: r.indexRef,
      })),
      conclusion: conclusion.value,
    }
    await http.put(
      `/api/workpapers/${props.wpId}/checklist-responses`,
      { sheet_name: '内部控制调查表S10-2', data: payload }
    )
    isDirty.value = false
    ElMessage.success('内控调查表已保存')
  } catch (err: any) {
    ElMessage.error(`保存失败：${err?.message || '未知错误'}`)
  } finally {
    saving.value = false
  }
}

// ─── 数据加载 ────────────────────────────────────────────────────────────────

async function loadData() {
  try {
    const res = await http.get(
      `/api/workpapers/${props.wpId}/render-config`,
      { _silent: true } as any
    )
    const sheets = res?.data?.sheets || res?.sheets || []
    const sheet = sheets.find((s: any) =>
      s.sheet_name?.includes('内控调查表S10') || s.sheet_name?.includes('S10-2')
    )
    const htmlData = sheet?.html_data

    if (htmlData?.checklist_rows?.length) {
      checklistRows.value = htmlData.checklist_rows.map((r: any, idx: number) => ({
        id: r.id || `s10-2-${idx}`,
        controlItem: r.control_item || r.controlItem || '',
        rating: r.rating || '',
        evidence: r.evidence || '',
        indexRef: r.index_ref || r.indexRef || '',
      }))
    } else {
      // 使用默认检查项初始化
      checklistRows.value = DEFAULT_CHECKLIST_ITEMS.map((item, idx) => ({
        id: `s10-2-${idx}`,
        controlItem: item,
        rating: '' as const,
        evidence: '',
        indexRef: '',
      }))
    }

    if (htmlData?.conclusion) {
      conclusion.value = htmlData.conclusion
    }
  } catch (err) {
    // 降级：使用默认检查项
    checklistRows.value = DEFAULT_CHECKLIST_ITEMS.map((item, idx) => ({
      id: `s10-2-${idx}`,
      controlItem: item,
      rating: '' as const,
      evidence: '',
      indexRef: '',
    }))
  }
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.s10-internal-control {
  padding: 12px;
}

.audit-section {
  margin-bottom: 16px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.compile-hint {
  margin-bottom: 12px;
  font-size: var(--wp-font-size, 13px);
}

.compile-hint summary {
  cursor: pointer;
  color: #909399;
  font-size: 12px;
  margin-bottom: 8px;
}

.methodology-context {
  padding: 10px 14px;
  border-left: 4px solid #e6a23c;
  background-color: #fdf6ec;
  font-size: var(--wp-font-size, 13px);
  line-height: 1.7;
  color: #606266;
}

.methodology-context p {
  margin: 4px 0;
}

.control-item-text {
  font-size: var(--wp-font-size, 13px);
  line-height: 1.6;
}

.control-summary {
  margin-top: 12px;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.text-placeholder {
  color: #c0c4cc;
}

:deep(.rating-cell) {
  text-align: center;
}

:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}

:deep(.el-radio__label) {
  display: none;
}
</style>
