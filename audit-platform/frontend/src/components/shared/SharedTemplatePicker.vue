<template>
  <!-- 保存为模板 + 从模板引用 按钮组 -->
  <div class="gt-stp-btns">
    <el-button size="small" @click="showSaveDialog = true" title="将当前配置保存为共享模板，供其他项目引用">
      💾 保存为模板
    </el-button>
    <el-button size="small" @click="loadTemplates" title="从已有模板中引用配置到当前项目">
      📥 引用模板
    </el-button>
  </div>

  <!-- 保存为模板弹窗 -->
  <el-dialog v-model="showSaveDialog" title="保存为共享模板" width="480px" append-to-body destroy-on-close>
    <el-form label-width="80px" size="small">
      <el-form-item label="模板名称">
        <el-input v-model="saveName" placeholder="如：XX集团公式配置" />
      </el-form-item>
      <el-form-item label="说明">
        <el-input v-model="saveDesc" type="textarea" :rows="2" placeholder="可选，描述模板用途" />
      </el-form-item>
      <el-form-item label="共享范围">
        <el-radio-group v-model="saveOwnerType">
          <el-radio value="personal">👤 仅自己（我参与的项目可引用）</el-radio>
          <el-radio value="group">🏗️ 集团级（同集团子企业可引用）</el-radio>
          <el-radio value="system" disabled>🏢 事务所级（需管理员）</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item v-if="saveOwnerType === 'group'" label="所属集团">
        <span style="font-size: 12px; color: #666;">{{ projectName || '当前项目' }}</span>
      </el-form-item>
      <el-form-item label="公开">
        <el-switch v-model="savePublic" />
        <span style="font-size: 11px; color: #999; margin-left: 8px;">公开后所有人可见</span>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="showSaveDialog = false">取消</el-button>
      <el-button type="primary" @click="onSave" :loading="saving">保存</el-button>
    </template>
  </el-dialog>

  <!-- 引用模板弹窗 -->
  <el-dialog v-model="showPickDialog" title="引用共享模板" width="700px" append-to-body destroy-on-close>
    <div v-if="loadingTemplates" style="text-align: center; padding: 30px;">
      <el-icon class="is-loading" :size="20"><Loading /></el-icon>
      <span style="margin-left: 8px; color: #999;">加载模板列表...</span>
    </div>
    <div v-else-if="templates.length === 0" style="text-align: center; padding: 30px; color: #999;">
      暂无可用模板
    </div>
    <div v-else>
      <el-input v-model="pickSearch" size="small" placeholder="搜索模板名称..." clearable style="margin-bottom: 10px; width: 240px;" />
      <el-table :data="filteredTemplates" size="small" border highlight-current-row max-height="400px"
        @row-click="selectedTemplate = $event"
        :row-class-name="({ row }: any) => selectedTemplate?.id === row.id ? 'gt-stp-selected' : ''">
        <el-table-column label="来源" width="120">
          <template #default="{ row }">
            <span style="font-size: 11px;">{{ getOwnerLabel(row.owner_type) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="模板名称" min-width="180" />
        <el-table-column prop="description" label="说明" min-width="160" show-overflow-tooltip />
        <el-table-column label="版本" width="60" align="center">
          <template #default="{ row }">v{{ row.config_version }}</template>
        </el-table-column>
        <el-table-column label="引用次数" width="80" align="center">
          <template #default="{ row }">{{ row.reference_count }}</template>
        </el-table-column>
        <el-table-column prop="owner_project_name" label="来源项目" width="120" show-overflow-tooltip />
      </el-table>
    </div>
    <template #footer>
      <el-button @click="showPickDialog = false">取消</el-button>
      <el-button type="primary" :disabled="!selectedTemplate" @click="onApply" :loading="applying">
        引用到当前项目
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { handleApiError } from '@/utils/errorHandler'
import { Loading } from '@element-plus/icons-vue'
import {
  listSharedTemplates, saveAsTemplate, applyTemplate, getTemplateDetail,
  type SharedConfigTemplate, getOwnerTypeLabel,
} from '@/services/sharedConfigApi'
import { eventBus } from '@/utils/eventBus'

const props = defineProps<{
  configType: string          // report_mapping / account_mapping / formula_config / report_template / workpaper_template
  projectId?: string
  projectName?: string
  getConfigData: () => Record<string, any>  // 获取当前配置数据的函数
}>()

const emit = defineEmits<{
  'applied': [data: Record<string, any>]  // 引用模板后返回配置数据
}>()

// ── 保存为模板 ──
const showSaveDialog = ref(false)
const saveName = ref('')
const saveDesc = ref('')
const saveOwnerType = ref('personal')
const savePublic = ref(false)
const saving = ref(false)

async function onSave() {
  if (!saveName.value.trim()) {
    ElMessage.warning('请输入模板名称')
    return
  }
  saving.value = true
  try {
    const configData = props.getConfigData()
    await saveAsTemplate({
      name: saveName.value.trim(),
      config_type: props.configType,
      config_data: configData,
      owner_type: saveOwnerType.value,
      owner_project_id: saveOwnerType.value === 'group' ? props.projectId : undefined,
      description: saveDesc.value,
      is_public: savePublic.value,
    })
    ElMessage.success('模板已保存')
    showSaveDialog.value = false
  } catch (e: any) {
    handleApiError(e, '保存失败')
  } finally {
    saving.value = false
  }
}

// ── 引用模板 ──
const showPickDialog = ref(false)
const templates = ref<SharedConfigTemplate[]>([])
const loadingTemplates = ref(false)
const pickSearch = ref('')
const selectedTemplate = ref<SharedConfigTemplate | null>(null)
const applying = ref(false)

async function loadTemplates() {
  showPickDialog.value = true
  loadingTemplates.value = true
  selectedTemplate.value = null
  pickSearch.value = ''
  try {
    templates.value = await listSharedTemplates(props.configType, props.projectId)
  } catch {
    templates.value = []
  } finally {
    loadingTemplates.value = false
  }
}

const filteredTemplates = computed(() => {
  const kw = pickSearch.value.toLowerCase()
  if (!kw) return templates.value
  return templates.value.filter(t =>
    t.name.toLowerCase().includes(kw) || (t.description || '').toLowerCase().includes(kw)
  )
})

function getOwnerLabel(type: string) {
  return getOwnerTypeLabel(type)
}

async function onApply() {
  if (!selectedTemplate.value || !props.projectId) return
  applying.value = true
  try {
    // 先获取完整配置数据
    const detail = await getTemplateDetail(selectedTemplate.value.id)
    // 记录引用
    await applyTemplate(selectedTemplate.value.id, props.projectId)
    ElMessage.success(`已引用模板「${selectedTemplate.value.name}」`)
    emit('applied', detail.config_data || {})
    // 通知地址注册表刷新（新增表样可能改变可引用地址）
    eventBus.emit('template-applied', {
      configType: props.configType,
      projectId: props.projectId,
    })
    showPickDialog.value = false
  } catch (e: any) {
    handleApiError(e, '引用失败')
  } finally {
    applying.value = false
  }
}
</script>

<style scoped>
.gt-stp-btns {
  display: inline-flex;
  gap: 6px;
}
:deep(.gt-stp-selected) {
  background-color: #f0ecf5 !important;
}
</style>
