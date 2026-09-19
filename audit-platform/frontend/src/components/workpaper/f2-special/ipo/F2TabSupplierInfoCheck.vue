<template>
  <div class="f2-supplier-info f2-ipo-soft">
    <header class="sheet-header">
      <div>
        <h3>供应商信息核查表</h3>
        <span class="code">F2-70 · 核查项目 × 供应商档案（卡片 / 矩阵 / 在线编辑三模式）</span>
      </div>
      <div class="stats">
        <el-tag size="small">已建档 {{ ic.summary.value.supplierCount }} 家</el-tag>
        <el-tag v-if="ic.summary.value.incompleteCount" size="small" type="warning">
          信息不全 {{ ic.summary.value.incompleteCount }} 家
        </el-tag>
        <el-tag v-if="ic.summary.value.riskCount" size="small" type="danger">
          风险 {{ ic.summary.value.riskCount }} 家
        </el-tag>
      </div>
    </header>

    <details class="guidance-details">
      <summary>📋 审计目标与核查过程</summary>
      <div class="guidance-content">
        <p><strong>一、审计目标：</strong>资产负债表中记录的存货真实存在，且已经记录的存货交易均已入账。</p>
        <p><strong>二、审计过程：</strong></p>
        <p>1. 查询供应商工商、银行、税务信息资料，关注地址、董监高、联系方式、网站及 IP、企业邮箱、成立时间、注册资本、经营范围等，并与发票信息、网站信息核对，识别疑似关联关系。</p>
        <p>2. 通过关联网络穿透股权结构，将供应商股东、关键管理人员、关键经办人员与被审计单位实际控制人、董监高及其密切家庭成员比对，并判断供应商经营范围与采购产品是否匹配。</p>
        <p><strong>三、录入方式：</strong>「卡片模式」浏览档案并通过弹窗逐家录入；「矩阵模式」按核查项目×供应商对照编辑；在线编辑请切换上方「在线编辑」页签。</p>
      </div>
    </details>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-radio-group v-model="viewMode" size="small">
          <el-radio-button value="card">卡片模式</el-radio-button>
          <el-radio-button value="matrix">矩阵模式</el-radio-button>
        </el-radio-group>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="openCreateDialog">
          + 新增供应商
        </el-button>
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-spe"
          sheet="F2-70"
          :disabled="isReadonly"
          review-section="F2-70-check"
        />
        <GtIndexChip value="wp:F2-70" />
      </div>
    </div>

    <!-- ═══ 卡片模式 ═══ -->
    <div v-if="viewMode === 'card'" class="card-grid">
      <el-card
        v-for="(entity, index) in ic.enrichedEntities.value"
        :key="entity.id"
        shadow="hover"
        class="supplier-card"
        :class="{ 'risk-card': entity.isRisk }"
      >
        <template #header>
          <div class="card-head">
            <div class="card-title">
              <span class="supplier-seq">供应商{{ index + 1 }}</span>
              <strong>{{ entity.supplierName || '未命名供应商' }}</strong>
            </div>
            <div class="card-actions">
              <el-button size="small" link type="primary" @click="openEditDialog(entity.id)">
                {{ isReadonly ? '查看' : '编辑' }}
              </el-button>
              <el-button
                v-if="!isReadonly"
                size="small"
                link
                type="danger"
                :disabled="ic.entities.value.length <= 1"
                @click="ic.removeEntity(entity.id)"
              >删除</el-button>
            </div>
          </div>
        </template>
        <div class="card-progress">
          <span class="progress-label">信息完整度 <span class="formula">{{ Math.round(entity.completionPct * 100) }}%</span></span>
          <el-progress
            :percentage="Math.round(entity.completionPct * 100)"
            :show-text="false"
            :stroke-width="6"
            :status="entity.completionPct === 1 ? 'success' : undefined"
          />
        </div>
        <dl class="card-fields">
          <div v-for="field in cardFields" :key="field.key" class="card-field">
            <dt>{{ field.label }}</dt>
            <dd>{{ entity[field.key] || '—' }}</dd>
          </div>
          <div class="card-field wide">
            <dt>股东及持股比例</dt>
            <dd>{{ shareholdersText(entity) || '—' }}</dd>
          </div>
          <div class="card-field wide">
            <dt>关键管理/经办人员</dt>
            <dd>{{ keyPeopleText(entity) || '—' }}</dd>
          </div>
        </dl>
        <div class="card-risk">
          <template v-if="entity.riskFlags.length">
            <el-tag v-for="flag in entity.riskFlags" :key="flag" type="danger" size="small" class="risk-tag">
              {{ flag }}
            </el-tag>
          </template>
          <span v-else class="ok-flag">未见异常</span>
        </div>
      </el-card>
      <button v-if="!isReadonly" type="button" class="add-card" @click="openCreateDialog">
        <span class="add-plus">＋</span>
        <span>弹窗录入新供应商</span>
      </button>
    </div>

    <!-- ═══ 矩阵模式 ═══ -->
    <div v-else class="table-scroll">
      <table class="info-matrix">
        <thead>
          <tr>
            <th class="sticky item-col">核查项目</th>
            <th
              v-for="(entity, index) in ic.enrichedEntities.value"
              :key="entity.id"
              class="supplier-head"
              :class="{ 'risk-head': entity.isRisk }"
            >
              <div class="supplier-head-inner">
                <span class="supplier-seq">供应商{{ index + 1 }}</span>
                <span class="head-ops">
                  <el-button link size="small" class="head-btn" @click="openEditDialog(entity.id)">✎</el-button>
                  <el-button
                    v-if="!isReadonly"
                    link
                    size="small"
                    class="head-btn"
                    :disabled="ic.entities.value.length <= 1"
                    @click="ic.removeEntity(entity.id)"
                  >✕</el-button>
                </span>
              </div>
              <el-input
                v-if="!isReadonly"
                :model-value="entity.supplierName"
                size="small"
                placeholder="供应商名称"
                @update:model-value="(value: string) => ic.updateEntity(entity.id, { supplierName: value })"
              />
              <strong v-else>{{ entity.supplierName || '未填写' }}</strong>
            </th>
          </tr>
        </thead>
        <tbody>
          <template v-for="section in sections" :key="section.title">
            <tr class="section-row">
              <td class="sticky item-col section-cell">{{ section.title }}</td>
              <td
                v-for="entity in ic.enrichedEntities.value"
                :key="entity.id"
                class="section-cell"
              ></td>
            </tr>
            <tr v-for="item in section.items" :key="item.key">
              <td class="sticky item-col">{{ item.label }}</td>
              <td
                v-for="entity in ic.enrichedEntities.value"
                :key="entity.id"
                :class="{ 'risk-cell': item.riskWhenYes && entity[item.key] === '是' }"
              >
                <el-select
                  v-if="item.yesNo && !isReadonly"
                  :model-value="entity[item.key] || undefined"
                  size="small"
                  clearable
                  placeholder="—"
                  @change="(value: string) => ic.updateEntity(entity.id, { [item.key]: (value || '') as any })"
                >
                  <el-option label="是" value="是" />
                  <el-option label="否" value="否" />
                </el-select>
                <el-input
                  v-else-if="!isReadonly"
                  :model-value="String(entity[item.key] ?? '')"
                  size="small"
                  :placeholder="item.placeholder || ''"
                  :type="item.textarea ? 'textarea' : 'text'"
                  :autosize="item.textarea ? { minRows: 1, maxRows: 3 } : undefined"
                  @update:model-value="(value: string) => ic.updateEntity(entity.id, { [item.key]: value as any })"
                />
                <span v-else>{{ entity[item.key] || '—' }}</span>
              </td>
            </tr>
          </template>
          <tr class="section-row">
            <td class="sticky item-col section-cell">六、系统核对结果（自动）</td>
            <td
              v-for="entity in ic.enrichedEntities.value"
              :key="entity.id"
              class="section-cell"
            ></td>
          </tr>
          <tr>
            <td class="sticky item-col">信息完整度</td>
            <td
              v-for="entity in ic.enrichedEntities.value"
              :key="entity.id"
              class="calc-cell"
            >
              <span class="formula">{{ Math.round(entity.completionPct * 100) }}%</span>
              <el-progress
                :percentage="Math.round(entity.completionPct * 100)"
                :show-text="false"
                :stroke-width="5"
                :status="entity.completionPct === 1 ? 'success' : undefined"
              />
            </td>
          </tr>
          <tr>
            <td class="sticky item-col">风险提示</td>
            <td
              v-for="entity in ic.enrichedEntities.value"
              :key="entity.id"
              class="calc-cell"
            >
              <template v-if="entity.riskFlags.length">
                <el-tag
                  v-for="flag in entity.riskFlags"
                  :key="flag"
                  type="danger"
                  size="small"
                  class="risk-tag"
                >{{ flag }}</el-tag>
              </template>
              <span v-else class="ok-flag">未见异常</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- ═══ 弹窗录入 ═══ -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="780px"
      class="supplier-dialog"
      :close-on-click-modal="false"
    >
      <div v-if="draft" class="dialog-body">
        <div class="dialog-name-row">
          <label class="dialog-field wide">
            <span class="field-label">供应商名称</span>
            <el-input v-model="draft.supplierName" :disabled="isReadonly" placeholder="供应商全称" />
          </label>
        </div>
        <template v-for="section in sections" :key="section.title">
          <h4 class="dialog-section-title">{{ section.title }}</h4>
          <div class="dialog-grid">
            <label
              v-for="item in section.items"
              :key="item.key"
              class="dialog-field"
              :class="{ wide: item.textarea }"
            >
              <span class="field-label">{{ item.label }}</span>
              <el-select
                v-if="item.yesNo"
                :model-value="draft[item.key] || undefined"
                clearable
                placeholder="—"
                :disabled="isReadonly"
                @change="(value: string) => { (draft as any)[item.key] = value || '' }"
              >
                <el-option label="是" value="是" />
                <el-option label="否" value="否" />
              </el-select>
              <el-input
                v-else
                :model-value="String(draft[item.key] ?? '')"
                :type="item.textarea ? 'textarea' : 'text'"
                :autosize="item.textarea ? { minRows: 2, maxRows: 4 } : undefined"
                :placeholder="item.placeholder || ''"
                :disabled="isReadonly"
                @update:model-value="(value: string) => { (draft as any)[item.key] = value }"
              />
            </label>
          </div>
        </template>
        <div class="dialog-preview">
          <span>信息完整度 <span class="formula">{{ Math.round(draftEnriched.completionPct * 100) }}%</span></span>
          <template v-if="draftEnriched.riskFlags.length">
            <el-tag v-for="flag in draftEnriched.riskFlags" :key="flag" type="danger" size="small" class="risk-tag">
              {{ flag }}
            </el-tag>
          </template>
          <span v-else class="ok-flag">未见异常</span>
        </div>
      </div>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button v-if="!isReadonly" type="primary" @click="saveDraft">保存供应商档案</el-button>
      </template>
    </el-dialog>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span>三、审计说明</span>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="runAi('supplier-info-note')"
          >AI 填写审计说明</el-button>
        </div>
      </template>
      <el-input
        v-model="ic.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 5, maxRows: 12 }"
        :disabled="isReadonly"
        placeholder="说明供应商信息取数来源、股权及关键人员穿透比对结果、与被审计单位人员/地址/网站/邮箱的重合情况、异常事项及处理……"
      />
    </el-card>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span>四、审计结论</span>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="runAi('supplier-info-conclusion')"
          >AI 生成结论</el-button>
        </div>
      </template>
      <el-input
        :model-value="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="综合评价供应商信息真实性、与被审计单位的关联关系及第三方配合舞弊风险。"
        @update:model-value="saveConclusion"
      />
    </el-card>

    <details class="fraud-details">
      <summary>⚠️ 提示：第三方配合舞弊特征（问题解答第18号）</summary>
      <div class="fraud-body">
        <p><strong>典型特征（存在下列情形应重点关注）：</strong></p>
        <ol>
          <li>经营时间较短，或成立时间与合作起始时间接近。</li>
          <li>缴纳社保人数较少，或为个人、个体工商户。</li>
          <li>注册资本与交易规模不匹配；交易规模与第三方自身经营状况不匹配。</li>
          <li>经常变更名称、地址或频繁改变与被审计单位的交易模式。</li>
          <li>工商信息与被审计单位相似或重合（股东名称、董监高、注册地址、联系人、联系方式等）。</li>
          <li>不同第三方（如客户和供应商）的登记信息相互重合。</li>
          <li>既是客户又是供应商，且交易毛利异常或一方受同一实际控制人控制。</li>
          <li>对被审计单位存在大额依赖，或被审计单位是其主要客户/供应商。</li>
          <li>回函笔迹、格式、印章与其他函证雷同，或回函信息与账面高度一致且过于规整。</li>
          <li>在审计期间新增、注销或停止交易；合并报表范围频繁变化前后交易异常。</li>
          <li>以个人账户、现金或票据背书等异常方式收付款。</li>
          <li>股东、关键管理人员或经办人员与被审计单位股东、员工（含离职员工）、董监高及其亲属存在重合。</li>
          <li>存在预付款项长期挂账、大额资金拆借或往来性质异常。</li>
        </ol>
        <p><strong>应对措施：</strong></p>
        <ol>
          <li>对不符合商业惯例的第三方交易，评价交易的商业理由及合理性。</li>
          <li>核对交易价格、结算方式与同类交易是否一致，关注是否存在利益输送。</li>
          <li>核查资金流向，识别是否存在资金回流（预付采购款经由第三方回流形成销售回款）。</li>
          <li>结合物流、验收、出入库单据核对交易真实性，关注单据签字与印章是否前后一致。</li>
          <li>对存疑第三方实施实地走访、访谈及扩大函证，必要时向注册会计师认为必要的机构直接取证。</li>
          <li>对询证函全程保持控制，关注回函地址、笔迹、格式雷同及快递单号异常等迹象。</li>
          <li>金额重大且无法消除疑虑时，考虑对审计意见的影响并与治理层沟通。</li>
        </ol>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, toRef, type Ref } from 'vue'
