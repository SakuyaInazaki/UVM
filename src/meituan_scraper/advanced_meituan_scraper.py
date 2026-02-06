"""
美团丰e足食售货机高级爬虫

通过拦截网络请求获取真正的API接口数据

作者: UVM Research Team
"""

import asyncio
import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Set
from urllib.parse import quote

from playwright.async_api import async_playwright, Page, Request


CONFIG = {
    "keywords": ["自动售货机", "丰e足食"],
    "city": "北京",
    "output_dir": "data/raw",
    "output_file": "fenge_zushi_machines.csv",
    "headless": False,  # 需要手动登录
}


class MeituanAPIInterceptor:
    """美团API拦截器"""

    def __init__(self, config: Dict):
        self.config = config
        self.output_path = Path(config["output_dir"]) / config["output_file"]
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.api_calls = []  # 存储拦截到的API调用
        self.seen = set()
        self._init_csv()

    def _init_csv(self):
        if not self.output_path.exists() or self.output_path.stat().st_size == 0:
            with open(self.output_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "id", "name", "address", "district", "lng", "lat",
                    "distance", "category", "business_hours", "url",
                    "source", "crawl_time"
                ])
            print(f"✓ 创建文件: {self.output_path}")

    def is_valid_name(self, name: str) -> bool:
        if not name:
            return False
        invalid = ['undefined', 'null', 'function', '<', '>', 'class=', 'data-']
        for p in invalid:
            if p in name:
                return False
        if len(name) < 3 or len(name) > 100:
            return False
        return True

    def save_machine(self, machine: Dict) -> bool:
        name = machine.get("name", "").strip()
        name = re.sub(r'\s+', ' ', name)

        if not self.is_valid_name(name):
            return False

        key = f"{name}_{machine.get('lng', '')}_{machine.get('lat', '')}"
        if key in self.seen:
            return False
        self.seen.add(key)

        with open(self.output_path, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([
                machine.get("id", ""),
                name,
                machine.get("address", ""),
                machine.get("district", ""),
                machine.get("lng", ""),
                machine.get("lat", ""),
                machine.get("distance", ""),
                machine.get("category", ""),
                machine.get("business_hours", ""),
                machine.get("url", ""),
                "美团",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ])

        return True

    def parse_api_response(self, response_data: Dict) -> List[Dict]:
        """解析API响应数据"""
        machines = []

        try:
            # 美团API可能返回的数据结构
            # 尝试多种可能的路径
            data_paths = [
                response_data.get("data", {}),
                response_data.get("result", {}),
                response_data.get("poiList", []),
                response_data.get("list", []),
                response_data.get("items", []),
                response_data,
            ]

            for data in data_paths:
                if isinstance(data, dict):
                    # 查找可能包含POI列表的key
                    for key in ["poiList", "list", "items", "pois", "data", "poilist"]:
                        if key in data:
                            items = data[key]
                            if isinstance(items, list):
                                for item in items:
                                    machine = self._parse_poi_item(item)
                                    if machine:
                                        machines.append(machine)
                elif isinstance(data, list):
                    for item in data:
                        machine = self._parse_poi_item(item)
                        if machine:
                            machines.append(machine)

        except Exception as e:
            print(f"    解析错误: {e}")

        return machines

    def _parse_poi_item(self, item: Dict) -> Dict:
        """解析单个POI项"""
        try:
            # 尝试多种可能的字段名
            name = (item.get("name") or item.get("poiName") or
                   item.get("title") or item.get("shopName") or "")

            if not self.is_valid_name(name):
                return None

            # 位置
            lng = (item.get("lng") or item.get("longitude") or
                  item.get("lon") or "")
            lat = (item.get("lat") or item.get("latitude") or "")

            # 地址
            address = (item.get("address") or item.get("addr") or
                      item.get("location") or "")

            # 区域
            district = (item.get("district") or item.get("area") or
                       item.get("region") or "")

            # 距离
            distance = (item.get("distance") or item.get("dist") or "")

            # ID
            machine_id = (item.get("id") or item.get("poiId") or
                         item.get("shopId") or "")

            # URL
            url = (item.get("url") or item.get("link") or
                   item.get("href") or "")

            # 分类
            category = (item.get("category") or item.get("cate") or
                       item.get("type") or "")

            # 营业时间
            hours = (item.get("businessHours") or item.get("openTime") or
                    item.get("hours") or "")

            return {
                "id": machine_id,
                "name": name,
                "address": address,
                "district": district,
                "lng": str(lng) if lng else "",
                "lat": str(lat) if lat else "",
                "distance": str(distance) if distance else "",
                "category": category,
                "business_hours": hours,
                "url": url
            }

        except Exception as e:
            return None

    async def run(self):
        """运行爬虫"""
        print("=" * 70)
        print("美团丰e足食数据采集 - API拦截模式")
        print("=" * 70)
        print("\n提示：首次运行需要手动登录美团账号")
        print("启动后会自动打开浏览器，请在浏览器中完成登录")
        print("登录完成后按回车继续...\n")

        async with async_playwright() as p:
            # 存储拦截的请求
            captured_requests = []
            captured_responses = []

            def handle_request(request: Request):
                """处理请求"""
                url = request.url
                # 记录可能包含POI数据的请求
                if any(k in url for k in ["poi", "search", "query", "api"]):
                    captured_requests.append({
                        "url": url,
                        "method": request.method,  # 属性，不是方法
                        "headers": request.headers,
                    })

            browser = await p.chromium.launch_persistent_context(
                user_data_dir="/tmp/meituan_advanced_scraper",
                headless=self.config["headless"],
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-web-security',  # 允许跨域
                ],
                viewport={"width": 1440, "height": 900},
                locale="zh-CN",
            )

            page = browser.pages[0] if browser.pages else await browser.new_page()

            # 设置请求拦截
            page.on("request", handle_request)

            try:
                # 首先访问美团首页
                print("[1] 访问美团首页...")
                await page.goto("https://www.meituan.com/", timeout=30000)
                await asyncio.sleep(3)

                print("  页面已加载，请确认登录状态")
                print("  如果未登录，请在浏览器中手动登录")
                print("  登录完成后按回车继续...")
                input()

                # 访问搜索页面
                for keyword in self.config["keywords"]:
                    print(f"\n[2] 搜索关键词: {keyword}")

                    # 尝试多种URL格式
                    urls = [
                        f"https://www.meituan.com/s/{quote(keyword)}/",
                        f"https://www.meituan.com/s/{quote(keyword)}/?city={self.config['city']}",
                        f"https://www.meituan.cn/s/{quote(keyword)}/",
                        f"https://i.meituan.com/s/{quote(keyword)}/",
                    ]

                    for url in urls:
                        try:
                            print(f"  尝试: {url}")

                            # 清空之前的请求数据
                            captured_requests.clear()

                            await page.goto(url, wait_until="networkidle", timeout=60000)

                            # 等待动态内容加载
                            await asyncio.sleep(5)

                            # 尝试从页面中提取数据
                            machines = await self._extract_from_page(page)

                            print(f"    提取到 {len(machines)} 条结果")

                            for machine in machines:
                                if self.save_machine(machine):
                                    print(f"      ✓ {machine['name'][:50]}")

                            # 打印拦截到的API请求（用于调试）
                            if captured_requests:
                                print(f"    拦截到 {len(captured_requests)} 个API请求")
                                for req in captured_requests[:3]:  # 只显示前3个
                                    print(f"      - {req['url'][:100]}")

                            if machines:
                                break  # 如果获取到数据，不再尝试其他URL

                            await asyncio.sleep(2)

                        except Exception as e:
                            print(f"    失败: {e}")
                            continue

            finally:
                print(f"\n{'=' * 70}")
                print(f"采集完成！共获取 {len(self.seen)} 条数据")
                print(f"数据保存在: {self.output_path}")
                await asyncio.sleep(2)
                await browser.close()

    async def _extract_from_page(self, page: Page) -> List[Dict]:
        """从页面提取数据"""
        machines = []

        try:
            # 方法1: 查找页面中的JSON数据
            js1 = """() => {
                const results = [];

                // 查找script标签中的JSON数据
                const scripts = document.querySelectorAll('script');
                for (const script of scripts) {
                    const text = script.textContent || '';
                    try {
                        // 尝试解析JSON
                        if (text.includes('poi') || text.includes('shop') ||
                            text.includes('data') || text.includes('list')) {
                            // 尝试提取JSON对象
                            const matches = text.match(/\\{[^{}]*"[^"]*poi[^"]*"[^{}]*\\}/g) ||
                                           text.match(/\\{[^{}]*"[^"]*shop[^"]*"[^{}]*\\}/g);
                            if (matches) {
                                results.push(...matches);
                            }
                        }
                    } catch(e) {}
                }

                return results.slice(0, 10);
            }"""
            json_strings = await page.evaluate(js1)

            for json_str in json_strings:
                try:
                    data = json.loads(json_str)
                    parsed = self.parse_api_response(data)
                    machines.extend(parsed)
                except:
                    pass

            # 方法2: 查找DOM中的POI元素
            js2 = """() => {
                const results = [];

                // 查找可能的POI容器
                const containers = document.querySelectorAll('[class*="poi"], [class*="shop"], [class*="item"], [class*="list"]');

                for (const container of containers) {
                    const text = container.textContent || '';
                    if (text.length < 50) continue;  // 跳过太短的

                    // 尝试提取名称和地址
                    const nameEl = container.querySelector('[class*="name"], [class*="title"], h1, h2, h3, h4');
                    const addrEl = container.querySelector('[class*="addr"], [class*="address"]');

                    if (nameEl) {
                        const name = nameEl.textContent?.trim() || '';
                        const address = addrEl?.textContent?.trim() || '';

                        if (name.length >= 3 && name.length <= 100) {
                            results.push({
                                name: name,
                                address: address
                            });
                        }
                    }
                }

                return results.slice(0, 30);
            }"""
            dom_results = await page.evaluate(js2)

            for item in dom_results:
                if self.is_valid_name(item.get("name", "")):
                    machines.append(item)

            # 方法3: 查找所有链接
            js3 = """() => {
                const results = [];
                const links = document.querySelectorAll('a[href]');

                for (const link of links) {
                    const href = link.href || '';
                    const text = link.textContent?.trim() || '';

                    if (href.includes('/shop/') || href.includes('/store/') ||
                        href.includes('/poi/')) {
                        if (text.length >= 3 && text.length <= 100) {
                            results.push({
                                id: href.split('/').pop() || '',
                                name: text,
                                url: href
                            });
                        }
                    }
                }

                return results.slice(0, 50);
            }"""
            link_results = await page.evaluate(js3)

            for item in link_results:
                machines.append(item)

        except Exception as e:
            print(f"    提取错误: {e}")

        # 去重
        seen_names = set()
        unique_machines = []
        for m in machines:
            name = m.get("name", "")
            if name and name not in seen_names:
                seen_names.add(name)
                unique_machines.append(m)

        return unique_machines


async def main():
    interceptor = MeituanAPIInterceptor(CONFIG)
    await interceptor.run()


if __name__ == "__main__":
    asyncio.run(main())
