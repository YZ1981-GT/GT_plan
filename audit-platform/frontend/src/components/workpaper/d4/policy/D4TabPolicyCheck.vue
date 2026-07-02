<script setup lang="ts">
/**
 * D4TabPolicyCheck — D4-5 营业收入会计政策检查
 *
 * 对齐源模板真实结构：审计目标 / 经营模式(6项) / 会计政策(业务分组) / 信用政策 / 审计说明 / 审计结论
 * 引导式分步流程 + 左侧带完成状态导航 + 编制提示折叠 + 真实AI辅助 + 真实索引跳转 + 双模式
 *
 * Requirements: 7.1-7.7, 21.3
 */
import { ref, computed, inject, toRef, nextTick, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useD4PolicyCheck } from '../../composables/useD4PolicyCheck'
import GtOnlyOfficeSheet from '../../GtOnlyOfficeSheet.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

// ─── 双模式 ──────────────────────────────────────────────────────────
const editorMode = ref<'structured' | 'onlyoffice'>('structured')
const ooHealthy = ref(false)
const modeOptions = computed(() => [
  { label: '结构化视图', value: 'structured' },
  { label: '在线编辑', value: 'onlyoffice', disabled: !ooHealthy.value },
])
async function checkOoHealth() {
  try {
    const res = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
    ooHealthy.value = res.data?.data?.healthy ?? res.data?.healthy ?? false
  } catch { ooHealthy.value = false }
}
checkOoHealth()

// ─── AI 健康检查 ─────────────────────────────────────────────────────
const aiAvailable = ref(false)
async function checkAiHealth() {
  try {
    const res = await http.get('/api/ai/health', { _silent: true } as any)
    const status = res.data?.data?.status ?? res.data?.status
    aiAvailable.value = status === 'healthy' || status === 'degraded'
  } catch { aiAvailable.value = false }
}
checkAiHealth()

