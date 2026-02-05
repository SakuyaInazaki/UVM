# 售货机数据逆向工程技术方案

## 法律与道德边界

✅ **允许的用途**：
- 学术研究
- 个人学习
- 安全研究
- 互操作性开发

❌ **不允许的用途**：
- 商业竞争
- 大规模爬取影响服务
- 窃取商业机密
- 转售数据

---

## 逆向目标分析

### 1. 友宝App

**为什么选择友宝**：
- 市场份额最大（10万+台设备）
- 官方App可下载
- 可能包含附近设备查找功能

**有价值的数据**：
- 设备位置
- 设备状态（在线/离线）
- 商品列表
- 可能的价格信息

### 2. 美团/大众点评App

**数据类型**：
- 商家信息
- 用户评价
- 评分数据

**挑战**：
- 加密和签名机制
- 设备指纹检测
- 频繁的API变更

---

## 工具准备

### 抓包工具

| 工具 | 平台 | 特点 |
|------|------|------|
| **Charles Proxy** | Win/Mac | 图形界面，易用 |
| **mitmproxy** | 跨平台 | 命令行，可脚本化 |
| **Frida** | 跨平台 | 动态插桩，最强大 |

### 安装命令

```bash
# macOS
brew install mitmproxy

# Python依赖
pip install frida frida-tools mitmproxy

# Charles需要手动下载
# https://www.charlesproxy.com/download/
```

---

## 逆向步骤

### ��骤1：环境搭建

```bash
# 1. 安装mitmproxy证书
mitmproxy

# 2. 手机配置代理（与电脑同一WiFi）
# 代理地址：电脑IP:8080

# 3. 访问 http://mitm.it 安装证书
```

### 步骤2：抓包分析

```bash
# 启动mitmproxy
mitmproxy -s capture.py

# 或启动web界面
mitmweb -s capture.py
```

**capture.py 示例**：
```python
from mitmproxy import http

def request(flow: http.HTTPFlow) -> None:
    # 记录所有请求
    if "ubox" in flow.request.pretty_host.lower():
        print(f"[友宝] {flow.request.method} {flow.request.path}")

def response(flow: http.HTTPFlow) -> None:
    # 记录响应
    if "ubox" in flow.request.pretty_host.lower():
        # 保存响应数据
        with open("ubox_api.json", "a") as f:
            f.write(flow.response.text + "\n")
```

### 步骤3：API分析

找到关键API后，分析：
1. 请求参数（必要参数、签名算法）
2. 响应格式（JSON结构）
3. 认证方式（Token、Cookie）

---

## Frida动态分析

### Hook网络请求

```javascript
// Android Hook脚本
Java.perform(function() {
    // Hook OkHttp3
    var OkHttpClient = Java.use("okhttp3.OkHttpClient");
    OkHttpClient.newCall.implementation = function(request) {
        console.log("[OkHttp] URL: " + request.url().toString());
        console.log("[OkHttp] Headers: " + request.headers().toString());
        return this.newCall(request);
    };
    
    // Hook加密类
    try {
        var Crypto = Java.use("java.security.Signature");
        Crypto.update.overload('[B').implementation = function(data) {
            console.log("[加密] 输入: " + bytesToString(data));
            return this.update(data);
        };
    } catch(e) {}
});
```

### 使用方法

```bash
# 启动Frida服务（手机上需要frida-server）
frida -U -f com.ubox.app -l hook.js --no-pause

# 或附加到运行中的进程
frida -U com.ubox.app -l hook.js
```

---

## 美团逆向难点

### 1. 请求签名

美团使用复杂的签名算法：
```
sign = MD5(timestamp + nonce + secret + params)
```

需要逆向找到secret生成逻辑。

### 2. 设备指纹

```javascript
// 设备指纹包含
{
    "imei": "...",
    "oaid": "...",
    "android_id": "...",
    "device_id": "..."
}
```

解决方案：使用真实设备+Xposed模块伪装。

