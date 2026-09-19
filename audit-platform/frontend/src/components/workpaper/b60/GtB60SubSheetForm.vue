<script setup lang="ts">
/**
 * GtB60SubSheetForm — B60 结构化子底稿通用渲染器（schema 驱动）
 *
 * 按 B60_SUBSHEET_SCHEMAS 渲染 fields / questionnaire / table 三类 section，
 * 全部字段可点选/可编辑，持久化到子底稿自身 wp_id 的 checklist_responses。
 *
 * Spec: b60-strategy-rework（直接修复）
 */
import { computed } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useB60SubSheet } from './composables/useB60SubSheet'
import { B60_SUBSHEET_SCHEMAS, type B60Section, type B60Column } from './constants/subSheetSchemas'

const props = defineProps<{
  wpId: string
  code: string
  readonly?: boolean
}>()

const schema = computed(() => B60_SUBSHEET_SCHEMAS[props.code])

const { store, saveStatus, loading, markDirty } = useB60SubSheet({
  wpId: computed(() => props.wpId) as any,
  schema: schema.value,
})

// ─── fields ───
function fieldVal(sectionId: string, key: string): string {
  return store[sectionId]?.[key] ?? ''
}
function setField(sectionId: string, key: string, val: string): void {
  if (!store[sectionId]) store[sectionId] = {}
  store[sectionId][key] = val
  markDirty(sectionId)
}

// ─── questionnaire ───
function qAnswer(sectionId: string, key: string): string {
  return store[sectionId]?.[key]?.answer ?? ''
}
function qNote(sectionId: string, key: string): string {
  return store[sectionId]?.[key]?.note ?? ''
}
function setQAnswer(sectionId: string, key: string, val: string): void {
  if (!store[sectionId]) store[sectionId] = {}
  if (!store[sectionId][key]) store[sectionId][key] = { answer: '', note: '' }
  store[sectionId][key].answer = val
  markDirty(sectionId)
}
function setQNote(sectionId: string, key: string, val: string): void {
  if (!store[sectionId]) store[sectionId] = {}
  if (!store[sectionId][key]) store[sectionId][key] = { answer: '', note: '' }
  store[sectionId][key].note = val
  markDirty(sectionId)
}
function isRiskSignal(sectionId: string, key: string, type?: string): boolean {
  // 答"是"通常代表触发/风险信号（除 yesnona 的中性项外，统一高亮"是"）
  return qAnswer(sectionId, key) === '是'
}

// ─── table ───
function tableRows(sectionId: string): Record<string, string>[] {
  return store[sectionId]?.rows ?? []
}
function setCell(sectionId: string, rowIdx: number, key: string, val: string): void {
  const rows = tableRows(sectionId)
  if (rows[rowIdx]) {
    rows[rowIdx][key] = val
    markDirty(sectionId)
  }
}
async function addRow(section: B60Section): Promise<void> {
  if (!store[section.id]) store[section.id] = { rows: [] }
  if (!store[section.id].rows) store[section.id].rows = []
  const empty: Record<string, string> = {}
  ;(section.columns || []).forEach((c) => (empty[c.key] = ''))
  // 需命名的动态行先弹 prompt（对齐平台铁律）
  if (section.rowLabel && section.columns && section.columns.length > 0) {
    try {
      const { value } = await ElMessageBox.prompt(`请输入${section.rowLabel}名称`, '新增行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
      })
      empty[section.columns[0].key] = value || ''
    } catch {
      return
    }
  }
  store[section.id].rows.push(empty)
  markDirty(section.id)
}
function removeRow(sectionId: string, rowIdx: number): void {
  const rows = tableRows(sectionId)
  rows.splice(rowIdx, 1)
  markDirty(sectionId)
}

function yesnoOptions(type?: string): string[] {
  return type === 'yesnona' ? ['是', '否', '不适用'] : ['是', '否']
}
</script>

