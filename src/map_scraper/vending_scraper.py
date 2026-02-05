"""
自动售货机专用爬虫

针对性爬取自动售货机POI数据，严格过滤便利店等无关数据

数据来源:
- 腾讯地图 API (需要申请Key)
- 高德地图 API (需要申请Key)

作者: UVM Research Team
"""

import asyncio
import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Set, Dict, Any, List, Optional
from urllib.parse import quote

import aiohttp


# ==================== 配置 ====================
CONFIG = {
    "city": "北京",
    "output_dir": "data/raw",
    "output_file": "vending_machines.csv",

    # API Key配置 - 请至少填写一个
    "tencent_api_key": "",  # 腾讯地图: https://lbs.qq.com/dev/console/application/mine
    "amap_api_key": "6dc3b2f659ec16fefe5016f0ad69ad25",     # 高德地图: https://console.amap.com/dev/key/app

    # 自动售货机相关关键词 - 全面版
    "keywords": [
        # === 品牌关键词 ===
        "友宝", "U-BOX", "UBOX", "友宝售货机",
        "丰e足食", "丰翼",

        # === 类型关键词 ===
        "自动售货机", "自动贩卖机", "无人售货机", "无人售货", "售货机",

        # === 饮料类 ===
        "饮料售货机", "饮料机", "可乐机", "雪碧机",
        "农夫山泉售货机", "怡宝售货机", "康师傅售货机",
        "哇哈哈售货机", "红牛售货机", "功能饮料售货机",

        # === 咖啡类 ===
        "咖啡机", "咖啡售货机", "现磨咖啡机", "自助咖啡",
        "瑞幸咖啡机", "星巴克咖啡机", "luckin咖啡",

        # === 成人用品 ===
        "成人用品售货机", "成人用品无人", "情趣用品售货",
        "成人用品24小时", "无人售货成人",

        # === 潮玩类 ===
        "泡泡玛特", "POP MART", "盲盒售货机", "潮玩售货",
        "m豆", "M豆豆", "巧克力售货机",

        # === 冰淇淋类 ===
        "冰淇淋售货机", "冰淇淋机", "哈根达斯售货",
        "和路雪售货", "八喜售货机",

        # === 其他 ===
        "果汁售货机", "奶茶售货机", "零食售货机",
        "自助售货", "无人售货柜", "智能售货柜",
    ],

    # 地标位置 - 用于周边搜索
    "landmarks": [
        # 交通枢纽
        "北京站", "北京西站", "北京南站", "北京北站",
        "首都机场", "大兴机场",
        "国贸", "三元桥", "望京", "中关村",

        # 商圈
        "王府井", "西单", "三里屯", "五道口",
        "朝阳大悦城", "西单大悦城", "合生汇",
        "崇文门", "东直门", "复兴门",

        # 写字楼集中地
        "CBD", "金融街", "中关村软件园", "望京SOHO",
        "建国门", "亮马桥", "燕莎",

        # 高校
        "北京大学", "清华大学", "中国人民大学",
        "北京理工大学", "北京航空航天大学",
        "北京师范大学", "北京外国语大学",
    ],

    # 北京各区县 - 用于区域搜索
    "districts": [
        "朝阳区", "海淀区", "东城区", "西城区",
        "丰台区", "石景山区", "通州区", "昌平区",
        "大兴区", "顺义区", "房山区", "门头沟区",
        "平谷区", "怀柔区", "密云区", "延庆区"
    ],

    # 严格过滤词 - 包含这些词的将被过滤
    "filter_keywords": [
        # 便利店品牌
        "便利店", "7-11", "711", "全家", "FamilyMart", "罗森", "Lawson",
        "物美", "便利蜂", "喜士多", "OK", "快客", "十足", "人人乐",

        # 超市
        "超市", "卖场", "购物中心", "百货",

        # 无关
        "维修", "加盟", "招商", "招聘", "客服", "官网",
    ],
}

CSV_HEADERS = [
    "id", "name", "address", "category", "brand",
    "lat", "lng", "city", "district", "source", "crawl_time"
]


