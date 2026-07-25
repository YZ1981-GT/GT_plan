<template>
  <div class="g1-disclosure-listed" data-testid="g1-disclosure-listed">
    <div class="section-head">
      <h3 class="sheet-title">附注披露信息（上市公司）</h3>
      <div class="head-actions">
        <el-button size="small" :disabled="isReadonly" @click="refreshFromSources()">从审定/估值带数</el-button>
        <el-button size="small" type="primary" :loading="isSyncing" :disabled="isReadonly || !projectId" @click="syncToNotes">
          同步到附注
        </el-button>
        <span class="chip-wrap"><GtIndexChip :value="noteChip" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-1" /></span>
        <el-button size="small" @click="openReviewDialog('G1-note-listed')">💬复核</el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      title="审计目标：按上市公司附注格式披露交易性金融资产分类、衍生工具、公允价值层次及 L2/L3 输入值与第三层次调节，金额与 G1-1/G1-6/G1-7 勾稽，并同步至附注模块「五、2」。"
      class="objective-alert"
    />

    <el-alert
      v-if="adjudicatedAmount != null"
      :type="reconcileOk ? 'success' : 'warning'"
      :closable="false"
      class="sync-hint"
    >
      审定表 1501 合计 {{ fmt(adjudicatedAmount) }}
      · 分类披露合计 {{ fmt(classTotal) }}
      <template v-if="classVsAdjDiff != null">
        · 差异 {{ fmt(classVsAdjDiff) }}
        {{ classVsAdjDiff === 0 ? '✓' : '✗' }}
      </template>
    </el-alert>

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>长表拆为六个页签：分类 → 衍生 → FV 层次 → 输入值（按估值技术选指标）→ L3 调节 → 非 FV 披露。</li>
        <li>结构性存款未过 SPPI 测试应归入交易性；「指定为 FVTPL」须填写指定理由（15 号文）。</li>
        <li>衍生业务重要时启用②；无 L3 余额时可弱化⑤。点击索引可跳转 G1-1 / G1-6 / G1-7。</li>
        <li>「同步到附注」推送结构化子表至附注模块「{{ noteSectionId }} 交易性金融资产」。</li>
      </ul>
    </details>

    <el-tabs v-model="activeTab" type="card" class="disc-tabs">
      <!-- ① 分类 -->
      <el-tab-pane label="① 分类披露" name="classification">
        <div class="tab-toolbar">
          <span class="chip-wrap"><GtIndexChip value="wp:G1-1" /></span>
          <span class="hint">期末/上年年末应对齐 G1-1 账面余额（公允价值）</span>
        </div>
        <el-table :data="classificationRows" border size="small" class="amount-table" :row-class-name="amountRowClass" max-height="480">
          <el-table-column label="项目" min-width="280">
            <template #default="{ row }">
              <span :style="{ paddingLeft: `${(row.indent || 0) * 14}px` }" :class="{ strong: row.kind !== 'leaf' }">{{ row.label }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末余额" min-width="150" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.kind === 'leaf' && !isReadonly"
                :model-value="row.endAmount"
                size="small"
                :controls="false"
                style="width:100%"
                @update:model-value="(v: number) => updateClassField(row.rowKey, 'endAmount', v ?? 0)"
              />
              <span v-else>{{ fmt(row.endAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="上年年末余额" min-width="150" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.kind === 'leaf' && !isReadonly"
                :model-value="row.priorAmount"
                size="small"
                :controls="false"
                style="width:100%"
                @update:model-value="(v: number) => updateClassField(row.rowKey, 'priorAmount', v ?? 0)"
              />
              <span v-else>{{ fmt(row.priorAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="适用" width="70" align="center">
            <template #default="{ row }">
              <el-checkbox
                v-if="row.kind === 'leaf'"
                :model-value="row.applicable !== false"
                :disabled="isReadonly"
                @change="(v: boolean) => updateClassField(row.rowKey, 'applicable', v)"
              />
            </template>
          </el-table-column>
        </el-table>
        <div class="text-block">
          <div class="text-label">指定为 FVTPL 的理由与依据（有指定余额时必填）</div>
          <el-input
            v-model="designatedReason"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
            :disabled="isReadonly"
            placeholder="说明指定的原因及依据（参照 15 号文相关条款）…"
          />
        </div>
      </el-tab-pane>

      <!-- ② 衍生 -->
      <el-tab-pane label="② 衍生工具" name="derivative">
        <div class="tab-toolbar">
          <el-switch v-model="derivativeApplicable" :disabled="isReadonly" active-text="衍生业务重要，单独披露" />
          <!-- 跳转回附注（默认上市 五、3，下拉可切国企 八、3）-->
          <el-dropdown
            split-button
            type="primary"
            size="small"
            trigger="click"
            @click="jumpDerivativeToNote('listed')"
            @command="jumpDerivativeToNote"
          >
            ↩ 跳转回附注（五、3）
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="listed">上市版附注（五、3）</el-dropdown-item>
                <el-dropdown-item command="soe">国企版附注（八、3）</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <span class="chip-wrap"><GtIndexChip value="wp:G1-14" /></span>
        </div>
        <template v-if="derivativeApplicable">
          <el-table :data="derivativeRows" border size="small" class="amount-table" :row-class-name="amountRowClass" max-height="360">
            <el-table-column label="项目" min-width="200" prop="label" />
            <el-table-column label="期末余额" min-width="150" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="row.kind === 'leaf' && !isReadonly"
                  :model-value="row.endAmount"
                  size="small"
                  :controls="false"
                  style="width:100%"
                  @update:model-value="(v: number) => updateDerivField(row.rowKey, 'endAmount', v ?? 0)"
                />
                <span v-else>{{ fmt(row.endAmount) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="上年年末余额" min-width="150" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="row.kind === 'leaf' && !isReadonly"
                  :model-value="row.priorAmount"
                  size="small"
                  :controls="false"
                  style="width:100%"
                  @update:model-value="(v: number) => updateDerivField(row.rowKey, 'priorAmount', v ?? 0)"
                />
                <span v-else>{{ fmt(row.priorAmount) }}</span>
              </template>
            </el-table-column>
          </el-table>
          <div class="text-block">
            <div class="text-label">说明：衍生工具产生原因及会计处理</div>
            <el-input
              v-model="derivativeNote"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 6 }"
              :disabled="isReadonly"
              placeholder="说明衍生工具产生原因、套期关系及会计处理…"
            />
          </div>
        </template>
        <el-empty v-else description="已标记衍生业务不重要，本段不单独披露" :image-size="64" />
      </el-tab-pane>

      <!-- ③ FV 层次 -->
      <el-tab-pane label="③ FV层次" name="fvHierarchy">
        <div class="tab-toolbar">
          <span class="chip-wrap"><GtIndexChip value="wp:G1-6" /></span>
          <span v-if="fvVsAdjDiff != null" :class="{ 'diff-warn': fvVsAdjDiff !== 0 }">
            层次合计 vs 审定差异 {{ fmt(fvVsAdjDiff) }}
          </span>
        </div>
        <el-table :data="fvRows" border size="small" :row-class-name="amountRowClass" max-height="420">
          <el-table-column label="项目" min-width="220">
            <template #default="{ row }">
              <span :style="{ paddingLeft: `${(row.indent || 0) * 14}px` }" :class="{ strong: row.kind !== 'leaf' }">{{ row.label }}</span>
            </template>
          </el-table-column>
          <el-table-column label="第一层次" width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.kind === 'leaf' && !isReadonly"
                :model-value="row.l1"
                size="small"
                :controls="false"
                style="width:100%"
                @update:model-value="(v: number) => updateFvField(row.rowKey, 'l1', v ?? 0)"
              />
              <span v-else>{{ fmt(row.l1) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="第二层次" width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.kind === 'leaf' && !isReadonly"
                :model-value="row.l2"
                size="small"
                :controls="false"
                style="width:100%"
                @update:model-value="(v: number) => updateFvField(row.rowKey, 'l2', v ?? 0)"
              />
              <span v-else>{{ fmt(row.l2) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="第三层次" width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.kind === 'leaf' && !isReadonly"
                :model-value="row.l3"
                size="small"
                :controls="false"
                style="width:100%"
                @update:model-value="(v: number) => updateFvField(row.rowKey, 'l3', v ?? 0)"
              />
              <span v-else>{{ fmt(row.l3) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="合计" width="110" align="right">
            <template #default="{ row }">{{ fmt((Number(row.l1) || 0) + (Number(row.l2) || 0) + (Number(row.l3) || 0)) }}</template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ④ 输入值 -->
      <el-tab-pane label="④ 输入值" name="inputs">
        <div class="tab-toolbar">
          <span class="chip-wrap"><GtIndexChip value="wp:G1-6" /></span>
          <span class="hint">先选估值技术，再勾选须披露的关键输入值指标</span>
        </div>
        <el-table :data="inputRows" border size="small" max-height="480">
          <el-table-column label="层次" width="70" align="center">
            <template #default="{ row }">L{{ row.level }}</template>
          </el-table-column>
          <el-table-column label="内容" width="140">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                :model-value="row.content"
                size="small"
                @change="(v: string) => updateInputField(row.rowKey, 'content', v)"
              />
              <span v-else>{{ row.content }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末公允价值" width="120" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.endFv"
                size="small"
                :controls="false"
                style="width:100%"
                @update:model-value="(v: number) => updateInputField(row.rowKey, 'endFv', v ?? 0)"
              />
              <span v-else>{{ fmt(row.endFv) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="估值技术" width="180">
            <template #default="{ row }">
              <el-select
                v-if="!isReadonly"
                :model-value="row.technique"
                size="small"
                style="width:100%"
                @change="(v: string) => applyTechniqueIndicators(row.rowKey, v)"
              >
                <el-option v-for="opt in techniqueOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-select>
              <span v-else>{{ row.technique }}</span>
            </template>
          </el-table-column>
          <el-table-column label="关键输入值（勾选）" min-width="220">
            <template #default="{ row }">
              <el-select
                v-if="!isReadonly"
                :model-value="row.selectedIndicators"
                multiple
                collapse-tags
                collapse-tags-tooltip
                size="small"
                style="width:100%"
                @change="(v: string[]) => onIndicatorsChange(row.rowKey, v)"
              >
                <el-option
                  v-for="ind in (G1_INPUT_CANDIDATES[row.technique] || [])"
                  :key="ind"
                  :label="ind"
                  :value="ind"
                />
              </el-select>
              <span v-else>{{ row.selectedIndicators?.join('、') || row.inputs || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="范围/加权平均" width="140">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                :model-value="row.range"
                size="small"
                placeholder="如 5%–20%"
                @change="(v: string) => updateInputField(row.rowKey, 'range', v)"
              />
              <span v-else>{{ row.range || '—' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ⑤ L3 调节 -->
      <el-tab-pane label="⑤ L3调节" name="l3Rollforward">
        <div class="tab-toolbar">
          <span class="chip-wrap"><GtIndexChip value="wp:G1-7" /></span>
          <span :class="{ 'diff-warn': l3VsFvDiff !== 0 }">
            L3 期末合计 {{ fmt(l3ClosingTotal) }} · vs 层次表 L3 差异 {{ fmt(l3VsFvDiff) }}
          </span>
        </div>
        <el-table :data="l3Rows" border size="small" :row-class-name="amountRowClass" max-height="420">
          <el-table-column label="项目" min-width="160" fixed prop="label" />
          <el-table-column label="期初" width="90" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.kind==='leaf'&&!isReadonly" :model-value="row.opening" size="small" :controls="false" style="width:100%"
                @update:model-value="(v:number)=>updateL3Field(row.rowKey,'opening',v??0)" />
              <span v-else>{{ fmt(row.opening) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="转入" width="80" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.kind==='leaf'&&!isReadonly" :model-value="row.transferIn" size="small" :controls="false" style="width:100%"
                @update:model-value="(v:number)=>updateL3Field(row.rowKey,'transferIn',v??0)" />
              <span v-else>{{ fmt(row.transferIn) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="转出" width="80" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.kind==='leaf'&&!isReadonly" :model-value="row.transferOut" size="small" :controls="false" style="width:100%"
                @update:model-value="(v:number)=>updateL3Field(row.rowKey,'transferOut',v??0)" />
              <span v-else>{{ fmt(row.transferOut) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="计入损益" width="90" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.kind==='leaf'&&!isReadonly" :model-value="row.gainPl" size="small" :controls="false" style="width:100%"
                @update:model-value="(v:number)=>updateL3Field(row.rowKey,'gainPl',v??0)" />
              <span v-else>{{ fmt(row.gainPl) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="计入OCI" width="90" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.kind==='leaf'&&!isReadonly" :model-value="row.gainOci" size="small" :controls="false" style="width:100%"
                @update:model-value="(v:number)=>updateL3Field(row.rowKey,'gainOci',v??0)" />
              <span v-else>{{ fmt(row.gainOci) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="购买" width="80" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.kind==='leaf'&&!isReadonly" :model-value="row.purchase" size="small" :controls="false" style="width:100%"
                @update:model-value="(v:number)=>updateL3Field(row.rowKey,'purchase',v??0)" />
              <span v-else>{{ fmt(row.purchase) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="发行" width="80" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.kind==='leaf'&&!isReadonly" :model-value="row.issue" size="small" :controls="false" style="width:100%"
                @update:model-value="(v:number)=>updateL3Field(row.rowKey,'issue',v??0)" />
              <span v-else>{{ fmt(row.issue) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="出售" width="80" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.kind==='leaf'&&!isReadonly" :model-value="row.sale" size="small" :controls="false" style="width:100%"
                @update:model-value="(v:number)=>updateL3Field(row.rowKey,'sale',v??0)" />
              <span v-else>{{ fmt(row.sale) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="结算" width="80" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.kind==='leaf'&&!isReadonly" :model-value="row.settlement" size="small" :controls="false" style="width:100%"
                @update:model-value="(v:number)=>updateL3Field(row.rowKey,'settlement',v??0)" />
              <span v-else>{{ fmt(row.settlement) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末" width="100" align="right">
            <template #default="{ row }"><span class="formula">{{ fmt(row.closing) }}</span></template>
          </el-table-column>
          <el-table-column label="仍持有未实现" width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.kind==='leaf'&&!isReadonly" :model-value="row.unrealizedHeld" size="small" :controls="false" style="width:100%"
                @update:model-value="(v:number)=>updateL3Field(row.rowKey,'unrealizedHeld',v??0)" />
              <span v-else>{{ fmt(row.unrealizedHeld) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ⑥ 非 FV -->
      <el-tab-pane label="⑥ 非FV披露" name="amortizedCost">
        <p class="hint">不以公允价值计量但需披露公允价值的金融工具（账面价值 vs 层次）。短期项目可近似账面。</p>
        <el-table :data="amortRows" border size="small" max-height="420">
          <el-table-column label="项目" min-width="200" prop="label" />
          <el-table-column label="账面价值" width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.bookValue" size="small" :controls="false" style="width:100%"
                @update:model-value="(v:number)=>updateAmortField(row.rowKey,'bookValue',v??0)" />
              <span v-else>{{ fmt(row.bookValue) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="L1" width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.l1" size="small" :controls="false" style="width:100%"
                @update:model-value="(v:number)=>updateAmortField(row.rowKey,'l1',v??0)" />
              <span v-else>{{ fmt(row.l1) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="L2" width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.l2" size="small" :controls="false" style="width:100%"
                @update:model-value="(v:number)=>updateAmortField(row.rowKey,'l2',v??0)" />
              <span v-else>{{ fmt(row.l2) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="L3" width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.l3" size="small" :controls="false" style="width:100%"
                @update:model-value="(v:number)=>updateAmortField(row.rowKey,'l3',v??0)" />
              <span v-else>{{ fmt(row.l3) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="备注" min-width="140">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
                @change="(v:string)=>updateAmortField(row.rowKey,'remark',v)" />
              <span v-else>{{ row.remark || '—' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <G1AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="generalNote"
      :show-conclusion="false"
      note-title="附注说明（推送附注模块）"
      note-ai-section="disclosure-listed-note"
      note-placeholder="汇总分类、层次、估值技术及重大判断说明…"
      note-hint="保存后通过 disclosure:note-text-updated 联动；亦可点「同步到附注」推送结构化子表。"
      :note-min-rows="3"
      :related-context="{ 分类合计: classTotal, FV合计: fvTotal }"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, toRef, ref, inject } from 'vue'
import { useRouter } from 'vue-router'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { useG1DisclosureListed } from '../../composables/useG1DisclosureListed'
import { buildG1ListedSubTableData, buildG1SyncPayload } from '../../composables/g1DisclosureSyncPayload'
import { G1_NOTE_SECTION } from '../../composables/g1NoteSectionMap'
import { G1_VALUATION_TECHNIQUE_OPTIONS } from '../../composables/g1DisclosureItems'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtIndexChip from '../../GtIndexChip.vue'
import G1AuditTextCards from '../G1AuditTextCards.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId?: string
  projectId?: string
  applicableStandards?: string[]
}>()

const wpId = computed(() => props.wpId ?? '')
const projectId = computed(() => props.projectId ?? '')
const router = useRouter()

// 跳转回附注模块「衍生金融资产」（披露表 → 附注为单向推送；此处仅导航方便相互编辑确认）
// 上市默认→五、3，下拉可切国企↔八、3
function jumpDerivativeToNote(target: DisclosureVariant): void {
  const route = buildNoteJumpRoute(projectId.value, 'G1_DERIVATIVE', target)
  if (!route) {
    ElMessage.warning('未找到对应的衍生金融资产附注章节')
    return
  }
  router.push(route)
}

const noteSectionId = G1_NOTE_SECTION.listed.trading
const noteChip = `Note:${noteSectionId}`
const techniqueOptions = G1_VALUATION_TECHNIQUE_OPTIONS
const isSyncing = ref(false)
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const dis = useG1DisclosureListed({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const {
  activeTab,
  classificationRows,
  derivativeRows,
  fvRows,
  inputRows,
  l3Rows,
  amortRows,
  designatedReason,
  derivativeNote,
  derivativeApplicable,
  generalNote,
  adjudicatedAmount,
  classTotal,
  fvTotal,
  l3ClosingTotal,
  classVsAdjDiff,
  fvVsAdjDiff,
  l3VsFvDiff,
  updateClassField,
  updateDerivField,
  updateFvField,
  updateInputField,
  applyTechniqueIndicators,
  updateL3Field,
  updateAmortField,
  refreshFromSources,
  getSyncSnapshot,
  G1_INPUT_CANDIDATES,
} = dis

const reconcileOk = computed(
  () => classVsAdjDiff.value == null || classVsAdjDiff.value === 0,
)

function fmt(n: number | null | undefined): string {
  if (n == null || n === 0) return '—'
  return n.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function amountRowClass({ row }: { row: { kind: string } }) {
  if (row.kind === 'header') return 'row-header'
  if (row.kind === 'subtotal') return 'row-subtotal'
  return ''
}

function onIndicatorsChange(rowKey: string, indicators: string[]) {
  updateInputField(rowKey, 'selectedIndicators', indicators)
  updateInputField(rowKey, 'inputs', indicators.join('、'))
}

async function syncToNotes() {
  if (isSyncing.value || props.isReadonly || !projectId.value || !wpId.value) return
  const payload = buildG1SyncPayload(
    'listed',
    wpId.value,
    props.applicableStandards ?? [],
    buildG1ListedSubTableData(getSyncSnapshot()),
  )
  if (!payload) {
    ElMessage.warning('无法构建附注同步 payload')
    return
  }
  isSyncing.value = true
  try {
    const result: any = await api.post(
      `/api/projects/${projectId.value}/disclosure-notes/sync-from-workpaper`,
      payload,
    )
    const data = result?.data ?? result
    ElMessage.success(`已同步 ${Number(data?.rows_synced ?? 0)} 行到附注「${noteSectionId} 交易性金融资产」`)
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}
</script>

<style scoped>
.g1-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; gap: 12px; flex-wrap: wrap; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.objective-alert, .sync-hint { margin-bottom: 10px; }
.prep-hint { margin: 0 0 12px; font-size: 12px; color: #606266; }
.prep-hint summary { cursor: pointer; color: #4b2d77; font-weight: 500; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
.disc-tabs { margin-top: 4px; }
.tab-toolbar { display: flex; gap: 12px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.hint { font-size: 12px; color: #909399; }
.strong { font-weight: 600; }
.text-block { margin-top: 12px; }
.text-label { font-size: 13px; font-weight: 500; margin-bottom: 6px; color: #303133; }
.diff-warn { color: #e6a23c; font-weight: 600; }
.formula { border-bottom: 1px dashed #909399; }
:deep(.row-header) { background: #f4f0fa !important; }
:deep(.row-subtotal) { background: #f0f2f5 !important; font-weight: 600; }
:deep(.el-table) { font-size: 13px; }
:deep(.el-table th),
:deep(.el-table td),
:deep(.el-table .cell) { font-size: 13px; }
/* 项目 + 金额列（分类/衍生）宽表：限制整体宽度，避免在超宽容器里项目列被拉伸出大片空白、金额列被挤到右侧 */
.amount-table { max-width: 760px; }
</style>
