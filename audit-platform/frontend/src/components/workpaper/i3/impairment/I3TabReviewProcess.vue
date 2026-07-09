<!--
  I3TabReviewProcess.vue — I3-8 复核公司减值测试过程及结论
  153行12列超大段落型检查（虚拟滚动 max-height=600 overflow-y auto）
  5 collapsible sections (el-collapse): 假设审阅/模型检查/参数合理性/计算验证/结论评价
  Each section ~30 check items: check title + textarea + conclusion select + evidence
  Section progress indicators + AI button per section
  蓝色渐变引导区(5步复核流程) + 琥珀色方法论
  结论汇总区(bottom: 总评价+是否存在重大偏差)
  Table font 13px
  Spec: .kiro/specs/i3-goodwill/ Task 4.9
  Requirements: 7.1~7.4
-->
<template>
  <div class="i3-review-process">
    <!-- 蓝色渐变引导区：5步复核流程 -->
    <div class="guide-banner">
      <div class="guide-title">复核公司减值测试过程（5步复核流程）</div>
      <div class="guide-steps">
        <div class="guide-step" v-for="(step, idx) in guideSteps" :key="idx">
          <span class="step-number">{{ idx + 1 }}</span>
          <span class="step-text">{{ step }}</span>
        </div>
      </div>
    </div>

    <!-- 琥珀色方法论上下文 -->
    <div class="methodology-block">
      <p><strong>CAS8第十七条~第二十条 商誉减值测试复核要点：</strong>
      含商誉的资产组减值测试应在资产负债表日进行。审计师需复核被审计单位的减值测试过程，
      包括：①关键假设（收入增长/毛利率/折现率/永续增长率）是否有充分依据；
      ②DCF模型逻辑是否正确（现金流预测/折现计算/终值处理）；
      ③关键参数是否在合理区间（与可比交易/行业数据对比）；
      ④数学计算是否准确无误；⑤最终减值结论是否恰当。
      商誉减值一经确认不得转回（CAS8第十七条）。</p>
    </div>

    <!-- Section Header -->
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

    <!-- 主内容区：虚拟滚动 -->
    <div class="review-scroll-area">
      <el-collapse v-model="activeNames">
        <!-- Section 1: 假设审阅 -->
        <el-collapse-item name="assumptions">
          <template #title>
            <div class="collapse-title">
              <span>一、假设审阅</span>
              <div class="collapse-title-right">
                <el-progress
                  :percentage="sectionProgress.assumptions"
                  :stroke-width="6" :show-text="false"
                  style="width:80px;margin-right:8px"
                />
                <el-tag size="small" :type="sectionTagType('assumptions')">
                  {{ sectionCompletedCount('assumptions') }}/{{ checkItems.assumptions.length }}
                </el-tag>
                <el-button size="small" type="primary" text
                  @click.stop="handleAiSection('assumptions')">
                  <el-icon><MagicStick /></el-icon> AI
                </el-button>
              </div>
            </div>
          </template>
          <div class="check-items-container">
            <div class="check-item" v-for="(item, idx) in checkItems.assumptions" :key="idx">
              <div class="check-item-header">
                <span class="check-item-number">1.{{ idx + 1 }}</span>
                <span class="check-item-title">{{ item.title }}</span>
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
                <el-select v-model="item.conclusion" size="small" :disabled="isReadonly"
                  placeholder="结论" style="width:140px" @change="markDirty">
                  <el-option label="合理" value="合理" />
                  <el-option label="不合理" value="不合理" />
                  <el-option label="需调整" value="需调整" />
                  <el-option label="待确认" value="待确认" />
                </el-select>
                <el-input v-model="item.evidence" size="small" :disabled="isReadonly"
                  placeholder="审计证据/依据" style="flex:1;margin-left:8px" @blur="markDirty" />
              </div>
            </div>
          </div>
        </el-collapse-item>

        <!-- Section 2: 模型检查 -->
        <el-collapse-item name="model">
          <template #title>
            <div class="collapse-title">
              <span>二、模型检查</span>
              <div class="collapse-title-right">
                <el-progress
                  :percentage="sectionProgress.model"
                  :stroke-width="6" :show-text="false"
                  style="width:80px;margin-right:8px"
                />
                <el-tag size="small" :type="sectionTagType('model')">
                  {{ sectionCompletedCount('model') }}/{{ checkItems.model.length }}
                </el-tag>
                <el-button size="small" type="primary" text
                  @click.stop="handleAiSection('model')">
                  <el-icon><MagicStick /></el-icon> AI
                </el-button>
              </div>
            </div>
          </template>
          <div class="check-items-container">
            <div class="check-item" v-for="(item, idx) in checkItems.model" :key="idx">
              <div class="check-item-header">
                <span class="check-item-number">2.{{ idx + 1 }}</span>
                <span class="check-item-title">{{ item.title }}</span>
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
                <el-select v-model="item.conclusion" size="small" :disabled="isReadonly"
                  placeholder="结论" style="width:140px" @change="markDirty">
                  <el-option label="合理" value="合理" />
                  <el-option label="不合理" value="不合理" />
                  <el-option label="需调整" value="需调整" />
                  <el-option label="待确认" value="待确认" />
                </el-select>
                <el-input v-model="item.evidence" size="small" :disabled="isReadonly"
                  placeholder="审计证据/依据" style="flex:1;margin-left:8px" @blur="markDirty" />
              </div>
            </div>
          </div>
        </el-collapse-item>

        <!-- Section 3: 参数合理性 -->
        <el-collapse-item name="parameters">
          <template #title>
            <div class="collapse-title">
              <span>三、参数合理性</span>
              <div class="collapse-title-right">
                <el-progress
                  :percentage="sectionProgress.parameters"
                  :stroke-width="6" :show-text="false"
                  style="width:80px;margin-right:8px"
                />
                <el-tag size="small" :type="sectionTagType('parameters')">
                  {{ sectionCompletedCount('parameters') }}/{{ checkItems.parameters.length }}
                </el-tag>
                <el-button size="small" type="primary" text
                  @click.stop="handleAiSection('parameters')">
                  <el-icon><MagicStick /></el-icon> AI
                </el-button>
              </div>
            </div>
          </template>
          <div class="check-items-container">
            <div class="check-item" v-for="(item, idx) in checkItems.parameters" :key="idx">
              <div class="check-item-header">
                <span class="check-item-number">3.{{ idx + 1 }}</span>
                <span class="check-item-title">{{ item.title }}</span>
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
                <el-select v-model="item.conclusion" size="small" :disabled="isReadonly"
                  placeholder="结论" style="width:140px" @change="markDirty">
                  <el-option label="合理" value="合理" />
                  <el-option label="不合理" value="不合理" />
                  <el-option label="需调整" value="需调整" />
                  <el-option label="待确认" value="待确认" />
                </el-select>
                <el-input v-model="item.evidence" size="small" :disabled="isReadonly"
                  placeholder="审计证据/依据" style="flex:1;margin-left:8px" @blur="markDirty" />
              </div>
            </div>
          </div>
        </el-collapse-item>

        <!-- Section 4: 计算验证 -->
        <el-collapse-item name="calculation">
          <template #title>
            <div class="collapse-title">
              <span>四、计算验证</span>
              <div class="collapse-title-right">
                <el-progress
                  :percentage="sectionProgress.calculation"
                  :stroke-width="6" :show-text="false"
                  style="width:80px;margin-right:8px"
                />
                <el-tag size="small" :type="sectionTagType('calculation')">
                  {{ sectionCompletedCount('calculation') }}/{{ checkItems.calculation.length }}
                </el-tag>
                <el-button size="small" type="primary" text
                  @click.stop="handleAiSection('calculation')">
                  <el-icon><MagicStick /></el-icon> AI
                </el-button>
              </div>
            </div>
          </template>
          <div class="check-items-container">
            <div class="check-item" v-for="(item, idx) in checkItems.calculation" :key="idx">
              <div class="check-item-header">
                <span class="check-item-number">4.{{ idx + 1 }}</span>
                <span class="check-item-title">{{ item.title }}</span>
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
                <el-select v-model="item.conclusion" size="small" :disabled="isReadonly"
                  placeholder="结论" style="width:140px" @change="markDirty">
                  <el-option label="合理" value="合理" />
                  <el-option label="不合理" value="不合理" />
                  <el-option label="需调整" value="需调整" />
                  <el-option label="待确认" value="待确认" />
                </el-select>
                <el-input v-model="item.evidence" size="small" :disabled="isReadonly"
                  placeholder="审计证据/依据" style="flex:1;margin-left:8px" @blur="markDirty" />
              </div>
            </div>
          </div>
        </el-collapse-item>

        <!-- Section 5: 结论评价 -->
        <el-collapse-item name="conclusion">
          <template #title>
            <div class="collapse-title">
              <span>五、结论评价</span>
              <div class="collapse-title-right">
                <el-progress
                  :percentage="sectionProgress.conclusion"
                  :stroke-width="6" :show-text="false"
                  style="width:80px;margin-right:8px"
                />
                <el-tag size="small" :type="sectionTagType('conclusion')">
                  {{ sectionCompletedCount('conclusion') }}/{{ checkItems.conclusion.length }}
                </el-tag>
                <el-button size="small" type="primary" text
                  @click.stop="handleAiSection('conclusion')">
                  <el-icon><MagicStick /></el-icon> AI
                </el-button>
              </div>
            </div>
          </template>
          <div class="check-items-container">
            <div class="check-item" v-for="(item, idx) in checkItems.conclusion" :key="idx">
              <div class="check-item-header">
                <span class="check-item-number">5.{{ idx + 1 }}</span>
                <span class="check-item-title">{{ item.title }}</span>
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
                <el-select v-model="item.conclusion" size="small" :disabled="isReadonly"
                  placeholder="结论" style="width:140px" @change="markDirty">
                  <el-option label="合理" value="合理" />
                  <el-option label="不合理" value="不合理" />
                  <el-option label="需调整" value="需调整" />
                  <el-option label="待确认" value="待确认" />
                </el-select>
                <el-input v-model="item.evidence" size="small" :disabled="isReadonly"
                  placeholder="审计证据/依据" style="flex:1;margin-left:8px" @blur="markDirty" />
              </div>
            </div>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>

    <!-- 结论汇总区 -->
    <el-card class="summary-card" shadow="never">
      <template #header>
        <div class="summary-header">
          <span class="summary-title">复核结论汇总</span>
          <el-tag :type="hasMajorDeviation ? 'danger' : 'success'" size="small">
            {{ hasMajorDeviation ? '存在重大偏差' : '未发现重大偏差' }}
          </el-tag>
        </div>
      </template>
      <div class="summary-body">
        <div class="summary-row">
          <span class="summary-label">总评价：</span>
          <el-select v-model="overallAssessment" :disabled="isReadonly"
            size="small" placeholder="选择总评价" style="width:220px">
            <el-option label="公司减值测试过程及结论合理" value="合理" />
            <el-option label="公司减值测试过程基本合理，存在瑕疵" value="基本合理" />
            <el-option label="公司减值测试过程存在重大缺陷" value="存在重大缺陷" />
            <el-option label="无法评价（资料不足）" value="无法评价" />
          </el-select>
        </div>
        <div class="summary-row">
          <span class="summary-label">是否存在重大偏差：</span>
          <el-radio-group v-model="hasMajorDeviation" :disabled="isReadonly">
            <el-radio :value="false">否</el-radio>
            <el-radio :value="true">是</el-radio>
          </el-radio-group>
        </div>
        <div class="summary-row" v-if="hasMajorDeviation">
          <span class="summary-label">偏差说明：</span>
          <el-input v-model="deviationDescription" type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly"
            placeholder="描述重大偏差的具体内容、影响金额及建议调整" style="flex:1" />
        </div>
        <div class="summary-row">
          <span class="summary-label">综合结论：</span>
          <el-input v-model="overallConclusionText" type="textarea"
            :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
            placeholder="综合五项复核结果，得出最终结论：&#10;1. 公司减值测试假设/模型/参数/计算/结论的合理性评价&#10;2. 审计师独立复核是否得出一致结论&#10;3. 后续跟进事项（若有）" style="flex:1" />
        </div>
      </div>
    </el-card>

    <!-- 保存按钮 -->
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
import { MagicStick } from '@element-plus/icons-vue'
import http from '@/utils/http'

