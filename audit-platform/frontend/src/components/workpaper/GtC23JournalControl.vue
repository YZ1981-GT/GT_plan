<template>
  <div class="gt-c23-journal-control">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <!-- 顶部操作引导区 -->
      <div class="guidance-area">
        <div class="guidance-header">
          <el-icon><InfoFilled /></el-icon>
          <span>操作流程引导</span>
        </div>
        <div class="guidance-steps">
          <div class="step-item">
            <span class="step-num">①</span>
            <span class="step-text">维护授权清单</span>
          </div>
          <div class="step-item">
            <span class="step-num">②</span>
            <span class="step-text">抽样核对</span>
          </div>
          <div class="step-item">
            <span class="step-num">③</span>
            <span class="step-text">判断偏差</span>
          </div>
          <div class="step-item">
            <span class="step-num">④</span>
            <span class="step-text">得出结论</span>
          </div>
        </div>
      </div>

      <!-- C23A 程序表 — HTML 步骤中控台（参照 C1 向导模式） -->
      <div v-if="currentSheet === 'C23A'" class="c23-program-html">
        <!-- 步骤表格 -->
        <table class="c23-grid-table c23-step-table">
          <thead>
            <tr>
              <th style="width: 40px">#</th>
              <th style="min-width: 280px">程序</th>
              <th style="width: 80px">适用?</th>
              <th style="width: 100px">执行人</th>
              <th style="width: 140px">执行情况</th>
              <th style="width: 100px">索引</th>
              <th v-if="!isReadonly" style="width: 70px">快捷</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(step, si) in C23A_PROGRAMS"
              :key="si"
              class="c23-step-row"
              :class="c23StepRowClass(si)"
              @click="openC23StepDialog(si)"
            >
              <td class="c23-cell-idx">{{ step.seq }}</td>
              <td class="c23-cell-name">
                <span class="c23-step-text">{{ step.name }}</span>
                <el-tag v-if="step.subItems?.length" size="small" type="info" effect="plain" style="margin-left:6px">
                  {{ step.subItems.length }} 子项
                </el-tag>
                <el-tag v-if="step.linkedSheet" size="small" type="warning" effect="plain" style="margin-left:4px">
                  → {{ step.linkedSheet }}
                </el-tag>
              </td>
              <td class="c23-cell-center">
                <span v-if="getC23StepVal(si, 'applicable') === 'Y'">✅</span>
                <span v-else-if="getC23StepVal(si, 'applicable') === 'N'">❌</span>
                <span v-else class="c23-cell-empty">—</span>
              </td>
              <td>{{ getC23StepVal(si, 'executor') || '' }}</td>
              <td>
                <el-tag v-if="getC23StepVal(si, 'conclusion')" :type="c23ConclusionType(getC23StepVal(si, 'conclusion'))" size="small" effect="plain">
                  {{ getC23StepVal(si, 'conclusion') }}
                </el-tag>
                <span v-else class="c23-cell-empty">—</span>
              </td>
              <td>
                <span v-if="getC23StepVal(si, 'index')" class="c23-index-link">{{ getC23StepVal(si, 'index') }}</span>
                <span v-else class="c23-cell-empty">—</span>
              </td>
              <td v-if="!isReadonly" class="c23-cell-center" @click.stop>
                <el-button
                  v-if="!getC23StepVal(si, 'conclusion')"
                  size="small" type="success" link
                  title="快速标记：适用 + 有效"
                  @click="quickMarkC23Step(si)"
                >✓有效</el-button>
                <span v-else class="c23-cell-empty">—</span>
              </td>
            </tr>
          </tbody>
        </table>

        <!-- 联动跳转区 -->
        <div class="c23-link-area">
          <el-button type="primary" plain size="small" @click="jumpToSheet('C23-1')">
            📋 C23-1 会计人员清单完整性测试
          </el-button>
          <el-button type="primary" plain size="small" @click="jumpToSheet('C23-2')">
            📋 C23-2 会计分录控制测试样本
          </el-button>
        </div>

        <!-- ═══ Step Dialog ═══ -->
        <el-dialog
          v-model="c23StepDialogVisible"
          :title="c23StepDialogTitle"
          width="60%"
          :close-on-click-modal="false"
          append-to-body
          class="c23-step-dialog"
        >
          <template v-if="activeC23Step !== null">
            <!-- 编制说明（内嵌参考） -->
            <div v-if="C23A_PROGRAMS[activeC23Step].hint" class="c23-edit-hint">
              <div class="c23-edit-hint-head">📖 编制说明</div>
              <div class="c23-edit-hint-body">{{ C23A_PROGRAMS[activeC23Step].hint }}</div>
            </div>

            <!-- 子项（步骤5的3个检查子项） -->
            <div v-if="C23A_PROGRAMS[activeC23Step].subItems?.length" class="c23-subitems">
              <div class="c23-subitems-head">包含以下检查子项：</div>
              <div v-for="(sub, si) in C23A_PROGRAMS[activeC23Step].subItems" :key="si" class="c23-subitem">
                <span class="c23-subitem-num">{{ sub.seq }}</span>
                <span>{{ sub.text }}</span>
              </div>
            </div>

            <!-- 表单字段 -->
            <el-form label-position="top" class="c23-step-form">
              <el-form-item label="是否适用">
                <el-radio-group
                  :model-value="getC23StepVal(activeC23Step, 'applicable')"
                  :disabled="isReadonly"
                  @change="(v: any) => setC23StepVal(activeC23Step!, 'applicable', v)"
                >
                  <el-radio value="Y">适用</el-radio>
                  <el-radio value="N">不适用</el-radio>
                </el-radio-group>
              </el-form-item>

              <el-form-item label="执行人">
                <el-input
                  :model-value="getC23StepVal(activeC23Step, 'executor')"
                  :disabled="isReadonly"
                  placeholder="执行人"
                  @input="(v: any) => setC23StepVal(activeC23Step!, 'executor', v)"
                />
              </el-form-item>

              <el-form-item label="执行情况说明">
                <template #label>
                  <div class="c23-form-label-row">
                    <span>执行情况说明</span>
                    <el-button
                      v-if="!isReadonly"
                      size="small"
                      type="primary"
                      plain
                      :disabled="!ai.aiEnabled.value"
                      @click="onAiSuggestStep"
                    >
                      ✨ AI 生成
                    </el-button>
                  </div>
                </template>
                <el-input
                  :model-value="getC23StepVal(activeC23Step, 'result')"
                  :disabled="isReadonly"
                  type="textarea"
                  :autosize="{ minRows: 3, maxRows: 8 }"
                  placeholder="描述执行情况（如：获取了被审计单位提供的人员名单共X人，经与系统实际设置核对，名单完整准确）"
                  @input="(v: any) => setC23StepVal(activeC23Step!, 'result', v)"
                />
              </el-form-item>

              <el-form-item label="结论">
                <el-select
                  :model-value="getC23StepVal(activeC23Step, 'conclusion')"
                  :disabled="isReadonly"
                  clearable
                  placeholder="执行结论"
                  @change="(v: any) => setC23StepVal(activeC23Step!, 'conclusion', v)"
                >
                  <el-option label="有效" value="有效" />
                  <el-option label="部分有效" value="部分有效" />
                  <el-option label="无效" value="无效" />
                </el-select>
              </el-form-item>

              <el-form-item label="索引号">
                <el-input
                  :model-value="getC23StepVal(activeC23Step, 'index')"
                  :disabled="isReadonly"
                  placeholder="关联底稿编码，如 C23-1、C23-2"
                  @input="(v: any) => setC23StepVal(activeC23Step!, 'index', v)"
                />
              </el-form-item>

              <!-- 联动跳转按钮 -->
              <div v-if="C23A_PROGRAMS[activeC23Step].linkedSheet" class="c23-dialog-link">
                <el-button type="primary" size="small" @click="jumpToSheet(C23A_PROGRAMS[activeC23Step].linkedSheet!)">
                  → 跳转到 {{ C23A_PROGRAMS[activeC23Step].linkedSheet }}
                </el-button>
              </div>
            </el-form>
          </template>

          <template #footer>
            <el-button @click="c23StepDialogVisible = false">关闭</el-button>
            <el-button type="primary" :disabled="isReadonly" @click="saveAndNextC23Step">保存并下一步 →</el-button>
          </template>
        </el-dialog>
      </div>

      <!-- C23-1 会计人员清单完整性测试表 -->
      <div v-else-if="currentSheet === 'C23-1'" class="c23-personnel-list">
        <C23PersonnelSheet
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :persons="persons"
          :source-desc="sourceDesc"
          :analysis-text="analysisText"
          :conclusion1="conclusion1"
          :is-readonly="isReadonly"
          @update:source-desc="onSourceDescChange"
          @update:analysis="onAnalysisChange"
          @update:conclusion1="onConclusion1Change"
          @add-person="onAddPerson"
          @add-person-full="onAddPersonFull"
          @remove-person="onRemovePerson"
          @update-person="onUpdatePerson"
          @ai-suggest="onAiSuggest('C23-1-conclusion')"
        />
      </div>

      <!-- C23-2 会计分录控制测试样本表 -->
      <div v-else-if="currentSheet === 'C23-2'" class="c23-control-test">
        <C23SampleSheet
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :samples="samples"
          :persons="persons"
          :deviation-count="deviationCount"
          :deviation-total="deviationTotal"
          :conclusion2="conclusion2"
          :is-readonly="isReadonly"
          @update-sample="onUpdateSample"
          @update:conclusion2="onConclusion2Change"
          @ai-suggest="onAiSuggest('C23-2-conclusion')"
        />
      </div>

      <!-- 示例 sheets (只读) -->
      <div v-else class="c23-example">
        <el-alert type="info" :closable="false" show-icon>
          <template #title>{{ currentSheet === '示例1' ? '示例 — 会计人员清单测试' : '示例 — 会计分录控制测试' }}</template>
          <p style="margin-top: 8px; color: #606266;">此为只读参考示例，请在 C23-1 / C23-2 中进行实际操作。</p>
        </el-alert>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtC23JournalControl — C23 会计分录控制测试专属组件
 *
 * componentType: c23-journal-entry-control
 * 对齐 D4 标准：sheetName v-if 分发，无内部 el-tabs
 *
 * Sheets: C23A / C23-1 人员清单 / C23-2 控制测试 / 示例1 / 示例2
 *
 * Spec: .kiro/specs/c23-c24-journal-entry-testing/
 * Task: 4.1
 * Requirements: 1.1, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5
 */
