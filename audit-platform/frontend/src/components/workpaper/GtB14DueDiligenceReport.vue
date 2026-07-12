<!--
  GtB14DueDiligenceReport.vue — B1-4 尽职调查（预备调查）报告

  el-segmented 双模式(结构化/在线编辑) + el-segmented 变体(标准版/简化版) +
  左侧导航(180px sticky scrollspy 13章) + 11~13 章折叠卡片(textarea/table/mixed) +
  签字区(partner/manager/report_date) + GtIndexChip(B15/B22A/B50)
-->
<template>
  <div class="gt-b14">
    <!-- Toolbar -->
    <div class="gt-b14__toolbar">
      <el-segmented v-model="mode" :options="modeOptions" size="small" />
      <el-segmented v-model="variantLabel" :options="variantOptions" size="small" class="gt-b14__variant" />
      <span class="gt-b14__save-status">
        <template v-if="saveStatus === 'saving'">
          <el-icon class="is-loading"><Loading /></el-icon> 保存中...
        </template>
        <template v-else-if="saveStatus === 'saved'">✓ 已保存</template>
        <template v-else>○ 未保存</template>
      </span>
    </div>

    <!-- Structured View -->
    <div v-if="mode === '结构化视图'" class="gt-b14__layout">
      <!-- Left Navigation (180px sticky) -->
      <nav class="gt-b14__nav">
        <ul class="gt-b14__nav-list">
          <li
            v-for="ch in visibleChapterList"
            :key="ch.id"
            class="gt-b14__nav-item"
            :class="{ 'is-active': activeChapter === ch.id }"
            @click="scrollToChapter(ch.id)"
          >
            <span class="gt-b14__nav-dot" :class="completionStatus[ch.id] ? 'is-complete' : ''" />
            <span class="gt-b14__nav-title">{{ ch.navLabel }}</span>
          </li>
        </ul>
        <el-progress :percentage="overallProgress" :stroke-width="6" class="gt-b14__progress" />
      </nav>

      <!-- Right Content -->
      <main class="gt-b14__content">
        <el-collapse v-model="expandedChapters" class="gt-b14__chapters">
          <template v-for="ch in allChapterMeta" :key="ch.id">
            <el-collapse-item
              v-show="chapters[ch.id]?.visible !== false"
              :name="ch.id"
              :id="`b14-chapter-${ch.id}`"
              class="gt-b14__chapter-item"
            >
              <template #title>
                <div class="gt-b14__chapter-header">
                  <span class="gt-b14__chapter-title">{{ ch.title }}</span>
                  <GtIndexChip v-if="ch.id === 'ch6' && crossRefs.b15" :wp-id="crossRefs.b15" label="B15" />
                  <GtIndexChip v-if="ch.id === 'ch9' && crossRefs.b22a" :wp-id="crossRefs.b22a" label="B22A" />
                  <GtIndexChip v-if="ch.id === 'ch13' && crossRefs.b50" :wp-id="crossRefs.b50" label="B50" />
                </div>
              </template>

              <!-- textarea type -->
              <div v-if="chapters[ch.id]?.type === 'textarea'" class="gt-b14__textarea-wrap">
                <el-input
                  :model-value="chapters[ch.id]?.content || ''"
                  type="textarea"
                  :autosize="{ minRows: 4 }"
                  :placeholder="`请输入${ch.title}相关内容`"
                  @change="(v: string) => updateTextarea(ch.id, 'content', v)"
                />
                <el-dropdown v-if="aiEnabled" trigger="click" class="gt-b14__ai-btn" @command="(cmd: string) => handleAiClick(ch.id, 'content', cmd)">
                  <el-button size="small" :loading="aiLoading && aiTargetChapterId === ch.id && aiTargetField === 'content'">
                    🤖 AI 生成
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="generate">✨ 生成</el-dropdown-item>
                      <el-dropdown-item command="polish" :disabled="!chapters[ch.id]?.content">🖊️ 润色</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
                <el-tooltip v-else content="AI 服务暂不可用" placement="top">
                  <el-button size="small" disabled class="gt-b14__ai-btn">🤖 AI</el-button>
                </el-tooltip>
              </div>

              <!-- table type -->
              <div v-else-if="chapters[ch.id]?.type === 'table'" class="gt-b14__table-wrap">
                <el-table :data="chapters[ch.id]?.rows || []" border size="small">
                  <el-table-column
                    v-for="col in getTableColumns(ch.id)"
                    :key="col.key"
                    :label="col.label"
                    :width="col.width"
                    :min-width="col.width ? undefined : 120"
                  >
                    <template #default="{ row, $index }">
                      <el-input
                        :model-value="row[col.key] || ''"
                        size="small"
                        @change="(v: string) => handleTableCellEdit(ch.id, chapters[ch.id]!.table_id!, $index, col.key, v)"
                      />
                    </template>
                  </el-table-column>
                  <el-table-column label="操作" width="60" align="center">
                    <template #default="{ $index }">
                      <el-button type="danger" link size="small" @click="removeTableRow(ch.id, chapters[ch.id]!.table_id!, $index)">删除</el-button>
                    </template>
                  </el-table-column>
                </el-table>
                <el-button size="small" type="primary" plain @click="addTableRow(ch.id, chapters[ch.id]!.table_id!)">+ 添加行</el-button>
              </div>

              <!-- mixed type -->
              <div v-else-if="chapters[ch.id]?.type === 'mixed'" class="gt-b14__mixed-wrap">
                <template v-for="sec in chapters[ch.id]?.sections || []" :key="sec.id">
                  <el-divider content-position="left">{{ sec.title }}</el-divider>
                  <!-- section textarea -->
                  <div v-if="sec.type === 'textarea'" class="gt-b14__textarea-wrap">
                    <el-input
                      :model-value="sec.content || ''"
                      type="textarea"
                      :autosize="{ minRows: 3 }"
                      :placeholder="`请输入${sec.title}相关内容`"
                      @change="(v: string) => updateTextarea(ch.id, sec.id, v)"
                    />
                    <el-dropdown v-if="aiEnabled" trigger="click" class="gt-b14__ai-btn" @command="(cmd: string) => handleAiClick(ch.id, sec.id, cmd)">
                      <el-button size="small" :loading="aiLoading && aiTargetChapterId === ch.id && aiTargetField === sec.id">
                        🤖 AI 生成
                      </el-button>
                      <template #dropdown>
                        <el-dropdown-menu>
                          <el-dropdown-item command="generate">✨ 生成</el-dropdown-item>
                          <el-dropdown-item command="polish" :disabled="!sec.content">🖊️ 润色</el-dropdown-item>
                        </el-dropdown-menu>
                      </template>
                    </el-dropdown>
                    <el-tooltip v-else content="AI 服务暂不可用" placement="top">
                      <el-button size="small" disabled class="gt-b14__ai-btn">🤖 AI</el-button>
                    </el-tooltip>
                  </div>
                  <!-- section table -->
                  <div v-else-if="sec.type === 'table' && sec.table_id" class="gt-b14__table-wrap">
                    <el-table :data="sec.rows || []" border size="small">
                      <el-table-column
                        v-for="col in getTableColumns(ch.id, sec.table_id)"
                        :key="col.key"
                        :label="col.label"
                        :width="col.width"
                        :min-width="col.width ? undefined : 120"
                      >
                        <template #default="{ row, $index }">
                          <el-input
                            :model-value="row[col.key] || ''"
                            size="small"
                            @change="(v: string) => handleTableCellEdit(ch.id, sec.table_id!, $index, col.key, v)"
                          />
                        </template>
                      </el-table-column>
                      <el-table-column label="操作" width="60" align="center">
                        <template #default="{ $index }">
                          <el-button type="danger" link size="small" @click="removeTableRow(ch.id, sec.table_id!, $index)">删除</el-button>
                        </template>
                      </el-table-column>
                    </el-table>
                    <el-button size="small" type="primary" plain @click="addTableRow(ch.id, sec.table_id!)">+ 添加行</el-button>
                  </div>
                </template>
              </div>
            </el-collapse-item>
          </template>
        </el-collapse>

        <!-- Signature Card -->
        <el-card shadow="never" class="gt-b14__signature-card">
          <template #header><span class="gt-b14__card-title">签字区</span></template>
          <div class="gt-b14__sig-grid">
            <div class="gt-b14__sig-row">
              <span class="gt-b14__sig-label">项目合伙人</span>
              <el-input :model-value="signature.partner || ''" size="small" placeholder="签名" @change="(v: string) => updateSignature('partner', v)" />
              <el-date-picker :model-value="signature.partner_date" type="date" size="small" value-format="YYYY-MM-DD" placeholder="日期" @change="(v: string) => updateSignature('partner_date', v || '')" />
            </div>
            <div class="gt-b14__sig-row">
              <span class="gt-b14__sig-label">项目经理</span>
              <el-input :model-value="signature.manager || ''" size="small" placeholder="签名" @change="(v: string) => updateSignature('manager', v)" />
              <el-date-picker :model-value="signature.manager_date" type="date" size="small" value-format="YYYY-MM-DD" placeholder="日期" @change="(v: string) => updateSignature('manager_date', v || '')" />
            </div>
            <div class="gt-b14__sig-row">
              <span class="gt-b14__sig-label">报告日期</span>
              <el-date-picker :model-value="signature.report_date" type="date" size="small" value-format="YYYY-MM-DD" placeholder="选择日期" @change="(v: string) => updateSignature('report_date', v || '')" />
            </div>
          </div>
        </el-card>
      </main>
    </div>

    <!-- Online Edit Mode -->
    <GtOnlyOfficeSheet v-else-if="mode === '在线编辑'" :wp-id="props.wpId" sheet-name="B1-4" class="gt-b14__oo" />

    <!-- AI 建议稿弹窗 -->
    <el-dialog v-model="aiDialogVisible" title="AI 建议稿" width="600px" :close-on-click-modal="false">
      <div v-if="aiLoading" class="gt-b14__ai-loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>正在生成建议稿...</span>
      </div>
      <div v-else-if="aiError" class="gt-b14__ai-error">{{ aiError }}</div>
      <el-input v-else-if="aiDraft" v-model="aiDraft" type="textarea" readonly :autosize="{ minRows: 6, maxRows: 16 }" />
      <template #footer>
        <el-button @click="aiDialogVisible = false">取消</el-button>
        <el-button v-if="aiError" type="warning" @click="handleAiClick(aiTargetChapterId, aiTargetField, aiMode)">重试</el-button>
        <el-button type="primary" :disabled="!aiDraft || aiLoading" @click="adoptAiDraft">采纳</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { toRef } from 'vue'
