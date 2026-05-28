# ADR-019: 附注章节编号体系重构（section_number → section_id + level + parent + sort_index）

## 状态
已实施（Sprint A.0，2026-05-28）

## 背景
致同附注模板 173 章节的 `section_number` 字段是手工编写的字符串（如 "四、记账本位币" / "八、22"），存在：
- 裁剪后断号无法自动重排
- 单体↔合并切换时序号全部失效
- 无法支持拖拽排序
- 内部引用（"见五、（一）2."）无法自动跟随

## 决策
用 `section_id`（稳定 ID）+ `level`（1-5 层级）+ `parent_section_id`（树形父引用）+ `sort_index`（同层排序）替代写死的 `section_number` 字符串。

### 关键设计选择
1. `section_id` 为 VARCHAR(100) 拼音 slug（如 `chapter-08-...-huo-bi-zi-jin`），跨年保持不变
2. `parent_section_id` 不做 FK（跨项目/年度场景复杂），用 CI-18 卡点校验代替
3. 保留旧 `note_section` 字段作为 legacy compat（v2 再废弃）
4. 合成 chapter 节点（level=1）仅存在于模板 JSON，DB 中 173 章节全为 level=2

## 影响
- V019 migration 加 7 列 + 2 索引 + 1 CHECK
- 模板 JSON 注入 D13 字段（14 合成 chapter SOE / 17 Listed）
- 一次性 backfill 脚本填充 DB 现有行
- NoteSectionNumberingService 新建（render_all / render_sections）

## 替代方案
- 方案 B：在 `section_number` 字段上做正则解析 → 脆弱，无法支持拖拽/锁定
- 方案 C：用 sort_order 整数编码层级 → 无法表达树形结构