import { ref, computed, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import { ElMessage, ElMessageBox } from 'element-plus'
import { checkPersonnel, type AuthorizedPerson, type JeControlSample } from '@/composables/useC23ControlData'
import { useWpAiSuggest } from '@/composables/useWpAiSuggest'

defineOptions({ name: 'GtC23JournalControl' })

// ─── Lazy child components ───
const C23PersonnelSheet = defineAsyncComponent(() => import('./c23/C23PersonnelSheet.vue'))
const C23SampleSheet = defineAsyncComponent(() => import('./c23/C23SampleSheet.vue'))

// ─── C23A 程序步骤定义（源模板 6 步 + 编制说明） ───
interface C23ProgramStep {
  seq: number
  name: string
  hint?: string
  subItems?: { seq: string; text: string }[]
  linkedSheet?: string
}

const C23A_PROGRAMS: C23ProgramStep[] = [
  {
    seq: 1,
    name: '获取编制、过账和审核日记账的职员名单。',
    hint: '从相关政策文件或与管理层的讨论中取得授权个人的名单。这份名单还应包括负责高层批准调整的会计分录（合并及重分类）的个人。名单应包括每个人的权限（创建、授权或记录）。',
    linkedSheet: 'C23-1',
  },
  {
    seq: 2,
    name: '对所获取清单中员工的专业胜任能力进行评价（如：员工人数，经验及其所履行的职责）。',
    hint: '评价"名单中的人员的恰当性"要求作出判断，评价时应考虑这些人是否能够执行管理IT职能（如更新用户资料），这类访问可能便于个人不受限制地记账。',
    linkedSheet: 'C23-1',
  },
  {
    seq: 3,
    name: '将观察得出实际设置与被审计单位提供的职员名单进行比较，确认清单的完整性和准确性。',
    hint: '该部分适用于以电子方式录入和批准的会计分录。项目组还可以取得相关的安全访问报告以核对信息。',
    linkedSheet: 'C23-1',
  },
  {
    seq: 4,
    name: '确认多久将对被批准可访问应用程序的职员名单进行审核以及由谁担任审核人员。',
    hint: '参见程序2。如果名单包括前雇员或转入其他职能的雇员，则为名单未被及时复核提供有力的证明，这一名单应作为控制缺陷予以报告。',
  },
  {
    seq: 5,
    name: '在该期间中选择一份无偏向的、未分层的25笔日记账分录样本，并对每个分录执行下列程序：',
    subItems: [
      { seq: '(1)', text: '确认编制人、过账人和审核人。' },
      { seq: '(2)', text: '同清单进行比较。' },
      { seq: '(3)', text: '确定支持性和批准性文件是否符合企业会计分录的记账政策。' },
    ],
    linkedSheet: 'C23-2',
  },
  {
    seq: 6,
    name: '我确信日记账控制有效运行。',
    hint: '基于上述步骤 1-5 的执行结果，形成对会计分录控制有效性的整体结论。',
  },
]

// ─── Props / Emits ───
const props = defineProps<{
  wpId: string
  projectId?: string
  wpCode?: string
  year?: string
  sheetName?: string
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

// ─── State ───
const isLoading = ref(true)
const isReadonly = computed(() => !!props.readonly)

const currentSheet = computed(() => {
  const name = props.sheetName || 'C23A'
  if (name.includes('C23A') || name.includes('程序表')) return 'C23A'
  if (name.includes('C23-1') || name.includes('人员清单')) return 'C23-1'
  if (name.includes('C23-2') || name.includes('控制测试')) return 'C23-2'
  if (name.includes('示例1') || name.includes('人员清单测试')) return '示例1'
  if (name.includes('示例2') || name.includes('分录控制测试')) return '示例2'
  return name
})

// ─── C23A 步骤状态 ───
const c23StepDialogVisible = ref(false)
const activeC23Step = ref<number | null>(null)
/** 步骤数据缓存 Map: `C23A-{seq}-{field}` → value */
const c23StepData = ref<Map<string, string>>(new Map())

function c23StepItemId(stepIdx: number, field: string): string {
  return `C23A-${stepIdx + 1}-${field}`
}

function getC23StepVal(stepIdx: number, field: string): string {
  return c23StepData.value.get(c23StepItemId(stepIdx, field)) || ''
}

function setC23StepVal(stepIdx: number, field: string, value: string | null): void {
  if (isReadonly.value) return
  const key = c23StepItemId(stepIdx, field)
  if (value) {
    c23StepData.value.set(key, value)
  } else {
    c23StepData.value.delete(key)
  }
  debounceSave()
}

function c23StepStatus(stepIdx: number): 'done' | 'wip' | 'todo' {
  if (getC23StepVal(stepIdx, 'conclusion')) return 'done'
  if (getC23StepVal(stepIdx, 'result') || getC23StepVal(stepIdx, 'applicable')) return 'wip'
  return 'todo'
}

function c23StepRowClass(stepIdx: number): Record<string, boolean> {
  const s = c23StepStatus(stepIdx)
  return { 'c23-step-done': s === 'done', 'c23-step-wip': s === 'wip' }
}

function c23ConclusionType(conclusion: string): string {
  if (conclusion === '有效') return 'success'
  if (conclusion === '无效') return 'danger'
  return 'warning'
}

const c23StepDialogTitle = computed(() => {
  if (activeC23Step.value === null) return '步骤详情'
  const step = C23A_PROGRAMS[activeC23Step.value]
  return `步骤 ${step.seq}：${step.name.substring(0, 30)}...`
})

function openC23StepDialog(stepIdx: number): void {
  activeC23Step.value = stepIdx
  c23StepDialogVisible.value = true
}

function quickMarkC23Step(stepIdx: number): void {
  if (isReadonly.value) return
  setC23StepVal(stepIdx, 'applicable', 'Y')
  setC23StepVal(stepIdx, 'conclusion', '有效')
  if (!getC23StepVal(stepIdx, 'result')) {
    setC23StepVal(stepIdx, 'result', '经执行相关测试程序，未发现异常，控制运行有效。')
  }
  ElMessage.success(`步骤 ${stepIdx + 1} 已标记为「有效」`)
}

function saveAndNextC23Step(): void {
  if (activeC23Step.value === null) return
  flushPendingSaves()
  const next = activeC23Step.value + 1
  if (next < C23A_PROGRAMS.length) {
    activeC23Step.value = next
  } else {
    c23StepDialogVisible.value = false
    ElMessage.success('所有步骤已完成')
  }
}

function jumpToSheet(sheet: string): void {
  // 通知父组件切换到指定 sheet tab
  emit('navigate-sheet', sheet)
  // 备用：通过路由 query 切换（如果 emit 没被父组件处理）
  try {
    const route = (window as any).__VUE_ROUTER__?.currentRoute?.value
    if (route) {
      ;(window as any).__VUE_ROUTER__.push({
        ...route,
        query: { ...route.query, sheet },
      })
    }
  } catch { /* silent */ }
  c23StepDialogVisible.value = false
}

/** AI 辅助生成步骤执行情况说明 */
async function onAiSuggestStep(): Promise<void> {
  if (isReadonly.value || activeC23Step.value === null || !ai.aiEnabled.value) return
  const step = C23A_PROGRAMS[activeC23Step.value]
  const currentVal = getC23StepVal(activeC23Step.value, 'result')
  const prompt = `请为会计分录控制测试程序「${step.name}」生成执行情况说明。${step.hint ? '编制说明参考：' + step.hint : ''}`
  await ai.requestSuggestion(prompt, currentVal)
  const text = ai.adoptSuggestion()
  if (text && activeC23Step.value !== null) {
    setC23StepVal(activeC23Step.value, 'result', text)
    ElMessage.success('AI 已生成执行情况说明')
  }
}

// ─── C23-1 数据来源 + 授权人员清单 ───
const sourceDesc = ref('')
const analysisText = ref('')
const conclusion1 = ref('')
const persons = ref<Array<{ seq: number; name: string; role: string; note: string; code?: string; canCreate?: string; canApprove?: string; canPost?: string }>>([])

// ─── C23-2 样本数据 ───
const SAMPLE_COUNT = 25
interface SampleRow {
  seq: number
  date: string
  voucherNo: string
  preparer: string
  poster: string
  reviewer: string
  supportDoc: string
  approval: string
  deviation: string   // '是' | '否' | ''
  deviationNote: string
  indexRef: string
}
const samples = ref<SampleRow[]>([])
const conclusion2 = ref('')

// ─── 偏差统计 (formula) ───
const deviationCount = computed(() => samples.value.filter(s => s.deviation.startsWith('是')).length)
const deviationTotal = computed(() => samples.value.filter(s => s.date || s.voucherNo || s.preparer).length || SAMPLE_COUNT)

// ─── AI ───
const ai = useWpAiSuggest({ wpId: props.wpId, sheetName: 'C23' })

// ─── Debounce save ───
let saveTimer: ReturnType<typeof setTimeout> | null = null

function debounceSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => { persistAll() }, 2000)
}

