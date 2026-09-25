#!/usr/bin/env python3
"""后端接口自检：起一个临时 uvicorn，把每个模块的接口跑一遍。

检查项（全部走真实 HTTP，不直接调函数）：
- GET  /api/health、/api/overview 能返回且模块数完整；
- 每个业务模块：
  - GET    /api/<m>              列表分页结构 {items,total,page,size}；
  - GET    /api/<m>/1            明细可读；GET 一个不存在的 id 返回 404；
  - POST   /api/<m>              缺必填字段时 ok=false，提交合法字段后创建成功；
  - POST   /api/<m>/<id>/actions 非法动作被拒，合法动作后状态落到目标状态；
  - GET    /api/<m>/export       导出 total 与列表一致。

服务只在自检期间存活：随机端口、跑完即停，不写文件、不留进程。
退出码非 0 即视为「后端构建/接口问题」。
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_ready(base_url: str, proc: subprocess.Popen[bytes], timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"uvicorn 提前退出（code={proc.returncode}），见上方日志")
        try:
            with urllib.request.urlopen(f"{base_url}/api/health", timeout=1) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:  # 服务还没起来，继续等
            last_error = exc
            time.sleep(0.3)
    raise RuntimeError(f"服务在 {timeout}s 内未就绪：{last_error}")


def request(method: str, url: str, payload: dict[str, Any] | None = None) -> tuple[int, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


class Reporter:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.checks = 0

    def check(self, condition: bool, message: str) -> None:
        self.checks += 1
        mark = "PASS" if condition else "FAIL"
        print(f"  [{mark}] {message}")
        if not condition:
            self.failures.append(message)


def main() -> int:
    sys.path.insert(0, str(BACKEND))
    from app.routers import ROUTERS  # noqa: E402

    python = str(BACKEND / ".venv" / "bin" / "python")
    if not Path(python).exists():
        print("[backend] 找不到后端虚拟环境 .venv，请先执行 make install", file=sys.stderr)
        return 2

    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    print(f"[backend] 启动临时服务 {base_url} ...")
    proc = subprocess.Popen(
        [python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(BACKEND),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        try:
            wait_ready(base_url, proc)
        except Exception as exc:
            output = proc.stdout.read().decode("utf-8", "replace") if proc.stdout else ""
            print(output, file=sys.stderr)
            print(f"[backend] 服务启动失败（构建问题）：{exc}", file=sys.stderr)
            return 1

        reporter = Reporter()

        status, health = request("GET", f"{base_url}/api/health")
        reporter.check(status == 200 and health.get("ok") is True, "GET /api/health 返回 ok=true")
        expected_modules = len(ROUTERS)
        reporter.check(
            health.get("modules") == expected_modules,
            f"health 模块数 {health.get('modules')} == {expected_modules}",
        )

        status, overview = request("GET", f"{base_url}/api/overview")
        overview_modules = overview.get("modules") if isinstance(overview, dict) else None
        reporter.check(
            status == 200 and isinstance(overview_modules, list)
            and len(overview_modules) == expected_modules,
            "GET /api/overview 汇总全部模块",
        )

        for router_module in ROUTERS:
            prefix = router_module.router.prefix  # 形如 /api/yard
            module = prefix.rsplit("/", 1)[-1]
            print(f"[backend] 检查模块 {module}")

            status, page = request("GET", f"{base_url}{prefix}?page=1&size=20")
            reporter.check(
                status == 200 and isinstance(page.get("items"), list)
                and isinstance(page.get("total"), int),
                f"{module} 列表返回分页结构",
            )
            total = page.get("total", 0)
            reporter.check(total >= 3, f"{module} 样板数据已加载（total={total}）")

            status, detail = request("GET", f"{base_url}{prefix}/1")
            reporter.check(status == 200 and detail.get("id") == 1, f"{module} 明细 /1 可读")

            status, _ = request("GET", f"{base_url}{prefix}/999999")
            reporter.check(status == 404, f"{module} 不存在的 id 返回 404")

            status, missing_result = request("POST", f"{base_url}{prefix}", {"values": {}})
            reporter.check(
                status == 200 and missing_result.get("ok") is False,
                f"{module} 缺必填字段时 ok=false",
            )

            service_module = __import__(f"app.services.{module}", fromlist=["x"])
            required = service_module.REQUIRED_FIELDS
            action_rules = service_module.ACTION_RULES
            status_order = service_module.STATUS_ORDER

            create_values = {field: f"自检-{field}" for field in required}
            status, created = request("POST", f"{base_url}{prefix}", {"values": create_values})
            new_id = (created.get("entry") or {}).get("id") if status == 200 else None
            reporter.check(
                status == 200 and created.get("ok") is True and isinstance(new_id, int),
                f"{module} 合法字段创建成功",
            )

            if isinstance(new_id, int):
                action_name, target_status = next(iter(action_rules.items()))
                status, rejected = request(
                    "POST", f"{base_url}{prefix}/{new_id}/actions", {"values": {"action": "不存在的动作"}}
                )
                reporter.check(
                    status == 200 and rejected.get("ok") is False,
                    f"{module} 非法动作被拦截",
                )
                status, acted = request(
                    "POST", f"{base_url}{prefix}/{new_id}/actions",
                    {"values": {"action": action_name}},
                )
                reporter.check(
                    status == 200 and acted.get("ok") is True
                    and (acted.get("entry") or {}).get("status") == target_status
                    and target_status in status_order,
                    f"{module} 动作「{action_name}」后状态流转到 {target_status}",
                )

            status, exported = request("GET", f"{base_url}{prefix}/export")
            reporter.check(
                status == 200 and exported.get("total") is not None
                and exported["total"] >= total,
                f"{module} 导出 total={exported.get('total')}",
            )

        print(f"\n[backend] 共 {reporter.checks} 项检查")
        if reporter.failures:
            print(f"[backend] {len(reporter.failures)} 项失败（后端构建/接口问题）：", file=sys.stderr)
            for failure in reporter.failures:
                print(f"  - {failure}", file=sys.stderr)
            return 1
        print("[backend] 全部接口自检通过")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


if __name__ == "__main__":
    raise SystemExit(main())
