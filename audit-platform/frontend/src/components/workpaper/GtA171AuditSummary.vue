<!--
  GtA171AuditSummary.vue — A17-1 重大事项概要汇总

  el-segmented 双模式 + 左侧导航(scrollspy 16章) + 签字表(10×3) +
  16章折叠卡片(textarea/table/yn) + GtIndexChip(B50/A13/A1-15)
-->
<template>
  <div class="gt-a171">
    <!-- Toolbar -->
    <div class="gt-a171__toolbar">
      <el-segmented v-model="mode" :options="modeOptions" size="small" />
      <span class="gt-a171__save-status">
        <template v-if="saveStatus === 'saving'">
          <el-icon class="is-loading"><Loading /></el-icon> 保存中...
        </template>
        <template v-else-if="saveStatus === 'saved'">✓ 已保存</template>
        <template v-else-if="saveStatus === 'unsaved'">○ 未保存</template>
      </span>
    </div>

    <!-- Structured View -->
    <div v-if="mode === '结构化视图'" class="gt-a171__layout">
      <!-- Left Navigation Sidebar -->
      <nav class="gt-a171__nav">
        <ul class="gt-a171__nav-list">
          <li
            v-for="n in 16"
            :key="n"
            class="gt-a171__nav-item"
            :class="{ 'is-active': activeChapter === n }"
            @click="scrollToChapter(n)"
          >
            <span class="gt-a171__nav-dot" :class="{ 'is-complete': completionStatus[n] }" />
            <span class="gt-a171__nav-title">{{ getNavLabel(n) }}</span>
          </li>
        </ul>
      </nav>

      <!-- Right Content Area -->
      <div class="gt-a171__content">
        <!-- Signature Table -->
        <el-card shadow="never" class="gt-a171__signature-card">
          <template #header><span class="gt-a171__card-title">签字确认</span></template>
          <div class="gt-a171__sig-grid">
            <div
              v-for="(row, idx) in visibleSignatureRows"
              :key="idx"
              class="gt-a171__sig-item"
            >
              <div class="gt-a171__sig-role">{{ row.role }}</div>
              <el-input :model-value="row.name || ''" size="small" placeholder="姓名" @change="(v: string) => updateSignature(row.originalIndex, 'name', v)" />
              <el-date-picker :model-value="row.date" type="date" size="small" value-format="YYYY-MM-DD" placeholder="日期" @change="(v: string) => updateSignature(row.originalIndex, 'date', v || '')" />
            </div>
          </div>
        </el-card>

        <!-- 16 Chapter Cards -->
        <el-collapse v-model="expandedChapters" class="gt-a171__chapters">
          <!-- Textarea chapters: 1,2,3,4,5,7,13,14,15,16 -->
          <template v-for="n in 16" :key="n">
            <el-collapse-item
              :name="n"
              :id="`a171-chapter-${n}`"
              class="gt-a171__chapter-item"
            >
              <template #title>
                <div class="gt-a171__chapter-header">
                  <span class="gt-a171__chapter-title">{{ chapters[String(n)]?.title }}</span>
                  <!-- Cross references -->
                  <GtIndexChip
                    v-if="n === 6 && crossReferences.b50_wp_id"
                    :wp-id="crossReferences.b50_wp_id"
                    label="B50"
                  />
                  <GtIndexChip
                    v-if="n === 14 && crossReferences.a13_wp_id"
                    :wp-id="crossReferences.a13_wp_id"
                    label="A13"
                  />
                  <GtIndexChip
                    v-if="n === 14 && crossReferences.a115_wp_id"
                    :wp-id="crossReferences.a115_wp_id"
                    label="A1-15"
                  />
                  <el-button text size="small" class="gt-a171__review-btn" @click.stop="openReview(n)">💬</el-button>
                </div>
              </template>

              <!-- Chapter 3: structured component -->
              <GtA171Chapter3
                v-if="n === 3"
                :wp-id="props.wpId"
                :project-id="props.projectId || ''"
                :client-name="projectContext.client_name"
              />

              <!-- Textarea type (other chapters) -->
              <div v-else-if="chapters[String(n)]?.type === 'textarea'" class="gt-a171__textarea-wrap">
                <el-input
                  :model-value="(chapters[String(n)] as any).content || ''"
                  type="textarea"
                  :autosize="{ minRows: 4 }"
                  :placeholder="`请输入${chapters[String(n)]?.title}相关内容`"
                  @input="(v: string) => updateTextarea(n, v)"
                />
                <div class="gt-a171__btn-group">
                  <el-tooltip v-if="CHAPTER_TEMPLATE[n]" content="从源模板骨架预填（即时，无需网络）" placement="top">
                    <el-button size="small" class="gt-a171__prefill-btn" @click.stop="handleTemplatePrefill(n)">📝 模板预填</el-button>
                  </el-tooltip>
                  <el-tooltip content="基于编制提示和项目知识库 AI 辅助填充" placement="top">
                    <el-button size="small" class="gt-a171__ai-btn" @click.stop="handleAiChapterFill(n)">🤖 AI</el-button>
                  </el-tooltip>
                </div>
              </div>

              <!-- Table type: chapter 6 -->
              <div v-else-if="n === 6 && chapters['6']?.type === 'table'" class="gt-a171__table-wrap">
                <el-table :data="(chapters['6'] as any).rows" border size="small">
                  <el-table-column label="风险描述" min-width="160">
                    <template #default="{ row, $index }">
                      <el-input
                        :model-value="row.risk"
                        size="small"
                        @change="(v: string) => updateTableCell(6, $index, 'risk', v)"
                      />
                    </template>
                  </el-table-column>
                  <el-table-column label="应对措施" min-width="160">
                    <template #default="{ row, $index }">
                      <el-input
                        :model-value="row.response"
                        size="small"
                        @change="(v: string) => updateTableCell(6, $index, 'response', v)"
                      />
                    </template>
                  </el-table-column>
                  <el-table-column label="执行情况" min-width="160">
                    <template #default="{ row, $index }">
                      <el-input
                        :model-value="row.result"
                        size="small"
                        @change="(v: string) => updateTableCell(6, $index, 'result', v)"
                      />
                    </template>
                  </el-table-column>
                  <el-table-column label="结论" min-width="120">
                    <template #default="{ row, $index }">
                      <el-input
                        :model-value="row.conclusion"
                        size="small"
                        @change="(v: string) => updateTableCell(6, $index, 'conclusion', v)"
                      />
                    </template>
                  </el-table-column>
                  <el-table-column label="操作" width="60" align="center">
                    <template #default="{ $index }">
                      <el-button type="danger" link size="small" @click="removeTableRow(6, $index)">删除</el-button>
                    </template>
                  </el-table-column>
                </el-table>
                <el-button size="small" type="primary" plain class="gt-a171__add-row" @click="addTableRow(6)">+ 添加行</el-button>
              </div>

              <!-- Table type: chapter 8 -->
              <div v-else-if="n === 8 && chapters['8']?.type === 'table'" class="gt-a171__table-wrap">
                <el-table :data="(chapters['8'] as any).rows" border size="small">
                  <el-table-column label="项目" min-width="160">
                    <template #default="{ row, $index }">
                      <el-input
                        :model-value="row.item"
                        size="small"
                        @change="(v: string) => updateTableCell(8, $index, 'item', v)"
                      />
                    </template>
                  </el-table-column>
                  <el-table-column label="金额（元）" min-width="140">
                    <template #default="{ row, $index }">
                      <el-input-number
                        :model-value="row.amount"
                        :precision="2"
                        :controls="false"
                        size="small"
                        placeholder="金额"
                        @change="(v: number | undefined) => updateTableCell(8, $index, 'amount', v ?? null)"
                      />
                    </template>
                  </el-table-column>
                  <el-table-column label="说明" min-width="160">
                    <template #default="{ row, $index }">
                      <el-input
                        :model-value="row.note"
                        size="small"
                        @change="(v: string) => updateTableCell(8, $index, 'note', v)"
                      />
                    </template>
                  </el-table-column>
                  <el-table-column label="操作" width="60" align="center">
                    <template #default="{ $index }">
                      <el-button type="danger" link size="small" @click="removeTableRow(8, $index)">删除</el-button>
                    </template>
                  </el-table-column>
                </el-table>
                <el-button size="small" type="primary" plain class="gt-a171__add-row" @click="addTableRow(8)">+ 添加行</el-button>
              </div>

              <!-- Y/N type: chapters 9,10,11,12 -->
              <div v-else-if="chapters[String(n)]?.type === 'yn'" class="gt-a171__yn-wrap">
                <el-radio-group
                  :model-value="(chapters[String(n)] as any).answer"
                  @change="(v: string) => handleYnChange(n, v as 'Y' | 'N' | null)"
                >
                  <el-radio value="Y">是</el-radio>
                  <el-radio value="N">否</el-radio>
                </el-radio-group>

                <!-- Explanation textarea (visible when answer is Y or N) -->
                <div v-if="(chapters[String(n)] as any).answer" class="gt-a171__yn-explanation">
                  <el-input
                    :model-value="(chapters[String(n)] as any).explanation || ''"
                    type="textarea"
                    :autosize="{ minRows: 2 }"
                    :placeholder="(chapters[String(n)] as any).answer === 'Y' ? '请说明详细情况' : '请简要说明原因'"
                    @change="(v: string) => updateYn(n, (chapters[String(n)] as any).answer, v || null)"
                  />
                </div>
              </div>
            </el-collapse-item>
          </template>
        </el-collapse>
      </div>
    </div>

    <!-- Online Edit Mode -->
    <GtOnlyOfficeSheet v-else :wp-id="props.wpId" sheet-name="A17-1" class="gt-a171__oo" />

    <!-- Review Panel -->
    <GtA171ReviewPanel
      :visible="reviewVisible"
      :wp-id="props.wpId"
      :chapter-num="reviewChapterNum"
      :chapter-title="reviewChapterTitle"
      :current-user="'审计员'"
      @close="reviewVisible = false"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, computed, watch, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { useA171AuditSummary, CHAPTER_TEMPLATE } from './composables/useA171AuditSummary'
