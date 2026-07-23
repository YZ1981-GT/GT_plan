<script setup lang="ts">
/**
 * B22AControlItemDialog — B22A 内部控制了解 · 引导式录入向导
 *
 * 以「分组卡片 + 逻辑流」替代扁平表格填报，体现审计了解逻辑：
 *   ① 控制识别（COSO 原则/关注点参考 + 控制要点 + 描述）
 *   ② 了解程序（了解方法多选）
 *   ③ 控制属性登记（B22B 矩阵字段：反舞弊/频率/执行人/胜任能力/风险/自动人工/IT应用）
 *   ④ 设计有效性评价（结论 + 实时缺陷提示）
 *   ⑤ 拟测试决策（是否拟测试→C 类 + 测试方法）
 * 右侧实时逻辑面板：随录入即时反馈缺陷/联动提示。
 */
import { ref, computed, watch } from 'vue'
import {
  CONCLUSIONS,
  UNDERSTANDING_METHODS,
  type Conclusion,
  type UnderstandingMethod,
} from './composables/useB22AControlMatrix'
import type { ElementReference } from './composables/b22aReference'
import {
  CONTROL_FREQUENCY_OPTIONS,
  CONTROL_PERFORMER_OPTIONS,
  CONTROL_RISK_OPTIONS,
  CONTROL_NATURE_OPTIONS,
  CONTROL_TEST_METHOD_OPTIONS,
} from './composables/b22aReference'

interface ItemForm {
  controlPoint: string
  description: string
  methods: UnderstandingMethod[]
  conclusion: Conclusion | null
  reference: string
}

const props = defineProps<{
  visible: boolean
  title?: string
  elementRef: ElementReference | null
  /** 当前检查项（编辑）或空（新增） */
  item: ItemForm
  /** 控制属性 JSON */
  attrs: Record<string, any>
  isReadonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'save', payload: { form: ItemForm; attrs: Record<string, any> }): void
}>()

// ─── 本地可编辑副本 ──────────────────────────────────────────────────────────

const form = ref<ItemForm>({ controlPoint: '', description: '', methods: [], conclusion: null, reference: '' })
const attrs = ref<Record<string, any>>({})

watch(
  () => props.visible,
  (v) => {
    if (v) {
      form.value = {
        controlPoint: props.item.controlPoint || '',
        description: props.item.description || '',
        methods: [...(props.item.methods || [])],
        conclusion: props.item.conclusion ?? null,
        reference: props.item.reference || '',
      }
      attrs.value = { ...(props.attrs || {}) }
    }
  },
  { immediate: true },
)

const FREQUENCY = CONTROL_FREQUENCY_OPTIONS
const PERFORMER = CONTROL_PERFORMER_OPTIONS
const RISK = CONTROL_RISK_OPTIONS
const NATURE = CONTROL_NATURE_OPTIONS
const TEST_METHOD = CONTROL_TEST_METHOD_OPTIONS

// ─── 实时逻辑面板 ────────────────────────────────────────────────────────────

const isDeficiency = computed(
  () => form.value.conclusion === '设计无效' || form.value.conclusion === '未实施',
)
const onlyInquiry = computed(
  () => form.value.methods.length === 1 && form.value.methods[0] === '询问',
)
const toTest = computed(() => attrs.value.toTest === 'Y')

const logicHints = computed(() => {
  const hints: { type: 'warn' | 'info' | 'ok'; text: string }[] = []
  if (isDeficiency.value) {
    hints.push({ type: 'warn', text: `评价为「${form.value.conclusion}」→ 自动进入控制缺陷清单，并联动 B22B 缺陷评价` })
  }
  if (form.value.conclusion && !isDeficiency.value && form.value.conclusion !== '不适用') {
    hints.push({ type: 'ok', text: '评价有效 → 该控制计入有效项统计' })
  }
  if (onlyInquiry.value) {
    hints.push({ type: 'warn', text: '仅实施「询问」不足以确定控制得到执行，建议补充观察/检查文件/穿行测试' })
  }
  if (attrs.value.antiFraud === 'Y') {
    hints.push({ type: 'info', text: '标记为反舞弊控制 → 关注管理层凌驾于控制之上（CAS 1141）' })
  }
  if (toTest.value) {
    hints.push({ type: 'info', text: '已标记「拟测试」→ 将联动 C1 企业层面控制测试；建议明确测试方法' })
    if (!attrs.value.testMethod) {
      hints.push({ type: 'warn', text: '拟测试控制尚未选择控制测试方法' })
    }
  }
  if (!form.value.controlPoint.trim()) {
    hints.push({ type: 'warn', text: '控制要点尚未填写' })
  }
  return hints
})

