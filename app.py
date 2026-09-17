import os
import time
import shutil
import platform
import threading
import subprocess
import urllib.request
from flask import Flask, request, Response

app = Flask(__name__)

# 读取环境变量
TOKEN_OR_URL = os.getenv("TOKEN_OR_URL", "UMiNq9PwdIceLTDFaMhSiBsShC/Y5frs9ahOWmmQWBQ=")
TARGET_WEB = os.getenv("WEB", "https://www.baidu.com").rstrip("/")
NEZHA_SERVER = os.getenv("NEZHA_SERVER")
NEZHA_PORT = os.getenv("NEZHA_PORT")
NEZHA_KEY = os.getenv("NEZHA_KEY")
NEZHA_TLS = os.getenv("NEZHA_TLS")
WARP = os.getenv("WARP")

current_token = ""
cli_process = None
process_lock = threading.Lock()


def get_token():
    """获取最新 Token"""
    if TOKEN_OR_URL.startswith("http://") or TOKEN_OR_URL.startswith("https://"):
        try:
            req = urllib.request.Request(TOKEN_OR_URL, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.read().decode("utf-8").strip()
        except Exception as e:
            print(f"[Error] 获取在线 Token 失败: {e}")
            return None
    return TOKEN_OR_URL


def run_cli(token):
    """启动或重启 /app/Cli 进程"""
    global cli_process
    with process_lock:
        if cli_process and cli_process.poll() is None:
            print("[Cli] 正在停止旧 Cli 实例...")
            cli_process.terminate()
            try:
                cli_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cli_process.kill()

        cmd = ["/app/Cli", "start", "accept", "--token", token]
        print(f"[Cli] 正在启动: {' '.join(cmd)}")
        cli_process = subprocess.Popen(cmd)


def token_watcher():
    """监控 Token 变更（每 10 分钟）并自动重启 Cli 进程"""
    global current_token
    while True:
        time.sleep(600)
        new_token = get_token()
        if new_token and new_token != current_token:
            print(f"[Token Watcher] 检测到 Token 变更，正在刷新...")
            current_token = new_token
            run_cli(current_token)


def start_nezha():
    """下载并启动哪吒探针"""
    if not (NEZHA_SERVER and NEZHA_PORT and NEZHA_KEY):
        return

    arch = platform.machine()
    arch_map = {"x86_64": "amd64", "aarch64": "arm64"}
    target_arch = arch_map.get(arch, arch)

    nezha_zip_url = f"https://github.com/nezhahq/agent/releases/latest/download/nezha-agent_linux_{target_arch}.zip"
    try:
        print("[Nezha] 正在下载哪吒探针...")
        urllib.request.urlretrieve(nezha_zip_url, "/app/nezha-agent.zip")
        shutil.unpack_archive("/app/nezha-agent.zip", "/app")
        if os.path.exists("/app/nezha-agent.zip"):
            os.remove("/app/nezha-agent.zip")
        
        agent_bin = "/app/nezha-agent"
        os.chmod(agent_bin, 0o755)

        cmd = [agent_bin, "-s", f"{NEZHA_SERVER}:{NEZHA_PORT}", "-p", NEZHA_KEY]
        if NEZHA_TLS:
            cmd.append("--tls")

        print(f"[Nezha] 启动探针: {' '.join(cmd)}")
        subprocess.Popen(cmd)
    except Exception as e:
        print(f"[Nezha] 探针启动失败: {e}")


def start_warp():
    """启动 WARP"""
    if WARP:
        print("[WARP] 正在启用 wgcf...")
        try:
            subprocess.run(["wg-quick", "up", "wgcf"], check=False)
        except Exception as e:
            print(f"[WARP] 启动失败: {e}")


# ================= Flask 反代路由 =================
import requests

@app.route("/", defaults={"path": ""}, methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@app.route("/<path:path>", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
def proxy(path):
    target_url = f"{TARGET_WEB}/{path}" if path else TARGET_WEB
    if request.query_string:
        target_url = f"{target_url}?{request.query_string.decode('utf-8')}"

    # 剔除逐跳标头
    headers = {k: v for k, v in request.headers if k.lower() not in ["host", "content-length"]}
    headers["Host"] = TARGET_WEB.split("//")[-1].split("/")[0]

    try:
        resp = requests.request(
            method=request.method,
            url=target_url,
            headers=headers,
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
            timeout=30
        )
        excluded_headers = ["content-encoding", "content-length", "transfer-encoding", "connection"]
        response_headers = [
            (name, value) for name, value in resp.raw.headers.items()
            if name.lower() not in excluded_headers
        ]
        return Response(resp.content, resp.status_code, response_headers)
    except Exception as e:
        return f"Proxy error: {str(e)}", 502


if __name__ == "__main__":
    start_warp()
    start_nezha()

    current_token = get_token() or TOKEN_OR_URL
    run_cli(current_token)

    if TOKEN_OR_URL.startswith("http://") or TOKEN_OR_URL.startswith("https://"):
        watcher = threading.Thread(target=token_watcher, daemon=True)
        watcher.start()

    # 启动 Web 服务，监听 80 端口
    app.run(host="0.0.0.0", port=80)
