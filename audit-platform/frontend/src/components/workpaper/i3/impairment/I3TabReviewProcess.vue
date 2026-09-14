<!--
  I3TabReviewProcess.vue — I3-8 复核公司减值测试过程及结论

  对齐致同 Excel「复核公司减值测试过程及结论I3-8」审计程序结构：
  一、过程复核（1~11，含使用价值/收益法/市场法/FVLCD/资产组分摊/管理层工作）
  二、结果或结论评价
  改进：补回缺号「4」、结论+证据栏、若适用开关、右侧指引折叠、进度汇总

  Spec: .kiro/specs/i3-goodwill/ Task 4.9
  Requirements: 7.1~7.4
-->
<template>
  <div class="i3-review-process">
    <!-- 引导：对齐模板编制逻辑 -->
    <div class="guide-banner">
      <div class="guide-title">复核公司减值测试过程（I3-8 程序逻辑）</div>
      <div class="guide-steps">
        <div class="guide-step" v-for="(step, idx) in guideSteps" :key="idx">
          <span class="step-number">{{ idx + 1 }}</span>
          <span class="step-text">{{ step }}</span>
        </div>
      </div>
    </div>

    <div class="methodology-block">
      <p>
        <strong>适用前提：</strong>本表适用于管理层与注册会计师均未利用专家工作的情形。
        若管理层利用专家 → 由 S13-3-1 / S13-3-2 替代；若项目组利用专家 → 由 S12-3-1 / S12-3-2 替代。
        编制逻辑：迹象判断 → 资产组/分摊 → 方法模型 → 可收回路径 → 参数复核 → 减值分配与管理层工作 → 结果结论。
        参照 CAS8 第十七~二十条及《会计提示第73号—商誉减值测试》。
      </p>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：在未利用专家时，系统复核被审计单位商誉减值测试过程（迹象、资产组、方法、使用价值/公允价值参数、可收回金额选择、分摊与两步法）并评价测试结果或结论是否恰当（CAS8 / 会计提示第73号）。"
    />

    <el-alert
      type="warning"
      :closable="false"
      show-icon
      class="expert-alert"
      title="专家替代提示：管理层利用专家 → S13-3-1/S13-3-2；项目组利用专家 → S12-3-1/S12-3-2。本表不与专家工作复核底稿并行重复编制。"
    />

    <el-alert
      v-for="(w, idx) in crossSheetWarnings"
      :key="'x-' + idx"
      type="warning"
      :closable="false"
      show-icon
      class="expert-alert"
      :title="w"
    />

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <ul>
          <li>按「1~11 过程复核 → 二、结果结论」顺序填写；第 6、7 项仅在采用收益法/市场法确定公允价值时适用，可标「不适用」。</li>
          <li>第 3 项重点防错：勿将「原标的公司股东权益」当作商誉减值测试对象，测试范围是分摊商誉的资产组/组合。</li>
          <li>使用价值现金流与资产组账面价值口径须一致（尤其营运资金是否双向包含）。</li>
          <li>可收回金额取使用价值与公允价值减处置费用后净额孰高；无法可靠估计公允净额时，以预计未来现金流量现值作为可收回金额。</li>
          <li>与 I3-5（迹象/分摊）、I3-6（减值测算）、I3-7（可收回金额）交叉索引，结论栏填「合理/不合理/需调整/待确认/不适用」。</li>
        </ul>
      </div>
    </details>

    <div class="section-header">
      <span class="section-title">I3-8 复核公司减值测试过程及结论</span>
      <div class="section-actions">
        <el-tag size="small" :type="overallProgressType">
          进度 {{ completedCount }}/{{ totalItems }}
        </el-tag>
        <el-button size="small" type="primary" text @click="handleReview">
          💬复核
        </el-button>
      </div>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" text type="primary" @click="emit('navigate-sheet', '针对性检查表I3-5')">→ I3-5</el-button>
        <el-button size="small" text type="primary" @click="emit('navigate-sheet', '商誉减值测试I3-6')">→ I3-6</el-button>
        <el-button size="small" text type="primary" @click="emit('navigate-sheet', '可收回金额测试I3-7')">→ I3-7</el-button>
      </div>
      <div class="toolbar-right">
        <GtIndexChip value="wp:I3-8" :context-project-id="projectId" />
      </div>
    </div>

    <div class="review-scroll-area">
      <el-collapse v-model="activeNames">
        <el-collapse-item
          v-for="section in sectionDefs"
          :key="section.key"
          :name="section.key"
        >
          <template #title>
            <div class="collapse-title">
              <span>
                {{ section.title }}
                <el-tag
                  v-if="section.optional"
                  size="small"
                  type="info"
                  effect="plain"
                  style="margin-left:8px"
                >若适用</el-tag>
              </span>
              <div class="collapse-title-right">
                <el-switch
                  v-if="section.optional"
                  v-model="sectionApplicable[section.key]"
                  :disabled="isReadonly"
                  size="small"
                  inline-prompt
                  active-text="适用"
                  inactive-text="不适用"
                  @change="markDirty"
                  @click.stop
                />
                <el-progress
                  :percentage="sectionProgress[section.key] || 0"
                  :stroke-width="6"
                  :show-text="false"
                  style="width:80px;margin-right:8px"
                />
                <el-tag size="small" :type="sectionTagType(section.key)">
                  {{ sectionCompletedCount(section.key) }}/{{ visibleItemCount(section.key) }}
                </el-tag>
              </div>
            </div>
          </template>

          <div
            v-if="section.optional && !sectionApplicable[section.key]"
            class="na-hint"
          >
            已标为不适用。若公司未采用本方法确定公允价值，可跳过本段；如后续改用该方法，请切换为「适用」后补填。
          </div>

          <div v-else class="check-items-container">
            <p v-if="section.intro" class="section-intro">{{ section.intro }}</p>
            <div
              class="check-item"
              v-for="item in checkItems[section.key]"
              :key="item.id"
            >
              <div class="check-item-header">
                <span class="check-item-number">{{ item.no }}</span>
                <span class="check-item-title">{{ item.title }}</span>
              </div>
              <div v-if="item.guidance" class="check-guidance">
                <details>
                  <summary>编制指引</summary>
                  <pre class="guidance-pre">{{ item.guidance }}</pre>
                </details>
              </div>
              <el-input
                v-model="item.content"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 8 }"
                :disabled="isReadonly"
                :placeholder="item.placeholder"
                @blur="markDirty"
              />
              <div class="check-item-footer">
                <el-select
                  v-model="item.conclusion"
                  size="small"
                  :disabled="isReadonly"
                  placeholder="结论"
                  style="width:140px"
                  @change="markDirty"
                >
                  <el-option label="合理" value="合理" />
                  <el-option label="不合理" value="不合理" />
                  <el-option label="需调整" value="需调整" />
                  <el-option label="待确认" value="待确认" />
                  <el-option label="不适用" value="不适用" />
                </el-select>
                <el-input
                  v-model="item.evidence"
                  size="small"
                  :disabled="isReadonly"
                  placeholder="审计证据 / 底稿索引（如 I3-5、I3-6、I3-7）"
                  style="flex:1;margin-left:8px"
                  @blur="markDirty"
                />
              </div>
            </div>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>

    <!-- 二、评价结果或结论 -->
    <el-card class="summary-card" shadow="never">
      <template #header>
        <div class="summary-header">
          <span class="summary-title">二、评价公司商誉减值测试的结果或结论</span>
          <el-tag :type="hasMajorDeviation ? 'danger' : 'success'" size="small">
            {{ hasMajorDeviation ? '存在重大偏差' : '未发现重大偏差' }}
          </el-tag>
        </div>
      </template>
      <div class="summary-body">
        <div class="summary-row">
          <span class="summary-label">总评价：</span>
          <el-select
            v-model="overallAssessment"
            :disabled="isReadonly"
            size="small"
            placeholder="选择总评价"
            style="width:280px"
            @change="markDirty"
          >
            <el-option label="公司减值测试过程及结论合理" value="合理" />
            <el-option label="公司减值测试过程基本合理，存在瑕疵" value="基本合理" />
            <el-option label="公司减值测试过程存在重大缺陷" value="存在重大缺陷" />
            <el-option label="无法评价（资料不足）" value="无法评价" />
          </el-select>
        </div>
        <div class="summary-row">
          <span class="summary-label">是否存在重大偏差：</span>
          <el-radio-group v-model="hasMajorDeviation" :disabled="isReadonly" @change="markDirty">
            <el-radio :value="false">否</el-radio>
            <el-radio :value="true">是</el-radio>
          </el-radio-group>
        </div>
        <div class="summary-row" v-if="hasMajorDeviation">
          <span class="summary-label">偏差说明：</span>
          <el-input
            v-model="deviationDescription"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
            :disabled="isReadonly"
            placeholder="描述重大偏差的具体内容、影响金额、建议调整及与 I3-6/I3-7 差异"
            style="flex:1"
            @blur="markDirty"
          />
        </div>
        <div class="summary-row">
          <span class="summary-label">结果或结论评价：</span>
          <el-input
            v-model="overallConclusionText"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 8 }"
            :disabled="isReadonly"
            placeholder="综合一、1~11 复核结果：&#10;1. 公司减值测试过程是否恰当&#10;2. 减值金额/是否减值结论是否可接受&#10;3. 审计师独立复核是否与管理层结论一致&#10;4. 后续跟进事项（若有）"
            style="flex:1"
            @blur="markDirty"
          />
        </div>
      </div>
    </el-card>

    <el-card class="audit-note-card" shadow="never">
      <template #header><span style="font-weight:600">审计说明</span></template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="记录复核范围、获取资料（减值测试模型/预算/评估报告）、执行程序、与 I3-5/I3-6/I3-7 勾稽情况等…"
        @blur="markDirty"
      />
    </el-card>

    <el-card class="audit-note-card" shadow="never">
      <template #header><span style="font-weight:600">审计结论</span></template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="如：公司减值测试过程及结论合理，独立复核未发现重大偏差；或：存在需调整事项，详见偏差说明…"
        @blur="markDirty"
      />
    </el-card>

    <div class="table-actions" v-if="!isReadonly">
      <el-button type="success" size="small" @click="handleSave" :loading="saving">
        保存
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, inject } from 'vue'
import { ElMessage } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import { useI3CrossSheet } from '../../composables/useI3CrossSheet'
import { toRef } from 'vue'

