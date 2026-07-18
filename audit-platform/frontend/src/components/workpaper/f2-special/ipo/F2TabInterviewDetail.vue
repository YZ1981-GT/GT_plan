<template>
  <div class="f2-interview-detail f2-ipo-soft">
    <header class="sheet-header">
      <div>
        <h3>供应商访谈记录</h3>
        <span class="code">F2-72 · 逐家正式访谈问卷（卡片列表 / 问卷详情 / 在线编辑），联动 F2-71/70/68</span>
      </div>
      <div class="stats">
        <el-tag size="small">访谈 {{ iv.summary.value.interviewCount }} 份</el-tag>
        <el-tag v-if="iv.summary.value.incompleteCount" size="small" type="warning">
          待完善 {{ iv.summary.value.incompleteCount }} 份
        </el-tag>
        <el-tag v-if="iv.summary.value.riskCount" size="small" type="danger">
          风险提示 {{ iv.summary.value.riskCount }} 份
        </el-tag>
      </div>
    </header>

    <details class="guidance-details">
      <summary>📋 审计目标与编制思路</summary>
      <div class="guidance-content">
        <p><strong>一、审计目标：</strong>{{ objective }}</p>
        <p><strong>二、编制思路：</strong>本表不是汇总矩阵，而是「一家供应商一份正式访谈记录」。按源表十一项提纲逐题记录回答；第10、11题可按项目风险改写题干；访谈结束后留存工商资料、函证回函、银行流水等附件，并由受访人、审计人员签字确认真实性声明。</p>
        <p><strong>三、联动：</strong>可从 F2-71 带入访谈对象与日期，从 F2-70 带入公司概况起草第2题，从 F2-68 带入采购额起草第5题；完成后回填 F2-71「访谈记录索引」。</p>
        <p><strong>四、模式：</strong>左侧卡片选择访谈档案；右侧填写问卷详情；在线编辑请切换上方「在线编辑」页签。</p>
        <p>
          <strong>五、示例：</strong>不确定如何询问或记录时，点击
          <el-button link type="warning" @click="exampleVisible = true">「查看编制示例」</el-button>
          参照 XYZ 公司走访示例（查工商 → 问交易 → 核合同条款 → 看现场 → 现场函证 → 比关联方 → 下结论）。
        </p>
      </div>
    </details>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="openCreateDialog">
          + 新增访谈记录
        </el-button>
        <el-button size="small" type="warning" plain @click="exampleVisible = true">
          📚 查看编制示例
        </el-button>
        <el-input
          v-model="iv.searchQuery.value"
          size="small"
          clearable
          placeholder="搜索供应商/受访人"
          class="search"
        />
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-spe"
          sheet="F2-72"
          :disabled="isReadonly"
          review-section="F2-72-interview"
        />
        <GtIndexChip value="wp:F2-72" />
      </div>
    </div>

    <div class="layout">
      <!-- 左侧卡片列表 -->
      <aside class="list-panel">
        <button
          v-for="(entity, index) in iv.filteredEntities.value"
          :key="entity.id"
          type="button"
          class="list-card"
          :class="{ active: iv.currentId.value === entity.id, risk: entity.riskFlags.length > 0 }"
          @click="iv.selectEntity(entity.id)"
        >
          <div class="list-card-head">
            <span class="seq">访谈{{ index + 1 }}</span>
            <span class="pct formula">{{ Math.round(entity.completionPct * 100) }}%</span>
          </div>
          <strong>{{ entity.supplierName || '未命名供应商' }}</strong>
          <div class="list-meta">{{ entity.interviewee || '未填受访人' }} · {{ entity.interviewDate || '未填日期' }}</div>
          <div v-if="entity.riskFlags.length" class="list-risk">
            <el-tag v-for="flag in entity.riskFlags.slice(0, 2)" :key="flag" type="danger" size="small">
              {{ flag }}
            </el-tag>
          </div>
        </button>
        <button v-if="!isReadonly" type="button" class="add-list-card" @click="openCreateDialog">
          ＋ 弹窗新建访谈
        </button>
      </aside>

      <!-- 右侧问卷详情 -->
      <main v-if="cur" class="detail-panel">
        <el-card shadow="never" class="meta-card">
          <template #header>
            <div class="card-head">
              <span>访谈基本信息</span>
              <div class="card-actions">
                <el-button
                  size="small"
                  plain
                  :disabled="isReadonly || !cur.supplierName"
                  @click="iv.applyLinkage(cur.id)"
                >从 F2-71/70/68 带入</el-button>
                <GtIndexChip
                  v-if="cur.supplierName"
                  :value="`F2-71:${cur.supplierName}`"
                  label="→F2-71 汇总"
                />
                <el-button
                  v-if="!isReadonly"
                  size="small"
                  link
                  type="danger"
                  :disabled="iv.entities.value.length <= 1"
                  @click="iv.removeEntity(cur.id)"
                >删除本份</el-button>
              </div>
            </div>
          </template>
          <div class="meta-grid">
            <label class="field">
              <span>供应商名称</span>
              <el-select
                v-if="!isReadonly"
                :model-value="cur.supplierName || undefined"
                filterable
                allow-create
                default-first-option
                clearable
                placeholder="输入或选择（联动名单）"
                @change="onSupplierChange"
              >
                <el-option
                  v-for="name in iv.linkage.value.knownSuppliers"
                  :key="name"
                  :label="name"
                  :value="name"
                />
              </el-select>
              <span v-else>{{ cur.supplierName || '—' }}</span>
            </label>
            <label class="field">
              <span>访谈对象</span>
              <el-input
                :model-value="cur.interviewee"
                :disabled="isReadonly"
                placeholder="姓名 / 职务"
                @update:model-value="(v: string) => iv.updateEntity(cur!.id, { interviewee: v })"
              />
            </label>
            <label class="field">
              <span>访谈日期</span>
              <el-date-picker
                :model-value="cur.interviewDate"
                type="date"
                value-format="YYYY-MM-DD"
                style="width: 100%"
                :disabled="isReadonly"
                @update:model-value="(v: string | null) => iv.updateEntity(cur!.id, { interviewDate: v ?? '' })"
              />
            </label>
            <label class="field">
              <span>访谈时间及地点</span>
              <el-input
                :model-value="cur.interviewTimePlace"
                :disabled="isReadonly"
                placeholder="时间 / 地点"
                @update:model-value="(v: string) => iv.updateEntity(cur!.id, { interviewTimePlace: v })"
              />
            </label>
            <label class="field wide">
              <span>参与人员</span>
              <el-input
                :model-value="cur.participants"
                :disabled="isReadonly"
                placeholder="审计人员及其他参与人员"
                @update:model-value="(v: string) => iv.updateEntity(cur!.id, { participants: v })"
              />
            </label>
          </div>
          <p class="hint-blue">提示：请根据被审计单位实际情况及所关注供应商的主要风险情况修改访谈内容。</p>
          <div v-if="linkHints.length" class="link-hints">
            <el-tag v-for="hint in linkHints" :key="hint" size="small" type="info">{{ hint }}</el-tag>
          </div>
        </el-card>

        <el-card
          v-for="(item, index) in cur.qaItems"
          :key="item.key"
          shadow="never"
          class="qa-card"
        >
          <template #header>
            <div class="qa-head">
              <span>{{ questionSection(item.key, index) }}</span>
              <el-tag v-if="isEditablePrompt(item.key)" size="small" type="warning">可改写题干</el-tag>
            </div>
          </template>
          <el-input
            v-if="isEditablePrompt(item.key) && !isReadonly"
            :model-value="item.prompt"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
            class="prompt-edit"
            @update:model-value="(v: string) => iv.updateQa(cur!.id, item.key, { prompt: v })"
          />
          <p v-else class="prompt-text">{{ item.prompt }}</p>
          <el-input
            :model-value="item.answer"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 8 }"
            :disabled="isReadonly"
            :placeholder="questionPlaceholder(item.key)"
            @update:model-value="(v: string) => iv.updateQa(cur!.id, item.key, { answer: v })"
          />
        </el-card>

        <el-card shadow="never" class="attach-card">
          <template #header>
            <span>附：访谈证据附件</span>
          </template>
          <ol class="attach-list">
            <li>加盖供应商公章的工商登记资料</li>
            <li>供应商函证回函</li>
            <li>相关银行流水 / 现场照片 / 身份证与名片复印件等</li>
          </ol>
          <ItemAttachment
            v-if="projectId && wpId"
            :project-id="projectId"
            :wp-id="wpId"
            sheet-key="F2-72"
            :item-index="cur.attSlot"
          />
        </el-card>

        <el-card shadow="never" class="sign-card">
          <template #header><span>参与访谈各方签字</span></template>
          <div class="meta-grid">
            <label class="field">
              <span>被访谈人员</span>
              <el-input
                :model-value="cur.intervieweeSign"
                :disabled="isReadonly"
                @update:model-value="(v: string) => iv.updateEntity(cur!.id, { intervieweeSign: v })"
              />
            </label>
            <label class="field">
              <span>审计人员</span>
              <el-input
                :model-value="cur.auditorSign"
                :disabled="isReadonly"
                @update:model-value="(v: string) => iv.updateEntity(cur!.id, { auditorSign: v })"
              />
            </label>
            <label class="field">
              <span>其他人员</span>
              <el-input
                :model-value="cur.otherSign"
                :disabled="isReadonly"
                @update:model-value="(v: string) => iv.updateEntity(cur!.id, { otherSign: v })"
              />
            </label>
            <label class="field">
              <span>日期</span>
              <el-date-picker
                :model-value="cur.signDate"
                type="date"
                value-format="YYYY-MM-DD"
                style="width: 100%"
                :disabled="isReadonly"
                @update:model-value="(v: string | null) => iv.updateEntity(cur!.id, { signDate: v ?? '' })"
              />
            </label>
          </div>
          <div class="declaration">
            <el-checkbox
              :model-value="cur.declarationAck"
              :disabled="isReadonly"
              @change="(v: boolean | string | number) => iv.updateEntity(cur!.id, { declarationAck: Boolean(v) })"
            >
              本公司承诺所提供资料、信息及陈述真实、完整；如有虚假，愿意承担全部法律责任，并加盖公章。
            </el-checkbox>
          </div>
        </el-card>

        <el-card shadow="never" class="conclusion-card">
          <template #header><span>本份访谈结论</span></template>
          <el-input
            :model-value="cur.conclusion"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 6 }"
            :disabled="isReadonly"
            placeholder="对本供应商访谈结果作简要结论，并同步至 F2-71 汇总表……"
            @update:model-value="(v: string) => iv.updateEntity(cur!.id, { conclusion: v })"
          />
        </el-card>
      </main>

      <main v-else class="detail-panel empty">
        <p>请选择左侧访谈档案，或新建一份访谈记录。</p>
      </main>
    </div>

    <!-- 编制示例弹窗 -->
    <el-dialog
      v-model="exampleVisible"
      title="访谈记录与核对（示例） · 只读参照"
      width="920px"
      class="example-dialog"
    >
      <div class="example-dialog-body">
        <F2InterviewCheckExample compact />
      </div>
      <template #footer>
        <el-button type="primary" @click="exampleVisible = false">我知道了</el-button>
      </template>
    </el-dialog>

    <!-- 新建弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      title="弹窗录入 · 新建供应商访谈记录"
      width="560px"
      :close-on-click-modal="false"
    >
      <div class="dialog-body">
        <label class="field">
          <span>供应商名称</span>
          <el-select
            v-model="draft.supplierName"
            filterable
            allow-create
            default-first-option
            clearable
            placeholder="可从 F2-71/70/68 名单选择"
          >
            <el-option
              v-for="name in iv.linkage.value.knownSuppliers"
              :key="name"
              :label="name"
              :value="name"
            />
          </el-select>
        </label>
        <label class="field">
          <span>访谈对象</span>
          <el-input v-model="draft.interviewee" placeholder="姓名 / 职务" />
        </label>
        <label class="field">
          <span>访谈日期</span>
          <el-date-picker
            v-model="draft.interviewDate"
            type="date"
            value-format="YYYY-MM-DD"
            style="width: 100%"
          />
        </label>
        <label class="field">
          <span>访谈时间及地点</span>
          <el-input v-model="draft.interviewTimePlace" placeholder="时间 / 地点" />
        </label>
        <label class="field">
          <span>参与人员</span>
          <el-input v-model="draft.participants" placeholder="审计人员及其他参与人员" />
        </label>
      </div>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveDraft">创建并填写问卷</el-button>
      </template>
    </el-dialog>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span>审计说明</span>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="runAi('interview-detail-note')"
          >AI 填写审计说明</el-button>
        </div>
      </template>
      <el-input
        v-model="iv.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="汇总各份访谈记录执行情况、关键发现、证据留存及异常处理……"
      />
    </el-card>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span>审计结论</span>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="runAi('interview-detail-conclusion')"
          >AI 生成结论</el-button>
        </div>
      </template>
      <el-input
        :model-value="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="综合评价供应商访谈结果及交易真实性结论。"
        @update:model-value="saveConclusion"
      />
    </el-card>

    <details class="fraud-details">
      <summary>⚠️ 提示：第三方配合舞弊访谈关注点（问题解答第18号）</summary>
      <div class="fraud-body">
        <ol>
          <li>访谈不同层级人员交叉验证，关注回答是否一致。</li>
          <li>关注供应商关键人员是否为被审计单位前员工或存在特殊关系。</li>
          <li>询问供应商是否同时向被审计单位采购，形成闭环交易。</li>
          <li>结合函证观察回函过程可靠性；要求供应商对资料真实性盖章承诺。</li>
        </ol>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, toRef, type Ref } from 'vue'
