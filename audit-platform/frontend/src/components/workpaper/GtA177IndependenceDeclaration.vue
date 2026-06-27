<!--
  GtA177IndependenceDeclaration.vue — A17-7/A17-7A 独立性声明书

  双变体(variant)专属组件：
  - A17-7 → variant="team" (全员独立性声明)
  - A17-7A → variant="committee" (独立性判断委员会声明)

  5 区块布局:
  1. 声明正文 + 期间承诺 (auto-fill + 2 date-range)
  2. 团队成员签字表 (el-table dynamic rows)
  3. 合伙人声明 + 签字 (Y/N radio + conditional textarea + 2-row sign)
  4. 附件威胁记录 (el-collapse 3 sub-tables)
  5. 编制指导 (el-collapse read-only)
-->
<template>
  <div class="gt-a177">
    <!-- Toolbar -->
    <div class="gt-a177__toolbar">
      <el-segmented
        v-model="mode"
        :options="modeOptions"
        size="small"
        @change="handleModeChange"
      />
      <span class="gt-a177__save-status">
        <template v-if="saveStatus === 'saving'">
          <el-icon class="is-loading"><Loading /></el-icon> 保存中...
        </template>
        <template v-else-if="saveStatus === 'saved' && lastSavedAt">
          ✓ 已保存
        </template>
        <template v-else-if="saveStatus === 'unsaved'">
          ○ 未保存
        </template>
      </span>
    </div>

    <!-- Structured View -->
    <div v-if="mode === '结构化视图'" class="gt-a177__content">
      <el-skeleton v-if="loading" :rows="10" animated />

      <template v-else>
        <!-- Section 1: 声明正文 + 期间承诺 -->
        <el-card class="gt-a177__card" shadow="never">
          <template #header>
            <span class="gt-a177__card-title">{{ variantTitle }}</span>
          </template>

          <!-- Declaration Text (read-only) -->
          <div class="gt-a177__declaration">
            <p class="gt-a177__declaration-prefix">
              <strong>{{ metaInfo.client_name || '______' }}</strong> {{ metaInfo.audit_year || '____' }}年度审计项目
            </p>
            <p class="gt-a177__declaration-text">{{ declarationText }}</p>
          </div>

          <!-- Period Date Pickers -->
          <div class="gt-a177__period-grid">
            <div class="gt-a177__period-item">
              <label>业务期间</label>
              <div class="gt-a177__date-range">
                <el-date-picker
                  :model-value="periodData.business_start"
                  type="date"
                  size="small"
                  value-format="YYYY-MM-DD"
                  placeholder="开始日期"
                  :disabled="props.readonly"
                  @change="(v: string) => updatePeriod('business_start', v || null)"
                />
                <span class="gt-a177__date-sep">至</span>
                <el-date-picker
                  :model-value="periodData.business_end"
                  type="date"
                  size="small"
                  value-format="YYYY-MM-DD"
                  placeholder="结束日期"
                  :disabled="props.readonly"
                  @change="(v: string) => updatePeriod('business_end', v || null)"
                />
              </div>
            </div>
            <div class="gt-a177__period-item">
              <label>财务报告期间</label>
              <div class="gt-a177__date-range">
                <el-date-picker
                  :model-value="periodData.report_start"
                  type="date"
                  size="small"
                  value-format="YYYY-MM-DD"
                  placeholder="开始日期"
                  :disabled="props.readonly"
                  @change="(v: string) => updatePeriod('report_start', v || null)"
                />
                <span class="gt-a177__date-sep">至</span>
                <el-date-picker
                  :model-value="periodData.report_end"
                  type="date"
                  size="small"
                  value-format="YYYY-MM-DD"
                  placeholder="结束日期"
                  :disabled="props.readonly"
                  @change="(v: string) => updatePeriod('report_end', v || null)"
                />
              </div>
            </div>
          </div>
        </el-card>

        <!-- Section 2: 团队成员签字表 -->
        <el-card class="gt-a177__card" shadow="never">
          <template #header>
            <div class="gt-a177__card-header">
              <span class="gt-a177__card-title">团队成员签字</span>
              <el-button
                v-if="!props.readonly"
                type="primary"
                size="small"
                @click="addTeamMember"
              >
                添加成员
              </el-button>
            </div>
          </template>

          <el-table :data="teamSignTable" border size="small" class="gt-a177__sign-table">
            <el-table-column label="序号" width="60" align="center">
              <template #default="scope">{{ (scope?.$index ?? 0) + 1 }}</template>
            </el-table-column>
            <el-table-column label="姓名" min-width="120">
              <template #default="scope">
                <el-input
                  :model-value="scope?.row?.name"
                  size="small"
                  placeholder="姓名"
                  :disabled="props.readonly"
                  @change="(v: string) => updateTeamMember(scope?.$index ?? 0, 'name', v)"
                />
              </template>
            </el-table-column>
            <el-table-column label="签字" width="80" align="center">
              <template #default="scope">
                <el-checkbox
                  :model-value="scope?.row?.signed"
                  :disabled="props.readonly"
                  @change="(v: boolean) => updateTeamMember(scope?.$index ?? 0, 'signed', v)"
                />
              </template>
            </el-table-column>
            <el-table-column label="日期" width="160">
              <template #default="scope">
                <el-date-picker
                  :model-value="scope?.row?.date"
                  type="date"
                  size="small"
                  value-format="YYYY-MM-DD"
                  placeholder="日期"
                  :disabled="props.readonly"
                  @change="(v: string) => updateTeamMember(scope?.$index ?? 0, 'date', v || null)"
                />
              </template>
            </el-table-column>
            <el-table-column v-if="!props.readonly" label="操作" width="60" align="center">
              <template #default="scope">
                <el-icon
                  class="gt-a177__delete-icon"
                  @click="handleRemoveMember(scope?.$index ?? 0)"
                >
                  <Delete />
                </el-icon>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <!-- Section 3: 合伙人声明 + 签字 -->
        <el-card class="gt-a177__card" shadow="never">
          <template #header>
            <span class="gt-a177__card-title">合伙人及负责经理声明</span>
          </template>

          <div class="gt-a177__partner">
            <div class="gt-a177__partner-confirm">
              <label>经审查，项目组全体成员均已遵守独立性要求：</label>
              <el-radio-group
                :model-value="partnerSection.confirmed"
                :disabled="props.readonly"
                @change="(v: boolean | null) => updatePartner('confirmed', v)"
              >
                <el-radio :value="true">是</el-radio>
                <el-radio :value="false">否</el-radio>
              </el-radio-group>
            </div>

            <!-- Conditional explanation textarea -->
            <div v-if="partnerSection.confirmed === false" class="gt-a177__partner-explain">
              <label>不确认原因说明：</label>
              <el-input
                :model-value="partnerSection.explanation || ''"
                type="textarea"
                :autosize="{ minRows: 3, maxRows: 8 }"
                placeholder="请说明存在的独立性问题及已采取的措施"
                :disabled="props.readonly"
                @change="(v: string) => updatePartner('explanation', v)"
              />
            </div>

            <!-- Partner/Manager Sign Table -->
            <el-table
              :data="partnerSignRows"
              border
              size="small"
              class="gt-a177__partner-table"
            >
              <el-table-column label="角色" width="120" prop="role" />
              <el-table-column label="姓名" min-width="120">
                <template #default="{ row }">
                  <el-input
                    :model-value="row.name || ''"
                    size="small"
                    placeholder="姓名"
                    :disabled="props.readonly"
                    @change="(v: string) => handlePartnerSign(row.key, 'name', v)"
                  />
                </template>
              </el-table-column>
              <el-table-column label="日期" width="160">
                <template #default="{ row }">
                  <el-date-picker
                    :model-value="row.date"
                    type="date"
                    size="small"
                    value-format="YYYY-MM-DD"
                    placeholder="日期"
                    :disabled="props.readonly"
                    @change="(v: string) => handlePartnerSign(row.key, 'date', v || null)"
                  />
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-card>

        <!-- Section 4: 附件威胁记录 -->
        <el-card class="gt-a177__card" shadow="never">
          <template #header>
            <span class="gt-a177__card-title">附件：独立性威胁记录</span>
          </template>

          <el-collapse class="gt-a177__threat-collapse">
            <!-- 经济利益 -->
            <el-collapse-item title="经济利益记录" name="economic">
              <div class="gt-a177__threat-actions">
                <el-button
                  v-if="!props.readonly"
                  size="small"
                  @click="addThreatRow('economic_interest')"
                >
                  添加记录
                </el-button>
              </div>
              <el-table
                :data="threatRecords.economic_interest"
                border
                size="small"
              >
                <el-table-column label="成员姓名" min-width="100">
                  <template #default="{ row, $index }">
                    <el-input
                      :model-value="row.member"
                      size="small"
                      :disabled="props.readonly"
                      @change="(v: string) => updateThreatRow('economic_interest', $index, 'member', v)"
                    />
                  </template>
                </el-table-column>
                <el-table-column label="利益类型" min-width="100">
                  <template #default="{ row, $index }">
                    <el-input
                      :model-value="row.type"
                      size="small"
                      :disabled="props.readonly"
                      @change="(v: string) => updateThreatRow('economic_interest', $index, 'type', v)"
                    />
                  </template>
                </el-table-column>
                <el-table-column label="金额" width="100">
                  <template #default="{ row, $index }">
                    <el-input
                      :model-value="row.amount"
                      size="small"
                      :disabled="props.readonly"
                      @change="(v: string) => updateThreatRow('economic_interest', $index, 'amount', v)"
                    />
                  </template>
                </el-table-column>
                <el-table-column label="处理措施" min-width="120">
                  <template #default="{ row, $index }">
                    <el-input
                      :model-value="row.measure"
                      size="small"
                      :disabled="props.readonly"
                      @change="(v: string) => updateThreatRow('economic_interest', $index, 'measure', v)"
                    />
                  </template>
                </el-table-column>
                <el-table-column v-if="!props.readonly" label="" width="50" align="center">
                  <template #default="{ $index }">
                    <el-icon class="gt-a177__delete-icon" @click="removeThreatRow('economic_interest', $index)"><Delete /></el-icon>
                  </template>
                </el-table-column>
              </el-table>
            </el-collapse-item>

            <!-- 贷款担保 -->
            <el-collapse-item title="贷款担保记录" name="loan">
              <div class="gt-a177__threat-actions">
                <el-button
                  v-if="!props.readonly"
                  size="small"
                  @click="addThreatRow('loan_guarantee')"
                >
                  添加记录
                </el-button>
              </div>
              <el-table
                :data="threatRecords.loan_guarantee"
                border
                size="small"
              >
                <el-table-column label="成员姓名" min-width="100">
                  <template #default="{ row, $index }">
                    <el-input
                      :model-value="row.member"
                      size="small"
                      :disabled="props.readonly"
                      @change="(v: string) => updateThreatRow('loan_guarantee', $index, 'member', v)"
                    />
                  </template>
                </el-table-column>
                <el-table-column label="贷款类型" min-width="100">
                  <template #default="{ row, $index }">
                    <el-input
                      :model-value="row.type"
                      size="small"
                      :disabled="props.readonly"
                      @change="(v: string) => updateThreatRow('loan_guarantee', $index, 'type', v)"
                    />
                  </template>
                </el-table-column>
                <el-table-column label="金额" width="100">
                  <template #default="{ row, $index }">
                    <el-input
                      :model-value="row.amount"
                      size="small"
                      :disabled="props.readonly"
                      @change="(v: string) => updateThreatRow('loan_guarantee', $index, 'amount', v)"
                    />
                  </template>
                </el-table-column>
                <el-table-column label="处理措施" min-width="120">
                  <template #default="{ row, $index }">
                    <el-input
                      :model-value="row.measure"
                      size="small"
                      :disabled="props.readonly"
                      @change="(v: string) => updateThreatRow('loan_guarantee', $index, 'measure', v)"
                    />
                  </template>
                </el-table-column>
                <el-table-column v-if="!props.readonly" label="" width="50" align="center">
                  <template #default="{ $index }">
                    <el-icon class="gt-a177__delete-icon" @click="removeThreatRow('loan_guarantee', $index)"><Delete /></el-icon>
                  </template>
                </el-table-column>
              </el-table>
            </el-collapse-item>

            <!-- 商业关系 -->
            <el-collapse-item title="商业关系记录" name="business">
              <div class="gt-a177__threat-actions">
                <el-button
                  v-if="!props.readonly"
                  size="small"
                  @click="addThreatRow('business_relation')"
                >
                  添加记录
                </el-button>
              </div>
              <el-table
                :data="threatRecords.business_relation"
                border
                size="small"
              >
                <el-table-column label="成员姓名" min-width="100">
                  <template #default="{ row, $index }">
                    <el-input
                      :model-value="row.member"
                      size="small"
                      :disabled="props.readonly"
                      @change="(v: string) => updateThreatRow('business_relation', $index, 'member', v)"
                    />
                  </template>
                </el-table-column>
                <el-table-column label="关系描述" min-width="150">
                  <template #default="{ row, $index }">
                    <el-input
                      :model-value="row.description"
                      size="small"
                      :disabled="props.readonly"
                      @change="(v: string) => updateThreatRow('business_relation', $index, 'description', v)"
                    />
                  </template>
                </el-table-column>
                <el-table-column label="处理措施" min-width="120">
                  <template #default="{ row, $index }">
                    <el-input
                      :model-value="row.measure"
                      size="small"
                      :disabled="props.readonly"
                      @change="(v: string) => updateThreatRow('business_relation', $index, 'measure', v)"
                    />
                  </template>
                </el-table-column>
                <el-table-column v-if="!props.readonly" label="" width="50" align="center">
                  <template #default="{ $index }">
                    <el-icon class="gt-a177__delete-icon" @click="removeThreatRow('business_relation', $index)"><Delete /></el-icon>
                  </template>
                </el-table-column>
              </el-table>
            </el-collapse-item>
          </el-collapse>
        </el-card>

        <!-- Section 5: 编制指导 -->
        <el-card class="gt-a177__card" shadow="never">
          <template #header>
            <span class="gt-a177__card-title">
              编制指导
              <el-badge :value="guidanceNotes.length" type="info" class="gt-a177__badge" />
            </span>
          </template>

          <el-collapse class="gt-a177__guidance-collapse">
            <el-collapse-item
              v-for="(note, idx) in guidanceNotes"
              :key="idx"
              :title="`指导 ${idx + 1}`"
              :name="idx"
            >
              <p class="gt-a177__guidance-text">{{ note }}</p>
            </el-collapse-item>
          </el-collapse>
        </el-card>
      </template>
    </div>

    <!-- Online Edit Mode -->
    <GtOnlyOfficeSheet
      v-else
      :wp-id="props.wpId"
      :sheet-name="variant === 'team' ? 'A17-7' : 'A17-7A'"
      class="gt-a177__oo"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { Loading, Delete } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import { useA177IndependenceDeclaration } from './composables/useA177IndependenceDeclaration'