/**
 * I3-8 复核公司减值测试过程及结论
 * 对齐致同 Excel 程序结构（补回缺号 4），非原 153 行微粒化检查清单。
 */

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const STORAGE_KEY = 'I3-8-review-process'

const injectedCross = inject<ReturnType<typeof useI3CrossSheet> | null>('i3CrossSheet', null)
const localCross = injectedCross || useI3CrossSheet(toRef(props, 'allResponses') as any)

/** I3-8 ↔ I3-6/I3-7 硬勾稽提示 */
const crossSheetWarnings = computed(() => {
  const list: string[] = []
  const byCgu = localCross.impairmentResult.value.byCgu
  const i36Count = Object.keys(byCgu).length
  const rec = localCross.recoverableDetailByCgu.value
  const i37Count = Object.keys(rec).length

  if (i36Count === 0) {
    list.push('尚未编制 I3-6 减值测试：本表过程复核缺少测算对象，请先完成 I3-6。')
  }
  if (i36Count > 0 && i37Count === 0) {
    list.push('I3-6 已有 CGU，但 I3-7 无可收回金额明细：请确认使用价值/公允净额是否已测并回写。')
  }
  for (const [cgu, d] of Object.entries(rec)) {
    const i6 = byCgu[cgu]
    if (!i6) {
      list.push(`I3-7 资产组「${cgu}」在 I3-6 无对应行，名称须一致。`)
      continue
    }
    if (d.recoverableAmount > 0 && i6.recoverableAmount > 0
      && Math.abs(d.recoverableAmount - i6.recoverableAmount) > 0.01) {
      list.push(
        `「${cgu}」可收回金额 I3-7=${d.recoverableAmount.toLocaleString('zh-CN')} ≠ I3-6=${i6.recoverableAmount.toLocaleString('zh-CN')}，请回写或核对。`,
      )
    }
  }
  const totalImp = localCross.impairmentResult.value.totalImpairment
  if (totalImp > 0.01) {
    list.push(`I3-6 合并确认商誉减值合计 ${totalImp.toLocaleString('zh-CN')}：请在结论中评价是否与公司结论一致，并索引 I3-6。`)
  }
  return list
})
const SCHEMA_VERSION = 2

