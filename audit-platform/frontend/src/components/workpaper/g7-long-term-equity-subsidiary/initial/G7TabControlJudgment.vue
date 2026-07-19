<!--
  G7TabControlJudgment.vue — G7-7 初始判断决策树（CAS33六要素问卷）

  47行×9列: 序号|判断维度|判断标准(预填)|被投资单位|判断结果(下拉)|判断依据(textarea)|风险标识(下拉)|审计结论|索引
  6 sections: (一)权力 (二)可变回报 (三)权力与回报关系 (四)保护性权利 (五)代理人/委托人 (六)综合判断
  每section标题行: AI按钮 + 复核按钮 右对齐
  底部综合审计结论textarea(AI辅助)

  Spec: .kiro/specs/g7-long-term-equity-subsidiary/ Task 4.1
  Requirements: 2.1, 2.2, 2.3
-->
<template>
  <div class="g7-tab-control-judgment">
    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <div class="methodology-title">CAS33 控制的定义（三要素）</div>
      <ul class="methodology-list">
        <li><strong>权力</strong> — 投资方拥有对被投资方的现时权利，能主导被投资方的相关活动</li>
        <li><strong>可变回报</strong> — 投资方因参与被投资方的相关活动而享有可变回报</li>
        <li><strong>权力与回报的联系</strong> — 投资方有能力运用对被投资方的权力影响其回报金额</li>
      </ul>
      <div class="methodology-note">
        三要素同时满足 → 控制；部分满足需结合实质性权利、代理人判断综合评估
      </div>
    </div>

    <!-- ═══ 蓝色渐变引导区（4步骤，2列grid） ═══ -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step">
          <span class="step-num">Step 1</span>
          <span class="step-desc">逐项填写六要素判断</span>
        </div>
        <div class="guide-step">
          <span class="step-num">Step 2</span>
          <span class="step-desc">确定控制类型结论</span>
        </div>
        <div class="guide-step">
          <span class="step-num">Step 3</span>
          <span class="step-desc">据此选择计量方法</span>
        </div>
        <div class="guide-step">
          <span class="step-num">Step 4</span>
          <span class="step-desc">AI辅助生成综合结论</span>
        </div>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert"
      title="审计目标：验证对被投资方是否构成控制的判断依据充分——按 CAS33 逐项评估权力、可变回报及两者的联系，结合保护性权利与代理人/委托人判断，恰当确定控制类型（控制/共同控制/重大影响/无重大影响）及相应计量方法。" />

    <!-- 工具栏：索引 chip + 行数 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-tag size="small" :type="route.tone">
          {{ route.code || '待判断' }} {{ route.label }}
        </el-tag>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G7-7" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rowCount }} 行</el-tag>
      </div>
    </div>

    <!-- 核心决策链：关系类型 → 合并类型 → 控制权转移日 → 后续底稿 -->
    <el-card shadow="never" class="decision-card">
      <template #header>
        <div class="conclusion-header">
          <span class="conclusion-title">三、初始确认决策结果</span>
          <el-button v-if="!isReadonly" size="small" @click="fillConclusionDraft">生成结论草稿</el-button>
        </div>
      </template>
      <el-form label-width="150px" class="decision-form">
        <div class="decision-grid">
          <el-form-item label="被投资单位">
            <el-input
              v-if="!isReadonly"
              v-model="decision.investeeName"
              placeholder="填写被投资单位全称"
              @change="applyInvesteeName"
            />
            <span v-else>{{ decision.investeeName || '—' }}</span>
          </el-form-item>
          <el-form-item label="投资关系类型" required>
            <el-select
              v-if="!isReadonly"
              v-model="decision.relationshipType"
              placeholder="请选择"
              style="width:100%"
              @change="handleRelationshipChange"
            >
              <el-option value="控制" label="控制" />
              <el-option value="共同控制" label="共同控制" />
              <el-option value="重大影响" label="重大影响" />
              <el-option value="无重大影响" label="无重大影响" />
            </el-select>
            <span v-else>{{ decision.relationshipType || '—' }}</span>
          </el-form-item>
          <el-form-item label="企业合并类型" :required="decision.relationshipType === '控制'">
            <el-select
              v-if="!isReadonly"
              v-model="decision.combinationType"
              :disabled="decision.relationshipType !== '控制'"
              placeholder="请选择"
              style="width:100%"
              @change="persistData"
            >
              <el-option value="同一控制下企业合并" label="同一控制下企业合并" />
              <el-option value="非同一控制下企业合并" label="非同一控制下企业合并" />
              <el-option value="非企业合并（投资设立等）" label="非企业合并（投资设立等）" />
            </el-select>
            <span v-else>{{ decision.combinationType || '—' }}</span>
          </el-form-item>
          <el-form-item label="合并日/购买日">
            <el-date-picker
              v-if="!isReadonly"
              v-model="decision.acquisitionDate"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="控制权转移日"
              style="width:100%"
              :disabled="!isBusinessCombination"
              @change="persistData"
            />
            <span v-else>{{ decision.acquisitionDate || '—' }}</span>
          </el-form-item>
          <el-form-item label="前期关系结论">
            <el-select
              v-if="!isReadonly"
              v-model="decision.priorConclusion"
              clearable
              placeholder="首次投资可不填"
              style="width:100%"
              @change="persistData"
            >
              <el-option value="控制" label="控制" />
              <el-option value="共同控制" label="共同控制" />
              <el-option value="重大影响" label="重大影响" />
              <el-option value="无重大影响" label="无重大影响" />
            </el-select>
            <span v-else>{{ decision.priorConclusion || '首次判断' }}</span>
          </el-form-item>
          <el-form-item label="后续底稿路线">
            <el-tag :type="route.tone">{{ route.code || '—' }} {{ route.label }}</el-tag>
          </el-form-item>
        </div>
        <el-form-item label="控制权转移日依据" :required="isBusinessCombination">
          <el-input
            v-model="decision.acquisitionDateBasis"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
            :disabled="isReadonly || !isBusinessCombination"
            placeholder="说明批准、对价支付、财产权转移、管理层接管等事实及证据索引"
            @change="persistData"
          />
        </el-form-item>
        <el-form-item label="合并类型判断依据" :required="decision.relationshipType === '控制'">
          <el-input
            v-model="decision.combinationBasis"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
            :disabled="isReadonly || decision.relationshipType !== '控制'"
            placeholder="说明是否构成业务、合并前后最终控制方、控制是否非暂时性等"
            @change="persistData"
          />
        </el-form-item>
        <el-form-item
          v-if="decision.priorConclusion && decision.priorConclusion !== decision.relationshipType"
          label="结论变化原因"
          required
        >
          <el-input
            v-model="decision.conclusionChangeReason"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
            :disabled="isReadonly"
            placeholder="说明股权变化、协议变化、事实和情况变化及生效日期"
            @change="persistData"
          />
        </el-form-item>
      </el-form>
    </el-card>

    <!-- ═══ 6 Sections ═══ -->
    <div v-for="section in sections" :key="section.id" class="judgment-section">
      <!-- Section标题行 -->
      <div class="section-header">
        <h4 class="section-title">{{ section.sectionNo }} {{ section.title }}</h4>
        <div class="section-actions">
          <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAiSection(section.id)">
            🤖 AI
          </el-button>
          <el-button size="small" @click="handleReview(section.id)">💬 复核</el-button>
        </div>
      </div>

      <!-- Section表格 9列 -->
      <el-table
        :data="section.rows"
        border
        size="small"
        max-height="400"
        row-key="id"
        class="judgment-table"
      >
        <el-table-column label="序号" width="60" align="center">
          <template #default="{ row }">{{ row.seq }}</template>
        </el-table-column>

        <el-table-column label="判断维度" min-width="130">
          <template #default="{ row }">
            <span class="dimension-text">{{ row.dimension }}</span>
          </template>
        </el-table-column>

        <el-table-column label="判断标准" min-width="200">
          <template #default="{ row }">
            <span class="criterion-text">{{ row.criterion }}</span>
          </template>
        </el-table-column>

        <el-table-column label="被投资单位" min-width="140">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.investeeName"
              size="small"
              placeholder="被投资单位"
              @change="persistData"
            />
            <span v-else>{{ row.investeeName }}</span>
          </template>
        </el-table-column>

        <el-table-column label="判断结果" min-width="120">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.judgmentResult"
              size="small"
              placeholder="请选择"
              clearable
              style="width: 100%"
              @change="persistData"
            >
              <el-option value="是" label="是" />
              <el-option value="否" label="否" />
              <el-option value="不适用" label="不适用" />
            </el-select>
            <el-tag v-else :type="getResultTagType(row.judgmentResult)" size="small">
              {{ row.judgmentResult || '—' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="判断依据" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.judgmentBasis"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              size="small"
              placeholder="填写判断依据"
              @change="persistData"
            />
            <span v-else class="multiline-cell">{{ row.judgmentBasis }}</span>
          </template>
        </el-table-column>

        <el-table-column label="风险标识" min-width="100">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.riskFlag"
              size="small"
              placeholder="风险"
              clearable
              style="width: 100%"
              @change="persistData"
            >
              <el-option value="高" label="高">
                <span style="color:#F56C6C">● 高</span>
              </el-option>
              <el-option value="中" label="中">
                <span style="color:#E6A23C">● 中</span>
              </el-option>
              <el-option value="低" label="低">
                <span style="color:#67C23A">● 低</span>
              </el-option>
              <el-option value="无" label="无">
                <span style="color:#909399">● 无</span>
              </el-option>
            </el-select>
            <el-tag v-else :type="getRiskTagType(row.riskFlag)" size="small">
              {{ row.riskFlag || '—' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="审计结论" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.auditConclusion"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              size="small"
              placeholder="审计结论"
              @change="persistData"
            />
            <span v-else class="multiline-cell">{{ row.auditConclusion }}</span>
          </template>
        </el-table-column>

        <el-table-column label="索引" width="100" align="center">
          <template #default="{ row }">
            <GtIndexChip v-if="row.indexRef" :value="row.indexRef" />
            <el-input
              v-else-if="!isReadonly"
              v-model="row.indexRef"
              size="small"
              placeholder="索引"
              @change="persistData"
            />
            <span v-else>—</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ═══ 审计说明 ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="conclusion-header">
          <span class="conclusion-title">审计说明</span>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：可概述控制判断所执行的程序、依据的证据及评估结果，需关注事项及其影响。"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- ═══ 底部综合审计结论（AI辅助） ═══ -->
    <el-card shadow="never" class="overall-conclusion-card">
      <template #header>
        <div class="conclusion-header">
          <span class="conclusion-title">综合审计结论</span>
          <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAiOverall">
            🤖 AI生成综合结论
          </el-button>
        </div>
      </template>
      <el-input
        v-model="overallConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="根据以上六要素判断结果，综合得出对被投资方的控制类型结论（控制/共同控制/重大影响/无重大影响）"
        @change="saveAuditConclusion"
      />
    </el-card>

    <div v-if="!isReadonly" class="save-actions">
      <el-button type="success" @click="handleSave">保存并校验</el-button>
    </div>

    <!-- 编制提示 -->
    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>CAS33要求同时满足"权力""可变回报""权力与回报的联系"三要素方可认定控制</li>
        <li>权力判断关注：表决权(含潜在)、合同安排、委派管理人员等</li>
        <li>可变回报不限于正回报，担保义务等负回报亦属于可变回报</li>
        <li>代理人仅代为行使权力，不具有控制（需评估决策权范围、可撤换性、报酬安排等）</li>
        <li>保护性权利（如清算权、重大变更否决权）不构成权力</li>
        <li>判断结果选"是"表示满足该要素，"否"表示不满足，"不适用"表示该项目不涉及</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G7TabControlJudgment — G7-7 初始判断决策树（CAS33六要素问卷）
 *
 * 47行×9列 六section问卷式决策树
 * 方法论上下文(琥珀色): 控制三要素定义
 * 蓝色渐变引导区(4步骤)
 * 每section标题行: AI按钮+复核按钮右对齐
 * 底部综合审计结论textarea(AI辅助)
 *
 * Spec: .kiro/specs/g7-long-term-equity-subsidiary/
 * Requirements: 2.1, 2.2, 2.3
 */
import { ref, reactive, computed, inject, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import { useG7SubFormData } from '../../composables/useG7SubFormData'
import {
  buildG7ControlConclusion,
  deriveG7ControlRoute,
  validateG7ControlDecision,
  type CombinationType,
  type G7ControlDecision,
  type RelationshipType,
} from '../../composables/g7ControlJudgmentModel'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const isReadonly = computed(() => props.readonly ?? false)

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// ─── 数据模型 ────────────────────────────────────────────────────────────────

interface G7ControlRow {
  id: string
  seq: number
  dimension: string
  criterion: string
  investeeName: string
  judgmentResult: '是' | '否' | '不适用' | ''
  judgmentBasis: string
  riskFlag: '高' | '中' | '低' | '无' | ''
  auditConclusion: string
  indexRef: string
}

interface G7ControlSection {
  id: string
  sectionNo: string
  title: string
  rows: G7ControlRow[]
}

interface G7ControlJudgmentData {
  sections: G7ControlSection[]
  overallConclusion: string
  decision: G7ControlDecision
}

// ─── 方法论预填数据（CAS33六要素） ──────────────────────────────────────────

const SECTION_DEFINITIONS: Array<{
  id: string
  sectionNo: string
  title: string
  rows: Array<{ dimension: string; criterion: string }>
}> = [
  {
    id: 'power',
    sectionNo: '(一)',
    title: '权力',
    rows: [
      { dimension: '表决权', criterion: '投资方是否持有被投资方超过半数的表决权' },
      { dimension: '潜在表决权', criterion: '是否存在可转换工具、期权等潜在表决权' },
      { dimension: '合同安排', criterion: '是否通过合同安排主导被投资方相关活动' },
      { dimension: '委派管理人员', criterion: '是否有能力委派或批准被投资方关键管理人员' },
      { dimension: '主导相关活动', criterion: '是否有能力主导被投资方经营和财务决策' },
      { dimension: '持有多数表决权但非控制', criterion: '虽持有多数表决权，是否因其他安排不构成控制' },
      { dimension: '持有少数表决权的权力', criterion: '虽持有少数表决权，是否通过其他安排拥有权力' },
      { dimension: '结构化主体', criterion: '是否通过设计目的/活动范围/风险暴露获得对结构化主体的权力' },
    ],
  },
  {
    id: 'variableReturns',
    sectionNo: '(二)',
    title: '可变回报',
    rows: [
      { dimension: '股利分配', criterion: '投资方是否因参与被投资方活动而享有股利分配等正回报' },
      { dimension: '资产增值', criterion: '投资方是否因被投资方净资产增值而获得回报' },
      { dimension: '协同效应', criterion: '投资方是否因与被投资方的交易获得协同效应收益' },
      { dimension: '规模经济', criterion: '投资方是否因被投资方资源共享获得规模经济利益' },
      { dimension: '负回报/风险敞口', criterion: '投资方是否承担被投资方亏损、担保义务等负回报风险' },
      { dimension: '管理费/服务费', criterion: '投资方是否因管理被投资方获取管理费或服务费收入' },
      { dimension: '回报的可变性', criterion: '投资方回报是否随被投资方业绩变动而变动' },
      { dimension: '税收利益', criterion: '投资方是否通过被投资方获得税收优惠或递延利益' },
    ],
  },
  {
    id: 'powerReturnLink',
    sectionNo: '(三)',
    title: '权力与回报的联系',
    rows: [
      { dimension: '权力影响回报', criterion: '投资方是否有能力运用权力影响其从被投资方获取的回报金额' },
      { dimension: '自身利益最大化', criterion: '投资方运用权力时是否为了自身利益最大化' },
      { dimension: '决策影响路径', criterion: '投资方的决策权是否直接影响被投资方产生回报的活动' },
      { dimension: '利益与风险对称', criterion: '投资方享有的回报与其承担的风险是否对称' },
      { dimension: '回报依赖性', criterion: '投资方的回报是否实质依赖于被投资方的经营业绩' },
      { dimension: '权力行使意愿', criterion: '投资方是否有意愿和动机运用权力影响回报' },
      { dimension: '替代回报来源', criterion: '投资方是否存在不依赖权力即可获取的固定回报（不构成联系）' },
      { dimension: '控制权溢价', criterion: '投资方是否因控制地位获得超出比例份额的回报' },
    ],
  },
  {
    id: 'protectiveRights',
    sectionNo: '(四)',
    title: '保护性权利',
    rows: [
      { dimension: '清算权/解散权', criterion: '少数股东是否仅持有清算或解散被投资方的权利' },
      { dimension: '章程修改否决权', criterion: '少数股东是否仅持有对章程重大修改的否决权' },
      { dimension: '超常规交易否决权', criterion: '少数股东是否仅持有对超出正常经营范围重大交易的否决权' },
      { dimension: '利率/信用保护', criterion: '债权人是否仅持有限制债务人增加风险的保护性权利' },
      { dimension: '保护性权利不构成权力', criterion: '上述保护性权利是否不构成对被投资方相关活动的主导权力' },
      { dimension: '保护性权利独立性', criterion: '保护性权利的行使是否不需要其持有人主导被投资方的相关活动' },
      { dimension: '保护性与实质性界限', criterion: '所评估的权利是否已超出保护性权利范畴（构成实质性权利）' },
      { dimension: '是否需排除保护性权利', criterion: '权力评估中是否已正确排除保护性权利的影响' },
    ],
  },
  {
    id: 'agentPrincipal',
    sectionNo: '(五)',
    title: '代理人/委托人',
    rows: [
      { dimension: '决策权范围', criterion: '代为行使决策权的一方其决策权的范围是否受限' },
      { dimension: '可撤换性', criterion: '其他方是否享有无条件罢免决策者的权利' },
      { dimension: '报酬安排', criterion: '决策者的报酬是否与市场公允水平一致（非超额报酬）' },
      { dimension: '其他利益敞口', criterion: '决策者是否因持有被投资方的其他权益导致利益敞口过大' },
      { dimension: '综合判断-委托人', criterion: '综合上述因素，决策者是否为委托人（为自身利益行使权力）' },
      { dimension: '综合判断-代理人', criterion: '综合上述因素，决策者是否仅为代理人（代他人行使权力）' },
      { dimension: '多重委托人', criterion: '是否存在多个委托人且需评估谁拥有实际控制' },
      { dimension: '代理关系对控制的影响', criterion: '代理人判断结果是否改变了控制结论' },
    ],
  },
  {
    id: 'overallJudgment',
    sectionNo: '(六)',
    title: '分类与控制权转移时点判断',
    rows: [
      { dimension: '控制三要素同时满足', criterion: '权力+可变回报+联系三要素是否同时满足→控制' },
      { dimension: '共同控制条件满足', criterion: '合同约定相关活动的决策是否必须经分享控制权的参与方一致同意' },
      { dimension: '重大影响条件满足', criterion: '是否具有董事席位、参与政策制定、重大交易或技术依赖等重大影响证据' },
      { dimension: '被购买方构成业务', criterion: '取得的活动和资产组合是否至少包含投入及实质性加工处理过程并能够产出' },
      { dimension: '同一最终控制方', criterion: '合并前后是否受同一方或相同多方最终控制，且该控制并非暂时性' },
      { dimension: '控制权已实际转移', criterion: '批准、对价支付、财产权交接、经营决策及财务政策控制等条件是否实质满足' },
      { dimension: '前期结论变化已说明', criterion: '与前期关系分类或控制结论不一致时，变化原因及生效时点是否已有充分证据' },
    ],
  },
]

// ─── 状态 ────────────────────────────────────────────────────────────────────

const sections = reactive<G7ControlSection[]>([])
const overallConclusion = ref('')
const rowCount = computed(() => sections.reduce((n, s) => n + s.rows.length, 0))
const decision = reactive<G7ControlDecision>({
  investeeName: '',
  relationshipType: '',
  combinationType: '',
  combinationBasis: '',
  acquisitionDate: '',
  acquisitionDateBasis: '',
  priorConclusion: '',
  conclusionChangeReason: '',
})
const route = computed(() => deriveG7ControlRoute(decision))
const isBusinessCombination = computed(() =>
  decision.combinationType === '同一控制下企业合并'
  || decision.combinationType === '非同一控制下企业合并',
)

// ─── 明细/审计说明/结论持久化 ───
const auditFormData = useG7SubFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const DATA_KEY = 'G7-7-control-judgment-data'
const NOTE_KEY = 'G7-7-control-judgment-audit-note'
const CONCLUSION_KEY = 'G7-7-control-judgment-audit-conclusion'
const auditNote = ref('')

function saveAuditNote(val: string): void {
  if (isReadonly.value) return
  auditNote.value = val
  auditFormData.debouncedSave(NOTE_KEY, { remark: val, conclusion: null })
}
function saveAuditConclusion(val: string): void {
  if (isReadonly.value) return
  overallConclusion.value = val
  auditFormData.debouncedSave(CONCLUSION_KEY, { remark: val, conclusion: null })
  persistData()
}

function persistData(): void {
  if (isReadonly.value) return
  auditFormData.debouncedSave(DATA_KEY, {
    conclusion: JSON.stringify(getData()),
    remark: null,
  })
}

function applyInvesteeName(): void {
  for (const section of sections) {
    for (const row of section.rows) row.investeeName = decision.investeeName
  }
  persistData()
}

function handleRelationshipChange(value: RelationshipType): void {
  if (value !== '控制') {
    decision.combinationType = '不适用'
    decision.combinationBasis = ''
    decision.acquisitionDate = ''
    decision.acquisitionDateBasis = ''
  } else if (decision.combinationType === '不适用') {
    decision.combinationType = '' as CombinationType
  }
  persistData()
}

function fillConclusionDraft(): void {
  const errors = validateG7ControlDecision(decision)
  if (errors.length > 0) {
    ElMessage.warning(errors[0])
    return
  }
  overallConclusion.value = buildG7ControlConclusion(decision)
  saveAuditConclusion(overallConclusion.value)
  ElMessage.success('已按决策结果生成结论草稿')
}

async function handleSave(): Promise<void> {
  const errors = validateG7ControlDecision(decision)
  if (errors.length > 0) {
    ElMessage.error(errors.join('；'))
    return
  }
  const unansweredKeyRows = sections
    .find(s => s.id === 'overallJudgment')
    ?.rows.filter(r => !r.judgmentResult).map(r => r.dimension) ?? []
  if (unansweredKeyRows.length > 0) {
    ElMessage.error(`综合判断尚未完成：${unansweredKeyRows.join('、')}`)
    return
  }
  await auditFormData.saveImmediate(DATA_KEY, {
    conclusion: JSON.stringify(getData()),
    remark: null,
  })
  await auditFormData.saveImmediate(CONCLUSION_KEY, {
    remark: overallConclusion.value,
    conclusion: null,
  })
  ElMessage.success('G7-7 初始判断已保存')
}

// ─── 初始化 ──────────────────────────────────────────────────────────────────

function initSections(): void {
  sections.length = 0
  let globalSeq = 1

  for (const def of SECTION_DEFINITIONS) {
    const sectionRows: G7ControlRow[] = def.rows.map(r => ({
      id: crypto.randomUUID(),
      seq: globalSeq++,
      dimension: r.dimension,
      criterion: r.criterion,
      investeeName: '',
      judgmentResult: '' as const,
      judgmentBasis: '',
      riskFlag: '' as const,
      auditConclusion: '',
      indexRef: '',
    }))

    sections.push({
      id: def.id,
      sectionNo: def.sectionNo,
      title: def.title,
      rows: sectionRows,
    })
  }
}

// ─── 从 htmlData 加载已有数据 ────────────────────────────────────────────────

function loadFromHtmlData(data: Record<string, any> | null): void {
  if (!data) {
    initSections()
    return
  }

  const judgmentData = data.controlJudgment || data
  const savedSections = judgmentData?.sections

  if (Array.isArray(savedSections) && savedSections.length > 0) {
    sections.length = 0
    for (const sec of savedSections) {
      const rows: G7ControlRow[] = (sec.rows || []).map((r: any, idx: number) => ({
        id: r.id || crypto.randomUUID(),
        seq: r.seq || idx + 1,
        dimension: r.dimension || '',
        criterion: r.criterion || '',
        investeeName: r.investeeName || '',
        judgmentResult: r.judgmentResult || '',
        judgmentBasis: r.judgmentBasis || '',
        riskFlag: r.riskFlag || '',
        auditConclusion: r.auditConclusion || '',
        indexRef: r.indexRef || '',
      }))
      sections.push({
        id: sec.id,
        sectionNo: sec.sectionNo,
        title: sec.title,
        rows,
      })
    }
    overallConclusion.value = judgmentData?.overallConclusion || ''
    if (judgmentData?.decision) {
      Object.assign(decision, {
        investeeName: judgmentData.decision.investeeName ?? '',
        relationshipType: judgmentData.decision.relationshipType ?? '',
        combinationType: judgmentData.decision.combinationType ?? '',
        combinationBasis: judgmentData.decision.combinationBasis ?? '',
        acquisitionDate: judgmentData.decision.acquisitionDate ?? '',
        acquisitionDateBasis: judgmentData.decision.acquisitionDateBasis ?? '',
        priorConclusion: judgmentData.decision.priorConclusion ?? '',
        conclusionChangeReason: judgmentData.decision.conclusionChangeReason ?? '',
      })
    } else {
      decision.investeeName = rowsFirstInvesteeName()
    }
  } else {
    initSections()
  }
}

function rowsFirstInvesteeName(): string {
  for (const section of sections) {
    const name = section.rows.find(r => r.investeeName.trim())?.investeeName
    if (name) return name
  }
  return ''
}

// ─── UI辅助函数 ──────────────────────────────────────────────────────────────

function getResultTagType(result: string): 'success' | 'danger' | 'info' | 'warning' {
  if (result === '是') return 'success'
  if (result === '否') return 'danger'
  if (result === '不适用') return 'info'
  return 'warning'
}

function getRiskTagType(risk: string): 'danger' | 'warning' | 'success' | 'info' {
  if (risk === '高') return 'danger'
  if (risk === '中') return 'warning'
  if (risk === '低') return 'success'
  return 'info'
}

// ─── AI辅助 ──────────────────────────────────────────────────────────────────

async function handleAiSection(sectionId: string): Promise<void> {
  if (isReadonly.value) return
  const section = sections.find(s => s.id === sectionId)
  if (!section) return

  ElMessage.info('正在生成AI辅助内容...')
  try {
    const res = await (await import('@/utils/http')).default.post(
      `/api/workpapers/${props.wpId}/g7-sub/ai/control-judgment-conclusion`,
      {
        existingContent: section.rows.map(r => r.auditConclusion).filter(Boolean).join('\n'),
        relatedContext: { sectionId, sectionTitle: `${section.sectionNo} ${section.title}`, rows: section.rows },
      },
    )
    const text = res?.data?.data?.conclusion ?? res?.data?.conclusion ?? res?.data?.text ?? ''
    if (text) {
      // 将AI生成内容填入该section各行的审计结论（仅填充空白行）
      for (const row of section.rows) {
        if (!row.auditConclusion) {
          row.auditConclusion = text
          break // AI只填1行作为参考
        }
      }
      persistData()
      ElMessage.success('AI辅助内容已生成')
    }
  } catch {
    ElMessage.warning('AI辅助暂未连接，请手动填写')
  }
}

async function handleAiOverall(): Promise<void> {
  if (isReadonly.value) return

  ElMessage.info('正在生成AI综合结论...')
  try {
    const res = await (await import('@/utils/http')).default.post(
      `/api/workpapers/${props.wpId}/g7-sub/ai/control-judgment-conclusion`,
      {
        existingContent: overallConclusion.value,
        relatedContext: {
          type: 'overall',
          decision: { ...decision },
          route: route.value,
          sections: sections.map(s => ({
            id: s.id,
            title: `${s.sectionNo} ${s.title}`,
            rows: s.rows.map(r => ({ dimension: r.dimension, judgmentResult: r.judgmentResult, judgmentBasis: r.judgmentBasis })),
          })),
        },
      },
    )
    const text = res?.data?.data?.conclusion ?? res?.data?.conclusion ?? res?.data?.text ?? ''
    if (text) {
      overallConclusion.value = text
      auditFormData.debouncedSave(CONCLUSION_KEY, { remark: text, conclusion: null })
      persistData()
      ElMessage.success('AI综合结论已生成')
      return
    }
  } catch {
    // AI后端未连接，降级为本地逻辑生成草案
  }

  const errors = validateG7ControlDecision(decision)
  if (errors.length > 0) {
    ElMessage.warning(`AI不可用；生成本地结论前请完善：${errors[0]}`)
    return
  }
  overallConclusion.value = buildG7ControlConclusion(decision)
  auditFormData.debouncedSave(CONCLUSION_KEY, { remark: overallConclusion.value, conclusion: null })
  persistData()
  ElMessage.success('已生成本地结论草稿')
}

// ─── 复核对话 ────────────────────────────────────────────────────────────────

function handleReview(sectionId: string): void {
  openReviewDialog(`G7-7-${sectionId}`)
}

// ─── 数据导出（供父组件保存） ────────────────────────────────────────────────

function getData(): G7ControlJudgmentData {
  return {
    sections: sections.map(s => ({
      id: s.id,
      sectionNo: s.sectionNo,
      title: s.title,
      rows: s.rows.map(r => ({ ...r })),
    })),
    overallConclusion: overallConclusion.value,
    decision: { ...decision },
  }
}

defineExpose({ getData, loadFromHtmlData })

// ─── 生命周期 ────────────────────────────────────────────────────────────────

onMounted(async () => {
  // 先同步渲染模板/传入数据，避免网络加载期间页面为空
  loadFromHtmlData(props.htmlData)
  await auditFormData.load()
  const savedRaw = auditFormData.data.value.get(DATA_KEY)?.conclusion
  let savedData: Record<string, any> | null = null
  if (typeof savedRaw === 'string' && savedRaw.trim()) {
    try {
      savedData = JSON.parse(savedRaw)
    } catch {
      savedData = null
    }
  }
  if (savedData) loadFromHtmlData(savedData)
  const n = auditFormData.data.value.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = auditFormData.data.value.get(CONCLUSION_KEY)
  if (c?.remark) overallConclusion.value = c.remark
})

watch(() => props.htmlData, (newData) => {
  if (newData && sections.length === 0) {
    loadFromHtmlData(newData)
  }
})
</script>

<style scoped>
.g7-tab-control-judgment { padding: 12px; font-size: var(--wp-font-size, 13px); }

/* ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ */
.methodology-context {
  margin-bottom: 16px;
  padding: 14px 16px;
  background: #fffbeb;
  border-left: 4px solid #f59e0b;
  border-radius: 4px;
}
.methodology-title {
  font-weight: 600;
  font-size: 14px;
  color: #92400e;
  margin-bottom: 8px;
}
.methodology-list {
  margin: 0; padding-left: 18px; line-height: 1.8;
  color: #78350f;
}
.methodology-list li { margin-bottom: 2px; }
.methodology-list strong { color: #b45309; }
.methodology-note {
  margin-top: 8px;
  font-size: 12px;
  color: #a16207;
  font-style: italic;
}

/* ═══ 蓝色渐变引导区 ═══ */
.guide-area {
  margin-bottom: 16px;
  padding: 14px 18px;
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  border-radius: 8px;
  border: 1px solid #bfdbfe;
}
.guide-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.guide-step {
  display: flex; align-items: center; gap: 8px;
}
.step-num {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 52px; height: 24px;
  background: #3b82f6; color: #fff;
  border-radius: 12px; font-size: 11px; font-weight: 600;
}
.step-desc {
  font-size: var(--wp-font-size, 13px); color: #1e40af; font-weight: 500;
}

/* ═══ Section ═══ */
.judgment-section {
  margin-bottom: 20px;
}
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  padding: 8px 12px;
  background: #f8fafc;
  border-radius: 4px;
  border-bottom: 2px solid #e2e8f0;
}
.section-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
}
.section-actions {
  display: flex; gap: 6px; align-items: center;
}

/* ═══ 表格 ═══ */
.judgment-table { font-size: var(--wp-font-size, 13px); }
.dimension-text { font-weight: 500; color: #334155; }
.criterion-text { font-size: 12px; color: #64748b; line-height: 1.5; }
.multiline-cell { white-space: pre-wrap; word-break: break-all; font-size: 12px; line-height: 1.4; }

/* ═══ 审计目标 / 工具栏 ═══ */
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin: 8px 0 16px; gap: 8px; flex-wrap: wrap; }
.tab-toolbar .toolbar-left { display: flex; align-items: center; gap: 8px; }
.tab-toolbar .toolbar-right { display: flex; align-items: center; gap: 8px; }
.tab-toolbar .chip-wrap { display: inline-flex; }

/* ═══ 初始确认决策链 ═══ */
.decision-card { margin-bottom: 18px; border-color: #bfdbfe; }
.decision-card :deep(.el-card__header) { background: #eff6ff; padding: 10px 16px; }
.decision-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 18px;
}
.decision-form :deep(.el-form-item) { margin-bottom: 14px; }
.save-actions { margin-top: 16px; display: flex; justify-content: flex-end; }

/* ═══ 底部综合结论 ═══ */
.audit-note-card { margin-top: 20px; }
.overall-conclusion-card { margin-top: 20px; }
.conclusion-header {
  display: flex; justify-content: space-between; align-items: center;
}
.conclusion-title { font-weight: 600; font-size: 14px; color: #1e293b; }

/* ═══ 编制提示 ═══ */
.prep-hint { margin-top: 16px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; font-weight: 500; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; line-height: 1.8; }

@media (max-width: 900px) {
  .decision-grid { grid-template-columns: 1fr; }
}
</style>
