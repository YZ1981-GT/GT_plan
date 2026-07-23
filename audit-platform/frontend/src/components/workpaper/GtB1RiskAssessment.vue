<!--
  GtB1RiskAssessment.vue — B1-1/B1-2 A、B类鉴证业务风险评估表

  源模板=分章节固定问卷表（事项 | 事实或描述 | 说明或附件），后端预置全部固定事项。
  - 承接(B1-1) / 保持(B1-2) 变体由 wp_code 判定
  - 左侧章节导航 + 右侧分章节问卷卡片
  - choice 事项(是否类)→ 是/否/N/A 点选，答"是"高亮为风险信号
  - 顶部风险信号统计 + 综合结论(变体化枚举)+ AI 辅助综合说明
  - 保持场景显示上年度风险结论承继提示
  - GtIndexChip 跳转 B1A/B1B 程序表、B1-4 尽调报告
-->
<template>
  <div class="gt-b1risk">
    <!-- Toolbar -->
    <div class="gt-b1risk__toolbar">
      <el-segmented v-model="mode" :options="modeOptions" size="small" />
      <el-tag :type="variant === 'retention' ? 'warning' : 'success'" effect="plain" size="small">
        {{ variant === 'retention' ? '业务保持' : '业务承接' }}
      </el-tag>
      <span class="gt-b1risk__spacer" />
      <span class="gt-b1risk__save-status">
        <template v-if="saveStatus === 'saving'"><el-icon class="is-loading"><Loading /></el-icon> 保存中...</template>
        <template v-else-if="saveStatus === 'saved'">✓ 已保存</template>
        <template v-else>○ 未保存</template>
      </span>
    </div>

    <div v-if="mode === '结构化视图'" class="gt-b1risk__body">
      <!-- 审计目标/方法论提示 -->
      <el-alert type="info" :closable="false" show-icon class="gt-b1risk__objective">
        <template #title>
          <strong>评估目标（质量管理准则 CSQM1 / 中国注册会计师职业道德守则）</strong>
        </template>
        <ul class="gt-b1risk__obj-list">
          <li>识别与{{ variant === 'retention' ? '保持' : '承接' }}该项业务相关的风险因素，评价事务所的独立性、专业胜任能力及资源；</li>
          <li>逐项核实下列固定评估事项，凡"是否"类事项回答<strong>"是"</strong>的通常构成需关注的风险信号，须在"说明或附件"中记录依据；</li>
          <li>综合各项评估形成总体风险结论，作为{{ variant === 'retention' ? 'B1B 业务保持' : 'B1A 业务承接' }}程序表审批的依据。</li>
        </ul>
      </el-alert>

      <!-- 上年度承继（保持） -->
      <el-alert
        v-if="variant === 'retention'"
        :type="priorYear ? 'success' : 'warning'"
        :closable="false"
        show-icon
        class="gt-b1risk__prior"
      >
        <template #title>
          <template v-if="priorYear">
            上年度（{{ priorYear.year }}）风险评估结论：<strong>{{ priorYearLabel }}</strong>，请结合本年变化重新评估
          </template>
          <template v-else>未获取到上年度风险评估结论，请手工填写并关注客户风险变化</template>
        </template>
      </el-alert>

      <!-- 头部信息 -->
      <el-card shadow="never" class="gt-b1risk__header-card">
        <div class="gt-b1risk__header-grid">
          <div v-for="hf in headerFields" :key="hf.field" class="gt-b1risk__header-item">
            <label>{{ hf.label }}</label>
            <el-input
              :model-value="header[hf.field] || ''"
              size="small"
              placeholder="请输入"
              @update:model-value="(v: string) => updateHeader(hf.field, v)"
            />
          </div>
        </div>
      </el-card>

      <!-- 风险信号统计 -->
      <div class="gt-b1risk__summary">
        <el-tag type="danger" effect="dark" size="small">风险信号 {{ riskSignalCount }} 项</el-tag>
        <el-tag v-if="riskSignalMissingBasis > 0" type="warning" effect="dark" size="small">
          ⚠️ {{ riskSignalMissingBasis }} 项未填依据
        </el-tag>
        <el-tag type="info" effect="plain" size="small">待填事项 {{ pendingCount }} / {{ totalItems }}</el-tag>
        <el-tag v-if="kaaHint" :type="kaaHint.reached ? 'warning' : 'success'" effect="plain" size="small">
          B1-5 KAA：{{ kaaHint.reached ? '达到标准' : '未达到' }}
        </el-tag>
        <el-button
          size="small"
          type="danger"
          plain
          :disabled="riskSignalCount === 0"
          class="gt-b1risk__signal-btn"
          @click="signalDialogVisible = true"
        >📋 风险信号汇总</el-button>
        <span class="gt-b1risk__summary-hint">（"是否"类事项答"是"计为风险信号，须在"说明或附件"记录依据）</span>
      </div>

      <div class="gt-b1risk__layout">
        <!-- 左侧导航 -->
        <nav class="gt-b1risk__nav">
          <ul>
            <li
              v-for="(sec, si) in sections"
              :key="si"
              :class="{ 'is-active': activeSection === si }"
              @click="scrollToSection(si)"
            >
              <span class="gt-b1risk__nav-dot" :class="sectionComplete(sec) ? 'is-complete' : ''" />
              <span class="gt-b1risk__nav-title">{{ shortTitle(sec.title) }}</span>
              <el-badge
                v-if="sectionRiskCount(sec) > 0"
                :value="sectionRiskCount(sec)"
                type="danger"
                class="gt-b1risk__nav-badge"
              />
            </li>
          </ul>
        </nav>

        <!-- 右侧内容 -->
        <main class="gt-b1risk__content">
          <el-card
            v-for="(sec, si) in sections"
            :key="si"
            shadow="never"
            class="gt-b1risk__section-card"
            :id="`b1risk-sec-${si}`"
          >
            <template #header>
              <span class="gt-b1risk__section-title">{{ sec.title }}</span>
            </template>
            <el-table :data="sec.items" size="small" border class="gt-b1risk__table">
              <el-table-column label="事项" min-width="280">
                <template #default="{ row }">
                  <span class="gt-b1risk__item-label">{{ row.item }}</span>
                </template>
              </el-table-column>
              <el-table-column label="事实或描述" min-width="220">
                <template #default="{ row }">
                  <el-select
                    v-if="row.kind === 'choice'"
                    :model-value="row.answer"
                    size="small"
                    placeholder="选择"
                    clearable
                    :class="{ 'is-risk': isRiskAnswer(row) }"
                    @update:model-value="(v: string) => updateAnswer(row.key, v)"
                  >
                    <el-option v-for="o in choiceOptions" :key="o" :label="o" :value="o" />
                  </el-select>
                  <el-input
                    v-else
                    :model-value="row.answer"
                    type="textarea"
                    :autosize="{ minRows: 1, maxRows: 4 }"
                    size="small"
                    placeholder="填写事实或描述"
                    @update:model-value="(v: string) => updateAnswer(row.key, v)"
                  />
                </template>
              </el-table-column>
              <el-table-column label="说明或附件" min-width="240">
                <template #default="{ row }">
                  <div class="gt-b1risk__note-cell">
                    <el-input
                      :model-value="row.note"
                      type="textarea"
                      :autosize="{ minRows: 1, maxRows: 4 }"
                      size="small"
                      :placeholder="isRiskAnswer(row) ? '⚠️ 风险信号，请记录依据/应对' : '如有请说明'"
                      :class="{ 'is-risk-note': isRiskAnswer(row) }"
                      @update:model-value="(v: string) => updateNote(row.key, v)"
                    />
                    <el-upload
                      :show-file-list="false"
                      :before-upload="(f: File) => beforeRowOcr(row.key, f)"
                      accept=".pdf,.png,.jpg,.jpeg,.webp"
                      class="gt-b1risk__note-upload"
                    >
                      <el-tooltip content="上传附件并 OCR 识别，追加到说明" placement="top">
                        <el-button
                          size="small"
                          text
                          :loading="ocrLoadingKey === row.key"
                          class="gt-b1risk__ocr-btn"
                        >📎</el-button>
                      </el-tooltip>
                    </el-upload>
                  </div>
                </template>
              </el-table-column>
            </el-table>
          </el-card>

          <!-- 综合结论 -->
          <el-card shadow="never" class="gt-b1risk__conclusion-card">
            <template #header>
              <span class="gt-b1risk__section-title">总体风险评估结论</span>
              <GtReviewTrigger section-id="b1risk-conclusion" label="💬 复核" />
            </template>
            <div class="gt-b1risk__conclusion-row">
              <label>综合评估说明</label>
              <div class="gt-b1risk__explanation">
                <el-input
                  :model-value="overall.explanation"
                  type="textarea"
                  :autosize="{ minRows: 4 }"
                  placeholder="综合上述评估事项，说明风险因素、应对措施及总体判断"
                  @update:model-value="updateOverallExplanation"
                />
                <el-button
                  size="small"
                  text
                  type="primary"
                  :loading="aiLoading"
                  class="gt-b1risk__ai-btn"
                  @click="handleAiGenerate"
                >🤖 AI 辅助说明</el-button>
              </div>
            </div>
            <div class="gt-b1risk__conclusion-row">
              <label>总体风险评估结论</label>
              <el-select
                :model-value="overall.conclusion"
                placeholder="选择总体结论"
                @update:model-value="updateOverallConclusion"
              >
                <el-option
                  v-for="o in conclusionOptions"
                  :key="o.value"
                  :label="o.label"
                  :value="o.value"
                />
              </el-select>
              <el-tag v-if="currentConclusionOption" :type="currentConclusionOption.class" effect="dark" size="small">
                {{ currentConclusionOption.label }}
              </el-tag>
              <el-tag
                v-if="suggestedConclusion && !overall.conclusion"
                type="info" effect="plain" size="small"
              >
                💡 建议：{{ suggestedConclusion === 'high_risk' ? '高风险' : suggestedConclusion === 'medium_risk' ? '中风险' : '低风险' }}（{{ riskSignalCount }}项风险信号）
              </el-tag>
            </div>
            <el-alert
              v-if="riskConsistency"
              :type="riskConsistency.mismatch ? 'warning' : 'success'"
              :closable="false"
              show-icon
              class="gt-b1risk__consistency"
            >
              <template #title>
                <span v-if="riskConsistency.mismatch">
                  ⚠️ 与 B1-3 业务评价表"综合客户风险：{{ riskConsistency.evalLabel }}"不一致，请核对（本表结论：{{ riskConsistency.selfLabel }}）
                </span>
                <span v-else>✓ 与 B1-3 业务评价表综合客户风险（{{ riskConsistency.evalLabel }}）一致</span>
              </template>
            </el-alert>
            <p class="gt-b1risk__conclusion-hint">
              结论确定后将自动同步至 {{ variant === 'retention' ? 'B1B 业务保持' : 'B1A 业务承接' }}程序表（步骤 5.1 / 5.3）。
            </p>
          </el-card>
        </main>
      </div>
    </div>

    <!-- 在线编辑（OnlyOffice 降级） -->
    <div v-else class="gt-b1risk__oo">
      <GtOnlyOfficeSheet :wp-id="wpId" :sheet-name="ooSheetName" :project-id="projectId" />
    </div>

    <!-- P2-8：风险信号汇总弹窗（复核视角） -->
    <el-dialog v-model="signalDialogVisible" title="风险信号汇总（复核视角）" width="660px" append-to-body>
      <div class="gt-b1risk__signal-summary">
        <el-tag type="danger" effect="dark" size="small">风险信号 {{ riskSignalRows.length }} 项</el-tag>
        <el-tag v-if="riskSignalMissingBasis > 0" type="warning" effect="dark" size="small">
          ⚠️ {{ riskSignalMissingBasis }} 项缺依据
        </el-tag>
      </div>
      <el-table :data="riskSignalRows" size="small" border max-height="480" class="gt-b1risk__signal-table">
        <el-table-column label="章节" prop="section" min-width="120" show-overflow-tooltip />
        <el-table-column label="事项（答是即风险信号）" prop="item" min-width="240" show-overflow-tooltip />
        <el-table-column label="依据" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.hasBasis" type="success" size="small" effect="plain">已填</el-tag>
            <el-tag v-else type="warning" size="small" effect="dark">缺依据</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="jumpToSignal(row.si)">定位</el-button>
          </template>
        </el-table-column>
        <template #empty>暂无风险信号（无"是否"类事项答"是"）</template>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef, inject, provide, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import { useB1RiskAssessment, CHOICE_OPTIONS, type B1RiskRenderData, type B1RiskSection, type B1RiskItem } from './composables/useB1RiskAssessment'
