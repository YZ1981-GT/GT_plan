<!--
  GtA91DeficiencyLetter.vue — A9-1 向管理层通报内部控制缺陷沟通函

  7 区块卡片 + 左侧 mini 导航 + 双模式切换(结构化/OnlyOffice)
  - Section 1: 收件人 (自动填充 client_name)
  - Section 2: 正文引言 (只读, collapsible)
  - Section 3: 独立性声明 (4 sub-items Y/N + conditional textarea)
  - Section 4: 内部控制缺陷 (3 severity groups + B22B 联动)
  - Section 5: 审计委员会监督 (Y/N/NA + conditional textarea)
  - Section 6: 签发区 (firm name + date picker)
  - Section 7: 管理层回复区 (opinion + conclusion + representative + date)
-->
<template>
  <div class="gt-a91">
    <!-- Toolbar -->
    <div class="gt-a91__toolbar">
      <el-segmented v-model="mode" :options="modeOptions" size="small" />
      <span class="gt-a91__save-status">
        <template v-if="saveStatus === 'saving'">
          <el-icon class="is-loading"><Loading /></el-icon> 保存中...
        </template>
        <template v-else-if="saveStatus === 'saved'">✓ 已保存</template>
        <template v-else-if="saveStatus === 'unsaved'">○ 未保存</template>
      </span>
    </div>

    <!-- Structured View -->
    <div v-if="mode === '结构化视图'" class="gt-a91__layout">
      <!-- Left Navigation -->
      <aside class="gt-a91__nav">
        <div
          v-for="nav in navItems"
          :key="nav.id"
          class="gt-a91__nav-item"
          :class="{ 'gt-a91__nav-item--active': activeSection === nav.id }"
          @click="scrollToSection(nav.id)"
        >
          {{ nav.label }}
        </div>
      </aside>

      <!-- Main Content -->
      <main class="gt-a91__content">
        <el-skeleton v-if="loading" :rows="10" animated />
        <template v-else>
          <!-- Section 1: 收件人 -->
          <el-card id="section-addressee" class="gt-a91__card" shadow="never">
            <template #header><span class="gt-a91__card-title">收件人</span></template>
            <div class="gt-a91__addressee">
              <template v-if="projectContext.client_name">
                <span class="gt-a91__addressee-text">
                  <template v-if="props.variant === 'governance'">
                    {{ projectContext.client_name }}董事会\监事会\审计委员会：
                  </template>
                  <template v-else>
                    {{ projectContext.client_name }}总经理\财务总监\…：
                  </template>
                </span>
              </template>
              <el-input
                v-else
                :model-value="sectionData.addressee.custom_text || ''"
                placeholder="请输入收件单位"
                @change="(v: string) => updateField('addressee', 'custom_text', v)"
              />
            </div>
          </el-card>

          <!-- Section 2: 正文引言 -->
          <el-card id="section-intro" class="gt-a91__card" shadow="never">
            <template #header><span class="gt-a91__card-title">正文引言</span></template>
            <el-collapse v-model="introCollapse">
              <el-collapse-item title="审计责任与保密声明" name="intro">
                <p class="gt-a91__muted-text">
                  在审计贵公司{{ projectContext.client_name || 'XX公司' }}财务报表过程中，我们关注到以下需要向管理层通报的事项。
                </p>
                <p class="gt-a91__muted-text">
                  根据中国注册会计师审计准则第1152号——向治理层和管理层通报内部控制缺陷的规定，注册会计师应当以书面形式及时向管理层通报审计过程中识别出的、尚未引起管理层注意的其他内部控制缺陷。
                </p>
                <p class="gt-a91__muted-text">
                  本函仅供贵公司管理层使用，未经我们书面许可，不得将其内容向第三方披露。
                </p>
              </el-collapse-item>
            </el-collapse>
          </el-card>

          <!-- Section 3: 独立性声明 -->
          <el-card id="section-independence" class="gt-a91__card" shadow="never">
            <template #header><span class="gt-a91__card-title">一、独立性问题</span></template>
            <div class="gt-a91__independence">
              <!-- (一) 保持独立性 -->
              <div class="gt-a91__sub-item">
                <span class="gt-a91__sub-label">（一）审计项目组成员保持独立性</span>
                <el-radio-group
                  :model-value="sectionData.independence.team_independent"
                  @change="(v: string) => updateField('independence', 'team_independent', v)"
                >
                  <el-radio value="Y">是</el-radio>
                  <el-radio value="N">否</el-radio>
                </el-radio-group>
              </div>
              <!-- (二) 不存在影响关系 -->
              <div class="gt-a91__sub-item">
                <span class="gt-a91__sub-label">（二）不存在影响独立性的关系和事项</span>
                <el-radio-group
                  :model-value="sectionData.independence.no_relationships"
                  @change="(v: string) => updateField('independence', 'no_relationships', v)"
                >
                  <el-radio value="Y">是</el-radio>
                  <el-radio value="N">否</el-radio>
                </el-radio-group>
                <el-input
                  v-if="sectionData.independence.no_relationships === 'N'"
                  :model-value="sectionData.independence.no_relationships_detail || ''"
                  type="textarea"
                  :autosize="{ minRows: 3 }"
                  placeholder="请说明影响独立性的关系和事项"
                  class="gt-a91__conditional-textarea"
                  @change="(v: string) => updateField('independence', 'no_relationships_detail', v)"
                />
              </div>

              <!-- (三) 已采取防护措施 -->
              <div class="gt-a91__sub-item">
                <span class="gt-a91__sub-label">（三）已采取必要防护措施</span>
                <el-radio-group
                  :model-value="sectionData.independence.safeguards_taken"
                  @change="(v: string) => updateField('independence', 'safeguards_taken', v)"
                >
                  <el-radio value="Y">是</el-radio>
                  <el-radio value="N">否</el-radio>
                </el-radio-group>
              </div>

              <!-- 非审计服务声明 -->
              <div class="gt-a91__sub-item">
                <span class="gt-a91__sub-label">是否提供非审计服务</span>
                <el-radio-group
                  :model-value="sectionData.independence.non_audit_services"
                  @change="(v: string) => updateField('independence', 'non_audit_services', v)"
                >
                  <el-radio value="Y">是</el-radio>
                  <el-radio value="N">否</el-radio>
                </el-radio-group>
                <el-input
                  v-if="sectionData.independence.non_audit_services === 'Y'"
                  :model-value="sectionData.independence.non_audit_services_detail || ''"
                  type="textarea"
                  :autosize="{ minRows: 3 }"
                  placeholder="请描述提供的非审计服务内容"
                  class="gt-a91__conditional-textarea"
                  @change="(v: string) => updateField('independence', 'non_audit_services_detail', v)"
                />
              </div>
            </div>
          </el-card>

          <!-- Section 4: 内部控制缺陷 -->
          <el-card id="section-deficiency" class="gt-a91__card" shadow="never">
            <template #header><span class="gt-a91__card-title">二、内部控制缺陷</span></template>

            <!-- Guidance collapse -->
            <el-collapse v-model="guidanceCollapse" class="gt-a91__guidance-collapse">
              <el-collapse-item title="缺陷定义参考" name="def-guidance">
                <el-alert type="info" :closable="false" show-icon>
                  <template #title>缺陷严重程度定义</template>
                  重大缺陷：一个或多个控制缺陷的组合，可能导致企业严重偏离控制目标。<br />
                  重要缺陷：一个或多个控制缺陷的组合，其严重程度低于重大缺陷，但仍应引起管理层关注。<br />
                  一般缺陷：除重大缺陷和重要缺陷之外的其他缺陷。
                </el-alert>
              </el-collapse-item>
            </el-collapse>

            <!-- B22B Warning -->
            <el-alert
              v-if="b22bWarning"
              type="warning"
              :closable="false"
              show-icon
              class="gt-a91__b22b-warning"
            >
              {{ b22bWarning }}
            </el-alert>

            <!-- 3 severity sub-groups -->
            <div
              v-for="group in severityGroups"
              :key="group.key"
              class="gt-a91__severity-group"
            >
              <div class="gt-a91__severity-header">
                <h4 class="gt-a91__severity-title">{{ group.label }}</h4>
                <el-button size="small" type="primary" plain @click="addDeficiency(group.key)">
                  + 新增缺陷
                </el-button>
              </div>

              <div
                v-for="(item, idx) in deficiencyList[group.key]"
                :key="item.id"
                class="gt-a91__deficiency-card"
              >
                <div class="gt-a91__deficiency-header">
                  <span class="gt-a91__deficiency-index">缺陷 {{ idx + 1 }}</span>
                  <GtIndexChip v-if="item.indexRef" :index-ref="item.indexRef" />
                  <el-button
                    v-if="item.source === 'manual'"
                    size="small"
                    type="danger"
                    text
                    @click="removeDeficiency(group.key, idx)"
                  >
                    删除
                  </el-button>
                </div>
                <div class="gt-a91__deficiency-fields">
                  <div class="gt-a91__field">
                    <label>缺陷描述</label>
                    <el-input
                      :model-value="item.description"
                      type="textarea"
                      :autosize="{ minRows: 2 }"
                      placeholder="请描述内部控制缺陷"
                      @change="(v: string) => updateDeficiency(group.key, idx, 'description', v)"
                    />
                  </div>
                  <div class="gt-a91__field">
                    <label>影响说明</label>
                    <el-input
                      :model-value="item.impact"
                      type="textarea"
                      :autosize="{ minRows: 2 }"
                      placeholder="请说明该缺陷的影响"
                      @change="(v: string) => updateDeficiency(group.key, idx, 'impact', v)"
                    />
                  </div>
                  <div class="gt-a91__field">
                    <label>整改建议</label>
                    <div class="gt-a91__recommendation-row">
                      <el-input
                        :model-value="item.recommendation"
                        type="textarea"
                        :autosize="{ minRows: 2 }"
                        placeholder="请提出整改建议"
                        @change="(v: string) => updateDeficiency(group.key, idx, 'recommendation', v)"
                      />
                      <el-tooltip content="AI 生成整改建议即将上线" placement="top">
                        <el-button size="small" disabled class="gt-a91__ai-btn">
                          <el-icon><MagicStick /></el-icon> AI
                        </el-button>
                      </el-tooltip>
                    </div>
                  </div>
                </div>
              </div>

              <div v-if="deficiencyList[group.key].length === 0" class="gt-a91__empty-hint">
                暂无{{ group.label.replace(/（[一二三]）/, '') }}记录
              </div>
            </div>
          </el-card>

          <!-- Section 5: 审计委员会监督 -->
          <el-card id="section-committee" class="gt-a91__card" shadow="never">
            <template #header>
              <span class="gt-a91__card-title">三、审计委员会和内部审计机构对内部控制的监督无效</span>
            </template>
            <div class="gt-a91__committee">
              <div class="gt-a91__sub-item">
                <span class="gt-a91__sub-label">适用性：</span>
                <el-radio-group
                  :model-value="sectionData.committee.applicability"
                  @change="(v: string) => updateField('committee', 'applicability', v)"
                >
                  <el-radio value="Y">适用</el-radio>
                  <el-radio value="N">不适用</el-radio>
                  <el-radio value="NA">不涉及</el-radio>
                </el-radio-group>
              </div>
              <el-input
                v-if="sectionData.committee.applicability === 'Y'"
                :model-value="sectionData.committee.description || ''"
                type="textarea"
                :autosize="{ minRows: 4 }"
                placeholder="请描述审计委员会监督无效的具体情况"
                class="gt-a91__conditional-textarea"
                @change="(v: string) => updateField('committee', 'description', v)"
              />
            </div>
          </el-card>

          <!-- Section 6: 签发区 -->
          <el-card id="section-signature" class="gt-a91__card" shadow="never">
            <template #header><span class="gt-a91__card-title">签发</span></template>
            <div class="gt-a91__signature">
              <div class="gt-a91__field">
                <label>事务所</label>
                <el-input :model-value="projectContext.firm_name" size="small" disabled />
              </div>
              <div class="gt-a91__field">
                <label>签发日期</label>
                <el-date-picker
                  :model-value="sectionData.signature.date || projectContext.audit_report_date"
                  type="date"
                  size="small"
                  value-format="YYYY-MM-DD"
                  placeholder="选择签发日期"
                  @change="(v: string) => updateField('signature', 'date', v || '')"
                />
              </div>
            </div>
          </el-card>

          <!-- Section 7: 管理层回复区 -->
          <el-card v-if="props.variant !== 'governance'" id="section-response" class="gt-a91__card" shadow="never">
            <template #header><span class="gt-a91__card-title">管理层回复区</span></template>
            <div class="gt-a91__response">
              <div class="gt-a91__field">
                <label>管理层意见</label>
                <el-input
                  :model-value="sectionData.response.opinion || ''"
                  type="textarea"
                  :autosize="{ minRows: 4 }"
                  placeholder="请填写管理层对上述事项的意见"
                  @change="(v: string) => updateField('response', 'opinion', v)"
                />
              </div>
              <div class="gt-a91__field">
                <label>管理层结论</label>
                <el-input
                  :model-value="sectionData.response.conclusion || defaultConclusion"
                  type="textarea"
                  :autosize="{ minRows: 3 }"
                  placeholder="管理层结论"
                  @change="(v: string) => updateField('response', 'conclusion', v)"
                />
              </div>
              <div class="gt-a91__response-footer">
                <div class="gt-a91__field">
                  <label>授权代表签字</label>
                  <el-input
                    :model-value="sectionData.response.representative || ''"
                    size="small"
                    placeholder="签字人姓名"
                    @change="(v: string) => updateField('response', 'representative', v)"
                  />
                </div>
                <div class="gt-a91__field">
                  <label>日期</label>
                  <el-date-picker
                    :model-value="sectionData.response.response_date"
                    type="date"
                    size="small"
                    value-format="YYYY-MM-DD"
                    placeholder="选择日期"
                    @change="(v: string) => updateField('response', 'response_date', v || '')"
                  />
                </div>
              </div>
            </div>
          </el-card>

          <!-- Guidance notes -->
          <el-collapse v-model="notesCollapse" class="gt-a91__notes">
            <el-collapse-item title="编制指导" name="notes">
              <el-alert type="info" :closable="false" show-icon>
                <template #title>模板说明</template>
                本沟通函模板依据《中国注册会计师审计准则第1152号》编制。蓝色文字为编制指导，完成后应删除。各区块应根据具体审计项目情况进行调整。
              </el-alert>
            </el-collapse-item>
          </el-collapse>
        </template>
      </main>
    </div>

    <!-- Online Edit Mode -->
    <GtOnlyOfficeSheet v-else :wp-id="props.wpId" sheet-name="A9-1" class="gt-a91__oo" />
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, watch, computed, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { Loading, MagicStick } from '@element-plus/icons-vue'
import { useA91DeficiencyLetter } from './composables/useA91DeficiencyLetter'
import type { A91RenderData } from './composables/useA91DeficiencyLetter'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtIndexChip = defineAsyncComponent(() => import('./GtIndexChip.vue'))