# ==================== 数据保存类 ====================
class VendingMachineSaver:
    """自动售货机数据保存器"""

    # 便利店特征词 - 用于严格过滤
    CONVENIENCE_STORES = {
        "便利店", "7-11", "711", "全家", "familymart", "罗森", "lawson",
        "物美", "便利蜂", "喜士多", "ok便利店", "快客", "十足",
        "京客隆", "超市发", "华联", "永辉", "华润", "家乐福", "沃尔玛",
        "盒马", "便利", "超市"
    }

    def __init__(self, output_dir: str, output_file: str):
        self.output_path = Path(output_dir)
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.file_path = self.output_path / output_file
        self.seen: Set[str] = set()
        self._init_csv()

    def _init_csv(self):
        if not self.file_path.exists() or self.file_path.stat().st_size == 0:
            with open(self.file_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
                writer.writeheader()
            print(f"✓ 创建文件: {self.file_path}")

    def is_vending_machine(self, name: str, category: str = "") -> bool:
        """
        判断是否为自动售货机

        规则:
        1. 名称中必须包含售货机相关词
        2. 不能包含便利店等过滤词
        """
        if not name:
            return False

        name_lower = name.lower()

        # 检查是否包含便利店关键词
        for store in self.CONVENIENCE_STORES:
            if store in name_lower:
                return False

        # 检查是否包含售货机相关词
        vending_keywords = [
            "售货机", "贩卖机", "无人售货", "自动售货",
            "友宝", "ubox", "u-box", "丰e足食", "丰翼",
            "成人用品", "情趣用品"
        ]

        has_vending_keyword = any(kw in name or kw in name_lower for kw in vending_keywords)

        return has_vending_keyword

    def extract_brand(self, name: str) -> str:
        """从名称中提取品牌"""
        if not name:
            return ""

        brands = {
            "友宝": ["友宝", "U-BOX", "UBOX", "U-Box"],
            "丰e足食": ["丰e足食", "丰翼"],
            "成人用品": ["成人用品", "情趣用品"],
        }

        for brand, keywords in brands.items():
            for kw in keywords:
                if kw in name:
                    return brand

        return "其他"

    def save_poi(self, poi: Dict[str, Any], source: str = "") -> bool:
        """保存POI数据"""
        name = poi.get("title") or poi.get("name") or ""
        address = poi.get("address", "")
        category = poi.get("category", "")

        if not self.is_vending_machine(name, category):
            return False

        # 生成唯一ID
        poi_id = poi.get("id", "")
        key = f"{poi_id}_{name}_{address}"

        if key in self.seen:
            return False
        self.seen.add(key)

        # 提取坐标
        location = poi.get("location", {})
        if isinstance(location, str):
            lat, lng = "", ""
        elif isinstance(location, dict):
            lat = location.get("lat", "")
            lng = location.get("lng", "")
        else:
            lat, lng = "", ""

        # 提取区域信息
        ad_info = poi.get("ad_info", {})
        district = ad_info.get("district", "") if isinstance(ad_info, dict) else ""

        with open(self.file_path, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writerow({
                "id": poi_id,
                "name": name,
                "address": address,
                "category": category,
                "brand": self.extract_brand(name),
                "lat": lat,
                "lng": lng,
                "city": CONFIG["city"],
                "district": district,
                "source": source,
                "crawl_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })

        brand_tag = self.extract_brand(name)
        print(f"  [{brand_tag}] {name}")
        return True

    def get_count(self) -> int:
        return len(self.seen)


# ==================== 腾讯地图爬虫 ====================
class TencentMapScraper:
    """腾讯地图POI爬虫"""

    BASE_URL = "https://apis.map.qq.com/ws/place/v1/search"

    def __init__(self, api_key: str, config: Dict[str, Any]):
        self.api_key = api_key
        self.config = config
        self.saver = VendingMachineSaver(config["output_dir"], config["output_file"])

    def has_api_key(self) -> bool:
        return bool(self.api_key)

    async def run(self):
        if not self.has_api_key():
            print("⚠️ 未配置腾讯地图API Key")
            return False

        print("\n[腾讯地图] 开始搜索...")

        async with aiohttp.ClientSession() as session:
            for keyword in self.config["keywords"]:
                count = await self.search_keyword(session, keyword)
                if count > 0:
                    print(f"    {keyword}: 获取 {count} 条")
                await asyncio.sleep(0.5)

        return True

    async def search_keyword(self, session: aiohttp.ClientSession, keyword: str) -> int:
        """搜索单个关键词"""
        city = self.config["city"]
        count = 0

        # 城市级搜索
        for page in range(1, 11):  # 最多10页
            params = {
                "keyword": keyword,
                "boundary": f"region({city},0)",
                "page_size": 20,
                "page_index": page,
                "key": self.api_key,
                "output": "json"
            }

            pois = await self._request(session, params)
            if not pois:
                break

            for poi in pois:
                if self.saver.save_poi(poi, "腾讯地图"):
                    count += 1

            if len(pois) < 20:
                break

            await asyncio.sleep(0.3)

        return count

    async def _request(self, session: aiohttp.ClientSession, params: Dict) -> List[Dict]:
        """执行API请求"""
        url = f"{self.BASE_URL}?{self._build_query(params)}"

        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()

                if data.get("status") == 0:
                    return data.get("data", [])
                else:
                    error = data.get("message", "Unknown error")
                    print(f"    API错误: {error}")
                    return []
        except Exception as e:
            print(f"    请求失败: {e}")
            return []

    def _build_query(self, params: Dict) -> str:
        return "&".join(f"{k}={quote(str(v))}" for k, v in params.items())


# ==================== 高德地图爬虫 ====================
class AmapScraper:
    """高德地图POI爬虫"""

    BASE_URL = "https://restapi.amap.com/v5/place/text"

    def __init__(self, api_key: str, config: Dict[str, Any]):
        self.api_key = api_key
        self.config = config
        self.saver = VendingMachineSaver(config["output_dir"], config["output_file"])

    def has_api_key(self) -> bool:
        return bool(self.api_key)

    async def run(self):
        if not self.has_api_key():
            print("⚠️ 未配置高德地图API Key")
            return False

        print("\n[高德地图] 开始搜索...")
        print("  搜索策略: 城市级 + 各区县 + 地标周边")

        async with aiohttp.ClientSession() as session:
            total_count = 0

            # 策略1: 城市级搜索主要关键词（多页深度爬取）
            print("\n  === 策略1: 全市关键词搜索 ===")
            main_keywords = ["友宝", "售货机", "无人售货", "饮料机", "咖啡机"]
            for keyword in main_keywords:
                count = await self.search_keyword(session, keyword, self.config["city"])
                if count > 0:
                    print(f"    [全市] {keyword}: 获取 {count} 条")
                    total_count += count
                await asyncio.sleep(0.5)

            # 策略2: 按区县搜索（每个区单独搜索）
            print(f"\n  === 策略2: 按区县搜索 (共16个区) ===")
            districts = self.config.get("districts", [])
            main_keywords = ["友宝", "售货机", "无人售货"]
            for district in districts:
                for keyword in main_keywords:
                    count = await self.search_keyword(session, keyword, district)
                    if count > 0:
                        print(f"    [{district}] {keyword}: {count} 条")
                        total_count += count
                await asyncio.sleep(0.3)

            # 策略3: 地标周边搜索
            print(f"\n  === 策略3: 地标周边搜索 ===")
            landmarks = self.config.get("landmarks", [])
            for landmark in landmarks[:15]:  # 先搜索前15个地标
                for keyword in ["售货机", "友宝"]:
                    count = await self.search_nearby(session, landmark, keyword)
                    if count > 0:
                        print(f"    [{landmark}] {keyword}: {count} 条")
                        total_count += count
                await asyncio.sleep(0.3)

        print(f"\n  [高德地图] 共获取 {total_count} 条数据")
        return True

    async def search_keyword(self, session: aiohttp.ClientSession, keyword: str, region: str) -> int:
        """搜索单个关键词，指定区域"""
        count = 0

        for page in range(1, 11):
            params = {
                "keywords": keyword,
                "region": region,
                "page_size": 20,
                "page_num": page,
                "key": self.api_key,
            }

            pois = await self._request(session, params)
            if not pois:
                break

            for poi in pois:
                # 转换高德格式到统一格式
                formatted_poi = {
                    "id": poi.get("id", ""),
                    "title": poi.get("name", ""),
                    "address": poi.get("address", ""),
                    "category": poi.get("type", ""),
                    "location": {
                        "lat": poi.get("location", "").split(",")[1] if poi.get("location") else "",
                        "lng": poi.get("location", "").split(",")[0] if poi.get("location") else "",
                    },
                    "ad_info": {
                        "district": poi.get("adname", "")
                    }
                }
                if self.saver.save_poi(formatted_poi, "高德地图"):
                    count += 1

            if len(pois) < 20:
                break

            await asyncio.sleep(0.3)

        return count

    async def search_nearby(self, session: aiohttp.ClientSession, location: str, keyword: str) -> int:
        """在指定地标周边搜索"""
        count = 0

        for page in range(1, 6):  # 周边搜索最多5页
            params = {
                "keywords": keyword,
                "city": self.config["city"],
                "address": location,  # 使用address参数进行周边搜索
                "page_size": 20,
                "page_num": page,
                "key": self.api_key,
            }

            pois = await self._request(session, params)
            if not pois:
                break

            for poi in pois:
                formatted_poi = {
                    "id": poi.get("id", ""),
                    "title": poi.get("name", ""),
                    "address": poi.get("address", ""),
                    "category": poi.get("type", ""),
                    "location": {
                        "lat": poi.get("location", "").split(",")[1] if poi.get("location") else "",
                        "lng": poi.get("location", "").split(",")[0] if poi.get("location") else "",
                    },
                    "ad_info": {
                        "district": poi.get("adname", "")
                    }
                }
                if self.saver.save_poi(formatted_poi, "高德地图"):
                    count += 1

            if len(pois) < 20:
                break

            await asyncio.sleep(0.3)

        return count

    async def _request(self, session: aiohttp.ClientSession, params: Dict, retry: int = 3) -> List[Dict]:
        """执行API请求，带重试机制"""
        url = self.BASE_URL

        for attempt in range(retry):
            try:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    data = await resp.json()

                    if data.get("status") == "1":
                        return data.get("pois", [])
                    else:
                        error = data.get("info", "Unknown error")
                        # 某些错误不需要重试
                        if "INVALID_USER_KEY" in error or "DAILY_QUERY_OVER_LIMIT" in error:
                            print(f"    API错误: {error}")
                            return []
                        # 其他错误可以重试
                        if attempt < retry - 1:
                            await asyncio.sleep(2 ** attempt)  # 指数退避
                            continue
                        print(f"    API错误: {error}")
                        return []
            except Exception as e:
                if attempt < retry - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                # 最后一次失败时不打印错误，避免刷屏
                return []

        return []


# ==================== 主程序 ====================
async def main():
    print("=" * 60)
    print("自动售货机数据爬虫")
    print("=" * 60)

    # 检查API Key
    has_tencent = bool(CONFIG["tencent_api_key"])
    has_amap = bool(CONFIG["amap_api_key"])

    if not has_tencent and not has_amap:
        print("\n⚠️ 请至少配置一个地图API Key:\n")
        print("1. 腾讯地图: https://lbs.qq.com/dev/console/application/mine")
        print("2. 高德地图: https://console.amap.com/dev/key/app")
        print("\n在CONFIG中填写 'tencent_api_key' 或 'amap_api_key'")
        return

    saver = VendingMachineSaver(CONFIG["output_dir"], CONFIG["output_file"])

    # 腾讯地图
    if has_tencent:
        tencent = TencentMapScraper(CONFIG["tencent_api_key"], CONFIG)
        await tencent.run()

    # 高德地图
    if has_amap:
        amap = AmapScraper(CONFIG["amap_api_key"], CONFIG)
        await amap.run()

    print(f"\n{'=' * 60}")
    print(f"✓ 完成! 共获取 {saver.get_count()} 条自动售货机数据")
    print(f"✓ 数据保存在: {saver.file_path}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    asyncio.run(main())
