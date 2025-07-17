import os, json, asyncio
import firebase_admin
from firebase_admin import credentials, firestore
import aiohttp
from bs4 import BeautifulSoup

# 初始化 Firebase
if not firebase_admin._apps:
    cred = credentials.Certificate(json.loads(os.environ['FIREBASE_SERVICE_ACCOUNT']))
    firebase_admin.initialize_app(cred)
db = firestore.client()

def get_target_url():
    return os.environ.get('CRAWL_TARGET_URL', 'https://example.com')

def get_xpath_selectors():
    # 可根据实际需求自定义
    return [
        {"name": "title", "xpath": "title"},
        # 可添加更多 selector
    ]

async def crawl():
    url = get_target_url()
    xpath_selectors = get_xpath_selectors()
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            html = await resp.text()
            soup = BeautifulSoup(html, 'html.parser')
            result = {"url": url}
            for selector in xpath_selectors:
                try:
                    elements = soup.select(selector['xpath'])
                    result[selector['name']] = [el.get_text(strip=True) for el in elements] if elements else None
                except Exception as e:
                    result[selector['name']] = f"解析错误: {str(e)}"
            db.collection('crawl_results').add(result)

async def handler(request):
    await crawl()
    return {'statusCode': 200, 'body': json.dumps({'message': 'Crawl completed'})}

if __name__ == "__main__":
    asyncio.run(crawl()) 