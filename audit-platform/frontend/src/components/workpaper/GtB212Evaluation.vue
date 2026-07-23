<script setup lang="ts">
/**
 * GtB212Evaluation — B2-12 对前任注册会计师的评价底稿（结构化）
 *
 * 依据审计准则 1153 号 §5.2（重新审计 / IPO 三年一期 / 重大资产重组两年一期等
 * 期间内变更审计机构，后任拟查阅前任底稿或取得审计证据时对前任的评价记录）。
 *
 * 上：9 步了解程序检查表（第 8 步底稿审阅拆 5 子项）
 * 下：7 点结论判断矩阵（是否存在[是/否/不适用] → 应对措施 → 对审计计划及程序的影响）
 * 结论区：AI 辅助 + 审计说明。数据存 checklist_responses（item_id B2-12-*）。
 */
import { ref, computed, onMounted, toRef, defineAsyncComponent } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import { useWorkpaperVersionToolbar } from './composables/useWorkpaperVersionToolbar'
import { useWorkpaperReviewProvide } from './composables/useWorkpaperReviewProvide'
import { uploadAttachment } from '@/services/commonApi'

const GtWpVersionTrail = defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))
const GtWpReviewDialogHost = defineAsyncComponent(() => import('./GtWpReviewDialogHost.vue'))

const props = defineProps<{
  wpId: string
  projectId?: string
  htmlData?: Record<string, any>
  readonly?: boolean
}>()

// ─── 版本链 + 复核对话（对齐 B60 范式） ───
const { versionTrailRef, scheduleAutoSnapshot, openVersionHistory } = useWorkpaperVersionToolbar({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId') as any,
})
const { openReview } = useWorkpaperReviewProvide({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId') as any,
})

// ─── 静态定义：9 步了解程序 ───
interface StepDef { seq: number; text: string; subItems?: string[] }
const STEP_DEFS: StepDef[] = [
  { seq: 1, text: '了解并记录前任注册会计师的姓名、执业年限。' },
  { seq: 2, text: '了解被审计单位所处行业，以及项目合伙人、项目经理（即联合签字注册会计师）、审计项目组现场负责人在对该行业客户的执业经验。' },
  { seq: 3, text: '询问项目合伙人、项目经理在执业过程中是否曾经受到行政处罚，或者接受非行政处罚性监管措施。' },
  { seq: 4, text: '询问并记录前任审计项目组的人员配备、人员构成和投入的工时情况。' },
  { seq: 5, text: '了解前任注册会计师的独立性管理流程，并询问该被审计单位的审计项目中是否存在独立性威胁。' },
  { seq: 6, text: '了解并记录前任注册会计师及会计师事务所的专业标准体系和质量控制制度的建立及运行情况。' },
  { seq: 7, text: '获取前任注册会计师出具的审计报告，从形式、内容和要素等方面判断是否存在不符合审计准则规定之处。' },
  {
    seq: 8,
    text: '获取前任注册会计师的审计工作底稿，从以下方面进行审阅：',
    subItems: [
      '（1）工作底稿记录是否能体现出项目组执行了前任会计师事务所的专业标准和质控制度；',
      '（2）工作底稿所记录的审计程序是否运用了系统、规范化的方法，并能够体现出风险导向审计的"自上而下"思路；',
      '（3）工作底稿记录是否存在重大缺失，包括不限于：与重大错报风险、特别风险、关键审计事项应对程序相关底稿记录不完整；',
      '（4）工作底稿记录与直接从被审计单位获取的信息或审计证据之间是否存在重大不一致、实质性矛盾；',
      '（5）工作底稿的编制时间、编制人及复核人签名是否与该审计项目执行时间及项目组人员组成相吻合。',
    ],
  },
  { seq: 9, text: '综合对比审计报告、审计工作底稿及其他方面（包括不限于被审计单位和公众媒体）获取的信息，判断前任注册会计师获取的审计证据和所执行程序是否能够支持所发表的审计意见或鉴证结论。' },
]

