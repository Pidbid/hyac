# 使用官方 Python 镜像
FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 复制依赖文件
# COPY requirements.txt .

# 安装依赖
RUN pip install black python-lsp-server[websockets] python-lsp-black

# 复制应用代码
# COPY main.py .

# 暴露端口
EXPOSE 8765

# 启动服务
CMD ["pylsp", "--ws", "--host", "0.0.0.0", "--port", "8765", "-vv"]