<template>
  <div class="b60-subsheet" v-loading="loading">
    <div class="subsheet-head">
      <span class="subsheet-title">{{ schema?.title }}</span>
      <span class="save-status" :class="`save-status--${saveStatus}`">
        {{ saveStatus === 'saved' ? '✓ 已保存' : saveStatus === 'saving' ? '保存中…' : '● 未保存' }}
      </span>
    </div>

    <el-card
      v-for="section in schema?.sections || []"
      :key="section.id"
      shadow="never"
      class="section-card"
    >
      <template #header>
        <span class="section-title">{{ section.title }}</span>
      </template>

      <details v-if="section.hint" class="amber-hint" open>
        <summary>编制提示</summary>
        <div class="hint-content">{{ section.hint }}</div>
      </details>

      <!-- ─── fields ─── -->
      <div v-if="section.kind === 'fields'" class="fields-grid">
        <div v-for="f in section.fields" :key="f.key" class="field-row">
          <label class="field-label">{{ f.label }}</label>
          <div class="field-control">
            <el-input
              v-if="f.type === 'text'"
              :model-value="fieldVal(section.id, f.key)"
              :disabled="readonly"
              @update:model-value="(v: string) => setField(section.id, f.key, v)"
            />
            <el-input
              v-else-if="f.type === 'textarea'"
              type="textarea"
              :autosize="{ minRows: 3 }"
              :model-value="fieldVal(section.id, f.key)"
              :disabled="readonly"
              @update:model-value="(v: string) => setField(section.id, f.key, v)"
            />
            <el-date-picker
              v-else-if="f.type === 'date'"
              :model-value="fieldVal(section.id, f.key)"
              type="date"
              value-format="YYYY-MM-DD"
              :disabled="readonly"
              @update:model-value="(v: string) => setField(section.id, f.key, v)"
            />
            <el-select
              v-else-if="f.type === 'select'"
              :model-value="fieldVal(section.id, f.key)"
              :disabled="readonly"
              clearable
              @update:model-value="(v: string) => setField(section.id, f.key, v)"
            >
              <el-option v-for="o in f.options" :key="o" :label="o" :value="o" />
            </el-select>
            <el-radio-group
              v-else
              :model-value="fieldVal(section.id, f.key)"
              :disabled="readonly"
              @update:model-value="(v: string) => setField(section.id, f.key, v as string)"
            >
              <el-radio v-for="o in yesnoOptions(f.type)" :key="o" :value="o">{{ o }}</el-radio>
            </el-radio-group>
            <span v-if="f.hint" class="field-hint">{{ f.hint }}</span>
          </div>
        </div>
      </div>

      <!-- ─── questionnaire ─── -->
      <div v-else-if="section.kind === 'questionnaire'" class="questionnaire">
        <template v-for="group in section.groups" :key="group.label || 'g'">
          <div v-if="group.label" class="q-group-label">{{ group.label }}</div>
          <div
            v-for="q in group.items"
            :key="q.key"
            class="q-item"
            :class="{ 'q-item--signal': isRiskSignal(section.id, q.key, q.type) }"
          >
            <div class="q-label">{{ q.label }}</div>
            <div class="q-controls">
              <el-radio-group
                :model-value="qAnswer(section.id, q.key)"
                :disabled="readonly"
                @update:model-value="(v: string) => setQAnswer(section.id, q.key, v as string)"
              >
                <el-radio v-for="o in yesnoOptions(q.type)" :key="o" :value="o">{{ o }}</el-radio>
              </el-radio-group>
              <el-input
                :model-value="qNote(section.id, q.key)"
                :disabled="readonly"
                size="small"
                placeholder="说明"
                class="q-note"
                @update:model-value="(v: string) => setQNote(section.id, q.key, v)"
              />
            </div>
          </div>
        </template>
      </div>

      <!-- ─── table ─── -->
      <div v-else-if="section.kind === 'table'" class="table-wrap">
        <el-table :data="tableRows(section.id)" size="small" border>
          <el-table-column type="index" label="#" width="48" />
          <el-table-column
            v-for="col in section.columns"
            :key="col.key"
            :label="col.label"
            :min-width="col.minWidth || 120"
          >
            <template #default="{ row, $index }">
              <el-select
                v-if="col.type === 'select'"
                :model-value="row[col.key]"
                :disabled="readonly"
                size="small"
                clearable
                @update:model-value="(v: string) => setCell(section.id, $index, col.key, v)"
              >
                <el-option v-for="o in col.options" :key="o" :label="o" :value="o" />
              </el-select>
              <el-radio-group
                v-else-if="col.type === 'yesno' || col.type === 'yesnona'"
                :model-value="row[col.key]"
                :disabled="readonly"
                size="small"
                @update:model-value="(v: string) => setCell(section.id, $index, col.key, v as string)"
              >
                <el-radio v-for="o in yesnoOptions(col.type)" :key="o" :value="o">{{ o }}</el-radio>
              </el-radio-group>
              <el-input
                v-else-if="col.type === 'textarea'"
                type="textarea"
                :autosize="{ minRows: 1, maxRows: 4 }"
                :model-value="row[col.key]"
                :disabled="readonly"
                size="small"
                @update:model-value="(v: string) => setCell(section.id, $index, col.key, v)"
              />
              <el-input
                v-else
                :model-value="row[col.key]"
                :disabled="readonly"
                size="small"
                @update:model-value="(v: string) => setCell(section.id, $index, col.key, v)"
              />
            </template>
          </el-table-column>
          <el-table-column v-if="section.addable && !readonly" label="操作" width="70" align="center">
            <template #default="{ $index }">
              <el-button link type="danger" size="small" @click="removeRow(section.id, $index)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-button
          v-if="section.addable && !readonly"
          size="small"
          class="add-row-btn"
          @click="addRow(section)"
        >
          + 新增{{ section.rowLabel || '行' }}
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.b60-subsheet {
  font-size: 13px;
}

.subsheet-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.subsheet-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.save-status {
  font-size: 12px;
}
.save-status--saved { color: #67c23a; }
.save-status--saving { color: #909399; }
.save-status--unsaved { color: #e6a23c; }

.section-card {
  margin-bottom: 14px;
  border-left: 3px solid var(--el-color-primary);
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.amber-hint {
  border-left: 3px solid #f59e0b;
  background: #fffbeb;
  padding: 8px 12px;
  margin-bottom: 12px;
  border-radius: 4px;
}
.amber-hint summary {
  cursor: pointer;
  font-weight: 500;
  color: #92400e;
  font-size: 12px;
}
.hint-content {
  margin-top: 6px;
  color: #78350f;
  font-size: 12px;
  line-height: 1.6;
}

/* fields */
.fields-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.field-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}
.field-label {
  width: 180px;
  min-width: 180px;
  color: #606266;
  padding-top: 6px;
}
.field-control {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.field-hint {
  color: #909399;
  font-size: 12px;
}

/* questionnaire */
.questionnaire {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.q-group-label {
  font-weight: 600;
  color: #409eff;
  margin: 8px 0 4px;
  font-size: 13px;
}
.q-item {
  padding: 8px 10px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
}
.q-item--signal {
  background: #fef0f0;
  border-color: #fbc4c4;
}
.q-label {
  color: #303133;
  line-height: 1.5;
  margin-bottom: 6px;
}
.q-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}
.q-note {
  flex: 1;
  max-width: 420px;
}

/* table */
.table-wrap {
  overflow-x: auto;
}
.add-row-btn {
  margin-top: 8px;
}
</style>