import { ElMessage } from 'element-plus'
import { useB14DueDiligence, type B14RenderData, type B14ChapterData } from './composables/useB14DueDiligence'
import { useB14Navigation } from './composables/useB14Navigation'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtIndexChip = defineAsyncComponent(() => import('./GtIndexChip.vue'))

defineOptions({ name: 'GtB14DueDiligenceReport' })

const props = withDefaults(defineProps<{
  wpId: string
  projectId?: string
  htmlData?: B14RenderData | null
}>(), { projectId: '', htmlData: null })

// ─── Mode & Variant ───
const mode = ref('结构化视图')
const modeOptions = ref(['结构化视图', '在线编辑'])
const variantOptions = ['标准版', '简化版']
const variantLabel = ref('标准版')

// ─── Composable ───
const {
  chapters, variant, signature, projectContext, saveStatus, loading,
  updateTextarea, updateTableRows, addTableRow, removeTableRow,
  setVariant, updateSignature, flushPendingSaves, loadData,
} = useB14DueDiligence({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  htmlData: toRef(props, 'htmlData'),
})

// ─── Navigation ───
const { activeChapter, scrollToChapter, completionStatus, overallProgress } = useB14Navigation({
  chapters,
  variant,
})

// ─── AI Assist State ───
const aiEnabled = ref(false)
const aiLoading = ref(false)
const aiDialogVisible = ref(false)
const aiDraft = ref('')
const aiError = ref('')
const aiMode = ref<'generate' | 'polish'>('generate')
const aiTargetChapterId = ref('')
const aiTargetField = ref('')

