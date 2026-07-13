<template>
  <div class="i2-tab-policy-check">
    <!-- Section Header -->
    <div class="section-header">
      <span class="section-title">I2-4 会计政策检查 — 研发/开发支出会计政策适当性</span>
      <div class="section-actions">
        <el-button size="small" type="default" text @click="handleReview">复核</el-button>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：检查研发支出资本化会计政策是否符合会计准则要求、是否符合研发业务特点及行业惯例，研究阶段与开发阶段界定时点、开发完成时点的界定是否合理，前后期政策是否一贯。" />

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 访谈管理层，了解业务类型、研发项目流程与研发模式，针对不同业务或模式检查会计政策合理性及与前期一致性；</p>
        <p>2. 重点核查研发费用归集范围、资本化时点、非全时研发人员工时分摊、高新认定及加计扣除等政策；</p>
        <p>3. 检查研究阶段与开发阶段界定时点、开发完成时点界定是否合理（CAS6§7-9）；</p>
        <p>4. 将本期会计政策/估计与前期及同行业公司对比，关注是否利用政策变更操纵利润；</p>
        <p>5. 依据 CAS6《无形资产》、财会〔2019〕6号研发费用列示要求。</p>
      </div>
    </details>

    <!-- 方法论上下文（源模板 I2-4 融入） -->
    <div class="methodology-context">
      <p><strong>研究阶段 vs 开发阶段（CAS6）：</strong>研究阶段支出全部费用化计入当期损益；开发阶段支出满足"五个条件"方可资本化。确实无法区分研究阶段与开发阶段支出的，应将其所发生的研发支出全部费用化。</p>
      <p><strong>明细核算：</strong>开发支出可按研究开发项目分别"费用化支出"、"资本化支出"进行明细核算；研发费用核算时应从开发支出的贷方转出，不能直接列支在损益中。</p>
    </div>

    <!-- 索引工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-right">
        <GtIndexChip value="wp:I2" :context-project-id="props.projectId" />
        <el-tag size="small" type="info">共 {{ checkItems.length }} 项</el-tag>
      </div>
    </div>

    <!-- 进度条 -->
    <div class="progress-section">
      <el-progress :percentage="completionPct" :stroke-width="10" :format="() => `${completedCount}/${checkItems.length}`" />
    </div>

    <!-- 检查项卡片列表 -->
    <el-card
      v-for="(item, idx) in checkItems"
      :key="item.key"
      shadow="never"
      class="check-card"
      :class="{ 'check-card-done': item.conclusion === '是' || item.conclusion === '不适用' }"
    >
      <template #header>
        <div class="card-title-row">
          <span class="check-title">{{ idx + 1 }}. {{ item.label }}</span>
          <el-tag v-if="item.conclusion" :type="conclusionTagType(item.conclusion)" size="small">
            {{ item.conclusion }}
          </el-tag>
        </div>
      </template>

      <!-- 准则/依据引用 -->
      <div class="cas-reference">
        <el-icon><InfoFilled /></el-icon>
        <span>{{ item.casRef }}</span>
      </div>

      <!-- 被审计单位实际政策 -->
      <div class="field-group">
        <label>被审计单位实际政策：</label>
        <el-input
          :model-value="item.actualPolicy"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          :disabled="isReadonly"
          placeholder="描述被审计单位就此方面的实际会计政策..."
          @change="(v: string) => onItemChange(idx, 'actualPolicy', v)"
        />
      </div>

      <!-- 审计师评价 -->
      <div class="field-group">
        <label>审计师评价：</label>
        <el-input
          :model-value="item.evaluation"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          :disabled="isReadonly"
          placeholder="评价该政策是否符合准则要求、是否符合研发业务特点及行业惯例..."
          @change="(v: string) => onItemChange(idx, 'evaluation', v)"
        />
      </div>

      <!-- 勾选结论 -->
      <div class="field-group conclusion-group">
        <label>结论：</label>
        <el-radio-group
          :model-value="item.conclusion"
          :disabled="isReadonly"
          @change="(v: any) => onItemChange(idx, 'conclusion', String(v))"
        >
          <el-radio value="是">符合</el-radio>
          <el-radio value="否">不符合</el-radio>
          <el-radio value="不适用">不适用</el-radio>
        </el-radio-group>
      </div>

      <!-- 否时强制说明 -->
      <div v-if="item.conclusion === '否'" class="field-group n-explanation">
        <label>不符合原因及影响：</label>
        <el-input
          :model-value="item.explanationIfNo"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 4 }"
          :disabled="isReadonly"
          placeholder="必须说明不符合准则的具体原因和对审计的潜在影响..."
          @change="(v: string) => onItemChange(idx, 'explanationIfNo', v)"
        />
        <el-alert v-if="!item.explanationIfNo" type="error" :closable="false" show-icon>
          结论为"不符合"时必须填写原因说明
        </el-alert>
      </div>
    </el-card>

    <!-- 操作按钮 -->
    <div class="table-actions">
      <el-button size="small" type="success" :disabled="isReadonly" @click="handleSave">保存</el-button>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><span>审计说明</span></template>
      <el-input type="textarea" :model-value="auditNote" :disabled="isReadonly" :autosize="{ minRows: 5 }" placeholder="记录审计过程、发现的问题及处理..." @change="saveAuditNote" />
    </el-card>
    <el-card shadow="never" class="audit-conclusion-card">
      <template #header><span>审计结论</span></template>
      <el-input type="textarea" :model-value="auditConclusion" :disabled="isReadonly" :autosize="{ minRows: 3 }" placeholder="填写会计政策检查总体结论..." @change="saveAuditConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * I2TabPolicyCheck.vue — I2-4 会计政策检查（研发/开发支出）
 *
 * 段落型检查组件。逐项对照 CAS6 检查研发支出资本化会计政策适当性。
 * 每个检查项：准则/依据引用 → 被审计单位政策 → 审计师评价 → 结论(符合/不符合/不适用)。
 * 无 AI 辅助（I 循环无 AI composable，P7 铁律：纯 textarea）。
 *
 * Storage: 检查项 JSON → 'I2-4-policy-items'；审计说明/结论 → 'I2-4-audit-note' / 'I2-4-audit-conclusion'
 * 源模板：I无形资产循环底稿模板库 §会计政策检查 I2-4 / I2A 程序步骤 4
 * Requirements: 1.1, 1.2, 2.1, 3.1, 3.3, 4.1, 5.1, 7.1
 */
