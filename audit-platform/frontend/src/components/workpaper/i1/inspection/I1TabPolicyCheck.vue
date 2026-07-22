<template>
  <div class="i1-tab-policy-check">
    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>一、审计目标</template>
      判断无形资产相关重大会计政策和会计估计的合理性（摊销方法、使用寿命、残值、减值迹象与测试频率），并与同行业及前期比较。
    </el-alert>

    <div class="methodology-context">
      <p>
        <b>CAS6：</b>寿命有限者系统摊销（§17）；方法反映消耗方式，无法可靠确定时用直线法（§19）；残值通常为零（§16）；每年复核寿命与方法（§21-22）。
        <b>CAS8：</b>存在迹象应测试（§4）；寿命不确定/未达预定用途者每年至少测试一次（§6）。
      </p>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="chip-wrap"><GtIndexChip value="wp:I1-4" :context-project-id="projectId" /></span>
        <GtIndexChip value="wp:I1-2" :context-project-id="projectId" />
        <GtIndexChip value="wp:I1-7" :context-project-id="projectId" />
        <GtIndexChip v-if="state.hasAnyChange.value" value="wp:S3-2" :context-project-id="projectId" />
        <el-tag size="small" :type="state.completenessOk.value ? 'success' : 'warning'">
          完成度 {{ state.completionProgress.value }}%
        </el-tag>
        <el-tag v-if="state.negativeJudgments.value.length" size="small" type="danger">
          不合理判断 {{ state.negativeJudgments.value.length }}
        </el-tag>
        <el-tag
          v-if="state.hasAnyChange.value"
          size="small"
          type="warning"
          class="nav-chip"
          @click="emit('navigate-sheet', 'I1-7')"
        >
          估计变更 → I1-7（{{ state.changedCategories.value.length }}）
        </el-tag>
        <el-tag v-if="state.lastAppliedTemplateLabel.value" size="small" type="info" effect="plain">
          {{ state.lastAppliedTemplateLabel.value }} · 示意须核年报
        </el-tag>
      </div>
      <div class="toolbar-right">
        <el-button size="small" :disabled="isReadonly" @click="handleSyncDetail">从 I1-2 带入</el-button>
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
        <el-button size="small" type="default" link @click="handleReview('I1-4')">💬 复核</el-button>
      </div>
    </div>

    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> CAS6/CAS8 段落评价</div>
        <div class="guide-step"><span class="step-num">②</span> 表A：按类别填政策 + 五维判断</div>
        <div class="guide-step"><span class="step-num">③</span> 表B：同业寿命/方法对标</div>
        <div class="guide-step"><span class="step-num">④</span> 有变更→表C原估计 → 说明/结论</div>
      </div>
    </div>

    <el-card shadow="never" class="gate-card" :class="{ 'gate-ok': state.completenessOk.value }">
      <template #header>
        <div class="section-title">
          <span>完成度闸门</span>
          <el-tag :type="state.completenessOk.value ? 'success' : 'danger'" size="small">
            {{ state.completenessOk.value ? '可关闭本检查项' : '未达标' }}
          </el-tag>
        </div>
      </template>
      <el-progress :percentage="state.completionProgress.value" :stroke-width="10" style="margin-bottom:10px" />
      <div class="gate-list">
        <div v-for="c in state.completeness.value" :key="c.id" class="gate-item" :class="{ ok: c.ok }">
          <span>{{ c.ok ? '✓' : '○' }} {{ c.label }}</span>
          <span class="gate-hint">{{ c.hint }}</span>
        </div>
      </div>
    </el-card>

    <el-alert
      v-if="state.hasAnyChange.value"
      type="warning"
      :closable="false"
      show-icon
      class="cross-alert"
    >
      <template #title>
        本期存在会计估计变更（{{ state.changedCategories.value.join('、') || '见表A' }}）：请填写表C，并视重要性同步
        <GtIndexChip value="wp:S3-2" :context-project-id="projectId" />
        估计变更程序；寿命明细复核见
        <el-button size="small" type="warning" link @click="emit('navigate-sheet', 'I1-7')">
          I1-7 使用寿命检查 →
        </el-button>
        <GtIndexChip value="wp:I1-7" :context-project-id="projectId" />。
      </template>
    </el-alert>

    <!-- CAS 段落 -->
    <div class="section-label">二、审计过程 — CAS6/CAS8 政策段落评价</div>
    <el-card
      v-for="(item, idx) in state.casItems.value"
      :key="item.key"
      shadow="never"
      class="check-card"
      :class="{ 'check-card-done': item.conclusion === '是' || item.conclusion === '不适用' }"
    >
      <template #header>
        <div class="section-title">
          <span class="check-title">{{ idx + 1 }}. {{ item.label }}</span>
          <div class="title-actions">
            <el-tag v-if="item.conclusion" :type="casTagType(item.conclusion)" size="small">
              {{ item.conclusion }}
            </el-tag>
            <el-button size="small" type="default" link @click="handleReview(`I1-4-${item.key}`)">💬</el-button>
          </div>
        </div>
      </template>
      <details class="cas-reference">
        <summary>{{ item.casRef.slice(0, 36) }}…（展开）</summary>
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
          placeholder="评价是否符合准则…"
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
          <span>（一）被审计单位的无形资产摊销政策</span>
          <el-button size="small" type="primary" :disabled="isReadonly" @click="state.addParamRow()">
            + 新增类别
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
        <el-table-column prop="category" label="类别" min-width="110" fixed>
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
            <div v-if="row.detailCount" class="peer-hint">I1-2 {{ row.detailCount }}笔</div>
          </template>
        </el-table-column>
        <el-table-column prop="usefulLife" label="使用寿命" width="100">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.usefulLife"
              size="small"
              placeholder="如10年"
              @change="state.persistParams()"
            />
            <span v-else>{{ row.usefulLife }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="amortMethod" label="摊销方法" width="140">
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
        <el-table-column label="经济利益" width="78" align="center">
          <template #header>
            <el-tooltip content="是否与相关资产所包含的经济利益预期实现方式相一致" placement="top">
              <span>经济利益</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <YnSelect v-model="row.matchesEconomicBenefit" :readonly="isReadonly" @change="state.persistParams()" />
          </template>
        </el-table-column>
        <el-table-column label="同业合理" width="78" align="center">
          <template #default="{ row }">
            <YnSelect v-model="row.reasonableVsPeers" :readonly="isReadonly" @change="state.persistParams()" />
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
          <span>（二）同行业其他公司的无形资产摊销政策</span>
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
          <el-table-column label="使用寿命" width="100">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                :model-value="cellOf(row, peer.peerId).usefulLife"
                size="small"
                placeholder="如10年"
                @update:model-value="(v: string) => state.updatePeerCell(row.category, peer.peerId, 'usefulLife', v)"
              />
              <span v-else>{{ cellOf(row, peer.peerId).usefulLife }}</span>
            </template>
          </el-table-column>
          <el-table-column label="摊销方法" width="120">
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
        <el-table-column prop="category" label="类别" min-width="100" />
        <el-table-column label="原使用寿命" width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.usefulLife"
              size="small"
              placeholder="变更前"
              @change="state.persistPriors()"
            />
            <span v-else>{{ row.usefulLife }}</span>
          </template>
        </el-table-column>
        <el-table-column label="原摊销方法" width="140">
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
        placeholder="记录同业选取标准、重大判断依据、估计变更影响、与I1-7寿命检查勾稽等…"
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
        title="完成度闸门未通过前，建议勿将本检查项标为已完成。"
      />
    </el-card>

    <details class="compile-hint" open>
      <summary>编制提示</summary>
      <ul>
        <li>本表对齐源模板：表A（政策+五维判断）→ 表B（同业寿命/方法）→ 有变更则表C（原估计）。</li>
        <li>优先「从 I1-2 带入」按类别汇总寿命/方法；寿命逐项复核请跳转 I1-7。</li>
        <li>行业模板仅为示意起步数据，引用前须核对手工年报附注并填写信息来源。</li>
        <li>估计变更属 CAS28 未来适用法；重大变更应联动 S3-2 并关注附注披露。</li>
        <li>「否」结论及表A「N」判断须在备注/说明中分析影响，必要时调整。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I1TabPolicyCheck.vue — I1-4 无形资产摊销/减值政策检查表
 * 对齐源 xlsx + H1-5 范式：CAS段落 + 表A/B/C + 完成度闸门
 */
import { computed, defineComponent, h, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import {
  useI1PolicyCheck,
  DEFAULT_CATEGORIES,
  type PeerPolicyRow,
  type Yn,
} from '../../composables/useI1PolicyCheck'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  'save': [itemId: string, value: any]
  'navigate-sheet': [sheetName: string]
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const allResponsesRef = computed(() => props.allResponses)

const state = useI1PolicyCheck(allResponsesRef as any, {
  onSave: (itemId, value) => emit('save', itemId, value),
})

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
  return row.cells?.[peerId] ?? { usefulLife: '', amortMethod: '' }
}

function casTagType(c: string): 'success' | 'danger' | 'info' {
  if (c === '是') return 'success'
  if (c === '否') return 'danger'
  return 'info'
}

function paramRowClass({ row }: { row: { meetsStandards?: string; matchesEconomicBenefit?: string; reasonableVsPeers?: string; changeReasonable?: string } }) {
  if ([row.meetsStandards, row.matchesEconomicBenefit, row.reasonableVsPeers, row.changeReasonable].includes('N')) {
    return 'neg-row'
  }
  return ''
}

function handleReview(id: string) {
  openReviewDialog(id)
}

async function handleSyncDetail() {
  const detailData = props.allResponses.get('I1-2-rows')
  const raw = (detailData as any)?.remark ?? (detailData as any)?.conclusion
  if (!raw) {
    ElMessageBox.alert('未找到 I1-2 明细表数据，请先完善明细表。', '提示')
    return
  }
  try {
    await ElMessageBox.confirm(
      '将按 I1-2 明细类别汇总使用寿命/摊销方法带入表A，已有判断字段尽量保留。是否继续？',
      '从 I1-2 带入',
      { type: 'warning', confirmButtonText: '确定', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed) || !parsed.length) {
      ElMessage.warning('I1-2 暂无明细行')
      return
    }
    const n = state.syncFromDetail(parsed)
    ElMessage.success(`已带入 ${n} 个类别`)
  } catch {
    ElMessage.error('I1-2 数据解析失败')
  }
}

function handleIndustryTpl(id: string) {
  state.applyIndustryTemplate(id)
  ElMessage.success('已套用示意性行业模板（须核对手工年报附注后再作证据）')
}

function applyConclusionTpl() {
  state.overallConclusion.value = state.suggestConclusionTemplate()
  state.persistConclusion()
}
</script>

<style scoped>
.i1-tab-policy-check {
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
