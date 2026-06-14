<!--
  BusinessCategorySelect — 业务分类选择器

  下拉选择 A1~A8 / B1~B6 / C + "查看分类标准"弹窗。
  Requirements: 2.1, 2.5
-->
<template>
  <div class="business-category-select">
    <el-select
      :model-value="modelValue"
      placeholder="选择业务分类"
      @update:model-value="$emit('update:modelValue', $event)"
    >
      <el-option-group label="A类（重大公众利益实体）">
        <el-option value="A1" label="A1 上市公司" />
        <el-option value="A2" label="A2 IPO首次申报" />
        <el-option value="A3" label="A3 重大资产重组" />
        <el-option value="A4" label="A4 再融资" />
        <el-option value="A5" label="A5 央企/大型国企" />
        <el-option value="A6" label="A6 金融机构" />
        <el-option value="A7" label="A7 境外上市" />
        <el-option value="A8" label="A8 其他重大公众利益实体" />
      </el-option-group>
      <el-option-group label="B类（其他公众利益实体）">
        <el-option value="B1" label="B1 新三板/北交所" />
        <el-option value="B2" label="B2 债券发行" />
        <el-option value="B3" label="B3 特定行业" />
        <el-option value="B4" label="B4 大型民营企业" />
        <el-option value="B5" label="B5 事业单位/政府审计" />
        <el-option value="B6" label="B6 境外审计协作" />
      </el-option-group>
      <el-option-group label="C类（一般审计）">
        <el-option value="C" label="C 一般审计业务" />
      </el-option-group>
    </el-select>

    <el-button link type="primary" @click="showReference = true">
      查看分类标准
    </el-button>

    <!-- 分类标准参考弹窗 -->
    <el-dialog
      v-model="showReference"
      title="业务分类标准"
      width="640px"
      :close-on-click-modal="true"
    >
      <div v-if="referenceData" class="category-reference">
        <div v-for="(cat, key) in referenceData.categories" :key="key" class="category-reference__group">
          <h4>{{ cat.name }}</h4>
          <p class="category-reference__measures">质控措施：{{ cat.quality_measures }}</p>
          <ul v-if="cat.subcategories?.length">
            <li v-for="sub in cat.subcategories" :key="sub.code">
              <strong>{{ sub.code }}</strong> {{ sub.name }} — {{ sub.description }}
            </li>
          </ul>
          <p v-else class="category-reference__default">默认分类，无子分类</p>
        </div>
      </div>
      <div v-else class="category-reference__loading">加载中...</div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/services/apiProxy'

defineProps<{
  modelValue: string
}>()

defineEmits<{
  'update:modelValue': [value: string]
}>()

const showReference = ref(false)
const referenceData = ref<any>(null)

onMounted(async () => {
  try {
    referenceData.value = await api.get('/api/workpapers/template-list/reference')
  } catch {
    // 降级：无参考数据时弹窗显示空
  }
})
</script>

<style scoped>
.business-category-select {
  display: flex;
  align-items: center;
  gap: 8px;
}

.category-reference__group {
  margin-bottom: 16px;
}

.category-reference__group h4 {
  color: var(--gt-color-primary, #4b2d77);
  margin-bottom: 4px;
}

.category-reference__measures {
  font-size: 12px;
  color: #909399;
  margin-bottom: 6px;
}

.category-reference__default {
  font-size: 13px;
  color: #606266;
}

.category-reference__loading {
  text-align: center;
  padding: 20px;
  color: #909399;
}
</style>