import { useA171Navigation } from './composables/useA171Navigation'
import type { A171RenderData } from './composables/useA171AuditSummary'
import { ElMessage, ElMessageBox } from 'element-plus'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtIndexChip = defineAsyncComponent(() => import('./GtIndexChip.vue'))
const GtA171ReviewPanel = defineAsyncComponent(() => import('./GtA171ReviewPanel.vue'))
const GtA171Chapter3 = defineAsyncComponent(() => import('./GtA171Chapter3.vue'))

defineOptions({ name: 'GtA171AuditSummary' })

const props = withDefaults(defineProps<{
  wpId: string
  projectId?: string
  htmlData?: A171RenderData | null
}>(), { projectId: '', htmlData: null })

// ─── Mode Switch ───
const mode = ref('结构化视图')
const modeOptions = ref(['结构化视图', '在线编辑'])

// ─── Composable ───
const {
  chapters,
  signatureTable,
  crossReferences,
  projectContext,
  saveStatus,
  updateTextarea,
  updateTableRows,
  addTableRow,
  removeTableRow,
  updateYn,
  updateSignature,
  flushPendingSaves,
  prefillFromTemplate,
} = useA171AuditSummary({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  htmlData: toRef(props, 'htmlData'),
})

// ─── Navigation ───
const { activeChapter, scrollToChapter: _rawScroll, completionStatus } = useA171Navigation(chapters)

