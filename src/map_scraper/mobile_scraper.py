"""
移动版百度地图搜索

作者: UVM Research Team
"""

import asyncio
from playwright.async_api import async_playwright


async def mobile_search():
    chrome_path = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir='/tmp/mobile_map_v2',
            headless=False,
            executable_path=chrome_path,
            user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
            viewport={'width': 375, 'height': 812},
        )

        page = browser.pages[0] if browser.pages else await browser.new_page()

        print('使用移动版百度地图搜索...')

        # 直接搜索便利店
        await page.goto('https://map.baidu.com/search/便利店/@12959220,4825336,13z')
        await asyncio.sleep(10)

        # 获取页面内容
        text = await page.evaluate('''() => {
            const results = [];
            document.querySelectorAll('a, div, span').forEach(el => {
                const t = el.textContent ? el.textContent.trim() : '';
                if (t.includes('便利店') && t.length < 100 && t.length > 10) {
                    results.push(t);
                }
            });
            return [...new Set(results)].slice(0, 20);
        }''')

        print(f'\\n获取到 {len(text)} 条结果:')
        for t in text:
            print(f'  - {t[:50]}')

        await asyncio.sleep(30)
        await browser.close()

if __name__ == '__main__':
    asyncio.run(mobile_search())
