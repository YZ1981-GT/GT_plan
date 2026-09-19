# wp_render_schema — 底稿渲染 Schema 定义

## 定位

本目录下的 `.yaml` 文件是 **d-form-table 类型底稿的结构定义文档**，用途：

1. **设计文档**：记录每个 d-form-table 底稿的字段结构、公式、联动关系
2. **前端渲染参考**：前端 GtDFormTable 组件可按 schema 动态生成表格列
3. **导入映射**：从 Excel 导入时按 schema 字段名做列映射
4. **测试契约**：单元测试验证 schema 字段完整性

## 当前状态

- **后端 `get_render_config` 尚未读取这些 YAML**——前端 d-form-table 的实际数据来自 `working_papers.parsed_data`
- 后续计划：在 `get_render_config` 中增加 schema loader，按 wp_code 查找对应 YAML 返回给前端

## 命名规则

- `{wp_code}.yaml` — 每个需要特殊 schema 的底稿一个文件
- 通用结构的底稿（同一循环内字段相同的审定表）可不建 YAML，走通用渲染

## 文件清单

按循环分布：
- D~N 循环审定表：`D1-1.yaml`, `E1-1.yaml`, `F1-1.yaml` ... `N5-1.yaml`
- 特殊 d-form-table：`K5-3.yaml`(或有事项), `K6-3.yaml`(CAS42), `L3-4.yaml`(重分类), `M9-3.yaml`(OCI) 等
- J 循环精算：`J2-3.yaml`(精算假设评估)