defineOptions({ name: 'GtA91DeficiencyLetter' })

const props = withDefaults(defineProps<{
  wpId: string
  projectId?: string
  htmlData?: A91RenderData | null
  variant?: 'management' | 'governance'
}>(), { projectId: '', htmlData: null, variant: 'management' })

// ─── Mode Switch ───
const mode = ref('结构化视图')
const modeOptions = ref(['结构化视图', '在线编辑'])

// ─── Collapse states ───
const introCollapse = ref<string[]>(['intro'])
const guidanceCollapse = ref<string[]>([])
const notesCollapse = ref<string[]>([])

// ─── Navigation items ───
const allNavItems = [
  { id: 'addressee', label: '收件人' },
  { id: 'intro', label: '引言' },
  { id: 'independence', label: '独立性' },
  { id: 'deficiency', label: '缺陷' },
  { id: 'committee', label: '委员会' },
  { id: 'signature', label: '签发' },
  { id: 'response', label: '回复' },
]

const navItems = computed(() =>
  props.variant === 'governance'
    ? allNavItems.filter(n => n.id !== 'response')
    : allNavItems
)

// ─── Severity groups ───
const allSeverityGroups = [
  { key: 'major' as const, label: '（一）重大缺陷' },
  { key: 'significant' as const, label: '（二）重要缺陷' },
  { key: 'general' as const, label: '（三）一般缺陷' },
]