import { useWpDualMode } from './composables/useWpDualMode'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
import { WorkpaperRuntimeContextKey, type WorkpaperRuntimeContext } from './composables/useWorkpaperScaffold'
import GtReviewTrigger from './GtReviewTrigger.vue'

// 版本快照由 Runtime Boundary(GtWpRenderer) 提供的运行时上下文承载；复核对话由 GtReviewTrigger 自行 inject
const runtime = inject<WorkpaperRuntimeContext | null>(WorkpaperRuntimeContextKey, null)
const scheduleAutoSnapshot = () => runtime?.version?.scheduleAutoSnapshot?.()

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

defineOptions({ name: 'GtB1RiskAssessment' })

const props = withDefaults(defineProps<{
  wpId: string
  projectId?: string
  wpCode?: string
  htmlData?: B1RiskRenderData | null
}>(), { projectId: '', wpCode: '', htmlData: null })

const {
  loading, saveStatus, variant, sourceSheet, sections, headerFields, header,
  overall, conclusionOptions, projectContext, priorYear, kaaHint, evalClientRisk,
  updateAnswer, updateNote, updateHeader, updateOverallConclusion, updateOverallExplanation,
  flushPendingSaves, loadData, suggestedConclusion, ocrRowNote, ocrLoadingKey,
} = useB1RiskAssessment({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  htmlData: toRef(props, 'htmlData'),
  onAfterSave: () => scheduleAutoSnapshot?.(),
})

