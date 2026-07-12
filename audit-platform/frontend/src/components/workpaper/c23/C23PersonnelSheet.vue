<template>
  <div class="c23-personnel-sheet">
    <!-- 编制提示（源模板示例参考） -->
    <details class="c23-edit-hint" open>
      <summary class="c23-edit-hint-summary">📖 编制提示 — 参照示例</summary>
      <div class="c23-edit-hint-body">
        <p><strong>目标：</strong>将观察得出实际设置与被审计单位提供的职员名单进行比较，确认清单的完整性和准确性。</p>
        <p><strong>数据来源：</strong>① 创建、授权及记录会计分录的人员名单 ② 相关应用程序中的人员权限设置清单</p>
        <p><strong>程序：</strong>① 获取人员名单 → ② 从信息管理部门获取应用程序人员设置清单 → ③ 将两份清单比较 → ④ 对异常予以查询验证</p>
        <p class="c23-edit-hint-example"><strong>示例结论：</strong>经测试，应用程序设置清单包括了人员名单中的相关人员，其访问权限与人员名单中赋予职责一致。人员清单不存在异常。</p>
      </div>
    </details>

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <div class="methodology-bar" />
      <p>C23-1 会计人员清单完整性测试：维护经授权的会计人员清单，后续在 C23-2 中核对样本分录人员是否在此清单内。</p>
    </div>

    <!-- 数据来源描述 -->
    <section class="c23-section">
      <div class="section-header">
        <span class="section-title">1. 数据来源描述</span>
        <el-button v-if="!isReadonly" size="small" type="primary" plain @click="$emit('ai-suggest')">
          <span>✨ AI</span>
        </el-button>
      </div>
      <el-input
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :model-value="sourceDesc"
        :disabled="isReadonly"
        placeholder="请说明数据来源，如：&#10;1. 创建、授权及记录会计分录的人员名单（来源：XX系统导出）&#10;2. 相关应用程序中的人员权限设置清单（来源：IT部门直接打印）"
        @input="$emit('update:source-desc', $event)"
      />
    </section>

    <!-- 授权人员清单（参照示例增加列） -->
    <section class="c23-section">
      <div class="section-header">
        <span class="section-title">2. 授权人员清单</span>
        <el-button
          v-if="!isReadonly"
          type="primary"
          size="small"
          @click="openAddPersonDialog"
        >
          + 新增人员
        </el-button>
      </div>

      <el-table
        :data="persons"
        border
        size="small"
        class="c23-table"
        empty-text="暂无授权人员，请点击「新增人员」添加"
      >
        <el-table-column label="序号" width="50" align="center">
          <template #default="{ row }">{{ row.seq }}</template>
        </el-table-column>
        <el-table-column label="用户编号" min-width="90">
          <template #default="{ row, $index }">
            <el-input
              :model-value="row.code || ''"
              :disabled="isReadonly"
              size="small"
              placeholder="如FN03"
              @input="$emit('update-person', $index, 'code', $event)"
            />
          </template>
        </el-table-column>
        <el-table-column label="姓名" min-width="100">
          <template #default="{ row, $index }">
            <el-input
              :model-value="row.name"
              :disabled="isReadonly"
              size="small"
              placeholder="姓名"
              @input="$emit('update-person', $index, 'name', $event)"
            />
          </template>
        </el-table-column>
        <el-table-column label="职位" min-width="100">
          <template #default="{ row, $index }">
            <el-input
              :model-value="row.role"
              :disabled="isReadonly"
              size="small"
              placeholder="职位"
              @input="$emit('update-person', $index, 'role', $event)"
            />
          </template>
        </el-table-column>
        <el-table-column label="职责" min-width="140">
          <template #default="{ row, $index }">
            <el-input
              :model-value="row.note"
              :disabled="isReadonly"
              size="small"
              placeholder="职责描述"
              @input="$emit('update-person', $index, 'note', $event)"
            />
          </template>
        </el-table-column>
        <el-table-column label="编制" width="60" align="center">
          <template #default="{ row, $index }">
            <el-checkbox
              :model-value="row.canCreate === '√'"
              :disabled="isReadonly"
              @change="(v: any) => $emit('update-person', $index, 'canCreate', v ? '√' : '')"
            />
          </template>
        </el-table-column>
        <el-table-column label="批准" width="60" align="center">
          <template #default="{ row, $index }">
            <el-checkbox
              :model-value="row.canApprove === '√'"
              :disabled="isReadonly"
              @change="(v: any) => $emit('update-person', $index, 'canApprove', v ? '√' : '')"
            />
          </template>
        </el-table-column>
        <el-table-column label="过账" width="60" align="center">
          <template #default="{ row, $index }">
            <el-checkbox
              :model-value="row.canPost === '√'"
              :disabled="isReadonly"
              @change="(v: any) => $emit('update-person', $index, 'canPost', v ? '√' : '')"
            />
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="60" align="center">
          <template #default="{ $index }">
            <el-button type="danger" size="small" link @click="$emit('remove-person', $index)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- 3. 测试结果及分析 -->
    <section class="c23-section">
      <div class="section-header">
        <span class="section-title">3. 测试结果及分析</span>
        <el-button v-if="!isReadonly" size="small" type="primary" plain @click="$emit('ai-suggest')">
          <span>✨ AI 生成分析</span>
        </el-button>
      </div>
      <el-input
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :model-value="analysisText"
        :disabled="isReadonly"
        placeholder="描述测试结果及分析，如：经测试，应用程序设置清单包括了人员名单中的XX和XX，其访问权限与人员名单中赋予职责一致。"
        @input="$emit('update:analysis', $event)"
      />
    </section>

    <!-- 4. 测试结论 -->
    <section class="c23-section">
      <div class="section-header">
        <span class="section-title">4. 测试结论</span>
      </div>
      <el-select
        :model-value="conclusion1Select"
        :disabled="isReadonly"
        size="default"
        placeholder="请选择测试结论"
        style="width: 100%; margin-bottom: 8px;"
        @change="onConclusionSelect"
      >
        <el-option label="人员清单不存在异常" value="人员清单不存在异常" />
        <el-option label="未发现偏差" value="未发现偏差" />
        <el-option label="发现偏差-影响不重大" value="发现偏差-影响不重大" />
        <el-option label="发现偏差-影响重大" value="发现偏差-影响重大" />
      </el-select>
      <el-input
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :model-value="conclusion1Detail"
        :disabled="isReadonly"
        placeholder="补充说明（可选）"
        @input="onConclusionDetailInput"
      />
    </section>

    <!-- ═══ 新增人员 Dialog ═══ -->
    <el-dialog
      v-model="addPersonDialogVisible"
      title="新增授权人员"
      width="500px"
      :close-on-click-modal="false"
      append-to-body
    >
      <div class="c23-add-person-hint">
        💡 填写经授权可创建/批准/过账会计分录的人员信息。可通过 AI 从系统截图或描述中自动提取。
      </div>
      <el-form label-position="top" class="c23-add-person-form">
        <el-form-item label="用户编号" required>
          <el-input v-model="newPerson.code" placeholder="如 FN03、AC001" size="default" />
        </el-form-item>
        <el-form-item label="姓名" required>
          <el-input v-model="newPerson.name" placeholder="人员姓名" size="default" />
        </el-form-item>
        <el-form-item label="职位">
          <el-input v-model="newPerson.role" placeholder="如：会计经理、助理经理" size="default" />
        </el-form-item>
        <el-form-item label="职责">
          <el-input v-model="newPerson.note" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" placeholder="该人员的主要职责描述" />
        </el-form-item>
        <el-form-item label="权限（可多选）">
          <el-checkbox-group v-model="newPersonPermissions">
            <el-checkbox label="编制" value="编制">编制分录</el-checkbox>
            <el-checkbox label="批准" value="批准">批准分录</el-checkbox>
            <el-checkbox label="过账" value="过账">过账</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
      </el-form>

      <!-- AI 辅助区 -->
      <div class="c23-add-person-ai">
        <el-input
          v-model="aiPersonInput"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 4 }"
          placeholder="粘贴人员信息文本或描述（如：张三 FN03 会计经理 负责复核 可编制和批准分录），AI 将自动解析填入"
        />
        <el-button type="primary" plain size="small" style="margin-top: 8px" @click="aiParsePerson">
          ✨ AI 解析填入
        </el-button>
      </div>

      <template #footer>
        <el-button @click="addPersonDialogVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!newPerson.name.trim()" @click="confirmAddPerson">确认添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * C23PersonnelSheet — C23-1 会计人员清单完整性测试表
 *
 * 增强版：参照源模板示例，加入编制提示+用户编号+权限三列+测试分析+AI辅助
 */
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps<{
  wpId: string
  projectId?: string
  persons: Array<{ seq: number; name: string; role: string; note: string; code?: string; canCreate?: string; canApprove?: string; canPost?: string }>
  sourceDesc: string
  analysisText?: string
  conclusion1: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'update:source-desc', val: string): void
  (e: 'update:analysis', val: string): void
  (e: 'update:conclusion1', val: string): void
  (e: 'add-person'): void
  (e: 'add-person-full', person: { code: string; name: string; role: string; note: string; canCreate: string; canApprove: string; canPost: string }): void
  (e: 'remove-person', index: number): void
  (e: 'update-person', index: number, field: string, value: string): void
  (e: 'ai-suggest'): void
}>()

