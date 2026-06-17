<script setup lang="ts">
/**
 * GtSegmentReport — 经营分部审定表组件
 *
 * A4-1 经营分部列报：动态分部列 + 合计 + 本期/上期 Tab
 * 含地区信息交叉表和主要客户列表。
 *
 * 功能：
 *  - 动态分部列（用户可增删分部）
 *  - 本期/上期 Tab 切换
 *  - 行项目：收入/成本/利润/资产/负债/资本性支出等
 *  - 地区信息交叉表：境内/境外 × 收入/非流动资产
 *  - 主要客户列表：≥10% 收入客户
 *  - 准则说明 hover tooltip
 */
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { api } from '@/services/apiProxy'
import { ElMessage } from 'element-plus'

const props = defineProps<{
  wpId: string
  projectId?: string
  htmlData?: any
  readonly?: boolean
}>()

const emit = defineEmits<{ (e: 'save'): void }>()

// ─── Types ───
interface SegmentRow {
  code: string
  label: string
  indent: number
  is_total: boolean
  tooltip?: string
  values: Record<string, number> // segment_id → amount
}

interface CustomerRow {
  name: string
  revenue: number
  pct: number
  segment: string
}

interface GeoRow {
  region: string
  revenue: number
  non_current_assets: number
}

// ─── State ───
const activeTab = ref<'current' | 'prior'>('current')
const activeSection = ref<'profit' | 'geo' | 'customer'>('profit')
const segments = ref<{ id: string; name: string }[]>([
  { id: 'seg1', name: '分部1' },
  { id: 'seg2', name: '分部2' },
])

const ROW_DEFS: { code: string; label: string; indent: number; is_total: boolean; tooltip?: string }[] = [
  { code: 'rev_ext', label: '对外交易收入', indent: 1, is_total: false, tooltip: '来自外部客户的收入' },
  { code: 'rev_inter', label: '分部间交易收入', indent: 1, is_total: false, tooltip: '与其他经营分部之间的内部转移收入' },
  { code: 'rev_total', label: '收入合计', indent: 0, is_total: true },
  { code: 'interest_income', label: '利息收入', indent: 1, is_total: false },
  { code: 'interest_expense', label: '利息费用', indent: 1, is_total: false },
  { code: 'dep_amort', label: '折旧和摊销', indent: 1, is_total: false },
  { code: 'equity_income', label: '权益法投资收益', indent: 1, is_total: false, tooltip: '对联营/合营企业的权益法核算收益' },
  { code: 'income_tax', label: '所得税费用', indent: 1, is_total: false },
  { code: 'segment_profit', label: '分部利润（损失）', indent: 0, is_total: true, tooltip: '解释3号八(三)：应当披露每个报告分部的利润（亏损）总额' },
  { code: 'total_assets', label: '分部资产', indent: 0, is_total: false, tooltip: '按报告分部披露资产总额' },
  { code: 'total_liabilities', label: '分部负债', indent: 0, is_total: false, tooltip: '按报告分部披露负债总额' },
  { code: 'capex', label: '资本性支出', indent: 0, is_total: false, tooltip: '取得除长期股权投资以外的非流动资产支出' },
  { code: 'equity_investment', label: '权益法投资金额', indent: 0, is_total: false },
]

// 数据存储
const currentData = ref<Record<string, Record<string, number>>>({})
const priorData = ref<Record<string, Record<string, number>>>({})
const customers = ref<CustomerRow[]>([{ name: '', revenue: 0, pct: 0, segment: '' }])
const geoData = ref<GeoRow[]>([
  { region: '境内', revenue: 0, non_current_assets: 0 },
  { region: '境外', revenue: 0, non_current_assets: 0 },
])

const activeData = computed(() => activeTab.value === 'current' ? currentData.value : priorData.value)

function getCellValue(code: string, segId: string): number {
  return activeData.value[code]?.[segId] ?? 0
}

