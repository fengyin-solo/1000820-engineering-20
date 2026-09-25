#!/usr/bin/env python3
"""后端接口自检。

把以前「各跑各的」的接口自检固定下来：
1. 用 backend/.venv 起一个临时 uvicorn（加载 .ci-work/data/yard.json 箱区样板）；
2. 打健康检查、运营概览、全部 18 个模块的列表接口；
3. 校验 /api/yard 返回与样板数据逐条一致，并跑一遍启用/封闭/腾空状态流转；
4. 结果写报告文件，任何一步失败都指出是数据问题还是构建（代码/环境）问题。

退出码：
    0 通过            2 数据问题（样板与接口对不上）
    3 构建问题（代码/接口报错）   4 环境问题（venv/依赖/起不来）
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
VENV_PYTHON = BACKEND_DIR / ".venv" / "bin" / "python"
DATA_FILE = REPO_ROOT / ".ci-work" / "data" / "yard.json"
REPORT = REPO_ROOT / ".ci-work" / "reports" / "backend-selfcheck.log"
EXPECTED_MODULES = 18
EXPECTED_MODULE_NAMES = [
    "berth", "container", "crane", "customer", "damage", "gate", "loading",
    "manifest", "pilot", "safety", "settle", "storage", "tally", "truck",
    "vessel", "voyage", "yard", "yardstore",
]

EXIT_OK = 0
EXIT_DATA = 2
EXIT_BUILD = 3
EXIT_ENV = 4


class Reporter:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def log(self, message: str = "") -> None:
        print(message)
        self.lines.append(message)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")


def fail(code: int, kind: str, message: str, report: Reporter) -> int:
    report.log(f"[失败][{kind}] {message}")
    report.log(f"结论：后端自检未通过（{kind}），本次不能提交。")
    report.save(REPORT)
    return code


def ensure_venv(report: Reporter) -> int:
    """确认 venv 可用；不存在或解释器失效时按 backend/run.sh 同样口径重建。"""
    if VENV_PYTHON.exists():
        probe = subprocess.run(
            [str(VENV_PYTHON), "-c", "import fastapi, uvicorn"],
            cwd=BACKEND_DIR, capture_output=True, text=True,
        )
        if probe.returncode == 0:
            return EXIT_OK
        report.log("[环境] 现有 .venv 已失效（解释器或依赖不可用），删除重建。")
        import shutil
        shutil.rmtree(BACKEND_DIR / ".venv", ignore_errors=True)

    report.log("[环境] 未找到可用的 backend/.venv，开始创建并安装依赖……")
    # 部分系统 python3-venv 缺 ensurepip：先建无 pip 的 venv，再用 get-pip 引导
    created = subprocess.run(
        [sys.executable, "-m", "venv", ".venv"], cwd=BACKEND_DIR,
        capture_output=True, text=True,
    )
    if created.returncode != 0 and "ensurepip" in (created.stderr + created.stdout):
        report.log("[环境] 标准 venv 创建失败（缺 ensurepip），改用 --without-pip + get-pip 引导。")
        subprocess.run([sys.executable, "-m", "venv", "--without-pip", ".venv"],
                       cwd=BACKEND_DIR, check=True, capture_output=True)
        bootstrap = REPO_ROOT / ".ci-work" / "get-pip.py"
        if not bootstrap.exists():
            bootstrap.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve("https://bootstrap.pypa.io/get-pip.py", bootstrap)
        pip_bootstrap = subprocess.run(
            [str(VENV_PYTHON), str(bootstrap)], cwd=BACKEND_DIR,
            capture_output=True, text=True,
        )
        if pip_bootstrap.returncode != 0:
            return fail(EXIT_ENV, "环境问题",
                        f"无法在 venv 中引导 pip：{pip_bootstrap.stderr.strip() or pip_bootstrap.stdout.strip()}",
                        report)
    elif created.returncode != 0:
        return fail(EXIT_ENV, "环境问题",
                    f"创建 venv 失败：{created.stderr.strip() or created.stdout.strip()}", report)

    install = subprocess.run(
        [str(VENV_PYTHON), "-m", "pip", "install", "-q", "-r", "requirements.txt"],
        cwd=BACKEND_DIR, capture_output=True, text=True,
    )
    if install.returncode != 0:
        return fail(EXIT_ENV, "环境问题",
                    f"安装后端依赖失败：{install.stderr.strip() or install.stdout.strip()}", report)
    report.log("[环境] backend/.venv 就绪。")
    return EXIT_OK


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request(method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode())


def wait_ready(base: str, proc: subprocess.Popen) -> tuple[bool, str]:
    deadline = time.time() + 20
    last = "服务在 20 秒内未监听端口"
    while time.time() < deadline:
        if proc.poll() is not None:
            return False, f"uvicorn 提前退出（exit={proc.returncode}），见上方服务日志"
        try:
            with urllib.request.urlopen(f"{base}/api/health", timeout=2) as resp:
                if resp.status == 200:
                    return True, ""
        except (urllib.error.URLError, ConnectionError, OSError) as exc:
            last = str(exc)
        time.sleep(0.4)
    return False, last


def main() -> int:
    report = Reporter()
    report.log("==== 后端接口自检 ====")

    if not DATA_FILE.exists():
        return fail(EXIT_DATA, "数据问题",
                    f"找不到箱区样板 {DATA_FILE.relative_to(REPO_ROOT)}，请先重跑数据生成步骤（make verify-data）。",
                    report)
    try:
        seed = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        seed_rows = seed["rows"]
    except (json.JSONDecodeError, KeyError) as exc:
        return fail(EXIT_DATA, "数据问题", f"箱区样板文件无法解析：{exc}", report)

    code = ensure_venv(report)
    if code != EXIT_OK:
        return code

    port = free_port()
    base = f"http://127.0.0.1:{port}"
    env = {**os.environ, "YARD_SEED_FILE": str(DATA_FILE)}
    report.log(f"[构建] 启动临时 uvicorn（端口 {port}，加载箱区样板 {len(seed_rows)} 条）……")
    server = subprocess.Popen(
        [str(VENV_PYTHON), "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=BACKEND_DIR, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        ready, reason = wait_ready(base, server)
        if not ready:
            output = server.stdout.read() if server.stdout else ""
            report.log("---- uvicorn 输出 ----")
            report.log(output.strip()[-2000:])
            return fail(EXIT_BUILD, "构建问题", f"后端服务启动失败：{reason}", report)

        # 1) 健康检查
        try:
            health = request("GET", f"{base}/api/health")
        except Exception as exc:  # noqa: BLE001 - 自检脚本需要兜住一切请求异常
            return fail(EXIT_BUILD, "构建问题", f"/api/health 请求失败：{exc}", report)
        if health.get("modules") != EXPECTED_MODULES:
            return fail(EXIT_BUILD, "构建问题",
                        f"/api/health 报告模块数 {health.get('modules')}，应为 {EXPECTED_MODULES}", report)
        report.log(f"[构建] 健康检查通过：{EXPECTED_MODULES} 个模块已挂载。")

        # 2) 全部模块列表接口可访问、分页口径正确
        for name in EXPECTED_MODULE_NAMES:
            try:
                page = request("GET", f"{base}/api/{name}?page=1&size=20")
            except Exception as exc:  # noqa: BLE001
                return fail(EXIT_BUILD, "构建问题", f"GET /api/{name} 请求失败：{exc}", report)
            if not isinstance(page.get("items"), list) or page.get("page") != 1 or page.get("size") != 20:
                return fail(EXIT_BUILD, "构建问题",
                            f"GET /api/{name} 返回不符合 {{items,total,page,size}} 口径：{page}", report)
        report.log(f"[构建] {EXPECTED_MODULES} 个模块列表接口全部可访问。")

        # 3) 箱区接口数据与样板逐条一致（这是数据问题的主要判定点）
        served = request("GET", f"{base}/api/yard?page=1&size=200")
        if served.get("total") != len(seed_rows):
            return fail(EXIT_DATA, "数据问题",
                        f"/api/yard 共 {served.get('total')} 条，样板文件有 {len(seed_rows)} 条", report)
        served_by_id = {row["id"]: row for row in served["items"]}
        for expected in seed_rows:
            actual = served_by_id.get(expected["id"])
            if actual is None:
                return fail(EXIT_DATA, "数据问题",
                            f"样板箱区 id={expected['id']}（{expected['箱区编号']}）在接口结果中缺失", report)
            for field, value in expected.items():
                if actual.get(field) != value:
                    return fail(EXIT_DATA, "数据问题",
                                f"箱区 {expected['箱区编号']} 字段「{field}」接口返回 {actual.get(field)!r}，"
                                f"样板为 {value!r}", report)
        report.log(f"[数据] /api/yard 返回与样板完全一致：{len(seed_rows)} 条。")

        # 4) 状态流转：待启用 -> 正常堆放 -> 已封闭 -> 待启用
        first = seed_rows[0]
        if first["status"] != "待启用":
            return fail(EXIT_DATA, "数据问题",
                        f"样板首条箱区应为「待启用」以便验证流转，实际为 {first['status']}", report)
        entry_id = first["id"]
        for action, expect in [("启用箱区", "正常堆放"), ("封闭箱区", "已封闭"), ("腾空箱区", "待启用")]:
            result = request("POST", f"{base}/api/yard/{entry_id}/actions",
                             {"values": {"action": action}})
            if not result.get("ok") or result.get("entry", {}).get("status") != expect:
                return fail(EXIT_BUILD, "构建问题",
                            f"箱区动作「{action}」未到达「{expect}」，接口返回：{result}", report)
        report.log("[构建] 箱区动作流转验证通过：启用 -> 封闭 -> 腾空。")

        # 5) 非法动作应被拦下（错误处理不能 500）
        blocked = request("POST", f"{base}/api/yard/{entry_id}/actions",
                          {"values": {"action": "不存在的动作"}})
        if blocked.get("ok") is not False:
            return fail(EXIT_BUILD, "构建问题",
                        f"非法动作本应被业务层拦下返回 ok=false，实际：{blocked}", report)
        report.log("[构建] 非法动作被正确拦截。")
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()

    report.log("结论：后端自检通过（接口可访问、箱区样板一致、状态流转正常）。")
    report.save(REPORT)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