// 结论解析
const CONCLUSION_OPTIONS = ['人员清单不存在异常', '未发现偏差', '发现偏差-影响不重大', '发现偏差-影响重大']
const conclusion1Select = computed(() => {
  const raw = props.conclusion1 || ''
  const selectPart = raw.split('||')[0] || ''
  return CONCLUSION_OPTIONS.includes(selectPart) ? selectPart : ''
})
const conclusion1Detail = computed(() => {
  const raw = props.conclusion1 || ''
  const parts = raw.split('||')
  if (parts.length > 1) return parts.slice(1).join('||')
  if (!CONCLUSION_OPTIONS.includes(raw)) return raw
  return ''
})

function onConclusionSelect(val: string) {
  const detail = conclusion1Detail.value
  emit('update:conclusion1', detail ? `${val}||${detail}` : val)
}

function onConclusionDetailInput(val: string) {
  const sel = conclusion1Select.value
  emit('update:conclusion1', sel ? `${sel}||${val}` : val)
}

// ─── 新增人员 Dialog ───
const addPersonDialogVisible = ref(false)
const newPerson = ref({ code: '', name: '', role: '', note: '' })
const newPersonPermissions = ref<string[]>([])
const aiPersonInput = ref('')

function openAddPersonDialog() {
  newPerson.value = { code: '', name: '', role: '', note: '' }
  newPersonPermissions.value = []
  aiPersonInput.value = ''
  addPersonDialogVisible.value = true
}