// 双模式：健康检查 + 切换前 flush（对齐 D4/GtB14 gold 范式）
const { mode, modeOptions, checkOOHealth } = useWpDualMode({ flush: flushPendingSaves })

// OnlyOffice tab 名兜底（source_sheet 缺失时按变体回退真实 tab 名）
const ooSheetName = computed(
  () => sourceSheet.value || (variant.value === 'retention' ? '风险评估表-保持' : '风险评估表-承接'),
)

// 复核线程蓝/红点（供后代 GtReviewTrigger/GtReviewDot inject）
const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(toRef(props, 'wpId') as any)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

const choiceOptions = CHOICE_OPTIONS

// ─── 风险信号判定 ───
function isRiskAnswer(row: B1RiskItem): boolean {
  return row.kind === 'choice' && row.answer === '是'
}
const riskSignalCount = computed(() =>
  sections.value.reduce((n, s) => n + s.items.filter(isRiskAnswer).length, 0),
)
const totalItems = computed(() => sections.value.reduce((n, s) => n + s.items.length, 0))
const pendingCount = computed(() =>
  sections.value.reduce((n, s) => n + s.items.filter((i) => !i.answer).length, 0),
)
// 风险信号(答"是")但"说明或附件"为空 → 依据缺失，须提醒补录
const riskSignalMissingBasis = computed(() =>
  sections.value.reduce(
    (n, s) => n + s.items.filter((i) => isRiskAnswer(i) && !(i.note || '').trim()).length,
    0,
  ),
)
function sectionRiskCount(sec: B1RiskSection): number {
  return sec.items.filter(isRiskAnswer).length
}
function sectionComplete(sec: B1RiskSection): boolean {
  return sec.items.length > 0 && sec.items.every((i) => !!i.answer)
}
function shortTitle(t: string): string {
  return t.length > 12 ? t.slice(0, 12) + '…' : t
}