// ─── Variant sync ───
watch(variant, (v) => { variantLabel.value = v === 'standard' ? '标准版' : '简化版' }, { immediate: true })
watch(variantLabel, (label) => {
  const v = label === '标准版' ? 'standard' : 'simplified'
  if (v !== variant.value) setVariant(v)
})

// ─── Chapter metadata ───
const allChapterMeta = [
  { id: 'ch1', title: '一、序言', navLabel: '序言' },
  { id: 'ch2', title: '二、报告概要', navLabel: '报告概要' },
  { id: 'ch3', title: '三、释义', navLabel: '释义' },
  { id: 'ch4', title: '四、公司基本情况', navLabel: '基本情况' },
  { id: 'ch5', title: '五、公司经营情况', navLabel: '经营情况' },
  { id: 'ch6', title: '六、财务信息分析', navLabel: '财务分析' },
  { id: 'ch7', title: '七、同行业比较', navLabel: '同行比较' },
  { id: 'ch8', title: '八、税项', navLabel: '税项' },
  { id: 'ch9', title: '九、内部控制', navLabel: '内部控制' },
  { id: 'ch10', title: '十、关联方关系及交易', navLabel: '关联方' },
  { id: 'ch11', title: '十一、上市条件分析', navLabel: '上市条件' },
  { id: 'ch12', title: '十二、财务尽职调查的结果', navLabel: '调查结果' },
  { id: 'ch13', title: '十三、主要问题及建议', navLabel: '问题建议' },
]