function confirmAddPerson() {
  if (!newPerson.value.name.trim()) {
    ElMessage.warning('姓名不能为空')
    return
  }
  // 通过 emit 传递完整的人员信息给父组件
  emit('add-person-full', {
    code: newPerson.value.code.trim(),
    name: newPerson.value.name.trim(),
    role: newPerson.value.role.trim(),
    note: newPerson.value.note.trim(),
    canCreate: newPersonPermissions.value.includes('编制') ? '√' : '',
    canApprove: newPersonPermissions.value.includes('批准') ? '√' : '',
    canPost: newPersonPermissions.value.includes('过账') ? '√' : '',
  })
  addPersonDialogVisible.value = false
  ElMessage.success(`已添加人员「${newPerson.value.name}」`)
}

/** AI 解析人员信息文本 */
function aiParsePerson() {
  const text = aiPersonInput.value.trim()
  if (!text) {
    ElMessage.warning('请先输入或粘贴人员信息文本')
    return
  }
  // 简单规则解析（无需后端 AI 即可覆盖常见格式）
  // 格式：编号 姓名 职位 职责 权限关键词
  const parts = text.split(/[\s,，;；|]+/).filter(Boolean)

  // 尝试提取编号（FN开头或纯数字编码）
  const codeMatch = parts.find(p => /^[A-Z]{1,4}\d{2,}$/i.test(p) || /^\d{3,}$/.test(p))
  if (codeMatch) newPerson.value.code = codeMatch

  // 尝试提取中文姓名（2-4个汉字）
  const nameMatch = parts.find(p => /^[\u4e00-\u9fa5]{2,4}$/.test(p))
  if (nameMatch) newPerson.value.name = nameMatch

  // 权限关键词
  const permissions: string[] = []
  if (/编制|创建|录入/.test(text)) permissions.push('编制')
  if (/批准|审批|复核/.test(text)) permissions.push('批准')
  if (/过账|记账|过帐/.test(text)) permissions.push('过账')
  if (permissions.length) newPersonPermissions.value = permissions

  // 职位关键词
  const roleMatch = text.match(/(会计[^\s,，]*|经理|主管|总监|助理[^\s,，]*|出纳|财务[^\s,，]*)/)
  if (roleMatch) newPerson.value.role = roleMatch[0]

  // 剩余文本作为职责
  const usedParts = [codeMatch, nameMatch, roleMatch?.[0]].filter(Boolean)
  const remaining = parts.filter(p => !usedParts.includes(p) && !/编制|创建|录入|批准|审批|复核|过账|记账|过帐/.test(p))
  if (remaining.length > 0 && remaining.join('').length > 4) {
    newPerson.value.note = remaining.join(' ')
  }

  ElMessage.success('已解析填入，请核对后确认')
}
</script>