// Wrap scroll to auto-expand target chapter first
function scrollToChapter(n: number) {
  if (!expandedChapters.value.includes(n)) {
    expandedChapters.value = [...expandedChapters.value, n]
  }
  // Wait for DOM update after expand
  import('vue').then(({ nextTick }) => nextTick(() => _rawScroll(n)))
}

// ─── Collapse State: all collapsed by default ───
const expandedChapters = ref<number[]>([])

// ─── Signature visibility by business_category ───
const visibleSignatureRows = computed(() => {
  const bc = projectContext.value?.business_category || ''
  // A类: 4角色全显 | B类: 编制人+复核人+EQCR(跳过质控)=3 | C类: 编制人+复核人=2
  if (bc.startsWith('A')) {
    return signatureTable.value.map((row, idx) => ({ ...row, originalIndex: idx }))
  } else if (bc.startsWith('B')) {
    // 跳过 index 2 (质量控制复核合伙人)
    return signatureTable.value
      .filter((_, idx) => idx !== 2)
      .map((row, idx) => ({ ...row, originalIndex: idx === 2 ? 3 : idx < 2 ? idx : idx + 1 }))
  }
  // C类及其他：只显示前2个
  return signatureTable.value.slice(0, 2).map((row, idx) => ({ ...row, originalIndex: idx }))
})
// ─── Helpers ───
const CHAPTER_NAV_LABELS: Record<number, string> = {
  1: '一、审计约定范围',
  2: '二、独立性',
  3: '三、计划更新修改',
  4: '四、合伙人关注',
  5: '五、咨询及分歧',
  6: '六、风险应对执行',
  7: '七、利用专家',
  8: '八、财务报表分析',
  9: '九、关联方结论',
  10: '十、持续经营',
  11: '十一、期后事项',
  12: '十二、关键审计事项',
  13: '十三、其他信息',
  14: '十四、审计结论',
  15: '十五、特殊考虑',
  16: '十六、下年度关注',
}