const visibleChapterList = computed(() =>
  allChapterMeta.filter(ch => chapters.value[ch.id]?.visible !== false),
)

// ─── Default expanded ───
const expandedChapters = ref<string[]>(['ch1', 'ch2'])

// ─── Cross-references (loaded from projectContext or API) ───
const crossRefs = ref<{ b15?: string; b22a?: string; b50?: string }>({})

// ─── Table schemas ───
const TABLE_SCHEMAS: Record<string, { key: string; label: string; width?: number }[]> = {
  team: [
    { key: 'role', label: '角色', width: 120 },
    { key: 'name', label: '人员', width: 100 },
    { key: 'duty', label: '职责' },
  ],
  shareholders: [
    { key: 'name', label: '股东名称', width: 150 },
    { key: 'ratio', label: '持股比例(%)', width: 100 },
    { key: 'contribution', label: '出资方式', width: 120 },
  ],
  customers: [
    { key: 'name', label: '客户名称', width: 150 },
    { key: 'revenue_ratio', label: '收入占比(%)', width: 100 },
    { key: 'aging', label: '账龄', width: 100 },
  ],
  suppliers: [
    { key: 'name', label: '供应商名称', width: 150 },
    { key: 'purchase_ratio', label: '采购占比(%)', width: 100 },
  ],
  industry_comparison: [
    { key: 'indicator', label: '指标', width: 120 },
    { key: 'target', label: '目标公司', width: 120 },
    { key: 'peer1', label: '对标公司1', width: 120 },
    { key: 'peer2', label: '对标公司2', width: 120 },
  ],
  related_parties: [
    { key: 'name', label: '关联方名称', width: 150 },
    { key: 'relationship', label: '关联关系', width: 120 },
    { key: 'transaction_type', label: '交易类型', width: 120 },
    { key: 'amount', label: '交易金额(元)', width: 120 },
  ],
}