const guideSteps = [
  '迹象与资产组（1~2）— 是否测、测哪里',
  '方法与可收回路径（3~4）— 测什么、怎么取数',
  '使用价值参数（5）— 现金流/折现/终值/敏感度',
  '公允价值路径（6~8，若适用）— 收益法/市场法/FVLCD',
  '分摊、管理层工作与结论（9~11 + 二）',
]

interface CheckItem {
  id: string
  no: string
  title: string
  placeholder: string
  guidance: string
  content: string
  conclusion: string
  evidence: string
}

interface SectionDef {
  key: string
  title: string
  optional?: boolean
  intro?: string
}

const sectionDefs: SectionDef[] = [
  { key: 's1', title: '1、商誉减值迹象判断' },
  { key: 's2', title: '2、资产组划分与商誉分摊（概要）' },
  { key: 's3', title: '3、减值测试方法与模型' },
  {
    key: 's4',
    title: '4、可收回金额确定路径',
    intro: '（补回原模板缺号）评价公司如何在使用价值与公允价值减处置费用后净额之间确定可收回金额。',
  },
  { key: 's5', title: '5、使用价值（预计未来现金流量现值）参数' },
  {
    key: 's6',
    title: '6、收益法确定公允价值的参数',
    optional: true,
    intro: '仅当以收益法估计公允价值（进而确定公允净额）时填写。',
  },
  {
    key: 's7',
    title: '7、市场法确定公允价值的参数',
    optional: true,
    intro: '仅当以市场法（价值乘数等）估计公允价值时填写。',
  },
  { key: 's8', title: '8、公允价值减去处置费用后的净额' },
  { key: 's9', title: '9、最终选择可收回金额计算方法的理由' },
  { key: 's10', title: '10、资产组确定及商誉分摊（详细）' },
  { key: 's11', title: '11、评价管理层的工作' },
]

