<template>
  <div class="g5-ecl-policy">
    <div class="section-head tab-toolbar">
      <h3 class="sheet-title">G5-8 信用减值损失会计政策检查</h3>
      <GtIndexChip value="wp:G5-8" />
    </div>

    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title><span class="ao-title">一、审计目标</span></template>
      <ol class="ao-list">
        <li v-for="(obj, i) in policy.auditObjectives" :key="i">{{ obj }}</li>
      </ol>
    </el-alert>

    <details class="prep-hint top-hint">
      <summary>📋 编制提示（CAS 22 · 源模板要点）</summary>
      <ul>
        <li>按「政策说明 → 历史损失 → 前瞻性信息 → 同业对比」四段形成证据链，再归纳说明与结论。</li>
        <li>组合划分须与 G5-3 坏账准备明细、会计政策披露及附注「按组合计提」名称一致。</li>
        <li>关注是否利用会计政策/估计变更操纵利润，是否存在管理层偏向迹象。</li>
        <li>结论应与 G5-9 三阶段划分、G5-10 减值测算所用损失率相互印证。</li>
      </ul>
    </details>

    <div class="process-tag-row">
      <el-tag size="small" type="info">二、审计过程</el-tag>
    </div>

    <!-- 四段评价 -->
    <div v-for="item in policy.evalItems" :key="item.id" class="eval-card">
      <div class="eval-header">
        <span class="eval-title">{{ item.title }}</span>
        <el-button
          size="small"
          type="primary"
          plain
          :disabled="props.readonly || !aiAvailable"
          :loading="aiLoading"
          @click="aiGenerateEval(item)"
        >🤖 AI辅助</el-button>
      </div>

      <div class="amber-context">
        <span class="amber-icon">📌</span>
        <span class="amber-text">{{ item.guidance }}</span>
      </div>

      <el-input
        :model-value="policy.paragraphs.value[item.id]"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 16 }"
        :disabled="props.readonly"
        :placeholder="item.placeholder"
        @update:model-value="(v: string) => { policy.setParagraph(item.id, v); persistPolicy() }"
      />

      <!-- (一) 组合划分表 -->
      <template v-if="item.id === 'policy'">
        <div class="group-block">
          <div class="group-block-head">
            <span class="group-block-title">组合划分（与会计政策披露一致）</span>
            <el-button size="small" plain :disabled="props.readonly" @click="onAddGroup">+ 新增组合</el-button>
          </div>
          <el-alert
            type="warning"
            :closable="false"
            show-icon
            class="policy-group-tip"
            title="【注意：与会计政策中披露的组合保持一致】组合名称将同步到 G5-3 / 上市·国企附注「按组合计提」账龄块。"
          />
          <el-table :data="policy.section2.value" border size="small" class="group-table">
            <el-table-column label="组合名称" min-width="140">
              <template #default="{ row }">
                <el-input v-model="row.checkItem" size="small" :disabled="props.readonly" @change="persistPolicy" />
              </template>
            </el-table-column>
            <el-table-column label="划分依据（款项性质/风险特征）" min-width="180">
              <template #default="{ row }">
                <el-input
                  v-model="row.requirement"
                  size="small"
                  :disabled="props.readonly"
                  placeholder="如：融资租赁应收款"
                  @change="persistPolicy"
                />
              </template>
            </el-table-column>
            <el-table-column label="企业政策披露名称" min-width="140">
              <template #default="{ row }">
                <el-input
                  v-model="row.companyPolicy"
                  size="small"
                  :disabled="props.readonly"
                  placeholder="默认同组合名称"
                  @change="persistPolicy"
                />
              </template>
            </el-table-column>
            <el-table-column label="合规性" width="100">
              <template #default="{ row }">
                <el-select v-model="row.compliance" size="small" :disabled="props.readonly" @change="persistPolicy">
                  <el-option label="合规" value="合规" />
                  <el-option label="不合规" value="不合规" />
                  <el-option label="待核实" value="待核实" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="说明" min-width="120">
              <template #default="{ row }">
                <el-input v-model="row.explanation" size="small" :disabled="props.readonly" @change="persistPolicy" />
              </template>
            </el-table-column>
            <el-table-column v-if="!props.readonly" label="操作" width="64" align="center">
              <template #default="{ row }">
                <el-button
                  size="small"
                  type="danger"
                  link
                  :disabled="policy.section2.value.length <= 1"
                  @click="onRemoveGroup(row.id)"
                >删</el-button>
              </template>
            </el-table-column>
          </el-table>

          <details class="checklist-details">
            <summary>准则对照要点（可选勾稽）</summary>
            <el-table :data="policy.section1.value" border size="small" class="group-table">
              <el-table-column prop="checkItem" label="检查项" min-width="120" />
              <el-table-column prop="requirement" label="要求" min-width="180" />
              <el-table-column label="企业政策" min-width="120">
                <template #default="{ row }">
                  <el-input v-model="row.companyPolicy" size="small" :disabled="props.readonly" @change="persistPolicy" />
                </template>
              </el-table-column>
              <el-table-column label="合规性" width="100">
                <template #default="{ row }">
                  <el-select v-model="row.compliance" size="small" :disabled="props.readonly" @change="persistPolicy">
                    <el-option label="合规" value="合规" />
                    <el-option label="不合规" value="不合规" />
                    <el-option label="待核实" value="待核实" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="说明" min-width="120">
                <template #default="{ row }">
                  <el-input v-model="row.explanation" size="small" :disabled="props.readonly" @change="persistPolicy" />
                </template>
              </el-table-column>
            </el-table>
          </details>
        </div>
      </template>

      <!-- (四) 同业案例 -->
      <template v-if="item.id === 'peer'">
        <details class="ref-details">
          <summary>📘 上市公司会计政策披露示例（点击展开，可一键套用到本节）</summary>
          <div class="ref-grid">
            <div v-for="ref in policy.industryRefs" :key="ref.company" class="ref-item">
              <div class="ref-item-header">
                <span class="ref-company">{{ ref.company }}</span>
                <el-button
                  size="small"
                  type="success"
                  plain
                  :disabled="props.readonly"
                  @click="onApplyIndustry(ref)"
                >套用</el-button>
              </div>
              <div class="ref-policy">{{ ref.policy }}</div>
            </div>
          </div>
        </details>
      </template>
    </div>

    <!-- 说明与结论 -->
    <el-card shadow="never" class="opinion-card">
      <template #header>
        <div class="opinion-header">
          <span>三 / 四、审计说明与结论</span>
          <el-select
            v-model="selectedTemplate"
            placeholder="快速选择结论模板"
            size="small"
            clearable
            :disabled="props.readonly"
            style="width: 240px"
            @change="onTemplateSelect"
          >
            <el-option
              v-for="t in policy.conclusionTemplates"
              :key="t.label"
              :label="t.label"
              :value="t.value"
            />
          </el-select>
        </div>
      </template>
      <div class="amber-context amber-conclusion">
        <span class="amber-icon">📌</span>
        <span class="amber-text">源模板结论参考：被审计单位预期减值计提相关的会计政策和会计估计与同行业企业大体一致，反映经营业务实际情况，与同业相比不存在显著差异，且计提准备政策得到一贯执行。——请按项目实际情况改写后落结论。</span>
      </div>
      <G5AuditTextCards
        :wp-id="props.wpId"
        :is-readonly="!!props.readonly"
        :note="auditNote"
        :conclusion="policy.conclusion.value"
        note-title="三、审计说明"
        conclusion-title="四、审计结论"
        conclusion-ai-section="ecl-policy-conclusion"
        :related-context="aiContext"
        note-placeholder="填写审计说明：可概述 ECL 会计政策核对情况、组合划分核实、历史/前瞻性信息及同业对比的主要发现。"
        conclusion-placeholder="填写综合结论：A、政策合规且与同业无重大差异、一贯执行。B、除下述事项外未见异常。C、存在重大不合规或参数不当事项。"
        @update:note="saveAuditNote"
        @update:conclusion="(v: string) => { policy.conclusion.value = v }"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, watch, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import {
  useG5EclPolicy,
  type IndustryPolicyRef,
  type PolicyEvalItem,
} from '../../composables/useG5EclPolicy'
import { useInjectedG5FormData } from '../../composables/useG5LonRecFormData'
import { G5_ITEM_IDS, readCanonicalRaw } from '../../composables/g5StorageContract'
import { useG5AiGenerate, type G5AiSection } from '../../composables/useG5AiGenerate'
import GtIndexChip from '../../GtIndexChip.vue'
import G5AuditTextCards from '../G5AuditTextCards.vue'

