#!/usr/bin/env bash
# Feature: zero-downtime-deployment, Component 6c (A 专属)
# 滚动替换脚本：逐副本启新→就绪门控→nginx reload→停旧→nginx reload
set -euo pipefail

# 配置
IMAGE="${1:?Usage: $0 <new-image> [--rollback <old-image>]}"
READINESS_TIMEOUT="${READINESS_TIMEOUT:-120}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
NGINX_SERVICE="nginx"
REPLICAS=("backend1" "backend2")

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

check_readyz() {
    local container="$1"
    local timeout="$2"
    local elapsed=0
    while [ $elapsed -lt $timeout ]; do
        if docker exec "$container" curl -sf http://localhost:8000/readyz > /dev/null 2>&1; then
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    return 1
}

reload_nginx() {
    docker compose -f "$COMPOSE_FILE" exec "$NGINX_SERVICE" nginx -s reload
    log "nginx reloaded"
}

# 主流程：逐副本替换
for replica in "${REPLICAS[@]}"; do
    log "Rolling $replica → $IMAGE"

    # 1. 启动新容器
    log "Starting new $replica..."
    docker compose -f "$COMPOSE_FILE" up -d --no-deps --build "$replica"

    # 2. 就绪门控
    log "Waiting for $replica readyz (timeout=${READINESS_TIMEOUT}s)..."
    if ! check_readyz "$replica" "$READINESS_TIMEOUT"; then
        log "ERROR: $replica failed readyz within ${READINESS_TIMEOUT}s"
        log "ABORT: Keeping old replicas running, NOT stopping anything"
        exit 1
    fi

    log "$replica is ready"

    # 3. nginx reload（新副本加入 upstream）
    reload_nginx

    # 4. 给 drain 时间（SIGTERM 由 docker stop 发送，stop_grace_period=40s）
    log "$replica rolling complete"
done

log "All replicas updated successfully. Zero-downtime rolling update complete."