// ─── 静态定义：7 点结论判断 ───
const CONCLUSION_DEFS: string[] = [
  '对前任注册会计师的独立性存在威胁的事项；',
  '对前任注册会计师专业素质、胜任能力产生不利影响的因素；',
  '前任注册会计师所在的会计师事务所未建立统一的专业标准体系或质量控制制度，或者其质量控制制度的设计和运行存在重大缺陷；',
  '前任注册会计师的工作底稿存在重大缺失，包括不限于：与重大错报风险、特别风险、关键审计事项应对程序相关底稿记录不完整；',
  '前任注册会计师的工作底稿记录与直接从被审计单位获取的信息或审计证据存在重大不一致、实质性矛盾；',
  '前任注册会计师及审计项目组投入的审计成本严重不足；',
  '前任注册会计师出具的审计报告意见类型或者审计报告的其他内容、要素不恰当。',
]

const EXISTS_OPTIONS = ['是', '否', '不适用']

// ─── 数据模型 ───
interface StepRow { record: string; subChecks: boolean[]; attachmentId?: string; attachmentName?: string }
interface ConclusionRow { exists: string; measure: string; impact: string }

const steps = ref<StepRow[]>(
  STEP_DEFS.map((d) => ({ record: '', subChecks: d.subItems ? d.subItems.map(() => false) : [], attachmentId: '', attachmentName: '' }))
)
const conclusions = ref<ConclusionRow[]>(
  CONCLUSION_DEFS.map(() => ({ exists: '否', measure: '', impact: '' }))
)
const note = ref('')

const loading = ref(false)
const aiLoading = ref(false)

// ─── 项目上下文（抬头） ───
const clientName = computed(() => props.htmlData?.project_context?.client_name || '')
const auditYear = computed(() => props.htmlData?.project_context?.audit_year || '')

// ─── "存在"数量（P5 高亮 + 提示） ───
const existsCount = computed(() => conclusions.value.filter((c) => c.exists === '是').length)

function conclusionRowClass({ rowIndex }: { rowIndex: number }): string {
  return conclusions.value[rowIndex]?.exists === '是' ? 'exists-row' : ''
}

// ─── 导出 Word（Task B / 防归档回归） ───
async function exportDocx() {
  if (!props.wpId || !props.projectId) {
    ElMessage.warning('缺少底稿或项目信息，无法导出')
    return
  }
  try {
    const res: any = await api.get(
      `/api/projects/${props.projectId}/working-papers/${props.wpId}/b2-12/export-docx`,
      { responseType: 'blob' } as any,
    )
    const blob = res instanceof Blob ? res : (res?.data instanceof Blob ? res.data : new Blob([res?.data ?? res]))
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `B2-12_对前任注册会计师的评价_${clientName.value || ''}.docx`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  } catch {
    ElMessage.error('导出失败，请重试')
  }
}

// ─── 推送前任沟通发现到 B50 风险因素（Task 9 / R6.1） ───
function pushToB50() {
  const factors = conclusions.value
    .map((c, i) => ({ c, i }))
    .filter(({ c }) => c.exists === '是')
    .map(({ i }) => `前任沟通发现：${CONCLUSION_DEFS[i].replace(/；$/, '')}`)
  if (!factors.length) {
    ElMessage.info('当前无"存在"的不利事项，无需推送至 B50')
    return
  }
  eventBus.emit('b50:push-risk-factor' as any, { factors, source: 'B2-12' })
  ElMessage.success(`已推送 ${factors.length} 项前任沟通发现至 B50 风险因素识别`)
}

// ─── 加载 ───
function hydrate(snapshot: Record<string, any>) {
  const sRaw = snapshot['B2-12-steps']?.remark
  if (sRaw) {
    try {
      const arr = JSON.parse(sRaw)
      if (Array.isArray(arr)) {
        arr.forEach((it: any, i: number) => {
          if (steps.value[i]) {
            steps.value[i].record = it.record ?? ''
            steps.value[i].attachmentId = it.attachmentId ?? ''
            steps.value[i].attachmentName = it.attachmentName ?? ''
            if (Array.isArray(it.subChecks) && steps.value[i].subChecks.length) {
              it.subChecks.forEach((v: boolean, j: number) => {
                if (j < steps.value[i].subChecks.length) steps.value[i].subChecks[j] = !!v
              })
            }
          }
        })
      }
    } catch { /* ignore */ }
  }
  const cRaw = snapshot['B2-12-conclusions']?.remark
  if (cRaw) {
    try {
      const arr = JSON.parse(cRaw)
      if (Array.isArray(arr)) {
        arr.forEach((it: any, i: number) => {
          if (conclusions.value[i]) {
            conclusions.value[i].exists = it.exists ?? '否'
            conclusions.value[i].measure = it.measure ?? ''
            conclusions.value[i].impact = it.impact ?? ''
          }
        })
      }
    } catch { /* ignore */ }
  }
  const nRaw = snapshot['B2-12-note']?.remark
  if (nRaw != null) note.value = nRaw
}