const props = defineProps<{ htmlData?: any; wpId: string; projectId: string; readonly?: boolean }>()
const policy = useG5EclPolicy()
const wpIdRef = toRef(props, 'wpId')
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useG5AiGenerate(wpIdRef)

const g5Notes = useInjectedG5FormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })
const auditNote = ref('')
const selectedTemplate = ref('')
const G5_NOTE_KEY = 'G5-8-audit-note'
const G5_CONCLUSION_KEY = 'G5-8-audit-conclusion'
const G5_POLICY_KEY = G5_ITEM_IDS.G5_8_POLICY
let persistReady = false

const aiContext = computed(() => ({
  组合划分: policy.groupNames().join('、'),
  政策说明: policy.paragraphs.value.policy,
  历史坏账: policy.paragraphs.value.historical,
  前瞻性信息: policy.paragraphs.value.forwardLooking,
  同业对比: policy.paragraphs.value.peer,
}))

function saveAuditNote(val: string): void {
  if (props.readonly) return
  auditNote.value = val
  void g5Notes.saveImmediate(G5_NOTE_KEY, { conclusion: null, remark: val })
}

function persistPolicy() {
  if (!persistReady || props.readonly) return
  const json = policy.serialize()
  void g5Notes.debouncedSave(G5_POLICY_KEY, { conclusion: json, remark: json })
}

