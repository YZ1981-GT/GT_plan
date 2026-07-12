<!--
  GtA177IndependenceDeclaration.vue — A17-7/A17-7A 独立性声明书（升级版）

  双变体 + 5章节 + 左侧导航 + 双模式 + AI辅助 + 批量签署弹窗
-->
<template>
  <div class="gt-a177">
    <!-- Toolbar -->
    <div class="gt-a177__toolbar">
      <el-segmented v-model="mode" :options="modeOptions" size="small" @change="handleModeChange" />
      <span class="gt-a177__save-status">
        <template v-if="saveStatus === 'saving'"><el-icon class="is-loading"><Loading /></el-icon> 保存中...</template>
        <template v-else-if="saveStatus === 'saved' && lastSavedAt">✓ 已保存</template>
        <template v-else-if="saveStatus === 'unsaved'">○ 未保存</template>
      </span>
    </div>

    <!-- Structured View -->
    <div v-if="mode === '结构化视图'" class="gt-a177__layout">
      <!-- Left Navigation -->
      <nav class="gt-a177__nav">
        <ul class="gt-a177__nav-list">
          <li v-for="n in 5" :key="n" class="gt-a177__nav-item" :class="{ 'is-active': activeChapter === n }" @click="scrollToChapter(n)">
            <span class="gt-a177__nav-dot" :class="{ 'is-complete': chapterComplete[n] }" />
            <span class="gt-a177__nav-title">{{ navLabels[n] }}</span>
          </li>
        </ul>
        <div v-if="signingProgress.total > 0" class="gt-a177__nav-progress">
          <el-progress :percentage="Math.round(signingProgress.signed / signingProgress.total * 100)" :stroke-width="6" :color="signingProgress.complete ? '#67c23a' : '#409eff'" />
          <span class="gt-a177__nav-progress-text">{{ signingProgress.signed }}/{{ signingProgress.total }} 已签</span>
        </div>
      </nav>

      <!-- Right Content -->
      <div class="gt-a177__content">
        <el-skeleton v-if="loading" :rows="10" animated />
        <template v-else>
          <!-- Ch1: 声明正文 + 期间 -->
          <el-card :id="'a177-ch-1'" shadow="never" class="gt-a177__card">
            <template #header>
              <div class="gt-a177__card-header">
                <span class="gt-a177__card-title">{{ variantTitle }}</span>
                <el-button size="small" text @click="handleAiFill(1)">🤖 AI</el-button>
              </div>
            </template>
            <details v-if="CHAPTER_GUIDANCE[1]" class="gt-a177__guidance"><summary>📋 编制提示</summary><div class="gt-a177__guidance-body">{{ CHAPTER_GUIDANCE[1] }}</div></details>
            <div class="gt-a177__declaration">
              <p class="gt-a177__declaration-prefix"><strong>{{ metaInfo.client_name || '______' }}</strong> {{ metaInfo.audit_year || '____' }}年度审计项目</p>
              <el-input :model-value="declarationText" type="textarea" :autosize="{ minRows: 4, maxRows: 10 }" :disabled="props.readonly" @change="handleDeclarationChange" />
            </div>
            <div class="gt-a177__period-grid">
              <div class="gt-a177__period-item">
                <label>业务期间</label>
                <div class="gt-a177__date-range">
                  <el-date-picker :model-value="periodData.business_start" type="date" size="small" value-format="YYYY-MM-DD" placeholder="开始" :disabled="props.readonly" @change="(v: string) => updatePeriod('business_start', v || null)" />
                  <span>至</span>
                  <el-date-picker :model-value="periodData.business_end" type="date" size="small" value-format="YYYY-MM-DD" placeholder="结束" :disabled="props.readonly" @change="(v: string) => updatePeriod('business_end', v || null)" />
                </div>
              </div>
              <div class="gt-a177__period-item">
                <label>财务报告期间</label>
                <div class="gt-a177__date-range">
                  <el-date-picker :model-value="periodData.report_start" type="date" size="small" value-format="YYYY-MM-DD" placeholder="开始" :disabled="props.readonly" @change="(v: string) => updatePeriod('report_start', v || null)" />
                  <span>至</span>
                  <el-date-picker :model-value="periodData.report_end" type="date" size="small" value-format="YYYY-MM-DD" placeholder="结束" :disabled="props.readonly" @change="(v: string) => updatePeriod('report_end', v || null)" />
                </div>
              </div>
            </div>
          </el-card>

          <!-- Ch2: 独立性承诺事项 -->
          <el-card :id="'a177-ch-2'" shadow="never" class="gt-a177__card">
            <template #header>
              <div class="gt-a177__card-header">
                <span class="gt-a177__card-title">二、独立性承诺事项</span>
                <el-button size="small" text @click="handleAiFill(2)">🤖 AI</el-button>
              </div>
            </template>
            <details v-if="CHAPTER_GUIDANCE[2]" class="gt-a177__guidance"><summary>📋 编制提示</summary><div class="gt-a177__guidance-body">{{ CHAPTER_GUIDANCE[2] }}</div></details>
            <div class="gt-a177__commitments">
              <div v-for="(item, idx) in commitmentItems" :key="item.id" class="gt-a177__commit-item">
                <div class="gt-a177__commit-header">
                  <span class="gt-a177__commit-index">{{ idx + 1 }}.</span>
                  <span class="gt-a177__commit-label">{{ item.label }}</span>
                </div>
                <div class="gt-a177__commit-actions">
                  <el-radio-group :model-value="item.answer" :disabled="props.readonly" @change="(v: any) => updateCommitment(item.id, 'answer', v)">
                    <el-radio value="Y">是（无威胁）</el-radio>
                    <el-radio value="N">否（存在威胁）</el-radio>
                  </el-radio-group>
                </div>
                <div v-if="item.answer === 'N'" class="gt-a177__commit-explain">
                  <el-input :model-value="item.explanation || ''" type="textarea" :autosize="{ minRows: 2 }" placeholder="请简述具体情况及已采取的防范措施" :disabled="props.readonly" @change="(v: string) => updateCommitment(item.id, 'explanation', v)" />
                </div>
              </div>
            </div>
          </el-card>

          <!-- Ch3: 签字确认表 -->
          <el-card :id="'a177-ch-3'" shadow="never" class="gt-a177__card">
            <template #header>
              <div class="gt-a177__card-header">
                <span class="gt-a177__card-title">三、项目组成员签字确认</span>
                <div class="gt-a177__card-actions">
                  <el-button v-if="!props.readonly" type="warning" size="small" @click="handleSendConfirmation">📨 发送确认</el-button>
                  <el-button v-if="!props.readonly" type="primary" size="small" @click="addTeamMember">添加成员</el-button>
                </div>
              </div>
            </template>
            <details v-if="CHAPTER_GUIDANCE[3]" class="gt-a177__guidance"><summary>📋 编制提示</summary><div class="gt-a177__guidance-body">{{ CHAPTER_GUIDANCE[3] }}</div></details>
            <!-- Signing progress bar -->
            <div v-if="signingProgress.total > 0" class="gt-a177__signing-bar">
              <el-progress :percentage="Math.round(signingProgress.signed / signingProgress.total * 100)" :format="() => `${signingProgress.signed}/${signingProgress.total}`" />
              <el-tag v-if="signingProgress.complete" type="success" size="small">全员已签署</el-tag>
              <el-tag v-else type="warning" size="small">{{ signingProgress.total - signingProgress.signed }}人待签</el-tag>
            </div>
            <el-table :data="teamSignTable" border size="small" class="gt-a177__sign-table">
              <el-table-column label="序号" width="60" align="center">
                <template #default="scope">{{ (scope?.$index ?? 0) + 1 }}</template>
              </el-table-column>
              <el-table-column label="姓名" min-width="120">
                <template #default="scope">
                  <el-input :model-value="scope?.row?.name" size="small" placeholder="姓名" :disabled="props.readonly" @change="(v: string) => updateTeamMember(scope?.$index ?? 0, 'name', v)" />
                </template>
              </el-table-column>
              <el-table-column label="签字确认" width="120" align="center">
                <template #default="scope">
                  <el-button v-if="!scope?.row?.signed && !props.readonly" size="small" type="primary" plain @click="handleMemberSign(scope?.$index ?? 0)">确认签字</el-button>
                  <el-tag v-else-if="scope?.row?.signed" type="success" size="small">✓ 已签</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="日期" width="120">
                <template #default="scope">
                  <span v-if="scope?.row?.date" class="gt-a177__date-text">{{ scope.row.date }}</span>
                  <span v-else class="gt-a177__date-placeholder">—</span>
                </template>
              </el-table-column>
              <el-table-column v-if="!props.readonly" label="" width="50" align="center">
                <template #default="scope">
                  <el-icon class="gt-a177__delete-icon" @click="handleRemoveMember(scope?.$index ?? 0)"><Delete /></el-icon>
                </template>
              </el-table-column>
            </el-table>
          </el-card>

          <!-- Ch4: 合伙人审查确认 -->
          <el-card :id="'a177-ch-4'" shadow="never" class="gt-a177__card">
            <template #header><span class="gt-a177__card-title">四、合伙人及负责经理审查确认</span></template>
            <details v-if="CHAPTER_GUIDANCE[4]" class="gt-a177__guidance"><summary>📋 编制提示</summary><div class="gt-a177__guidance-body">{{ CHAPTER_GUIDANCE[4] }}</div></details>
            <div class="gt-a177__partner">
              <div class="gt-a177__partner-confirm">
                <label>经审查，项目组全体成员均已遵守独立性要求：</label>
                <el-radio-group :model-value="partnerSection.confirmed" :disabled="props.readonly" @change="(v: boolean | null) => updatePartner('confirmed', v)">
                  <el-radio :value="true">是</el-radio>
                  <el-radio :value="false">否</el-radio>
                </el-radio-group>
              </div>
              <div v-if="partnerSection.confirmed === false" class="gt-a177__partner-explain">
                <label>不确认原因说明：</label>
                <el-input :model-value="partnerSection.explanation || ''" type="textarea" :autosize="{ minRows: 3 }" placeholder="请说明存在的独立性问题及已采取的措施" :disabled="props.readonly" @change="(v: string) => updatePartner('explanation', v)" />
              </div>
              <!-- Signature buttons (A17-1 pattern) -->
              <el-table :data="partnerSignRows" border size="small" class="gt-a177__partner-table">
                <el-table-column label="角色" width="120" prop="role" />
                <el-table-column label="签字" min-width="150">
                  <template #default="{ row }">
                    <el-button v-if="!row.name && !props.readonly" size="small" type="primary" plain @click="handlePartnerSignConfirm(row.key)">确认签字</el-button>
                    <div v-else-if="row.name" class="gt-a177__signed-info">
                      <span>{{ row.name }}</span>
                      <span class="gt-a177__signed-date">{{ row.date || '' }}</span>
                    </div>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </el-card>

          <!-- Ch5: 威胁记录 -->
          <el-card :id="'a177-ch-5'" shadow="never" class="gt-a177__card">
            <template #header>
              <div class="gt-a177__card-header">
                <span class="gt-a177__card-title">五、独立性威胁记录（附件）</span>
                <el-button size="small" text @click="handleAiFill(5)">🤖 AI</el-button>
              </div>
            </template>
            <details v-if="CHAPTER_GUIDANCE[5]" class="gt-a177__guidance"><summary>📋 编制提示</summary><div class="gt-a177__guidance-body">{{ CHAPTER_GUIDANCE[5] }}</div></details>
            <el-collapse class="gt-a177__threat-collapse">
              <!-- 经济利益 -->
              <el-collapse-item title="1. 经济利益记录" name="economic">
                <div class="gt-a177__threat-actions">
                  <el-button v-if="!props.readonly" size="small" @click="addThreatRow('economic_interest')">添加记录</el-button>
                </div>
                <el-table :data="threatRecords.economic_interest" border size="small">
                  <el-table-column label="成员" min-width="100"><template #default="{ row, $index }"><el-input :model-value="row.member" size="small" :disabled="props.readonly" @change="(v: string) => updateThreatRow('economic_interest', $index, 'member', v)" /></template></el-table-column>
                  <el-table-column label="利益类型" min-width="100"><template #default="{ row, $index }"><el-input :model-value="row.type" size="small" :disabled="props.readonly" @change="(v: string) => updateThreatRow('economic_interest', $index, 'type', v)" /></template></el-table-column>
                  <el-table-column label="金额" width="100"><template #default="{ row, $index }"><el-input :model-value="row.amount" size="small" :disabled="props.readonly" @change="(v: string) => updateThreatRow('economic_interest', $index, 'amount', v)" /></template></el-table-column>
                  <el-table-column label="防范措施" min-width="120"><template #default="{ row, $index }"><el-input :model-value="row.measure" size="small" :disabled="props.readonly" @change="(v: string) => updateThreatRow('economic_interest', $index, 'measure', v)" /></template></el-table-column>
                  <el-table-column v-if="!props.readonly" width="50" align="center"><template #default="{ $index }"><el-icon class="gt-a177__delete-icon" @click="removeThreatRow('economic_interest', $index)"><Delete /></el-icon></template></el-table-column>
                </el-table>
              </el-collapse-item>
              <!-- 贷款担保 -->
              <el-collapse-item title="2. 贷款担保记录" name="loan">
                <div class="gt-a177__threat-actions">
                  <el-button v-if="!props.readonly" size="small" @click="addThreatRow('loan_guarantee')">添加记录</el-button>
                </div>
                <el-table :data="threatRecords.loan_guarantee" border size="small">
                  <el-table-column label="成员" min-width="100"><template #default="{ row, $index }"><el-input :model-value="row.member" size="small" :disabled="props.readonly" @change="(v: string) => updateThreatRow('loan_guarantee', $index, 'member', v)" /></template></el-table-column>
                  <el-table-column label="贷款类型" min-width="100"><template #default="{ row, $index }"><el-input :model-value="row.type" size="small" :disabled="props.readonly" @change="(v: string) => updateThreatRow('loan_guarantee', $index, 'type', v)" /></template></el-table-column>
                  <el-table-column label="金额" width="100"><template #default="{ row, $index }"><el-input :model-value="row.amount" size="small" :disabled="props.readonly" @change="(v: string) => updateThreatRow('loan_guarantee', $index, 'amount', v)" /></template></el-table-column>
                  <el-table-column label="防范措施" min-width="120"><template #default="{ row, $index }"><el-input :model-value="row.measure" size="small" :disabled="props.readonly" @change="(v: string) => updateThreatRow('loan_guarantee', $index, 'measure', v)" /></template></el-table-column>
                  <el-table-column v-if="!props.readonly" width="50" align="center"><template #default="{ $index }"><el-icon class="gt-a177__delete-icon" @click="removeThreatRow('loan_guarantee', $index)"><Delete /></el-icon></template></el-table-column>
                </el-table>
              </el-collapse-item>
              <!-- 商业关系 -->
              <el-collapse-item title="3. 商业关系记录" name="business">
                <div class="gt-a177__threat-actions">
                  <el-button v-if="!props.readonly" size="small" @click="addThreatRow('business_relation')">添加记录</el-button>
                </div>
                <el-table :data="threatRecords.business_relation" border size="small">
                  <el-table-column label="成员" min-width="100"><template #default="{ row, $index }"><el-input :model-value="row.member" size="small" :disabled="props.readonly" @change="(v: string) => updateThreatRow('business_relation', $index, 'member', v)" /></template></el-table-column>
                  <el-table-column label="关系描述" min-width="150"><template #default="{ row, $index }"><el-input :model-value="row.description" size="small" :disabled="props.readonly" @change="(v: string) => updateThreatRow('business_relation', $index, 'description', v)" /></template></el-table-column>
                  <el-table-column label="防范措施" min-width="120"><template #default="{ row, $index }"><el-input :model-value="row.measure" size="small" :disabled="props.readonly" @change="(v: string) => updateThreatRow('business_relation', $index, 'measure', v)" /></template></el-table-column>
                  <el-table-column v-if="!props.readonly" width="50" align="center"><template #default="{ $index }"><el-icon class="gt-a177__delete-icon" @click="removeThreatRow('business_relation', $index)"><Delete /></el-icon></template></el-table-column>
                </el-table>
              </el-collapse-item>
            </el-collapse>
          </el-card>
        </template>
      </div>
    </div>

    <!-- Online Edit Mode -->
    <div v-else class="gt-a177__oo-mode">
      <div v-if="ooGenerating" class="gt-a177__oo-loading"><el-icon class="is-loading" :size="24"><Loading /></el-icon><span>正在生成 Word 文档...</span></div>
      <GtOnlyOfficeSheet v-else-if="ooReady" :wp-id="props.wpId" :sheet-name="variant === 'team' ? 'A17-7' : 'A17-7A'" class="gt-a177__oo" />
      <div v-else class="gt-a177__oo-error"><el-alert type="warning" :closable="false" show-icon><template #title>Word 文档生成失败</template><span>{{ ooError || '请重试或切回结构化视图' }}</span></el-alert></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { Loading, Delete } from '@element-plus/icons-vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import {
  useA177IndependenceDeclaration,
  CHAPTER_GUIDANCE,
  DECLARATION_TEMPLATES,
  type Variant,
} from './composables/useA177IndependenceDeclaration'
import { useAuthStore } from '@/stores/auth'
import { api } from '@/services/apiProxy'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

