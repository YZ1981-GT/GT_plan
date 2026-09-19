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
      <div class="toolbar-left">
        <el-button
          v-if="!readonly"
          size="small"
          type="success"
          plain
          :loading="syncing"
          @click="syncFromMain"
        >
          从 G6-2 同步项目
        </el-button>
        <el-button
          v-if="!readonly"
          size="small"
          @click="addProject"
        >
          新增项目
        </el-button>
        <el-button
          v-if="!readonly && instruments.length > 1"
          size="small"
          type="danger"
          plain
          @click="removeCurrentProject"
        >
          删除当前项目
        </el-button>
      </div>
      <div class="toolbar-right">
        <G6SppiImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          sheet="G6-8"
          :disabled="readonly"
          @imported="onImported"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:G6-8" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">{{ instruments.length }} 个项目 · {{ totalRows }} 项检查</el-tag>
      </div>
    </div>

    <!-- 投资项目切换 -->
    <div class="instrument-bar">
      <el-radio-group
        :model-value="activeInstrumentId || undefined"
        size="small"
        @update:model-value="(id: string) => setActiveInstrument(id)"
      >
        <el-radio-button
          v-for="inst in instruments"
          :key="inst.id"
          :value="inst.id"
        >
          <span
            :class="{
              'inst-fail': inst.overallConclusion === 'fail',
              'inst-pass': inst.overallConclusion === 'pass',
            }"
          >{{ inst.name || '未命名' }}</span>
        </el-radio-button>
      </el-radio-group>
      <div v-if="activeInstrument" class="instrument-meta">
        <el-input
          :model-value="activeInstrument.name"
          size="small"
          :disabled="readonly"
          placeholder="投资项目名称"
          style="width: 240px"
          @update:model-value="(v: string) => updateInstrumentName(activeInstrument!.id, v)"
          @change="persist"
        />
        <el-tag
          v-if="activeOverallConclusion === 'pass'"
          type="success"
          size="small"
          effect="plain"
        >本项目：满足</el-tag>
        <el-tag
          v-else-if="activeOverallConclusion === 'fail'"
          type="danger"
          size="small"
          effect="plain"
        >本项目：不满足</el-tag>
        <el-tag v-else type="info" size="small" effect="plain">本项目：待完成</el-tag>
      </div>
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

        <el-table-column label="索引" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="!readonly"
              v-model="row.indexRef"
              size="small"
              placeholder="索引"
              @change="handleItemUpdate(section.id, row.id, 'indexRef', row.indexRef)"
            />
            <span v-else-if="!row.indexRef">-</span>
            <div v-if="row.indexRef" class="row-index-chip">
              <GtIndexChip :value="row.indexRef" :context-project-id="projectId" />
            </div>
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
          >全部项目满足SPPI</el-tag>
          <el-tag
            v-else-if="overallConclusion === 'fail'"
            type="danger"
            effect="dark"
          >存在项目不满足SPPI</el-tag>
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

      <!-- G6-7 业务模式交叉一致性（与 G6-7 对称） -->
      <div v-if="crossCheck.level" class="cross-check-alert">
        <el-alert
          :title="crossCheckTitle"
          :type="crossCheckAlertType"
          :closable="false"
          show-icon
        >
          <template #default>
            <span>{{ crossCheck.message }}</span>
          </template>
        </el-alert>
      </div>
      <div v-else-if="!businessModelConclusion" class="cross-check-alert">
        <el-alert
          title="尚未读取到 G6-7 业务模式最终结论；完成 G6-7 后将自动交叉提示分类影响。"
          type="info"
          :closable="false"
          show-icon
        />
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
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. <b>编制目的</b>：按投资项目/合同测试现金流量是否仅为本金及未偿付本金之利息（SPPI），支持分类结论。</p>
        <p>2. <b>建议顺序</b>：G6-2 维护项目清单 →「从 G6-2 同步项目」→ 逐项目完成六节检查 → 与 G6-7 业务模式交叉核对预期分类。</p>
        <p>3. 六个 section：本金定义／利息定义／修改时间价值／提前还款／合同关联工具／综合判断；「是否满足SPPI」选「是/否/不适用」。</p>
        <p>4. 已作答项须填合同条款摘要与判断依据；判定「否」或高风险项须填证据索引（合同原文页码、法律意见等）。</p>
        <p>5. 任一项目任一项选「否」→ 该项目及整体不通过，并提示需重分类（通常不再适用 FVOCI-Debt）。</p>
        <p>6. 完成 G6-7 后查看交叉提示中的预期分类；与本表结论冲突时先复核合同条款与业务模式证据，再写审计结论。</p>
        <p>7. 支持 Excel 扁平行导入导出（投资项目×检查项）；结论可通过 AI 辅助初稿，但须人工确认后保存。</p>
        <p>8. 分类结果影响后续 G6-5/G6-6/G6-11~14 及附注表述；变更结论后应通知复核人并核对 G6-1 顶部分类摘要。</p>
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
import { inject, computed, ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { ChatDotRound } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useG6SppiTest } from '../../composables/useG6SppiTest'
import type { SppiTestData, SppiItem } from '../../composables/useG6SppiTest'
import {
  evaluateG67G68Consistency,
  buildG6ClassificationSummary,
  type BusinessModelConclusion,
} from '../../composables/useG6SppiBusinessModel'
import { useG6SppiFormData } from '../../composables/useG6SppiFormData'
import { useG6SppiAiGenerate } from '../../composables/useG6SppiAiGenerate'
import {
  parseG6ChecklistPayload,
  writeG6ClassificationSummary,
  fetchG62DetailRows,
  mapG62RowsToSppiSeeds,
} from '../../composables/g6CrossHelpers'
import GtIndexChip from '../../GtIndexChip.vue'
import G6SppiImportExportDropdown from '../G6SppiImportExportDropdown.vue'

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
  instruments,
  activeInstrumentId,
  activeInstrument,
  sections,
  overallConclusion,
  activeOverallConclusion,
  hasFailedSection,
  failedSections,
  evidenceGaps,
  evidenceComplete,
  failedItemSummaries,
  totalRows,
  updateItem,
  setActiveInstrument,
  updateInstrumentName,
  addInstrument,
  removeInstrument,
  syncFromSeeds,
  loadData,
  toJSON,
  getSectionMethodology,
} = useG6SppiTest()