const GtOnlyOfficeSheet = defineAsyncComponent(
  () => import('./GtOnlyOfficeSheet.vue'),
)

defineOptions({ name: 'GtA177IndependenceDeclaration' })

const props = withDefaults(defineProps<{
  wpId: string
  readonly?: boolean
}>(), { readonly: false })

// ─── Mode Switch ───
const mode = ref('结构化视图')
const modeOptions = ['结构化视图', '在线编辑']

async function handleModeChange() {
  await flushPendingSaves()
}

// ─── Composable ───
const wpIdRef = ref(props.wpId)
const {
  loading,
  variant,
  metaInfo,
  declarationText,
  periodData,
  teamSignTable,
  partnerSection,
  threatRecords,
  guidanceNotes,
  saveStatus,
  lastSavedAt,
  addTeamMember,
  removeTeamMember,
  updateTeamMember,
  addThreatRow,
  removeThreatRow,
  updateThreatRow,
  updatePeriod,
  updatePartner,
  loadData,
  flushPendingSaves,
} = useA177IndependenceDeclaration(wpIdRef)

// ─── Computed ───
const variantTitle = computed(() =>
  variant.value === 'team'
    ? '审计项目团队成员独立性声明书'
    : '专业技术委员会审核委员独立性声明书',
)

const partnerSignRows = computed(() => [
  {
    key: 'partner_sign',
    role: '项目合伙人',
    name: partnerSection.value.partner_sign.name,
    date: partnerSection.value.partner_sign.date,
  },
  {
    key: 'manager_sign',
    role: '负责经理',
    name: partnerSection.value.manager_sign.name,
    date: partnerSection.value.manager_sign.date,
  },
])

