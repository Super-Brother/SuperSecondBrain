#!/usr/bin/env bash
# 重新部署 Docker Compose 服务（停 → 构建 → 启动 → 健康检查）
#
# 用法：
#   ./redeploy.sh                      # 默认使用 docker-compose.server.yml，增量构建
#   ./redeploy.sh -f docker-compose.yml  # 指定 compose 文件
#   ./redeploy.sh --no-cache            # 完全重建（清缓存）
#   ./redeploy.sh --logs                # 启动后跟随日志
#   ./redeploy.sh --pull                # 重新拉取基础镜像
#   ./redeploy.sh --service api         # 只重建指定服务
#
# 注意：默认保留命名卷（redis_data / huggingface_cache），避免丢失模型缓存。
#       如需清空数据卷请加 --volumes（危险操作）。

set -euo pipefail

# ---------- 默认参数 ----------
COMPOSE_FILE="docker-compose.server.yml"
NO_CACHE=""
PULL=""
FOLLOW_LOGS=false
TARGET_SERVICE=""
REMOVE_VOLUMES=false
HEALTH_PORT="8001"
HEALTH_TIMEOUT=120

# ---------- 颜色输出 ----------
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_err()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ---------- 解析参数 ----------
require_arg() {
    if [[ $# -lt 2 || -z "${2:-}" || "${2:0:1}" == "-" ]]; then
        log_err "参数 $1 需要一个值"
        exit 1
    fi
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -f|--file)
            require_arg "$@"
            COMPOSE_FILE="$2"
            shift 2
            ;;
        --no-cache)
            NO_CACHE="--no-cache"
            shift
            ;;
        --pull)
            PULL="--pull"
            shift
            ;;
        --logs)
            FOLLOW_LOGS=true
            shift
            ;;
        --service)
            require_arg "$@"
            TARGET_SERVICE="$2"
            shift 2
            ;;
        --volumes)
            REMOVE_VOLUMES=true
            shift
            ;;
        --port)
            require_arg "$@"
            HEALTH_PORT="$2"
            shift 2
            ;;
        -h|--help)
            cat <<'EOF'
重新部署 Docker Compose 服务（停 → 构建 → 启动 → 健康检查）

用法：
  ./redeploy.sh                      # 默认使用 docker-compose.server.yml，增量构建
  ./redeploy.sh -f docker-compose.yml  # 指定 compose 文件
  ./redeploy.sh --no-cache            # 完全重建（清缓存）
  ./redeploy.sh --logs                # 启动后跟随日志
  ./redeploy.sh --pull                # 重新拉取基础镜像
  ./redeploy.sh --service api         # 只重建指定服务
  ./redeploy.sh --port 8001           # 健康检查端口（默认 8001）
  ./redeploy.sh --volumes             # 同时移除命名卷（危险，会丢模型缓存）

注意：默认保留命名卷（redis_data / huggingface_cache），避免丢失模型缓存。
EOF
            exit 0
            ;;
        *)
            log_err "未知参数: $1"
            exit 1
            ;;
    esac
done

# ---------- 前置检查 ----------
if ! command -v docker >/dev/null 2>&1; then
    log_err "未检测到 docker，请先安装"
    exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
    log_err "未检测到 docker compose v2，请升级"
    exit 1
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
    log_err "Compose 文件不存在: $COMPOSE_FILE"
    exit 1
fi

log_info "Compose 文件: $COMPOSE_FILE"
log_info "构建参数: ${NO_CACHE:-增量} ${PULL:-}"
[[ -n "$TARGET_SERVICE" ]] && log_info "目标服务: $TARGET_SERVICE"

# ---------- Step 1: 停止现有容器 ----------
log_info "[1/4] 停止现有容器..."
DOWN_ARGS=()
if $REMOVE_VOLUMES; then
    log_warn "将移除命名卷（数据丢失风险）"
    read -rp "确认继续？(yes/N) " confirm
    [[ "$confirm" == "yes" ]] || { log_info "已取消"; exit 0; }
    DOWN_ARGS+=("--volumes")
fi

if [[ -n "$TARGET_SERVICE" ]]; then
    docker compose -f "$COMPOSE_FILE" stop "$TARGET_SERVICE" || true
    docker compose -f "$COMPOSE_FILE" rm -f "$TARGET_SERVICE" || true
else
    docker compose -f "$COMPOSE_FILE" down "${DOWN_ARGS[@]}" || true
fi
log_ok "容器已停止"

# ---------- Step 2: 构建镜像 ----------
log_info "[2/4] 构建镜像..."
BUILD_ARGS=()
[[ -n "$NO_CACHE" ]] && BUILD_ARGS+=("$NO_CACHE")
[[ -n "$PULL" ]] && BUILD_ARGS+=("$PULL")

if [[ -n "$TARGET_SERVICE" ]]; then
    docker compose -f "$COMPOSE_FILE" build "${BUILD_ARGS[@]}" "$TARGET_SERVICE"
else
    docker compose -f "$COMPOSE_FILE" build "${BUILD_ARGS[@]}"
fi
log_ok "镜像构建完成"

# ---------- Step 3: 启动容器 ----------
log_info "[3/4] 启动容器..."
if [[ -n "$TARGET_SERVICE" ]]; then
    docker compose -f "$COMPOSE_FILE" up -d "$TARGET_SERVICE"
else
    docker compose -f "$COMPOSE_FILE" up -d
fi
log_ok "容器已启动"

# ---------- Step 4: 健康检查 ----------
log_info "[4/4] 等待服务就绪（端口 $HEALTH_PORT，最长 ${HEALTH_TIMEOUT}s）..."
ELAPSED=0
INTERVAL=3
HEALTH_OK=false
while [[ $ELAPSED -lt $HEALTH_TIMEOUT ]]; do
    if curl -fsS "http://localhost:${HEALTH_PORT}/health" >/dev/null 2>&1; then
        HEALTH_OK=true
        break
    fi
    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))
    printf "."
done
echo

if $HEALTH_OK; then
    log_ok "服务就绪（${ELAPSED}s）"
    HEALTH_RESP=$(curl -s "http://localhost:${HEALTH_PORT}/health")
    echo "  → $HEALTH_RESP"
else
    log_err "健康检查超时（${HEALTH_TIMEOUT}s），打印最近 50 行日志："
    docker compose -f "$COMPOSE_FILE" logs --tail=50
    exit 2
fi

# ---------- 容器状态 ----------
echo
log_info "容器状态："
docker compose -f "$COMPOSE_FILE" ps

# ---------- 可选：跟随日志 ----------
if $FOLLOW_LOGS; then
    echo
    log_info "跟随日志（Ctrl+C 退出）..."
    docker compose -f "$COMPOSE_FILE" logs -f --tail=50
fi
