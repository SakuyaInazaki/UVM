"""
美团丰e足食自动爬虫

自动访问搜索页面并提取数据

使用方法：
1. 先在浏览器中登录美团（使用已有的用户数据目录）
2. 运行此脚本自动采集数据

作者: UVM Research Team
"""

import asyncio
import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict
from urllib.parse import quote

from playwright.async_api import async_playwright


CONFIG = {
    "keywords": ["自动售货机", "丰e足食", "无人售货"],
    "output_dir": "data/raw",
    "output_file": "fenge_zushi_machines.csv",
    "headless": False,
    "wait_time": 5,  # 等待页面加载时间（秒）
}


class MeituanAutoScraper:
    """美团自动爬虫"""

    def __init__(self, config: Dict):
        self.config = config
        self.output_path = Path(config["output_dir"]) / config["output_file"]
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.seen = set()
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
        invalid = ['undefined', 'null', 'function', '<', '>', 'class=', 'data-',
                   '美团', '更多', '查看', 'transform', 'window', 'document']
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
                "美团",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ])

        return True

    async def extract_from_page(self, page) -> List[Dict]:
        """从页面提取数据"""
        machines = []

        # 等待页面加载
        await asyncio.sleep(self.config["wait_time"])

        # 尝试多种提取方法
        js_code = """() => {
            const results = [];
            const seen = new Set();

            // 方法1: 查找所有文本，尝试识别POI模式
            const allText = document.body.innerText;

            // 按行分割
            const lines = allText.split('\\n').map(l => l.trim()).filter(l => l.length > 0);

            // 查找可能POI的行（包含地址特征的）
            for (let i = 0; i < lines.length; i++) {
                const line = lines[i];

                // 跳过明显不是POI的行
                if (line.length < 3 || line.length > 200) continue;
                if (line.includes('美团') || line.includes('更多') || line.includes('登录')) continue;
                if (line.includes('客服') || line.includes('反馈') || line.includes('协议')) continue;

                // 查找地址特征
                const hasAddress = line.includes('区') || line.includes('路') ||
                                  line.includes('街') || line.includes('号') ||
                                  line.includes('楼') || line.includes('大厦') ||
                                  line.includes('中心') || line.includes('广场');

                if (hasAddress || line.length > 20) {
                    // 前一行可能是名称
                    if (i > 0 && lines[i-1].length >= 3 && lines[i-1].length < 50) {
                        const name = lines[i-1];
                        const address = line;

                        // 验证名称
                        if (!name.includes('区') && !name.includes('路') &&
                            !seen.has(name + address)) {
                            seen.add(name + address);
                            results.push({
                                name: name,
                                address: address
                            });
                        }
                    }
                }
            }

            // 方法2: 查找链接
            const links = document.querySelectorAll('a[href]');
            for (const link of links) {
                const href = link.href || '';
                const text = link.textContent?.trim() || '';

                if (text.length >= 3 && text.length < 100) {
                    if (href.includes('/shop/') || href.includes('/store/')) {
                        if (!seen.has(text)) {
                            seen.add(text);
                            results.push({
                                id: href.split('/').pop(),
                                name: text,
                                url: href
                            });
                        }
                    }
                }
            }

            // 方法3: 查找JSON数据
            const scripts = document.querySelectorAll('script');
            for (const script of scripts) {
                const text = script.textContent || '';
                try {
                    // 查找包含poi/shop的JSON
                    if (text.includes('poi') || text.includes('shop')) {
                        // 尝试提取JSON对象
                        const regex = /\\{[^{}]*"name"\\s*:\\s*"[^"]+"[^{}]*\\}/g;
                        const matches = text.match(regex);
                        if (matches) {
                            for (const match of matches) {
                                try {
                                    const obj = JSON.parse(match);
                                    if (obj.name && !seen.has(obj.name)) {
                                        seen.add(obj.name);
                                        results.push({
                                            name: obj.name,
                                            address: obj.address || '',
                                            lng: obj.lng || obj.longitude || '',
                                            lat: obj.lat || obj.latitude || ''
                                        });
                                    }
                                } catch(e) {}
                            }
                        }
                    }
                } catch(e) {}
            }

            return results.slice(0, 100);
        }"""

        try:
            extracted = await page.evaluate(js_code)
            machines = extracted or []
        except Exception as e:
            print(f"    提取错误: {e}")

        return machines

    async def run(self):
        """运行爬虫"""
        print("=" * 70)
        print("美团丰e足食自动爬虫")
        print("=" * 70)
        print("\n提示：如果未登录，爬虫会自动打开浏览器等待您登录")
        print("      程序会在搜索时自动等待页面加载\n")

        async with async_playwright() as p:
            browser = await p.chromium.launch_persistent_context(
                user_data_dir="/tmp/meituan_auto_scraper",
                headless=self.config["headless"],
                args=['--disable-blink-features=AutomationControlled'],
                viewport={"width": 1440, "height": 900},
                locale="zh-CN",
            )

            page = browser.pages[0] if browser.pages else await browser.new_page()

            try:
                # 首先访问美团首页
                print("[1] 访问美团首页...")
                await page.goto("https://www.meituan.com/", timeout=30000)
                await asyncio.sleep(3)

                # 检查登录状态
                logged_in = await page.evaluate("""() => {
                    const loginBtn = document.querySelector('.login-btn, [class*="login"]');
                    return !loginBtn || !loginBtn.textContent.includes('登录');
                }""")

                if not logged_in:
                    print("  ! 检测到未登录状态")
                    print("  请在浏览器中完成登录（30秒后自动继续）")
                    print("  如需更多时间，请按Ctrl+C停止后重新运行")
                    await asyncio.sleep(30)
                else:
                    print("  ✓ 已登录")

                # 搜索关键词
                for keyword in self.config["keywords"]:
                    print(f"\n[2] 搜索: {keyword}")

                    # 尝试不同的URL格式
                    urls = [
                        f"https://www.meituan.com/s/{quote(keyword)}/",
                    ]

                    for url in urls:
                        try:
                            print(f"  访问: {url[:60]}...")
                            await page.goto(url, wait_until="domcontentloaded", timeout=60000)

                            # 等待动态内容
                            await asyncio.sleep(self.config["wait_time"])

                            # 提取数据
                            machines = await self.extract_from_page(page)

                            if machines:
                                print(f"  提取到 {len(machines)} 条")
                                for m in machines:
                                    if self.save_machine(m):
                                        name = m.get('name', '')[:40]
                                        print(f"    ✓ {name}")
                            else:
                                print(f"  未提取到数据")

                            # 滚动加载更多
                            for _ in range(2):
                                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                                await asyncio.sleep(2)
                                more = await self.extract_from_page(page)
                                for m in more:
                                    if self.save_machine(m):
                                        print(f"    + {m.get('name', '')[:40]}")

                            break  # 成功访问后不再尝试其他URL

                        except Exception as e:
                            print(f"  错误: {e}")
                            continue

            finally:
                print(f"\n{'=' * 70}")
                print(f"采集完成！共获取 {len(self.seen)} 条数据")
                print(f"数据保存在: {self.output_path}")
                await asyncio.sleep(2)
                await browser.close()


async def main():
    scraper = MeituanAutoScraper(CONFIG)
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
