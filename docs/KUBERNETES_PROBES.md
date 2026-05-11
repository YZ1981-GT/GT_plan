# Kubernetes Liveness / Readiness Probe 配置

## 健康端点

```
GET /api/health/ledger-import
```

返回 JSON：

```json
{
  "status": "healthy",
  "queue_depth": 2,
  "active_workers": 1,
  "expected_workers": 1,
  "p95_duration_seconds": 45.0,
  "pg_connection_pool_used": 5,
  "pg_connection_pool_max": 20
}
```

### 三态健康模型

| 状态 | 含义 | HTTP |
|------|------|------|
| `healthy` | worker 全存活 + P95 < 10min + pool < 80% | 200 |
| `degraded` | P95 > 10min 或 pool > 80%（仍可服务） | 200 |
| `unhealthy` | worker 预期 ≥1 但活跃 = 0，或 pool 满 | 200 |

## Deployment YAML 示例

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: audit-platform-backend
spec:
  template:
    spec:
      containers:
        - name: backend
          image: audit-platform-backend:latest
          ports:
            - containerPort: 9980
          livenessProbe:
            httpGet:
              path: /api/health/ledger-import
              port: 9980
            initialDelaySeconds: 30
            periodSeconds: 15
            failureThreshold: 3
            timeoutSeconds: 5
          readinessProbe:
            httpGet:
              path: /api/health/ledger-import
              port: 9980
            initialDelaySeconds: 30
            periodSeconds: 15
            failureThreshold: 3
            timeoutSeconds: 5
```

## Probe 判定逻辑

- **Liveness**：`GET /api/health/ledger-import` 返回 200 即存活。
- **Readiness**：响应 200 且 `status != "unhealthy"` 视为就绪。
  K8s 原生 httpGet 只看 status code，如需按 body 判定可改用 exec probe：

```yaml
readinessProbe:
  exec:
    command:
      - sh
      - -c
      - 'curl -sf http://localhost:9980/api/health/ledger-import | grep -v unhealthy'
  initialDelaySeconds: 30
  periodSeconds: 15
  failureThreshold: 3
```

## 推荐参数

| 参数 | 值 | 说明 |
|------|-----|------|
| `initialDelaySeconds` | 30 | 等待 Alembic 迁移 + worker 启动 |
| `periodSeconds` | 15 | 平衡灵敏度与 PG 查询开销 |
| `failureThreshold` | 3 | 连续 3 次失败才重启/摘流量 |
| `timeoutSeconds` | 5 | 端点内部查 PG pool，正常 <1s |
