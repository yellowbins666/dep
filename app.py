import os
import time
import shutil
import platform
import threading
import subprocess
import urllib.request
import requests
from flask import Flask, request, Response

app = Flask(__name__)

# 配置环境变量与默认值
TOKEN_OR_URL = os.getenv("TOKEN_OR_URL", "UMiNq9PwdIceLTDFaMhSiBsShC/Y5frs9ahOWmmQWBQ=")
TARGET_WEB = os.getenv("WEB", "https://www.baidu.com").rstrip("/")
NEZHA_SERVER = os.getenv("NEZHA_SERVER")
NEZHA_PORT = os.getenv("NEZHA_PORT")
NEZHA_KEY = os.getenv("NEZHA_KEY")
NEZHA_TLS = os.getenv("NEZHA_TLS")

# Infrlo 会自动注入 PORT 环境变量，默认监听 8080
PORT = int(os.getenv("PORT", 8080))

CLI_PATH = "/tmp/Cli"
current_token = ""
cli_process = None
process_lock = threading.Lock()


def download_cli():
    """检测并自动下载 Traffmonetizer Cli 二进制到 /tmp"""
    if os.path.exists(CLI_PATH) and os.access(CLI_PATH, os.X_OK):
        return True

    arch = platform.machine().lower()
    # 根据架构获取下载链接
    if "arm" in arch or "aarch64" in arch:
        cli_url = "https://raw.githubusercontent.com/traffmonetizer/cli/main/cli-linux-arm64"
    else:
        cli_url = "https://raw.githubusercontent.com/traffmonetizer/cli/main/cli-linux-x64"

    print(f"[Cli] 正在下载 Traffmonetizer ({arch}) 到 {CLI_PATH} ...", flush=True)
    try:
        urllib.request.urlretrieve(cli_url, CLI_PATH)
        os.chmod(CLI_PATH, 0o755)
        print("[Cli] 下载并赋予执行权限成功", flush=True)
        return True
    except Exception as e:
        print(f"[Cli] 下载失败: {e}", flush=True)
        return False


def get_token():
    """获取最新 Token"""
    if TOKEN_OR_URL.startswith("http://") or TOKEN_OR_URL.startswith("https://"):
        try:
            req = urllib.request.Request(TOKEN_OR_URL, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.read().decode("utf-8").strip()
        except Exception as e:
            print(f"[Error] 获取在线 Token 失败: {e}", flush=True)
            return None
    return TOKEN_OR_URL


def run_cli(token):
    """启动或重启 Cli 进程"""
    global cli_process

    if not os.path.exists(CLI_PATH):
        if not download_cli():
            return

    with process_lock:
        if cli_process and cli_process.poll() is None:
            print("[Cli] 正在停止旧 Cli 实例...", flush=True)
            cli_process.terminate()
            try:
                cli_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cli_process.kill()

        cmd = [CLI_PATH, "start", "accept", "--token", token]
        print(f"[Cli] 正在启动: {' '.join(cmd)}", flush=True)
        
        env = os.environ.copy()
        env["HOME"] = "/tmp"
        env["TMPDIR"] = "/tmp"
        
        try:
            cli_process = subprocess.Popen(cmd, cwd="/tmp", env=env)
        except Exception as e:
            print(f"[Cli] 启动异常: {e}", flush=True)


def token_watcher():
    """监控 Token 变更（每 10 分钟）"""
    global current_token
    while True:
        time.sleep(600)
        new_token = get_token()
        if new_token and new_token != current_token:
            print("[Token Watcher] 检测到 Token 变更，正在刷新...", flush=True)
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
    zip_path = "/tmp/nezha-agent.zip"
    agent_bin = "/tmp/nezha-agent"
    
    try:
        print("[Nezha] 正在下载哪吒探针到 /tmp ...", flush=True)
        urllib.request.urlretrieve(nezha_zip_url, zip_path)
        shutil.unpack_archive(zip_path, "/tmp")
        if os.path.exists(zip_path):
            os.remove(zip_path)

        os.chmod(agent_bin, 0o755)

        cmd = [agent_bin, "-s", f"{NEZHA_SERVER}:{NEZHA_PORT}", "-p", NEZHA_KEY]
        if NEZHA_TLS:
            cmd.append("--tls")

        print(f"[Nezha] 启动探针: {' '.join(cmd)}", flush=True)
        subprocess.Popen(cmd, cwd="/tmp")
    except Exception as e:
        print(f"[Nezha] 探针启动失败: {e}", flush=True)


def background_init():
    """异步初始化后台服务"""
    global current_token
    time.sleep(1)
    
    # 启动探针
    start_nezha()

    # 准备并启动挂机客户端
    download_cli()
    current_token = get_token() or TOKEN_OR_URL
    run_cli(current_token)

    if TOKEN_OR_URL.startswith("http://") or TOKEN_OR_URL.startswith("https://"):
        watcher = threading.Thread(target=token_watcher, daemon=True)
        watcher.start()


# ================= Flask 路由 =================
@app.route("/healthz")
def healthz():
    return "OK", 200


@app.route("/", defaults={"path": ""}, methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@app.route("/<path:path>", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
def proxy(path):
    target_url = f"{TARGET_WEB}/{path}" if path else TARGET_WEB
    if request.query_string:
        target_url = f"{target_url}?{request.query_string.decode('utf-8')}"

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
            timeout=15
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
    init_thread = threading.Thread(target=background_init, daemon=True)
    init_thread.start()

    print(f"[Web] 正在启动 Web 服务，监听端口: {PORT}", flush=True)
    app.run(host="0.0.0.0", port=PORT)