type SectionKey = typeof sectionDefs[number]['key']

function item(
  id: string,
  no: string,
  title: string,
  placeholder: string,
  guidance = '',
): CheckItem {
  return { id, no, title, placeholder, guidance, content: '', conclusion: '', evidence: '' }
}

const GUIDANCE = {
  assetGroupValue:
    '资产组价值=企业自由现金流评估值（经营性资产价值）－期初营运资金\n' +
    '其中，企业自由现金流评估值（经营性资产价值）＝EBIT +折旧及摊销－营运资本增加额－资本性支出\n' +
    'EBIT=营业收入－营业成本－税金及附加－销售费用－管理费用\n' +
    '（可将营运资金纳入现金流预测模型不予扣除，则对比用的含商誉资产组账面价值中也应包含营运资金）',
  workingCapital:
    '若在确定可收回金额的未来现金流量时考虑了期初营运资金的影响，则资产组的账面价值中也应包括营运资金，即资产组也不得扣除与经营相关的流动资产和流动负债。',
  capex: '资本性支出=资产更新投资+新增长期资产投资（新增固定资产或其他长期资产）',
  forecastPeriod:
    '在确定未来现金净流量的预测期时，应建立在经管理层批准的最近财务预算或预测数据基础上，原则上最多涵盖5年。',
  discountRate:
    '对折现率预测时，是否与相应的宏观、行业、地域、特定市场、特定市场主体的风险因素相匹配，是否与未来现金净流量均一致采用税前口径。',
  terminalValue:
    '假设使用后续现金流量永续增长模型，根据销售增长率估计现金流量增长率。绝大多数可以持续生存的企业，其销售增长率可以按宏观经济增长率估计。',
  incomeFv:
    '对未来现金净流量预测时，应以资产的当前状况为基础，以税前口径为预测依据，并充分关注关键参数（销量、价格、成本、费用、预测期/稳定期增长率）是否有可靠数据来源，是否与历史、计划、行业及宏观相符；重大假设与内外部信息不符时是否有合理理由。',
  marketBestInfo:
    '在不存在销售协议和资产活跃市场的情况下，应当以可获取的最佳信息为基础，估计资产的公允价值减去处置费用后的净额，可参考同行业类似资产的最近交易价格或结果。',
  fvHierarchy:
    '公允价值减处置费用后的净额：有销售协议的，按协议价减处置费用；无协议但有活跃市场的，按市价（通常买方出价）减处置费用；均无则按最佳信息估计。仍无法可靠估计的，以预计未来现金流量现值作为可收回金额。',
  fairValueDef:
    '资产组的公允价值是指市场参与者在计量日发生的有序交易中，出售一项资产所能收到或者转移一项负债所需支付的价格。',
  disposalCost:
    '处置费用是指可以直接归属于资产组处置的增量费用，包括与资产组处置有关的法律费用、相关税费、搬运费以及为使资产组达到可销售状态所发生的直接费用等。',
  cguLevel:
    '分摊商誉的资产组应当代表企业基于内部管理目的对商誉进行监控的最低水平，并且不应大于按《企业会计准则第35号——分部报告》所确定的报告分部。',
  allocationMethod:
    '公司应在充分考虑能够受益于企业合并的协同效应的资产组或资产组组合基础上，将商誉账面价值按各资产组或资产组组合的公允价值所占比例进行分摊。详见《会计提示第73号》附录2。',
  basisConsistency:
    '资产组或资产组组合的可收回金额与其账面价值的确定基础应保持一致，即二者应包括相同的资产和负债，且应按与资产组内资产和负债一致的基础预测未来现金流量。',
  nciGoodwill:
    '将商誉分摊至相关资产组时，应关注归属于少数股东的商誉：先将归属于母公司股东的商誉账面价值调整为全部商誉账面价值，再合理分摊至相关资产组或资产组组合。',
  realloc:
    '因重组等原因经营组成部分变化、影响已分摊商誉所在资产组构成的，应将商誉账面价值重新分摊至受影响的资产组或资产组组合，并充分披露理由及依据。',
  impairAlloc:
    '减值损失应先抵减分摊至资产组中商誉的账面价值，再按除商誉外其他资产账面价值比重抵减其他资产；并合理确定归属于母公司与少数股东的商誉减值金额。合并报表只反映归属于母公司的商誉减值。详见会计提示第73号附录3、4。',
  twoStep:
    '如与商誉相关的资产组存在减值迹象：①先对不含商誉的资产组测试并确认减值；②再对含商誉的资产组测试，比较账面价值（含分摊商誉、已扣除上一步减值）与可收回金额。',
  subsequent:
    '重大期后事项包括但不限于内外部环境重大变化、重大诉讼与仲裁的最新进展等。',
  priorMethod:
    '若以前期间减值测试有关预测参数与期后实际情况存在重大偏差，应关注管理层会计估计中的判断与决策，识别是否存在管理层偏向。',
  equityMistake:
    '将原收购标的公司“全部资产和全部负债组成的资产组（股东权益）”界定为评估对象、采用股东权益价值方法，不符合准则要求。商誉减值测试范围不是原标的公司股权，而是被分摊商誉的资产组或资产组组合。',
}