/**
 * I3TabReviewProcess.vue — I3-8 复核公司减值测试过程及结论
 * 153行12列超大段落型检查
 * 5 sections × ~30 items = ~150 check items (maps to 153 rows)
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

// --- Guide Steps ---
const guideSteps = [
  '审阅关键假设（收入增长/毛利率/折现率/永续增长率）',
  '检查DCF模型逻辑（现金流预测/折现/终值处理）',
  '验证参数合理性（与行业/可比交易/历史对比）',
  '复核数学计算正确性（PV/TV/WACC公式）',
  '评价最终结论恰当性（减值金额/是否需调整）',
]

// --- Check Item Type ---
interface CheckItem {
  title: string
  placeholder: string
  content: string
  conclusion: string
  evidence: string
}

// --- Active collapse panels ---
const activeNames = ref<string[]>(['assumptions'])
const saving = ref(false)
const dirty = ref(false)

// --- Section 1: 假设审阅 (31 items) ---
function createAssumptionItems(): CheckItem[] {
  return [
    { title: '收入预测假设——历史增长趋势分析', placeholder: '复核公司收入预测是否基于合理的历史增长趋势，是否考虑了市场容量变化', content: '', conclusion: '', evidence: '' },
    { title: '收入预测假设——行业增长率对比', placeholder: '对比行业整体增长率（Wind/同花顺数据），评估公司收入增长假设的合理性', content: '', conclusion: '', evidence: '' },
    { title: '收入预测假设——客户集中度影响', placeholder: '前五大客户占比/客户流失风险是否在预测中反映', content: '', conclusion: '', evidence: '' },
    { title: '收入预测假设——新业务/新产品贡献', placeholder: '新业务收入假设是否有订单/合同支撑，是否过于乐观', content: '', conclusion: '', evidence: '' },
    { title: '收入预测假设——市场份额变动', placeholder: '市场份额假设是否合理，是否考虑竞争格局变化', content: '', conclusion: '', evidence: '' },
    { title: '收入预测假设——价格变动因素', placeholder: '产品/服务价格调整假设是否有市场依据', content: '', conclusion: '', evidence: '' },
    { title: '毛利率假设——历史毛利率趋势', placeholder: '复核毛利率假设是否符合历史趋势，异常波动是否有合理解释', content: '', conclusion: '', evidence: '' },
    { title: '毛利率假设——成本结构变化', placeholder: '原材料/人工/制造费用变化假设是否合理', content: '', conclusion: '', evidence: '' },
    { title: '毛利率假设——规模效应考虑', placeholder: '收入增长带来的规模效应在毛利率中的体现是否合理', content: '', conclusion: '', evidence: '' },
    { title: '毛利率假设——与同行业对比', placeholder: '毛利率假设与同行业上市公司对比是否处于合理区间', content: '', conclusion: '', evidence: '' },
    { title: '费用率假设——销售费用率', placeholder: '销售费用率假设是否考虑渠道拓展/品牌投入等因素', content: '', conclusion: '', evidence: '' },
    { title: '费用率假设——管理费用率', placeholder: '管理费用率假设是否考虑组织扩张/系统建设等因素', content: '', conclusion: '', evidence: '' },
    { title: '费用率假设——研发费用率', placeholder: '研发费用投入假设是否与技术迭代需求匹配', content: '', conclusion: '', evidence: '' },
    { title: '折现率假设——WACC计算方法', placeholder: '复核WACC计算方法是否正确（CAPM/APM/多因子模型选择）', content: '', conclusion: '', evidence: '' },
    { title: '折现率假设——无风险利率选取', placeholder: '无风险利率选取是否合理（国债收益率期限/到期日匹配）', content: '', conclusion: '', evidence: '' },
    { title: '折现率假设——Beta系数选取', placeholder: 'Beta系数选取是否合理（可比公司/时间窗口/调整方法）', content: '', conclusion: '', evidence: '' },
    { title: '折现率假设——市场风险溢价', placeholder: '市场风险溢价(ERP)选取是否有权威数据支持', content: '', conclusion: '', evidence: '' },
    { title: '折现率假设——特定风险溢价', placeholder: '公司特定风险溢价/规模溢价/非流动性折价是否合理', content: '', conclusion: '', evidence: '' },
    { title: '折现率假设——资本结构假设', placeholder: '目标资本结构(D/E)假设是否合理（行业均值/公司实际）', content: '', conclusion: '', evidence: '' },
    { title: '折现率假设——债务成本', placeholder: '债务成本是否反映当前市场利率和公司信用等级', content: '', conclusion: '', evidence: '' },
    { title: '永续增长率假设——与GDP/CPI对比', placeholder: '永续增长率是否不超过宏观经济长期增长率', content: '', conclusion: '', evidence: '' },
    { title: '永续增长率假设——行业成熟度', placeholder: '永续增长率是否考虑行业生命周期阶段（成长/成熟/衰退）', content: '', conclusion: '', evidence: '' },
    { title: '永续增长率假设——与折现率关系', placeholder: '永续增长率是否小于折现率（g<WACC否则终值公式无意义）', content: '', conclusion: '', evidence: '' },
    { title: '营运资本假设——应收款周转', placeholder: '应收账款周转天数假设是否与历史及行业水平匹配', content: '', conclusion: '', evidence: '' },
    { title: '营运资本假设——存货周转', placeholder: '存货周转天数假设是否合理', content: '', conclusion: '', evidence: '' },
    { title: '营运资本假设——应付款周转', placeholder: '应付账款周转天数假设是否合理', content: '', conclusion: '', evidence: '' },
    { title: '资本支出假设——维持性CAPEX', placeholder: '维持性资本支出假设是否与折旧摊销匹配', content: '', conclusion: '', evidence: '' },
    { title: '资本支出假设——扩张性CAPEX', placeholder: '扩张性资本支出假设是否与收入增长预期匹配', content: '', conclusion: '', evidence: '' },
    { title: '预测期假设——预测期限合理性', placeholder: '预测期限（通常5年）是否足够覆盖到稳定状态', content: '', conclusion: '', evidence: '' },
    { title: '税率假设——有效税率', placeholder: '有效税率假设是否考虑了税收优惠/高新认定/地区政策', content: '', conclusion: '', evidence: '' },
    { title: '假设一致性——各假设间内部协调', placeholder: '各项假设之间是否保持内部逻辑一致（如高增长→高CAPEX）', content: '', conclusion: '', evidence: '' },
  ]
}

// --- Section 2: 模型检查 (30 items) ---
function createModelItems(): CheckItem[] {
  return [
    { title: 'DCF模型结构——现金流定义', placeholder: '复核FCF定义：EBIT×(1-t)+折旧摊销-CAPEX-ΔWC 是否完整', content: '', conclusion: '', evidence: '' },
    { title: 'DCF模型结构——折现方法', placeholder: '折现采用年中折现/年末折现，是否与现金流产生时点匹配', content: '', conclusion: '', evidence: '' },
    { title: 'DCF模型结构——终值模型选择', placeholder: '终值采用永续增长/退出倍数，选择是否合理', content: '', conclusion: '', evidence: '' },
    { title: 'DCF模型结构——终值公式正确性', placeholder: 'TV=FCF_n×(1+g)/(WACC-g) 公式是否正确应用', content: '', conclusion: '', evidence: '' },
    { title: 'DCF模型结构——折现期数', placeholder: '折现期数(n)是否与预测年数一致，终值折现期是否正确', content: '', conclusion: '', evidence: '' },
    { title: '现金流预测——收入到EBIT推导', placeholder: '从收入→毛利→EBIT的推导逻辑是否清晰正确', content: '', conclusion: '', evidence: '' },
    { title: '现金流预测——非经营项目排除', placeholder: '是否正确排除了非经营性项目（一次性收益/非核心资产）', content: '', conclusion: '', evidence: '' },
    { title: '现金流预测——折旧摊销一致性', placeholder: '折旧摊销金额是否与CAPEX假设和资产规模匹配', content: '', conclusion: '', evidence: '' },
    { title: '现金流预测——营运资本变动', placeholder: '营运资本变动计算是否正确（增量法vs绝对值法）', content: '', conclusion: '', evidence: '' },
    { title: '现金流预测——资本支出分类', placeholder: '维持性/扩张性CAPEX区分是否清晰合理', content: '', conclusion: '', evidence: '' },
    { title: '现金流预测——现金流平衡检验', placeholder: 'FCF各年数据是否通过利润表+资产负债表交叉验证', content: '', conclusion: '', evidence: '' },
    { title: '终值处理——终值占比合理性', placeholder: '终值占总价值比重是否在合理范围（通常50-80%）', content: '', conclusion: '', evidence: '' },
    { title: '终值处理——永续年现金流', placeholder: '永续年FCF是否为正常化水平（非预测期末年异常值）', content: '', conclusion: '', evidence: '' },
    { title: '终值处理——永续增长vs退出倍数交叉验证', placeholder: '两种终值方法计算结果是否相互印证', content: '', conclusion: '', evidence: '' },
    { title: 'WACC应用——一致性检查', placeholder: 'WACC应用于税后FCF（FCFF→WACC）还是税后权益CF（FCFE→Ke）是否一致', content: '', conclusion: '', evidence: '' },
    { title: 'WACC应用——名义vs实际利率', placeholder: '折现率与现金流预测的通胀基准是否一致（同为名义或同为实际）', content: '', conclusion: '', evidence: '' },
    { title: 'WACC应用——币种一致性', placeholder: '多币种情况下折现率与现金流币种是否匹配', content: '', conclusion: '', evidence: '' },
    { title: '模型完整性——少数股东利益', placeholder: '是否正确处理了少数股东权益对应的现金流', content: '', conclusion: '', evidence: '' },
    { title: '模型完整性——非经营资产', placeholder: '非经营资产（现金/投资等）是否单独加回', content: '', conclusion: '', evidence: '' },
    { title: '模型完整性——有息负债', placeholder: '从企业价值(EV)到权益价值时有息负债是否正确扣减', content: '', conclusion: '', evidence: '' },
    { title: '模型完整性——或有负债/表外项目', placeholder: '或有负债/表外承诺是否在模型中反映', content: '', conclusion: '', evidence: '' },
    { title: '模型逻辑——循环引用检查', placeholder: '模型中是否存在循环引用（WACC↔D/E↔EV）', content: '', conclusion: '', evidence: '' },
    { title: '模型逻辑——正负号一致性', placeholder: '现金流入/流出正负号是否全模型一致', content: '', conclusion: '', evidence: '' },
    { title: '模型逻辑——时间轴对齐', placeholder: '基准日/预测起始日/报告日时间轴是否正确对齐', content: '', conclusion: '', evidence: '' },
    { title: '模型适用性——被评估资产界定', placeholder: '模型评估的资产范围是否与CGU账面资产范围一致', content: '', conclusion: '', evidence: '' },
    { title: '模型适用性——评估对象价值类型', placeholder: '使用价值(VIU)的限制条件是否满足（无处置费用扣除/税前折现率）', content: '', conclusion: '', evidence: '' },
    { title: '模型适用性——估值方法选择', placeholder: '选用DCF（而非市场法/资产基础法）的理由是否充分', content: '', conclusion: '', evidence: '' },
    { title: '可比验证——EV/EBITDA交叉检验', placeholder: '隐含的EV/EBITDA倍数是否在可比公司范围内', content: '', conclusion: '', evidence: '' },
    { title: '可比验证——P/E交叉检验', placeholder: '隐含PE是否与行业/公司历史PE一致', content: '', conclusion: '', evidence: '' },
    { title: '模型版本——与上年模型对比', placeholder: '模型结构是否与上年一致，变更是否有合理说明', content: '', conclusion: '', evidence: '' },
  ]
}

// --- Section 3: 参数合理性 (31 items) ---
function createParameterItems(): CheckItem[] {
  return [
    { title: 'WACC——无风险利率来源验证', placeholder: '验证无风险利率数据来源（中债/国债收益率曲线），期限是否匹配', content: '', conclusion: '', evidence: '' },
    { title: 'WACC——Beta系数来源验证', placeholder: '验证Beta来源（Wind/Bloomberg），时间窗口（2-5年）/频率（周/月）', content: '', conclusion: '', evidence: '' },
    { title: 'WACC——可比公司选取', placeholder: '可比公司选取标准是否适当（行业/规模/业务构成）', content: '', conclusion: '', evidence: '' },
    { title: 'WACC——去杠杆/再杠杆过程', placeholder: 'Unlevered Beta→Relevered Beta转换公式及参数是否正确', content: '', conclusion: '', evidence: '' },
    { title: 'WACC——市场风险溢价(ERP)数据源', placeholder: 'ERP取值来源（Damodaran/CSMAR/历史均值法/隐含法）是否合理', content: '', conclusion: '', evidence: '' },
    { title: 'WACC——规模溢价', placeholder: '规模溢价选取是否有依据（Duff & Phelps/市值排序）', content: '', conclusion: '', evidence: '' },
    { title: 'WACC——特定风险溢价', placeholder: '公司特定风险溢价的加点依据是否充分且一致', content: '', conclusion: '', evidence: '' },
    { title: 'WACC——债务成本', placeholder: '债务成本取值是否反映当前融资环境和公司信用水平', content: '', conclusion: '', evidence: '' },
    { title: 'WACC——目标资本结构', placeholder: '目标D/E比率是否合理（行业均值/公司目标/可比公司）', content: '', conclusion: '', evidence: '' },
    { title: 'WACC——最终计算结果', placeholder: '最终WACC值是否在行业合理范围内（8-15%通常区间）', content: '', conclusion: '', evidence: '' },
    { title: '永续增长率——经济依据', placeholder: '永续增长率g与长期GDP增长率/CPI对比是否合理', content: '', conclusion: '', evidence: '' },
    { title: '永续增长率——行业特征', placeholder: '永续增长率是否反映行业长期发展趋势（衰退行业应<GDP）', content: '', conclusion: '', evidence: '' },
    { title: '永续增长率——与上年对比', placeholder: '永续增长率较上年变化是否有合理解释', content: '', conclusion: '', evidence: '' },
    { title: '收入参数——增长率合理性', placeholder: '各年收入增长率是否合理（高增→逐年递减→稳态）', content: '', conclusion: '', evidence: '' },
    { title: '收入参数——与在手订单/合同匹配', placeholder: '近1-2年收入预测是否有订单/合同支撑', content: '', conclusion: '', evidence: '' },
    { title: '收入参数——与管理层预算对比', placeholder: '收入预测是否与管理层年度预算/五年规划一致', content: '', conclusion: '', evidence: '' },
    { title: '收入参数——与分析师预期对比', placeholder: '收入预测是否与市场分析师一致预期在合理偏差内', content: '', conclusion: '', evidence: '' },
    { title: '利润率参数——毛利率趋势', placeholder: '毛利率假设是否体现了从当前水平到稳态水平的合理过渡', content: '', conclusion: '', evidence: '' },
    { title: '利润率参数——EBITDA利润率', placeholder: 'EBITDA利润率是否在可比公司范围内', content: '', conclusion: '', evidence: '' },
    { title: '利润率参数——净利率合理性', placeholder: '最终净利率是否在合理区间，是否存在利润率"虚高"', content: '', conclusion: '', evidence: '' },
    { title: '营运资本参数——周转率数据源', placeholder: '周转率取值是否基于历史数据+合理调整', content: '', conclusion: '', evidence: '' },
    { title: '营运资本参数——与行业对比', placeholder: '营运资本占收入比与行业水平对比是否合理', content: '', conclusion: '', evidence: '' },
    { title: '资本支出参数——折旧覆盖率', placeholder: 'CAPEX/折旧比率是否合理（成长期>1/稳态期≈1）', content: '', conclusion: '', evidence: '' },
    { title: '资本支出参数——固定资产周转率', placeholder: '隐含的固定资产周转率与历史及行业是否匹配', content: '', conclusion: '', evidence: '' },
    { title: '税率参数——实际有效税率', placeholder: '税率假设是否考虑了优惠到期/地区差异/递延税', content: '', conclusion: '', evidence: '' },
    { title: '参数敏感性——WACC±1%影响', placeholder: 'WACC变动±1%对可收回金额的影响金额和幅度', content: '', conclusion: '', evidence: '' },
    { title: '参数敏感性——增长率±0.5%影响', placeholder: '永续增长率变动±0.5%对可收回金额的影响', content: '', conclusion: '', evidence: '' },
    { title: '参数敏感性——收入±10%影响', placeholder: '收入假设变动±10%对可收回金额的影响', content: '', conclusion: '', evidence: '' },
    { title: '参数敏感性——综合敏感性分析', placeholder: '多参数同时变动（最悲观/最乐观情景）的影响', content: '', conclusion: '', evidence: '' },
    { title: '参数一致性——评估机构参数采信', placeholder: '若引用评估报告，评估机构参数选取依据是否充分', content: '', conclusion: '', evidence: '' },
    { title: '参数一致性——与其他CGU参数对比', placeholder: '多个CGU的参数选取是否保持内部一致（折现率/增长率差异合理性）', content: '', conclusion: '', evidence: '' },
  ]
}

// --- Section 4: 计算验证 (31 items) ---
function createCalculationItems(): CheckItem[] {
  return [
    { title: 'PV计算——各年折现因子', placeholder: '验证各年折现因子 1/(1+WACC)^i 计算是否正确', content: '', conclusion: '', evidence: '' },
    { title: 'PV计算——各年现值', placeholder: '验证各年FCF×折现因子=各年现值 计算是否正确', content: '', conclusion: '', evidence: '' },
    { title: 'PV计算——现值合计', placeholder: '验证各年现值加总是否正确（含终值现值）', content: '', conclusion: '', evidence: '' },
    { title: '终值计算——永续公式应用', placeholder: '验证TV=FCF_n×(1+g)/(WACC-g) 代入数值是否正确', content: '', conclusion: '', evidence: '' },
    { title: '终值计算——终值折现', placeholder: '验证终值折现到基准日的计算是否正确', content: '', conclusion: '', evidence: '' },
    { title: '终值计算——终值占比', placeholder: '终值占总企业价值的比例是否在50-80%合理范围', content: '', conclusion: '', evidence: '' },
    { title: 'WACC计算——权益成本Ke', placeholder: '验证Ke=Rf+β×ERP+Rs 计算过程及结果', content: '', conclusion: '', evidence: '' },
    { title: 'WACC计算——加权平均过程', placeholder: '验证WACC=Ke×E/(E+D)+Kd×(1-t)×D/(E+D) 计算是否正确', content: '', conclusion: '', evidence: '' },
    { title: '现金流计算——EBIT计算', placeholder: '验证收入-成本-费用=EBIT推导过程', content: '', conclusion: '', evidence: '' },
    { title: '现金流计算——税后NOPAT', placeholder: '验证NOPAT=EBIT×(1-t) 计算是否正确', content: '', conclusion: '', evidence: '' },
    { title: '现金流计算——FCF推导', placeholder: '验证FCF=NOPAT+D&A-CAPEX-ΔWC 各项是否完整', content: '', conclusion: '', evidence: '' },
    { title: '现金流计算——营运资本变动', placeholder: '验证ΔWC=本年WC-上年WC 计算是否正确', content: '', conclusion: '', evidence: '' },
    { title: '现金流计算——各年加总校验', placeholder: '验证各年FCF加总与分项计算一致', content: '', conclusion: '', evidence: '' },
    { title: '减值计算——账面价值确定', placeholder: '验证CGU账面价值（含商誉）加总是否正确', content: '', conclusion: '', evidence: '' },
    { title: '减值计算——可收回金额确定', placeholder: '验证可收回金额=MAX(FVLCD, VIU) 选择是否正确', content: '', conclusion: '', evidence: '' },
    { title: '减值计算——减值金额', placeholder: '验证减值=MAX(账面-可收回, 0) 计算是否正确', content: '', conclusion: '', evidence: '' },
    { title: '减值分摊——先冲商誉', placeholder: '验证减值先冲商誉（至零为止）的分摊金额', content: '', conclusion: '', evidence: '' },
    { title: '减值分摊——其他资产按比例', placeholder: '验证剩余减值按资产组其他资产账面比例分摊计算', content: '', conclusion: '', evidence: '' },
    { title: '减值分摊——下限约束', placeholder: '各资产分摊后不低于：公允-处置费/使用价值/零 三者孰高', content: '', conclusion: '', evidence: '' },
    { title: '四则运算——加减法复核', placeholder: '对模型中的加减法运算进行抽样复核', content: '', conclusion: '', evidence: '' },
    { title: '四则运算——乘除法复核', placeholder: '对模型中的乘除法/幂运算进行抽样复核', content: '', conclusion: '', evidence: '' },
    { title: '引用链接——数据来源追溯', placeholder: '模型中引用的外部数据是否均可追溯到原始来源', content: '', conclusion: '', evidence: '' },
    { title: '引用链接——内部勾稽', placeholder: '模型各sheet/区域之间的数据引用是否一致无断裂', content: '', conclusion: '', evidence: '' },
    { title: '单位一致性——金额单位', placeholder: '全模型金额单位（元/万元/百万）是否统一', content: '', conclusion: '', evidence: '' },
    { title: '单位一致性——百分比格式', placeholder: '增长率/利润率/折现率百分比表示是否一致（小数vs百分数）', content: '', conclusion: '', evidence: '' },
    { title: '期间对齐——基准日', placeholder: '评估基准日是否与报告日一致（若不一致如何调整）', content: '', conclusion: '', evidence: '' },
    { title: '期间对齐——预测起始年', placeholder: '预测第一年是否从基准日后开始（非基准日当年）', content: '', conclusion: '', evidence: '' },
    { title: '合计校验——分部vs合计', placeholder: '多CGU情况下分部合计是否等于总表合计', content: '', conclusion: '', evidence: '' },
    { title: '合计校验——减值总额vs审定表', placeholder: '减值测试得出的总减值金额是否与I3-1审定表一致', content: '', conclusion: '', evidence: '' },
    { title: '独立估算——审计师独立PV计算', placeholder: '审计师独立重新计算的现值与公司模型差异分析', content: '', conclusion: '', evidence: '' },
    { title: '独立估算——合理偏差范围判断', placeholder: '审计师独立估算与公司结论的差异是否在可接受范围内（<5%）', content: '', conclusion: '', evidence: '' },
  ]
}

// --- Section 5: 结论评价 (30 items) ---
function createConclusionItems(): CheckItem[] {
  return [
    { title: '减值结论——金额判断', placeholder: '公司得出的减值金额结论是否合理，与审计师独立估算差异', content: '', conclusion: '', evidence: '' },
    { title: '减值结论——是否需要减值', placeholder: '公司"需要/不需要减值"的结论判断是否有充分依据', content: '', conclusion: '', evidence: '' },
    { title: '减值结论——减值充分性', placeholder: '减值是否充分计提（是否存在隐瞒减值/少提减值风险）', content: '', conclusion: '', evidence: '' },
    { title: '减值结论——不可转回确认', placeholder: '确认公司未对以前年度商誉减值进行转回', content: '', conclusion: '', evidence: '' },
    { title: '对比分析——与上年对比', placeholder: '本年减值结论与上年对比，变化原因是否充分', content: '', conclusion: '', evidence: '' },
    { title: '对比分析——各CGU减值分布', placeholder: '各CGU减值分布是否与业务实况一致（业绩差的CGU减值多）', content: '', conclusion: '', evidence: '' },
    { title: '对比分析——与行业可比公司对比', placeholder: '减值幅度与同行业公司商誉减值情况对比是否合理', content: '', conclusion: '', evidence: '' },
    { title: '对比分析——与过往年度趋势对比', placeholder: '减值趋势是否与公司/行业经营趋势一致', content: '', conclusion: '', evidence: '' },
    { title: '管理层判断——乐观偏差', placeholder: '管理层是否存在系统性乐观偏差（假设偏高/不愿减值）', content: '', conclusion: '', evidence: '' },
    { title: '管理层判断——盈余管理迹象', placeholder: '是否存在利用减值测试进行盈余管理的迹象（大洗澡/平滑利润）', content: '', conclusion: '', evidence: '' },
    { title: '管理层判断——后续期间验证', placeholder: '上年假设是否被本年实际结果验证（回溯测试）', content: '', conclusion: '', evidence: '' },
    { title: '管理层判断——管理层书面声明', placeholder: '是否需要管理层对减值测试关键假设做出书面声明', content: '', conclusion: '', evidence: '' },
    { title: '第三方——评估报告质量', placeholder: '若引用第三方评估报告，报告质量/资质/独立性是否充分', content: '', conclusion: '', evidence: '' },
    { title: '第三方——评估师胜任能力', placeholder: '评估师是否具备相关行业经验和资质（ISA620）', content: '', conclusion: '', evidence: '' },
    { title: '第三方——评估范围充分性', placeholder: '评估报告覆盖的资产范围是否与减值测试需求一致', content: '', conclusion: '', evidence: '' },
    { title: '披露要求——减值损失披露', placeholder: '减值损失是否在利润表和附注中充分披露', content: '', conclusion: '', evidence: '' },
    { title: '披露要求——CGU信息披露', placeholder: 'CGU的可收回金额/关键假设/敏感性分析是否充分披露', content: '', conclusion: '', evidence: '' },
    { title: '披露要求——减值测试方法披露', placeholder: '减值测试采用的方法（DCF/市场法）是否在附注中说明', content: '', conclusion: '', evidence: '' },
    { title: '披露要求——关键假设披露', placeholder: '关键假设（折现率/增长率/预测期）是否在附注中量化披露', content: '', conclusion: '', evidence: '' },
    { title: '披露要求——敏感性分析披露', placeholder: '敏感性分析结果是否在附注中披露', content: '', conclusion: '', evidence: '' },
    { title: '审计程序——充分性评价', placeholder: '本次复核程序是否充分覆盖了减值测试的所有重要方面', content: '', conclusion: '', evidence: '' },
    { title: '审计程序——重要性水平考虑', placeholder: '减值金额相对重要性水平的比例，是否影响审计意见', content: '', conclusion: '', evidence: '' },
    { title: '审计程序——关键审计事项考虑', placeholder: '商誉减值是否构成关键审计事项（KAM），沟通内容是否充分', content: '', conclusion: '', evidence: '' },
    { title: '审计程序——专家参与', placeholder: '是否需要估值专家参与（ISA620），专家工作是否充分', content: '', conclusion: '', evidence: '' },
    { title: '后续事项——资产负债表日后事项', placeholder: '资产负债表日后是否有影响减值结论的新事项', content: '', conclusion: '', evidence: '' },
    { title: '后续事项——持续经营假设', placeholder: '减值测试假设是否与持续经营评估结论一致', content: '', conclusion: '', evidence: '' },
    { title: '后续事项——对其他科目影响', placeholder: '减值结论对递延税项/少数股东权益等其他科目的影响', content: '', conclusion: '', evidence: '' },
    { title: '后续事项——对审计报告影响', placeholder: '减值结论是否影响审计报告类型的判断', content: '', conclusion: '', evidence: '' },
    { title: '综合判断——证据充分性', placeholder: '所获取的审计证据是否足以支持减值结论的判断', content: '', conclusion: '', evidence: '' },
    { title: '综合判断——审计师最终意见', placeholder: '审计师对公司减值测试过程及结论的最终评价意见', content: '', conclusion: '', evidence: '' },
  ]
}

// --- Reactive check items ---
const checkItems = reactive<Record<string, CheckItem[]>>({
  assumptions: createAssumptionItems(),
  model: createModelItems(),
  parameters: createParameterItems(),
  calculation: createCalculationItems(),
  conclusion: createConclusionItems(),
})

// --- Summary / Conclusion area ---
const overallAssessment = ref('')
const hasMajorDeviation = ref(false)
const deviationDescription = ref('')
const overallConclusionText = ref('')

// --- Progress computed ---
type SectionKey = 'assumptions' | 'model' | 'parameters' | 'calculation' | 'conclusion'

function sectionCompletedCount(section: string): number {
  return (checkItems[section] || []).filter((it: CheckItem) => !!it.conclusion).length
}

const sectionProgress = computed(() => {
  const sections: SectionKey[] = ['assumptions', 'model', 'parameters', 'calculation', 'conclusion']
  const result: Record<string, number> = {}
  for (const s of sections) {
    const items = checkItems[s] || []
    result[s] = items.length ? Math.round((sectionCompletedCount(s) / items.length) * 100) : 0
  }
  return result
})

const totalItems = computed(() => {
  return Object.values(checkItems).reduce((sum, arr) => sum + arr.length, 0)
})

const completedCount = computed(() => {
  return Object.values(checkItems).reduce(
    (sum, arr) => sum + arr.filter((it: CheckItem) => !!it.conclusion).length, 0
  )
})

const overallProgressType = computed(() => {
  const pct = totalItems.value ? completedCount.value / totalItems.value : 0
  if (pct >= 1) return 'success'
  if (pct >= 0.5) return 'warning'
  return 'info'
})

function sectionTagType(section: string): 'success' | 'warning' | 'info' {
  const pct = sectionProgress.value[section] || 0
  if (pct >= 100) return 'success'
  if (pct >= 50) return 'warning'
  return 'info'
}

function markDirty() {
  dirty.value = true
}

// --- Load data from allResponses ---
function loadData() {
  const raw = props.allResponses.get(STORAGE_KEY)
  if (!raw) return
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : (raw.remark ? JSON.parse(raw.remark) : raw)
    if (!parsed) return
    // Restore check items per section
    const sections: SectionKey[] = ['assumptions', 'model', 'parameters', 'calculation', 'conclusion']
    for (const s of sections) {
      if (parsed.checkItems?.[s]) {
        const saved = parsed.checkItems[s] as Partial<CheckItem>[]
        for (let i = 0; i < Math.min(saved.length, checkItems[s].length); i++) {
          if (saved[i]?.content) checkItems[s][i].content = saved[i].content!
          if (saved[i]?.conclusion) checkItems[s][i].conclusion = saved[i].conclusion!
          if (saved[i]?.evidence) checkItems[s][i].evidence = saved[i].evidence!
        }
      }
    }
    // Restore summary
    overallAssessment.value = parsed.overallAssessment || ''
    hasMajorDeviation.value = parsed.hasMajorDeviation || false
    deviationDescription.value = parsed.deviationDescription || ''
    overallConclusionText.value = parsed.overallConclusionText || ''
  } catch { /* ignore parse errors */ }
}