// ─── Handlers ───
function handlePartnerSign(key: string, field: string, value: string | null) {
  const current = key === 'partner_sign'
    ? { ...partnerSection.value.partner_sign }
    : { ...partnerSection.value.manager_sign }
  ;(current as any)[field] = value
  updatePartner(key, current)
}

async function handleRemoveMember(index: number) {
  try {
    await ElMessageBox.confirm('确认删除该成员？', '提示', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      type: 'warning',
    })
    removeTeamMember(index)
  } catch {
    // cancelled
  }
}

// ─── Lifecycle ───
onMounted(() => { loadData(props.wpId) })
onBeforeUnmount(() => { flushPendingSaves() })

defineExpose({ reload: () => loadData(props.wpId) })
</script>

<style scoped>
.gt-a177 {
  padding: 16px;
  max-width: 960px;
}

.gt-a177__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.gt-a177__save-status {
  font-size: 12px;
  color: #909399;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.gt-a177__content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.gt-a177__card {
  border-radius: 8px;
}

.gt-a177__card-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.gt-a177__card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.gt-a177__declaration {
  margin-bottom: 20px;
  padding: 12px 16px;
  background: #f5f7fa;
  border-radius: 6px;
}

.gt-a177__declaration-prefix {
  font-size: 14px;
  margin-bottom: 8px;
  color: #303133;
}