const syncing = ref(false)

// ─── 数据层（自加载/保存，对齐同组其他 tab） ──────────────────────────────
const formData = useG6SppiFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const wpIdRef = computed(() => props.wpId)
const { generateAndConfirm, loading: aiLoading } = useG6SppiAiGenerate(wpIdRef)

const SPPI_ITEM_ID = 'G6-8-sppi-test-data'
const BM_ITEM_ID = 'G6-7-business-model-data'

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

const businessModelConclusion = computed<BusinessModelConclusion>(() => {
  const payload = parseG6ChecklistPayload(formData.allResponses.value.get(BM_ITEM_ID))
  const v = payload?.finalConclusion
  if (v === 'hold_collect' || v === 'hold_and_sell' || v === 'other') return v
  return null
})

const crossCheck = computed(() =>
  evaluateG67G68Consistency(businessModelConclusion.value, overallConclusion.value),
)

const crossCheckTitle = computed(() => {
  if (!crossCheck.value.expectedClassification) return '与 G6-7 业务模式交叉提示'
  return `与 G6-7 业务模式交叉提示 · 预期分类：${crossCheck.value.expectedClassification}`
})

const crossCheckAlertType = computed(() => {
  if (crossCheck.value.level === 'warning') return 'warning'
  if (crossCheck.value.level === 'ok') return 'success'
  return 'info'
})

async function syncClassificationWriteback(): Promise<void> {
  const check = evaluateG67G68Consistency(businessModelConclusion.value, overallConclusion.value)
  if (!check.expectedClassification && !businessModelConclusion.value && !overallConclusion.value) {
    return
  }
  const summary = buildG6ClassificationSummary({
    businessModel: businessModelConclusion.value,
    sppiOverall: overallConclusion.value,
    instruments: instruments.value.map((i) => ({
      id: i.id,
      name: i.name,
      overallConclusion: i.overallConclusion,
    })),
    source: 'G6-8',
  })
  const result = await writeG6ClassificationSummary({
    projectId: props.projectId,
    sppiWpId: props.wpId,
    summary,
  })
  if (!result.mainOk && result.resolveError) {
    ElMessage.warning(`分类摘要已存 SPPI；Main 未写入：${result.resolveError}`)
  }
}