function getTableColumns(chapterId: string, tableId?: string): { key: string; label: string; width?: number }[] {
  const ch = chapters.value[chapterId]
  if (!ch) return []
  const tid = tableId || ch.table_id
  if (tid && TABLE_SCHEMAS[tid]) return TABLE_SCHEMAS[tid]
  // Fallback: derive from chapter columns if available
  if (ch.type === 'mixed' && ch.sections) {
    const sec = ch.sections.find(s => s.table_id === tableId)
    if (sec?.columns) return sec.columns as any[]
  }
  return []
}

function handleTableCellEdit(chapterId: string, tableId: string, rowIndex: number, field: string, value: string) {
  const ch = chapters.value[chapterId]
  if (!ch) return
  let rows: Record<string, any>[] | undefined
  if (ch.type === 'table') {
    rows = ch.rows ? [...ch.rows] : []
  } else if (ch.type === 'mixed' && ch.sections) {
    const sec = ch.sections.find(s => s.table_id === tableId)
    rows = sec?.rows ? [...sec.rows] : []
  }
  if (rows && rowIndex >= 0 && rowIndex < rows.length) {
    rows[rowIndex] = { ...rows[rowIndex], [field]: value }
    updateTableRows(chapterId, tableId, rows)
  }
}

// ─── AI Assist ───
async function checkAiEnabled() {
  try {
    const { api } = await import('@/services/apiProxy')
    const resp = await api.get('/api/feature-flags', { _silent: true } as any) as any
    const flags = resp?.flags || resp || {}
    aiEnabled.value = !!flags.WP_AI_SERVICE_ENABLED
  } catch { aiEnabled.value = false }
}

function handleAiClick(chapterId: string, field: string, mode: string) {
  aiTargetChapterId.value = chapterId
  aiTargetField.value = field
  aiMode.value = mode as 'generate' | 'polish'
  aiDraft.value = ''
  aiError.value = ''

  // Get current content for polish mode
  const currentContent = getFieldContent(chapterId, field)
  doAiGenerate(chapterId, field, mode as 'generate' | 'polish', currentContent)
}

function getFieldContent(chapterId: string, field: string): string {
  const ch = chapters.value[chapterId]
  if (!ch) return ''
  if (field === 'content') return ch.content || ''
  if (ch.type === 'mixed' && ch.sections) {
    const sec = ch.sections.find(s => s.id === field)
    return sec?.content || ''
  }
  return ''
}

async function doAiGenerate(chapterId: string, field: string, mode: 'generate' | 'polish', currentContent: string) {
  aiLoading.value = true
  aiDraft.value = ''
  aiError.value = ''
  try {
    const { api } = await import('@/services/apiProxy')
    const result = await api.post(
      `/api/projects/${props.projectId}/b14/chapters/${chapterId}/ai-generate`,
      { mode, user_hint: '', current_content: currentContent },
    ) as { draft?: string; error?: string }
    if (result?.error) { aiError.value = result.error }
    else if (result?.draft) { aiDraft.value = result.draft }
    else { aiError.value = '未获取到生成内容' }
  } catch (err: any) {
    aiError.value = err?.message || 'AI 服务请求失败'
  } finally {
    aiLoading.value = false
  }
  aiDialogVisible.value = true
}

function adoptAiDraft() {
  if (aiDraft.value && aiTargetChapterId.value) {
    updateTextarea(aiTargetChapterId.value, aiTargetField.value, aiDraft.value)
    aiDialogVisible.value = false
    ElMessage.success('已采纳 AI 建议稿')
  }
}

// ─── OO health check ───
async function checkOOHealth() {
  try {
    const { api } = await import('@/services/apiProxy')
    const res = await api.get<any>('/api/workpapers/onlyoffice/health', { _silent: true } as any)
    if (!res?.healthy) modeOptions.value = ['结构化视图']
  } catch {
    modeOptions.value = ['结构化视图']
  }
}