function flushPendingSaves() {
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
    persistAll()
  }
}

// ─── Persist functions ───
async function persistAll() {
  if (!props.wpId || isReadonly.value) return
  const items: Array<{ item_id: string; conclusion?: string | null; remark?: string | null }> = []

  // C23A step data
  for (const [key, val] of c23StepData.value.entries()) {
    if (key.startsWith('C23A-')) {
      // conclusion/applicable fields → conclusion column; others → remark
      const isConclusion = key.endsWith('-conclusion') || key.endsWith('-applicable')
      items.push({
        item_id: key,
        conclusion: isConclusion ? (val || null) : null,
        remark: isConclusion ? null : (val || null),
      })
    }
  }

  // C23-1 source & conclusion
  items.push({ item_id: 'C23-1-source', conclusion: null, remark: sourceDesc.value || null })
  items.push({ item_id: 'C23-1-analysis', conclusion: null, remark: analysisText.value || null })
  items.push({ item_id: 'C23-1-conclusion', conclusion: conclusion1.value || null, remark: null })

  // C23-1 persons
  persons.value.forEach((p, i) => {
    const n = i + 1
    items.push({ item_id: `C23-person-${n}-name`, conclusion: null, remark: p.name || null })
    items.push({ item_id: `C23-person-${n}-role`, conclusion: p.role || null, remark: null })
    items.push({ item_id: `C23-person-${n}-note`, conclusion: null, remark: p.note || null })
  })

  // C23-2 samples
  samples.value.forEach((s) => {
    const prefix = `C23-sample-${s.seq}`
    items.push({ item_id: `${prefix}-date`, conclusion: null, remark: s.date || null })
    items.push({ item_id: `${prefix}-voucherNo`, conclusion: null, remark: s.voucherNo || null })
    items.push({ item_id: `${prefix}-preparer`, conclusion: null, remark: s.preparer || null })
    items.push({ item_id: `${prefix}-poster`, conclusion: null, remark: s.poster || null })
    items.push({ item_id: `${prefix}-reviewer`, conclusion: null, remark: s.reviewer || null })
    items.push({ item_id: `${prefix}-supportDoc`, conclusion: null, remark: s.supportDoc || null })
    items.push({ item_id: `${prefix}-approval`, conclusion: null, remark: s.approval || null })
    items.push({ item_id: `${prefix}-deviation`, conclusion: s.deviation || null, remark: null })
    items.push({ item_id: `${prefix}-deviationNote`, conclusion: null, remark: s.deviationNote || null })
    items.push({ item_id: `${prefix}-indexRef`, conclusion: null, remark: s.indexRef || null })
  })

  // C23-2 conclusion & deviation count
  items.push({ item_id: 'C23-2-conclusion', conclusion: conclusion2.value || null, remark: null })
  items.push({ item_id: 'C23-2-deviationCount', conclusion: null, remark: `${deviationCount.value}/${deviationTotal.value}` })

  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId || undefined,
      items,
    })
    emit('save')
  } catch (err: any) {
    ElMessage.error('保存失败，数据已保留在本地')
    console.warn('[C23] persist failed:', err)
  }
}