function setCellValue(code: string, segId: string, val: number) {
  if (props.readonly) return
  const data = activeTab.value === 'current' ? currentData.value : priorData.value
  if (!data[code]) data[code] = {}
  data[code][segId] = val
  scheduleSave()
}

function getRowTotal(code: string): number {
  const row = activeData.value[code]
  if (!row) return 0
  return Object.values(row).reduce((sum, v) => sum + (v || 0), 0)
}

// ─── 分部管理 ───
function addSegment() {
  const id = `seg${Date.now()}`
  segments.value.push({ id, name: `分部${segments.value.length + 1}` })
  scheduleSave()
}

function removeSegment(idx: number) {
  if (segments.value.length <= 1) return
  const seg = segments.value[idx]
  segments.value.splice(idx, 1)
  // 清理数据
  for (const code of Object.keys(currentData.value)) {
    delete currentData.value[code]?.[seg.id]
  }
  for (const code of Object.keys(priorData.value)) {
    delete priorData.value[code]?.[seg.id]
  }
  scheduleSave()
}

// ─── 客户管理 ───
function addCustomer() {
  customers.value.push({ name: '', revenue: 0, pct: 0, segment: '' })
}
function removeCustomer(idx: number) {
  customers.value.splice(idx, 1)
  scheduleSave()
}

// ─── 保存 ───
const saving = ref(false)
let saveTimer: ReturnType<typeof setTimeout> | null = null

function scheduleSave() {
  if (props.readonly) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(doSave, 2000)
}