function createAllItems(): Record<string, CheckItem[]> {
  return {
    s1: [
      item('s1-1', '1', '公司对商誉减值迹象的判断是否合理',
        '说明外部/内部迹象核查结论；存在迹象时应随时测试。可与 I3-5 交叉索引。',
        '当存在减值迹象时，应随时进行减值测试。因企业合并形成的商誉，无论是否存在减值迹象，每年均应进行减值测试（CAS8第十八条）。'),
    ],
    s2: [
      item('s2-1', '2', '资产组或资产组组合划分是否合理，商誉账面价值是否恰当分摊',
        '说明 CGU 划分依据、协同效应受益对象、分摊方法；详见第10项展开复核。',
        GUIDANCE.allocationMethod),
    ],
    s3: [
      item('s3-1', '3', '公司确定的减值测试方法与模型是否恰当',
        '说明采用 VIU / FVLCD / 孰高；是否误用「股东权益价值」评估原标的股权。',
        GUIDANCE.equityMistake),
    ],
    s4: [
      item('s4-1', '4', '可收回金额确定路径是否合理（使用价值与公允净额孰高）',
        '说明公司最终采用的可收回金额来源、孰高比较过程，及无法可靠估计公允净额时的处理。',
        GUIDANCE.fvHierarchy),
    ],
    s5: [
      item('s5-1', '5.(1)', '盈利预测数据来源是否可靠，是否与历史/计划/行业/宏观相符',
        '复核销量、价格、成本、费用、增长率等关键假设依据。',
        GUIDANCE.assetGroupValue),
      item('s5-2', '5.(2)', '营运资金口径是否与非经营性资产负债一致',
        '说明营运资金是否纳入现金流与账面价值双侧口径。',
        GUIDANCE.workingCapital),
      item('s5-3', '5.(3)', '资本性支出预测是否与预算、运营计划一致',
        '区分更新投资与新增长期资产投资，核对预算/计划。',
        GUIDANCE.capex),
      item('s5-4', '5.(4)', '折旧摊销费用预测是否合理',
        '与资产规模、CAPEX、会计政策是否匹配。'),
      item('s5-5', '5.(5)', '收益期（增长期及永续期）选择是否合理',
        '是否基于管理层批准的预算/预测，原则上不超过5年。',
        GUIDANCE.forecastPeriod),
      item('s5-6', '5.(6)', '可比公司或可比交易的选择是否合理',
        '行业、规模、业务构成、交易时点是否可比。'),
      item('s5-7', '5.(7)', '折现率计算是否合理',
        '风险匹配、税前口径与现金流一致；与 I3-7 WACC 勾稽。',
        GUIDANCE.discountRate),
      item('s5-8', '5.(8)', '终值的处理是否合理',
        '永续增长/退出倍数选择、g 与宏观增长率关系、g 须小于折现率。',
        GUIDANCE.terminalValue),
      item('s5-9', '5.(9)', '关键假设敏感性分析结果',
        '增长率、毛利率、折现率等变动对可收回金额/减值结论的影响。'),
    ],
    s6: [
      item('s6-1', '6.(1)', '盈利预测数据来源是否可靠（收益法公允价值）',
        '同使用价值关注点，但服务于公允价值估计。',
        GUIDANCE.incomeFv),
      item('s6-2', '6.(2)', '营运资金口径是否与非经营性资产负债一致',
        '与账面价值口径双向一致。',
        GUIDANCE.workingCapital),
      item('s6-3', '6.(3)', '资本性支出预测是否与预算、运营计划一致',
        '', GUIDANCE.capex),
      item('s6-4', '6.(4)', '折旧摊销费用预测是否合理',
        '与资产与 CAPEX 假设匹配。'),
      item('s6-5', '6.(5)', '收益期（增长期及永续期）选择是否合理',
        '', GUIDANCE.forecastPeriod),
      item('s6-6', '6.(6)', '可比公司或可比交易的选择是否合理',
        '与收益法其他假设是否协调。'),
      item('s6-7', '6.(7)', '折现率计算是否合理',
        '', GUIDANCE.discountRate),
      item('s6-8', '6.(8)', '终值的处理是否合理',
        '', GUIDANCE.terminalValue),
      item('s6-9', '6.(9)', '关键假设敏感性分析结果',
        '增长率、毛利率、折现率等。'),
    ],
    s7: [
      item('s7-1', '7.(1)', '价值乘数的选择是否合理',
        'EV/EBITDA、P/E 等乘数选取依据。',
        GUIDANCE.marketBestInfo),
      item('s7-2', '7.(2)', '可比公司/交易选择是否与收益法一致且合理',
        '与收益法可比口径交叉核对。',
        GUIDANCE.fvHierarchy),
      item('s7-3', '7.(3)', '价值乘数的计算时间是否合理',
        '时点是否接近计量日、是否存在异常波动。'),
      item('s7-4', '7.(4)', '对价值乘数的调整是否合理',
        '规模、流动性、控制权、非经常性损益等调整。'),
      item('s7-5', '7.(5)', '关键假设敏感性分析结果',
        '乘数±变动对公允价值的影响。'),
    ],
    s8: [
      item('s8-1', '8.(1)', '公允价值的确定是否合理',
        '协议价 / 活跃市价 / 最佳信息估计的层级运用。',
        GUIDANCE.fairValueDef),
      item('s8-2', '8.(2)', '处置费用预测是否合理，证据是否充分适当',
        '法律费用、税费、搬运费、达可售状态直接费用等。',
        GUIDANCE.disposalCost),
    ],
    s9: [
      item('s9-1', '9', '最终选择可收回金额计算方法的理由是否合理',
        '说明为何取 VIU、FVLCD 或孰高；无法可靠估计公允净额时是否改用现值。',
        GUIDANCE.fvHierarchy),
    ],
    s10: [
      item('s10-1', '10.(1)', '商誉所在资产组或资产组组合的划分是否合理',
        '内部监控最低水平、不大于报告分部。',
        GUIDANCE.cguLevel),
      item('s10-2', '10.(2)', '将商誉分摊至相关资产组的方法是否合理',
        '协同效应、相对公允价值比例。',
        GUIDANCE.allocationMethod),
      item('s10-3', '10.(3)', '可收回金额与账面价值的确定基础是否一致',
        '相同资产/负债范围与现金流口径。',
        GUIDANCE.basisConsistency),
      item('s10-4', '10.(4)', '是否将归属于少数股东的商誉调整计入相关资产组账面价值',
        '全部商誉口径调整后再分摊。',
        GUIDANCE.nciGoodwill),
      item('s10-5', '10.(5)', '资产组构成改变时是否重新合理分摊商誉',
        '重组等情形下的重分配与披露。',
        GUIDANCE.realloc),
      item('s10-6', '10.(6)', '商誉减值的分配是否合理',
        '先冲商誉再按比例分摊；母公司与少数股东分摊。',
        GUIDANCE.impairAlloc),
    ],
    s11: [
      item('s11-1', '11.(1)', '是否分两步进行商誉减值测试',
        '不含商誉资产组 → 含商誉资产组。',
        GUIDANCE.twoStep),
      item('s11-2', '11.(2)', '是否考虑期后事项的影响',
        '内外部环境重大变化、重大诉讼仲裁进展等。',
        GUIDANCE.subsequent),
      item('s11-3', '11.(3)', '与以前期间方法是否一致',
        '方法变更理由；回溯测试识别管理层偏向。',
        GUIDANCE.priorMethod),
    ],
  }
}

