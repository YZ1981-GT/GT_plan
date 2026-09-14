<script setup lang="ts">
/**
 * GtB19Bundle — B19 识别关联方
 *
 * Tab：
 * 1. 程序表（GtAProgramConsole）
 * 2. 管理层关联方清单 → related_party_registry（结构化真源，全平台各循环关联方核对据此匹配）
 * 3. 关联方交易台账 → related_party_transactions
 * 4. 未披露关联方扫描（B19-1）→ checklist_responses，异常迹象推送 B50 风险因素
 *
 * 关系/交易类型枚举对齐后端 VALID_RELATION_TYPES / VALID_TRANSACTION_TYPES。
 */
import { ref, watch, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtAProgramConsole from './GtAProgramConsole.vue'
import { useB19RelatedParty, type RelatedParty, type RelatedPartyTxn } from './b19/useB19RelatedParty'
import { useRegisterRelatedParty } from './b19/useRegisterRelatedParty'
import {
  RELATION_TYPE_OPTIONS,
  RELATION_TYPE_LABEL,
  TRANSACTION_TYPE_OPTIONS,
  TRANSACTION_TYPE_LABEL,
  EXIST_OPTIONS,
  UNDISCLOSED_SECTIONS,
} from './b19/b19Presets'

const props = defineProps<{
  wpId: string
  projectId: string
  sheetName?: string
  readonly?: boolean
}>()

const TABS = [
  { id: 'program', label: '程序表', aliases: ['program', 'B19识别关联方程序表', '识别关联方程序表'] },
  { id: 'list', label: '管理层关联方清单', aliases: ['B19-1', '管理层提供的关联方清单', 'list'] },
  { id: 'txn', label: '关联方交易台账', aliases: ['txn', '交易'] },
  { id: 'undisclosed', label: '未披露关联方扫描', aliases: ['undisclosed', '未披露', '异常关联交易'] },
]

const route = useRoute()
const active = ref('program')

const rp = useB19RelatedParty(props.projectId, props.wpId)
const { registerSuspected } = useRegisterRelatedParty(props.projectId)

// 程序表适用性提示（按项目类型裁剪 IPO/新三板/首次承接专用步骤）
const APPLICABILITY_HINTS = [
  { tag: 'IPO 项目', desc: '步骤四/十一/十六等标注「适用于 IPO 项目」的程序' },
  { tag: '新三板业务', desc: '步骤二十二/二十等标注「适用于新三板业务」的程序' },
  { tag: '首次承接', desc: '步骤二「与前任审计师清单比较」标注「适用于首次承接」' },
]

/** ③ 反向回流：登记扫描中识别出的疑似关联方到 B19 清单 */
async function handleRegisterSuspected() {
  const ok = await registerSuspected('', { source: 'B19-1 未披露关联方扫描' })
  if (ok) await rp.loadParties()
}

// ─── Tab 解析 ────────────────────────────────────────────────────────
function resolveTabId(raw?: string | null): string {
  if (!raw) return 'program'
  const s = String(raw).trim()
  for (const t of TABS) {
    if (t.id === s) return t.id
    if (t.aliases.some((a) => a === s || s.includes(a) || a.includes(s))) return t.id
  }
  return 'program'
}
function resolveActiveTab(): string {
  const view = route.query.view as string | undefined
  const qSheet = route.query.sheet as string | undefined
  if (view) return resolveTabId(view)
  if (qSheet && resolveTabId(qSheet) === 'list') return 'list'
  return resolveTabId(props.sheetName || qSheet)
}
watch(() => props.sheetName, () => { active.value = resolveActiveTab() })
watch(() => [route.query.view, route.query.sheet] as const, () => { active.value = resolveActiveTab() })

onMounted(() => {
  active.value = resolveActiveTab()
  rp.loadParties()
  rp.loadScan()
})

// ─── 关联方清单 CRUD 弹窗 ────────────────────────────────────────────
const partyDialog = ref(false)
const editingPartyId = ref<string | null>(null)
function emptyDetail() {
  return { enterprise_type: '', registered_place: '', legal_rep: '', business_nature: '', registered_capital: '', shareholding_ratio: '' }
}
const partyForm = ref<{ name: string; relation_type: string; is_controlled_by_same_party: boolean; detail: Record<string, string> }>({
  name: '', relation_type: 'subsidiary', is_controlled_by_same_party: false, detail: emptyDetail(),
})

function openCreateParty() {
  editingPartyId.value = null
  partyForm.value = { name: '', relation_type: 'subsidiary', is_controlled_by_same_party: false, detail: emptyDetail() }
  partyDialog.value = true
}
function openEditParty(row: RelatedParty) {
  editingPartyId.value = row.id
  partyForm.value = {
    name: row.name,
    relation_type: row.relation_type,
    is_controlled_by_same_party: row.is_controlled_by_same_party,
    detail: { ...emptyDetail(), ...(row.detail || {}) },
  }
  partyDialog.value = true
}
async function submitParty() {
  const name = partyForm.value.name.trim()
  if (!name) return ElMessage.warning('请填写关联方名称')
  try {
    if (editingPartyId.value) {
      await rp.updateParty(editingPartyId.value, { ...partyForm.value, name })
      ElMessage.success('已更新')
    } else {
      await rp.createParty({ ...partyForm.value, name })
    }
    partyDialog.value = false
  } catch { /* http 拦截器已提示 */ }
}
async function removeParty(row: RelatedParty) {
  try {
    await ElMessageBox.confirm(`确认删除关联方「${row.name}」？相关交易记录不会自动删除。`, '删除确认', { type: 'warning' })
    await rp.deleteParty(row.id)
  } catch { /* cancel */ }
}

// ─── 交易台账 CRUD 弹窗 ──────────────────────────────────────────────
const txnDialog = ref(false)
const editingTxnId = ref<string | null>(null)
const txnForm = ref<{ related_party_id: string; amount: number | null; transaction_type: string; is_arms_length: boolean | null }>({
  related_party_id: '', amount: null, transaction_type: 'sales', is_arms_length: null,
})
function partyName(id: string): string {
  return rp.parties.value.find((p) => p.id === id)?.name || '（已删除）'
}
function openCreateTxn() {
  if (!rp.parties.value.length) return ElMessage.warning('请先在「管理层关联方清单」中登记关联方')
  editingTxnId.value = null
  txnForm.value = { related_party_id: rp.parties.value[0].id, amount: null, transaction_type: 'sales', is_arms_length: null }
  txnDialog.value = true
}
function openEditTxn(row: RelatedPartyTxn) {
  editingTxnId.value = row.id
  txnForm.value = {
    related_party_id: row.related_party_id,
    amount: row.amount != null ? Number(row.amount) : null,
    transaction_type: row.transaction_type,
    is_arms_length: row.is_arms_length,
  }
  txnDialog.value = true
}
async function submitTxn() {
  if (!txnForm.value.related_party_id) return ElMessage.warning('请选择关联方')
  try {
    if (editingTxnId.value) {
      await rp.updateTxn(editingTxnId.value, { ...txnForm.value })
      ElMessage.success('已更新')
    } else {
      await rp.createTxn({ ...txnForm.value })
    }
    txnDialog.value = false
  } catch { /* handled */ }
}
async function removeTxn(row: RelatedPartyTxn) {
  try {
    await ElMessageBox.confirm('确认删除该关联交易记录？', '删除确认', { type: 'warning' })
    await rp.deleteTxn(row.id)
  } catch { /* cancel */ }
}

// ─── 未披露扫描 ──────────────────────────────────────────────────────
const existCount = computed(() => rp.collectExistFactors().length)
function cell(si: number, ii: number) {
  return rp.ensureCell(si, ii)
}
</script>

<template>
  <div class="gt-b19-bundle">
    <el-tabs v-model="active">
      <!-- 1. 程序表 -->
      <el-tab-pane label="程序表" name="program" lazy>
        <el-alert type="info" :closable="true" show-icon class="gt-b19-bundle__alert" title="程序适用性裁剪提示">
          <template #default>
            <div class="gt-b19-bundle__hint">
              部分程序仅适用于特定项目类型，非适用项目可按「类别」筛选后多选批量裁剪（填写裁剪理由）：
              <ul class="gt-b19-bundle__hint-list">
                <li v-for="h in APPLICABILITY_HINTS" :key="h.tag">
                  <el-tag size="small" type="warning">{{ h.tag }}</el-tag>
                  <span>{{ h.desc }}</span>
                </li>
              </ul>
            </div>
          </template>
        </el-alert>
        <GtAProgramConsole :wp-id="wpId" :embedded="true" :readonly="readonly" />
      </el-tab-pane>

      <!-- 2. 管理层关联方清单 -->
      <el-tab-pane label="管理层关联方清单" name="list" lazy>
        <el-alert
          type="info" :closable="false" show-icon
          title="被审计单位关联方清单（结构化主数据）"
          description="此清单是全平台各循环（D1/D2/D5/D6/D7/E1/F1/F2/F4/F5/G1/H1/H2/K1 等）关联方完整性核对的唯一数据源。请完整录入关联方名称与关系类型。"
          class="gt-b19-bundle__alert"
        />
        <div class="gt-b19-bundle__toolbar">
          <el-button type="primary" :disabled="readonly" @click="openCreateParty">+ 新增关联方</el-button>
          <span class="gt-b19-bundle__count">共 {{ rp.parties.value.length }} 个关联方</span>
        </div>
        <el-table :data="rp.parties.value" v-loading="rp.loadingParties.value" size="small" border>
          <el-table-column type="index" label="#" width="50" />
          <el-table-column prop="name" label="公司全称 / 姓名" min-width="220" />
          <el-table-column label="关联关系" width="160">
            <template #default="{ row }">
              <el-tag size="small">{{ RELATION_TYPE_LABEL[row.relation_type] || row.relation_type }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="同一控制" width="90" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.is_controlled_by_same_party" type="warning" size="small">是</el-tag>
              <span v-else class="gt-b19-bundle__muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="企业类型" min-width="120">
            <template #default="{ row }">{{ row.detail?.enterprise_type || '—' }}</template>
          </el-table-column>
          <el-table-column label="法人代表" min-width="100">
            <template #default="{ row }">{{ row.detail?.legal_rep || '—' }}</template>
          </el-table-column>
          <el-table-column label="持股%" width="80" align="right">
            <template #default="{ row }">{{ row.detail?.shareholding_ratio || '—' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="140" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" :disabled="readonly" @click="openEditParty(row)">编辑</el-button>
              <el-button link type="danger" size="small" :disabled="readonly" @click="removeParty(row)">删除</el-button>
            </template>
          </el-table-column>
          <template #empty>暂无关联方，点击「新增关联方」开始录入</template>
        </el-table>
      </el-tab-pane>

      <!-- 3. 关联方交易台账 -->
      <el-tab-pane label="关联方交易台账" name="txn" lazy>
        <el-alert
          type="info" :closable="false" show-icon
          title="关联方交易台账"
          description="登记本期已识别的关联方交易（类型/金额/定价是否公允），供 A7 关联方汇总及各循环关联方检查表引用。"
          class="gt-b19-bundle__alert"
        />
        <div class="gt-b19-bundle__toolbar">
          <el-button type="primary" :disabled="readonly" @click="openCreateTxn">+ 新增关联交易</el-button>
          <span class="gt-b19-bundle__count">共 {{ rp.transactions.value.length }} 笔交易</span>
        </div>
        <el-table :data="rp.transactions.value" v-loading="rp.loadingTxns.value" size="small" border>
          <el-table-column type="index" label="#" width="50" />
          <el-table-column label="关联方" min-width="200">
            <template #default="{ row }">{{ partyName(row.related_party_id) }}</template>
          </el-table-column>
          <el-table-column label="交易类型" width="180">
            <template #default="{ row }">
              <el-tag size="small" type="info">{{ TRANSACTION_TYPE_LABEL[row.transaction_type] || row.transaction_type }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="金额（元）" width="160" align="right">
            <template #default="{ row }">{{ row.amount != null ? Number(row.amount).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—' }}</template>
          </el-table-column>
          <el-table-column label="定价公允" width="100" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.is_arms_length === true" type="success" size="small">公允</el-tag>
              <el-tag v-else-if="row.is_arms_length === false" type="danger" size="small">非公允</el-tag>
              <span v-else class="gt-b19-bundle__muted">未评价</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="140" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" :disabled="readonly" @click="openEditTxn(row)">编辑</el-button>
              <el-button link type="danger" size="small" :disabled="readonly" @click="removeTxn(row)">删除</el-button>
            </template>
          </el-table-column>
          <template #empty>暂无关联交易记录</template>
        </el-table>
      </el-tab-pane>

      <!-- 4. 未披露关联方扫描 -->
      <el-tab-pane label="未披露关联方扫描" name="undisclosed" lazy>
        <el-alert
          type="warning" :closable="false" show-icon
          title="识别未披露的关联方关系及异常关联交易（CAS 1323 / 审计准则问题解答第6号）"
          description="逐项判断是否存在下列迹象；标记为「存在」的应填写信息来源并制定拟执行程序，可一键推送至 B50 风险因素识别。"
          class="gt-b19-bundle__alert"
        />
        <div class="gt-b19-bundle__toolbar">
          <el-button type="primary" :disabled="readonly" @click="rp.saveScan()">保存扫描结果</el-button>
          <el-button type="warning" plain :disabled="readonly" @click="rp.pushToB50()">推送 {{ existCount }} 项迹象至 B50</el-button>
          <el-button type="success" plain :disabled="readonly" @click="handleRegisterSuspected">+ 登记疑似关联方</el-button>
        </div>

        <div v-for="(sec, si) in UNDISCLOSED_SECTIONS" :key="sec.key" class="gt-b19-bundle__section">
          <h4 class="gt-b19-bundle__section-title">{{ sec.title }}</h4>
          <el-table :data="sec.items" size="small" border row-key="key">
            <el-table-column label="#" width="46" align="center">
              <template #default="{ $index }">{{ $index + 1 }}</template>
            </el-table-column>
            <el-table-column label="迹象特征" min-width="360">
              <template #default="{ row }"><span class="gt-b19-bundle__feature">{{ row.text }}</span></template>
            </el-table-column>
            <el-table-column label="是否存在" width="130">
              <template #default="{ $index }">
                <el-select v-model="cell(si, $index).exist" size="small" :disabled="readonly" placeholder="—" clearable>
                  <el-option v-for="o in EXIST_OPTIONS" :key="o.value" :label="o.value" :value="o.value" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="索引号 / 信息来源" min-width="180">
              <template #default="{ $index }">
                <el-input v-model="cell(si, $index).source" size="small" :disabled="readonly" placeholder="索引号或信息来源" />
              </template>
            </el-table-column>
            <el-table-column label="拟执行的审计程序" min-width="200">
              <template #default="{ $index }">
                <el-input v-model="cell(si, $index).program" size="small" :disabled="readonly" type="textarea" :autosize="{ minRows: 1 }" placeholder="拟执行程序" />
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div class="gt-b19-bundle__summary">
          <h4 class="gt-b19-bundle__section-title">汇总识别的风险因素（记录并区分财务报表层次 / 认定层次风险，制订初步应对 → B50-1）</h4>
          <el-input
            v-model="rp.overallSummary.value" type="textarea" :autosize="{ minRows: 4 }" :disabled="readonly"
            placeholder="汇总上述所有已发现的迹象，区分财务报表层次的风险和认定层次的风险，制订初步的应对措施。"
          />
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 关联方 CRUD 弹窗 -->
    <el-dialog v-model="partyDialog" :title="editingPartyId ? '编辑关联方' : '新增关联方'" width="480px">
      <el-form label-width="110px">
        <el-form-item label="公司全称/姓名" required>
          <el-input v-model="partyForm.name" placeholder="关联方名称" />
        </el-form-item>
        <el-form-item label="关联关系" required>
          <el-select v-model="partyForm.relation_type" style="width: 100%">
            <el-option v-for="o in RELATION_TYPE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="同一控制">
          <el-switch v-model="partyForm.is_controlled_by_same_party" active-text="受同一方控制" />
        </el-form-item>
        <el-divider content-position="left">工商信息（供披露/台账，选填）</el-divider>
        <el-form-item label="企业类型">
          <el-input v-model="partyForm.detail.enterprise_type" placeholder="如 有限责任公司 / 自然人" />
        </el-form-item>
        <el-form-item label="注册地">
          <el-input v-model="partyForm.detail.registered_place" placeholder="注册地" />
        </el-form-item>
        <el-form-item label="法人代表">
          <el-input v-model="partyForm.detail.legal_rep" placeholder="法定代表人" />
        </el-form-item>
        <el-form-item label="业务性质">
          <el-input v-model="partyForm.detail.business_nature" placeholder="主营业务" />
        </el-form-item>
        <el-form-item label="注册资本">
          <el-input v-model="partyForm.detail.registered_capital" placeholder="如 1000 万元" />
        </el-form-item>
        <el-form-item label="持股比例%">
          <el-input v-model="partyForm.detail.shareholding_ratio" placeholder="如 100" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="partyDialog = false">取消</el-button>
        <el-button type="primary" @click="submitParty">保存</el-button>
      </template>
    </el-dialog>

    <!-- 交易 CRUD 弹窗 -->
    <el-dialog v-model="txnDialog" :title="editingTxnId ? '编辑关联交易' : '新增关联交易'" width="480px">
      <el-form label-width="110px">
        <el-form-item label="关联方" required>
          <el-select v-model="txnForm.related_party_id" filterable style="width: 100%">
            <el-option v-for="p in rp.parties.value" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="交易类型" required>
          <el-select v-model="txnForm.transaction_type" style="width: 100%">
            <el-option v-for="o in TRANSACTION_TYPE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="交易金额（元）">
          <el-input-number v-model="txnForm.amount" :controls="false" :precision="2" style="width: 100%" placeholder="金额" />
        </el-form-item>
        <el-form-item label="定价是否公允">
          <el-select v-model="txnForm.is_arms_length" clearable style="width: 100%" placeholder="未评价">
            <el-option :value="true" label="公允" />
            <el-option :value="false" label="非公允" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="txnDialog = false">取消</el-button>
        <el-button type="primary" @click="submitTxn">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.gt-b19-bundle__alert {
  margin-bottom: 12px;
}
.gt-b19-bundle__toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}
.gt-b19-bundle__count {
  color: #909399;
  font-size: 13px;
}
.gt-b19-bundle__muted {
  color: #c0c4cc;
}
.gt-b19-bundle__section {
  margin-bottom: 18px;
}
.gt-b19-bundle__section-title {
  margin: 8px 0;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}
.gt-b19-bundle__feature {
  font-size: 12px;
  line-height: 1.5;
}
.gt-b19-bundle__summary {
  margin-top: 16px;
}
.gt-b19-bundle__hint {
  font-size: 12px;
  line-height: 1.6;
}
.gt-b19-bundle__hint-list {
  margin: 6px 0 0;
  padding-left: 4px;
  list-style: none;
}
.gt-b19-bundle__hint-list li {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}
:deep(.el-table) {
  font-size: 13px;
}
</style>