import { ref, reactive, computed, inject, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { InfoFilled } from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'

// ─── Props & Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveResponse: (sheetCode: string, data: Record<string, any>) => Promise<void>
  isReadonly?: boolean
}>()

const emit = defineEmits<{
  'save': []
  'navigate-sheet': [sheetName: string]
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

// ─── Check Items Definition ──────────────────────────────────────────────────

interface CheckItem {
  key: string
  label: string
  casRef: string
  actualPolicy: string
  evaluation: string
  conclusion: string
  explanationIfNo: string
}

const CHECK_ITEM_DEFS: Pick<CheckItem, 'key' | 'label' | 'casRef'>[] = [
  {
    key: 'research-development-split',
    label: '研究阶段与开发阶段界定',
    casRef: 'CAS6§7-8：研究阶段的支出全部费用化计入当期损益；企业须根据研发立项、可行性研究报告、董事会纪要等文件合理界定研究阶段与开发阶段的时点。',
  },
  {
    key: 'capitalization-policy',
    label: '开发支出资本化会计政策',
    casRef: 'CAS6§9：开发阶段支出同时满足"五个条件"方可资本化确认为无形资产；须检查资本化归集范围、资本化时点及开发完成时点界定是否合理、是否符合研发业务特点与行业惯例。',
  },
  {
    key: 'cost-aggregation-scope',
    label: '研发费用归集范围',
    casRef: '研发支出应单独核算，包括直接研发人员工资、材料费、相关设备折旧费、委外研发费等；同时从事多项研究开发活动的，应按合理标准分摊，无法合理分配的计入当期损益。',
  },
  {
    key: 'part-time-staff-allocation',
    label: '非全时研发人员工时分摊政策',
    casRef: '非全时研发人员应清晰统计从事不同职能的工时情况，按企业会计准则将属于研发活动的薪酬准确合理分摊计入研发支出；工时占比低于50%的原则上不应认定为研发人员。',
  },
  {
    key: 'expense-capitalize-detail',
    label: '费用化/资本化明细核算',
    casRef: '开发支出可按研究开发项目分别"费用化支出"、"资本化支出"明细核算；研发费用应从开发支出贷方转出，不能直接列支在损益中。',
  },
  {
    key: 'policy-consistency',
    label: '会计政策一贯性及税会差异',
    casRef: '将本期会计政策/估计与前期及同行业公司对比，关注是否利用政策变更操纵利润；关注高新技术认定及研发费用加计扣除的税会差异是否恰当处理（CAS28/财会〔2019〕6号）。',
  },
]

const checkItems = reactive<CheckItem[]>(
  CHECK_ITEM_DEFS.map((def) => ({
    ...def,
    actualPolicy: '',
    evaluation: '',
    conclusion: '',
    explanationIfNo: '',
  })),
)

// ─── Audit Note / Conclusion ─────────────────────────────────────────────────

const ITEMS_KEY = 'I2-4-policy-items'
const AUDIT_NOTE_KEY = 'I2-4-audit-note'
const AUDIT_CONCLUSION_KEY = 'I2-4-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

// ─── Computed ────────────────────────────────────────────────────────────────

const completedCount = computed(() => checkItems.filter((i) => !!i.conclusion).length)
const completionPct = computed(() =>
  checkItems.length === 0 ? 0 : Math.round((completedCount.value / checkItems.length) * 100),
)

// ─── Load ────────────────────────────────────────────────────────────────────

function readRemark(key: string): string {
  const raw = props.allResponses.get(key)
  if (raw == null) return ''
  return typeof raw === 'string' ? raw : (raw.remark ?? '')
}

function loadData() {
  const raw = props.allResponses.get(ITEMS_KEY)
  if (raw) {
    try {
      const text = typeof raw === 'string' ? raw : (raw.remark ?? '')
      const parsed = text ? JSON.parse(text) : null
      if (Array.isArray(parsed)) {
        for (const saved of parsed) {
          const target = checkItems.find((i) => i.key === saved.key)
          if (target) {
            target.actualPolicy = saved.actualPolicy || ''
            target.evaluation = saved.evaluation || ''
            target.conclusion = saved.conclusion || ''
            target.explanationIfNo = saved.explanationIfNo || ''
          }
        }
      }
    } catch { /* ignore parse errors */ }
  }
  auditNote.value = readRemark(AUDIT_NOTE_KEY)
  auditConclusion.value = readRemark(AUDIT_CONCLUSION_KEY)
}

watch(() => props.allResponses, () => loadData(), { immediate: true })
onMounted(loadData)

// ─── Events ──────────────────────────────────────────────────────────────────

function onItemChange(idx: number, field: keyof CheckItem, value: string) {
  if (props.isReadonly) return
  ;(checkItems[idx][field] as string) = value
}

async function handleSave() {
  if (props.isReadonly) return
  const payload = checkItems.map((i) => ({
    key: i.key,
    actualPolicy: i.actualPolicy,
    evaluation: i.evaluation,
    conclusion: i.conclusion,
    explanationIfNo: i.explanationIfNo,
  }))
  await props.saveResponse('I2-4', { [ITEMS_KEY]: JSON.stringify(payload) })
  emit('save')
  ElMessage.success('会计政策检查已保存')
}

function saveAuditNote(val: string) {
  if (props.isReadonly) return
  auditNote.value = val
  void props.saveResponse('I2-4', { [AUDIT_NOTE_KEY]: val })
}

function saveAuditConclusion(val: string) {
  if (props.isReadonly) return
  auditConclusion.value = val
  void props.saveResponse('I2-4', { [AUDIT_CONCLUSION_KEY]: val })
}

// ─── Review ──────────────────────────────────────────────────────────────────

function handleReview() {
  openReviewDialog('I2-4-会计政策检查')
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function conclusionTagType(conclusion: string): 'success' | 'danger' | 'info' {
  if (conclusion === '是') return 'success'
  if (conclusion === '否') return 'danger'
  return 'info'
}
</script>

<style scoped>
.i2-tab-policy-check { padding: 16px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { font-size: 15px; font-weight: 600; color: #1f2937; }
.section-actions { display: flex; align-items: center; gap: 4px; }

.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 14px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.7;
}
.methodology-context p { margin: 0 0 4px; }
.methodology-context strong { color: #78350f; }

.progress-section { margin-bottom: 16px; }

.check-card { margin-bottom: 12px; }
.check-card-done { border-left: 3px solid var(--el-color-success); }
.card-title-row { display: flex; align-items: center; justify-content: space-between; }
.check-title { font-weight: 600; color: #374151; }

.cas-reference {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 8px 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  margin-bottom: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}

.field-group { margin-bottom: 12px; }
.field-group label { display: block; font-weight: 500; margin-bottom: 4px; }
.conclusion-group { display: flex; align-items: center; gap: 12px; }
.n-explanation { border-left: 3px solid var(--el-color-danger); padding-left: 12px; }

.table-actions { display: flex; gap: 8px; margin-top: 12px; margin-bottom: 8px; }

.objective-alert { margin-bottom: 12px; }
.guidance-details { margin-bottom: 12px; font-size: 12px; color: var(--el-text-color-secondary); background: #f9fafb; border: 1px solid #ebeef5; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 600; color: #374151; }
.guidance-details .guidance-content { margin-top: 8px; line-height: 1.7; }
.guidance-details .guidance-content p { margin: 0 0 4px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 10px; }
.tab-toolbar .toolbar-right { display: flex; align-items: center; gap: 8px; }
.audit-note-card, .audit-conclusion-card { margin-top: 16px; }
</style>
