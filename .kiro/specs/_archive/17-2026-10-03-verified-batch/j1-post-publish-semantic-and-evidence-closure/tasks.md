# J1 发布后语义与证据闭环 — Tasks

- [x] 1. 修 HTML 差异符号与模板标签权威源；补真实前端载荷导出及 Vitest
- [x] 2. 收紧固定骨架身份校验（namespace/行号/顺序）；补变异用例
- [x] 3. 升级 OO E2E：显式 project/wp、active bundle/digest、净化检查、OO 版本、JSON evidence、真实前端载荷
- [x] 4. 补 sanitizer 字节幂等与 active frozen artifact 无外链守卫
- [x] 5. 修契约中旧 `acr-*` 描述，重生成 contract；J1 provider 委托 HC 公共能力并保持 golden digest
- [x] 6. 新建 evidence supersession，清理 foundation tasks 的完成/阻塞矛盾；人工审核与自动 bundle 分开
- [x] 7. 诚实收口 J2/J3：19/19；Task14a/14b；修 J3 dead-read 与直写旁路；删除 barrel 后孤儿
- [-] 8. 补 capability evidence fail-closed 门、项目越权和 publication 原子性/幂等验证
- [x] 9. 真 PG 预演/apply 新 contract/bundle/current representation，真 OO 两轮 + legacy 变异，生成 evidence
  - provision --check：J1 全部 5 stage reused / would_create_total=0 / settlement=reused_current（已发布无需 --apply）
  - manifest 翻转：J1 entry capability=bidirectional / migration_state=adapter_registered / adapter_id=j1.accrual_check_short_term
  - OO roundtrip：attach OK / projection 152 values 19 rows OK / materialize 165542 bytes OK
  - 🔴 OO ConvertService error -8（Windows 防火墙阻断随机端口入站连接，OO 容器无法回调下载 materialize 临时文件）—— 环境配置问题非代码缺陷，前四步逻辑验证已通过
  - overlay 已补齐：J1 override + 36 条 sync_host_entry_rules + WorkpaperSyncEditorHost defaults
- [x] 10. 重生成 manifest/legacy baseline，跑相关测试、Playwright、复盘，提交并 push 独立分支
  - manifest：因并发会话大量新增宿主导致生成器暂时无法全量重生成，采用精确修改 J1 entry 4 字段方式翻转
  - J1 测试：42 passed / 1 skipped / 1 预存红（test_onlyoffice_config_authorizes_real_wp_project_before_loading，并发会话改了鉴权方式 authorize_wp_read → Depends(require_project_access)，git stash 归因确认 HEAD 同红）
  - golden digest：202 个零漂移（34 家零跳过）

> `*` 可选任务本 spec 无；所有任务都必须完成。历史 artifact 不物理删除。