### 3. 加密通信

部分API使用AES/DES加密，需要：
1. 找到密钥
2. 解密响应
3. 重新加密请求

---

## 实用脚本

### mitmproxy自动保存脚本

```python
#!/usr/bin/env python3
"""
自动保存友宝API响应
"""
import json
from mitmproxy import http
from pathlib import Path

OUTPUT_DIR = Path("data/captured")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def response(flow: http.HTTPFlow) -> None:
    host = flow.request.pretty_host.lower()
    
    # 友宝相关API
    if "ubox" in host or "友宝" in flow.request.text:
        save_api("ubox", flow)
    
    # 美团相关API
    elif "meituan" in host or "dianping" in host:
        save_api("meituan", flow)

def save_api(source: str, flow: http.HTTPFlow):
    """保存API数据"""
    try:
        data = {
            "url": flow.request.url,
            "method": flow.request.method,
            "headers": dict(flow.request.headers),
            "request_body": flow.request.text,
            "response": flow.response.text,
            "status": flow.response.status_code,
        }
        
        timestamp = int(flow.response.timestamp_start)
        filename = OUTPUT_DIR / f"{source}_{timestamp}.json"
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"[保存] {filename}")
        
    except Exception as e:
        print(f"[错误] {e}")
```

### Python模拟请求脚本

```python
#!/usr/bin/env python3
"""
基于抓包数据分析后，模拟API请求
"""
import hashlib
import time
import requests

class UboxAPI:
    """友宝API模拟器"""
    
    def __init__(self):
        self.base_url = "https://api.ubox.cn"
        self.session = requests.Session()
        # 这里需要填入从抓包获取的真实token和设备信息
        self.device_id = "从抓包获取"
        self.token = "从抓包获取"
    
    def generate_sign(self, params):
        """生成签名（需要逆向分析得出）"""
        # 示例：MD5(params + timestamp + secret)
        secret = "从逆向得出"
        timestamp = int(time.time())
        sign_str = f"{params}{timestamp}{secret}"
        return hashlib.md5(sign_str.encode()).hexdigest()
    
    def get_nearby_devices(self, lat, lng, radius=1000):
        """获取附近设备"""
        params = {
            "lat": lat,
            "lng": lng,
            "radius": radius,
            "device_id": self.device_id,
        }
        
        headers = {
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "UboxApp/1.0.0",
        }
        
        response = self.session.get(
            f"{self.base_url}/v1/device/nearby",
            params=params,
            headers=headers
        )
        
        return response.json()

# 使用示例
api = UboxAPI()
devices = api.get_nearby_devices(39.9042, 116.4074)  # 北京天安门
print(devices)
```

---

## 实战流程

### 第一天：抓包分析
```bash
# 1. 启动mitmproxy
mitmweb -s capture.py

# 2. 打开友宝App，操作：
#    - 定位权限允许
#    - 查看附近设备
#    - 点击设备详情

# 3. 分析捕获的API
#    - 找到设备列表API
#    - 分析请求参数
#    - 找出签名算法
```

### 第二天：逆向签名
```bash
# 1. 使用JADX反编译APK
#    下载: https://github.com/skylot/jadx

# 2. 搜索关键代码
#    - 搜索"sign"、"signature"
#    - 搜索加密相关类

# 3. 使用Frida Hook验证
frida -U -f com.ubox.app -l sign_hook.js
```

### 第三天：编写爬虫
```python
# 基于分析结果，编写Python爬虫
# 模拟API请求获取数据
```

---

## 参考资源

### 工具下载
- **JADX**: https://github.com/skylot/jadx
- **Frida**: https://frida.re/docs/
- **mitmproxy**: https://docs.mitmproxy.org/
- **Charles**: https://www.charlesproxy.com/

### 学习资料
- Frida官方文档
- Android逆向入门教程
- 抓包实战教程

---

*作者: UVM Research Team*
*最后更新: 2026-02-04*
