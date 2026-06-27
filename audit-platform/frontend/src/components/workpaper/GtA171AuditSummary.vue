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
          <template #header><span class="gt-a171__card-title">签字表</span></template>
          <el-table :data="signatureTable" border size="small" class="gt-a171__sig-table">
            <el-table-column label="角色" prop="role" width="140" />
            <el-table-column label="签名" min-width="160">
              <template #default="{ row, $index }">
                <el-input
                  :model-value="row.name || ''"
                  size="small"
                  placeholder="姓名"
                  @change="(v: string) => updateSignature($index, 'name', v)"
                />
              </template>
            </el-table-column>
            <el-table-column label="日期" width="180">
              <template #default="{ row, $index }">
                <el-date-picker
                  :model-value="row.date"
                  type="date"
                  size="small"
                  value-format="YYYY-MM-DD"
                  placeholder="选择日期"
                  @change="(v: string) => updateSignature($index, 'date', v || '')"
                />
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <!-- 16 Chapter Cards -->
        <el-collapse v-model="expandedChapters" class="gt-a171__chapters">
          <!-- Textarea chapters: 1,2,3,4,5,7,13,14,15,16 -->
          <template v-for="n in 16" :key="n">
            <el-collapse-item
              :name="n"
              :id="`a171-section-${n}`"
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
                </div>
              </template>

              <!-- Textarea type -->
              <div v-if="chapters[String(n)]?.type === 'textarea'" class="gt-a171__textarea-wrap">
                <el-input
                  :model-value="(chapters[String(n)] as any).content || ''"
                  type="textarea"
                  :autosize="{ minRows: 4 }"
                  :placeholder="`请输入${chapters[String(n)]?.title}相关内容`"
                  @change="(v: string) => updateTextarea(n, v)"
                />
                <el-button size="small" disabled class="gt-a171__ai-btn">
                  <el-tooltip content="AI 辅助填写即将上线" placement="top">
                    <span>🤖 AI</span>
                  </el-tooltip>
                </el-button>
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
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, watch, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { useA171AuditSummary } from './composables/useA171AuditSummary'
import { useA171Navigation } from './composables/useA171Navigation'
import type { A171RenderData } from './composables/useA171AuditSummary'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtIndexChip = defineAsyncComponent(() => import('./GtIndexChip.vue'))

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
} = useA171AuditSummary({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  htmlData: toRef(props, 'htmlData'),
})

// ─── Navigation ───
const { activeChapter, scrollToChapter, completionStatus } = useA171Navigation(chapters)

// ─── Collapse State: all collapsed by default ───
const expandedChapters = ref<number[]>([])

// ─── Helpers ───
const CHAPTER_NAV_LABELS: Record<number, string> = {
  1: '一、审计概况',
  2: '二、会计变更',
  3: '三、关键事项',
  4: '四、持续经营',
  5: '五、范围调整',
  6: '六、风险应对',
  7: '七、集团审计',
  8: '八、财务分析',
  9: '九、舞弊识别',
  10: '十、违规情况',
  11: '十一、关联方',
  12: '十二、期后事项',
  13: '十三、审计意见',
  14: '十四、错报处理',
  15: '十五、治理沟通',
  16: '十六、审计总结',
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

onMounted(() => { checkOOHealth(); selfLoad() })
onBeforeUnmount(() => { flushPendingSaves() })
defineExpose({ reload: () => flushPendingSaves() })
</script>

<style scoped>
.gt-a171 { padding: 16px; }
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
.gt-a171__card-title { font-size: 15px; font-weight: 600; color: #303133; }
.gt-a171__sig-table { width: 100%; }

/* Chapters */
.gt-a171__chapters { border: none; }
.gt-a171__chapter-item { margin-bottom: 8px; }
.gt-a171__chapter-header { display: flex; align-items: center; gap: 8px; width: 100%; }
.gt-a171__chapter-title { font-size: 14px; font-weight: 600; color: #303133; }

/* Textarea */
.gt-a171__textarea-wrap { position: relative; }
.gt-a171__ai-btn { position: absolute; top: 4px; right: 4px; opacity: 0.6; }

/* Table */
.gt-a171__table-wrap { display: flex; flex-direction: column; gap: 8px; }
.gt-a171__add-row { align-self: flex-start; }

/* Y/N */
.gt-a171__yn-wrap { display: flex; flex-direction: column; gap: 12px; }
.gt-a171__yn-explanation { margin-top: 4px; }

/* OO */
.gt-a171__oo { height: calc(100vh - 200px); min-height: 500px; }
</style>