// ─── 结论 ───
const currentConclusionOption = computed(() =>
  conclusionOptions.value.find((o) => o.value === overall.value.conclusion),
)
const priorYearLabel = computed(() => {
  if (!priorYear.value) return ''
  const map: Record<string, string> = {
    low_risk: '低风险', medium_risk: '中风险', high_risk: '高风险',
  }
  return map[priorYear.value.conclusion] || priorYear.value.conclusion
})

// B1-1/B1-2 总体结论 ↔ B1-3 综合客户风险 一致性（仅两者都填时提示）
const riskConsistency = computed(() => {
  const evalRisk = evalClientRisk.value
  const selfConc = overall.value.conclusion
  if (!evalRisk || !selfConc) return null
  // 归一化到 low/medium/high
  const selfLevel = selfConc.replace('_risk', '')
  const riskCn: Record<string, string> = { low: '低', medium: '中', high: '高' }
  const selfCn: Record<string, string> = { low_risk: '低风险', medium_risk: '中风险', high_risk: '高风险' }
  return {
    mismatch: selfLevel !== evalRisk,
    evalLabel: riskCn[evalRisk] || evalRisk,
    selfLabel: selfCn[selfConc] || selfConc,
  }
})

// ─── 导航 scrollspy ───
const activeSection = ref(0)
function scrollToSection(si: number) {
  activeSection.value = si
  const el = document.getElementById(`b1risk-sec-${si}`)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

// ─── P1-6：行级 📎 OCR（el-upload before-upload 返回 false 阻止默认上传）───
function beforeRowOcr(key: string, file: File): boolean {
  void ocrRowNote(key, file)
  return false
}

// ─── P2-8：风险信号汇总弹窗（复核视角一屏看全命中项 + 依据缺口）───
const signalDialogVisible = ref(false)
interface RiskSignalRow { si: number; section: string; item: string; hasBasis: boolean; note: string }
const riskSignalRows = computed<RiskSignalRow[]>(() => {
  const rows: RiskSignalRow[] = []
  sections.value.forEach((sec, si) => {
    for (const it of sec.items) {
      if (isRiskAnswer(it)) {
        rows.push({ si, section: sec.title, item: it.item, hasBasis: !!(it.note || '').trim(), note: it.note || '' })
      }
    }
  })
  return rows
})
function jumpToSignal(si: number) {
  signalDialogVisible.value = false
  scrollToSection(si)
}

// ─── AI 辅助 ───
const aiLoading = ref(false)
async function handleAiGenerate() {
  aiLoading.value = true
  try {
    const riskItems: string[] = []
    for (const sec of sections.value) {
      for (const it of sec.items) {
        if (isRiskAnswer(it)) riskItems.push(`${it.item}：是${it.note ? '（' + it.note + '）' : ''}`)
      }
    }
    const ctx: Record<string, string> = {
      被审计单位: header.value.audited_entity || projectContext.value.client_name || '',
      业务类型: variant.value === 'retention' ? '业务保持' : '业务承接',
      行业: projectContext.value.industry || '',
      风险信号数: String(riskSignalCount.value),
      风险信号明细: riskItems.slice(0, 20).join('；') || '无明显风险信号',
    }
    const res = await api.post<any>(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'b1-risk-assessment-conclusion',
      prompt: '根据下列业务承接/保持风险评估的风险信号，撰写综合评估说明，概述主要风险因素、应对措施及总体判断',
      existingContent: overall.value.explanation || '',
      context: ctx,
    })
    const text = res?.content || res?.data?.content || res?.text || ''
    if (text) {
      updateOverallExplanation(text)
      ElMessage.success('AI 已生成综合评估说明')
    } else {
      ElMessage.warning('AI 未返回内容')
    }
  } catch {
    ElMessage.warning('AI 生成失败，请稍后重试或手工填写')
  } finally {
    aiLoading.value = false
  }
}