import { useF2InterviewDetail } from '../../composables/useF2InterviewDetail'
import {
  F2_72_OBJECTIVE,
  F2_72_QUESTIONS,
} from '../../composables/useF2InterviewDetailFormulas'
import { useF2SpecialAiGenerate, type F2SpeAiSection } from '../../composables/useF2SpecialAiGenerate'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import ItemAttachment from '../../ItemAttachment.vue'
import F2InterviewCheckExample from './F2InterviewCheckExample.vue'

const props = defineProps<{
  wpId?: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const exampleVisible = ref(false)

const iv = useF2InterviewDetail({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const objective = F2_72_OBJECTIVE
const cur = computed(() => iv.current.value)

const questionMap = new Map(F2_72_QUESTIONS.map((q) => [q.key, q]))

function questionSection(key: string, index: number): string {
  return questionMap.get(key)?.section || `补充问题 ${index + 1}`
}

function isEditablePrompt(key: string): boolean {
  return !!questionMap.get(key)?.editablePrompt
}

function questionPlaceholder(key: string): string {
  return questionMap.get(key)?.placeholder || '填写访谈回答……'
}

function onSupplierChange(value: string): void {
  if (!cur.value) return
  iv.updateEntity(cur.value.id, { supplierName: value || '' })
}

const linkHints = computed(() => {
  if (!cur.value?.supplierName) return [] as string[]
  const hints: string[] = []
  const s71 = iv.linkage.value.summaryOf(cur.value.supplierName)
  const s70 = iv.linkage.value.profileOf(cur.value.supplierName)
  const amount = iv.linkage.value.purchaseAmountOf(cur.value.supplierName)
  if (s71) hints.push(`F2-71：${s71.method || '已建档'} ${s71.reason || ''}`.trim())
  if (s70) hints.push('F2-70：已有工商档案')
  if (amount !== null) hints.push(`F2-68 本年采购额：${amount.toLocaleString('zh-CN')}`)
  return hints
})

// ─── 新建弹窗 ────────────────────────────────────────────────────────────────
const dialogVisible = ref(false)
const draft = reactive({
  supplierName: '',
  interviewee: '',
  interviewDate: '',
  interviewTimePlace: '',
  participants: '',
})

function openCreateDialog(): void {
  if (props.isReadonly) return
  draft.supplierName = ''
  draft.interviewee = ''
  draft.interviewDate = ''
  draft.interviewTimePlace = ''
  draft.participants = ''
  dialogVisible.value = true
}

function saveDraft(): void {
  if (props.isReadonly) return
  const id = iv.addEntityFrom({
    supplierName: draft.supplierName,
    interviewee: draft.interviewee,
    interviewDate: draft.interviewDate,
    interviewTimePlace: draft.interviewTimePlace || draft.interviewDate,
    participants: draft.participants,
  })
  dialogVisible.value = false
  if (draft.supplierName) iv.applyLinkage(id)
}

// ─── 审计结论 ────────────────────────────────────────────────────────────────
const CONCLUSION_KEY = 'F2-72-audit-conclusion'
const auditConclusion = ref('')

function saveConclusion(value: string): void {
  if (props.isReadonly) return
  auditConclusion.value = value
  const item = { item_id: CONCLUSION_KEY, conclusion: null, remark: value }
  props.allResponses.set(CONCLUSION_KEY, item)
  window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items: [item] } }))
}