// ─── 政策检查逻辑 ─────────────────────────────────────────────────────
const {
  auditObjective,
  bizModelItems,
  updateBizModel,
  policyGroups,
  addPolicyGroup,
  removePolicyGroup,
  updatePolicyGroup,
  creditPolicy,
  updateCreditPolicy,
  auditNote,
  auditConclusion,
  updateAuditNote,
  updateAuditConclusion,
  completedCount,
  totalCount,
  progress,
  guidanceTips,
} = useD4PolicyCheck({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

// ─── 各章节完成状态（引导式流程用） ──────────────────────────────────
const bizModelDone = computed(() => bizModelItems.value.filter(i => i.content.trim()).length)
const secDone = computed<Record<string, boolean>>(() => ({
  objective: true, // 固定文本，视为已完成
  'biz-model': bizModelDone.value === bizModelItems.value.length && bizModelItems.value.length > 0,
  policy: policyGroups.value.length > 0 && policyGroups.value.every(g => g.rationalityAnalysis.trim()),
  credit: !!creditPolicy.value.trim(),
  note: !!auditNote.value.trim(),
  conclusion: !!auditConclusion.value.trim(),
}))

// ─── 章节导航 ────────────────────────────────────────────────────────
const sections = [
  { id: 'objective', label: '一、审计目标', hint: '明确本底稿的审计目标' },
  { id: 'biz-model', label: '二、经营模式', hint: '了解并记录 6 项经营模式' },
  { id: 'policy', label: '（二）会计政策', hint: '按业务类型评价政策合理性' },
  { id: 'credit', label: '（三）信用政策', hint: '记录信用期与坏账政策' },
  { id: 'note', label: '三、审计说明', hint: '补充审计过程说明' },
  { id: 'conclusion', label: '四、审计结论', hint: '形成政策合理性结论' },
]
const activeSection = ref('objective')
function goToSection(id: string) {
  activeSection.value = id
  nextTick(() => {
    document.getElementById(`d45-sec-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

const currentIndex = computed(() => sections.findIndex(s => s.id === activeSection.value))
function goNext() {
  const i = currentIndex.value
  if (i < sections.length - 1) goToSection(sections[i + 1].id)
}
function goPrev() {
  const i = currentIndex.value
  if (i > 0) goToSection(sections[i - 1].id)
}

// ─── AI 辅助（真实端点） ─────────────────────────────────────────────
const aiLoadingKey = ref<string | null>(null)

async function callD4Ai(section: string, existingContent: string, relatedContext: Record<string, any>): Promise<string> {
  const res = await http.post(
    `/api/workpapers/${props.wpId}/d4/ai-generate`,
    { section, existingContent, relatedContext },
    { _silent: true } as any,
  )
  return res.data?.data?.content ?? res.data?.content ?? ''
}

async function generatePolicyRationality(g: (typeof policyGroups.value)[number]) {
  if (props.isReadonly || !aiAvailable.value) return
  aiLoadingKey.value = `rationality-${g.id}`
  try {
    const existing = [
      `业务类型：${g.bizName || '（未填写）'}`,
      `收入会计政策：${g.revenuePolicy || '（未填写）'}`,
      `同行业相关政策：${g.industryPolicy || '（未填写）'}`,
      g.rationalityAnalysis ? `现有分析：${g.rationalityAnalysis}` : '',
    ].filter(Boolean).join('\n')
    const text = await callD4Ai('policy-evaluation', existing, { 业务类型: g.bizName })
    if (!text) { ElMessage.warning('AI 未生成内容，请检查 LLM 服务'); return }
    await ElMessageBox.confirm(
      text.length > 300 ? text.slice(0, 300) + '…' : text,
      'AI 生成 · 合理性分析',
      { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' },
    )
    updatePolicyGroup(g.id, 'rationalityAnalysis', text)
  } catch (err: any) {
    if (err !== 'cancel' && err?.message !== 'cancel') ElMessage.warning('AI 生成失败，请稍后重试')
  } finally {
    aiLoadingKey.value = null
  }
}

async function generateConclusion() {
  if (props.isReadonly || !aiAvailable.value) return
  aiLoadingKey.value = 'conclusion'
  try {
    const existing = [
      ...policyGroups.value.map(g => `【${g.bizName || '业务'}】政策：${g.revenuePolicy || '—'}；合理性：${g.rationalityAnalysis || '—'}`),
      `信用政策：${creditPolicy.value || '（未填写）'}`,
      auditConclusion.value ? `现有结论：${auditConclusion.value}` : '',
    ].filter(Boolean).join('\n')
    const text = await callD4Ai('adj-conclusion', existing, {})
    if (!text) { ElMessage.warning('AI 未生成内容，请检查 LLM 服务'); return }
    await ElMessageBox.confirm(
      text.length > 300 ? text.slice(0, 300) + '…' : text,
      'AI 生成 · 审计结论',
      { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' },
    )
    updateAuditConclusion(text)
  } catch (err: any) {
    if (err !== 'cancel' && err?.message !== 'cancel') ElMessage.warning('AI 生成失败，请稍后重试')
  } finally {
    aiLoadingKey.value = null
  }
}

const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')
</script>

<template>
  <div class="d4-policy-check">
    <!-- 顶部工具条 -->
    <div class="mode-bar">
      <el-segmented v-model="editorMode" :options="modeOptions" size="small" />
      <div class="mode-bar-right">
        <span class="chip-label">关联底稿</span>
        <GtIndexChip value="wp:D4-2" :context-project-id="projectId" />
        <GtIndexChip value="wp:D4-12" :context-project-id="projectId" />
        <GtIndexChip value="wp:D4-1" :context-project-id="projectId" />
      </div>
    </div>

    <!-- 结构化视图 -->
    <template v-if="editorMode === 'structured'">
      <!-- 概览横幅 -->
      <div class="overview-panel">
        <el-progress
          type="circle"
          :percentage="progress"
          :width="60"
          :stroke-width="6"
          :color="progress === 100 ? '#67c23a' : undefined"
        />
        <div class="overview-title">
          <h3>营业收入会计政策检查 <span class="overview-tag">D4-5</span></h3>
          <p class="overview-subtitle">
            检查收入确认会计政策的合理性及与前期的一致性 · 已填 {{ completedCount }}/{{ totalCount }} 项
          </p>
        </div>
        <div class="overview-steps">
          <span
            v-for="(s, i) in sections"
            :key="s.id"
            class="step-dot"
            :class="{ done: secDone[s.id], active: activeSection === s.id }"
            :title="s.label"
            @click="goToSection(s.id)"
          >{{ secDone[s.id] ? '✓' : i + 1 }}</span>
        </div>
      </div>

      <div class="main-layout">
        <!-- 左侧引导导航 -->
        <div class="sec-nav">
          <div
            v-for="s in sections"
            :key="s.id"
            class="sec-nav-item"
            :class="{ active: activeSection === s.id, done: secDone[s.id] }"
            @click="goToSection(s.id)"
          >
            <span class="nav-status">
              <el-icon v-if="secDone[s.id]" color="#67c23a"><svg viewBox="0 0 1024 1024" width="14" height="14"><path fill="currentColor" d="M406.656 706.944 195.84 496.256a32 32 0 1 0-45.248 45.248l256 256 512-512a32 32 0 0 0-45.248-45.248L406.592 706.944z"/></svg></el-icon>
              <span v-else class="nav-dot" />
            </span>
            <div class="nav-text">
              <div class="nav-label">{{ s.label }}</div>
              <div class="nav-hint">{{ s.hint }}</div>
            </div>
          </div>
        </div>

        <!-- 右侧内容 -->
        <div class="sec-content">
          <!-- 编制提示（顶部折叠） -->
          <div class="guidance-box">
            <details v-for="(tip, i) in guidanceTips" :key="i" class="guidance-details">
              <summary>📋 {{ tip.title }}</summary>
              <div class="guidance-content">{{ tip.content }}</div>
            </details>
          </div>

          <!-- 一、审计目标 -->
          <el-card id="d45-sec-objective" class="sec-card" shadow="never">
            <template #header><span class="sec-title"><span class="sec-no">1</span>审计目标</span></template>
            <div class="objective-text">
              <el-icon class="obj-icon"><svg viewBox="0 0 1024 1024" width="16" height="16"><path fill="currentColor" d="M512 64a448 448 0 1 1 0 896 448 448 0 0 1 0-896zm-38.4 300.8a38.4 38.4 0 1 0 76.8 0 38.4 38.4 0 0 0-76.8 0zM448 512v192h128V512H448z"/></svg></el-icon>
              {{ auditObjective }}
            </div>
          </el-card>

          <!-- 二、审计过程 - 经营模式 -->
          <el-card id="d45-sec-biz-model" class="sec-card" shadow="never">
            <template #header>
              <div class="sec-header-row">
                <span class="sec-title"><span class="sec-no">2</span>审计过程 ·（一）经营模式</span>
                <el-tag size="small" :type="bizModelDone === bizModelItems.length ? 'success' : 'info'" effect="light">
                  {{ bizModelDone }}/{{ bizModelItems.length }}
                </el-tag>
              </div>
            </template>
            <div v-for="item in bizModelItems" :key="item.key" class="field-block">
              <label class="field-label">
                {{ item.label }}
                <el-icon v-if="item.content.trim()" color="#67c23a" class="field-check"><svg viewBox="0 0 1024 1024" width="12" height="12"><path fill="currentColor" d="M406.656 706.944 195.84 496.256a32 32 0 1 0-45.248 45.248l256 256 512-512a32 32 0 0 0-45.248-45.248L406.592 706.944z"/></svg></el-icon>
              </label>
              <el-input
                type="textarea"
                :rows="2"
                :model-value="item.content"
                :disabled="isReadonly"
                :placeholder="`请描述${item.label.replace(/^\d+\.\s*/, '')}...`"
                @input="(v: string) => updateBizModel(item.key, v)"
              />
            </div>
          </el-card>

          <!-- （二）会计政策 -->
          <el-card id="d45-sec-policy" class="sec-card" shadow="never">
            <template #header>
              <div class="sec-header-row">
                <span class="sec-title"><span class="sec-no">3</span>（二）会计政策</span>
                <el-button size="small" type="primary" plain :disabled="isReadonly" @click="addPolicyGroup">+ 添加业务类型</el-button>
              </div>
            </template>
            <p class="sec-hint">包括销售退回、质量保证、售后回购、主要责任人和代理人、授予知识产权许可等特殊交易</p>
            <div v-for="(g, idx) in policyGroups" :key="g.id" class="policy-group">
              <div class="policy-group-head">
                <span class="policy-group-idx">{{ idx + 1 }}</span>
                <el-input
                  :model-value="g.bizName"
                  size="small"
                  placeholder="业务类型名称（如 销售商品收入 / 贸易业务）"
                  :disabled="isReadonly"
                  style="max-width: 320px"
                  @input="(v: string) => updatePolicyGroup(g.id, 'bizName', v)"
                />
                <el-button
                  v-if="!isReadonly && policyGroups.length > 1"
                  type="danger" size="small" link
                  @click="removePolicyGroup(g.id)"
                >删除</el-button>
              </div>
              <div class="field-block">
                <label class="field-label">（1）收入会计政策</label>
                <el-input type="textarea" :rows="2" :model-value="g.revenuePolicy" :disabled="isReadonly"
                  placeholder="描述该业务的收入确认会计政策..."
                  @input="(v: string) => updatePolicyGroup(g.id, 'revenuePolicy', v)" />
              </div>
              <div class="field-block">
                <label class="field-label">（2）同行业相关政策</label>
                <el-input type="textarea" :rows="2" :model-value="g.industryPolicy" :disabled="isReadonly"
                  placeholder="对比同行业的相关会计政策..."
                  @input="(v: string) => updatePolicyGroup(g.id, 'industryPolicy', v)" />
              </div>
              <div class="field-block">
                <div class="field-label-row">
                  <label class="field-label">（3）合理性分析</label>
                  <el-tooltip :content="aiTip" placement="top">
                    <el-button size="small" type="primary" plain
                      :loading="aiLoadingKey === `rationality-${g.id}`"
                      :disabled="isReadonly || !aiAvailable"
                      @click="generatePolicyRationality(g)">🤖 AI生成</el-button>
                  </el-tooltip>
                </div>
                <el-input type="textarea" :rows="3" :model-value="g.rationalityAnalysis" :disabled="isReadonly"
                  placeholder="通过合同检查、收入检查底稿，分析该会计政策的合理性，说明理由..."
                  @input="(v: string) => updatePolicyGroup(g.id, 'rationalityAnalysis', v)" />
              </div>
            </div>
          </el-card>

          <!-- （三）信用政策 -->
          <el-card id="d45-sec-credit" class="sec-card" shadow="never">
            <template #header><span class="sec-title"><span class="sec-no">4</span>（三）信用政策</span></template>
            <el-input type="textarea" :rows="3" :model-value="creditPolicy" :disabled="isReadonly"
              placeholder="描述被审计单位的信用政策（信用期、信用额度、坏账政策等）..."
              @input="(v: string) => updateCreditPolicy(v)" />
          </el-card>

          <!-- 三、审计说明 -->
          <el-card id="d45-sec-note" class="sec-card" shadow="never">
            <template #header>
              <div class="sec-header-row">
                <span class="sec-title"><span class="sec-no">5</span>审计说明</span>
                <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-5-note')">💬 复核</el-button>
              </div>
            </template>
            <el-input type="textarea" :rows="3" :model-value="auditNote" :disabled="isReadonly"
              placeholder="请输入审计说明..."
              @input="(v: string) => updateAuditNote(v)" />
          </el-card>

          <!-- 四、审计结论 -->
          <el-card id="d45-sec-conclusion" class="sec-card" shadow="never">
            <template #header>
              <div class="sec-header-row">
                <span class="sec-title"><span class="sec-no">6</span>审计结论</span>
                <el-tooltip :content="aiTip" placement="top">
                  <el-button size="small" type="primary" plain
                    :loading="aiLoadingKey === 'conclusion'"
                    :disabled="isReadonly || !aiAvailable"
                    @click="generateConclusion">🤖 AI生成</el-button>
                </el-tooltip>
              </div>
            </template>
            <el-input type="textarea" :rows="4" :model-value="auditConclusion" :disabled="isReadonly"
              placeholder="请输入审计结论..."
              @input="(v: string) => updateAuditConclusion(v)" />
          </el-card>

          <!-- 引导式上一步/下一步 -->
          <div class="step-actions">
            <el-button :disabled="currentIndex <= 0" @click="goPrev">← 上一步</el-button>
            <span class="step-indicator">{{ currentIndex + 1 }} / {{ sections.length }}</span>
            <el-button type="primary" :disabled="currentIndex >= sections.length - 1" @click="goNext">下一步 →</el-button>
          </div>
        </div>
      </div>
    </template>

    <!-- OnlyOffice 模式 -->
    <template v-else>
      <div style="min-height: 600px; height: calc(100vh - 280px);">
        <GtOnlyOfficeSheet
          :wp-id="props.wpId"
          :project-id="props.projectId"
          sheet-name="营业收入会计政策检查D4-5"
          :readonly="isReadonly"
        />
      </div>
    </template>
  </div>
</template>

<style scoped>
.d4-policy-check {
  padding: 12px 16px;
}
.mode-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.mode-bar-right { display: flex; gap: 6px; align-items: center; }
.chip-label { font-size: 12px; color: #909399; margin-right: 2px; }

.overview-panel {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 16px 22px;
  background: linear-gradient(135deg, #f3f0ff 0%, #eaf4ff 100%);
  border-radius: 12px;
  margin-bottom: 18px;
  border: 1px solid #e0d8f5;
}
.overview-title { flex: 1; min-width: 0; }
.overview-title h3 {
  margin: 0 0 5px; font-size: 16px; color: #303133;
  display: flex; align-items: center; gap: 8px;
}
.overview-tag {
  font-size: 12px; font-weight: 500; color: #7c5cff;
  background: #fff; border: 1px solid #d9c9ff; border-radius: 4px;
  padding: 1px 7px;
}
.overview-subtitle { margin: 0; font-size: 13px; color: #909399; }
.overview-steps { display: flex; gap: 6px; }
.step-dot {
  display: inline-flex; align-items: center; justify-content: center;
  width: 26px; height: 26px; border-radius: 50%;
  font-size: 12px; font-weight: 600; cursor: pointer;
  background: #fff; color: #909399; border: 1px solid #dcdfe6;
  transition: all 0.2s;
}
.step-dot:hover { transform: translateY(-1px); }
.step-dot.done { background: #67c23a; color: #fff; border-color: #67c23a; }
.step-dot.active { box-shadow: 0 0 0 3px rgba(124, 92, 255, 0.25); border-color: #7c5cff; color: #7c5cff; }
.step-dot.active.done { color: #fff; }

.main-layout { display: flex; gap: 20px; }

.sec-nav {
  width: 200px;
  flex-shrink: 0;
  position: sticky;
  top: 12px;
  align-self: flex-start;
}
.sec-nav-item {
  display: flex;
  gap: 10px;
  padding: 9px 12px;
  cursor: pointer;
  border-radius: 8px;
  border-left: 3px solid transparent;
  transition: all 0.2s;
  margin-bottom: 4px;
}
.sec-nav-item:hover { background: #f5f7fa; }
.sec-nav-item.active {
  background: #f3f0ff;
  border-left-color: #7c5cff;
}
.nav-status { padding-top: 2px; }
.nav-dot {
  display: inline-block; width: 8px; height: 8px; border-radius: 50%;
  background: #dcdfe6; margin: 3px;
}
.sec-nav-item.active .nav-dot { background: #7c5cff; }
.nav-text { min-width: 0; }
.nav-label { font-size: 13px; color: #606266; font-weight: 500; }
.sec-nav-item.active .nav-label { color: #7c5cff; }
.sec-nav-item.done .nav-label { color: #303133; }
.nav-hint { font-size: 11px; color: #c0c4cc; margin-top: 2px; line-height: 1.4; }

.sec-content { flex: 1; min-width: 0; }

.guidance-box { margin-bottom: 16px; }
.guidance-details {
  margin-bottom: 8px;
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #e6a23c;
  font-size: 13px;
}
.guidance-content {
  margin-top: 8px;
  font-size: 13px;
  color: #606266;
  line-height: 1.7;
  white-space: pre-wrap;
}

.sec-card { margin-bottom: 16px; border-radius: 10px; }
.sec-title {
  font-size: 15px; font-weight: 600; color: #303133;
  display: flex; align-items: center; gap: 8px;
}
.sec-no {
  display: inline-flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; border-radius: 6px;
  background: #7c5cff; color: #fff; font-size: 12px; font-weight: 700;
}
.sec-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.sec-hint {
  margin: 0 0 12px;
  font-size: 12px;
  color: #909399;
}
.objective-text {
  margin: 0;
  font-size: 14px;
  color: #303133;
  line-height: 1.8;
  padding: 12px 14px;
  background: #f5f7fa;
  border-radius: 8px;
  display: flex;
  gap: 8px;
}
.obj-icon { color: #7c5cff; flex-shrink: 0; margin-top: 4px; }

.field-block { margin-bottom: 14px; }
.field-label {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 13px;
  font-weight: 500;
  color: #303133;
  margin-bottom: 6px;
}
.field-check { flex-shrink: 0; }
.field-label-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.policy-group {
  border: 1px solid #ebeef5;
  border-radius: 10px;
  padding: 14px;
  margin-bottom: 14px;
  background: #fafbfc;
}
.policy-group-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.policy-group-idx {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #7c5cff;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}

.step-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 4px 4px;
}
.step-indicator { font-size: 13px; color: #909399; }
</style>
