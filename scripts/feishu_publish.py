#!/usr/bin/env python3
"""
feishu_publish.py · SocietyAdvisor Phase 0 #6 飞书日报真推送模块(9/9 T5 周期)

承接 9/8 commit `fa57304` 中 scripts/run_daily_report.sh 显式预留的
"真飞书 webhook 推送"占位,把 --push-stub 升级为真 --push 形态。

飞书自定义机器人 Webhook 协议(简化版 msg_type=text):
  POST <webhook_url>
  Content-Type: application/json
  Body: {"msg_type": "text", "content": {"text": "<消息正文>"}}

退出码约定:
  0 - 推送成功(或 dry-run 正常)
  1 - 参数错误 / 必填数据缺失(--strict 触发)
  2 - 缺 curl / 缺 Python 依赖
  3 - 网络层失败(curl 自身报错 / DNS / TCP 不可达)
  4 - HTTP 4xx(认证 / 路径 / 频控)
  5 - HTTP 5xx(飞书服务端)
  6 - HTTP 非 2xx 其他(2xx 之外)

用法:
  python3 scripts/feishu_publish.py --webhook-url <URL> --text "hello"
  python3 scripts/feishu_publish.py --webhook-url <URL> --from-file .Log/日报-20260908.md
  python3 scripts/feishu_publish.py --webhook-url <URL> --from-file .Log/日报-20260908.md --dry-run
  FEISHU_WEBHOOK_URL=https://open.feishu.cn/... python3 scripts/feishu_publish.py --from-file .Log/日报-20260908.md

依赖:仅 Python 3.8+ stdlib(urllib + json + subprocess),无需 PyYAML。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

# ============== 退出码 ==============
EXIT_OK = 0
EXIT_PARAM = 1
EXIT_DEP = 2
EXIT_NET = 3
EXIT_HTTP_4XX = 4
EXIT_HTTP_5XX = 5
EXIT_HTTP_OTHER = 6

# 飞书自定义机器人 webhook 协议常量
FEISHU_MSG_TYPE = "text"
HTTP_TIMEOUT_SEC = 10  # 单次 POST 10s 超时,与 mavis cron 调度窗口兼容


# ============== 加载文本 ==============

def load_text(args: argparse.Namespace) -> tuple[str, str]:
    """
    返回 (text, source_tag) 二元组。
    source_tag 供日志/上报区分"来自文件"还是"来自 --text"。
    """
    if args.from_file:
        p = Path(args.from_file)
        if not p.exists():
            print(f"❌ --from-file 文件不存在: {p}", file=sys.stderr)
            sys.exit(EXIT_PARAM)
        body = p.read_text(encoding="utf-8")
        return body, f"file:{p}"
    if args.text:
        return args.text, "arg:--text"
    print("❌ 必须提供 --text 或 --from-file 之一", file=sys.stderr)
    sys.exit(EXIT_PARAM)


# ============== 飞书协议封装 ==============

def build_payload(text: str, title: Optional[str]) -> dict:
    """
    构造飞书自定义机器人 POST body。
    msg_type=text 形态最稳定,无 markdown 解析差异,飞书 / Lark 客户端均能直接展示。
    若 --title 给出,首行加 `【title】` 前缀,便于飞书消息列表识别日报批次。
    """
    body = text.strip()
    if title:
        body = f"【{title}】\n{body}"
    return {"msg_type": FEISHU_MSG_TYPE, "content": {"text": body}}


# ============== HTTP 投递 ==============

def post_via_urllib(url: str, payload: dict) -> tuple[int, str]:
    """
    走 stdlib urllib 投递,避免对 curl / requests 的依赖。
    返回 (http_status_code, response_body_text)。
    """
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urlrequest.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=HTTP_TIMEOUT_SEC) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except HTTPError as e:
        # HTTPError 也是返回响应体的(只是非 2xx)
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return e.code, body
    except URLError as e:
        # DNS / TCP / 拒接 等
        raise ConnectionError(f"URLError: {e.reason}") from e
    except (TimeoutError, OSError) as e:
        raise ConnectionError(f"timeout/oserror: {e}") from e


def post_via_curl(url: str, payload: dict) -> tuple[int, str, int]:
    """
    走 curl 投递(若 urllib 失败,可用此降级路径)。
    返回 (http_status_code, response_body, curl_exit_code)。
    依赖 curl 在 PATH;缺失时 raise FileNotFoundError。
    """
    if shutil.which("curl") is None:
        raise FileNotFoundError("curl not found in PATH")
    proc = subprocess.run(
        [
            "curl", "-sS",
            "-X", "POST",
            "-H", "Content-Type: application/json; charset=utf-8",
            "--max-time", str(HTTP_TIMEOUT_SEC),
            "-w", "\n__HTTP_STATUS__:%{http_code}",
            "--data-binary", "@-",  # body 从 stdin 读
            url,
        ],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
    )
    out = proc.stdout
    status = 0
    body = out
    if "__HTTP_STATUS__:" in out:
        body, _, status_str = out.rpartition("__HTTP_STATUS__:")
        try:
            status = int(status_str.strip())
        except ValueError:
            status = 0
    return status, body, proc.returncode


# ============== 主流程 ==============

def main() -> int:
    parser = argparse.ArgumentParser(
        description="SocietyAdvisor 飞书日报真推送(Phase 0 #6 9/9 补完)",
    )
    parser.add_argument(
        "--webhook-url",
        default=os.environ.get("FEISHU_WEBHOOK_URL", ""),
        help="飞书自定义机器人 webhook URL(可由环境变量 FEISHU_WEBHOOK_URL 提供)",
    )
    parser.add_argument("--text", help="直接传入消息正文")
    parser.add_argument("--from-file", help="从文件读取消息正文(配合 run_daily_report.sh)")
    parser.add_argument("--title", help="可选消息标题,首行加 【title】 前缀")
    parser.add_argument(
        "--transport",
        choices=["urllib", "curl"],
        default="urllib",
        help="HTTP 投递后端(默认 urllib 走 stdlib,curl 适合有代理 / TLS 调优的环境)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印 payload + 目标 URL,不真发(本地手测 / 9/9 周期默认使用)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="webhook-url / text / from-file 任一缺失 → exit 1(cron 通过 mavis 通知)",
    )
    args = parser.parse_args()

    # 1. 校验 webhook url
    if not args.webhook_url:
        msg = "❌ --webhook-url 缺失,可通过 --webhook-url 或环境变量 FEISHU_WEBHOOK_URL 传入"
        if args.strict:
            print(msg, file=sys.stderr)
            return EXIT_PARAM
        print(msg, file=sys.stderr)
        print("   降级为 dry-run 预览(payload 不发送)", file=sys.stderr)
        args.dry_run = True

    # 2. 加载文本
    if not args.text and not args.from_file:
        msg = "❌ --text / --from-file 至少给一个(--strict 触发 exit 1)"
        if args.strict:
            print(msg, file=sys.stderr)
            return EXIT_PARAM
        print(msg, file=sys.stderr)
        return EXIT_PARAM

    text, source = load_text(args)

    # 3. 构造 payload
    payload = build_payload(text, args.title)
    payload_bytes = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    text_len = len(text)

    if args.dry_run:
        print(f"🔍 DRY-RUN 飞书推送预览")
        print(f"   目标 webhook: {args.webhook_url or '(empty)'}")
        print(f"   文本来源: {source}")
        print(f"   文本长度: {text_len} 字符 / payload {payload_bytes} 字节")
        print(f"   msg_type: {FEISHU_MSG_TYPE}")
        if args.title:
            print(f"   标题前缀: 【{args.title}】")
        print(f"   transport: {args.transport}")
        print("--- payload preview (前 600 字符) ---")
        preview = json.dumps(payload, ensure_ascii=False, indent=2)
        print(preview[:600] + ("..." if len(preview) > 600 else ""))
        print("--- end ---")
        return EXIT_OK

    # 4. 真投递
    print(f"▶ 飞书推送: text {text_len} 字符 / {source} → {args.webhook_url[:60]}...")
    if args.transport == "urllib":
        try:
            status, body = post_via_urllib(args.webhook_url, payload)
        except ConnectionError as e:
            print(f"❌ 网络层失败: {e}", file=sys.stderr)
            return EXIT_NET
    else:
        try:
            status, body, curl_rc = post_via_curl(args.webhook_url, payload)
        except FileNotFoundError as e:
            print(f"❌ 缺 curl: {e}", file=sys.stderr)
            return EXIT_DEP
        if curl_rc != 0 and status == 0:
            print(f"❌ curl 退出码 {curl_rc},body={body[:200]}", file=sys.stderr)
            return EXIT_NET

    # 5. 评估 HTTP 状态
    print(f"   HTTP {status} · body[:200] = {body[:200]}")
    if 200 <= status < 300:
        # 飞书 200 响应体里通常含 {"StatusCode":0, "StatusMessage":"success", "Data":{...}}
        # 也可能含 {"code":..., "msg":"..."};二者都接受,只看 HTTP 状态作为基础
        try:
            j = json.loads(body)
            if isinstance(j, dict):
                inner_code = j.get("StatusCode") if "StatusCode" in j else j.get("code")
                inner_msg = j.get("StatusMessage") or j.get("msg") or ""
                if inner_code not in (0, None, "0"):
                    print(f"⚠️  HTTP 200 但飞书返回 code={inner_code} msg={inner_msg}", file=sys.stderr)
                    return EXIT_HTTP_OTHER
        except json.JSONDecodeError:
            pass  # 非 JSON 也按 HTTP 200 通过
        print(f"✅ 飞书推送成功 · {text_len} 字符")
        return EXIT_OK

    if 400 <= status < 500:
        print(f"❌ HTTP {status} (4xx): 检查 webhook URL / 频控 / 群机器人开关", file=sys.stderr)
        return EXIT_HTTP_4XX
    if 500 <= status < 600:
        print(f"❌ HTTP {status} (5xx): 飞书服务端问题,稍后重试", file=sys.stderr)
        return EXIT_HTTP_5XX
    print(f"❌ HTTP {status} (非 2xx/4xx/5xx)", file=sys.stderr)
    return EXIT_HTTP_OTHER


if __name__ == "__main__":
    sys.exit(main())