onMounted(() => {
  auditConclusion.value = props.allResponses.get(CONCLUSION_KEY)?.remark || ''
  const legacy = props.allResponses.get('F2-72-audit-note')?.remark
  if (!iv.auditNote.value && legacy) iv.auditNote.value = legacy
})

const wpIdRef = toRef(() => props.wpId || '') as Ref<string>
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2SpecialAiGenerate(wpIdRef)

function aiContext(): Record<string, unknown> {
  return {
    sheet: 'F2-72',
    summary: iv.summary.value,
    interviews: iv.enrichedEntities.value
      .filter((entity) => entity.supplierName.trim())
      .slice(0, 15)
      .map((entity) => ({
        supplierName: entity.supplierName,
        interviewee: entity.interviewee,
        interviewDate: entity.interviewDate,
        interviewTimePlace: entity.interviewTimePlace,
        participants: entity.participants,
        answeredCount: entity.answeredCount,
        completionPct: entity.completionPct,
        riskFlags: entity.riskFlags,
        declarationAck: entity.declarationAck,
        conclusion: entity.conclusion,
        answers: entity.qaItems
          .filter((item) => item.answer.trim())
          .map((item) => ({ section: questionSection(item.key, 0), answer: item.answer.slice(0, 200) })),
      })),
    auditNote: iv.auditNote.value,
  }
}

