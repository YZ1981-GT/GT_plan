<template>
  <div class="gt-format-mgr gt-fade-in">
    <div class="gt-page-header">
      <h2 class="gt-page-title">报告排版模板</h2>
      <el-button type="primary" @click="showCreate = true">新建模板</el-button>
    </div>
    <el-table :data="templates" stripe>
      <el-table-column prop="template_name" label="模板名称" />
      <el-table-column prop="template_type" label="类型" width="120" />
      <el-table-column prop="version" label="版本" width="80" align="center" />
      <el-table-column label="默认" width="80" align="center">
        <template #default="{ row }"><el-tag v-if="row.is_default" type="success" size="small">默认</el-tag></template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间">
        <template #default="{ row }">{{ row.created_at?.slice(0, 16) }}</template>
      </el-table-column>
    </el-table>
    <el-dialog v-model="showCreate" title="新建排版模板" width="500px">
      <el-form label-width="80px">
        <el-form-item label="名称"><el-input v-model="form.template_name" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.template_type">
            <el-option label="审计报告" value="audit_report" />
            <el-option label="管理建议书" value="management_letter" />
            <el-option label="函证" value="confirmation" />
          </el-select>
        </el-form-item>
        <el-form-item label="字体"><el-input v-model="form.config.font" placeholder="仿宋_GB2312" /></el-form-item>
        <el-form-item label="字号"><el-input-number v-model="form.config.font_size" :min="8" :max="24" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="onCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { listFormatTemplates, createFormatTemplate } from '@/services/phase10Api'
const templates = ref<any[]>([])
const showCreate = ref(false)
const form = ref({ template_name: '', template_type: 'audit_report', config: { font: '仿宋_GB2312', font_size: 12 } })
async function fetch() { templates.value = await listFormatTemplates() }
async function onCreate() {
  if (!form.value.template_name) return ElMessage.warning('请输入名称')
  await createFormatTemplate(form.value)
  showCreate.value = false
  ElMessage.success('模板已创建')
  await fetch()
}
onMounted(fetch)
</script>
<style scoped>
.gt-format-mgr { padding: var(--gt-space-4); }
.gt-page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-3); }
</style>