async function load() {
  // 优先 htmlData.responses_snapshot（render 注入）
  const snap = props.htmlData?.responses_snapshot
  if (snap && typeof snap === 'object' && Object.keys(snap).length) {
    hydrate(snap)
    return
  }
  if (!props.wpId) return
  loading.value = true
  try {
    const res = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const list: any[] = Array.isArray(res) ? res : (res?.data ?? [])
    const map: Record<string, any> = {}
    for (const r of list) map[r.item_id] = { conclusion: r.conclusion, remark: r.remark }
    hydrate(map)
  } catch { /* 空表单 */ } finally {
    loading.value = false
  }
}

// ─── 保存（防抖 per-item） ───
const _timers: Record<string, ReturnType<typeof setTimeout>> = {}
function saveItem(itemId: string, remark: string) {
  if (props.readonly || !props.wpId) return
  if (_timers[itemId]) clearTimeout(_timers[itemId])
  _timers[itemId] = setTimeout(async () => {
    try {
      await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
        project_id: props.projectId || undefined,
        items: [{ item_id: itemId, conclusion: null, remark }],
      })
      scheduleAutoSnapshot()
    } catch { /* silent */ }
  }, 700)
}

function saveSteps() { saveItem('B2-12-steps', JSON.stringify(steps.value)) }

// ─── 步骤附件上传（Task G / 证据留痕） ───
async function handleStepUpload(index: number, options: any) {
  if (props.readonly || !props.projectId) return
  try {
    const fd = new FormData()
    fd.append('file', options.file)
    const att: any = await uploadAttachment(props.projectId, fd)
    const id = att?.id || att?.data?.id
    const name = att?.file_name || att?.data?.file_name || options.file?.name || '附件'
    if (id && steps.value[index]) {
      steps.value[index].attachmentId = id
      steps.value[index].attachmentName = name
      saveSteps()
      ElMessage.success('附件已上传')
    }
  } catch {
    ElMessage.error('附件上传失败')
  }
}
function stepAttachmentUrl(index: number): string {
  const id = steps.value[index]?.attachmentId
  return id ? `/api/attachments/${id}/preview` : ''
}
function removeStepAttachment(index: number) {
  if (props.readonly || !steps.value[index]) return
  steps.value[index].attachmentId = ''
  steps.value[index].attachmentName = ''
  saveSteps()
}
function saveConclusions() { saveItem('B2-12-conclusions', JSON.stringify(conclusions.value)) }
function saveNote() { saveItem('B2-12-note', note.value) }

