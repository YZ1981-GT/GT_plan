# 任务清单：多 Sheet 底稿 OnlyOffice 渲染

## Sprint 1：后端 WOPI 基础设施（4 任务）

- [x] 1.1 创建 `wp_onlyoffice_router.py`：`GET /{wp_id}/sheets/{sheet_name}/onlyoffice-config` 端点（生成 doc_key + download_url + callback_url + JWT token）
- [x] 1.2 实现文件管理：首次打开从模板复制到项目存储 `storage/projects/{pid}/workpapers/onlyoffice/`，后续复用
- [x] 1.3 实现 `POST /{wp_id}/sheets/{sheet_name}/onlyoffice-callback`：status=2 时下载编辑后文件覆盖存储
- [x] 1.4 `wp_render_config.py` dispatch 循环：非 HTML 白名单 + 无 renderer + 多 sheet → `componentType="onlyoffice-sheet"` + `html_data={onlyoffice: true, sheet_name}`

## Sprint 2：前端 OnlyOffice 集成（3 任务）

- [x] 2.1 创建 `GtOnlyOfficeSheet.vue`：动态加载 OnlyOffice JS API + 创建 DocEditor iframe
- [x] 2.2 `GtWpRenderer.vue`：在 `noRendererGridFallback` 之前加 `isOnlyOfficeSheet` 分发，路由到 `GtOnlyOfficeSheet`
- [x] 2.3 降级逻辑：OnlyOffice 不可用时（fetch 超时/容器 down）自动回退 GtGridSheet 只读网格

## Sprint 3：测试与验证（3 任务）

- [x] 3.1 后端测试：WOPI config 生成 + JWT 签名 + 文件复制逻辑（pytest）
- [x] 3.2 render-config 冒烟测试：D0 底稿非白名单 sheet 返回 `onlyoffice-sheet` componentType（1101 测试零回归）
- [x] 3.3 Playwright 实测：D0 底稿切换到函证检查表 tab → OnlyOffice iframe 可见 / 编辑 / 保存回调生效

## 验收门槛

- V1: D0 底稿 HTML 白名单 sheet（目录/D0A/审定表/附注/调整表）渲染不变
- V2: D0 底稿非白名单 sheet（D0-1~D0-8/示例表）在 OnlyOffice 中可编辑
- V3: OnlyOffice 容器 down 时自动降级到只读网格
- V4: 1101 render-config 冒烟测试零回归
- V5: 现有交付模块 OnlyOffice 功能不受影响
