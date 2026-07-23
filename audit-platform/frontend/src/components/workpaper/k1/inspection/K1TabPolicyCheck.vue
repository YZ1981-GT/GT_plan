<!--
  K1TabPolicyCheck.vue — K1-6 信用减值损失会计政策检查

  编制逻辑：政策理解 → 历史数据验证 → 前瞻性 → 同业对标 → 形成结论
  组合划分须与 K1-7 三阶段划分、K1-8 坏账测算一致。
-->
<template>
  <div class="k1-tab-policy-check">
    <div class="methodology-context">
      <p>K1-6 评价其他应收款预期信用损失会计政策是否符合 CAS 22，并与前期及同行业对比，关注是否利用会计政策/估计变更操纵利润，是否存在管理层偏向迹象。组合划分结果应贯穿 K1-7、K1-8。</p>
    </div>

    <div class="section-head">
      <h3 class="sheet-title">K1-6 信用减值损失会计政策检查</h3>
      <div class="head-actions">
        <el-tag size="small" type="info">完成度 {{ completionScore.done }}/{{ completionScore.total }}</el-tag>
        <el-button size="small" @click="onExportTemplate">导出模板</el-button>
        <el-button size="small" @click="onExportData">导出数据</el-button>
        <el-upload
          v-if="!isReadonly"
          :show-file-list="false"
          accept=".xlsx,.xls"
          :auto-upload="false"
          :on-change="onImportChange"
        >
          <el-button size="small" :loading="importing">导入 Excel</el-button>
        </el-upload>
        <GtReviewTrigger section-id="K1-6-policy-header" />
        <el-button size="small" type="primary" link @click="handleReview">💬 复核</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title><span class="ao-title">一、审计目标</span></template>
      <p class="ao-text">其他应收款、坏账准备以恰当的金额包括在财务报表中，与之相关的计价或分摊调整已恰当记录，相关披露已得到恰当计量和描述。</p>
    </el-alert>

    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">二、审计程序</span></template>
      <el-input
        v-model="auditProcedures"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 6 }"
        :disabled="isReadonly"
        @change="persist"
      />
    </el-card>

    <!-- (一) 具体减值政策说明 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">三、(一) 具体减值政策说明</span>
          <el-button v-if="!isReadonly" size="small" @click="addCombo(); persist()">＋ 新增组合</el-button>
        </div>
      </template>
      <p class="hint-text">
        当单项其他应收款无法以合理成本评估预期信用损失信息时，依据信用风险特征划分为若干组合。
        共同信用风险特征包括：金融工具类型、信用风险评级、担保物类型、账龄、债务人所处行业/地理位置等。
      </p>
      <el-input
        v-model="policyDesc"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 5 }"
        :disabled="isReadonly"
        placeholder="摘录或概述被审计单位披露的减值政策（单项计提条件、组合划分逻辑、损失率确定方法等）..."
        class="policy-desc-input"
        @change="persist"
      />
      <el-table :data="combos" border size="small" class="policy-table">
        <el-table-column label="组合" width="130">
          <template #default="{ $index }">其他应收款组合{{ $index + 1 }}</template>
        </el-table-column>
        <el-table-column label="划分依据（款项性质）" min-width="200">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.basis" size="small" placeholder="如：押金和保证金" @change="persist" />
            <span v-else>{{ row.basis || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="损失率确定方法" min-width="160">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.method" size="small" clearable filterable allow-create @change="persist">
              <el-option v-for="m in LOSS_METHODS" :key="m" :label="m" :value="m" />
            </el-select>
            <span v-else>{{ row.method || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="persist" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" align="center">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="removeCombo(row.id); persist()">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <!-- K1-8 反向校验 -->
      <el-alert
        v-if="k18ComboConsistency.hasK18Data"
        :type="k18ComboConsistency.isConsistent ? 'success' : 'warning'"
        :closable="false"
        class="k18-reconcile"
      >
        <template #title>
          <span>K1-8 组合名称勾稽{{ k18ComboConsistency.isConsistent ? ' — 一致' : ' — 存在差异' }}</span>
        </template>
        <div v-if="k18ComboConsistency.matched.length" class="reconcile-row">
          <span class="muted">已匹配 {{ k18ComboConsistency.matched.length }} 组：</span>
          <el-tag v-for="m in k18ComboConsistency.matched" :key="m.k16Basis" size="small" type="success" class="match-tag">
            {{ m.k16Basis }} ↔ {{ m.k18GroupName }}
          </el-tag>
        </div>
        <div v-if="k18ComboConsistency.onlyInK16.length" class="reconcile-row">
          <span class="warn-label">仅 K1-6 有：</span>
          <el-tag v-for="n in k18ComboConsistency.onlyInK16" :key="n" size="small" type="warning">{{ n }}</el-tag>
        </div>
        <div v-if="k18ComboConsistency.onlyInK18.length" class="reconcile-row">
          <span class="warn-label">仅 K1-8 有：</span>
          <el-tag v-for="n in k18ComboConsistency.onlyInK18" :key="n" size="small" type="danger">{{ n }}</el-tag>
        </div>
        <div v-if="!isReadonly" class="reconcile-actions">
          <el-button size="small" @click="onSyncFromK18">从 K1-8 同步组合名称</el-button>
          <el-button size="small" link type="primary" @click="goSheet('K1-8')">打开 K1-8 →</el-button>
        </div>
      </el-alert>
      <el-alert v-else type="info" :closable="false" class="k18-reconcile">
        <template #title><span>K1-8 尚未填写</span></template>
        <p class="ao-text">完成 K1-8 坏账测算后，可在此反向校验组合名称是否与 K1-6 一致。</p>
        <el-button size="small" link type="primary" @click="goSheet('K1-8')">前往 K1-8 →</el-button>
      </el-alert>

      <div class="cross-links">
        <span class="muted">组合划分应与以下底稿一致：</span>
        <el-button size="small" link type="primary" @click="goSheet('K1-7')">K1-7 三阶段 →</el-button>
        <el-button size="small" link type="primary" @click="goSheet('K1-8')">K1-8 坏账测算 →</el-button>
      </div>
    </el-card>

    <!-- K2 账龄-预期信用损失率表（K1 循环内嵌引用，供 K1-8 账龄组合推送） -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">K2 账龄—预期信用损失率表（引用）</span>
          <div v-if="!isReadonly" class="k2-actions">
            <el-button size="small" @click="onPullK2FromK18">从 K1-8 回填损失率</el-button>
            <el-button size="small" type="primary" @click="onPushK2ToK18">推送至 K1-8 账龄组合</el-button>
          </div>
        </div>
      </template>
      <p class="hint-text">
        基于历史坏账损失率及前瞻性调整确定各账龄段预期信用损失率；调整后损失率可一键写入 K1-8 对应账龄组合的「损失率」列（须先完成 K1-6/K1-8 组合名称匹配）。
      </p>
      <el-table :data="k2LossRates" border size="small" class="policy-table">
        <el-table-column label="账龄段" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.agingBucket" size="small" @change="persist" />
            <span v-else>{{ row.agingBucket }}</span>
          </template>
        </el-table-column>
        <el-table-column label="历史损失率" width="130" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.historicalRate"
              size="small"
              :min="0"
              :max="1"
              :step="0.01"
              :precision="4"
              controls-position="right"
              class="rate-input"
              @change="persist"
            />
            <span v-else>{{ formatRate(row.historicalRate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="调整后损失率" width="130" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.adjustedRate"
              size="small"
              :min="0"
              :max="1"
              :step="0.01"
              :precision="4"
              controls-position="right"
              class="rate-input"
              @change="persist"
            />
            <span v-else>{{ formatRate(row.adjustedRate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="persist" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- (二) 历史坏账损失 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">三、(二) 被审计单位历史坏账损失情况</span>
          <el-button v-if="aiAvailable && !isReadonly" size="small" link type="primary" :loading="aiLoading" @click="onAiSection('historical')">
            🤖 AI 辅助
          </el-button>
        </div>
      </template>
      <p class="hint-text">说明历史损失数据来源（账龄分析、核销记录、管理层提供等）及验证程序，评价历史损失率/迁徙率是否可靠。</p>
      <el-input
        v-model="historicalLoss"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="描述历史坏账损失/核销情况、数据期间、验证程序及结论..."
        @change="persist"
      />
    </el-card>

    <!-- (三) 前瞻性信息 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">三、(三) 前瞻性信息的来源及其影响</span>
          <el-button v-if="aiAvailable && !isReadonly" size="small" link type="primary" :loading="aiLoading" @click="onAiSection('forward')">
            🤖 AI 辅助
          </el-button>
        </div>
      </template>
      <p class="hint-text">前瞻性信息来源可包括：内部预测、第三方数据、外部专家工作等；说明获取途径及验证程序。</p>
      <el-input
        v-model="forwardLooking"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="说明前瞻性信息来源及其对预期信用损失率的影响..."
        @change="persist"
      />
    </el-card>

    <!-- 与前期对比 -->
    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">与前期会计政策对比</span></template>
      <el-input
        v-model="priorYearPolicy"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 5 }"
        :disabled="isReadonly"
        placeholder="与上期政策是否一致？如有变更，说明变更原因、审批程序及对 ECL 的影响..."
        @change="persist"
      />
    </el-card>

    <!-- (四) 同行业对比 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">三、(四) 同行业公司的会计政策</span>
          <el-button v-if="!isReadonly" size="small" @click="addPeerRow(); persist()">＋ 新增同行</el-button>
        </div>
      </template>
      <el-table :data="peerRows" border size="small" class="policy-table" empty-text="可点击下方示例「套用」，或手动新增">
        <el-table-column label="公司" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.company" size="small" @change="persist" />
            <span v-else>{{ row.company || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="会计政策摘要" min-width="320">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.policyText" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }" size="small" @change="persist" />
            <span v-else class="pre-wrap">{{ row.policyText || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="与被审计单位可比" width="130" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.comparable" size="small" clearable @change="persist">
              <el-option v-for="o in COMPARABLE_OPTIONS" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.comparable || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" align="center">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="removePeerRow(row.id); persist()">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-input
        v-model="peerComparison"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="综合对比结论：与同行业相比是否存在重大差异？是否利用政策/估计变更调节利润？"
        class="peer-summary"
        @change="persist"
      />
    </el-card>

    <!-- 上市公司示例 -->
    <el-card shadow="never" class="ref-card">
      <template #header><span class="card-title">📚 上市公司会计政策披露示例参考</span></template>
      <p class="hint-text">以下为部分上市公司其他应收款减值组合披露示例，可点击「套用」填入同业对比表。</p>
      <el-collapse>
        <el-collapse-item v-for="ex in listedExamples" :key="ex.company" :name="ex.company">
          <template #title>
            <span class="ex-company">{{ ex.company }}</span>
            <el-button v-if="!isReadonly" size="small" type="primary" link class="ex-apply" @click.stop="applyExample(ex)">套用 →</el-button>
          </template>
          <p class="ex-text">{{ ex.text }}</p>
        </el-collapse-item>
      </el-collapse>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">四、审计说明</span>
          <el-button v-if="aiAvailable && !isReadonly" size="small" link type="primary" :loading="aiLoading" @click="onAiSection('note')">
            🤖 AI 生成
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="综合说明政策检查过程、主要发现、与 K1-7/K1-8 的衔接..."
        @change="persist"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header><span class="card-title">五、审计结论</span></template>
      <el-select
        v-model="conclusionOption"
        :disabled="isReadonly"
        size="small"
        class="concl-select"
        placeholder="选择结论模板"
        @change="onConclusionOption"
      >
        <el-option label="A、政策合理且一贯执行" value="A" />
        <el-option label="B、除上述关注事项外，政策合理" value="B" />
        <el-option label="C、存在重大不当或管理层偏向" value="C" />
      </el-select>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 5 }"
        :disabled="isReadonly"
        placeholder="形成审计结论..."
        @change="persist"
      />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示（CAS 22）</summary>
      <ul>
        <li>组合划分：押金/保证金、关联公司、代垫款、员工备用金等为常见示例，须按被审计单位实际业务调整</li>
        <li>历史损失率/迁徙率须说明数据来源及验证程序；前瞻性信息须说明来源及合理性</li>
        <li>与前期及同行业对比，关注政策/估计变更是否操纵利润；回顾上期估计与当期实际，考虑管理层偏向</li>
        <li>本表组合划分须与 K1-7 三阶段划分、K1-8 坏账测算勾稽一致；K2 账龄损失率表可推送至 K1-8</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { inject, onMounted, toRef } from 'vue'
import { ElMessage } from 'element-plus'
import type { UploadFile } from 'element-plus'
import http from '@/utils/http'
import {
  useK1PolicyCheck,
  K1_LISTED_POLICY_EXAMPLES,
  K1_POLICY_CONCLUSION_TEMPLATES,
} from '../../composables/useK1PolicyCheck'
import { useK1ImportExport } from '../../composables/useK1ImportExport'
import { useK1AiGenerate } from '../../composables/useK1AiGenerate'
import { K18_STORAGE_KEY } from '../../composables/k1CrossHelpers'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheet: string): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const LOSS_METHODS = ['账龄分析法', '迁徙率模型', '单项评估', '固定比例', '其他']
const COMPARABLE_OPTIONS = ['是', '否', '部分一致'] as const
const listedExamples = K1_LISTED_POLICY_EXAMPLES

const {
  combos,
  peerRows,
  k2LossRates,
  policyDesc,
  auditProcedures,
  historicalLoss,
  forwardLooking,
  priorYearPolicy,
  peerComparison,
  auditNote,
  conclusion,
  conclusionOption,
  completionScore,
  k18ComboConsistency,
  load,
  addCombo,
  removeCombo,
  addPeerRow,
  removePeerRow,
  applyListedExample,
  buildSaveItems,
  syncCombosFromK18,
  pullK2RatesFromK18Sheet,
  pushK2RatesToK18,
} = useK1PolicyCheck({ allResponses: toRef(props, 'allResponses') })

const { isImporting: importing, exportTemplate, exportData, importData } = useK1ImportExport({
  wpId: toRef(props, 'wpId'),
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useK1AiGenerate(toRef(props, 'wpId'))

onMounted(() => load())

function persist() {
  for (const item of buildSaveItems()) {
    props.allResponses.set(item.item_id, item)
    emit('save', item.item_id, { remark: item.remark, conclusion: item.conclusion })
  }
}

function applyExample(ex: { company: string; text: string }) {
  applyListedExample(ex.company, ex.text)
  persist()
  ElMessage.success(`已套用 ${ex.company} 至同业对比表`)
}

function onConclusionOption(val: string) {
  if (K1_POLICY_CONCLUSION_TEMPLATES[val] && !conclusion.value) {
    conclusion.value = K1_POLICY_CONCLUSION_TEMPLATES[val]
  }
  persist()
}

async function onAiSection(section: 'historical' | 'forward' | 'note') {
  const ctx = {
    comboCount: combos.value.filter((c) => c.basis.trim()).length,
    combos: combos.value.map((c) => c.basis).filter(Boolean),
    policyDesc: policyDesc.value,
    priorYearPolicy: priorYearPolicy.value,
    peerCount: peerRows.value.length,
  }
  let existing = ''
  let title = ''
  if (section === 'historical') {
    existing = historicalLoss.value
    title = 'AI 辅助 — 历史坏账损失分析'
  } else if (section === 'forward') {
    existing = forwardLooking.value
    title = 'AI 辅助 — 前瞻性信息分析'
  } else {
    existing = auditNote.value
    title = 'AI 生成 K1-6 审计说明'
  }
  const content = await generateAndConfirm('policy-check', existing, ctx, title)
  if (!content) return
  if (section === 'historical') historicalLoss.value = content
  else if (section === 'forward') forwardLooking.value = content
  else auditNote.value = content
  persist()
}

function goSheet(sheet: string) {
  emit('navigate-sheet', sheet)
}

function formatRate(v: number): string {
  if (!v) return '-'
  return `${(v * 100).toFixed(2)}%`
}

function onSyncFromK18() {
  const { added, updated } = syncCombosFromK18()
  persist()
  ElMessage.success(`已从 K1-8 同步：新增 ${added} 组、更新 ${updated} 组名称`)
}

function onPullK2FromK18() {
  const count = pullK2RatesFromK18Sheet()
  persist()
  if (count > 0) ElMessage.success(`已从 K1-8 回填 ${count} 个账龄段损失率`)
  else ElMessage.info('K1-8 账龄组合中暂无有效损失率')
}

function onPushK2ToK18() {
  if (!k18ComboConsistency.value.hasK18Data) {
    ElMessage.warning('请先在 K1-8 填写坏账测算')
    return
  }
  if (!k18ComboConsistency.value.matched.some((m) => m.section === 'aging')) {
    ElMessage.warning('K1-6 与 K1-8 账龄组合名称未匹配，请先同步组合名称')
    return
  }
  const { updatedCells, written } = pushK2RatesToK18()
  if (written) {
    emit('save', K18_STORAGE_KEY, { remark: props.allResponses.get(K18_STORAGE_KEY)?.remark })
    ElMessage.success(`已推送 ${updatedCells} 个账龄段损失率至 K1-8`)
  } else {
    ElMessage.info('无需要更新的损失率（请填写调整后损失率）')
  }
}

async function reloadFromServer() {
  try {
    const res = await http.get(`/api/workpapers/${props.wpId}/checklist-responses`, { _silent: true } as any)
    const items: any[] = Array.isArray(res?.data?.data) ? res.data.data : Array.isArray(res?.data) ? res.data : []
    for (const item of items) {
      const id = item.item_id || item.itemId
      if (!id || (!String(id).startsWith('K1-6') && id !== 'K1-k2-aging-loss-rates')) continue
      props.allResponses.set(id, {
        item_id: id,
        remark: item.remark ?? null,
        conclusion: item.conclusion ?? null,
      })
    }
    load()
  } catch {
    load()
  }
}

function onExportTemplate() {
  exportTemplate('K1-6')
}

function onExportData() {
  exportData('K1-6')
}

async function onImportChange(uploadFile: UploadFile) {
  const raw = uploadFile.raw
  if (!raw) return
  const result = await importData('K1-6', raw)
  if (result) await reloadFromServer()
}

function handleReview() {
  openReviewDialog('K1-6-policy')
}
</script>

<style scoped>
.k1-tab-policy-check { padding: 12px 14px; font-size: var(--wp-font-size, 13px); }
.methodology-context {
  border-left: 4px solid var(--el-color-warning); background: #fffbeb;
  padding: 10px 14px; margin-bottom: 12px; font-size: 12px; color: var(--el-text-color-regular); line-height: 1.6;
}
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.sheet-title { font-size: 15px; font-weight: 600; margin: 0; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.audit-objective { margin-bottom: 10px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-title { font-weight: 600; }
.ao-text { margin: 4px 0 0; line-height: 1.6; font-size: 12px; }
.section-card { margin-bottom: 10px; }
.section-card :deep(.el-card__header) { padding: 8px 14px; }
.section-card :deep(.el-card__body) { padding: 12px 14px; }
.card-title { font-weight: 600; }
.card-header-row { display: flex; align-items: center; justify-content: space-between; }
.hint-text { font-size: 12px; color: var(--el-text-color-secondary); line-height: 1.6; margin: 0 0 10px; }
.policy-desc-input { margin-bottom: 10px; }
.policy-table { font-size: var(--wp-font-size, 13px); margin-bottom: 8px; }
.k18-reconcile { margin-top: 10px; }
.reconcile-row { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-top: 6px; font-size: 12px; }
.match-tag { margin: 2px 0; }
.warn-label { color: var(--el-color-warning); font-weight: 500; }
.reconcile-actions { margin-top: 8px; display: flex; gap: 8px; align-items: center; }
.k2-actions { display: flex; gap: 8px; }
.rate-input { width: 100%; }
.cross-links { display: flex; align-items: center; gap: 8px; margin-top: 8px; font-size: 12px; }
.muted { color: var(--el-text-color-secondary); }
.peer-summary { margin-top: 10px; }
.pre-wrap { white-space: pre-wrap; line-height: 1.6; }
.ref-card { margin-bottom: 10px; }
.ref-card :deep(.el-card__header) { padding: 8px 14px; }
.ref-card :deep(.el-card__body) { padding: 12px 14px; }
.ex-company { font-weight: 600; }
.ex-apply { margin-left: 12px; }
.ex-text { font-size: 12px; line-height: 1.7; color: var(--el-text-color-regular); margin: 0; }
.conclusion-card { margin-bottom: 10px; }
.conclusion-card :deep(.el-card__header) { padding: 8px 14px; }
.conclusion-card :deep(.el-card__body) { padding: 12px 14px; }
.concl-select { width: 100%; margin-bottom: 8px; }
.compile-hint { margin-top: 6px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 18px; margin-top: 8px; line-height: 1.7; }
</style>