const severityGroups = computed(() =>
  props.variant === 'governance'
    ? allSeverityGroups.filter(g => g.key !== 'general')
    : allSeverityGroups
)

// ─── Default text ───
const defaultConclusion = '同意上述贵所就独立性问题所做的声明，并确认已知悉上述内部控制缺陷及整改建议。'

// ─── Composable ───
const {
  sectionData,
  deficiencyList,
  projectContext,
  b22bWarning,
  loading,
  saveStatus,
  activeSection,
  updateField,
  addDeficiency,
  removeDeficiency,
  updateDeficiency,
  flushPendingSaves,
  scrollToSection,
} = useA91DeficiencyLetter({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  htmlData: toRef(props, 'htmlData'),
  itemIdPrefix: props.variant === 'governance' ? 'a92' : 'a91',
})

// ─── OO health check ───
async function checkOOHealth() {
  try {
    const { api } = await import('@/services/apiProxy')
    const res = await api.get<any>('/api/workpapers/onlyoffice/health', { _silent: true } as any)
    if (!res?.healthy) {
      modeOptions.value = ['结构化视图']
    }
  } catch {
    modeOptions.value = ['结构化视图']
  }
}

// Flush pending saves before switching to OO
watch(mode, async (newMode, oldMode) => {
  if (oldMode === '结构化视图' && newMode === '在线编辑') {
    await flushPendingSaves()
  }
})

