FROM --platform=$TARGETPLATFORM traffmonetizer/cli_v2:latest AS source[cite: 2]

FROM alpine:latest[cite: 2]

# 安装系统运行依赖与 Node.js 环境[cite: 2]
RUN apk add --no-cache \
    bash curl wget unzip ca-certificates \
    wireguard-tools iproute2 icu-libs krb5-libs libgcc \
    libintl libssl3 libstdc++ zlib gcompat \
    nodejs npm[cite: 2]

WORKDIR /app[cite: 2]

# 复制二进制并重命名为小写的 cli
COPY --from=source /usr/local/bin/cli /app/cli
COPY package*.json /app/
RUN npm install --production

COPY index.js /app/index.js
RUN chmod +x /app/cli

ENV PORT=8080
EXPOSE 8080

CMD ["node", "/app/index.js"]