async function handleAi(): Promise<void> {
  if (props.isReadonly) return
  const unsatisfied = sections.value.flatMap((s) =>
    s.items
      .filter((i) => i.isSPPISatisfied === 'no' || i.riskLevel === 'high')
      .slice(0, 3)
      .map((i) => ({
        section: s.title,
        checkItem: i.checkItem,
        isSPPISatisfied: i.isSPPISatisfied,
        riskLevel: i.riskLevel,
        contractExcerpt: (i.contractTermSummary || '').slice(0, 160),
        judgmentBasis: (i.judgmentBasis || '').slice(0, 160),
      })),
  ).slice(0, 12)

  const text = await generateAndConfirm(
    'sppi-conclusion',
    auditConclusion.value || '',
    {
      instrumentCount: instruments.value.length,
      instruments: instruments.value.map((i) => ({
        name: i.name,
        conclusion: i.overallConclusion,
      })),
      overallConclusion: overallConclusion.value,
      hasFailedSection: hasFailedSection.value,
      failedSections: failedSections.value.map((s) => s.title),
      totalRows: totalRows.value,
      evidenceGapCount: evidenceGaps.value.length,
      businessModelConclusion: businessModelConclusion.value,
      crossCheck: crossCheck.value,
      unsatisfiedOrHighRisk: unsatisfied,
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

function addProject(): void {
  if (props.isReadonly) return
  addInstrument('未命名投资项目')
  persist()
}

function removeCurrentProject(): void {
  if (props.isReadonly || !activeInstrumentId.value) return
  removeInstrument(activeInstrumentId.value)
  persist()
}

async function syncFromMain(): Promise<void> {
  if (props.isReadonly) return
  syncing.value = true
  try {
    const rows = await fetchG62DetailRows(props.projectId, props.wpId)
    const seeds = mapG62RowsToSppiSeeds(rows)
    if (!seeds.length) {
      ElMessage.warning('未从 G6-2 取到投资项目，请先维护明细')
      return
    }
    const { added, kept } = syncFromSeeds(seeds)
    persist()
    ElMessage.success(`已同步：新增 ${added} 个，保留 ${kept} 个`)
  } catch {
    ElMessage.error('从 G6-2 同步失败')
  } finally {
    syncing.value = false
  }
}

async function onImported(): Promise<void> {
  await formData.loadAll()
  initFromData()
  const noteResp = formData.allResponses.value.get(NOTE_KEY)
  if (noteResp?.remark) auditNote.value = noteResp.remark
  const concResp = formData.allResponses.value.get(CONCLUSION_KEY)
  if (concResp?.remark) auditConclusion.value = concResp.remark
}

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
      if (parsed?.instruments?.length || parsed?.sections?.length) {
        loadData(parsed)
        return
      }
    } catch { /* ignore parse error */ }
  }
  // 其次从 render-config 解析内容
  const content = formData.parseContent()
  if (content.sppiTest && ((content.sppiTest as any).instruments || (content.sppiTest as any).sections)) {
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
  void syncClassificationWriteback()
}

function flushPersist(): void {
  if (props.isReadonly) return
  persist()
  formData.flushPending()
}

onBeforeUnmount(() => {
  flushPersist()
})

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
  justify-content: space-between;
  align-items: center;
  gap: 6px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.instrument-bar {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
  padding: 10px 12px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  background: #fafafa;
}
.instrument-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.inst-fail { color: #f56c6c; font-weight: 600; }
.inst-pass { color: #67c23a; font-weight: 600; }
.chip-wrap {
  display: inline-flex;
  align-items: center;
}
.row-index-chip {
  margin-top: 4px;
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

.cross-check-alert {
  margin: 10px 0;
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