onMounted(() => { checkOOHealth() })
onBeforeUnmount(() => { flushPendingSaves() })
defineExpose({ reload: () => flushPendingSaves() })
</script>

<style scoped>
.gt-a91 { padding: 16px; }
.gt-a91__toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.gt-a91__save-status { font-size: 12px; color: #909399; display: inline-flex; align-items: center; gap: 4px; }

.gt-a91__layout { display: flex; gap: 16px; }

/* Left Navigation */
.gt-a91__nav {
  position: sticky;
  top: 80px;
  align-self: flex-start;
  width: 72px;
  min-width: 72px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  background: #f5f7fa;
  border-radius: 8px;
  padding: 8px 4px;
}
.gt-a91__nav-item {
  padding: 6px 8px;
  font-size: 12px;
  color: #606266;
  border-radius: 4px;
  cursor: pointer;
  text-align: center;
  transition: all 0.2s;
  white-space: nowrap;
}
.gt-a91__nav-item:hover { background: #e8eaed; color: #303133; }
.gt-a91__nav-item--active { background: #409eff; color: #fff; font-weight: 500; }

/* Main Content */
.gt-a91__content { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 16px; max-width: 860px; }
.gt-a91__card { border-radius: 8px; }
.gt-a91__card-title { font-size: 15px; font-weight: 600; color: #303133; }

/* Section 1: Addressee */
.gt-a91__addressee { padding: 4px 0; }
.gt-a91__addressee-text { font-size: 14px; color: #303133; font-weight: 500; }

/* Section 2: Intro */
.gt-a91__muted-text { font-size: var(--wp-font-size, 13px); color: #909399; line-height: 1.8; margin: 0 0 12px; }
.gt-a91__muted-text:last-child { margin-bottom: 0; }

/* Section 3: Independence */
.gt-a91__independence { display: flex; flex-direction: column; gap: 16px; }
.gt-a91__sub-item { display: flex; flex-direction: column; gap: 8px; }
.gt-a91__sub-label { font-size: 14px; font-weight: 500; color: #303133; }
.gt-a91__conditional-textarea { margin-top: 4px; }

/* Section 4: Deficiency */
.gt-a91__guidance-collapse { margin-bottom: 16px; }
.gt-a91__b22b-warning { margin-bottom: 16px; border-radius: 6px; }
.gt-a91__severity-group { margin-bottom: 20px; }
.gt-a91__severity-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.gt-a91__severity-title { font-size: 14px; font-weight: 600; color: #303133; margin: 0; }
.gt-a91__deficiency-card {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 12px;
  background: #fafbfc;
}
.gt-a91__deficiency-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.gt-a91__deficiency-index { font-size: var(--wp-font-size, 13px); font-weight: 600; color: #409eff; }
.gt-a91__deficiency-fields { display: flex; flex-direction: column; gap: 12px; }
.gt-a91__recommendation-row { display: flex; gap: 8px; align-items: flex-start; }
.gt-a91__recommendation-row .el-textarea { flex: 1; }
.gt-a91__ai-btn { margin-top: 4px; }
.gt-a91__empty-hint { font-size: var(--wp-font-size, 13px); color: #c0c4cc; text-align: center; padding: 12px 0; }

/* Section 5: Committee */
.gt-a91__committee { display: flex; flex-direction: column; gap: 12px; }

/* Section 6: Signature */
.gt-a91__signature { display: flex; gap: 16px; flex-wrap: wrap; }

/* Section 7: Response */
.gt-a91__response { display: flex; flex-direction: column; gap: 16px; }
.gt-a91__response-footer { display: flex; gap: 16px; flex-wrap: wrap; }

/* Common field */
.gt-a91__field { display: flex; flex-direction: column; gap: 4px; min-width: 180px; }
.gt-a91__field label { font-size: 12px; color: #909399; }

/* Notes */
.gt-a91__notes { margin-top: 0; }

/* OO */
.gt-a91__oo { height: calc(100vh - 200px); min-height: 500px; }
</style>