defineOptions({ name: 'GtA177IndependenceDeclaration' })

const props = withDefaults(defineProps<{
  wpId: string
  projectId?: string
  readonly?: boolean
}>(), { readonly: false, projectId: '' })

// ─── Mode Switch ───
const mode = ref('结构化视图')
const modeOptions = ref(['结构化视图', '在线编辑'])

// ─── Composable ───
const wpIdRef = ref(props.wpId)
const projectIdRef = ref(props.projectId)
const {
  loading, variant, metaInfo, declarationText, periodData,
  commitmentItems, teamSignTable, partnerSection, threatRecords,
  projectContext, saveStatus, lastSavedAt, chapters, signingProgress,
  addTeamMember, removeTeamMember, updateTeamMember, updateCommitment,
  addThreatRow, removeThreatRow, updateThreatRow,
  updatePeriod, updatePartner, loadData, flushPendingSaves,
  initiateSigningBatch, refreshSigningProgress, aiGenerateChapter,
} = useA177IndependenceDeclaration(wpIdRef, { projectId: projectIdRef })

// ─── Navigation ───
const activeChapter = ref(1)
const navLabels: Record<number, string> = {
  1: '声明正文',
  2: '承诺事项',
  3: '签字确认',
  4: '合伙人审查',
  5: '威胁记录',
}