// ─── 生命周期 ───
onMounted(async () => {
  checkOOHealth()
  if (!props.htmlData) await loadData()
})
onBeforeUnmount(() => { flushPendingSaves() })
</script>

<style scoped>
/* ── 统一字号 13px + 视觉语言 ── */
.gt-b1risk { display: flex; flex-direction: column; gap: 12px; font-size: 13px; color: var(--el-text-color-primary); }
.gt-b1risk :deep(.el-input__inner),
.gt-b1risk :deep(.el-textarea__inner),
.gt-b1risk :deep(.el-select__placeholder),
.gt-b1risk :deep(.el-table) { font-size: 13px; }

.gt-b1risk__toolbar { display: flex; align-items: center; gap: 10px; padding: 8px 12px; background: var(--el-fill-color-lighter); border-radius: 6px; }
.gt-b1risk__spacer { flex: 1; }
.gt-b1risk__save-status { font-size: 12px; color: var(--el-text-color-secondary); }
.gt-b1risk__body { display: flex; flex-direction: column; gap: 12px; }
.gt-b1risk__objective :deep(.el-alert__content) { padding: 2px 0; }
.gt-b1risk__obj-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.7; font-size: 13px; }

/* ── 卡片统一：primary 左强调条 + 渐变标题栏 ── */
.gt-b1risk :deep(.el-card) { border-radius: 8px; border-color: var(--el-border-color-lighter); }
.gt-b1risk :deep(.el-card__header) {
  padding: 9px 14px;
  background: linear-gradient(90deg, var(--el-color-primary-light-9), transparent 70%);
  border-left: 3px solid var(--el-color-primary);
  display: flex; align-items: center; justify-content: space-between;
}
.gt-b1risk :deep(.el-card__body) { padding: 14px; }
.gt-b1risk__section-title { font-weight: 600; font-size: 13px; color: var(--el-text-color-primary); }