const checkItems = reactive(createAllItems())
const sectionApplicable = reactive<Record<string, boolean>>({
  s6: false,
  s7: false,
})

const activeNames = ref<string[]>(['s1', 's2', 's3', 's4', 's5'])
const saving = ref(false)
const dirty = ref(false)

const overallAssessment = ref('')
const hasMajorDeviation = ref(false)
const deviationDescription = ref('')
const overallConclusionText = ref('')
const auditNote = ref('')
const auditConclusion = ref('')

function isSectionActive(key: string): boolean {
  const def = sectionDefs.find((s) => s.key === key)
  if (def?.optional) return !!sectionApplicable[key]
  return true
}

function visibleItemCount(section: string): number {
  if (!isSectionActive(section)) return 0
  return (checkItems[section] || []).length
}

function sectionCompletedCount(section: string): number {
  if (!isSectionActive(section)) return 0
  return (checkItems[section] || []).filter((it) => !!it.conclusion).length
}

const sectionProgress = computed(() => {
  const result: Record<string, number> = {}
  for (const s of sectionDefs) {
    const total = visibleItemCount(s.key)
    result[s.key] = total ? Math.round((sectionCompletedCount(s.key) / total) * 100) : 0
  }
  return result
})

const totalItems = computed(() =>
  sectionDefs.reduce((sum, s) => sum + visibleItemCount(s.key), 0),
)