// ─── 套用关注点为控制要点 ────────────────────────────────────────────────────

function applyExampleToPoint(example: string) {
  if (props.isReadonly) return
  form.value.controlPoint = form.value.controlPoint
    ? `${form.value.controlPoint}\n${example}`
    : example
}

function setAttr(key: string, val: unknown) {
  if (props.isReadonly) return
  attrs.value = { ...attrs.value, [key]: val }
}

function onClose() {
  emit('update:visible', false)
}

function onSave() {
  emit('save', { form: form.value, attrs: attrs.value })
  emit('update:visible', false)
}
</script>

<template>
  <el-dialog
    :model-value="visible"
    :title="title || '内部控制了解 · 引导式录入'"
    width="920px"
    top="5vh"
    :close-on-click-modal="false"
    class="b22a-item-dialog"
    @update:model-value="(v: boolean) => emit('update:visible', v)"
    @close="onClose"
  >
    <div class="b22a-dialog-body">
      <!-- 左：分组卡片 -->
      <div class="b22a-dialog-main">
        <!-- 审计目标 -->
        <el-alert v-if="elementRef" :closable="false" type="info" class="dlg-objective">
          <template #title><strong>{{ elementRef.elementName }} · 审计目标：</strong>{{ elementRef.auditObjective }}</template>
        </el-alert>

        <!-- ① 控制识别 -->
        <el-card shadow="never" class="dlg-card">
          <template #header><span class="dlg-card-t">① 控制识别</span></template>
          <div v-if="elementRef" class="coso-ref">
            <div class="coso-ref-label">COSO 原则 / 关注点（点击「关注点」可套用为控制要点）：</div>
            <div v-for="p in elementRef.principles" :key="p.no" class="coso-ref-row">
              <span class="coso-ref-no">原则 {{ p.no }}</span>
              <span class="coso-ref-title">{{ p.title }}</span>
              <span class="coso-ref-pofs">
                <el-tag
                  v-for="(pf, i) in p.pointsOfFocus"
                  :key="i"
                  size="small"
                  effect="plain"
                  class="pof-chip"
                  :class="{ clickable: !isReadonly }"
                  @click="applyExampleToPoint(pf)"
                >{{ pf }}</el-tag>
              </span>
            </div>
          </div>
          <el-form label-position="top" class="dlg-form">
            <el-form-item label="控制要点（该控制在做什么）">
              <el-input v-model="form.controlPoint" :disabled="isReadonly" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" placeholder="描述被审计单位设计的控制..." />
            </el-form-item>
            <el-form-item label="信息来源及控制如何得到执行">
              <el-input v-model="form.description" :disabled="isReadonly" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" placeholder="记录信息来源（询问/文件/观察）及控制执行情况..." />
            </el-form-item>
          </el-form>
        </el-card>

        <!-- ② 了解程序 -->
        <el-card shadow="never" class="dlg-card">
          <template #header><span class="dlg-card-t">② 了解程序</span></template>
          <el-form label-position="top" class="dlg-form">
            <el-form-item label="了解方法（可多选）">
              <el-checkbox-group v-model="form.methods" :disabled="isReadonly">
                <el-checkbox v-for="m in UNDERSTANDING_METHODS" :key="m" :label="m" :value="m" border />
              </el-checkbox-group>
            </el-form-item>
            <el-form-item label="参考引用 / 索引">
              <el-input v-model="form.reference" :disabled="isReadonly" placeholder="如：访谈记录 / 文件索引 / C23" style="max-width: 320px" />
            </el-form-item>
          </el-form>
        </el-card>

        <!-- ③ 控制属性登记 -->
        <el-card shadow="never" class="dlg-card">
          <template #header><span class="dlg-card-t">③ 控制属性登记（控制矩阵）</span></template>
          <div class="attr-grid">
            <div class="attr-cell">
              <label>是否反舞弊控制</label>
              <el-radio-group :model-value="attrs.antiFraud || ''" :disabled="isReadonly" size="small" @update:model-value="(v: any) => setAttr('antiFraud', v)">
                <el-radio-button value="Y">是</el-radio-button><el-radio-button value="N">否</el-radio-button>
              </el-radio-group>
            </div>
            <div class="attr-cell">
              <label>控制频率</label>
              <el-select :model-value="attrs.frequency || ''" :disabled="isReadonly" size="small" placeholder="选择" @update:model-value="(v: string) => setAttr('frequency', v)">
                <el-option v-for="f in FREQUENCY" :key="f" :label="f" :value="f" />
              </el-select>
            </div>
            <div class="attr-cell">
              <label>执行人</label>
              <el-select :model-value="attrs.performer || ''" :disabled="isReadonly" size="small" placeholder="选择" @update:model-value="(v: string) => setAttr('performer', v)">
                <el-option v-for="p in PERFORMER" :key="p" :label="p" :value="p" />
              </el-select>
            </div>
            <div class="attr-cell">
              <label>与控制相关的风险</label>
              <el-select :model-value="attrs.risk || ''" :disabled="isReadonly" size="small" placeholder="选择" @update:model-value="(v: string) => setAttr('risk', v)">
                <el-option v-for="r in RISK" :key="r" :label="r" :value="r" />
              </el-select>
            </div>
            <div class="attr-cell">
              <label>自动 / 人工</label>
              <el-select :model-value="attrs.nature || ''" :disabled="isReadonly" size="small" placeholder="选择" @update:model-value="(v: string) => setAttr('nature', v)">
                <el-option v-for="n in NATURE" :key="n" :label="n" :value="n" />
              </el-select>
            </div>
            <div class="attr-cell">
              <label>执行人胜任能力</label>
              <el-input :model-value="attrs.competence || ''" :disabled="isReadonly" size="small" placeholder="知识/经验/技能" @update:model-value="(v: string) => setAttr('competence', v)" />
            </div>
            <div class="attr-cell">
              <label>IT 应用名称（如适用）</label>
              <el-input :model-value="attrs.itApp || ''" :disabled="isReadonly" size="small" placeholder="如适用" @update:model-value="(v: string) => setAttr('itApp', v)" />
            </div>
          </div>
        </el-card>

        <!-- ④ 设计有效性评价 -->
        <el-card shadow="never" class="dlg-card">
          <template #header><span class="dlg-card-t">④ 设计有效性评价</span></template>
          <el-radio-group v-model="form.conclusion" :disabled="isReadonly">
            <el-radio-button v-for="c in CONCLUSIONS" :key="c" :value="c">{{ c }}</el-radio-button>
          </el-radio-group>
          <div v-if="isDeficiency" class="deficiency-flag">⚠ 该控制构成控制缺陷，将自动汇总至缺陷清单</div>
        </el-card>

        <!-- ⑤ 拟测试决策 -->
        <el-card shadow="never" class="dlg-card">
          <template #header><span class="dlg-card-t">⑤ 拟测试决策（联动 C 类控制测试）</span></template>
          <div class="attr-grid">
            <div class="attr-cell">
              <label>是否拟测试运行有效性</label>
              <el-radio-group :model-value="attrs.toTest || ''" :disabled="isReadonly" size="small" @update:model-value="(v: any) => setAttr('toTest', v)">
                <el-radio-button value="Y">是</el-radio-button><el-radio-button value="N">否</el-radio-button>
              </el-radio-group>
            </div>
            <div v-if="toTest" class="attr-cell">
              <label>控制测试方法</label>
              <el-select :model-value="attrs.testMethod || ''" :disabled="isReadonly" size="small" placeholder="选择" @update:model-value="(v: string) => setAttr('testMethod', v)">
                <el-option v-for="tm in TEST_METHOD" :key="tm" :label="tm" :value="tm" />
              </el-select>
            </div>
          </div>
        </el-card>
      </div>

      <!-- 右：实时逻辑面板 -->
      <div class="b22a-dialog-side">
        <div class="side-title">📋 逻辑与联动提示</div>
        <div v-if="logicHints.length === 0" class="side-empty">按左侧步骤录入，此处将实时提示缺陷判定与跨底稿联动。</div>
        <div v-for="(h, i) in logicHints" :key="i" class="side-hint" :class="`side-hint--${h.type}`">
          {{ h.text }}
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="onClose">取消</el-button>
      <el-button type="primary" :disabled="isReadonly" @click="onSave">保存</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.b22a-dialog-body {
  display: flex;
  gap: 14px;
  max-height: 72vh;
  overflow: hidden;
  font-size: 13px;
  color: #303133;
}
.b22a-dialog-body :deep(.el-form-item__label),
.b22a-dialog-body :deep(.el-input__inner),
.b22a-dialog-body :deep(.el-textarea__inner),
.b22a-dialog-body :deep(.el-checkbox__label),
.b22a-dialog-body :deep(.el-radio__label) {
  font-size: 13px;
}
.b22a-dialog-main {
  flex: 1;
  overflow-y: auto;
  padding-right: 4px;
}
.b22a-dialog-side {
  width: 260px;
  flex-shrink: 0;
  background: #F8FAFC;
  border: 1px solid #E5E7EB;
  border-radius: 6px;
  padding: 12px;
  overflow-y: auto;
}
.dlg-objective { margin-bottom: 10px; }
.dlg-card { margin-bottom: 10px; }
.dlg-card-t { font-weight: 600; font-size: 14px; color: #4b2d77; }
.dlg-form :deep(.el-form-item) { margin-bottom: 12px; }
.coso-ref {
  background: #FEFCF5;
  border: 1px solid #FDE9C8;
  border-radius: 4px;
  padding: 8px 10px;
  margin-bottom: 12px;
  font-size: 12px;
}
.coso-ref-label { color: #92400E; font-weight: 600; margin-bottom: 6px; }
.coso-ref-row { display: flex; align-items: flex-start; gap: 6px; margin-bottom: 5px; flex-wrap: wrap; }
.coso-ref-no { color: #B45309; font-weight: 600; white-space: nowrap; }
.coso-ref-title { color: #374151; white-space: nowrap; }
.coso-ref-pofs { display: flex; flex-wrap: wrap; gap: 4px; }
.pof-chip.clickable { cursor: pointer; }
.pof-chip.clickable:hover { background: #FEF3C7; }
.attr-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}
.attr-cell { display: flex; flex-direction: column; gap: 5px; }
.attr-cell label { font-size: 12px; color: #6B7280; }
.deficiency-flag {
  margin-top: 10px;
  color: #DC2626;
  background: #FEE2E2;
  border-radius: 4px;
  padding: 6px 10px;
  font-size: 13px;
  font-weight: 500;
}
.side-title { font-weight: 600; color: #374151; margin-bottom: 10px; }
.side-empty { font-size: 12px; color: #9CA3AF; line-height: 1.6; }
.side-hint {
  font-size: 12px;
  line-height: 1.5;
  border-radius: 4px;
  padding: 7px 9px;
  margin-bottom: 8px;
}
.side-hint--warn { background: #FEF3C7; color: #92400E; border-left: 3px solid #D97706; }
.side-hint--info { background: #EFF6FF; color: #1D4ED8; border-left: 3px solid #3B82F6; }
.side-hint--ok { background: #D1FAE5; color: #059669; border-left: 3px solid #059669; }
</style>
