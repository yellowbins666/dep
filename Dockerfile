# ----------------------------------------------------
# 第一阶段：从官方镜像精准提取
# ----------------------------------------------------
# 使用 --platform=$BUILDPLATFORM 确保拉取到正确的架构镜像
FROM --platform=$TARGETPLATFORM traffmonetizer/cli_v2:latest AS source

# ----------------------------------------------------
# 第二阶段：构建 Alpine 运行环境
# ----------------------------------------------------
FROM alpine:latest

# 1. 安装必要的兼容库
RUN apk add --no-cache \
    bash supervisor nginx curl wget unzip ca-certificates \
    wireguard-tools iproute2 icu-libs krb5-libs libgcc \
    libintl libssl3 libstdc++ zlib gcompat 

# 2. 准备目录
WORKDIR /app
RUN mkdir -p /run/nginx /etc/supervisor.d

# 3. 【核心修正】
# 已经确认官方镜像路径为 /usr/local/bin/cli
# 我们将其复制到 /app 并改名为 Cli 以匹配你的 start.sh 脚本
COPY --from=source /usr/local/bin/cli /app/Cli

# 4. 复制本地启动脚本
COPY start.sh /app/start.sh

# 5. 赋予权限
RUN chmod +x /app/Cli /app/start.sh

# 6. 配置 Supervisord
RUN sed -i 's/*.ini/*.conf/' /etc/supervisord.conf || true && \
    echo "[include]" > /etc/supervisord.conf && \
    echo "files = /etc/supervisor.d/*.ini" >> /etc/supervisord.conf

# 7. 端口及启动
EXPOSE 80
CMD ["/app/start.sh"]