.gt-a177__declaration-text {
  font-size: 13px;
  color: #606266;
  line-height: 1.8;
}

.gt-a177__period-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.gt-a177__period-item label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: #606266;
  margin-bottom: 6px;
}

.gt-a177__date-range {
  display: flex;
  align-items: center;
  gap: 8px;
}

.gt-a177__date-sep {
  font-size: 13px;
  color: #909399;
}

.gt-a177__sign-table {
  width: 100%;
}

.gt-a177__delete-icon {
  cursor: pointer;
  color: #f56c6c;
  font-size: 16px;
}

.gt-a177__delete-icon:hover {
  color: #e63e3e;
}

.gt-a177__partner {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.gt-a177__partner-confirm {
  display: flex;
  align-items: center;
  gap: 12px;
}

.gt-a177__partner-confirm label {
  font-size: 13px;
  color: #606266;
}

.gt-a177__partner-explain label {
  display: block;
  font-size: 13px;
  color: #606266;
  margin-bottom: 6px;
}

.gt-a177__partner-table {
  width: 100%;
}

.gt-a177__threat-collapse {
  border: none;
}

.gt-a177__threat-actions {
  margin-bottom: 8px;
}

.gt-a177__guidance-collapse {
  border: none;
}

.gt-a177__guidance-text {
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
  padding: 4px 0;
}

.gt-a177__badge {
  margin-left: 8px;
}

.gt-a177__oo {
  height: calc(100vh - 200px);
  min-height: 500px;
}
</style>