/** 即时保存结论字段 */
async function saveConclusion(itemId: string, value: string) {
  if (!props.wpId || isReadonly.value) return
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId || undefined,
      items: [{ item_id: itemId, conclusion: value || null, remark: null }],
    })
  } catch { /* silent */ }
}

// ─── Event handlers ───

function onSourceDescChange(val: string) {
  sourceDesc.value = val
  debounceSave()
}

function onAnalysisChange(val: string) {
  analysisText.value = val
  debounceSave()
}

function onConclusion1Change(val: string) {
  conclusion1.value = val
  saveConclusion('C23-1-conclusion', val)
}

function onConclusion2Change(val: string) {
  conclusion2.value = val
  saveConclusion('C23-2-conclusion', val)
}

async function onAddPerson() {
  if (isReadonly.value) return
  try {
    const { value: name } = await ElMessageBox.prompt('请输入人员姓名', '新增授权人员', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPlaceholder: '请输入姓名',
      inputValidator: (v) => (v?.trim() ? true : '姓名不能为空'),
    })
    if (!name?.trim()) return
    const seq = persons.value.length + 1
    persons.value.push({ seq, name: name.trim(), role: '', note: '' })
    debounceSave()
    runPersonnelCheck()
  } catch { /* cancelled */ }
}

/** 从 Dialog 新增完整人员信息 */
function onAddPersonFull(person: { code: string; name: string; role: string; note: string; canCreate: string; canApprove: string; canPost: string }) {
  if (isReadonly.value) return
  const seq = persons.value.length + 1
  persons.value.push({
    seq,
    name: person.name,
    role: person.role,
    note: person.note,
    code: person.code,
    canCreate: person.canCreate,
    canApprove: person.canApprove,
    canPost: person.canPost,
  })
  debounceSave()
  runPersonnelCheck()
}