const completedCount = computed(() =>
  sectionDefs.reduce((sum, s) => sum + sectionCompletedCount(s.key), 0),
)

const overallProgressType = computed(() => {
  const pct = totalItems.value ? completedCount.value / totalItems.value : 0
  if (pct >= 1) return 'success'
  if (pct >= 0.5) return 'warning'
  return 'info'
})

function sectionTagType(section: string): 'success' | 'warning' | 'info' {
  if (!isSectionActive(section)) return 'info'
  const pct = sectionProgress.value[section] || 0
  if (pct >= 100) return 'success'
  if (pct >= 50) return 'warning'
  return 'info'
}

function markDirty() {
  dirty.value = true
}

function loadData() {
  const raw = props.allResponses.get(STORAGE_KEY)
  if (!raw) return
  try {
    const parsed = typeof raw === 'string'
      ? JSON.parse(raw)
      : (raw.remark ? JSON.parse(raw.remark) : raw)
    if (!parsed) return

    // v2：按 id 恢复；兼容旧版五段微粒结构时仅恢复汇总字段
    if (parsed.schemaVersion === SCHEMA_VERSION && parsed.checkItems) {
      for (const s of sectionDefs) {
        const saved = parsed.checkItems[s.key] as Array<Partial<CheckItem>> | undefined
        if (!saved?.length) continue
        const byId = new Map(saved.map((x) => [x.id, x]))
        for (const it of checkItems[s.key] || []) {
          const row = byId.get(it.id)
          if (!row) continue
          if (row.content != null) it.content = String(row.content)
          if (row.conclusion != null) it.conclusion = String(row.conclusion)
          if (row.evidence != null) it.evidence = String(row.evidence)
        }
      }
      if (parsed.sectionApplicable) {
        sectionApplicable.s6 = !!parsed.sectionApplicable.s6
        sectionApplicable.s7 = !!parsed.sectionApplicable.s7
      }
    }

    overallAssessment.value = parsed.overallAssessment || ''
    hasMajorDeviation.value = !!parsed.hasMajorDeviation
    deviationDescription.value = parsed.deviationDescription || ''
    overallConclusionText.value = parsed.overallConclusionText || ''
    auditNote.value = parsed.auditNote || ''
    auditConclusion.value = parsed.auditConclusion || ''
  } catch { /* ignore */ }
}

watch(() => props.allResponses, () => loadData(), { immediate: true })