function scrollToChapter(n: number) {
  activeChapter.value = n
  const el = document.getElementById(`a177-ch-${n}`)
  el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

// ─── Chapter completion check ───
const chapterComplete = computed(() => ({
  1: !!(periodData.value.business_start && periodData.value.business_end),
  2: commitmentItems.value.every(item => item.answer !== null),
  3: teamSignTable.value.length > 0 && teamSignTable.value.every(r => r.signed),
  4: partnerSection.value.confirmed !== null && !!partnerSection.value.partner_sign.name,
  5: true, // optional
}))

// ─── Computed ───
const variantTitle = computed(() =>
  variant.value === 'team' ? '审计项目团队成员独立性声明书' : '专业技术委员会审核委员独立性声明书',
)

const partnerSignRows = computed(() => [
  { key: 'partner_sign', role: '项目合伙人', name: partnerSection.value.partner_sign.name, date: partnerSection.value.partner_sign.date },
  { key: 'manager_sign', role: '负责经理', name: partnerSection.value.manager_sign.name, date: partnerSection.value.manager_sign.date },
])

// ─── Declaration text update ───
function handleDeclarationChange(v: string) {
  declarationText.value = v
  // Save declaration text as item
  const prefix = variant.value === 'committee' ? 'a177a-' : 'a177-'
  // No separate save needed — text is part of the static template, but user might customize
}

// ─── Member sign via button popup (A17-1 pattern) ───
async function handleMemberSign(index: number) {
  const row = teamSignTable.value[index]
  if (!row) return
  const authStore = useAuthStore()
  const userName = authStore.user?.display_name || authStore.user?.username || '当前用户'
  try {
    await ElMessageBox.confirm(
      `<div style="line-height:1.8">
        <p><strong>操作</strong>：签署独立性声明确认</p>
        <p><strong>签署人</strong>：${userName}</p>
        <p><strong>声明内容</strong>：本人已阅读并确认遵守上述独立性承诺事项</p>
        <p style="color:#E6A23C;font-size:12px">⚠️ 此操作不可撤销</p>
      </div>`,
      '独立性声明签字确认',
      { confirmButtonText: '确认签字', cancelButtonText: '取消', type: 'warning', dangerouslyUseHTMLString: true },
    )
    const today = new Date().toISOString().slice(0, 10)
    updateTeamMember(index, 'name', row.name || userName)
    updateTeamMember(index, 'signed', true)
    updateTeamMember(index, 'date', today)
    ElMessage.success('签字确认成功')
  } catch { /* cancelled */ }
}

// ─── Partner sign via button popup ───
async function handlePartnerSignConfirm(key: string) {
  const authStore = useAuthStore()
  const userName = authStore.user?.display_name || authStore.user?.username || '当前用户'
  const role = key === 'partner_sign' ? '项目合伙人' : '负责经理'
  try {
    await ElMessageBox.confirm(
      `<div style="line-height:1.8">
        <p><strong>操作</strong>：审查确认签字</p>
        <p><strong>角色</strong>：${role}</p>
        <p><strong>签字人</strong>：${userName}</p>
        <p style="color:#E6A23C;font-size:12px">⚠️ 此操作不可撤销</p>
      </div>`,
      '审查确认签字',
      { confirmButtonText: '确认签字', cancelButtonText: '取消', type: 'warning', dangerouslyUseHTMLString: true },
    )
    const today = new Date().toISOString().slice(0, 10)
    updatePartner(key, { name: userName, date: today })
    ElMessage.success(`${role}签字确认成功`)
  } catch { /* cancelled */ }
}

// ─── Send batch signing confirmation ───
async function handleSendConfirmation() {
  try {
    await ElMessageBox.confirm(
      `<div style="line-height:1.8">
        <p>将向项目组全体成员发送<strong>独立性声明确认</strong>弹窗。</p>
        <p>每位成员将收到通知，需阅读并确认独立性承诺事项后电子签署。</p>
        <p>签署进度将实时更新在本页面。</p>
      </div>`,
      '发送独立性声明确认',
      { confirmButtonText: '确认发送', cancelButtonText: '取消', type: 'info', dangerouslyUseHTMLString: true },
    )
    await initiateSigningBatch()
  } catch { /* cancelled */ }
}

// ─── Remove member ───
async function handleRemoveMember(index: number) {
  try {
    await ElMessageBox.confirm('确认删除该成员？', '提示', { confirmButtonText: '确认', cancelButtonText: '取消', type: 'warning' })
    removeTeamMember(index)
  } catch { /* cancelled */ }
}

// ─── AI fill ───
async function handleAiFill(chapterNum: number) {
  ElMessage.info('AI 正在生成内容...')
  const content = await aiGenerateChapter(chapterNum)
  if (content) {
    ElMessage.success('AI 已生成内容')
    // For ch1, update declaration text
    if (chapterNum === 1) declarationText.value = content
  }
}

// ─── OO Mode State ───
const ooGenerating = ref(false)
const ooReady = ref(false)
const ooError = ref('')

async function handleModeChange() {
  if (mode.value === '在线编辑') {
    await flushPendingSaves()
    ooGenerating.value = true
    ooReady.value = false
    ooError.value = ''
    try {
      await api.post(`/api/workpapers/${props.wpId}/a177/generate-docx`)
      ooReady.value = true
    } catch (err: any) {
      ooError.value = err?.response?.data?.detail || err?.message || '生成失败'
    } finally {
      ooGenerating.value = false
    }
  } else if (mode.value === '结构化视图') {
    // Sync back from docx
    try {
      await api.post(`/api/workpapers/${props.wpId}/a177/sync-from-docx`)
      await loadData(props.wpId)
    } catch { /* best effort */ }
    ooReady.value = false
  }
}

// ─── OO health check ───
async function checkOOHealth() {
  try {
    const res = await api.get<any>('/api/workpapers/onlyoffice/health', { _silent: true } as any)
    if (!res?.healthy) modeOptions.value = ['结构化视图']
  } catch { modeOptions.value = ['结构化视图'] }
}

// ─── Lifecycle ───
onMounted(() => {
  loadData(props.wpId)
  checkOOHealth()
  refreshSigningProgress()
})
onBeforeUnmount(() => { flushPendingSaves() })
defineExpose({ reload: () => loadData(props.wpId) })
</script>

<style scoped>
.gt-a177 { padding: 16px; font-size: var(--wp-font-size, 13px); }
.gt-a177__toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.gt-a177__save-status { font-size: 12px; color: #909399; display: inline-flex; align-items: center; gap: 4px; }

.gt-a177__layout { display: flex; gap: 16px; }

/* Left nav */
.gt-a177__nav { position: sticky; top: 80px; width: 140px; min-width: 140px; max-height: calc(100vh - 120px); overflow-y: auto; border-right: 1px solid #ebeef5; padding-right: 8px; }
.gt-a177__nav-list { list-style: none; margin: 0; padding: 0; }
.gt-a177__nav-item { display: flex; align-items: center; gap: 6px; padding: 6px 8px; font-size: 12px; color: #606266; cursor: pointer; border-radius: 4px; transition: background-color 0.2s; }
.gt-a177__nav-item:hover { background-color: #f5f7fa; }
.gt-a177__nav-item.is-active { background-color: #ecf5ff; color: #409eff; font-weight: 500; }
.gt-a177__nav-dot { width: 6px; height: 6px; border-radius: 50%; background-color: #dcdfe6; flex-shrink: 0; }
.gt-a177__nav-dot.is-complete { background-color: #67c23a; }
.gt-a177__nav-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gt-a177__nav-progress { margin-top: 12px; padding: 8px; }
.gt-a177__nav-progress-text { font-size: 11px; color: #909399; margin-top: 4px; display: block; }

/* Right content */
.gt-a177__content { flex: 1; max-width: 960px; display: flex; flex-direction: column; gap: 16px; }
.gt-a177__card { border-radius: 8px; }
.gt-a177__card-title { font-size: 14px; font-weight: 600; color: #303133; }
.gt-a177__card-header { display: flex; align-items: center; justify-content: space-between; width: 100%; }
.gt-a177__card-actions { display: flex; gap: 8px; }

/* Guidance */
.gt-a177__guidance { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; }
.gt-a177__guidance summary { cursor: pointer; padding: 6px 10px; font-size: 12px; color: #409eff; font-weight: 500; user-select: none; }
.gt-a177__guidance-body { padding: 4px 10px 8px; font-size: 12px; color: #606266; line-height: 1.7; white-space: pre-wrap; }

/* Declaration */
.gt-a177__declaration { margin-bottom: 16px; padding: 12px 16px; background: #f5f7fa; border-radius: 6px; }
.gt-a177__declaration-prefix { font-size: 14px; margin-bottom: 8px; color: #303133; }

/* Period */
.gt-a177__period-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.gt-a177__period-item label { display: block; font-size: var(--wp-font-size, 13px); font-weight: 500; color: #606266; margin-bottom: 6px; }
.gt-a177__date-range { display: flex; align-items: center; gap: 8px; }
.gt-a177__date-range span { font-size: var(--wp-font-size, 13px); color: #909399; }

/* Commitments */
.gt-a177__commitments { display: flex; flex-direction: column; gap: 12px; }
.gt-a177__commit-item { padding: 12px 16px; border: 1px solid #ebeef5; border-radius: 6px; background: #fafafa; }
.gt-a177__commit-header { display: flex; gap: 8px; margin-bottom: 8px; }
.gt-a177__commit-index { font-weight: 600; color: #409eff; min-width: 20px; }
.gt-a177__commit-label { font-size: var(--wp-font-size, 13px); color: #303133; line-height: 1.5; }
.gt-a177__commit-actions { margin-bottom: 4px; }
.gt-a177__commit-explain { margin-top: 8px; }

/* Sign table */
.gt-a177__sign-table { width: 100%; }
.gt-a177__signing-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; }
.gt-a177__signing-bar .el-progress { flex: 1; }
.gt-a177__date-text { font-size: 12px; color: #606266; }
.gt-a177__date-placeholder { font-size: 12px; color: #c0c4cc; }
.gt-a177__delete-icon { cursor: pointer; color: #f56c6c; font-size: 16px; }
.gt-a177__delete-icon:hover { color: #e63e3e; }

/* Partner */
.gt-a177__partner { display: flex; flex-direction: column; gap: 16px; }
.gt-a177__partner-confirm { display: flex; align-items: center; gap: 12px; }
.gt-a177__partner-confirm label { font-size: var(--wp-font-size, 13px); color: #606266; }
.gt-a177__partner-explain label { display: block; font-size: var(--wp-font-size, 13px); color: #606266; margin-bottom: 6px; }
.gt-a177__partner-table { width: 100%; }
.gt-a177__signed-info { display: flex; flex-direction: column; gap: 2px; }
.gt-a177__signed-date { font-size: 11px; color: #909399; }

/* Threat */
.gt-a177__threat-collapse { border: none; }
.gt-a177__threat-actions { margin-bottom: 8px; }

/* OO */
.gt-a177__oo { height: calc(100vh - 200px); min-height: 500px; }
.gt-a177__oo-mode { min-height: 400px; }
.gt-a177__oo-loading { display: flex; align-items: center; justify-content: center; gap: 12px; padding: 80px 20px; color: #909399; font-size: 14px; }
.gt-a177__oo-error { padding: 40px 20px; }
</style>
