# ADR-014: 附注文字段落 Jinja 模板引擎

**状态**: 已采纳 (Accepted)
**日期**: 2026-05-28
**Sprint**: A.4

## 背景

会计政策段落原写死为字符串（如「本公司是经登记成立的有限责任公司」），无法按企业类型/规模/上市状态动态适配。

## 决策

引入 Jinja2 模板引擎：

```jinja
本公司是经{{ registration_authority }}核准，
{% if is_listed %}于{{ list_date | date_cn }}在{{ list_exchange }}上市，{% endif %}
注册资本{{ registered_capital | format_amount }}元。
```

变量来源（优先级链路）：
- project < wizard < consol < prior < year < section_db < section_param

3 个核心 service 文件：
1. `note_text_template_engine.py`: Jinja env + 3 filters（format_amount/cn_number/date_cn）+ ref() 函数
2. `note_text_paragraph_vars.py`: 变量收集合并（async）
3. `note_paragraph_renderer.py`: 三级降级（text_template → text_content → text_sections）

技术细节：
- 默认 `StrictUndefined` 严格模式
- `strict=False` 切到 `ChainableUndefined`，未定义变量渲染为空字符串
- 所有 filter 永不抛错（None→""，非数字字符串原样返回）
- DB 操作全部 try/except + rollback，不阻塞渲染

## 备选方案

- ❌ Python f-string：可注入风险
- ❌ 自研 DSL：维护成本

## 后果

正面：
- 段落动态化（同模板支持 SOE / Listed / 集团 / 单体）
- ref() 自动跟随章节序号变化
- CI-11 校验必有变量声明

负面：
- 新增依赖 Jinja2
- 模板编写需培训

## 相关 CI

- CI-11: Jinja 模板必有变量声明