import { useF2SupplierInfoCheck } from '../../composables/useF2SupplierInfoCheck'
import {
  emptySupplierInfoEntity,
  enrichSupplierInfoEntity,
  type SupplierInfoEntity,
  type SupplierInfoField,
} from '../../composables/useF2SupplierInfoCheckFormulas'
import { useF2SpecialAiGenerate, type F2SpeAiSection } from '../../composables/useF2SpecialAiGenerate'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId?: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const ic = useF2SupplierInfoCheck({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const viewMode = ref<'card' | 'matrix'>('card')

interface CheckItem {
  key: SupplierInfoField
  label: string
  yesNo?: boolean
  textarea?: boolean
  riskWhenYes?: boolean
  placeholder?: string
}

const sections: Array<{ title: string; items: CheckItem[] }> = [
  {
    title: '一、工商与网络信息',
    items: [
      { key: 'creditCode', label: '统一社会信用代码' },
      { key: 'registeredAddress', label: '注册地址', placeholder: '关注与被审计单位是否重合' },
      { key: 'officeAddress', label: '办公地址' },
      { key: 'websiteUrl', label: '网站地址' },
      { key: 'websiteIp', label: '网站IP地址', placeholder: '关注与被审计单位IP是否一致' },
      { key: 'companyEmail', label: '企业邮箱' },
      { key: 'establishDate', label: '成立时间', placeholder: '关注是否临近合作起始' },
      { key: 'registeredCapital', label: '注册资本/实缴资本', placeholder: '关注与交易规模是否匹配' },
      { key: 'businessScope', label: '经营范围', textarea: true, placeholder: '关注与采购产品是否匹配' },
      { key: 'staffScale', label: '人员规模/缴纳社保人数' },
      { key: 'legalRepresentative', label: '法定代表人' },
    ],
  },
  {
    title: '二、股东及持股比例',
    items: [
      { key: 'shareholder1', label: '股东1及持股比例', placeholder: '示例：张三 60%' },
      { key: 'shareholder2', label: '股东2及持股比例' },
      { key: 'shareholder3', label: '股东3及持股比例' },
      { key: 'shareholder4', label: '股东4及持股比例' },
      { key: 'shareholder5', label: '股东5及持股比例' },
    ],
  },
  {
    title: '三、关键管理人员',
    items: [
      { key: 'chairman', label: '董事长' },
      { key: 'generalManager', label: '总经理' },
      { key: 'otherManagers', label: '其他关键管理人员', textarea: true },
    ],
  },
  {
    title: '四、关键经办人员',
    items: [
      { key: 'keyHandlers', label: '业务/合同/收款经办人', textarea: true },
    ],
  },
  {
    title: '五、穿透核查',
    items: [
      { key: 'actualController', label: '实际控制人' },
      { key: 'isRelatedParty', label: '是否为关联方', yesNo: true, riskWhenYes: true },
      { key: 'isAlsoCustomer', label: '是否同时为客户（含同一实际控制人）', yesNo: true, riskWhenYes: true },
      { key: 'businessStatus', label: '经营状态', placeholder: '存续/在业/注销/吊销等' },
      { key: 'isDishonest', label: '是否列入失信名单', yesNo: true, riskWhenYes: true },
      { key: 'infoSource', label: '信息来源', placeholder: '企查查/公示系统/征信报告等' },
      { key: 'remark', label: '备注/异常说明', textarea: true },
    ],
  },
]

const cardFields: Array<{ key: SupplierInfoField; label: string }> = [
  { key: 'creditCode', label: '信用代码' },
  { key: 'establishDate', label: '成立时间' },
  { key: 'registeredCapital', label: '注册资本' },
  { key: 'staffScale', label: '人员规模' },
  { key: 'legalRepresentative', label: '法定代表人' },
  { key: 'actualController', label: '实际控制人' },
  { key: 'businessStatus', label: '经营状态' },
  { key: 'infoSource', label: '信息来源' },
]

function shareholdersText(entity: SupplierInfoEntity): string {
  return [
    entity.shareholder1, entity.shareholder2, entity.shareholder3,
    entity.shareholder4, entity.shareholder5,
  ].filter((value) => value.trim()).join('；')
}

function keyPeopleText(entity: SupplierInfoEntity): string {
  return [
    entity.chairman && `董事长 ${entity.chairman}`,
    entity.generalManager && `总经理 ${entity.generalManager}`,
    entity.otherManagers,
    entity.keyHandlers && `经办 ${entity.keyHandlers}`,
  ].filter(Boolean).join('；')
}

// ─── 弹窗录入 ────────────────────────────────────────────────────────────────
const dialogVisible = ref(false)
const draft = ref<SupplierInfoEntity | null>(null)
const isNewDraft = ref(false)

const dialogTitle = computed(() => {
  if (props.isReadonly) return '供应商档案 · 查看'
  return isNewDraft.value ? '弹窗录入 · 新增供应商档案' : `编辑供应商档案：${draft.value?.supplierName || '未命名'}`
})

const draftEnriched = computed(() =>
  enrichSupplierInfoEntity(draft.value ?? emptySupplierInfoEntity()),
)

function openCreateDialog(): void {
  if (props.isReadonly) return
  draft.value = emptySupplierInfoEntity()
  isNewDraft.value = true
  dialogVisible.value = true
}

function openEditDialog(id: string): void {
  const entity = ic.entities.value.find((item) => item.id === id)
  if (!entity) return
  draft.value = JSON.parse(JSON.stringify(entity)) as SupplierInfoEntity
  isNewDraft.value = false
  dialogVisible.value = true
}

function saveDraft(): void {
  if (!draft.value || props.isReadonly) return
  const { id, ...patch } = draft.value
  if (ic.entities.value.some((entity) => entity.id === id)) {
    ic.updateEntity(id, patch)
  } else {
    ic.addEntityFrom(draft.value)
  }
  dialogVisible.value = false
}

// ─── 审计结论（沿用 f2-spe:save-items 持久化）───────────────────────────────
const CONCLUSION_KEY = 'F2-70-audit-conclusion'
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
  const legacy = props.allResponses.get('F2-70-audit-note')?.remark
  if (!ic.auditNote.value && legacy) ic.auditNote.value = legacy
})