async function doSave() {
  if (saving.value) return
  saving.value = true
  try {
    await api.put(`/api/workpapers/${props.wpId}/parsed-data`, {
      segment_report: {
        segments: segments.value,
        current: currentData.value,
        prior: priorData.value,
        customers: customers.value,
        geo: geoData.value,
      },
    })
    emit('save')
  } catch {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

// ─── 加载 ───
async function loadData() {
  if (!props.wpId) return
  try {
    const data = await api.get(`/api/workpapers/${props.wpId}/render-config`)
    const parsed = data?.sheets?.[0]?.html_data?.segment_report || data?.fill_results?.segment_report
    if (parsed) {
      if (parsed.segments) segments.value = parsed.segments
      if (parsed.current) currentData.value = parsed.current
      if (parsed.prior) priorData.value = parsed.prior
      if (parsed.customers) customers.value = parsed.customers
      if (parsed.geo) geoData.value = parsed.geo
    }
  } catch { /* 降级 */ }
}

onMounted(loadData)
onBeforeUnmount(() => { if (saveTimer) { clearTimeout(saveTimer); doSave() } })
</script>

<template>
  <div class="gt-segment-report">
    <!-- 区域切换 -->
    <el-radio-group v-model="activeSection" size="small" style="margin-bottom: 12px">
      <el-radio-button value="profit">分部利润表</el-radio-button>
      <el-radio-button value="geo">地区信息</el-radio-button>
      <el-radio-button value="customer">主要客户</el-radio-button>
    </el-radio-group>

    <!-- ═══ 分部利润表 ═══ -->
    <template v-if="activeSection === 'profit'">
      <div class="gt-sr-toolbar">
        <el-radio-group v-model="activeTab" size="small">
          <el-radio-button value="current">本期</el-radio-button>
          <el-radio-button value="prior">上期</el-radio-button>
        </el-radio-group>
        <el-button v-if="!readonly" size="small" @click="addSegment">+ 添加分部</el-button>
      </div>

      <el-table :data="ROW_DEFS" border size="small" class="gt-compact-table">
        <el-table-column label="项目" width="180" fixed>
          <template #default="{ row }">
            <span :style="{ paddingLeft: row.indent * 16 + 'px', fontWeight: row.is_total ? 600 : 400 }">
              {{ row.label }}
              <el-tooltip v-if="row.tooltip" :content="row.tooltip" placement="right">
                <span class="gt-sr-tip">?</span>
              </el-tooltip>
            </span>
          </template>
        </el-table-column>
        <el-table-column
          v-for="(seg, idx) in segments"
          :key="seg.id"
          :label="seg.name"
          min-width="140"
          align="right"
        >
          <template #header>
            <div class="gt-sr-col-header">
              <el-input
                v-if="!readonly"
                v-model="segments[idx].name"
                size="small"
                style="width: 100px"
                @change="scheduleSave"
              />
              <span v-else>{{ seg.name }}</span>
              <el-button
                v-if="!readonly && segments.length > 1"
                size="small"
                text
                type="danger"
                @click="removeSegment(idx)"
              >×</el-button>
            </div>
          </template>
          <template #default="{ row }">
            <el-input-number
              :model-value="getCellValue(row.code, seg.id)"
              @update:model-value="(v: number) => setCellValue(row.code, seg.id, v || 0)"
              :disabled="readonly"
              size="small"
              :controls="false"
              style="width: 100%"
            />
          </template>
        </el-table-column>
        <el-table-column label="合计" width="120" align="right" fixed="right">
          <template #default="{ row }">
            <strong>{{ getRowTotal(row.code).toLocaleString() }}</strong>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- ═══ 地区信息 ═══ -->
    <template v-if="activeSection === 'geo'">
      <el-table :data="geoData" border size="small" class="gt-compact-table">
        <el-table-column label="地区" prop="region" width="120" />
        <el-table-column label="来自外部客户的收入（万元）" min-width="180">
          <template #default="{ $index }">
            <el-input-number v-model="geoData[$index].revenue" :disabled="readonly" size="small" :controls="false" @change="scheduleSave" />
          </template>
        </el-table-column>
        <el-table-column label="非流动资产（万元）" min-width="180">
          <template #default="{ $index }">
            <el-input-number v-model="geoData[$index].non_current_assets" :disabled="readonly" size="small" :controls="false" @change="scheduleSave" />
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- ═══ 主要客户 ═══ -->
    <template v-if="activeSection === 'customer'">
      <div class="gt-sr-toolbar">
        <span class="gt-sr-hint">来自单个外部客户的收入占合计 10% 及以上的，应当披露</span>
        <el-button v-if="!readonly" size="small" @click="addCustomer">+ 添加客户</el-button>
      </div>
      <el-table :data="customers" border size="small" class="gt-compact-table">
        <el-table-column label="客户名称" min-width="150">
          <template #default="{ $index }">
            <el-input v-model="customers[$index].name" :disabled="readonly" size="small" placeholder="客户A" @change="scheduleSave" />
          </template>
        </el-table-column>
        <el-table-column label="收入金额（万元）" width="150">
          <template #default="{ $index }">
            <el-input-number v-model="customers[$index].revenue" :disabled="readonly" size="small" :controls="false" @change="scheduleSave" />
          </template>
        </el-table-column>
        <el-table-column label="占比 %" width="100">
          <template #default="{ $index }">
            <el-input-number v-model="customers[$index].pct" :disabled="readonly" size="small" :controls="false" :precision="2" @change="scheduleSave" />
          </template>
        </el-table-column>
        <el-table-column label="所在分部" width="140">
          <template #default="{ $index }">
            <el-select v-model="customers[$index].segment" :disabled="readonly" size="small" placeholder="选择分部" @change="scheduleSave">
              <el-option v-for="s in segments" :key="s.id" :label="s.name" :value="s.id" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column v-if="!readonly" label="" width="60" align="center">
          <template #default="{ $index }">
            <el-button size="small" text type="danger" @click="removeCustomer($index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>
  </div>
</template>

<style scoped>
.gt-segment-report { padding: 12px; }
.gt-sr-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.gt-sr-col-header { display: flex; align-items: center; gap: 4px; }
.gt-sr-tip { display: inline-block; width: 14px; height: 14px; line-height: 14px; text-align: center; border-radius: 50%; background: var(--gt-primary, #4b2d77); color: #fff; font-size: 10px; cursor: help; margin-left: 4px; }
.gt-sr-hint { font-size: 12px; color: #999; }
</style>