function onRemovePerson(index: number) {
  if (isReadonly.value) return
  persons.value.splice(index, 1)
  // Re-sequence
  persons.value.forEach((p, i) => { p.seq = i + 1 })
  debounceSave()
  runPersonnelCheck()
}

function onUpdatePerson(index: number, field: 'name' | 'role' | 'note', value: string) {
  if (isReadonly.value) return
  persons.value[index][field] = value
  debounceSave()
  if (field === 'name') runPersonnelCheck()
}

function onUpdateSample(index: number, field: keyof SampleRow, value: string) {
  if (isReadonly.value) return
  ;(samples.value[index] as any)[field] = value
  debounceSave()
  // Auto check personnel after preparer/poster/reviewer change
  if (['preparer', 'poster', 'reviewer'].includes(field)) {
    runPersonnelCheck()
  }
}

/** 人员核对：调用 checkPersonnel 自动标记偏差 */
function runPersonnelCheck() {
  const authorized: AuthorizedPerson[] = persons.value
    .filter(p => p.name.trim())
    .map(p => ({ name: p.name, role: p.role }))

  const sampleData: JeControlSample[] = samples.value
    .filter(s => s.preparer || s.poster || s.reviewer)
    .map(s => ({
      seq: s.seq,
      voucherDate: s.date,
      voucherNo: s.voucherNo,
      preparer: s.preparer,
      poster: s.poster,
      reviewer: s.reviewer,
      supportDoc: s.supportDoc,
      approval: s.approval,
    }))

  if (!authorized.length || !sampleData.length) return

  const results = checkPersonnel(sampleData, authorized)
  results.forEach(r => {
    const row = samples.value.find(s => s.seq === r.sample.seq)
    if (row) {
      // 自动标记：偏差为 "是-需跟进"，无偏差为 "否"
      if (r.deviation && !row.deviation) {
        row.deviation = '是-需跟进'
      } else if (!r.deviation && !row.deviation) {
        row.deviation = '否'
      }
      if (r.deviation && r.deviationDetails) {
        row.deviationNote = r.deviationDetails
      }
    }
  })
}

