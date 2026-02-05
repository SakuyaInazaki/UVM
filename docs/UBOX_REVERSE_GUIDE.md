# 友宝App逆向抓包实战指南

## 前置条件

- ✅ 安卓手机一台
- ✅ 电脑（macOS/Windows/Linux）
- ✅ 手机和电脑在同一WiFi网络

---

## 第一步：安装抓包工具

### 在电脑上安装 mitmproxy

```bash
# macOS
brew install mitmproxy

# ��证安装
mitmproxy --version
```

### 在手机上安装证书

1. 启动 mitmproxy：
```bash
mitmweb
# 会自动打开浏览器 http://127.0.0.1:8081
```

2. 手机设置代理（与电脑同一WiFi）：
- **代理地址**：电脑的IP地址
- **端口**：8080

3. 手机浏览器访问：`http://mitm.it`
- 选择 Android 图标
- 下载并安装证书

4. **信任证书**（安卓11+需要）：
```
设置 → 安全 → 加密与凭据 → 受信任的凭据 → 用户
找到 mitmproxy 证书并启用
```

---

## 第二步：编写抓包脚本

创建 `capture_ubox.py`：

```python
"""
友宝API抓包脚本
自动保存所有友宝相关的API请求和响应
"""
import json
import os
from datetime import datetime
from mitmproxy import http

# 输出目录
OUTPUT_DIR = "data/ubox_captured"
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
```

---

## 第三步：开始抓包

### 1. 启动带脚本的 mitmproxy

```bash
cd /Users/sakimi/Desktop/UVM_sakimi
mitmweb -s docs/capture_ubox.py
```

### 2. 手机操作友宝App

打开友宝App，执行以下操作：
- ✅ 允许定位权限
- ✅ 点击"附近的售货机"或类似功能
- ✅ 移动地图，查看不同区域的设备
- ✅ 点击某个设备查看详情
- ✅ 尝试扫码功能（如果有）

### 3. 观察抓包结果

在 mitmweb 界面中：
- 查看是否有 `ubox` 或 `uboxol` 相关的请求
- 找到返回设备列表的 API
- 记录请求参数和响应格式

---

## 第四步：分析API

抓包后，检查 `data/ubox_captured/` 目录：

```bash
# 查看抓取到的文件
ls -la data/ubox_captured/

# 分析API结构
cat data/ubox_captured/ubox_*.json | jq '.url, .request_body, .response_body' | less
```

### 关键API识别

寻找类似这样的接口：
```
GET /api/v1/device/nearby?lat=39.9&lng=116.4&radius=1000
GET /api/v1/machine/list?bounds=...
POST /api/v1/location/search
```

---

## 第五步：模拟API请求

分析完成后，可以编写Python脚本模拟请求：

```python
"""
友宝API模拟器（需要先完成抓包分析）
"""
import requests
import hashlib
import time

class UboxAPI:
    def __init__(self):
        self.base_url = "https://api.uboxol.com"  # 从抓包获取真实URL
        self.session = requests.Session()

        # 从抓包获取的真实参数
        self.headers = {
            "User-Agent": "UboxApp/3.x.x (Android)",
            "device-id": "",  # 从抓包获取
            "token": "",      # 从抓包获取（如果需要登录）
        }

    def get_nearby_devices(self, lat, lng, radius=1000):
        """获取附近设备（参数格式需要从抓包确认）"""
        params = {
            "lat": lat,
            "lng": lng,
            "radius": radius,
            # ... 其他参数从抓包获取
        }

        response = self.session.get(
            f"{self.base_url}/device/nearby",
            params=params,
            headers=self.headers
        )

        return response.json()

# 使用示例
api = UboxAPI()
devices = api.get_nearby_devices(39.9042, 116.4074)  # 北京
print(devices)
```

---

## 常见问题

### Q1: 手机无法访问网络
**A**: 检查代理设置是否正确，电脑IP是否正确

### Q2: HTTPS请求无法解密
**A**: 确保证书已安装并信任，安卓11+需要在系统设置中手动信任

### Q3: 友宝App检测到代理，无法使用
**A**: 某些App有代理检测，可能需要：
- 使用 Frida 绕过检测
- 或者使用 root 手机 + magisk 模块

### Q4: API需要签名怎么办
**A**: 如果API有签名验证，需要：
1. 使用 JADX 反编译APK
2. 搜索签名算法代码
3. 用 Frida Hook 获取签名参数

---

## 抓包完成后

把抓取到的文件发给我分析：
```bash
cd /Users/sakimi/Desktop/UVM_sakimi
tar -czf ubox_capture.tar.gz data/ubox_captured/
```

然后分享 `ubox_capture.tar.gz`，我可以帮你：
- 分析API结构
- 识别关键接口
- 编写批量爬虫

---

*文档创建时间：2026-02-05*
