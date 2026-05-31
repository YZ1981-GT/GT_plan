# note_template DB 化 ROI 评估

> 评估日期：2026-06  
> 关联需求：global-modules-p2-polish 需求 6.1, 6.4  
> 结论：**暂缓（Deferred）**

## 背景

设计方案提议将 `note_template_soe.json`（540KB）和 `note_template_listed.json`（919KB）按章节拆分存入 DB（复用 `section_id` 主键），`_load_templates` 改读 DB（JSON 作种子导入 + 降级）。

## 评估维度

### 改动面（高）

直接引用模板 JSON 的文件：

| 文件 | 用途 |
|------|------|
| `disclosure_engine.py` | `_load_templates` 核心加载 |
| `note_template_service.py` | `get_soe_template` / `get_listed_template` |
| `note_template_diff.py` | SOE↔Listed 转换差异计算 |
| `note_trim_service.py` | 模板裁剪 |
| `note_template_bindings_loader.py` | cell-binding 元数据 |
| `template_library_mgmt.py` | 模板库管理 record_count |
| 3+ migration/gen 脚本 | 种子生成、section_id 迁移 |
| 6+ 测试文件 | monkeypatch 模板路径 |

需新增：
- `note_template_sections` 表 + ORM 模型 + V042 迁移
- JSON → DB 种子导入脚本（~200+ sections × 2 模板）
- 所有上述文件的读取逻辑改写
- 测试全面更新

预估工作量：**2-3 人天**（含测试回归）

### 实际收益（低）

1. **并发冲突问题不存在**：JSON 模板是**只读基线数据**，仅开发者版本升级时修改。用户的项目级自定义已通过 `NoteCustomTemplateService`（per-project DB 存储 + merge_templates 合并）解决。
2. **多 worker 共享**：JSON 文件本身就是共享的（文件系统），不存在 worker 间不一致。
3. **section_id 已在 DisclosureNote 表**：项目实例数据已按章节粒度存 DB，模板只是初始化种子。

### 与 §五 registry↔JSON 边界的关系

spec F（global-modules-cleanup）已实现 `sync_registry_from_json` 联动机制——JSON 作权威源，registry 表作派生缓存。note_template 的场景类似：JSON 是权威基线，项目实例是派生。DB 化模板本身不改变这个单向关系，只是把"读 JSON"换成"读 DB"，增加了维护复杂度但不改变数据流方向。

## 结论

**暂缓实施**。原因：
- 高改动面（8+ 文件 + 新表 + 迁移 + 种子 + 测试）
- 低实际收益（并发问题已由 custom template overlay 解决）
- 风险：大量测试依赖 JSON 文件路径 monkeypatch，迁移期间回归风险高

### 未来触发条件

如果出现以下情况，可重新评估：
1. 需要支持**运行时在线编辑基线模板**（非开发者修改 JSON）
2. 模板文件增长到影响启动性能（当前 ~1.5MB 总计，加载 <100ms，不是瓶颈）
3. 需要模板版本管理 / 多租户隔离基线模板
