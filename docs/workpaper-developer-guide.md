# 底稿组件开发指南

**最后更新**：2026-07-14
**适用范围**：所有经 `GtWpRenderer` 渲染的专属底稿组件

---

## 一、Runtime Boundary 模式（必须遵循）

### 1.1 新组件接入

新建专属底稿组件**不再需要**手工 provide 版本链、复核、AI、displayPrefs 等横切能力。这些由 `GtWpRenderer` 统一提供。

```ts
// ✅ 正确：从 Runtime Boundary inject
import { inject } from 'vue'
import { WorkpaperRuntimeContextKey } from '@/components/workpaper/composables/useWorkpaperScaffold'

const runtime = inject(WorkpaperRuntimeContextKey, null)

// 子组件需要的能力通过 provide 转发
provide('scheduleAutoSnapshot', () => runtime?.version.scheduleAutoSnapshot())
provide('openReviewDialog', (opts) => runtime?.review.openReviewDialog(opts))
```

```ts
// ❌ 错误：不要在主入口本地 new 版本/复核 provider
import { useWorkpaperVersionToolbar } from '../composables/useWorkpaperVersionToolbar'
import { useWorkpaperReviewProvide } from '../composables/useWorkpaperReviewProvide'
const version = useWorkpaperVersionToolbar(wpId) // 重复！Runtime Boundary 已提供
```

### 1.2 Persistence Adapter（持久化）

所有新建 checklist 数据保存**必须使用工厂或适配器**：

```ts
// ✅ 使用工厂
import { createChecklistFormData } from '../composables/factories/createChecklistFormData'

const formData = createChecklistFormData({
  itemPrefix: 'G10-',
  label: 'G10',
  forceComponentType: 'g10-trading-financial-liabilities',
  normalizeResponse,
  afterSave,
})
```

```ts
// ❌ 禁止新建自建网络实现
const save = async () => {
  await api.put(`/api/workpapers/${wpId}/checklist-responses`, { items })
}
```

CI guard `check_homogeneous_formdata.py --strict` 会阻断新建同构 FormData。

---

## 二、注册四件套（每个新 componentType 必做）

1. **`VALID_COMPONENT_TYPES`**（`wp_classification_service.py`）
2. **`htmlRendererRegistry`**（前端 componentType→Vue 组件映射）
3. **`RENDERER_DISPATCH`**（后端 componentType→render 策略函数）
4. **`account_package_registry.json`**（sheet 清单+顺序=目录行顺序）

---

## 三、Coverage Ledger 维护

新组件必须在 `coverage-ledger.json` 中登记 8 项能力状态：

| 能力 | 说明 | 常见状态 |
|------|------|---------|
| displayPrefs | 全局显示偏好 | covered（Runtime Boundary） |
| agingConfig | 账龄段配置 | covered（Runtime Boundary） |
| version | 版本链 | covered（Runtime Boundary） |
| review | 复核对话 | covered（Runtime Boundary） |
| ai | AI 辅助 | covered（Runtime Boundary） |
| persistence | 持久化 | covered / exempt |
| acnr | 地址坐标 | covered / unknown |
| importExport | 导入导出 | covered / exempt |

**豁免规则**：
- 必须按单能力登记，不允许 entry 级 blanket exemption
- 每个豁免需注明 `reason/capability/approvedBy/approvedAt/reviewAt`

---

## 四、CI 守卫清单

| 守卫 | 文件 | 触发条件 |
|------|------|---------|
| Coverage Ledger | `check_coverage_ledger.py` | 明确缺失=阻断，不确定=放行 |
| API Prefix | `check_api_prefix_guard.py` | 缺 `/api` 的后端调用=阻断 |
| Import Contract | `check_import_contract.py` | default-only 模块 named import=阻断 |
| Persistence Contract | `check_homogeneous_formdata.py` | 新建同构 FormData=阻断 |
| Ref Contract | `check_wp_ref_contract.py` | props 声明 Ref<> 类型=阻断 |
| Import Depth | `fix_wp_composables_import_depth.py --check` | 相对路径层级错误=阻断 |
| Version Trail | `check_wp_version_trail.py` | 主入口未接入版本链=阻断 |
| Vite Transform | CI job | 编译失败=阻断 |
| Runtime Import | CI job | 动态 import 失败=阻断 |

---

## 五、组件 props 契约

```ts
// ✅ 正确：props 声明解包类型
defineProps<{
  wpId: string              // 不是 Ref<string>
  projectId: string
  allResponses: Map<string, any>  // 不是 Ref<Map>
}>()

// 需要传给 composable 时重新包装
const wpIdRef = toRef(props, 'wpId') as Ref<string>
```

---

## 六、自检清单

新底稿组件提交前确认：
- [ ] 从 Runtime Boundary inject，不本地 provide 版本/复核/AI
- [ ] 使用工厂或适配器保存 checklist 数据
- [ ] Coverage Ledger 已登记 8 项能力
- [ ] Props 使用解包类型（非 Ref<>）
- [ ] 相对 import 层级正确
- [ ] `get_diagnostics` 无错误
- [ ] Vite transform 200