async function onAiSuggest(fieldId: string) {
  if (isReadonly.value || !ai.aiEnabled.value) return
  const fieldName = fieldId === 'C23-1-conclusion' ? '人员清单完整性测试结论' : '控制测试结论'
  const currentVal = fieldId === 'C23-1-conclusion' ? conclusion1.value : conclusion2.value
  await ai.requestSuggestion(fieldName, currentVal)
  const text = ai.adoptSuggestion()
  if (text) {
    if (fieldId === 'C23-1-conclusion') {
      conclusion1.value = text
      saveConclusion('C23-1-conclusion', text)
    } else {
      conclusion2.value = text
      saveConclusion('C23-2-conclusion', text)
    }
  }
}

// ─── selfLoad ───
async function selfLoad() {
  try {
    const res = await api.get<any[]>(`/api/workpapers/${props.wpId}/checklist-responses`, { _silent: true } as any)
    const items: Array<{ item_id: string; conclusion?: string; remark?: string }> = Array.isArray(res) ? res : (res as any)?.data || []

    // Build lookup map
    const map = new Map<string, { conclusion?: string; remark?: string }>()
    for (const item of items) {
      if (item.item_id?.startsWith('C23')) {
        map.set(item.item_id, { conclusion: item.conclusion, remark: item.remark })
      }
    }

    // C23A step data
    for (const [key, val] of map.entries()) {
      if (key.startsWith('C23A-')) {
        const isConclusion = key.endsWith('-conclusion') || key.endsWith('-applicable')
        const v = isConclusion ? (val.conclusion || '') : (val.remark || '')
        if (v) c23StepData.value.set(key, v)
      }
    }

    // C23-1 source & conclusion
    sourceDesc.value = map.get('C23-1-source')?.remark || ''
    analysisText.value = map.get('C23-1-analysis')?.remark || ''
    conclusion1.value = map.get('C23-1-conclusion')?.conclusion || ''

    // C23-1 persons (find max n)
    const personKeys = [...map.keys()].filter(k => k.startsWith('C23-person-'))
    const maxPersonN = personKeys.reduce((max, k) => {
      const m = k.match(/^C23-person-(\d+)-/)
      return m ? Math.max(max, parseInt(m[1])) : max
    }, 0)
    const loadedPersons: Array<{ seq: number; name: string; role: string; note: string }> = []
    for (let n = 1; n <= maxPersonN; n++) {
      const name = map.get(`C23-person-${n}-name`)?.remark || ''
      const role = map.get(`C23-person-${n}-role`)?.conclusion || ''
      const note = map.get(`C23-person-${n}-note`)?.remark || ''
      if (name || role || note) {
        loadedPersons.push({ seq: n, name, role, note })
      }
    }
    persons.value = loadedPersons

    // C23-2 samples
    const loadedSamples: SampleRow[] = []
    for (let s = 1; s <= SAMPLE_COUNT; s++) {
      const prefix = `C23-sample-${s}`
      loadedSamples.push({
        seq: s,
        date: map.get(`${prefix}-date`)?.remark || '',
        voucherNo: map.get(`${prefix}-voucherNo`)?.remark || '',
        preparer: map.get(`${prefix}-preparer`)?.remark || '',
        poster: map.get(`${prefix}-poster`)?.remark || '',
        reviewer: map.get(`${prefix}-reviewer`)?.remark || '',
        supportDoc: map.get(`${prefix}-supportDoc`)?.remark || '',
        approval: map.get(`${prefix}-approval`)?.remark || '',
        deviation: map.get(`${prefix}-deviation`)?.conclusion || '',
        deviationNote: map.get(`${prefix}-deviationNote`)?.remark || '',
        indexRef: map.get(`${prefix}-indexRef`)?.remark || '',
      })
    }
    samples.value = loadedSamples

    // C23-2 conclusion
    conclusion2.value = map.get('C23-2-conclusion')?.conclusion || ''
  } catch (err) {
    console.warn('[GtC23JournalControl] selfLoad failed:', err)
  } finally {
    isLoading.value = false
  }
}