.gt-b1risk__header-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px 20px; }
.gt-b1risk__header-item { display: flex; align-items: center; gap: 8px; }
.gt-b1risk__header-item label { flex: 0 0 96px; font-size: 13px; color: var(--el-text-color-regular); text-align: right; }
.gt-b1risk__summary { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.gt-b1risk__summary-hint { font-size: 12px; color: var(--el-text-color-secondary); }
.gt-b1risk__layout { display: flex; gap: 14px; align-items: flex-start; }
.gt-b1risk__nav { position: sticky; top: 8px; flex: 0 0 184px; max-height: calc(100vh - 120px); overflow-y: auto; background: var(--el-bg-color); border: 1px solid var(--el-border-color-lighter); border-radius: 8px; padding: 6px; }
.gt-b1risk__nav ul { list-style: none; margin: 0; padding: 0; }
.gt-b1risk__nav li { display: flex; align-items: center; gap: 6px; padding: 7px 10px; font-size: 13px; cursor: pointer; border-radius: 6px; transition: background .18s, color .18s; }
.gt-b1risk__nav li:hover { background: var(--el-fill-color-light); }
.gt-b1risk__nav li.is-active { background: var(--el-color-primary-light-9); color: var(--el-color-primary); font-weight: 600; }
.gt-b1risk__nav-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--el-border-color); flex: 0 0 auto; }
.gt-b1risk__nav-dot.is-complete { background: var(--el-color-success); }
.gt-b1risk__nav-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gt-b1risk__content { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 12px; }
.gt-b1risk__table { font-size: 13px; }
.gt-b1risk__item-label { font-size: 13px; line-height: 1.6; }
.gt-b1risk__table :deep(.el-select.is-risk .el-select__wrapper) { box-shadow: 0 0 0 1px var(--el-color-danger) inset; }
.gt-b1risk__table :deep(.is-risk-note .el-textarea__inner) { background: var(--el-color-danger-light-9); }
.gt-b1risk__conclusion-card :deep(.el-card__body) { display: flex; flex-direction: column; gap: 12px; }
.gt-b1risk__conclusion-row { display: flex; gap: 10px; align-items: flex-start; }
.gt-b1risk__conclusion-row > label { flex: 0 0 96px; font-size: 13px; color: var(--el-text-color-regular); padding-top: 6px; }
.gt-b1risk__explanation { flex: 1; }
.gt-b1risk__ai-btn { margin-top: 4px; }
.gt-b1risk__conclusion-hint { margin: 0; font-size: 12px; color: var(--el-text-color-secondary); }
.gt-b1risk__consistency :deep(.el-alert__title) { font-size: 13px; }
.gt-b1risk__review-btn { padding: 2px 6px; }
.gt-b1risk__nav-badge { margin-left: auto; }
.gt-b1risk__oo { min-height: 600px; }
/* P1-6 说明或附件单元格：textarea + 📎 OCR */
.gt-b1risk__note-cell { display: flex; align-items: flex-start; gap: 4px; }
.gt-b1risk__note-cell .el-textarea { flex: 1; }
.gt-b1risk__note-upload { flex: 0 0 auto; }
.gt-b1risk__ocr-btn { padding: 2px 4px; font-size: 14px; }
/* P2-8 风险信号汇总弹窗 */
.gt-b1risk__signal-summary { display: flex; gap: 8px; margin-bottom: 10px; }
.gt-b1risk__signal-table { font-size: 13px; }
.gt-b1risk__signal-btn { margin-left: 4px; }
</style>
