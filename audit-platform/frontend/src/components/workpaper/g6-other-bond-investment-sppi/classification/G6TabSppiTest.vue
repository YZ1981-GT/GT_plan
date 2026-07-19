<template>
  <div class="g6-tab-sppi-test">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：评估其他债权投资合同现金流量特征是否仅为对本金和以未偿付本金为基础的利息的支付（SPPI），支持金融资产分类结论的恰当性。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:G6-8" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ totalRows }} 项检查</el-tag>
    </div>

    <!-- ═══ 顶部方法论上下文（琥珀色） ═══ -->
    <div class="methodology-banner">
      <div class="methodology-text">
        <strong>SPPI = 仅为对本金和利息的支付</strong>（Solely Payments of Principal and Interest）。
        合同现金流量特征分析旨在评估金融资产的合同条款是否引起在特定日期产生的现金流量，且该现金流量仅为对本金和以未偿付本金金额为基础的利息的支付。
      </div>
    </div>

    <!-- ═══ 六Section逐一渲染 ═══ -->
    <div
      v-for="section in sections"
      :key="section.id"
      class="sppi-section"
      :class="{ 'section-failed': section.sectionConclusion === 'fail' }"
    >
      <!-- Section标题行 -->
      <div class="section-header">
        <h3
          class="section-title"
          :class="{ 'title-failed': section.sectionConclusion === 'fail' }"
        >
          {{ section.title }}
        </h3>
        <div class="section-actions">
          <el-tag
            v-if="section.sectionConclusion === 'pass'"
            type="success"
            size="small"
            effect="plain"
          >通过</el-tag>
          <el-tag
            v-else-if="section.sectionConclusion === 'fail'"
            type="danger"
            size="small"
            effect="dark"
          >不通过</el-tag>
          <el-tag
            v-else-if="section.sectionConclusion === 'na'"
            type="info"
            size="small"
            effect="plain"
          >不适用</el-tag>
          <el-button
            size="small"
            :icon="ChatDotRound"
            @click="handleReview(`G6-8-${section.id}`)"
          >复核</el-button>
        </div>
      </div>

      <!-- Section方法论 -->
      <div class="section-methodology">
        {{ getSectionMethodology(section.id) }}
      </div>

      <!-- Section表格 (每section一张el-table, v-memo优化) -->
      <el-table
        v-memo="[section.items, readonly]"
        :data="section.items"
        border
        stripe
        size="small"
        :max-height="section.items.length > 12 ? 480 : undefined"
        class="sppi-table"
      >
        <el-table-column label="序号" width="50" align="center">
          <template #default="{ $index }">
            {{ $index + 1 }}
          </template>
        </el-table-column>

        <el-table-column label="检查区域" min-width="100" prop="checkArea">
          <template #default="{ row }">
            <span class="cell-text">{{ row.checkArea }}</span>
          </template>
        </el-table-column>

        <el-table-column label="检查项目" min-width="200">
          <template #default="{ row }">
            <span class="cell-text">{{ row.checkItem }}</span>
          </template>
        </el-table-column>

        <el-table-column label="CAS要求" min-width="200">
          <template #default="{ row }">
            <div class="cas-requirement">{{ row.casRequirement }}</div>
          </template>
        </el-table-column>

        <el-table-column label="合同条款摘要" min-width="200">
          <template #default="{ row }">
            <el-input
              v-model="row.contractTermSummary"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              size="small"
              :disabled="readonly"
              placeholder="摘录合同关键条款..."
              @change="handleItemUpdate(section.id, row.id, 'contractTermSummary', row.contractTermSummary)"
            />
          </template>
        </el-table-column>

        <el-table-column label="是否满足SPPI" width="120" align="center">
          <template #default="{ row }">
            <el-select
              v-model="row.isSPPISatisfied"
              size="small"
              :disabled="readonly"
              placeholder="--"
              clearable
              @change="handleItemUpdate(section.id, row.id, 'isSPPISatisfied', row.isSPPISatisfied)"
            >
              <el-option label="是" value="yes" />
              <el-option label="否" value="no" />
              <el-option label="不适用" value="na" />
            </el-select>
          </template>
        </el-table-column>

        <el-table-column label="判断依据" min-width="200">
          <template #default="{ row }">
            <el-input
              v-model="row.judgmentBasis"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              size="small"
              :disabled="readonly"
              placeholder="说明判断理由..."
              @change="handleItemUpdate(section.id, row.id, 'judgmentBasis', row.judgmentBasis)"
            />
          </template>
        </el-table-column>

        <el-table-column label="风险等级" width="90" align="center">
          <template #default="{ row }">
            <el-select
              v-model="row.riskLevel"
              size="small"
              :disabled="readonly"
              placeholder="--"
              clearable
              @change="handleItemUpdate(section.id, row.id, 'riskLevel', row.riskLevel)"
            >
              <el-option label="高" value="high" />
              <el-option label="中" value="medium" />
              <el-option label="低" value="low" />
            </el-select>
          </template>
        </el-table-column>

        <el-table-column label="索引" width="80">
          <template #default="{ row }">
            <el-input
              v-model="row.indexRef"
              size="small"
              :disabled="readonly"
              placeholder="索引"
              @change="handleItemUpdate(section.id, row.id, 'indexRef', row.indexRef)"
            />
          </template>
        </el-table-column>

        <el-table-column label="备注" min-width="150">
          <template #default="{ row }">
            <el-input
              v-model="row.remark"
              size="small"
              :disabled="readonly"
              placeholder="备注"
              @change="handleItemUpdate(section.id, row.id, 'remark', row.remark)"
            />
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ═══ 综合结论区 ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="conclusion-header">
          <span class="conclusion-title">综合结论</span>
          <el-tag
            v-if="overallConclusion === 'pass'"
            type="success"
            effect="dark"
          >满足SPPI</el-tag>
          <el-tag
            v-else-if="overallConclusion === 'fail'"
            type="danger"
            effect="dark"
          >不满足SPPI</el-tag>
          <el-tag
            v-else
            type="info"
            effect="plain"
          >待完成</el-tag>
        </div>
      </template>

      <!-- 红色警告横幅 -->
      <el-alert
        v-if="hasFailedSection"
        title="不满足SPPI条件，该金融资产需重新分类"
        type="error"
        :closable="false"
        show-icon
        class="fail-alert"
      />

      <!-- 证据完整性闸门 -->
      <el-alert
        v-else-if="!evidenceComplete && answeredWithoutFail"
        title="已作答项须补全合同条款摘要与判断依据后，方可给出「满足SPPI」综合结论；判定为否或高风险项还需填写索引。"
        type="warning"
        :closable="false"
        show-icon
        class="fail-alert"
      />

      <!-- 失败section列表 -->
      <div v-if="failedSections.length > 0" class="failed-sections-list">
        <span class="failed-label">不通过section：</span>
        <el-tag
          v-for="fs in failedSections"
          :key="fs.id"
          type="danger"
          size="small"
          effect="plain"
          class="failed-tag"
        >{{ fs.title }}</el-tag>
      </div>

      <!-- 证据缺口列表（最多展示 6 条） -->
      <div v-if="evidenceGaps.length > 0 && !hasFailedSection" class="failed-sections-list">
        <span class="failed-label">待补证据：</span>
        <el-tag
          v-for="gap in evidenceGaps.slice(0, 6)"
          :key="gap.itemId"
          type="warning"
          size="small"
          effect="plain"
          class="failed-tag"
        >{{ gap.checkItem.slice(0, 28) }}{{ gap.checkItem.length > 28 ? '…' : '' }}</el-tag>
        <span v-if="evidenceGaps.length > 6" class="failed-label">等 {{ evidenceGaps.length }} 项</span>
      </div>

      <!-- 总行数统计 -->
      <div class="total-rows-info">
        共 {{ totalRows }} 项检查 · {{ completedCount }} 项已完成 · {{ pendingCount }} 项待填
        <template v-if="evidenceGaps.length"> · {{ evidenceGaps.length }} 项缺证据</template>
      </div>
    </el-card>

    <!-- ═══ 审计说明 ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="conclusion-header"><span class="conclusion-title">审计说明</span></div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="readonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述 SPPI 各测试项的执行情况及结果、合同条款分析与判断依据、拟调整与未调整事项及其影响。"
        @update:model-value="saveAuditNote"
      />
    </el-card>

    <!-- ═══ 审计结论 ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="conclusion-header">
          <span class="conclusion-title">审计结论</span>
          <el-button
            size="small"
            :disabled="readonly || aiLoading"
            :loading="aiLoading"
            @click="handleAi"
          >✨ AI辅助</el-button>
        </div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="readonly"
        :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：说明其他债权投资是否满足 SPPI 条件及对分类结论的支持；如不满足，说明重分类处理。"
        @update:model-value="saveAuditConclusion"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="guidance-details">
      <summary>编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表用于分析金融资产的合同现金流量特征是否仅为对本金和利息的支付（SPPI测试）。</p>
        <p>2. 六个section分别评估本金定义、利息定义、修改时间价值、提前还款条款、合同关联工具及综合判断。</p>
        <p>3. 「检查项目」均为合规陈述：「是否满足SPPI」选「是」表示本项满足，「否」表示不满足，「不适用」表示与合同无关。</p>
        <p>4. 「CAS要求」列为只读方法论参考，「合同条款摘要」列摘录被审计单位合同关键条款；已作答项须同时填写判断依据。</p>
        <p>5. 任一项选「否」将导致该section结论自动判定为「不通过」；判定为否或高风险项还需填写索引。</p>
        <p>6. 任一section不通过将触发红色高亮提示，表明该金融资产不满足SPPI条件，需重新分类。</p>
        <p>7. 审计结论可使用 AI 辅助生成初稿（基于失败项与判断依据），人工复核后确认。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G6TabSppiTest.vue — G6-8 合同现金流量特征分析（SPPI测试，80行六section）
 *
 * Spec: .kiro/specs/g6-other-bond-investment-sppi/ Task 8.2
 * Requirements: 5.1, 5.2, 5.3, 5.4, 5.5
 *
 * 功能：
 * - 顶部方法论上下文（琥珀色: SPPI定义）
 * - 六section: (一)本金定义/(二)利息定义/(三)修改时间价值/(四)提前还款条款/(五)合同关联工具/(六)综合判断
 * - 每section el-table渲染10列（v-memo优化性能）
 * - 任一section FAIL → 红色高亮section标题 + 底部"不满足SPPI，需重分类"提示
 * - 每section标题行AI辅助按钮 + 复核按钮 + 综合结论区 + 编制提示
 */