function getNavLabel(n: number): string {
  return CHAPTER_NAV_LABELS[n] || `第${n}章`
}

// Handle table cell edit (update entire rows array after cell change)
function updateTableCell(chapterNum: number, rowIndex: number, field: string, value: any) {
  const ch = chapters.value[String(chapterNum)]
  if (!ch || ch.type !== 'table') return
  const rows = [...ch.rows]
  if (rowIndex >= 0 && rowIndex < rows.length) {
    rows[rowIndex] = { ...rows[rowIndex], [field]: value }
    updateTableRows(chapterNum, rows)
  }
}

// Handle Y/N radio change
function handleYnChange(chapterNum: number, answer: 'Y' | 'N' | null) {
  const ch = chapters.value[String(chapterNum)]
  if (!ch || ch.type !== 'yn') return
  updateYn(chapterNum, answer, ch.explanation)
}

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

// Flush before switching to OO
watch(mode, async (newMode, oldMode) => {
  if (oldMode === '结构化视图' && newMode === '在线编辑') {
    await flushPendingSaves()
  }
})

// ─── Self-load when htmlData not provided (bundle embed scenario) ───
async function selfLoad() {
  if (props.htmlData) return // Already hydrated via prop
  try {
    const { api } = await import('@/services/apiProxy')
    const res = await api.get<any>(
      `/api/workpapers/${props.wpId}/render-config?force_component_type=a17-1-audit-summary`,
      { _silent: true } as any,
    )
    const data = res?.sheets?.[0]?.html_data
    if (data) {
      // Trigger hydration by simulating htmlData watch
      const htmlDataRef = toRef(props, 'htmlData')
      // Direct hydration: assign to reactive state managed by composable
      // The composable's watch(htmlData, ..., { immediate: true }) won't fire for self-loaded data
      // So we need to hydrate manually or re-trigger the watch
      // Simplest: just set the internal chapters from loaded data
      if (data.chapters) {
        for (const [key, val] of Object.entries(data.chapters as Record<string, any>)) {
          const ch = chapters.value[key]
          if (!ch || !val) continue
          if (ch.type === 'textarea') (ch as any).content = val.content ?? null
          else if (ch.type === 'table') (ch as any).rows = Array.isArray(val.rows) ? val.rows : []
          else if (ch.type === 'yn') { (ch as any).answer = val.answer ?? null; (ch as any).explanation = val.explanation ?? null }
        }
      }
      if (data.signature_table && Array.isArray(data.signature_table)) {
        signatureTable.value = data.signature_table.map((r: any, i: number) => ({
          role: r.role || signatureTable.value[i]?.role || '', name: r.name ?? null, date: r.date ?? null,
        }))
      }
      if (data.cross_references) Object.assign(crossReferences.value, data.cross_references)
      if (data.project_context) Object.assign(projectContext.value, data.project_context)
    }
  } catch { /* silent */ }
}

// ─── Template Prefill Handler ───
// ─── Review Panel State ───
const reviewVisible = ref(false)
const reviewChapterNum = ref(1)
const reviewChapterTitle = ref('')

function openReview(n: number) {
  reviewChapterNum.value = n
  reviewChapterTitle.value = chapters.value[String(n)]?.title || `第${n}章`
  reviewVisible.value = true
}

function handleTemplatePrefill(chapterNum: number) {
  const ch = chapters.value[String(chapterNum)]
  if (!ch || ch.type !== 'textarea') return
  if ((ch as any).content) {
    ElMessageBox.confirm(
      '当前章节已有内容，模板预填将覆盖现有内容。确定继续？',
      '确认覆盖',
      { type: 'warning', confirmButtonText: '覆盖', cancelButtonText: '取消' },
    ).then(() => {
      prefillFromTemplate(chapterNum)
      ElMessage.success('已从模板预填')
    }).catch(() => { /* cancel */ })
    return
  }
  prefillFromTemplate(chapterNum)
  ElMessage.success('已从模板预填')
}

