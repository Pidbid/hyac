#!/bin/bash

# 默认值
PLATFORM_ENABLED=false
SERVICES=()
PUSH_ENABLED=true # 原始命令包含 --push

# 显示用法说明
usage() {
  echo "Usage: $0 [-p] [service1 service2 ...]"
  echo "  -p: 启用多平台构建 (linux/amd64, linux/arm64)."
  echo "  services: 要构建的服务的可选列表 (例如: app web server). 如果未指定则构建所有服务."
  echo "示例: ./build.sh -p app server"
  exit 1
}

# 解析选项
while getopts "p" opt; do
  case ${opt} in
    p )
      PLATFORM_ENABLED=true
      ;;
    \? )
      usage
      ;;
  esac
done
shift $((OPTIND -1))

# 从剩余参数中获取服务名称
SERVICES=("$@")

# 切换到项目根目录
cd "$(dirname "$0")/.."

# 构建基础命令
CMD="docker buildx bake --file docker-compose.yml"

# 如果启用，则添加平台设置
if [ "$PLATFORM_ENABLED" = true ]; then
  CMD+=" --set \"*.platform=linux/amd64,linux/arm64\""
fi

# 添加 --push 标志
if [ "$PUSH_ENABLED" = true ]; then
  CMD+=" --push"
fi

# 添加要构建的服务
if [ ${#SERVICES[@]} -gt 0 ]; then
  CMD+=" ${SERVICES[*]}"
fi

# 打印并执行命令
echo "Executing command:"
echo "$CMD"
eval "$CMD"