import { inject, computed, ref, watch, onMounted } from 'vue'
import { ChatDotRound } from '@element-plus/icons-vue'
import { useG6SppiTest } from '../../composables/useG6SppiTest'
import type { SppiTestData, SppiItem } from '../../composables/useG6SppiTest'
import { useG6SppiFormData } from '../../composables/useG6SppiFormData'
import { useG6SppiAiGenerate } from '../../composables/useG6SppiAiGenerate'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  htmlData: Record<string, any> | null
  isReadonly: boolean
  wpId: string
  projectId: string
}>()

const emit = defineEmits<{
  (e: 'update', data: SppiTestData): void
}>()

// 模板中以 `readonly` 绑定 :disabled，映射到父级传入的 is-readonly
const readonly = computed(() => props.isReadonly)

// ─── 复核对话 inject ────────────────────────────────────────────────────────
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog')
function handleReview(sectionId: string): void {
  openReviewDialog?.(sectionId)
}

// ─── useG6SppiTest composable ──────────────────────────────────────────────
const {
  sections,
  overallConclusion,
  hasFailedSection,
  failedSections,
  evidenceGaps,
  evidenceComplete,
  failedItemSummaries,
  totalRows,
  updateItem,
  loadData,
  toJSON,
  getSectionMethodology,
} = useG6SppiTest()

