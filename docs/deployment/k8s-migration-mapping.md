# A → B（K8s）替换映射表

## A/B 通用抽象（零改动复用）

| 能力 | A 实现 | K8s（B）对应 |
|------|--------|-------------|
| 就绪探针 /readyz | nginx 被动健康检查 | `readinessProbe: httpGet /readyz` |
| 存活探针 /livez | 手动监控 | `livenessProbe: httpGet /livez` |
| 版本端点 /api/version | 同 | 同 |
| 迁移串行化 pg_advisory_lock | 同 | 同 |
| HTTP 优雅下线 | SIGTERM + drain | `terminationGracePeriodSeconds: 40` |
| feature flag | DB-backed | 同 |

## A 专属 → B 替换

| A 方案（本期） | K8s（B）替换 |
|----------------|-------------|
| docker-compose backend × N | Deployment replicas: N |
| nginx upstream + reload | Service + Endpoints（readiness 自动增删）|
| rolling_update.sh | Deployment strategy: RollingUpdate (maxUnavailable=0) |
| stop_grace_period: 40s | terminationGracePeriodSeconds: 40 |
| nginx 80:80 | Service + Ingress |
| BUILD_VERSION_JSON env | ConfigMap/Secrets |

## 迁移路径

1. 通用抽象（探针/版本/优雅下线/迁移串行化）直接复用，不改代码
2. 删除 nginx service 和 rolling_update.sh
3. 编写 Deployment/Service/Ingress YAML
4. 配置 readiness/liveness probe 指向 /readyz /livez
5. 设置 terminationGracePeriodSeconds >= GRACEFUL_SHUTDOWN_TIMEOUT