async function handleSave() {
  saving.value = true
  try {
    const payload: Record<string, any> = {
      schemaVersion: SCHEMA_VERSION,
      checkItems: {} as Record<string, Array<{ id: string; content: string; conclusion: string; evidence: string }>>,
      sectionApplicable: {
        s6: sectionApplicable.s6,
        s7: sectionApplicable.s7,
      },
      overallAssessment: overallAssessment.value,
      hasMajorDeviation: hasMajorDeviation.value,
      deviationDescription: deviationDescription.value,
      overallConclusionText: overallConclusionText.value,
      auditNote: auditNote.value,
      auditConclusion: auditConclusion.value,
    }
    for (const s of sectionDefs) {
      payload.checkItems[s.key] = (checkItems[s.key] || []).map((it) => ({
        id: it.id,
        content: it.content,
        conclusion: it.conclusion,
        evidence: it.evidence,
      }))
    }
    emit('save', STORAGE_KEY, JSON.stringify(payload))
    dirty.value = false
    ElMessage.success('复核过程已保存')
  } finally {
    saving.value = false
  }
}

function handleReview() {
  openReviewDialog('I3-8-复核过程')
}
</script>

<style scoped>
.i3-review-process {
  font-size: var(--wp-font-size, 13px);
  padding: 16px;
}

.guide-banner {
  background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 50%, #93c5fd 100%);
  border-radius: 8px;
  padding: 14px 18px;
  margin-bottom: 14px;
}

.guide-title {
  font-size: 14px;
  font-weight: 600;
  color: #1e40af;
  margin-bottom: 10px;
}

.guide-steps {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 24px;
}

.guide-step {
  display: flex;
  align-items: center;
  gap: 8px;
}

.step-number {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #2563eb;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}

.step-text {
  font-size: 12px;
  color: #1e3a5f;
  line-height: 1.4;
}

.methodology-block {
  background: #fffbeb;
  border-left: 4px solid #f59e0b;
  padding: 10px 14px;
  margin-bottom: 12px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.7;
}

.methodology-block p {
  margin: 0;
}

.objective-alert,
.expert-alert {
  margin-bottom: 12px;
}

.guidance-details {
  margin-bottom: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
}

.guidance-details .guidance-content ul {
  padding-left: 20px;
  margin-top: 8px;
  line-height: 1.8;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
}

.section-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tab-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.tab-toolbar .toolbar-left,
.tab-toolbar .toolbar-right {
  display: flex;
  align-items: center;
  gap: 4px;
}

.review-scroll-area {
  max-height: 640px;
  overflow-y: auto;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 16px;
}

.collapse-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding-right: 8px;
  gap: 12px;
}

.collapse-title-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.section-intro {
  margin: 0 0 10px;
  font-size: 12px;
  color: #6b7280;
  line-height: 1.6;
}

.na-hint {
  padding: 12px;
  font-size: 12px;
  color: #6b7280;
  background: #f9fafb;
  border-radius: 6px;
}

.check-items-container {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 4px 0;
}

.check-item {
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 10px 12px;
  background: #fafafa;
}

.check-item-header {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 6px;
}

.check-item-number {
  font-weight: 600;
  color: #2563eb;
  font-size: 12px;
  min-width: 42px;
  flex-shrink: 0;
}

.check-item-title {
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #374151;
  line-height: 1.5;
}

.check-guidance {
  margin-bottom: 8px;
  font-size: 12px;
}

.check-guidance summary {
  cursor: pointer;
  color: #2563eb;
  font-weight: 500;
}

.guidance-pre {
  margin: 6px 0 0;
  padding: 8px 10px;
  background: #eff6ff;
  border-radius: 4px;
  color: #1e40af;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  font-size: 12px;
  line-height: 1.65;
}

.check-item-footer {
  display: flex;
  align-items: center;
  margin-top: 8px;
  gap: 8px;
}

.summary-card,
.audit-note-card {
  margin-bottom: 12px;
}

.summary-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.summary-title {
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
}

.summary-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.summary-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.summary-label {
  font-weight: 500;
  color: #374151;
  white-space: nowrap;
  min-width: 150px;
  line-height: 32px;
}

.table-actions {
  display: flex;
  gap: 8px;
}

:deep(.el-collapse-item__header) {
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
  height: auto;
  min-height: 44px;
  line-height: 1.4;
  padding: 8px 0;
}

:deep(.el-collapse-item__content) {
  padding-bottom: 12px;
}

:deep(.el-progress-bar__outer) {
  border-radius: 4px;
}
</style>