// ─── 数据层（自加载/保存，对齐同组其他 tab） ──────────────────────────────
const formData = useG6SppiFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const wpIdRef = computed(() => props.wpId)
const { generateAndConfirm, loading: aiLoading } = useG6SppiAiGenerate(wpIdRef)

const SPPI_ITEM_ID = 'G6-8-sppi-test-data'

// ─── 审计说明 / 审计结论（独立持久化 checklist_responses） ─────────────────
const NOTE_KEY = 'G6-8-sppi-test-audit-note'
const CONCLUSION_KEY = 'G6-8-sppi-test-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  formData.debouncedSave(NOTE_KEY, { remark: val })
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  formData.debouncedSave(CONCLUSION_KEY, { remark: val })
}

async function handleAi(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'sppi-conclusion',
    auditConclusion.value || '',
    {
      overallConclusion: overallConclusion.value,
      hasFailedSection: hasFailedSection.value,
      failedSections: failedSections.value.map((s) => s.title),
      totalRows: totalRows.value,
      evidenceGapCount: evidenceGaps.value.length,
      failedItems: failedItemSummaries.value.slice(0, 20),
      evidenceGapsSample: evidenceGaps.value.slice(0, 10).map((g) => ({
        section: g.sectionTitle,
        item: g.checkItem,
        missing: g.missing.join(','),
      })),
      sectionConclusions: sections.value.map((s) => ({
        id: s.id,
        title: s.title,
        conclusion: s.sectionConclusion,
      })),
    },
    'AI SPPI 审计结论',
  )
  if (text) saveAuditConclusion(text)
}

