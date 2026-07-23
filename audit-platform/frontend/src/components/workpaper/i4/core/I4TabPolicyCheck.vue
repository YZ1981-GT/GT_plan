<template>
  <div class="i4-tab-policy-check">
    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>一、审计目标</template>
      判断长期待摊费用相关重大会计政策和会计估计的合理性（摊销方法、受益期限、资本化边界、估计变更），并与同行业及前期比较。
    </el-alert>

    <div class="methodology-context">
      <p>
        <b>受益模式：</b>摊销方法应与费用受益模式一致（均匀→直线法；产出相关→工作量法）。
        <b>期限：</b>装修/租赁改良不超过租赁期与使用年限孰短；开办费按受益期审慎估计。
        <b>CAS28：</b>受益期限变更属会计估计变更，未来适用法；须披露原因与影响。
      </p>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="chip-wrap"><GtIndexChip value="wp:I4-4" :context-project-id="projectId" /></span>
        <GtIndexChip value="wp:I4-2" :context-project-id="projectId" />
        <GtIndexChip value="wp:I4-6" :context-project-id="projectId" />
        <GtIndexChip value="wp:I4-5" :context-project-id="projectId" />
        <el-tag size="small" :type="state.completenessOk.value ? 'success' : 'warning'">
          完成度 {{ state.completionProgress.value }}%
        </el-tag>
        <el-tag
          size="small"
          :type="state.sheetMarkedComplete.value ? 'success' : 'info'"
          effect="plain"
        >
          {{ state.sheetMarkedComplete.value ? '目录：已完成' : '目录：未标记完成' }}
        </el-tag>
        <el-tag v-if="state.negativeJudgments.value.length" size="small" type="danger">
          不合理判断 {{ state.negativeJudgments.value.length }}
        </el-tag>
        <el-tag
          v-if="state.hasAnyChange.value"
          size="small"
          type="warning"
          class="nav-chip"
          @click="emit('navigate-sheet', 'I4-6')"
        >
          估计变更 → 测算 I4-6/7（{{ state.changedCategories.value.length }}）
        </el-tag>
        <el-tag v-if="state.lastAppliedTemplateLabel.value" size="small" type="info" effect="plain">
          {{ state.lastAppliedTemplateLabel.value }} · 示意须核年报
        </el-tag>
      </div>
      <div class="toolbar-right">
        <el-button size="small" :disabled="isReadonly" @click="handleSyncDetail">从 I4-2 带入</el-button>
        <el-button size="small" :disabled="isReadonly" @click="handleSyncFromAmort">从测算回填空白</el-button>
        <el-button size="small" :disabled="isReadonly" @click="handleSuggestPeers">建议同业合理</el-button>
        <el-dropdown :disabled="isReadonly" trigger="click" @command="handleIndustryTpl">
          <el-button size="small">行业模板 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item
                v-for="t in state.INDUSTRY_TEMPLATES"
                :key="t.id"
                :command="t.id"
              >{{ t.label }}</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-dropdown :disabled="isReadonly || peerLoading" trigger="click" @command="handleFetchPeers">
          <el-button size="small" type="success" plain :loading="peerLoading">年报库拉取 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item
                v-if="state.industryHint.value"
                :command="state.industryHint.value.id"
                divided
              >
                推荐：{{ state.industryHint.value.label }}
              </el-dropdown-item>
              <el-dropdown-item command="retail">零售/连锁</el-dropdown-item>
              <el-dropdown-item command="manufacturing">制造业</el-dropdown-item>
              <el-dropdown-item command="property">物业/商业地产</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button
          v-if="state.industryHint.value"
          size="small"
          type="success"
          :disabled="isReadonly || peerLoading"
          :loading="peerLoading"
          @click="handleFetchPeers(state.industryHint.value.id)"
        >拉取推荐行业</el-button>
        <el-button size="small" type="default" link @click="handleReview('I4-4')">💬 复核</el-button>
      </div>
    </div>

    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 政策要点评价（方法/期限/边界/变更）</div>
        <div class="guide-step"><span class="step-num">②</span> 表A：按费用类型填政策 + 五维判断</div>
        <div class="guide-step"><span class="step-num">③</span> 表B：同业受益期/方法对标</div>
        <div class="guide-step"><span class="step-num">④</span> 有变更→表C原估计 → 说明/结论</div>
      </div>
    </div>

    <el-card shadow="never" class="gate-card" :class="{ 'gate-ok': state.completenessOk.value }">
      <template #header>
        <div class="section-title">
          <span>完成度闸门</span>
          <div class="title-actions">
            <el-tag :type="state.completenessOk.value ? 'success' : 'danger'" size="small">
              {{ state.completenessOk.value ? '可关闭本检查项' : '未达标' }}
            </el-tag>
            <el-button
              v-if="!isReadonly && !state.sheetMarkedComplete.value"
              size="small"
              type="success"
              :disabled="!state.canMarkComplete.value"
              @click="handleMarkComplete"
            >标记已完成</el-button>
            <el-button
              v-if="!isReadonly && state.sheetMarkedComplete.value"
              size="small"
              type="warning"
              plain
              @click="handleUnmarkComplete"
            >取消已完成</el-button>
          </div>
        </div>
      </template>
      <el-progress :percentage="state.completionProgress.value" :stroke-width="10" style="margin-bottom:10px" />
      <div class="gate-list">
        <div v-for="c in state.completeness.value" :key="c.id" class="gate-item" :class="{ ok: c.ok }">
          <span>{{ c.ok ? '✓' : '○' }} {{ c.label }}</span>
          <span class="gate-hint">{{ c.hint }}</span>
        </div>
      </div>
      <el-alert
        v-if="state.industryHint.value"
        type="info"
        :closable="false"
        show-icon
        style="margin-top:10px"
        :title="`行业推荐：${state.industryHint.value.label}（${state.industryHint.value.confidence}）— ${state.industryHint.value.reason}`"
      />
    </el-card>

    <el-alert
      v-if="!state.leaseShorterCheck.value.ok"
      type="error"
      :closable="false"
      show-icon
      class="cross-alert"
    >
      <template #title>
        租赁期孰短：{{ state.leaseShorterCheck.value.summary }}
        <span v-if="leaseErrorHints"> — {{ leaseErrorHints }}</span>
      </template>
    </el-alert>
    <el-alert
      v-else-if="state.leaseShorterCheck.value.items.length"
      type="success"
      :closable="false"
      show-icon
      class="cross-alert"
      :title="state.leaseShorterCheck.value.summary"
    />

    <el-alert
      v-if="state.hasAnyChange.value"
      type="warning"
      :closable="false"
      show-icon
      class="cross-alert"
    >
      <template #title>
        本期存在会计估计变更（{{ state.changedCategories.value.join('、') || '见表A' }}）：请填写表C，并核对
        <el-button size="small" type="warning" link @click="emit('navigate-sheet', 'I4-6')">
          I4-6/7 摊销测算 →
        </el-button>
        与
        <el-button size="small" type="warning" link @click="emit('navigate-sheet', 'I4-5')">
          I4-5 针对性检查 →
        </el-button>
        是否交叉印证。
      </template>
    </el-alert>

    <!-- 表A ↔ 测算勾稽 -->
    <el-card shadow="never" class="cross-card" :class="{ 'cross-ok': state.amortCrossCheck.value.ok }">
      <template #header>
        <div class="section-title">
          <span>表A ↔ I4-6/I4-7 测算勾稽</span>
          <div class="title-actions">
            <el-tag
              size="small"
              :type="state.amortCrossCheck.value.ok ? 'success' : 'danger'"
            >{{ state.amortCrossCheck.value.summary }}</el-tag>
            <el-button
              v-if="!isReadonly && state.amortCrossCheck.value.issues.some(i => i.severity !== 'info')"
              size="small"
              type="warning"
              plain
              @click="handleMarkAttention"
            >标记关注</el-button>
            <el-button
              v-if="!isReadonly && hasSignificantDiff"
              size="small"
              type="danger"
              plain
              @click="handleGenAdjDraft"
            >生成 I4-3 补提草稿</el-button>
            <el-button size="small" link @click="emit('navigate-sheet', 'I4-6')">测算 →</el-button>
          </div>
        </div>
      </template>
      <div v-if="state.amortCrossCheck.value.aggs.length" class="cross-agg">
        <el-tag
          v-for="a in state.amortCrossCheck.value.aggs"
          :key="a.category"
          size="small"
          effect="plain"
          class="agg-tag"
        >
          {{ a.category }} · {{ a.amortMethod }} · {{ a.benefitPeriod || '—' }}
          · 差异{{ Math.max(a.periodDiffAbs, a.accumDiffAbs).toLocaleString('zh-CN') }}
          （{{ a.source }} {{ a.itemCount }}项）
        </el-tag>
      </div>
      <el-alert
        v-else
        type="info"
        :closable="false"
        show-icon
        title="暂无 I4-6/I4-7 测算数据；编制测算后将自动勾稽方法、受益期与重大差异。"
      />
      <ul v-if="state.amortCrossCheck.value.issues.length" class="cross-issues">
        <li
          v-for="iss in state.amortCrossCheck.value.issues"
          :key="iss.id"
          :class="`sev-${iss.severity}`"
        >
          <b>[{{ iss.severity }}]</b> {{ iss.message }}
          <span v-if="iss.hint" class="iss-hint">— {{ iss.hint }}</span>
        </li>
      </ul>
    </el-card>

    <el-alert
      v-if="state.peerDeviations.value.length"
      type="warning"
      :closable="false"
      show-icon
      class="cross-alert"
    >
      <template #title>
        同业偏离 {{ state.peerDeviations.value.length }} 项
        <span v-if="state.peerRemarkNeeded.value.length">
          （须备注：{{ state.peerRemarkNeeded.value.join('、') }}）
        </span>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="warning"
          link
          @click="handleSuggestPeers"
        >自动建议「同业合理」→</el-button>
      </template>
      <ul class="peer-dev-list">
        <li v-for="(d, i) in state.peerDeviations.value.slice(0, 5)" :key="i">{{ d.message }}</li>
        <li v-if="state.peerDeviations.value.length > 5">…</li>
      </ul>
    </el-alert>

    <!-- 政策要点 -->
    <div class="section-label">二、审计过程 — 政策要点评价</div>
    <el-card
      v-for="(item, idx) in state.casItems.value"
      :key="item.key"
      shadow="never"
      class="check-card"
      :class="{ 'check-card-done': item.conclusion === '是' || item.conclusion === '不适用' }"
    >
      <template #header>
        <div class="section-title">
          <span class="check-title">{{ idx + 1 }. {{ item.label }}</span>
          <div class="title-actions">
            <el-tag v-if="item.conclusion" :type="casTagType(item.conclusion)" size="small">
              {{ item.conclusion }}
            </el-tag>
            <el-button size="small" type="default" link @click="handleReview(`I4-4-${item.key}`)">💬</el-button>
          </div>
        </div>
      </template>
      <details class="cas-reference">
        <summary>{{ item.casRef.slice(0, 40) }}…（展开）</summary>
        <p>{{ item.casRef }}</p>
      </details>
      <div class="field-group">
        <label>被审计单位实际政策：</label>
        <el-input
          v-model="item.actualPolicy"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 4 }"
          :disabled="isReadonly"
          placeholder="描述实际会计政策…"
          @blur="state.persistCas()"
        />
      </div>
      <div class="field-group">
        <label>审计师评价：</label>
        <el-input
          v-model="item.evaluation"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 4 }"
          :disabled="isReadonly"
          placeholder="评价是否符合准则及受益模式…"
          @blur="state.persistCas()"
        />
      </div>
      <div class="field-group conclusion-group">
        <label>结论：</label>
        <el-radio-group v-model="item.conclusion" :disabled="isReadonly" @change="state.persistCas()">
          <el-radio value="是">是</el-radio>
          <el-radio value="否">否</el-radio>
          <el-radio value="不适用">不适用</el-radio>
        </el-radio-group>
      </div>
      <div v-if="item.conclusion === '否'" class="field-group n-explanation">
        <label>不符合原因及影响：</label>
        <el-input
          v-model="item.explanationIfNo"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 4 }"
          :disabled="isReadonly"
          placeholder="必须说明原因及对审计的影响…"
          @blur="state.persistCas()"
        />
        <el-alert v-if="!item.explanationIfNo" type="error" :closable="false" show-icon>
          结论为「否」时必须填写原因说明
        </el-alert>
      </div>
    </el-card>

    <!-- 表A -->
    <el-card shadow="never" class="params-card">
      <template #header>
        <div class="section-title">
          <span>（一）被审计单位的长期待摊费用摊销政策</span>
          <el-button size="small" type="primary" :disabled="isReadonly" @click="state.addParamRow()">
            + 新增类型
          </el-button>
        </div>
      </template>
      <el-table
        :data="state.policyParams.value"
        border
        stripe
        size="small"
        class="wide-table"
        :row-class-name="paramRowClass"
      >
        <el-table-column type="index" label="序" width="44" align="center" />
        <el-table-column prop="category" label="费用类型" min-width="110" fixed>
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.category"
              size="small"
              filterable
              allow-create
              @change="state.persistParams()"
            >
              <el-option v-for="c in DEFAULT_CATEGORIES" :key="c" :label="c" :value="c" />
            </el-select>
            <span v-else>{{ row.category }}</span>
            <div v-if="row.detailCount" class="peer-hint">I4-2 {{ row.detailCount }}笔</div>
          </template>
        </el-table-column>
        <el-table-column prop="benefitPeriod" label="受益期限" width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.benefitPeriod"
              size="small"
              placeholder="如3年/租赁期"
              @change="state.persistParams()"
            />
            <span v-else>{{ row.benefitPeriod }}</span>
            <div v-if="state.peerLifeHints.value[row.category]" class="peer-hint">
              同业 {{ state.peerLifeHints.value[row.category] }}
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="amortMethod" label="摊销方法" width="120">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.amortMethod"
              size="small"
              @change="state.persistParams()"
            >
              <el-option v-for="m in state.AMORT_METHOD_OPTIONS" :key="m" :label="m" :value="m" />
            </el-select>
            <span v-else>{{ row.amortMethod }}</span>
          </template>
        </el-table-column>
        <el-table-column label="符合准则" width="78" align="center">
          <template #header>
            <el-tooltip content="是否符合实际经营情况和会计准则的要求" placement="top">
              <span>符合准则</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <YnSelect v-model="row.meetsStandards" :readonly="isReadonly" @change="state.persistParams()" />
          </template>
        </el-table-column>
        <el-table-column label="受益模式" width="78" align="center">
          <template #header>
            <el-tooltip content="是否与费用受益模式/经济利益预期实现方式相一致" placement="top">
              <span>受益模式</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <YnSelect v-model="row.matchesBenefitPattern" :readonly="isReadonly" @change="state.persistParams()" />
          </template>
        </el-table-column>
        <el-table-column label="同业合理" width="78" align="center">
          <template #default="{ row }">
            <YnSelect v-model="row.reasonableVsPeers" :readonly="isReadonly" @change="state.persistParams()" />
            <div
              v-if="state.peerRemarkNeeded.value.includes(row.category)"
              class="peer-hint peer-warn"
            >须备注</div>
          </template>
        </el-table-column>
        <el-table-column label="存在变更" width="78" align="center">
          <template #default="{ row }">
            <YnSelect v-model="row.hasChange" :readonly="isReadonly" @change="state.persistParams()" />
          </template>
        </el-table-column>
        <el-table-column label="变更合理" width="78" align="center">
          <template #default="{ row }">
            <YnSelect
              v-if="row.hasChange === 'Y'"
              v-model="row.changeReasonable"
              :readonly="isReadonly"
              @change="state.persistParams()"
            />
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.remark"
              size="small"
              placeholder="重大判断说明"
              @change="state.persistParams()"
            />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="52" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="state.removeParamRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 表B -->
    <el-card shadow="never" class="params-card">
      <template #header>
        <div class="section-title">
          <span>（二）同行业其他公司的长期待摊费用摊销政策（如适用）</span>
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
        <el-table-column prop="category" label="费用类型" min-width="100" fixed />
        <el-table-column
          v-for="peer in state.peerCompanies.value"
          :key="peer.peerId"
          :label="peer.name || '同行业公司'"
          align="center"
        >
          <el-table-column label="受益期限" width="110">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                :model-value="cellOf(row, peer.peerId).benefitPeriod"
                size="small"
                placeholder="如3-5年"
                @update:model-value="(v: string) => state.updatePeerCell(row.category, peer.peerId, 'benefitPeriod', v)"
              />
              <span v-else>{{ cellOf(row, peer.peerId).benefitPeriod }}</span>
            </template>
          </el-table-column>
          <el-table-column label="摊销方法" width="110">
            <template #default="{ row }">
              <el-select
                v-if="!isReadonly"
                :model-value="cellOf(row, peer.peerId).amortMethod || undefined"
                size="small"
                clearable
                placeholder="方法"
                @change="(v: string) => state.updatePeerCell(row.category, peer.peerId, 'amortMethod', v || '')"
              >
                <el-option v-for="m in state.AMORT_METHOD_OPTIONS" :key="m" :label="m" :value="m" />
              </el-select>
              <span v-else>{{ cellOf(row, peer.peerId).amortMethod }}</span>
            </template>
          </el-table-column>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 表C -->
    <el-card v-if="state.showPriorEstimates.value" shadow="never" class="params-card prior-card">
      <template #header>
        <div class="section-title">
          <span>如本期存在会计估计变更，原会计估计如下</span>
          <el-tag size="small" type="warning">未来适用法 · CAS28</el-tag>
        </div>
      </template>
      <el-table :data="state.priorEstimates.value" border stripe size="small">
        <el-table-column type="index" label="序" width="44" align="center" />
        <el-table-column prop="category" label="费用类型" min-width="100" />
        <el-table-column label="原受益期限" width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.benefitPeriod"
              size="small"
              placeholder="变更前"
              @change="state.persistPriors()"
            />
            <span v-else>{{ row.benefitPeriod }}</span>
          </template>
        </el-table-column>
        <el-table-column label="原摊销方法" width="120">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.amortMethod"
              size="small"
              clearable
              @change="state.persistPriors()"
            >
              <el-option v-for="m in state.AMORT_METHOD_OPTIONS" :key="m" :label="m" :value="m" />
            </el-select>
            <span v-else>{{ row.amortMethod }}</span>
          </template>
        </el-table-column>
        <el-table-column label="当期影响金额" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.impactAmount"
              :controls="false"
              size="small"
              @change="state.persistPriors()"
            />
            <span v-else>{{ row.impactAmount == null ? '—' : row.impactAmount.toLocaleString('zh-CN') }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.remark"
              size="small"
              @change="state.persistPriors()"
            />
            <span v-else>{{ row.remark }}</span>
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

    <!-- 说明 / 结论 -->
    <el-card shadow="never" class="note-card">
      <template #header><span>三、审计说明</span></template>
      <el-input
        v-model="state.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="记录同业选取标准、重大判断依据、估计变更影响、与 I4-2/I4-6 勾稽等…"
        @blur="state.persistNote()"
      />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>四、审计结论</span>
          <el-button
            v-if="!isReadonly"
            size="small"
            type="primary"
            plain
            @click="applyConclusionTpl"
          >套用结论模板</el-button>
        </div>
      </template>
      <el-input
        v-model="state.overallConclusion.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="A、政策恰当一贯。B、除变更事项外未见异常。C、存在不合理政策需调整/披露。"
        @blur="state.persistConclusion()"
      />
      <el-alert
        v-if="!state.completenessOk.value"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top:8px"
        title="完成度闸门未通过前，不能标记为已完成；已标记者若闸门回退将自动降为「进行中」。"
      />
    </el-card>

    <details class="compile-hint" open>
      <summary>编制提示</summary>
      <ul>
        <li>本表对齐源模板：表A（政策+五维判断）→ 表B（同业受益期/方法）→ 有变更则表C（原估计）。</li>
        <li>优先「从 I4-2 带入」；可用「从测算回填空白」将 I4-6/7 众数填入表A空字段。</li>
        <li>表A 与 I4-6/7 自动勾稽；「标记关注」写备注，「生成 I4-3 补提草稿」按重大差异落分录。</li>
        <li>「建议同业合理」按表B区间自动填 Y/N；偏离须在备注说明，否则完成度闸门不通过。</li>
        <li>「年报库拉取 / 拉取推荐行业」按项目名称或明细费用结构推荐行业；摘录库须核对手工年报后再作证据。</li>
        <li>装修/租赁改良须满足受益期 ≤ 租赁期孰短（读 I4-2 起止日）；违反则闸门阻断。</li>
        <li>闸门全部通过后方可「标记已完成」，并与目录状态硬绑定；估计变更属 CAS28 未来适用法。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I4TabPolicyCheck.vue — I4-4 摊销政策检查表
 * 对齐源 xlsx + I1-4 范式：政策要点 + 表A/B/C + 完成度闸门
 */
import { computed, defineComponent, h, inject, ref, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'
import {
  useI4PolicyCheck,
  DEFAULT_CATEGORIES,
  type PeerPolicyRow,
  type Yn,
} from '../../composables/useI4PolicyCheck'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  projectContext?: Record<string, any> | null
}>()

const emit = defineEmits<{
  'save': [itemId: string, value: any]
  'navigate-sheet': [sheetName: string]
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const allResponsesRef = computed(() => props.allResponses)
const projectContextRef = toRef(props, 'projectContext')
const peerLoading = ref(false)

const state = useI4PolicyCheck(allResponsesRef as any, {
  onSave: (itemId, value) => emit('save', itemId, value),
  projectContext: projectContextRef,
})

const leaseErrorHints = computed(() =>
  state.leaseShorterCheck.value.byCategory
    .filter((c) => c.severity === 'error')
    .map((c) => c.hint || c.message)
    .filter(Boolean)
    .slice(0, 2)
    .join('；'),
)

const YnSelect = defineComponent({
  name: 'YnSelect',
  props: {
    modelValue: { type: String, default: '' },
    readonly: { type: Boolean, default: false },
  },
  emits: ['update:modelValue', 'change'],
  setup(p, { emit: e }) {
    return () => {
      if (p.readonly) {
        const v = p.modelValue || '—'
        const type = v === 'Y' ? 'success' : v === 'N' ? 'danger' : 'info'
        return h('span', { class: `yn-tag yn-${type}` }, v === '' ? '—' : v)
      }
      return h(
        'select',
        {
          class: 'yn-native',
          value: p.modelValue,
          onChange: (ev: Event) => {
            const val = (ev.target as HTMLSelectElement).value as Yn
            e('update:modelValue', val)
            e('change', val)
          },
        },
        [
          h('option', { value: '' }, ''),
          h('option', { value: 'Y' }, 'Y'),
          h('option', { value: 'N' }, 'N'),
          h('option', { value: 'NA' }, 'NA'),
        ],
      )
    }
  },
})

function cellOf(row: PeerPolicyRow, peerId: string) {
  return row.cells?.[peerId] ?? { benefitPeriod: '', amortMethod: '' }
}

function casTagType(c: string): 'success' | 'danger' | 'info' {
  if (c === '是') return 'success'
  if (c === '否') return 'danger'
  return 'info'
}

function paramRowClass({ row }: { row: { meetsStandards?: string; matchesBenefitPattern?: string; reasonableVsPeers?: string; changeReasonable?: string; category?: string } }) {
  if ([row.meetsStandards, row.matchesBenefitPattern, row.reasonableVsPeers, row.changeReasonable].includes('N')) {
    return 'neg-row'
  }
  if (row.category && state.peerRemarkNeeded.value.includes(row.category)) {
    return 'peer-warn-row'
  }
  return ''
}

const hasSignificantDiff = computed(() =>
  state.amortCrossCheck.value.issues.some((i) => i.code === 'significant-diff'),
)

function handleReview(id: string) {
  openReviewDialog(id)
}

async function handleSyncDetail() {
  const detailData = props.allResponses.get('I4-2-rows')
  const raw = (detailData as any)?.remark ?? (detailData as any)?.conclusion
  if (!raw) {
    ElMessageBox.alert('未找到 I4-2 明细表数据，请先完善明细表。', '提示')
    return
  }
  try {
    await ElMessageBox.confirm(
      '将按 I4-2 费用类型汇总受益期限/摊销方法带入表A，已有判断字段尽量保留。是否继续？',
      '从 I4-2 带入',
      { type: 'warning', confirmButtonText: '确定', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed) || !parsed.length) {
      ElMessage.warning('I4-2 暂无明细行')
      return
    }
    const n = state.syncFromDetail(parsed)
    ElMessage.success(`已带入 ${n} 个费用类型`)
  } catch {
    ElMessage.error('I4-2 数据解析失败')
  }
}

function handleIndustryTpl(id: string) {
  state.applyIndustryTemplate(id)
  ElMessage.success('已套用示意性行业模板（须核对手工年报附注后再作证据）')
}

function handleSyncFromAmort() {
  const n = state.syncBlankParamsFromAmort()
  if (!n) {
    ElMessage.info('测算无新数据可回填，或表A已填满')
    return
  }
  ElMessage.success(`已从测算回填 ${n} 处空白字段/类型`)
}

function handleSuggestPeers() {
  const n = state.suggestJudgmentsFromPeers()
  if (!n) {
    ElMessage.info('无可建议项（表B无同业样本，或「同业合理」已填）')
    return
  }
  ElMessage.success(`已建议 ${n} 处「同业合理」判断（偏离已写入备注）`)
}

function handleMarkAttention() {
  const n = state.markCrossIssuesAsAttention()
  if (!n) {
    ElMessage.info('无勾稽问题可标记，或备注已存在')
    return
  }
  ElMessage.success(`已在表A写入 ${n} 处勾稽关注（重大差异已清空偏乐观的 Y 判断）`)
}

async function handleGenAdjDraft() {
  try {
    await ElMessageBox.confirm(
      '将按勾稽「重大差异」金额生成补提摊销分录草稿写入 I4-3（跳过已有同说明）。是否继续？',
      '生成 I4-3 补提草稿',
      { type: 'warning', confirmButtonText: '生成', cancelButtonText: '取消' },
    )
  } catch { return }
  const n = state.appendAdjDraftsFromCrossCheck()
  if (!n) {
    ElMessage.info('无新增草稿（可能金额不足或同说明已存在）')
    return
  }
  ElMessage.success(`已写入 I4-3 ${n} 行草稿`)
  emit('navigate-sheet', 'I4-3')
}

async function handleFetchPeers(industry: string) {
  peerLoading.value = true
  try {
    const res = await http.get('/api/workpapers/i4/peer-ltpa-policies', {
      params: { industry },
    })
    const data = res.data?.data ?? res.data
    const peers = data?.peers
    if (!Array.isArray(peers) || !peers.length) {
      ElMessage.warning('年报库无该行业同业数据')
      return
    }
    await ElMessageBox.confirm(
      `${data.disclaimer || '数据来自公开年报附注摘录库，引用前须核对原文。'}\n将填入 ${Math.min(peers.length, 4)} 家同业到表B，是否继续？`,
      '年报库拉取',
      { type: 'warning', confirmButtonText: '填入表B', cancelButtonText: '取消' },
    )
    const n = state.applyPeerCatalog({
      label: data.label || industry,
      peers,
    })
    ElMessage.success(`已填入 ${n} 家同业（须核对手工年报）`)
  } catch (e: any) {
    if (e === 'cancel' || e?.toString?.().includes('cancel')) return
    ElMessage.error(e?.response?.data?.detail || '年报库拉取失败')
  } finally {
    peerLoading.value = false
  }
}

function applyConclusionTpl() {
  state.overallConclusion.value = state.suggestConclusionTemplate()
  state.persistConclusion()
}

function handleMarkComplete() {
  const r = state.markSheetComplete()
  if (r.ok) ElMessage.success(r.message)
  else ElMessage.warning(r.message)
}

function handleUnmarkComplete() {
  state.unmarkSheetComplete()
  ElMessage.info('已取消「已完成」，目录将显示为进行中')
}
</script>

<style scoped>
.i4-tab-policy-check {
  padding: 16px;
  font-size: var(--wp-font-size, 13px);
}

.objective-alert { margin-bottom: 12px; }

.methodology-context {
  border-left: 3px solid var(--el-color-warning);
  background: #fffbe6;
  padding: 10px 14px;
  margin-bottom: 12px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.6;
}

.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.toolbar-left, .toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; }
.nav-chip { cursor: pointer; }

.guide-area {
  background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%);
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 12px;
}
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.guide-step { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.step-num { font-weight: 700; color: var(--el-color-primary); }

.gate-card { margin-bottom: 12px; }
.gate-card.gate-ok { border-left: 3px solid var(--el-color-success); }
.gate-list { display: flex; flex-direction: column; gap: 4px; font-size: 12px; }
.gate-item { display: flex; justify-content: space-between; gap: 8px; color: var(--el-text-color-secondary); }
.gate-item.ok { color: var(--el-color-success); }
.gate-hint { color: var(--el-text-color-placeholder); }

.cross-alert { margin-bottom: 12px; }

.cross-card { margin-bottom: 12px; }
.cross-card.cross-ok { border-left: 3px solid var(--el-color-success); }
.cross-agg { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.agg-tag { max-width: 100%; }
.cross-issues {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  line-height: 1.7;
}
.cross-issues .sev-error { color: var(--el-color-danger); }
.cross-issues .sev-warning { color: var(--el-color-warning-dark-2, #b88230); }
.cross-issues .sev-info { color: var(--el-text-color-secondary); }
.iss-hint { color: var(--el-text-color-placeholder); }

.section-label {
  font-weight: 600;
  margin: 8px 0 10px;
  font-size: 13px;
}

.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}
.title-actions { display: flex; align-items: center; gap: 8px; }

.check-card { margin-bottom: 10px; }
.check-card-done { border-left: 3px solid var(--el-color-success); }
.check-title { font-weight: 500; }

.cas-reference {
  margin-bottom: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-light);
  padding: 8px 12px;
  border-radius: 4px;
}
.cas-reference summary { cursor: pointer; }
.cas-reference p { margin: 6px 0 0; line-height: 1.5; }

.field-group { margin-bottom: 10px; }
.field-group label { display: block; font-weight: 500; margin-bottom: 4px; }
.conclusion-group { display: flex; align-items: center; gap: 12px; }
.n-explanation {
  border-left: 3px solid var(--el-color-danger);
  padding-left: 12px;
}

.params-card { margin-bottom: 12px; }
.wide-table { font-size: 12px; }
.wide-table :deep(.neg-row) { background: #fff1f0; }
.peer-hint { font-size: 11px; color: var(--el-text-color-secondary); }
.peer-warn { color: var(--el-color-warning); font-weight: 600; }
.wide-table :deep(.peer-warn-row) { background: #fffbe6; }
.peer-dev-list {
  margin: 6px 0 0;
  padding-left: 18px;
  font-size: 12px;
  line-height: 1.6;
}
.muted { color: var(--el-text-color-placeholder); }

.peer-meta-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-bottom: 12px;
}
.peer-meta { display: flex; flex-direction: column; gap: 4px; }
.need-remark :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px var(--el-color-warning) inset;
}

.prior-card { border-left: 3px solid var(--el-color-warning); }
.prior-placeholder { margin-bottom: 12px; }

.note-card { margin-bottom: 12px; }

.yn-native {
  width: 56px;
  height: 24px;
  font-size: 12px;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
}
.yn-tag { font-size: 12px; font-weight: 600; }
.yn-success { color: var(--el-color-success); }
.yn-danger { color: var(--el-color-danger); }
.yn-info { color: var(--el-text-color-secondary); }

.compile-hint {
  margin-top: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
