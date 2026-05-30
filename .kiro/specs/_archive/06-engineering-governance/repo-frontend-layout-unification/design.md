---
spec: repo-frontend-layout-unification
status: draft
version: v0.1
created: 2026-05-29
---

# 设计文档：仓库前端路径二义性消除（方案 A）

## 一、目标架构

```
执行前：
GT_workplan/
├── frontend/                            ← 删除
│   └── src/components/
│       ├── custom-query/  (2 .vue)      ← 5 文件迁移或删除
│       └── eqcr/          (3 .vue)
└── audit-platform/
    └── frontend/                        ← 唯一真前端

执行后：
GT_workplan/
└── audit-platform/
    └── frontend/                        ← 唯一前端（5 空壳已清）
```

## 二、5 空壳组件处理

通过 grep 引用判断 4 类处理：

| 文件 | 处理 | 判断依据 |
|------|------|---------|
| `frontend/src/components/custom-query/X.vue` | 看引用 | grep `from.*custom-query` 全仓 |
| `frontend/src/components/eqcr/Y.vue` | 看引用 | grep `from.*eqcr` 全仓 |

**3 类处理路径**：

1. **A 真有引用 + 真前端没对应文件** → `git mv` 迁移到 `audit-platform/frontend/src/components/`
2. **B 有引用但真前端已有同名（更新版）** → 删空壳 + 检查引用方是否需要更新 import 路径
3. **C 0 引用** → 直接 `git rm`（死代码）

## 三、改动清单

### 3.1 物理操作

```bash
# Step 1: 引用扫描（一次性脚本，用完即删）
python backend/scripts/_verify_orphan_frontend_components.py
# 输出 5 文件的引用情况 + 处理建议

# Step 2: 按建议处理 5 文件（分类执行）
# - A 类：git mv frontend/src/components/X.vue audit-platform/frontend/src/components/X.vue
# - B 类：git rm frontend/src/components/X.vue（确认空壳已被取代）
# - C 类：git rm frontend/src/components/X.vue（无引用死代码）

# Step 3: 删空壳目录
git rm -r frontend/

# Step 4: 验证
.\.venv\Scripts\python.exe backend/scripts/check_file_size.py  # 不破基线
cd audit-platform/frontend && npm run type-check                # vue-tsc
cd audit-platform/frontend && npm run test                      # vitest
```

### 3.2 配置文件检查

grep `frontend/src` 排除 `audit-platform/frontend/src` 后看是否还有遗留引用：

```bash
grep -r "frontend/src" --include="*.json" --include="*.ts" --include="*.js" --include="*.yaml" --include="*.yml" \
  | grep -v "audit-platform/frontend/src"
```

预期：0 命中（除文档历史档案）

### 3.3 memory.md 同步

删除旧铁律：
```
- 判断前端模块存在性必须同时检查 `views/` 根目录 + `components/` 子目录
```

加入新铁律（操作铁律区）：
```
- 前端唯一路径铁律（2026-05-29 落地）：仓库前端路径 = `audit-platform/frontend/`，
  仓库根无 `frontend/` 目录；任何文档 / IDE / grep / CI 不再引用 `frontend/src/`
```

## 四、防回归 hook

`.pre-commit-config.yaml` 加：

```yaml
- id: check-no-root-frontend
  name: check-no-root-frontend
  entry: python backend/scripts/check_no_root_frontend.py
  language: system
  pass_filenames: false
```

`check_no_root_frontend.py`（约 30 行）：
- 检查仓库根目录 `frontend/` 不存在
- 检查 staged 文件中无 `^frontend/src/` 路径

## 五、ADR

- ADR-026：repo frontend layout 选型（方案 A vs 方案 B），选 A 理由 = ROI 高 + 风险低

## 六、回滚

git tag `pre-frontend-cleanup-2026-05-29` 在执行前打。需要时 `git checkout <tag>` 恢复。

## 七、版本

- v0.1（2026-05-29）：初版