/** 已作答且尚无 fail section（用于证据闸门提示） */
const answeredWithoutFail = computed(() => {
  if (hasFailedSection.value) return false
  return sections.value.some((s) =>
    s.items.some((i) => i.isSPPISatisfied === 'yes' || i.isSPPISatisfied === 'no'),
  )
})

// ─── 加载数据 ──────────────────────────────────────────────────────────────
onMounted(async () => {
  await formData.loadAll()
  initFromData()
  const noteResp = formData.allResponses.value.get(NOTE_KEY)
  if (noteResp?.remark) auditNote.value = noteResp.remark
  const concResp = formData.allResponses.value.get(CONCLUSION_KEY)
  if (concResp?.remark) auditConclusion.value = concResp.remark
})

watch(() => props.htmlData, () => {
  initFromData()
})

function initFromData(): void {
  // 优先从已保存的 checklist-response 读取
  const saved = formData.allResponses.value.get(SPPI_ITEM_ID)
  if (saved?.conclusion) {
    try {
      const parsed = JSON.parse(saved.conclusion) as SppiTestData
      if (parsed?.sections?.length) {
        loadData(parsed)
        return
      }
    } catch { /* ignore parse error */ }
  }
  // 其次从 render-config 解析内容
  const content = formData.parseContent()
  if (content.sppiTest && (content.sppiTest as any).sections) {
    loadData(content.sppiTest as SppiTestData)
  } else {
    loadData(null)
  }
}

// ─── 持久化（debounce 保存到 checklist-responses） ──────────────────────────
function persist(): void {
  formData.debouncedSave(SPPI_ITEM_ID, {
    conclusion: JSON.stringify(toJSON()),
  })
}

// ─── 完成度统计 ─────────────────────────────────────────────────────────────
const completedCount = computed(() => {
  let count = 0
  for (const section of sections.value) {
    for (const item of section.items) {
      if (item.isSPPISatisfied !== null) count++
    }
  }
  return count
})