async function onAddGroup() {
  await policy.addSection2Row()
  persistPolicy()
}

function onRemoveGroup(id: string) {
  policy.removeSection2Row(id)
  persistPolicy()
}

function onApplyIndustry(ref: IndustryPolicyRef) {
  policy.applyIndustryRef(ref)
  persistPolicy()
  ElMessage.success(`已套用 ${ref.company} 政策示例`)
}

function onTemplateSelect(val: string) {
  if (!val) return
  policy.applyConclusionTemplate(val)
  selectedTemplate.value = ''
  persistPolicy()
}

async function aiGenerateEval(item: PolicyEvalItem) {
  const content = await generateAndConfirm(
    item.aiSection as G5AiSection,
    policy.paragraphs.value[item.id] || '',
    {
      ...aiContext.value,
      评价段落: item.title,
      方法论要求: item.guidance,
    },
    `G5-8 ${item.title}`,
  )
  if (content) {
    policy.setParagraph(item.id, content)
    persistPolicy()
  }
}

watch(() => policy.conclusion.value, (val) => {
  if (props.readonly) return
  void g5Notes.saveImmediate(G5_CONCLUSION_KEY, { conclusion: null, remark: val ?? '' })
  persistPolicy()
})

watch(
  () => [
    policy.section1.value,
    policy.section2.value,
    policy.section3.value,
    policy.section4.value,
    policy.paragraphs.value,
  ],
  () => persistPolicy(),
  { deep: true },
)

onMounted(async () => {
  try { await g5Notes.loadAll() } catch { /* ignore */ }
  const n = g5Notes.allResponses.value.get(G5_NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = g5Notes.allResponses.value.get(G5_CONCLUSION_KEY)
  if (c?.remark) policy.conclusion.value = c.remark
  const p = readCanonicalRaw(g5Notes.allResponses.value.get(G5_POLICY_KEY))
  if (p) policy.loadFromRaw(p)
  persistReady = true
})
</script>

<style scoped>
.g5-ecl-policy { font-size: var(--wp-font-size, 13px); padding: 4px; }
.section-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.audit-objective { margin-bottom: 10px; }
.ao-title { font-weight: 600; }
.ao-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.7; font-size: 12px; }
.process-tag-row { margin: 8px 0 10px; }
.eval-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 12px 14px;
  margin-bottom: 12px;
  background: var(--el-bg-color);
}
.eval-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.eval-title { font-weight: 600; font-size: 13px; }
.amber-context {
  display: flex;
  gap: 8px;
  background: #fffbeb;
  border-left: 3px solid var(--el-color-warning);
  padding: 8px 10px;
  margin-bottom: 10px;
  font-size: 12px;
  line-height: 1.65;
  color: var(--el-text-color-regular);
}
.amber-conclusion { margin-bottom: 12px; }
.amber-icon { flex-shrink: 0; }
.group-block { margin-top: 12px; }
.group-block-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.group-block-title { font-weight: 500; font-size: 12px; color: var(--el-text-color-primary); }
.policy-group-tip { margin-bottom: 8px; }
.group-table { font-size: 13px; }
.checklist-details, .ref-details, .prep-hint {
  margin-top: 10px;
  font-size: 12px;
  color: #606266;
}
.checklist-details summary,
.ref-details summary,
.prep-hint summary {
  cursor: pointer;
  font-weight: 500;
  color: var(--el-text-color-regular);
}
.prep-hint ul { margin: 6px 0 0; padding-left: 18px; line-height: 1.8; }
.top-hint { margin-bottom: 10px; color: #909399; }
.ref-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 10px;
  margin-top: 10px;
}
.ref-item {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 8px 10px;
  background: #fafafa;
}
.ref-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.ref-company { font-weight: 600; font-size: 12px; }
.ref-policy {
  font-size: 11px;
  line-height: 1.6;
  color: var(--el-text-color-secondary);
  white-space: pre-wrap;
}
.opinion-card { margin-top: 4px; }
.opinion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}
</style>
