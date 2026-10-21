# 后端披露表 payload builder — 设计文档

## §1 架构

```
checklist_responses (DB)
    │ 按 wp_id + item_id 查询
    ▼
DisclosurePayloadBuilder.build(wp_code, project_id, year)
    │ 分类/聚合/格式化（与前端 buildXSyncPayload 同逻辑）
    ▼
sub_table_data: dict[str, list[dict]]
    │
    ▼
sync_from_workpaper() → disclosure_notes.table_data
```

## §2 builder 接口

```python
@dataclass
class PayloadBuildResult:
    wp_code: str
    section_id: str              # 目标附注章节号
    sub_table_data: dict[str, list[dict]]
    sub_table_columns: dict[str, list[dict]] | None
    sheet_name: str              # 披露表 sheet 名
    current_standard: str        # soe / listed

class DisclosurePayloadBuilder(ABC):
    wp_code: str

    @abstractmethod
    async def build(
        self, db: AsyncSession, project_id: UUID, year: int,
    ) -> PayloadBuildResult | None:
        """构建 sub_table_data。None = 底稿无数据（checklist_responses 为空）。"""
```

## §3 每个 builder 的翻译策略

以 D2（应收账款）为例：

**前端**（`d2NoteSectionMap.ts`，~800 行）：
```typescript
export function buildD2SyncPayload(variant, wpId, applicableStandards, snapshot) {
  // ① 账龄行 → twoPeriodRow
  // ② 坏账分类宽表 → classWide (期末/期初各一张)
  // ③ 单项计提明细 → individuals
  // ④ 组合计提 → portfolios (每组一张子表)
  // ⑤ 坏账准备变动 → movement
  // ⑥ 转回/收回 → reversals
  // ⑦ 核销 → writeOffs
  // ⑧ 前五名 → top5
}
```

**后端翻译**（`builders/d2_builder.py`）：
```python
class D2Builder(DisclosurePayloadBuilder):
    wp_code = "D2"

    async def build(self, db, project_id, year):
        # 从 checklist_responses 读 D2 底稿数据
        entries = await self._load_entries(db, project_id)
        if not entries:
            return None
        # ① 解析 aging rows
        aging = self._parse_aging(entries)
        # ② 解析 class wide
        class_end, class_prior = self._parse_class_wide(entries)
        # ... 与前端同逻辑
        return PayloadBuildResult(...)
```

## §4 checklist_responses 数据读取

```python
async def load_disclosure_entries(
    db: AsyncSession, project_id: UUID, wp_code: str,
) -> dict[str, Any]:
    """读取底稿 wp_code 的全部 checklist_responses，按 item_id 索引。"""
    # wp_index → working_paper → checklist_responses
    # 返回 {item_id: {remark, conclusion, value, ...}}
```

## §5 分批计划

| 批次 | 科目数 | 复杂度 | 交付件 |
|------|--------|--------|--------|
| 第一批 | 8 | 高（E1/D1/D2/F2 有复杂分类） | 8 builder + 一致性测试 |
| 第二批 | 15 | 中（D3~D7/F/H/I 标准两字段） | 15 builder + 一致性测试 |
| 第三批 | 46 | 低（G/J/K/L/M/N 简单行） | 46 builder + 一致性测试 |

## §6 风险

- 前端 payload builder 的逻辑分散在 69 个 TypeScript 文件中，翻译到 Python 容易遗漏细节
- checklist_responses 的 item_id 命名规律因循环而异，需逐科目确认
- 前端有些 builder 依赖 Vue 响应式状态（如 `snapshot` 对象），后端需要从 raw 数据重建

## §7 现状勘误（实施阶段发现）

### §7.1 `load_disclosure_entries` SQL bug

`disclosure_payload_builder_service.py` 第 75 行：
```sql
AND cr.is_deleted = false
```
`checklist_responses` 表（V085~V161）**没有 `is_deleted` 列**。PG 上执行必抛 `UndefinedColumn`。
该函数从未被真实调用（`_BUILDER_REGISTRY` 为空 → `build_for_wp_code` 总返回 None），bug 未暴露。

**修复**：删除该条件（checklist_responses 不支持软删除，无需过滤）。

### §7.2 Phase 1 基础设施已就绪

`disclosure_payload_builder_service.py` 已实现：
- `PayloadBuildResult` 数据类
- `DisclosurePayloadBuilder` ABC + `register_builder` 装饰器
- `_BUILDER_REGISTRY`（空 dict）+ `get_builder` / `registered_wp_codes`
- `load_disclosure_entries` / `load_project_template_type` / `load_project_standard`
- `build_for_wp_code` / `build_and_sync`（→ `sync_from_workpaper`）

已被 `note_disclosure_refresh_service.py` 引用（第 314 行 `from ... import build_and_sync, get_builder`）。

### §7.3 `disclosure_source.py` 取数路径

`load_disclosure_sub_table_data()` 从 `disclosure_notes.table_data.sub_table_data` 读（前端已同步过的数据），**不从 `checklist_responses` 读**。后端 builder 的价值正是在前端未同步时能从 `checklist_responses` 直接构建。

### §7.4 `checklist_responses` 表结构

| 列 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | gen_random_uuid() |
| project_id | UUID FK | → projects |
| wp_id | UUID FK | → working_paper |
| item_id | VARCHAR(64) | 核对条目 ID（V089 扩宽） |
| conclusion | TEXT | 结论（V098 扩宽） |
| remark | TEXT | 备注（大部分底稿的数据列） |
| wp_ref | VARCHAR(100) | 底稿索引引用 |
| updated_by | UUID | → users |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |
| content_version | INTEGER | V161 加 |
| **⚠️ 无 is_deleted** | — | 不支持软删除 |