async function runAi(section: F2SpeAiSection): Promise<void> {
  const isNote = section === 'interview-detail-note'
  const content = await generateAndConfirm(
    section,
    isNote ? iv.auditNote.value : auditConclusion.value,
    aiContext(),
    isNote ? 'AI 生成 · 供应商访谈记录审计说明' : 'AI 生成 · 供应商访谈记录审计结论',
  )
  if (!content) return
  if (isNote) iv.auditNote.value = content
  else saveConclusion(content)
}
</script>

<style scoped>
.f2-interview-detail{padding:14px 18px;font-size:var(--wp-font-size, 13px);background:linear-gradient(180deg,#faf8fc 0,#fff 130px);--purple:#4b2d77}
.sheet-header,.stats,.tab-toolbar,.toolbar-left,.toolbar-right,.opinion-header,.card-head,.qa-head{display: flex;align-items:center}
.sheet-header,.tab-toolbar,.opinion-header,.card-head{justify-content:space-between}
.sheet-header{gap:12px;margin-bottom:12px}.sheet-header h3{margin:0;color:#35204f}.code{font-size:12px;color:#8c7b9d}
.stats,.toolbar-left,.toolbar-right,.card-actions{gap:8px;flex-wrap:wrap}
.guidance-details{margin-bottom:12px;border-left:3px solid var(--purple);background:#f7f2fa;border-radius:5px;padding:8px 12px}
.guidance-details summary{cursor:pointer;font-weight:600;color:var(--purple)}
.guidance-content{margin-top:8px;color:#606266;line-height:1.75}.guidance-content p{margin:4px 0}
.tab-toolbar{gap:10px;margin-bottom:12px}.search{width:220px}

.layout{display:flex;gap:14px;align-items:flex-start;min-height:480px}
.list-panel{width:260px;flex-shrink:0;display:flex;flex-direction:column;gap:8px;max-height:72vh;overflow-y:auto}
.list-card{text-align:left;border:1px solid #ded3e8;border-radius:6px;background:#fff;padding:10px 12px;cursor:pointer}
.list-card.active{border-color:var(--purple);background:#f7f2fa;box-shadow:0 0 0 1px var(--purple)}
.list-card.risk{border-color:#f3b2b2}
.list-card-head{display:flex;justify-content:space-between;margin-bottom:4px}
.seq{font-size:11px;color:#8c7b9d}.pct{font-size:12px}
.list-card strong{display:block;color:#35204f;margin-bottom:2px}
.list-meta{font-size:12px;color:#909399}.list-risk{margin-top:6px;display:flex;gap:4px;flex-wrap:wrap}
.add-list-card{border:1.5px dashed #b7a1cf;border-radius:6px;background:#fbf9fd;color:var(--purple);padding:14px;cursor:pointer}
.add-list-card:hover{background:#f4eef9}

.detail-panel{flex:1;min-width:0;display:flex;flex-direction:column;gap:10px}
.detail-panel.empty{align-items:center;justify-content:center;color:#909399;border:1px dashed #d7cae2;border-radius:6px;min-height:320px}
.meta-card,.qa-card,.attach-card,.sign-card,.conclusion-card{border-color:#ded3e8}
.meta-card :deep(.el-card__header),.qa-card :deep(.el-card__header),.attach-card :deep(.el-card__header),.sign-card :deep(.el-card__header),.conclusion-card :deep(.el-card__header){padding:10px 14px;background:#faf8fc;font-weight:600;color:var(--purple)}
.meta-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px 14px}
.field{display:flex;flex-direction:column;gap:4px;font-size:12px}.field.wide{grid-column:1 / -1}.field > span{color:#606266}
.hint-blue{margin:10px 0 0;color:#409eff;font-size:12px;line-height:1.6}
.link-hints{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
.prompt-text{margin:0 0 8px;color:#303133;line-height:1.7;font-weight:500}
.prompt-edit{margin-bottom:8px}
.attach-list{margin:0 0 10px;padding-left:20px;color:#606266;line-height:1.7}
.declaration{margin-top:12px;padding:10px 12px;background:#fff8f0;border:1px solid #f5dab1;border-radius:5px;line-height:1.6}
.formula{border-bottom:1px dotted #8d78a2;cursor:help;color:#4b2d77;font-weight:600}

.dialog-body{display:flex;flex-direction:column;gap:10px}
.example-dialog-body{max-height:68vh;overflow-y:auto;padding-right:6px}
.opinion-card{margin-top:16px;border-color:#ded3e8}
.opinion-card :deep(.el-card__header){padding:10px 14px;background:#faf8fc}
.opinion-header span{font-weight:700;color:var(--purple)}
.fraud-details{margin-top:14px;border:1px solid #fde2e2;border-left:3px solid #f56c6c;border-radius:5px;background:#fffafa}
.fraud-details summary{cursor:pointer;padding:9px 13px;color:#c45656;font-weight:600}
.fraud-body{padding:0 16px 12px;color:#606266;line-height:1.75}
.fraud-body ol{margin:4px 0 10px;padding-left:22px}
</style>
