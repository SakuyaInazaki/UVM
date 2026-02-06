"""
美团网络请求拦截器

通过拦截网络请求找到真实的API接口

作者: UVM Research Team
"""

import asyncio
import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Set
from urllib.parse import quote, parse_qs, urlparse

from playwright.async_api import async_playwright


CONFIG = {
    "keyword": "自动售货机",
    "output_dir": "data/raw",
    "output_file": "fenge_zushi_machines.csv",
    "headless": False,
}


class MeituanNetworkInterceptor:
    """美团网络拦截器"""

    def __init__(self, config: Dict):
        self.config = config
        self.output_path = Path(config["output_dir"]) / config["output_file"]
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.seen = set()
        self.api_responses = []  # 存储拦截的API响应
        self._init_csv()

    def _init_csv(self):
        if not self.output_path.exists() or self.output_path.stat().st_size == 0:
            with open(self.output_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "id", "name", "address", "district", "lng", "lat",
                    "distance", "category", "url", "source", "crawl_time"
                ])
            print(f"✓ 创建文件: {self.output_path}")

    def is_valid_name(self, name: str) -> bool:
        if not name:
            return False
        invalid = ['undefined', 'null', 'function', '<', '>', 'class=',
                   '投诉', '客服', '客服电话', '邮箱', 'protocol']
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
                machine.get("url", ""),
                "美团API",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ])

        return True

    def parse_api_data(self, data) -> List[Dict]:
        """解析API数据"""
        machines = []

        try:
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except:
                    return []

            if isinstance(data, dict):
                # 查找可能包含POI列表的key
                for key in ["data", "result", "list", "items", "pois", "poiList", "shopList", "shopInfo"]:
                    if key in data:
                        value = data[key]
                        if isinstance(value, list):
                            for item in value:
                                machine = self._parse_item(item)
                                if machine:
                                    machines.append(machine)
                        elif isinstance(value, dict):
                            # 递归处理
                            sub_machines = self.parse_api_data(value)
                            machines.extend(sub_machines)

                # 尝试直接解析当前层级
                if "name" in data and self.is_valid_name(data.get("name", "")):
                    machine = self._parse_item(data)
                    if machine:
                        machines.append(machine)

            elif isinstance(data, list):
                for item in data:
                    sub_machines = self.parse_api_data(item)
                    machines.extend(sub_machines)

        except Exception as e:
            print(f"    解析API数据错误: {e}")

        return machines

    def _parse_item(self, item: Dict) -> Dict:
        """解析单个POI项"""
        if not isinstance(item, dict):
            return None

        # 尝试多种可能的字段名
        name = (item.get("name") or item.get("poiName") or
               item.get("title") or item.get("shopName") or
               item.get("storeName") or "")

        if not self.is_valid_name(name):
            return None

        lng = (item.get("lng") or item.get("longitude") or
              item.get("lon") or item.get("long") or "")
        lat = (item.get("lat") or item.get("latitude") or "")

        address = (item.get("address") or item.get("addr") or
                  item.get("location") or item.get("addressText") or "")

        district = (item.get("district") or item.get("area") or
                   item.get("region") or item.get("cityname") or "")

        distance = (item.get("distance") or item.get("dist") or "")

        machine_id = (item.get("id") or item.get("poiId") or
                     item.get("shopId") or item.get("storeId") or "")

        url = (item.get("url") or item.get("link") or
               item.get("href") or item.get("shopUrl") or "")

        category = (item.get("category") or item.get("cate") or
                   item.get("type") or item.get("shopType") or "")

        return {
            "id": str(machine_id) if machine_id else "",
            "name": name,
            "address": address,
            "district": district,
            "lng": str(lng) if lng else "",
            "lat": str(lat) if lat else "",
            "distance": str(distance) if distance else "",
            "category": category,
            "url": url
        }

    async def run(self):
        """运行拦截器"""
        print("=" * 70)
        print("美团网络请求拦截器")
        print("=" * 70)
        print("\n正在访问美团搜索页面并拦截API请求...\n")

        async with async_playwright() as p:
            # 存储拦截的响应
            captured_responses = []

            browser = await p.chromium.launch_persistent_context(
                user_data_dir="/tmp/meituan_interceptor",
                headless=self.config["headless"],
                args=[
                    '--disable-blink-features=AutomationControlled',
                ],
                viewport={"width": 1440, "height": 900},
                locale="zh-CN",
            )

            page = browser.pages[0] if browser.pages else await browser.new_page()

            # 设置响应拦截
            def handle_response(response):
                try:
                    url = response.url
                    # 只记录可能包含POI数据的API响应
                    if any(k in url for k in ["api", "search", "poi", "query", "list", "shop"]):
                        content_type = response.headers.get("content-type", "")
                        if "json" in content_type or "api" in url:
                            captured_responses.append({
                                "url": url,
                                "status": response.status,
                                "headers": response.headers,
                                "data": None  # 稍后获取
                            })
                except:
                    pass

            page.on("response", handle_response)

            try:
                # 访问搜索页面
                keyword = self.config["keyword"]
                url = f"https://www.meituan.com/s/{quote(keyword)}/"

                print(f"[1] 访问: {url}")
                await page.goto(url, wait_until="networkidle", timeout=60000)

                print("  等待页面加载...")
                await asyncio.sleep(5)

                # 获取页面上所有的XHR/fetch请求
                api_data = await page.evaluate("""() => {
                    const results = [];

                    // 尝试从window对象中获取数据
                    if (window.__INITIAL_STATE__) {
                        results.push(window.__INITIAL_STATE__);
                    }
                    if (window.appState) {
                        results.push(window.appState);
                    }
                    if (window.store) {
                        results.push(window.store);
                    }

                    // 查找script标签中的JSON数据
                    const scripts = document.querySelectorAll('script[type="application/json"]');
                    scripts.forEach(script => {
                        try {
                            results.push(JSON.parse(script.textContent));
                        } catch(e) {}
                    });

                    return results;
                }""")

                print(f"  从页面获取到 {len(api_data)} 条数据")

                # 解析数据
                total_machines = 0
                for data in api_data:
                    machines = self.parse_api_data(data)
                    for machine in machines:
                        if self.save_machine(machine):
                            total_machines += 1
                            print(f"    ✓ {machine['name'][:50]}")

                # 尝试直接从DOM提取
                dom_data = await page.evaluate("""() => {
                    const results = [];
                    const seen = new Set();

                    // 查找所有包含shop/poi的元素
                    const elements = document.querySelectorAll('[data-shop-id], [data-poi-id], [class*="shop"], [class*="poi"]');

                    elements.forEach(el => {
                        const dataset = el.dataset || {};
                        const text = el.textContent?.trim() || '';

                        if (text && text.length >= 3 && text.length < 100) {
                            // 查找ID
                            const id = dataset.shopId || dataset.poiId || dataset.id || '';

                            // 查找链接
                            const link = el.querySelector('a');
                            const href = link?.href || el.href || '';

                            if (id || href.includes('/shop/')) {
                                if (!seen.has(text)) {
                                    seen.add(text);
                                    results.push({
                                        id: id,
                                        name: text,
                                        url: href
                                    });
                                }
                            }
                        }
                    });

                    return results;
                }""")

                print(f"  从DOM提取到 {len(dom_data)} 条")

                for machine in dom_data:
                    if self.save_machine(machine):
                        total_machines += 1
                        print(f"    + {machine['name'][:50]}")

                # 尝试搜索关键词
                search_input = await page.query_selector('input[type="search"], input[placeholder*="搜索"]')
                if search_input:
                    print("\n[2] 尝试使用搜索框...")
                    await search_input.fill(keyword)
                    await asyncio.sleep(1)
                    await page.keyboard.press("Enter")
                    await asyncio.sleep(5)

                    # 再次提取
                    api_data2 = await page.evaluate("""() => {
                        const results = [];

                        // 查找所有结果项
                        const items = document.querySelectorAll('[class*="item"], [class*="card"], [class*="poi"]');

                        items.forEach(item => {
                            const nameEl = item.querySelector('[class*="name"]');
                            const addrEl = item.querySelector('[class*="addr"]');

                            if (nameEl) {
                                const name = nameEl.textContent?.trim() || '';
                                const address = addrEl?.textContent?.trim() || '';

                                if (name && name.length >= 3 && name.length < 100) {
                                    results.push({
                                        name: name,
                                        address: address
                                    });
                                }
                            }
                        });

                        return results.slice(0, 50);
                    }""")

                    for machine in api_data2:
                        if self.save_machine(machine):
                            total_machines += 1
                            print(f"    ✓ {machine['name'][:50]}")

            finally:
                print(f"\n{'=' * 70}")
                print(f"采集完成！共获取 {len(self.seen)} 条数据")
                print(f"数据保存在: {self.output_path}")
                await asyncio.sleep(5)
                await browser.close()


async def main():
    interceptor = MeituanNetworkInterceptor(CONFIG)
    await interceptor.run()


if __name__ == "__main__":
    asyncio.run(main())
