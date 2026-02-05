"""
友宝API抓包脚本
自动保存所有友宝相关的API请求和响应

使用方法：
1. 启动 mitmproxy: mitmweb -s capture_ubox.py
2. 手机配置代理，打开友宝App
3. 查看抓取的数据: ls -la ../data/ubox_captured/
"""
import json
import os
from datetime import datetime
from mitmproxy import http

# 输出目录
OUTPUT_DIR = "../data/ubox_captured"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def request(flow: http.HTTPFlow) -> None:
    """记录所有请求"""
    host = flow.request.pretty_host.lower()

    # 友宝相关域名
    if any(keyword in host for keyword in ["ubox", "uboxol", "u-box"]):
        print(f"[请求] {flow.request.method} {flow.request.url}")

def response(flow: http.HTTPFlow) -> None:
    """保存友宝API响应"""
    host = flow.request.pretty_host.lower()

    # 判断是否是友宝API
    is_ubox = any(keyword in host for keyword in ["ubox", "uboxol", "u-box"])

    # 也检查请求路径
    path = flow.request.path.lower()
    is_ubox = is_ubox or any(keyword in path for keyword in [
        "vending", "machine", "device", "nearby", "location"
    ])

    if is_ubox:
        save_api_data(flow)

def save_api_data(flow: http.HTTPFlow):
    """保存API数据到文件"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

        data = {
            "timestamp": timestamp,
            "url": flow.request.url,
            "method": flow.request.method,
            "host": flow.request.pretty_host,
            "path": flow.request.path,
            "request_headers": dict(flow.request.headers),
            "request_body": flow.request.text,
            "response_status": flow.response.status_code,
            "response_headers": dict(flow.response.headers),
            "response_body": flow.response.text,
        }

        # 保存
        filename = f"{OUTPUT_DIR}/ubox_{timestamp}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"[保存] {filename}")
        print(f"  └─ {flow.request.method} {flow.request.path}")

    except Exception as e:
        print(f"[错误] {e}")
