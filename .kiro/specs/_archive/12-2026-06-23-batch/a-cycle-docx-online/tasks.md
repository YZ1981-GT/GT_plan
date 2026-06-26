# Implementation Plan: A循环 docx 底稿批量在线�?

## Overview

批量注册 25 �?A 循环 docx 底稿�?word-template + 6 个非 docx 底稿到正�?componentType，并新增模板预填增强、签署状态跟踪、A16 智能模板选择功能。采用配置优�?+ 最小代码增量策略，复用现有 OnlyOffice/field_overrides 基础设施�?

## Tasks

- [x] 1. 配置层：批量注册 wp_code_overrides.json
  - [x] 1.1 新增 25 �?word-template 映射�?6 个非 docx 映射�?wp_code_overrides.json
    - 添加 A8-1, A8-2, A9-1, A9-2, A10-1, A11-1, A12-1, A16-1~A16-7, A17-2-1, A17-3, A17-3-1, A17-4, A17-6, A18-1, A26-1~A26-4, A27-1 �?"word-template"
    - 添加 A30�?checklist-table", A28�?d-form-table", A4-1�?audit-sheet", A7-1�?audit-sheet", A10�?a-program-console", A12�?a-program-console"
    - 确保不修改已�?A16, A17-1, A17-7 条目
    - _Requirements: 1.1, 1.3, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 1.2 验证 backend/wp_templates/A/ 目录�?25 �?.docx 模板文件存在
    - 检查每�?wp_code 对应�?.docx 模板文件是否存在�?backend/wp_templates/A/
    - 缺失的模板文件需要创建占位或从源获取
    - _Requirements: 1.4, 1.5_

  - [x]* 1.3 编写 test_wp_code_overrides.py 验证配置完整�?
    - **Property 1: Override 注册正确�?*
    - 验证 JSON 包含全部 31 条新增映�?
    - 验证保护列表 (A16, A17-1, A17-7) 不变
    - **Validates: Requirements 1.1, 1.3, 2.1-2.6**

- [x] 2. 后端：模板预填服务增�?
  - [x] 2.1 扩展 _prefill_word_template() 占位�?token 集合
    - 新增 token: {{entity_name}}, {{period_end}}, {{preparer}}, {{current_date}}, {{client_name}}, {{audit_period}}, {{partner_name}}
    - period_end/current_date 格式化为 YYYY年MM月DD�?
    - 空值保留逻辑：对应值为 None 时保�?{{token}} 不替�?
    - 替换后记录审计日�?logger.info
    - _Requirements: 3.1, 3.2, 3.3, 3.5, 3.6_

  - [x] 2.2 实现快照幂等逻辑（已有快照不重复预填�?
    - 检�?storage/{project_id}/workpapers/{wp_code}.docx 是否已存�?
    - 存在则直接返回已有快照路径，不执行预�?
    - 原模板文件始终不修改
    - _Requirements: 3.4, 3.5_

  - [x]* 2.3 编写预填占位符替换属性测�?
    - **Property 3: 占位符替换完备�?*
    - 使用 hypothesis st.text() 生成随机 entity_name/preparer + st.dates() 生成 period_end
    - 验证替换后文档不含已替换 token 且包含实际�?
    - **Validates: Requirements 3.1, 3.2**

  - [x]* 2.4 编写空值保留属性测�?
    - **Property 4: 空值占位符保留**
    - 随机选择哪些字段�?None（st.sampled_from + st.none()�?
    - 验证空�?token 保留、非�?token 被替�?
    - **Validates: Requirements 3.3**

  - [x]* 2.5 编写快照幂等性属性测�?
    - **Property 5: 快照幂等�?*
    - 生成随机 docx 内容作为快照 �?验证 prefill 不修�?
    - **Validates: Requirements 3.4, 3.5**

- [x] 3. Checkpoint - 确认配置注册和预填功�?
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. 后端：签署状态跟�?
  - [x] 4.1 通用�?sign_status 端点（去�?A16 硬编码）
    - 修改 wp_editor_router.py �?sign_status 端点，支持所�?word-template wp_code
    - 添加 Pydantic 枚举校验：仅接受 "draft"/"pending"/"signed"
    - scope 格式: word_template:{parent_wp_code}:{wp_code}（A16子版本）�?word_template:{wp_code}（独立底稿）
    - 默认新建底稿 sign_status = "draft"
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 4.2 render-config 注入 sign_status 和只读权�?
    - 修改 working_paper.py render-config 逻辑，查�?field_overrides 获取 sign_status
    - sign_status="signed" 时返�?OnlyOffice permissions.edit=false
    - render-config response 包含 sign_status 字段
    - _Requirements: 4.4, 4.5_

  - [x] 4.3 实现签署状态回退权限控制
    - signed→draft/pending 转换需校验用户角色�?partner 或以�?
    - 低权限角色返�?HTTP 403
    - 记录 user_id + timestamp（利�?field_overrides �?updated_at�?
    - _Requirements: 4.6, 4.7_

  - [x]* 4.4 编写 sign_status 属性测�?
    - **Property 6: sign_status 持久化往�?*
    - st.sampled_from(["draft","pending","signed"]) × 随机 wp_code
    - 验证写入后查询返回相同�?+ user_id/updated_at 非空
    - **Validates: Requirements 4.3, 4.7**

  - [x]* 4.5 编写 sign_status 枚举验证属性测�?
    - **Property 7: sign_status 枚举验证**
    - st.text() 生成非法 status �?�?验证拒绝
    - **Validates: Requirements 4.1**

  - [x]* 4.6 编写签署状态权限控制属性测�?
    - **Property 9: 签署状态回退权限控制**
    - st.sampled_from(roles) × st.sampled_from(transitions)
    - 验证 partner 以下角色 signed→draft/pending �?403 拒绝
    - **Validates: Requirements 4.6**