// ─── AI 说明/结论 ────────────────────────────────────────────────────────────
const wpIdRef = toRef(() => props.wpId || '') as Ref<string>
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2SpecialAiGenerate(wpIdRef)

function aiContext(): Record<string, unknown> {
  return {
    sheet: 'F2-70',
    summary: ic.summary.value,
    suppliers: ic.enrichedEntities.value
      .filter((entity) => entity.supplierName.trim())
      .slice(0, 20)
      .map((entity) => ({
        supplierName: entity.supplierName,
        creditCode: entity.creditCode,
        establishDate: entity.establishDate,
        registeredCapital: entity.registeredCapital,
        staffScale: entity.staffScale,
        legalRepresentative: entity.legalRepresentative,
        shareholders: shareholdersText(entity),
        keyPeople: keyPeopleText(entity),
        actualController: entity.actualController,
        isRelatedParty: entity.isRelatedParty,
        isAlsoCustomer: entity.isAlsoCustomer,
        businessStatus: entity.businessStatus,
        isDishonest: entity.isDishonest,
        infoSource: entity.infoSource,
        completionPct: entity.completionPct,
        riskFlags: entity.riskFlags,
        remark: entity.remark,
      })),
    auditNote: ic.auditNote.value,
  }
}

async function runAi(section: F2SpeAiSection): Promise<void> {
  const isNote = section === 'supplier-info-note'
  const content = await generateAndConfirm(
    section,
    isNote ? ic.auditNote.value : auditConclusion.value,
    aiContext(),
    isNote ? 'AI 生成 · 供应商信息核查审计说明' : 'AI 生成 · 供应商信息核查审计结论',
  )
  if (!content) return
  if (isNote) ic.auditNote.value = content
  else saveConclusion(content)
}
</script>

