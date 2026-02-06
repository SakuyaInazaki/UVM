"""
美团丰e足食售货机数据采集爬虫 v2

采集方法：
1. 访问美团搜索页面
2. 等待动态内容加载
3. 搜索"丰e足食"或"自动售货机"
4. 提取售货机位置信息

注意：
- 美团使用动态加载，需要等待JavaScript执行完成
- 建议使用已登录的浏览器状态

作者: UVM Research Team
"""

import asyncio
import json
import csv
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from typing import List, Dict, Set, Optional

from playwright.async_api import async_playwright, Page, Browser


CONFIG = {
    "city": "北京",
    "keywords": ["自动售货机"],
    "output_dir": "data/raw",
    "output_file": "fenge_zushi_machines.csv",
    "headless": False,
    "max_pages": 5,
    "delay": 3,
    "debug": True,  # 保存调试信息
}


class FengESaver:
    """数据保存器"""

    def __init__(self, output_dir: str, output_file: str):
        self.output_path = Path(output_dir)
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.file_path = self.output_path / output_file
        self.debug_dir = self.output_path / "debug"
        self.debug_dir.mkdir(exist_ok=True)
        self.seen: Set[str] = set()
        self._init_csv()

    def _init_csv(self):
        if not self.file_path.exists() or self.file_path.stat().st_size == 0:
            with open(self.file_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "id", "name", "address", "district", "lat", "lng",
                    "distance", "category", "business_hours", "source",
                    "crawl_time"
                ])
            print(f"✓ 创建文件: {self.file_path}")

    def is_valid_name(self, name: str) -> bool:
        """验证名称有效性"""
        if not name:
            return False
        invalid = ['class=', 'data-', 'transform', 'none:', '<', '>',
                   '备案', '举报', 'ICP', 'cookies', 'function', 'return',
                   'undefined', 'null', 'object', 'window']
        for p in invalid:
            if p in name:
                return False
        if len(name) < 3 or len(name) > 100:
            return False
        return True

    def save_machine(self, machine: Dict) -> bool:
        """保存售货机数据"""
        name = machine.get("name", "").strip()
        name = re.sub(r'\s+', ' ', name)

        if not self.is_valid_name(name):
            return False

        key = f"{name}_{machine.get('address', '')}"
        if key in self.seen:
            return False
        self.seen.add(key)

        with open(self.file_path, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([
                machine.get("id", ""),
                name,
                machine.get("address", ""),
                machine.get("district", ""),
                machine.get("lat", ""),
                machine.get("lng", ""),
                machine.get("distance", ""),
                machine.get("category", ""),
                machine.get("business_hours", ""),
                "美团",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ])

        return True

    def get_count(self) -> int:
        return len(self.seen)

    def save_debug(self, filename: str, content: str):
        """保存调试信息"""
        debug_file = self.debug_dir / filename
        with open(debug_file, 'w', encoding='utf-8') as f:
            f.write(content)


class FengEScraper:
    """丰e足食售货机爬虫"""

    def __init__(self, config: Dict):
        self.config = config
        self.saver = FengESaver(config["output_dir"], config["output_file"])
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None

    async def run(self):
        """运行爬虫"""
        print("=" * 70)
        print("美团丰e足食售货机数据采集 v2")
        print("=" * 70)
        print("\n提示：首次运行需要手动登录美团账号")
        print("登录完成后按回车继续...\n")

        async with async_playwright() as p:
            self.browser = await p.chromium.launch_persistent_context(
                user_data_dir="/tmp/meituan_fenge_scraper_v2",
                headless=self.config["headless"],
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                ],
                viewport={"width": 1440, "height": 900},
                locale="zh-CN",
            )

            self.page = self.browser.pages[0] if self.browser.pages else await self.browser.new_page()

            try:
                # 检查登录状态
                await self._check_login()

                # 依次搜索每个关键词
                for keyword in self.config["keywords"]:
                    await self._search_keyword(keyword)

            finally:
                print(f"\n采集完成，共获取 {self.saver.get_count()} 条数据")
                print(f"数据保存在: {self.saver.file_path}")
                await asyncio.sleep(2)
                await self.browser.close()

    async def _check_login(self):
        """检查登录状态"""
        print("\n[1] 检查登录状态...")
        try:
            await self.page.goto("https://www.meituan.com/", timeout=30000)
            await asyncio.sleep(3)

            print("  页面已加载，请确认登录状态")
            print("  如果未登录，请在浏览器中手动登录")
            print("  登录完成后按回车继续...")
            input()

        except Exception as e:
            print(f"  ! 加载失败: {e}")

    async def _search_keyword(self, keyword: str):
        """搜索关键词"""
        print(f"\n[2] 搜索关键词: {keyword}")

        try:
            # 美团搜索URL
            search_url = f"https://www.meituan.com/s/{quote(keyword)}/"
            print(f"  访问: {search_url}")

            await self.page.goto(search_url, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(self.config["delay"])

            # 保存调试信息
            if self.config["debug"]:
                html = await self.page.content()
                self.saver.save_debug(f"{keyword}_page.html", html)
                print(f"  ✓ 已保存页面HTML到debug目录")

            # 尝试多种提取方法
            machines = await self._extract_results_v1()
            if not machines:
                machines = await self._extract_results_v2()
            if not machines:
                machines = await self._extract_results_v3()

            print(f"  提取到 {len(machines)} 条结果")

            for machine in machines:
                machine["category"] = keyword
                if self.saver.save_machine(machine):
                    print(f"    ✓ {machine.get('name', '')[:50]}")

            # 翻页
            for i in range(self.config["max_pages"] - 1):
                await asyncio.sleep(2)
                has_more = await self._next_page()
                if not has_more:
                    break
                await asyncio.sleep(self.config["delay"])

                machines = await self._extract_results_v1()
                if not machines:
                    machines = await self._extract_results_v2()

                print(f"  第{i+2}页: 提取到 {len(machines)} 条")

                for machine in machines:
                    machine["category"] = keyword
                    if self.saver.save_machine(machine):
                        print(f"    ✓ {machine.get('name', '')[:50]}")

        except Exception as e:
            print(f"  ! 搜索失败: {e}")
            import traceback
            traceback.print_exc()

    async def _extract_results_v1(self) -> List[Dict]:
        """提取方法1：通用POI列表"""
        try:
            js = """() => {
                const results = [];
                const seen = new Set();

                // 查找所有文本节点，尝试识别POI名称
                const walker = document.createTreeWalker(
                    document.body,
                    NodeFilter.SHOW_TEXT,
                    null
                );

                let node;
                while (node = walker.nextNode()) {
                    const text = node.textContent?.trim();
                    if (!text) continue;

                    // 查找父元素
                    let parent = node.parentElement;
                    if (!parent) continue;

                    // 跳过script和style
                    if (parent.tagName === 'SCRIPT' || parent.tagName === 'STYLE') continue;

                    // 尝试识别地址（包含"路"、"区"、"号"等）
                    if (text.length > 10 && text.length < 100 &&
                        (text.includes('区') || text.includes('路') || text.includes('街') ||
                         text.includes('号') || text.includes('栋') || text.includes('楼'))) {

                        // 查找关联的名称
                        let name = '';
                        let sibling = parent.previousElementSibling;
                        let attempts = 0;
                        while (sibling && attempts < 3) {
                            const siblingText = sibling.textContent?.trim();
                            if (siblingText && siblingText.length > 2 && siblingText.length < 50) {
                                name = siblingText;
                                break;
                            }
                            sibling = sibling.previousElementSibling;
                            attempts++;
                        }

                        if (!name) {
                            sibling = parent.nextElementSibling;
                            attempts = 0;
                            while (sibling && attempts < 2) {
                                const siblingText = sibling.textContent?.trim();
                                if (siblingText && siblingText.length > 2 && siblingText.length < 50) {
                                    name = siblingText;
                                    break;
                                }
                                sibling = sibling.nextElementSibling;
                                attempts++;
                            }
                        }

                        if (name && !seen.has(name + text)) {
                            seen.add(name + text);
                            results.push({
                                id: String(results.length),
                                name: name,
                                address: text
                            });
                        }
                    }
                }

                return results.slice(0, 30);
            }"""
            return await self.page.evaluate(js)
        except Exception as e:
            print(f"    v1提取失败: {e}")
            return []

    async def _extract_results_v2(self) -> List[Dict]:
        """提取方法2：查找特定class和属性"""
        try:
            js = """() => {
                const results = [];
                const seen = new Set();

                // 获取所有元素
                const allElements = document.querySelectorAll('*');

                for (const el of allElements) {
                    const className = el.className || '';
                    const id = el.id || '';

                    // 查找可能包含POI信息的元素
                    if (className.includes('poi') || className.includes('shop') ||
                        className.includes('item') || className.includes('list') ||
                        id.includes('poi') || id.includes('shop')) {

                        // 查找子元素中的文本
                        const textElements = el.querySelectorAll('*');
                        let name = '';
                        let address = '';

                        for (const textEl of textElements) {
                            const text = textEl.textContent?.trim() || '';
                            if (!text || text.length < 2) continue;

                            // 名称通常较短，地址较长
                            if (text.length > 3 && text.length < 30 && !name) {
                                // 可能是名称
                                if (!text.includes('路') && !text.includes('区') &&
                                    !text.includes('号') && !text.includes('米')) {
                                    name = text;
                                }
                            } else if (text.length > 10 && text.length < 100 && !address) {
                                // 可能是地址
                                if (text.includes('区') || text.includes('路') ||
                                    text.includes('街') || text.includes('号')) {
                                    address = text;
                                }
                            }

                            if (name && address) break;
                        }

                        if (name && !seen.has(name)) {
                            seen.add(name);
                            results.push({
                                id: String(results.length),
                                name: name,
                                address: address || ''
                            });
                        }
                    }
                }

                return results.slice(0, 30);
            }"""
            return await self.page.evaluate(js)
        except Exception as e:
            print(f"    v2提取失败: {e}")
            return []

    async def _extract_results_v3(self) -> List[Dict]:
        """提取方法3：查找链接元素"""
        try:
            js = """() => {
                const results = [];
                const seen = new Set();

                // 查找所有链接
                const links = document.querySelectorAll('a[href]');

                for (const link of links) {
                    const href = link.href || '';
                    const text = link.textContent?.trim() || '';

                    // 查找商家链接
                    if (href.includes('/shop/') || href.includes('/store/')) {
                        if (text && text.length > 2 && text.length < 100) {
                            if (!seen.has(text)) {
                                seen.add(text);
                                results.push({
                                    id: href.split('/').pop() || String(results.length),
                                    name: text,
                                    address: '',
                                    url: href
                                });
                            }
                        }
                    }
                }

                return results.slice(0, 50);
            }"""
            return await self.page.evaluate(js)
        except Exception as e:
            print(f"    v3提取失败: {e}")
            return []

    async def _next_page(self) -> bool:
        """点击下一页"""
        try:
            # 尝试多种可能的下一页选择器
            selectors = [
                'a.next:visible',
                '.next-page:visible',
                'a[class*="next"]:not([disabled])',
                'button[class*="next"]:not([disabled])',
                '.pagination a:last-child',
                '[class*="pagination"] a:contains("下一页")',
            ]

            for selector in selectors:
                try:
                    btn = await self.page.query_selector(selector)
                    if btn:
                        await btn.click()
                        await asyncio.sleep(3)
                        return True
                except:
                    continue

            # 尝试查找包含"下一页"文字的元素
            try:
                await self.page.click('text=下一页', timeout=2000)
                await asyncio.sleep(3)
                return True
            except:
                pass

            return False

        except Exception as e:
            print(f"    翻页失败: {e}")
            return False


async def main():
    """主函数"""
    scraper = FengEScraper(CONFIG)
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
