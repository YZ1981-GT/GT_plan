<template>
  <div class="h1-tab-policy-check">
    <!-- 一、审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert">
      <template #title>
        <div class="obj-title">一、审计目标</div>
      </template>
      <ol class="obj-list">
        <li>资产负债表中记录的固定资产是存在的，并均已记录至恰当的账户中。</li>
        <li>所有应当记录的固定资产均已记录，所有应当包括在财务报表中的相关披露均已包括。</li>
        <li>固定资产以恰当的金额包括在财务报表中，与之相关的计价或分摊调整已恰当记录，相关披露正确。</li>
      </ol>
    </el-alert>

    <div class="tab-toolbar">
      <GtIndexChip value="wp:H1-5" :context-project-id="projectId" />
      <GtIndexChip value="wp:H1-2" :context-project-id="projectId" />
      <GtIndexChip value="wp:H1-12" :context-project-id="projectId" />
      <GtIndexChip v-if="state.hasAnyChange.value" value="wp:S3-2" :context-project-id="projectId" />
      <el-tag size="small" :type="state.completenessOk.value ? 'success' : 'warning'">
        完成度 {{ state.completionProgress.value }}%
      </el-tag>
      <el-button v-if="!isReadonly" size="small" :loading="syncLoading" @click="handleSyncDetail">从 H1-2 带入</el-button>
      <el-button v-if="!isReadonly" size="small" :loading="priorLoading" @click="handlePriorYear">带入上年估计</el-button>
      <el-button v-if="!isReadonly && state.h12ChangeHint.value" size="small" @click="handleSyncH12">从 H1-12 带入变更</el-button>
      <el-dropdown v-if="!isReadonly" trigger="click" @command="handleIndustryTpl">
        <el-button size="small">行业模板 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item v-for="t in state.INDUSTRY_TEMPLATES" :key="t.id" :command="t.id">{{ t.label }}</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-button v-if="!isReadonly" size="small" @click="handleSuggestJudgments">AI建议同业判断</el-button>
      <el-dropdown trigger="click" @command="handleImportExport">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="export-json">导出 JSON 数据包</el-dropdown-item>
            <el-dropdown-item command="import-json" :disabled="isReadonly">导入 JSON 数据包</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <input ref="jsonInputRef" type="file" accept=".json,application/json" style="display:none" @change="onJsonSelected" />
      <el-button size="small" type="default" link @click="handleReview('H1-5')">💬 复核</el-button>
    </div>

    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> CAS4六段落逐项评价</div>
        <div class="guide-step"><span class="step-num">②</span> 表A：H1-2带入参数 + 五维判断</div>
        <div class="guide-step"><span class="step-num">③</span> 表B：同业对标（偏离须备注）</div>
        <div class="guide-step"><span class="step-num">④</span> 表C：变更原估计 + 影响金额 → 说明/结论</div>
      </div>
    </div>

    <!-- 完成度闸门 -->
    <el-card shadow="never" class="gate-card" :class="{ 'gate-ok': state.completenessOk.value }">
      <template #header>
        <div class="section-title">
          <span>完成度闸门</span>
          <el-tag :type="state.completenessOk.value ? 'success' : 'danger'" size="small">
            {{ state.completenessOk.value ? '可关闭本检查项' : '未达标，不可勾选已完成' }}
          </el-tag>
        </div>
      </template>
      <el-progress :percentage="state.completionProgress.value" :stroke-width="10" style="margin-bottom:10px" />
      <div class="gate-list">
        <div v-for="c in state.completeness.value" :key="c.id" class="gate-item" :class="{ ok: c.ok }">
          <span>{{ c.ok ? '✓' : '○' }} {{ c.label }}</span>
          <span v-if="!c.ok" class="gate-hint">{{ c.hint }}</span>
        </div>
      </div>
    </el-card>

    <!-- 交叉校验 -->
    <el-alert
      v-for="issue in state.crossCheckIssues.value"
      :key="issue.id"
      :type="issue.severity === 'error' ? 'error' : 'warning'"
      :closable="false"
      show-icon
      :title="issue.message"
      class="cross-alert"
    />

    <el-alert
      v-if="state.hasAnyChange.value"
      type="warning"
      :closable="false"
      show-icon
      class="cross-alert"
    >
      <template #title>
        本期存在会计估计变更：请同步
        <GtIndexChip value="wp:S3-2" :context-project-id="projectId" />
        估计变更程序，并勾稽
        <GtIndexChip value="wp:H1" :context-project-id="projectId" />
        附注披露（上市/国企披露页）。
      </template>
    </el-alert>

    <el-alert
      v-if="state.h12ChangeHint.value"
      type="info"
      :closable="false"
      show-icon
      :title="state.h12ChangeHint.value"
      class="cross-alert"
    />

    <!-- CAS4 六段落 -->
    <div class="section-label">二、审计过程 — CAS4 政策段落评价</div>
    <template v-for="(section, idx) in state.sections.value" :key="section.key">
      <el-card
        shadow="never"
        class="policy-card"
        :class="{ 'policy-card-done': isSectionDone(section) }"
      >
        <template #header>
          <div class="section-title">
            <span>{{ section.title }}</span>
            <div class="title-actions">
              <el-tag v-if="section.conclusion" :type="getConclusionType(section.conclusion)" size="small">
                {{ section.conclusion }}
              </el-tag>
              <el-button
                v-if="!isReadonly"
                size="small"
                type="primary"
                link
                :loading="aiLoadingKey === section.key"
                @click="handleAiEval(section)"
              >
                <el-icon><MagicStick /></el-icon> AI评价
              </el-button>
              <el-button size="small" type="default" link @click="handleReview(`H1-5-${section.key}`)">💬</el-button>
            </div>
          </div>
        </template>

        <details class="cas-reference">
          <summary>
            <el-icon><InfoFilled /></el-icon>
            准则条款（点击展开）
          </summary>
          <p>{{ section.description }}</p>
        </details>

        <div class="field-group">
          <label>被审计单位实际政策：</label>
          <el-input
            v-model="section.actualPolicy"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 5 }"
            :disabled="isReadonly"
            placeholder="描述被审计单位就此方面的实际会计政策..."
            @blur="onSectionBlur(idx)"
          />
        </div>

        <div class="field-group">
          <label>审计师评价：</label>
          <el-input
            v-model="section.evaluation"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 5 }"
            :disabled="isReadonly"
            placeholder="评价该政策是否符合CAS4要求..."
            @blur="onSectionBlur(idx)"
          />
        </div>

        <div class="field-group conclusion-group">
          <label>结论：</label>
          <el-radio-group v-model="section.conclusion" :disabled="isReadonly" @change="onSectionBlur(idx)">
            <el-radio value="Y">Y 符合</el-radio>
            <el-radio value="N">N 不符合</el-radio>
            <el-radio value="NA">NA 不适用</el-radio>
          </el-radio-group>
        </div>

        <div v-if="section.conclusion === 'N'" class="field-group n-explanation">
          <label>不符合原因及影响：</label>
          <el-input
            v-model="section.explanationIfN"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
            :disabled="isReadonly"
            placeholder="必须说明不符合的具体原因和对审计的影响..."
            @blur="onSectionBlur(idx)"
          />
          <el-alert v-if="!section.explanationIfN" type="error" :closable="false" show-icon>
            结论为N时必须填写原因说明
          </el-alert>
        </div>
      </el-card>
    </template>

    <!-- 表A -->
    <el-card shadow="never" class="params-card">
      <template #header>
        <div class="section-title">
          <span>表A：被审计单位的固定资产折旧政策</span>
          <div class="title-actions">
            <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddParam">+ 新增分类</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="state.depParams.value"
        border
        stripe
        size="small"
        class="wide-table"
        :row-class-name="depRowClass"
      >
        <el-table-column type="index" label="序" width="44" align="center" />
        <el-table-column prop="category" label="类别" min-width="100" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.category" size="small" @change="persistParams" />
            <span v-else>{{ row.category }}</span>
            <div v-if="row.detailCount" class="peer-hint">H1-2 {{ row.detailCount }}笔</div>
          </template>
        </el-table-column>
        <el-table-column label="折旧年限" width="140" align="center">
          <template #default="{ row }">
            <div v-if="!isReadonly" class="life-range">
              <el-input-number v-model="row.usefulLifeMin" :controls="false" size="small" :min="0" @change="persistParams" />
              <span>–</span>
              <el-input-number v-model="row.usefulLifeMax" :controls="false" size="small" :min="0" @change="persistParams" />
            </div>
            <span v-else>{{ formatLife(row) }}</span>
            <div v-if="state.peerLifeHints.value[row.category]" class="peer-hint">
              同业 {{ state.peerLifeHints.value[row.category] }}
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="depMethod" label="折旧方法" width="120">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.depMethod" size="small" @change="persistParams">
              <el-option v-for="m in state.DEP_METHOD_OPTIONS" :key="m" :label="m" :value="m" />
            </el-select>
            <span v-else>{{ row.depMethod }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="salvageRate" label="残值率%" width="80" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              v-model="row.salvageRate"
              size="small"
              @change="persistParams"
            />
            <span v-else>{{ row.salvageRate }}%</span>
          </template>
        </el-table-column>
        <el-table-column label="符合准则" width="78" align="center">
          <template #header>
            <el-tooltip content="是否符合实际经营情况和会计准则的要求" placement="top"><span>符合准则</span></el-tooltip>
          </template>
          <template #default="{ row }">
            <YnSelect v-model="row.meetsStandards" :readonly="isReadonly" @change="() => onJudgeChange(row.rowId, 'meetsStandards', row.meetsStandards)" />
          </template>
        </el-table-column>
        <el-table-column label="经济利益" width="78" align="center">
          <template #header>
            <el-tooltip content="是否与相关资产所包含的经济利益预期实现方式相一致" placement="top"><span>经济利益</span></el-tooltip>
          </template>
          <template #default="{ row }">
            <YnSelect v-model="row.matchesEconomicBenefit" :readonly="isReadonly" @change="() => onJudgeChange(row.rowId, 'matchesEconomicBenefit', row.matchesEconomicBenefit)" />
          </template>
        </el-table-column>
        <el-table-column label="同业合理" width="78" align="center">
          <template #default="{ row }">
            <YnSelect v-model="row.reasonableVsPeers" :readonly="isReadonly" @change="() => onJudgeChange(row.rowId, 'reasonableVsPeers', row.reasonableVsPeers)" />
          </template>
        </el-table-column>
        <el-table-column label="存在变更" width="78" align="center">
          <template #default="{ row }">
            <YnSelect v-model="row.hasChange" :readonly="isReadonly" @change="() => onJudgeChange(row.rowId, 'hasChange', row.hasChange)" />
          </template>
        </el-table-column>
        <el-table-column label="变更合理" width="78" align="center">
          <template #default="{ row }">
            <YnSelect
              v-if="row.hasChange === 'Y'"
              v-model="row.changeReasonable"
              :readonly="isReadonly"
              @change="() => onJudgeChange(row.rowId, 'changeReasonable', row.changeReasonable)"
            />
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="isReasonable" label="综合合理" width="78" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.isReasonable" size="small" style="width:56px" @change="persistParams">
              <el-option label="Y" value="Y" />
              <el-option label="N" value="N" />
            </el-select>
            <el-tag v-else-if="row.isReasonable" :type="row.isReasonable === 'Y' ? 'success' : 'danger'" size="small">
              {{ row.isReasonable }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.remark"
              size="small"
              :class="{ 'need-remark': needsDevRemark(row.category) }"
              :placeholder="needsDevRemark(row.category) ? '同业偏离须说明' : ''"
              @change="persistParams"
            />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="52" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="state.removeDepParam(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 表B -->
    <el-card shadow="never" class="params-card">
      <template #header>
        <div class="section-title">
          <span>表B：同行业其他公司的固定资产折旧政策</span>
          <el-tag v-if="state.peerDeviations.value.length" size="small" type="danger">
            偏离 {{ state.peerDeviations.value.length }} 项
          </el-tag>
        </div>
      </template>

      <div class="peer-meta-grid">
        <div v-for="peer in state.peerCompanies.value" :key="peer.peerId" class="peer-meta">
          <el-input
            v-model="peer.name"
            size="small"
            :disabled="isReadonly"
            placeholder="同行业公司名称"
            @change="state.persistPeers()"
          >
            <template #prepend>公司</template>
          </el-input>
          <el-input
            v-model="peer.source"
            size="small"
            :disabled="isReadonly"
            placeholder="信息来源（如：2024年报附注）"
            :class="{ 'need-remark': peer.name && !peer.source }"
            @change="state.persistPeers()"
          >
            <template #prepend>来源</template>
          </el-input>
        </div>
      </div>

      <el-table :data="state.peerPolicies.value" border stripe size="small" class="wide-table peer-table">
        <el-table-column prop="category" label="类别" min-width="100" fixed />
        <el-table-column
          v-for="peer in state.peerCompanies.value"
          :key="peer.peerId"
          :label="peer.name || '同行业公司'"
          align="center"
        >
          <el-table-column label="年限" width="88">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                :model-value="cellOf(row, peer.peerId).usefulLife"
                size="small"
                placeholder="如20-40"
                @update:model-value="(v: string) => state.updatePeerCell(row.category, peer.peerId, 'usefulLife', v)"
              />
              <span v-else>{{ cellOf(row, peer.peerId).usefulLife }}</span>
            </template>
          </el-table-column>
          <el-table-column label="方法" width="100">
            <template #default="{ row }">
              <el-select
                v-if="!isReadonly"
                :model-value="cellOf(row, peer.peerId).depMethod || undefined"
                size="small"
                clearable
                placeholder="方法"
                @change="(v: string) => state.updatePeerCell(row.category, peer.peerId, 'depMethod', v || '')"
              >
                <el-option v-for="m in state.DEP_METHOD_OPTIONS" :key="m" :label="m" :value="m" />
              </el-select>
              <span v-else>{{ cellOf(row, peer.peerId).depMethod }}</span>
            </template>
          </el-table-column>
          <el-table-column label="残值%" width="72" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="!isReadonly"
                :model-value="cellOf(row, peer.peerId).salvageRate ?? undefined"
                size="small"
                @change="(v: number | undefined) => state.updatePeerCell(row.category, peer.peerId, 'salvageRate', v ?? null)"
              />
              <span v-else>{{ formatSalvage(cellOf(row, peer.peerId).salvageRate) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 表C -->
    <el-card v-if="state.showPriorEstimates.value" shadow="never" class="params-card prior-card">
      <template #header>
        <div class="section-title">
          <span>表C：如本期存在会计估计变更，原会计估计如下</span>
          <el-tag size="small" type="warning">未来适用法 · CAS28</el-tag>
        </div>
      </template>
      <el-alert type="warning" :closable="false" show-icon class="prior-alert">
        折旧年限/方法/残值变更属会计估计变更。请填写变更前参数及对当期折旧/损益的影响金额，并跳转
        <GtIndexChip value="wp:S3-2" :context-project-id="projectId" /> 履行正式程序。
      </el-alert>
      <el-table :data="state.priorEstimates.value" border stripe size="small">
        <el-table-column type="index" label="序" width="44" align="center" />
        <el-table-column prop="category" label="类别" min-width="100" />
        <el-table-column label="原使用寿命" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.usefulLife" size="small" placeholder="变更前年限" @change="state.persistPriors()" />
            <span v-else>{{ row.usefulLife }}</span>
          </template>
        </el-table-column>
        <el-table-column label="原折旧方法" width="120">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.depMethod" size="small" clearable @change="state.persistPriors()">
              <el-option v-for="m in state.DEP_METHOD_OPTIONS" :key="m" :label="m" :value="m" />
            </el-select>
            <span v-else>{{ row.depMethod }}</span>
          </template>
        </el-table-column>
        <el-table-column label="原残值率%" width="90" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              v-model="row.salvageRate"
              size="small"
              @change="state.persistPriors()"
            />
            <span v-else>{{ formatSalvage(row.salvageRate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="当期影响金额" width="120" align="right">
          <template #header>
            <el-tooltip content="对当期折旧费用/损益的影响金额（正数增加费用）" placement="top">
              <span>当期影响金额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              v-model="row.impactAmount"
              size="small"
              @change="state.persistPriors()"
            />
            <span v-else>{{ row.impactAmount == null ? '' : row.impactAmount.toLocaleString('zh-CN') }}</span>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.source" size="small" type="info">{{ sourceLabel(row.source) }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
    <el-alert
      v-else
      type="info"
      :closable="false"
      show-icon
      class="prior-placeholder"
      title="表C：本期表A未标记「存在变更=Y」，无需填写原会计估计。"
    />

    <!-- 三、审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>三、审计说明</span>
          <el-button
            v-if="!isReadonly"
            size="small"
            type="primary"
            link
            :loading="aiLoadingKey === 'note'"
            @click="handleAiNote"
          >
            <el-icon><MagicStick /></el-icon> AI起草
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditNoteLocal"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="记录同业选取标准、重大判断依据、估计变更影响金额、与附注披露勾稽情况等..."
        @blur="saveAuditNote"
      />
    </el-card>

    <!-- 四、审计结论 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>四、审计结论</span>
          <el-button
            v-if="!isReadonly"
            size="small"
            type="success"
            :disabled="!state.completenessOk.value"
            @click="tryMarkReady"
          >
            确认可关闭
          </el-button>
        </div>
      </template>
      <el-input
        v-model="policyConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="固定资产会计政策/估计总体是否恰当、一贯，同业比较是否存在重大差异..."
        @change="savePolicyConclusion"
      />
      <el-alert
        v-if="!state.completenessOk.value"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top:8px"
        :title="`尚有 ${state.gateBlockers.value.length} 项未完成，完成度闸门未通过前不建议关闭本检查项`"
      />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>优先「从 H1-2 带入」填充表A，避免与明细分类两张皮</li>
        <li>表B须注明信息来源；偏离同业区间时备注为强制项</li>
        <li>存在变更时带入上年/H1-12 原估计，填写影响金额并跳转 S3-2</li>
        <li>段落(3)结论为Y时，表A不得残留「综合合理=N」</li>
        <li>完成度闸门全部打勾后方可关闭本检查项</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { ref, computed, inject, toRef, onMounted, watch, defineComponent, h } from 'vue'
import { MagicStick, InfoFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, ElSelect, ElOption, ElTag } from 'element-plus'
import {
  useH1PolicyCheck,
  type PolicySection,
  type DepParamRow,
  type PeerPolicyRow,
  type PeerCell,
  type YnNa,
} from '../../composables/useH1PolicyCheck'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

const YnSelect = defineComponent({
  name: 'YnSelect',
  props: {
    modelValue: { type: String, default: '' },
    readonly: { type: Boolean, default: false },
  },
  emits: ['update:modelValue', 'change'],
  setup(props, { emit }) {
    return () => {
      if (props.readonly) {
        const v = props.modelValue || '—'
        const type = v === 'Y' ? 'success' : v === 'N' ? 'danger' : 'info'
        return h(ElTag, { type: type as any, size: 'small' }, () => v)
      }
      return h(
        ElSelect,
        {
          modelValue: props.modelValue || undefined,
          size: 'small',
          style: { width: '56px' },
          clearable: true,
          'onUpdate:modelValue': (v: string) => {
            emit('update:modelValue', (v || '') as YnNa)
            emit('change', (v || '') as YnNa)
          },
        },
        () => [
          h(ElOption, { label: 'Y', value: 'Y' }),
          h(ElOption, { label: 'N', value: 'N' }),
          h(ElOption, { label: 'NA', value: 'NA' }),
        ],
      )
    }
  },
})

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const allResponsesRef = computed(() => props.allResponses)

const policyConclusion = ref('')
const auditNoteLocal = ref('')
const aiLoadingKey = ref('')
const syncLoading = ref(false)
const priorLoading = ref(false)
const jsonInputRef = ref<HTMLInputElement | null>(null)
const CONCLUSION_KEY = 'H1-5-audit-conclusion'

function persistPayload(itemId: string, value: any) {
  const existing = props.allResponses.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
  const remark = typeof value === 'string' ? value : JSON.stringify(value)
  props.allResponses.set(itemId, { ...existing, remark })
  saveResponse(itemId, value)
}

const state = useH1PolicyCheck(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  allResponsesRef as any,
  { onSave: persistPayload },
)

watch(
  () => state.auditNote.value,
  (v) => { if (auditNoteLocal.value !== v) auditNoteLocal.value = v },
  { immediate: true },
)

onMounted(() => {
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) policyConclusion.value = c.remark
})

function isSectionDone(s: PolicySection): boolean {
  if (!s.conclusion) return false
  if (s.conclusion === 'N' && !s.explanationIfN?.trim()) return false
  return true
}

function getConclusionType(conclusion: string): 'success' | 'danger' | 'info' {
  if (conclusion === 'Y') return 'success'
  if (conclusion === 'N') return 'danger'
  return 'info'
}

function formatLife(row: DepParamRow): string {
  if (row.usefulLifeMin && row.usefulLifeMax && row.usefulLifeMin !== row.usefulLifeMax) {
    return `${row.usefulLifeMin}–${row.usefulLifeMax}`
  }
  return String(row.usefulLifeMax || row.usefulLifeMin || '')
}

function formatSalvage(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v as number)) return ''
  return `${v}%`
}

function cellOf(row: PeerPolicyRow, peerId: string): PeerCell {
  return row.values[peerId] || { usefulLife: '', depMethod: '', salvageRate: null }
}

function needsDevRemark(category: string): boolean {
  return state.categoriesNeedingDeviationRemark.value.includes(category)
}

function depRowClass({ row }: { row: DepParamRow }): string {
  const classes: string[] = []
  if (row.mismatchDetail) classes.push('row-mismatch')
  if (needsDevRemark(row.category)) classes.push('row-deviate')
  return classes.join(' ')
}

function sourceLabel(s: string): string {
  if (s === 'prior-year') return '上年'
  if (s === 'h1-12') return 'H1-12'
  if (s === 'manual') return '手工'
  return s
}

function onSectionBlur(_idx: number) {
  state.persistSections()
}

function persistParams() {
  state.persistDepParams()
}

function onJudgeChange(rowId: string, field: keyof DepParamRow, value: YnNa) {
  state.updateDepParam(rowId, field, value)
}

function handleAddParam() {
  state.addDepParam()
}

function handleReview(id: string) {
  openReviewDialog(id)
}

function saveAuditNote() {
  state.setAuditNote(auditNoteLocal.value)
}

function savePolicyConclusion() {
  persistPayload(CONCLUSION_KEY, policyConclusion.value)
}

async function handleSyncDetail() {
  syncLoading.value = true
  try {
    const detailEmpty = !props.allResponses.get('H1-2-rows')?.remark
    if (detailEmpty) {
      ElMessage.warning('H1-2 明细尚无数据，请先完成明细表')
      return
    }
    let replace = false
    try {
      await ElMessageBox.confirm(
        '「覆盖」将按 H1-2 类别重建表A；「合并」仅刷新已有类别参数并追加新类别。',
        '从 H1-2 带入',
        { confirmButtonText: '合并刷新', cancelButtonText: '覆盖重建', distinguishCancelAndClose: true, type: 'info' },
      )
    } catch (e: any) {
      if (e === 'cancel') replace = true
      else return
    }
    const r = state.syncFromDetail({ replace })
    if (!r.categories.length) {
      ElMessage.warning('H1-2 未识别到资产类别')
      return
    }
    ElMessage.success(
      replace
        ? `已覆盖重建 ${r.added} 个类别`
        : `新增 ${r.added}、刷新 ${r.refreshed} 个类别`,
    )
  } finally {
    syncLoading.value = false
  }
}

async function handlePriorYear() {
  priorLoading.value = true
  try {
    const meta = await http.get(`/api/projects/${props.projectId}/workpapers/${props.wpId}/prior-year`)
    const priorWpId = meta.data?.wp_id || meta.data?.data?.wp_id
    if (!priorWpId) {
      ElMessage.warning('未找到上年底稿')
      return
    }
    const resp = await http.get(`/api/workpapers/${priorWpId}/checklist-responses`)
    const items = Array.isArray(resp.data) ? resp.data : (resp.data?.items || resp.data?.data || [])
    const r = state.applyPriorYearResponses(Array.isArray(items) ? items : [])
    ElMessage.success(
      r.filled || r.markedChange
        ? `已带入上年：标记变更 ${r.markedChange} 类，回填原估计 ${r.filled} 项`
        : '上年无参数差异或无可带入数据',
    )
  } catch (e: any) {
    const status = e?.response?.status
    ElMessage.warning(status === 404 ? '未关联上年项目或无对应 H1 底稿' : (e?.response?.data?.detail || '带入上年失败'))
  } finally {
    priorLoading.value = false
  }
}

function handleSyncH12() {
  const n = state.syncPriorsFromH12()
  ElMessage.success(n > 0 ? `已从 H1-12 带入 ${n} 个类别的原估计` : 'H1-12 无估计变更字段可带入')
}

function handleIndustryTpl(id: string) {
  const ok = state.applyIndustryTemplate(id)
  if (ok) ElMessage.success('已套用行业同业模板（示意数据，请按实际年报替换）')
  else ElMessage.warning('未找到该模板')
}

function handleSuggestJudgments() {
  const n = state.suggestJudgmentsFromPeers()
  ElMessage.success(n > 0 ? `已为 ${n} 个类别建议「同业合理」判断，请人工复核` : '无需建议（已填满或同业数据不足）')
}

function handleImportExport(cmd: string) {
  if (cmd === 'export-json') {
    const pack = state.buildExportPack(policyConclusion.value)
    const blob = new Blob([JSON.stringify(pack, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `H1-5_会计政策估计检查_${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('已导出 JSON 数据包')
  } else if (cmd === 'import-json') {
    jsonInputRef.value?.click()
  }
}

async function onJsonSelected(ev: Event) {
  const file = (ev.target as HTMLInputElement).files?.[0]
  ;(ev.target as HTMLInputElement).value = ''
  if (!file) return
  try {
    await ElMessageBox.confirm(`即将导入「${file.name}」，将覆盖当前 H1-5 数据。确认？`, '导入确认', {
      type: 'warning',
    })
    const text = await file.text()
    const pack = JSON.parse(text)
    const r = state.importExportPack(pack)
    if (!r.ok) {
      ElMessage.error(r.message)
      return
    }
    if (typeof pack.auditConclusion === 'string') {
      policyConclusion.value = pack.auditConclusion
      savePolicyConclusion()
    }
    ElMessage.success(r.message)
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e?.message || '导入失败')
  }
}

async function tryMarkReady() {
  if (!state.completenessOk.value) {
    await ElMessageBox.alert(
      state.gateBlockers.value.map((b, i) => `${i + 1}. ${b}`).join('\n'),
      '完成度闸门未通过',
      { type: 'warning' },
    )
    return
  }
  if (!policyConclusion.value.trim()) {
    policyConclusion.value =
      '经检查，被审计单位固定资产相关会计政策与会计估计符合企业会计准则规定，反映实际经营情况，与同行业相比不存在重大不合理差异，政策得到一贯执行。'
    savePolicyConclusion()
  }
  ElMessage.success('完成度闸门已通过，可关闭本检查项')
}

async function handleAiEval(section: PolicySection) {
  if (!props.wpId) return
  aiLoadingKey.value = section.key
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/h1/ai-generate`,
      {
        section: 'policy-evaluation',
        existingContent: section.evaluation || '',
        relatedContext: {
          paragraph: section.title,
          casRef: section.description,
          actualPolicy: section.actualPolicy,
          depParams: state.depParams.value,
          peers: { companies: state.peerCompanies.value, policies: state.peerPolicies.value },
          deviations: state.peerDeviations.value,
          crossChecks: state.crossCheckIssues.value,
        },
      },
      { _silent: true } as any,
    )
    const text = res.data?.content || res.data?.data?.content || ''
    if (!text) {
      ElMessage.warning('AI 未返回内容')
      return
    }
    section.evaluation = text
    state.persistSections()
    ElMessage.success('已生成审计师评价')
  } catch {
    ElMessage.error('AI 生成失败')
  } finally {
    aiLoadingKey.value = ''
  }
}

async function handleAiNote() {
  if (!props.wpId) return
  aiLoadingKey.value = 'note'
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/h1/ai-generate`,
      {
        section: 'policy-evaluation',
        existingContent: auditNoteLocal.value || '',
        relatedContext: {
          mode: 'audit-note',
          sections: state.sections.value.map((s) => ({
            title: s.title,
            conclusion: s.conclusion,
            evaluation: s.evaluation,
          })),
          depParams: state.depParams.value,
          peers: state.peerCompanies.value,
          priorEstimates: state.priorEstimates.value,
          changes: state.categoriesWithChange.value,
          deviations: state.peerDeviations.value,
          completeness: state.completeness.value,
        },
      },
      { _silent: true } as any,
    )
    const text = res.data?.content || res.data?.data?.content || ''
    if (!text) {
      ElMessage.warning('AI 未返回内容')
      return
    }
    auditNoteLocal.value = text
    saveAuditNote()
    ElMessage.success('已生成审计说明')
  } catch {
    ElMessage.error('AI 生成失败')
  } finally {
    aiLoadingKey.value = ''
  }
}
</script>

<style scoped>
.h1-tab-policy-check { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.obj-title { font-weight: 600; margin-bottom: 4px; }
.obj-list { margin: 4px 0 0; padding-left: 18px; font-size: 12px; line-height: 1.55; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.guide-area { background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%); border-radius: 8px; padding: 12px 16px; margin-bottom: 12px; }
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.guide-step { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.step-num { font-weight: 700; color: var(--el-color-primary); }
.section-label { font-weight: 600; margin: 8px 0 10px; font-size: 13px; }
.policy-card { margin-bottom: 12px; }
.policy-card-done { border-left: 3px solid var(--el-color-success); }
.section-title { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.title-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.cas-reference { margin-bottom: 12px; font-size: 12px; color: var(--el-text-color-secondary); background: var(--el-fill-color-light); border-radius: 4px; border-left: 3px solid var(--el-color-primary); padding: 8px 12px; }
.cas-reference summary { cursor: pointer; display: flex; align-items: center; gap: 6px; font-weight: 500; }
.cas-reference p { margin: 8px 0 0; line-height: 1.5; }
.field-group { margin-bottom: 12px; }
.field-group label { display: block; font-weight: 500; margin-bottom: 4px; }
.conclusion-group { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.n-explanation { border-left: 3px solid var(--el-color-danger); padding-left: 12px; }
.params-card, .note-card, .gate-card { margin-bottom: 12px; }
.gate-card { border-left: 3px solid var(--el-color-warning); }
.gate-card.gate-ok { border-left-color: var(--el-color-success); }
.gate-list { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 16px; font-size: 12px; }
.gate-item { color: var(--el-color-danger); }
.gate-item.ok { color: var(--el-color-success); }
.gate-hint { display: block; color: var(--el-text-color-secondary); margin-left: 14px; font-size: 11px; }
.cross-alert { margin-bottom: 8px; }
.wide-table { width: 100%; }
.life-range { display: flex; align-items: center; gap: 4px; }
.life-range :deep(.el-input-number) { width: 48px; }
.peer-hint { font-size: 10px; color: var(--el-color-primary); margin-top: 2px; }
.muted { color: var(--el-text-color-placeholder); }
.peer-meta-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 12px; }
.peer-meta { display: flex; flex-direction: column; gap: 6px; }
.peer-table :deep(.el-input-number) { width: 56px; }
.prior-card { border-left: 3px solid var(--el-color-warning); }
.prior-alert { margin-bottom: 10px; }
.prior-placeholder { margin-bottom: 12px; }
.need-remark :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px var(--el-color-danger) inset; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
:deep(.row-mismatch) { background: #fff7e6 !important; }
:deep(.row-deviate) { background: #fff1f0 !important; }
@media (max-width: 1100px) {
  .peer-meta-grid, .guide-grid, .gate-list { grid-template-columns: 1fr; }
}
</style>