<style scoped>
.f2-supplier-info{padding:14px 18px;font-size:var(--wp-font-size, 13px);background:linear-gradient(180deg,#faf8fc 0,#fff 130px);--purple:#4b2d77}
.sheet-header,.stats,.tab-toolbar,.toolbar-left,.toolbar-right,.opinion-header{display: flex;align-items:center}.sheet-header,.tab-toolbar,.opinion-header{justify-content:space-between}.sheet-header{gap:12px;margin-bottom:12px}.sheet-header h3{margin:0;color:#35204f}.code{font-size:12px;color:#8c7b9d}.stats,.toolbar-left,.toolbar-right{gap:8px;flex-wrap:wrap}
.guidance-details{margin-bottom:12px;border-left:3px solid var(--purple);background:#f7f2fa;border-radius:5px;padding:8px 12px}.guidance-details summary{cursor:pointer;font-weight:600;color:var(--purple)}.guidance-content{margin-top:8px;color:#606266;line-height:1.75}.guidance-content p{margin:4px 0}.tab-toolbar{gap:10px;margin-bottom:12px}

/* 卡片模式 */
.card-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(390px,1fr));gap:12px}
.supplier-card{border-color:#ded3e8}.supplier-card :deep(.el-card__header){padding:9px 14px;background:#faf8fc}
.risk-card{border-color:#f3b2b2}.risk-card :deep(.el-card__header){background:#fdf3f3}
.card-head{display:flex;align-items:center;justify-content:space-between;gap:8px}
.card-title{display:flex;align-items:center;gap:8px;min-width:0}.card-title strong{color:#35204f;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.card-actions{display:flex;align-items:center;flex-shrink:0}
.supplier-seq{font-size:11px;color:#8c7b9d;background:#f0e9f6;border-radius:3px;padding:1px 6px;white-space:nowrap}
.card-progress{display:flex;flex-direction:column;gap:4px;margin-bottom:8px}.progress-label{font-size:12px;color:#606266}
.card-fields{display:grid;grid-template-columns:1fr 1fr;gap:4px 14px;margin:0}
.card-field{display:flex;gap:6px;min-width:0}.card-field.wide{grid-column:1 / -1}
.card-field dt{color:#8c7b9d;flex-shrink:0}.card-field dd{margin:0;color:#303133;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.card-field.wide dd{white-space:normal}
.card-risk{margin-top:8px;padding-top:8px;border-top:1px dashed #e4d9ee}
.add-card{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;min-height:170px;border:1.5px dashed #b7a1cf;border-radius:6px;background:#fbf9fd;color:var(--purple);cursor:pointer;font-size:13px}
.add-card:hover{background:#f4eef9;border-color:var(--purple)}.add-plus{font-size:26px;line-height:1}

/* 矩阵模式 */
.table-scroll{max-width:100%;overflow-x: auto;border:1px solid #d7cae2;border-radius:7px}
.info-matrix{width:100%;min-width:900px;border-collapse:separate;border-spacing:0;font-size:11px}
.info-matrix th,.info-matrix td{border-right:1px solid #d8cce3;border-bottom:1px solid #d8cce3;padding:4px 6px;vertical-align:middle;background:#fff;text-align:center;min-width:200px}
.info-matrix thead th{position:sticky;top:0;z-index:3;background:var(--purple);color:#fff;font-weight:600}
.info-matrix .sticky{position:sticky;left:0;z-index:4}.info-matrix th.sticky{z-index:5}
.item-col{width:185px;min-width:185px !important;background:#f5f0f8 !important;color:#4b2d77;font-weight:600;text-align:left !important}
.info-matrix thead th.item-col{color:#4b2d77}
.supplier-head-inner{display:flex;align-items:center;justify-content:space-between;margin-bottom:4px}
.head-ops{display:inline-flex;gap:0}.head-btn{color:#e8dff2 !important}
.info-matrix .supplier-seq{color:#e8dff2;background:transparent;padding:0}
.risk-head{background:#7a3b52 !important}
.section-row .section-cell{background:#e8dff0 !important;color:#3f2465;font-weight:700;text-align:left !important;padding:5px 8px}
.risk-cell{background:#fef0f0 !important}
.calc-cell{background:#f2ecf7 !important}
.formula{border-bottom:1px dotted #8d78a2;cursor:help;color:#4b2d77;font-weight:600}
.risk-tag{margin:1px 2px}.ok-flag{color:#67a23a}

/* 弹窗录入 */
.dialog-body{max-height:64vh;overflow-y:auto;padding-right:6px}
.dialog-name-row{margin-bottom:6px}
.dialog-section-title{margin:12px 0 8px;padding:5px 10px;background:#f0e9f6;border-left:3px solid var(--purple);border-radius:3px;color:#3f2465;font-size:13px}
.dialog-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px 14px}
.dialog-field{display:flex;flex-direction:column;gap:4px;font-size:12px}.dialog-field.wide{grid-column:1 / -1}
.field-label{color:#606266}
.dialog-preview{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:14px;padding:8px 12px;background:#f7f2fa;border-radius:5px;color:#606266}

.opinion-card{margin-top:16px;border-color:#ded3e8}.opinion-card :deep(.el-card__header){padding:10px 14px;background:#faf8fc}.opinion-header span{font-weight:700;color:var(--purple)}
.fraud-details{margin-top:14px;border:1px solid #fde2e2;border-left:3px solid #f56c6c;border-radius:5px;background:#fffafa}.fraud-details summary{cursor:pointer;padding:9px 13px;color:#c45656;font-weight:600}.fraud-body{padding:0 16px 12px;color:#606266;line-height:1.75}.fraud-body ol{margin:4px 0 10px;padding-left:22px}.fraud-body p{margin:6px 0}
</style>