// ─── AI Chapter Fill (calls existing endpoint) ───
async function handleAiChapterFill(chapterNum: number) {
  try {
    const { api } = await import('@/services/apiProxy')
    const titles = chapters.value[String(chapterNum)]?.title || ''
    const res = await api.post<any>(
      `/api/workpapers/${props.wpId}/a171/ai-generate`,
      { chapter: chapterNum, chapter_title: titles, guidance: '', existing_content: (chapters.value[String(chapterNum)] as any)?.content || '', knowledge_doc_ids: [] },
      { _silent: true } as any,
    )
    const content = res?.content || ''
    if (content) {
      updateTextarea(chapterNum, content)
      ElMessage.success('AI 已生成内容')
    } else {
      ElMessage.info('AI 未生成有效内容，请检查 LLM 服务')
    }
  } catch (err: any) {
    const detail = err?.response?.data?.detail
    const msg = typeof detail === 'string' ? detail : (err?.message || '生成失败')
    ElMessage.warning(`AI 生成失败：${msg}`)
  }
}

onMounted(() => { checkOOHealth(); selfLoad() })
onBeforeUnmount(() => { flushPendingSaves() })
defineExpose({ reload: () => flushPendingSaves() })
</script>

<style scoped>
.gt-a171 { padding: 16px; font-size: 13px; }
.gt-a171__toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.gt-a171__save-status { font-size: 12px; color: #909399; display: inline-flex; align-items: center; gap: 4px; }

/* Layout: left nav + right content */
.gt-a171__layout { display: flex; gap: 16px; }

/* Left navigation */
.gt-a171__nav {
  position: sticky;
  top: 80px;
  width: 160px;
  min-width: 160px;
  max-height: calc(100vh - 120px);
  overflow-y: auto;
  border-right: 1px solid #ebeef5;
  padding-right: 8px;
}
.gt-a171__nav-list { list-style: none; margin: 0; padding: 0; }
.gt-a171__nav-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 8px;
  font-size: 12px;
  color: #606266;
  cursor: pointer;
  border-radius: 4px;
  transition: background-color 0.2s;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.gt-a171__nav-item:hover { background-color: #f5f7fa; }
.gt-a171__nav-item.is-active { background-color: #ecf5ff; color: #409eff; font-weight: 500; }

.gt-a171__nav-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background-color: #dcdfe6;
  flex-shrink: 0;
}
.gt-a171__nav-dot.is-complete { background-color: #67c23a; }
.gt-a171__nav-title { overflow: hidden; text-overflow: ellipsis; }

/* Right content */
.gt-a171__content { flex: 1; max-width: 960px; display: flex; flex-direction: column; gap: 16px; }

/* Signature card */
.gt-a171__signature-card { border-radius: 8px; }
.gt-a171__card-title { font-size: 14px; font-weight: 600; color: #303133; }
.gt-a171__sig-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.gt-a171__sig-item { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border: 1px solid #ebeef5; border-radius: 6px; background: #fafafa; font-size: 13px; }
.gt-a171__sig-role { font-size: 13px; font-weight: 500; color: #606266; min-width: 110px; white-space: nowrap; flex-shrink: 0; }

/* Chapters */
.gt-a171__chapters { border: none; }
.gt-a171__chapter-item { margin-bottom: 8px; }
.gt-a171__chapter-header { display: flex; align-items: center; gap: 8px; width: 100%; }
.gt-a171__chapter-title { font-size: 14px; font-weight: 600; color: #303133; }

/* Textarea */
.gt-a171__textarea-wrap { position: relative; }
.gt-a171__btn-group { position: absolute; top: 4px; right: 4px; z-index: 10; display: flex; gap: 4px; }
.gt-a171__ai-btn { opacity: 0.7; }
.gt-a171__ai-btn:hover { opacity: 1; }
.gt-a171__prefill-btn { opacity: 0.7; }
.gt-a171__prefill-btn:hover { opacity: 1; }
.gt-a171__review-btn { margin-left: auto; opacity: 0.6; }
.gt-a171__review-btn:hover { opacity: 1; }

/* Table */
.gt-a171__table-wrap { display: flex; flex-direction: column; gap: 8px; }
.gt-a171__add-row { align-self: flex-start; }

/* Y/N */
.gt-a171__yn-wrap { display: flex; flex-direction: column; gap: 12px; }
.gt-a171__yn-explanation { margin-top: 4px; }

/* OO */
.gt-a171__oo { height: calc(100vh - 200px); min-height: 500px; }
</style>