<style scoped>
.c23-personnel-sheet {
  font-size: var(--wp-font-size, 13px);
}

/* 编制提示 */
.c23-edit-hint {
  margin-bottom: 14px;
  border: 1px solid #c7d2fe;
  border-radius: 8px;
  background: #eef2ff;
  overflow: hidden;
}
.c23-edit-hint-summary {
  padding: 8px 12px;
  font-weight: 600;
  font-size: var(--wp-font-size, 13px);
  color: #1e40af;
  cursor: pointer;
  background: #dbeafe;
  border-bottom: 1px solid #bfdbfe;
}
.c23-edit-hint-body {
  padding: 10px 14px;
  font-size: 12px;
  color: #1e3a5f;
  line-height: 1.7;
}
.c23-edit-hint-body p { margin: 4px 0; }
.c23-edit-hint-example {
  margin-top: 8px;
  padding-top: 6px;
  border-top: 1px dashed #93c5fd;
  color: #1d4ed8;
  font-style: italic;
}

.methodology-context {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 10px 12px;
  margin-bottom: 16px;
  background: #fffbf0;
  border-radius: 4px;
}
.methodology-bar {
  width: 3px;
  min-height: 20px;
  align-self: stretch;
  background: #e6a23c;
  border-radius: 2px;
  flex-shrink: 0;
}
.methodology-context p {
  margin: 0;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.c23-section { margin-bottom: 20px; }
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.section-title {
  font-weight: 600;
  font-size: 14px;
  color: #303133;
}
.c23-table { font-size: var(--wp-font-size, 13px); }
.c23-table :deep(.el-table__header th) { font-size: var(--wp-font-size, 13px); background: #f5f7fa; }
.c23-table :deep(.el-table__body td) { font-size: var(--wp-font-size, 13px); }

/* 新增人员 Dialog */
.c23-add-person-hint {
  padding: 10px 12px;
  margin-bottom: 14px;
  background: #f0f9ff;
  border-left: 3px solid #3b82f6;
  border-radius: 0 6px 6px 0;
  font-size: 12px;
  color: #1e40af;
  line-height: 1.5;
}
.c23-add-person-form {
  padding: 0 4px;
}
.c23-add-person-ai {
  margin-top: 16px;
  padding: 12px;
  background: #fefce8;
  border: 1px solid #fde68a;
  border-radius: 8px;
}
</style>