- [x] 5. 后端：A16 智能模板选择
  - [x] 5.1 创建 template_selector.py 实现推荐逻辑
    - 实现 recommend_a16_version(business_category) 函数
    - 映射规则: IPO→A16-3, 上市/listed→A16-2, 新三板→A16-5, 企业�?债券→A16-6, 默认→A16-1
    - A16-7 始终作为 always_required 返回
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 5.2 创建 GET /api/projects/{project_id}/a16/recommended-version 端点
    - 返回 recommended_code, recommended_label, all_versions (�?exists_in_project), always_required
    - 查询项目�?business_category 字段
    - 查询�?A16-x 变体在项目中是否已创�?
    - _Requirements: 5.4, 5.5, 5.6_

  - [x]* 5.3 编写模板选择确定性属性测�?
    - **Property 10: A16 模板选择确定�?*
    - st.text() 生成随机 business_category �?验证输出在合法集合内且确定�?
    - **Validates: Requirements 5.1, 5.2**

  - [x]* 5.4 编写 A16-7 始终必需属性测�?
    - **Property 11: A16-7 始终必需 + render-config schema 完整**
    - st.text() �?st.none() 作为 business_category �?验证 A16-7 始终存在
    - **Validates: Requirements 5.3, 5.6**

- [x] 6. Checkpoint - 确认后端全部功能
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. 前端：WorkpaperWordEditor 通用�?
  - [x] 7.1 改�?WorkpaperWordEditor.vue 支持通用模式
    - 拆分通用模式（非 A16 底稿）vs A16 专用模式（版本选择面板�?
    - 通用模式: 直接加载 OnlyOffice editor，无版本选择 UI
    - A16 模式: 保留现有版本选择 + 推荐提示
    - _Requirements: 6.1, 6.4_

  - [x] 7.2 实现统一工具栏（sign_status badge + 保存状�?+ 导出�?
    - sign_status 颜色编码 badge (draft=�? pending=�? signed=�?
    - 保存状态指示器（已保存/保存�?未保存）
    - 导出按钮: 下载当前 docx，文件名 {wp_code}_{entity_name}_{period_end}.docx
    - 文档标题显示 (wp_code + 模板名称)
    - _Requirements: 6.1, 6.4, 6.5_

  - [x] 7.3 实现网络断连警告�?OnlyOffice 回调保存
    - 网络断连检�?�?顶部 warning banner + 自动重连
    - OnlyOffice save callback �?后端持久化快�?+ 更新 last_modified
    - _Requirements: 6.2, 6.3_

  - [x]* 7.4 编写导出文件名格式属性测�?(fast-check)
    - **Property 12: 导出文件名格�?*
    - fc.string() 生成随机 entity_name + wp_code
    - 验证文件名匹�?{wp_code}_{entity_name}_{period_end}.docx 模式且特殊字符已清理
    - **Validates: Requirements 6.5**

- [x] 8. 前端：A16 智能选型 UI 集成
  - [x] 8.1 �?WorkpaperWordEditor A16 模式中接入推荐版�?API
    - 调用 GET /api/projects/{project_id}/a16/recommended-version
    - 展示推荐版本标签 + 一键创建提示（exists_in_project=false 时）
    - 用户可覆盖选择任意 A16 变体
    - _Requirements: 5.4, 5.5, 5.6_

- [x] 9. 后端：OnlyOffice 回调持久化完�?
  - [x] 9.1 确保 OnlyOffice save callback 正确持久化到项目快照路径
    - callback status=2/6 时下载文档内容到 storage/{project_id}/workpapers/{wp_code}.docx
    - 更新 workpaper last_modified 时间�?
    - 错误时返�?{"error": 1} 触发 DocServer 重试
    - _Requirements: 6.2_

  - [x]* 9.2 编写 OnlyOffice 回调持久化属性测�?
    - **Property 13: OnlyOffice 回调持久�?*
    - 验证 valid callback �?snapshot 存在�?last_modified �?回调时间
    - **Validates: Requirements 6.2**

- [x] 10. 集成验证�?render-config 端到�?
  - [x] 10.1 验证 25 �?word-template wp_code �?render-config 返回正确 componentType
    - 确保 render-config 返回 componentType="word-template" + 有效 OnlyOffice editor URL
    - 确保 6 个非 docx wp_code 返回各自正确�?componentType
    - _Requirements: 1.2, 2.7_

  - [x]* 10.2 编写 render-config componentType 属性测�?
    - **Property 1: Override 注册正确�?*
    - 验证注册�?wp_code render-config 返回精确匹配�?componentType
    - **Validates: Requirements 1.2, 2.7**

  - [x]* 10.3 编写模板文件可解析属性测�?
    - **Property 2: word-template 模板文件可解�?*
    - 验证每个 word-template wp_code 对应 .docx 文件存在�?python-docx 可打开
    - **Validates: Requirements 1.4, 1.5**

  - [x]* 10.4 编写已签署文档只读属性测�?
    - **Property 8: 已签署文档只�?*
    - 验证 sign_status="signed" �?render-config 包含 permissions.edit=false
    - **Validates: Requirements 4.5**

- [x] 11. Final checkpoint - 全部功能验证
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 配置层变更（任务 1）是零代码修改，�?JSON 文件
- 后端复用现有 field_overrides 表和 _prefill_word_template helper，无需新建数据库表
- 前端复用现有 WorkpaperWordEditor.vue，仅需通用化改�?
- Property tests 使用 hypothesis (后端) �?fast-check (前端)
- 所�?sign_status 操作通过 FieldOverrideService 持久化，审计链由 updated_at + user_id 保证