const pendingCount = computed(() => totalRows.value - completedCount.value)

// ─── Item更新处理 ───────────────────────────────────────────────────────────
function handleItemUpdate(sectionId: string, itemId: string, field: keyof SppiItem, value: any): void {
  updateItem(sectionId, itemId, field, value)
  persist()
  // 兼容：向上通知父组件
  emit('update', toJSON())
}

// ─── 监听结论变化：持久化 + 向上通知 ────────────────────────────────────────
watch(
  () => sections.value.map(s => s.sectionConclusion),
  () => {
    persist()
    emit('update', toJSON())
  },
)
</script>

<style scoped>
.g6-tab-sppi-test {
  font-size: var(--wp-font-size, 13px);
  padding: 8px 0;
}

/* ═══ 审计目标 / 工具栏 ═══ */
.objective-alert {
  margin-bottom: 12px;
}
.tab-toolbar {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 6px;
  margin-bottom: 12px;
}
.chip-wrap {
  display: inline-flex;
  align-items: center;
}
.audit-note-card {
  margin: 16px 0;
}

/* ═══ 方法论横幅(琥珀色) ═══ */
.methodology-banner {
  background: #fffbe6;
  border-left: 4px solid #e6a23c;
  padding: 12px 16px;
  margin-bottom: 20px;
  border-radius: 4px;
}
.methodology-text {
  font-size: var(--wp-font-size, 13px);
  line-height: 1.6;
  color: #8b6914;
}
.methodology-text strong {
  color: #b86e00;
}

/* ═══ Section区块 ═══ */
.sppi-section {
  margin-bottom: 24px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 12px;
  transition: border-color 0.3s;
}
.sppi-section.section-failed {
  border-color: #f56c6c;
  background: #fef0f0;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.section-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.section-title.title-failed {
  color: #f56c6c;
  background: #fde2e2;
  padding: 2px 8px;
  border-radius: 3px;
}
.section-actions {
  display: flex;
  gap: 6px;
  align-items: center;
}

/* Section方法论 */
.section-methodology {
  background: #fdf6ec;
  border-left: 3px solid #e6a23c;
  padding: 6px 12px;
  margin-bottom: 10px;
  font-size: 12px;
  line-height: 1.5;
  color: #8b6914;
  border-radius: 2px;
}

/* ═══ 表格 ═══ */
.sppi-table {
  margin-bottom: 4px;
}
.sppi-table :deep(.el-table__header th) {
  font-size: 12px;
  font-weight: 600;
  background: #f5f7fa;
}
.sppi-table :deep(.el-table__body td) {
  font-size: var(--wp-font-size, 13px);
}

.cell-text {
  font-size: 12px;
  color: #606266;
  line-height: 1.4;
}

/* CAS要求列(只读灰色背景) */
.cas-requirement {
  background: #f5f7fa;
  padding: 4px 8px;
  border-radius: 3px;
  font-size: 11px;
  line-height: 1.4;
  color: #909399;
}

/* ═══ 综合结论区 ═══ */
.conclusion-card {
  margin: 20px 0 16px;
}
.conclusion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.conclusion-title {
  font-size: 14px;
  font-weight: 600;
}
.conclusion-card :deep(.el-card__header) {
  padding: 10px 16px;
}

.fail-alert {
  margin-bottom: 12px;
}

.failed-sections-list {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}
.failed-label {
  font-size: 12px;
  color: #909399;
}
.failed-tag {
  margin: 0;
}

.total-rows-info {
  font-size: 12px;
  color: #909399;
  margin-top: 8px;
}

/* ═══ 编制提示 ═══ */
.guidance-details {
  margin-top: 16px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #606266;
}
.guidance-content {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
  line-height: 1.8;
}
.guidance-content p {
  margin: 0;
}
</style>