// ─── Load cross-references ───
async function loadCrossRefs() {
  if (!props.projectId) return
  try {
    const { api } = await import('@/services/apiProxy')
    const res = await api.get<any>(`/api/projects/${props.projectId}/workpapers/cross-refs`, { _silent: true } as any)
    if (res) {
      crossRefs.value = {
        b15: res.B15 || res.b15 || undefined,
        b22a: res['B22A'] || res.b22a || undefined,
        b50: res.B50 || res.b50 || undefined,
      }
    }
  } catch { /* silent */ }
}

// Flush before switching to OO
watch(mode, async (newMode, oldMode) => {
  if (oldMode === '结构化视图' && newMode === '在线编辑') {
    await flushPendingSaves()
  }
})

// ─── Self-load (bundle embed scenario) ───
onMounted(async () => {
  checkOOHealth()
  loadCrossRefs()
  checkAiEnabled()
  if (!props.htmlData) {
    await loadData()
  }
})

onBeforeUnmount(() => { flushPendingSaves() })
defineExpose({ reload: () => flushPendingSaves() })
</script>

<style scoped>
.gt-b14 { padding: 16px; }
.gt-b14__toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
.gt-b14__variant { margin-left: 4px; }
.gt-b14__save-status { font-size: 12px; color: #909399; display: inline-flex; align-items: center; gap: 4px; margin-left: auto; }

.gt-b14__layout { display: flex; gap: 16px; }

/* Left nav 180px sticky */
.gt-b14__nav {
  position: sticky;
  top: 80px;
  width: 180px;
  min-width: 180px;
  max-height: calc(100vh - 120px);
  overflow-y: auto;
  border-right: 1px solid #ebeef5;
  padding-right: 8px;
}
.gt-b14__nav-list { list-style: none; margin: 0; padding: 0; }
.gt-b14__nav-item {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 8px; font-size: 12px; color: #606266;
  cursor: pointer; border-radius: 4px; transition: background 0.2s;
}
.gt-b14__nav-item:hover { background: #f5f7fa; }
.gt-b14__nav-item.is-active { background: #ecf5ff; color: #409eff; font-weight: 500; }
.gt-b14__nav-dot { width: 6px; height: 6px; border-radius: 50%; background: #dcdfe6; flex-shrink: 0; }
.gt-b14__nav-dot.is-complete { background: #67c23a; }
.gt-b14__nav-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gt-b14__progress { margin-top: 12px; padding: 0 8px; }

/* Right content */
.gt-b14__content { flex: 1; max-width: 1000px; display: flex; flex-direction: column; gap: 12px; }
.gt-b14__chapters { border: none; }
.gt-b14__chapter-item { margin-bottom: 8px; }
.gt-b14__chapter-header { display: flex; align-items: center; gap: 8px; width: 100%; }
.gt-b14__chapter-title { font-size: 14px; font-weight: 600; color: #303133; }

/* Textarea */
.gt-b14__textarea-wrap { position: relative; margin-bottom: 8px; }
.gt-b14__ai-btn { position: absolute; top: 4px; right: 4px; opacity: 0.6; }
.gt-b14__ai-btn:hover { opacity: 1; }

/* AI dialog */
.gt-b14__ai-loading { display: flex; align-items: center; gap: 8px; padding: 24px 0; justify-content: center; color: #409eff; }
.gt-b14__ai-error { color: #f56c6c; padding: 12px 0; }

/* Table */
.gt-b14__table-wrap { display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }

/* Mixed */
.gt-b14__mixed-wrap { display: flex; flex-direction: column; }

/* Signature card */
.gt-b14__signature-card { border-radius: 8px; margin-top: 8px; }
.gt-b14__card-title { font-size: 15px; font-weight: 600; color: #303133; }
.gt-b14__sig-grid { display: flex; flex-direction: column; gap: 12px; }
.gt-b14__sig-row { display: flex; align-items: center; gap: 12px; }
.gt-b14__sig-label { width: 80px; font-size: var(--wp-font-size, 13px); color: #606266; flex-shrink: 0; }

/* OO */
.gt-b14__oo { height: calc(100vh - 200px); min-height: 500px; }
</style>
