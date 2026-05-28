# ADR-020: 章节序号 5 级层级格式注册器

## 状态
已实施（Sprint A.0，2026-05-28）

## 背景
致同标准附注使用 5 级编号体系：一、/（一）/1./(1)/①。需要一个可扩展的格式注册器支持：
- 按 level 自动选择格式
- partner 可定制格式（v2）
- 中文数字 1~99 转换

## 决策
`LEVEL_FORMATS` 字典注册 5 个 lambda，每个接受 1-based 序号返回格式化字符串：

```python
LEVEL_FORMATS = {
    1: lambda i: f"{cn_number(i)}、",     # 一、二、三、
    2: lambda i: f"（{cn_number(i)}）",    # （一）（二）
    3: lambda i: f"{i}.",                  # 1. 2. 3.
    4: lambda i: f"({i})",                 # (1) (2)
    5: circled_number,                     # ① ② ③ (1~20)
}
```

### 工具函数
- `cn_number(i)`: 1~99 阿拉伯→中文数字，超界回退原数字串
- `circled_number(i)`: 1~20 带圈数字，超界回退 `(N)` 格式
- `render_section_number(level, sort_index)`: 单层级渲染入口

## 影响
- 位于 `note_section_numbering_service.py` 顶部
- 25 单测覆盖全部 5 级 + 边界情况
- CI-19 卡点确保渲染后序号在 scope 内唯一

## 扩展性
v2 可加 `custom_format` 字段让 partner 自定义格式字符串（如 `"{i})"` 或 `"第{cn}章"`）。