// ─── Lifecycle ───
onMounted(() => { selfLoad() })
onBeforeUnmount(() => { flushPendingSaves() })
defineExpose({ reload: selfLoad })
</script>

<style scoped>
.gt-c23-journal-control {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}
.loading-container {
  padding: 24px;
}
.guidance-area {
  background: linear-gradient(135deg, #ecf5ff 0%, #d9ecff 100%);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}
.guidance-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 14px;
  color: #303133;
  margin-bottom: 12px;
}
.guidance-header .el-icon {
  color: #409eff;
  font-size: 16px;
}
.guidance-steps {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 16px;
}
.step-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: rgba(255, 255, 255, 0.7);
  border-radius: 6px;
}
.step-num {
  font-weight: 700;
  color: #409eff;
  font-size: 14px;
}
.step-text {
  font-size: var(--wp-font-size, 13px);
  color: #303133;
}

/* ─── C23A HTML 步骤表格 ─── */
.c23-program-html {
  margin-top: 12px;
}
.c23-grid-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--wp-font-size, 13px);
}
.c23-grid-table th,
.c23-grid-table td {
  border: 1px solid #ebeef5;
  padding: 6px 10px;
  text-align: left;
  vertical-align: middle;
}
.c23-grid-table th {
  background: #f5f7fa;
  font-weight: 600;
  color: #303133;
}
.c23-cell-idx { text-align: center; color: #909399; }
.c23-cell-center { text-align: center; }
.c23-cell-empty { color: #c0c4cc; }
.c23-cell-name { font-weight: 500; }
.c23-step-text { display: inline; }
.c23-index-link { color: #4b2d77; text-decoration: underline; cursor: pointer; }

.c23-step-row {
  cursor: pointer;
  transition: background 0.15s;
}
.c23-step-row:hover { background: #f3eefb; }
.c23-step-done { background: #f0fdf4; }
.c23-step-wip { background: #fffde6; }

/* 联动跳转区 */
.c23-link-area {
  margin-top: 14px;
  display: flex;
  gap: 12px;
}

/* Step Dialog */
.c23-edit-hint {
  margin-bottom: 14px;
  border: 1px solid #fde68a;
  border-radius: 8px;
  background: #fffbeb;
  overflow: hidden;
}
.c23-edit-hint-head {
  padding: 8px 12px;
  font-weight: 600;
  font-size: var(--wp-font-size, 13px);
  color: #92400e;
  background: #fef3c7;
  border-bottom: 1px solid #fde68a;
}
.c23-edit-hint-body {
  padding: 10px 14px;
  font-size: 12px;
  color: #78350f;
  line-height: 1.7;
}
.c23-subitems {
  background: #f0f9ff;
  border-left: 3px solid #3b82f6;
  border-radius: 0 6px 6px 0;
  padding: 10px 14px;
  margin-bottom: 14px;
}
.c23-subitems-head {
  font-weight: 600;
  font-size: var(--wp-font-size, 13px);
  margin-bottom: 6px;
  color: #1e40af;
}
.c23-subitem {
  padding: 3px 0;
  font-size: var(--wp-font-size, 13px);
}
.c23-subitem-num {
  font-weight: 700;
  color: #3b82f6;
  margin-right: 6px;
}
.c23-step-form {
  padding: 0 8px;
}
.c23-dialog-link {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed #e5e7eb;
}

/* AI 辅助字段行 — label 行右对齐按钮 */
.c23-form-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}
.c23-form-label-row span {
  font-weight: 500;
}
</style>