watch(() => props.allResponses, () => loadData(), { immediate: true })

// --- Save ---
async function handleSave() {
  saving.value = true
  try {
    const sections: SectionKey[] = ['assumptions', 'model', 'parameters', 'calculation', 'conclusion']
    const payload: Record<string, any> = {
      checkItems: {} as Record<string, Array<{ content: string; conclusion: string; evidence: string }>>,
      overallAssessment: overallAssessment.value,
      hasMajorDeviation: hasMajorDeviation.value,
      deviationDescription: deviationDescription.value,
      overallConclusionText: overallConclusionText.value,
    }
    for (const s of sections) {
      payload.checkItems[s] = checkItems[s].map((it: CheckItem) => ({
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

// --- AI per section ---
const sectionNameMap: Record<string, string> = {
  assumptions: '假设审阅——收入增长/毛利率/折现率/永续增长率/营运资本/CAPEX假设合理性',
  model: '模型检查——DCF模型结构/现金流推导/终值处理/WACC应用/模型完整性',
  parameters: '参数合理性——WACC参数来源验证/收入利润率参数/敏感性分析/参数一致性',
  calculation: '计算验证——PV/终值/WACC/现金流/减值分摊/独立估算数学复核',
  conclusion: '结论评价——减值金额判断/管理层偏差/第三方评估/披露要求/审计程序充分性',
}

async function handleAiSection(sectionKey: string) {
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: `I3-8-review-${sectionKey}`,
      prompt: `商誉减值测试复核——${sectionNameMap[sectionKey] || sectionKey}。请针对本部分各检查项提供参考复核意见和常见问题标注。`,
      context: JSON.stringify({
        sectionItems: checkItems[sectionKey]?.map((it: CheckItem) => it.title),
      }),
    })
    if (res.data?.data?.content) {
      ElMessage.success(`AI已为"${sectionKey === 'assumptions' ? '假设审阅' : sectionKey === 'model' ? '模型检查' : sectionKey === 'parameters' ? '参数合理性' : sectionKey === 'calculation' ? '计算验证' : '结论评价'}"生成参考内容`)
    }
  } catch {
    ElMessage.warning('AI辅助暂不可用，请手动填写')
  }
}

// --- 复核对话 ---
function handleReview() {
  openReviewDialog('I3-8-复核过程')
}
</script>

<style scoped>
.i3-review-process {
  font-size: 13px;
  padding: 16px;
}

/* 蓝色渐变引导区 */
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

/* 琥珀色方法论 */
.methodology-block {
  background: #fffbeb;
  border-left: 4px solid #f59e0b;
  padding: 10px 14px;
  margin-bottom: 14px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.7;
}

.methodology-block p {
  margin: 0;
}

/* Section Header */
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

/* Virtual scroll container */
.review-scroll-area {
  max-height: 600px;
  overflow-y: auto;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 16px;
}

/* Collapse title */
.collapse-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding-right: 8px;
}

.collapse-title-right {
  display: flex;
  align-items: center;
  gap: 6px;
}

/* Check items container */
.check-items-container {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 4px 0;
}

/* Individual check item */
.check-item {
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 10px 12px;
  background: #fafafa;
}

.check-item-header {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: 6px;
}

.check-item-number {
  font-weight: 600;
  color: #6366f1;
  font-size: 12px;
  min-width: 28px;
}

.check-item-title {
  font-size: 13px;
  font-weight: 500;
  color: #374151;
}

.check-item-footer {
  display: flex;
  align-items: center;
  margin-top: 8px;
  gap: 8px;
}

/* Summary card */
.summary-card {
  margin-bottom: 16px;
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
  min-width: 140px;
  line-height: 32px;
}

/* Actions */
.table-actions {
  display: flex;
  gap: 8px;
}

/* El-collapse overrides for tighter look */
:deep(.el-collapse-item__header) {
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
  height: 44px;
}

:deep(.el-collapse-item__content) {
  padding-bottom: 12px;
}

:deep(.el-progress-bar__outer) {
  border-radius: 4px;
}
</style>