// ─── AI 辅助（综合结论说明） ───
async function handleAi() {
  if (props.readonly) return
  aiLoading.value = true
  try {
    const existingIssues = conclusions.value
      .map((c, i) => ({ c, i }))
      .filter(({ c }) => c.exists === '是')
      .map(({ c, i }) => `${i + 1}. ${CONCLUSION_DEFS[i]} 应对措施：${c.measure || '（未填）'}`)
      .join('；')
    const res: any = await api.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'b2-12-conclusion',
      prompt: '根据对前任注册会计师的 9 步了解程序与 7 点结论判断，撰写"执行程序的结论及对审计计划、审计程序的影响"综合说明。若存在不利事项需说明应对措施与对审计计划/程序的影响。',
      context: {
        被审计单位: String(clientName.value || ''),
        会计期间: String(auditYear.value || ''),
        存在不利事项数: String(existsCount.value),
        不利事项明细: existingIssues || '无',
      },
      existingContent: note.value || '',
    })
    const text = res?.data?.content ?? res?.content ?? res?.data?.text ?? res?.text ?? ''
    if (text) {
      note.value = text
      saveNote()
      ElMessage.success('AI 已生成综合评价说明')
    } else {
      ElMessage.warning('AI 暂无返回，请稍后重试或手工填写')
    }
  } catch {
    ElMessage.warning('AI 服务不可用，请手工填写')
  } finally {
    aiLoading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="gt-b212" v-loading="loading">
    <!-- 抬头 + 说明 -->
    <el-alert type="info" :closable="false" show-icon class="gt-b212__desc">
      <template #title>
        对前任注册会计师的评价底稿（准则 1153 号 §5.2）：适用于重新审计（含 IPO 三年一期 /
        重大资产重组两年一期期间内变更审计机构等），后任拟查阅前任底稿或在其协助下取得审计证据时的评价记录。
      </template>
    </el-alert>
    <div class="gt-b212__toolbar">
      <div v-if="clientName || auditYear" class="gt-b212__head">
        <span>客户名称：<b>{{ clientName || '—' }}</b></span>
        <span>会计期间：<b>{{ auditYear || '—' }}</b></span>
        <span>索引号：B2-12</span>
      </div>
      <div class="gt-b212__toolbar-actions">
        <el-button size="small" @click="exportDocx">导出 Word</el-button>
        <el-button size="small" @click="openVersionHistory">版本历史</el-button>
      </div>
    </div>

    <!-- 9 步了解程序 -->
    <el-card shadow="never" class="gt-b212__card">
      <template #header>
        <span class="gt-b212__title">一、所执行的程序及了解到情况的记录</span>
        <el-button link size="small" class="gt-b212__review" @click="openReview({ sectionId: 'b2-12-steps', sectionLabel: 'B2-12 了解程序' })">💬 复核</el-button>
      </template>
      <el-table :data="STEP_DEFS" border size="small" class="gt-b212__table">
        <el-table-column label="序号" width="56" align="center">
          <template #default="{ row }">{{ row.seq }}</template>
        </el-table-column>
        <el-table-column label="所执行的程序" min-width="360">
          <template #default="{ row }">
            <div class="gt-b212__proc">{{ row.text }}</div>
            <div v-if="row.subItems" class="gt-b212__subs">
              <div v-for="(sub, j) in row.subItems" :key="j" class="gt-b212__sub">
                <el-checkbox
                  v-model="steps[row.seq - 1].subChecks[j]"
                  :disabled="readonly"
                  @change="saveSteps"
                >
                  <span class="gt-b212__sub-text">{{ sub }}</span>
                </el-checkbox>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="了解到情况的记录" min-width="300">
          <template #default="{ row }">
            <el-input
              v-model="steps[row.seq - 1].record"
              type="textarea"
              :autosize="{ minRows: 2 }"
              :disabled="readonly"
              placeholder="记录了解到的情况"
              @change="saveSteps"
            />
          </template>
        </el-table-column>
        <el-table-column label="附件" width="130" align="center">
          <template #default="{ row }">
            <div v-if="steps[row.seq - 1].attachmentId" class="gt-b212__att">
              <a :href="stepAttachmentUrl(row.seq - 1)" target="_blank" :title="steps[row.seq - 1].attachmentName">
                📎 {{ steps[row.seq - 1].attachmentName }}
              </a>
              <el-button v-if="!readonly" link size="small" @click="removeStepAttachment(row.seq - 1)">移除</el-button>
            </div>
            <el-upload
              v-else-if="!readonly"
              :show-file-list="false"
              :before-upload="() => true"
              :http-request="(opt: any) => handleStepUpload(row.seq - 1, opt)"
            >
              <el-button link size="small">📎 上传</el-button>
            </el-upload>
            <span v-else>—</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 7 点结论判断矩阵 -->
    <el-card shadow="never" class="gt-b212__card">
      <template #header>
        <span class="gt-b212__title">二、记录执行程序的结论及对审计计划、审计程序的影响</span>
        <el-tag v-if="existsCount > 0" type="danger" effect="dark" size="small" class="gt-b212__badge">
          存在 {{ existsCount }} 项不利事项，需记录应对措施
        </el-tag>
        <el-button
          v-if="!readonly && existsCount > 0"
          type="warning"
          plain
          size="small"
          class="gt-b212__push"
          @click="pushToB50"
        >推送发现至 B50 风险因素</el-button>
        <el-button link size="small" class="gt-b212__review" @click="openReview({ sectionId: 'b2-12-conclusions', sectionLabel: 'B2-12 结论判断' })">💬 复核</el-button>
      </template>
      <el-alert type="warning" :closable="false" class="gt-b212__hint">
        <template #title>
          说明：说明是否发现存在以下情况。如存在，需记录相关应对措施及对审计计划、审计程序的影响。
        </template>
      </el-alert>
      <el-table :data="CONCLUSION_DEFS" border size="small" class="gt-b212__table" :row-class-name="conclusionRowClass">
        <el-table-column label="序号" width="56" align="center">
          <template #default="{ $index }">{{ $index + 1 }}</template>
        </el-table-column>
        <el-table-column label="判断事项" min-width="340">
          <template #default="{ row }">{{ row }}</template>
        </el-table-column>
        <el-table-column label="是否存在" width="120" align="center">
          <template #default="{ $index }">
            <el-select
              v-model="conclusions[$index].exists"
              size="small"
              :disabled="readonly"
              @change="saveConclusions"
            >
              <el-option v-for="o in EXISTS_OPTIONS" :key="o" :label="o" :value="o" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="应对措施" min-width="220">
          <template #default="{ $index }">
            <el-input
              v-model="conclusions[$index].measure"
              type="textarea"
              :autosize="{ minRows: 2 }"
              :disabled="readonly || conclusions[$index].exists !== '是'"
              :placeholder="conclusions[$index].exists === '是' ? '记录应对措施' : '（无需填写）'"
              @change="saveConclusions"
            />
          </template>
        </el-table-column>
        <el-table-column label="对审计计划及程序的影响" min-width="220">
          <template #default="{ $index }">
            <el-input
              v-model="conclusions[$index].impact"
              type="textarea"
              :autosize="{ minRows: 2 }"
              :disabled="readonly || conclusions[$index].exists !== '是'"
              :placeholder="conclusions[$index].exists === '是' ? '记录对审计计划及程序的影响' : '（无需填写）'"
              @change="saveConclusions"
            />
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 综合评价说明 -->
    <el-card shadow="never" class="gt-b212__card">
      <template #header>
        <span class="gt-b212__title">三、综合评价说明</span>
        <el-button
          v-if="!readonly"
          type="primary"
          plain
          size="small"
          :loading="aiLoading"
          class="gt-b212__ai"
          @click="handleAi"
        >🤖 AI 辅助说明</el-button>
        <el-button link size="small" class="gt-b212__review" @click="openReview({ sectionId: 'b2-12-note', sectionLabel: 'B2-12 综合说明' })">💬 复核</el-button>
      </template>
      <el-input
        v-model="note"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="readonly"
        placeholder="综合上述程序，说明对前任注册会计师的整体评价结论及对本期审计计划、审计程序的影响。"
        @change="saveNote"
      />
    </el-card>

    <!-- 版本历史抽屉 + 复核对话 Host（对齐 B60 范式） -->
    <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
    <GtWpReviewDialogHost />
  </div>
</template>

<style scoped>
.gt-b212 { padding: 6px; font-size: 13px; }
.gt-b212__desc { margin-bottom: 10px; }
.gt-b212__toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
.gt-b212__toolbar-actions { display: flex; gap: 8px; flex-shrink: 0; }
.gt-b212__review { float: right; margin-left: 8px; color: var(--gt-color-primary, #4b2d77); }
.gt-b212__att { display: flex; flex-direction: column; gap: 2px; font-size: 12px; }
.gt-b212__att a { color: var(--gt-color-primary, #4b2d77); word-break: break-all; }
.gt-b212__head {
  display: flex; gap: 24px; padding: 6px 10px; margin-bottom: 10px;
  background: var(--gt-color-primary-bg, #f4f0fa); border-radius: 6px; font-size: 13px;
}
.gt-b212__card { margin-bottom: 14px; }
.gt-b212__title { font-weight: 600; color: var(--gt-color-primary, #4b2d77); }
.gt-b212__badge { margin-left: 12px; }
.gt-b212__ai { float: right; }
.gt-b212__push { float: right; margin-left: 8px; }
.gt-b212__hint { margin-bottom: 10px; }
.gt-b212__table :deep(.el-table__cell) { font-size: 13px; vertical-align: top; }
.gt-b212__proc { line-height: 1.5; }
.gt-b212__subs { margin-top: 6px; display: flex; flex-direction: column; gap: 4px; }
.gt-b212__sub-text { white-space: normal; line-height: 1.4; font-size: 12px; }
/* 存在不利事项行高亮（P5） */
.gt-b212__table :deep(.el-table__row.exists-row) { background: #fef0f0; }
</style>
