import os
import json
import logging
import asyncio
import firebase_admin
from firebase_admin import credentials, firestore
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
import aiohttp
from bs4 import BeautifulSoup

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 初始化Firebase
try:
    # 从环境变量加载Firebase凭证
    firebase_cred = credentials.Certificate(json.loads(os.environ['FIREBASE_SERVICE_ACCOUNT']))
    firebase_admin.initialize_app(firebase_cred)
    db = firestore.client()
    logger.info("Firebase初始化成功")
except Exception as e:
    logger.error(f"Firebase初始化失败: {e}")
    raise

# 定义数据模型
class XPathSelector(BaseModel):
    name: str
    xpath: str

class CrawlConfig(BaseModel):
    target_url: str
    xpath_selectors: List[XPathSelector]
    auto_discovery: bool = False
    max_depth: int = 2
    concurrency: int = 3

class CrawlResult(BaseModel):
    id: str = Field(..., alias='_id')
    url: str
    success: bool
    duration: float
    data_size: int
    status_code: int
    error: Optional[str] = None
    result: Dict = {}
    timestamp: float

# 创建FastAPI应用
app = FastAPI(title="Web Crawler API", version="1.0.0")

# 添加CORS支持
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 或指定你的前端地址如 "http://127.0.0.1:5500"
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 爬虫任务队列
crawl_tasks = {}

# 爬取单个URL
async def crawl_url(session, url, xpath_selectors, depth=1, max_depth=2):
    start_time = asyncio.get_event_loop().time()
    result = {
        'url': url,
        'success': False,
        'duration': 0,
        'data_size': 0,
        'status_code': 0,
        'error': None,
        'result': {},
        'timestamp': start_time
    }
    
    try:
        async with session.get(url) as response:
            result['status_code'] = response.status
            result['duration'] = asyncio.get_event_loop().time() - start_time
            
            if response.status == 200:
                html = await response.text()
                result['data_size'] = len(html)
                result['success'] = True
                
                # 使用BeautifulSoup和XPath解析内容
                soup = BeautifulSoup(html, 'html.parser')
                for selector in xpath_selectors:
                    try:
                        # 注意：BeautifulSoup不直接支持XPath，这里简化处理
                        elements = soup.select(selector.xpath.replace('//', ' ').replace('@', ''))
                        if elements:
                            result['result'][selector.name] = [el.get_text(strip=True) for el in elements]
                        else:
                            result['result'][selector.name] = None
                    except Exception as e:
                        logger.error(f"XPath解析错误: {e}")
                        result['result'][selector.name] = f"解析错误: {str(e)}"
            
            else:
                result['error'] = f"HTTP状态码: {response.status}"
    
    except Exception as e:
        logger.error(f"爬取错误: {e}")
        result['error'] = str(e)
    
    # 保存结果到Firebase
    try:
        doc_ref = db.collection('crawl_results').document()
        doc_ref.set(result)
        result['_id'] = doc_ref.id
    except Exception as e:
        logger.error(f"保存结果到Firebase失败: {e}")
    
    return result

# 后台爬取任务
async def crawl_task(config: CrawlConfig, task_id: str):
    try:
        # 更新任务状态
        task_ref = db.collection('crawl_tasks').document(task_id)
        task_ref.set({
            'status': 'running',
            'config': config.dict(),
            'start_time': firestore.SERVER_TIMESTAMP,
            'completed_urls': 0,
            'total_urls': 1
        })
        
        # 创建会话
        async with aiohttp.ClientSession() as session:
            # 爬取目标URL
            result = await crawl_url(
                session, 
                config.target_url, 
                config.xpath_selectors, 
                max_depth=config.max_depth
            )
            
            # 更新任务状态
            task_ref.update({
                'status': 'completed',
                'end_time': firestore.SERVER_TIMESTAMP,
                'completed_urls': 1,
                'success': result['success']
            })
            
            logger.info(f"任务 {task_id} 完成")
            
    except Exception as e:
        logger.error(f"爬取任务异常: {e}")
        # 更新任务状态为失败
        try:
            task_ref = db.collection('crawl_tasks').document(task_id)
            task_ref.update({
                'status': 'failed',
                'end_time': firestore.SERVER_TIMESTAMP,
                'error': str(e)
            })
        except:
            pass

# API端点
@app.get("/status", response_model=Dict)
async def get_status():
    """获取爬虫状态"""
    try:
        # 获取最近的任务和结果统计
        tasks_ref = db.collection('crawl_tasks').order_by('start_time', direction=firestore.Query.DESCENDING).limit(5)
        tasks = [doc.to_dict() for doc in tasks_ref.stream()]
        
        results_ref = db.collection('crawl_results')
        total_crawls = len(list(results_ref.stream()))
        success_count = len(list(results_ref.where('success', '==', True).stream()))
        
        # 计算成功率
        success_rate = (success_count / total_crawls * 100) if total_crawls > 0 else 0
        
        # 获取最近的爬取记录
        recent_results = [doc.to_dict() for doc in results_ref.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(5).stream()]
        
        return {
            'status': 'ready',
            'total_crawls': total_crawls,
            'success_rate': success_rate,
            'recent_tasks': tasks,
            'recent_results': recent_results
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取状态失败: {str(e)}")

@app.post("/start", response_model=Dict)
async def start_crawl(config: CrawlConfig, background_tasks: BackgroundTasks):
    """启动爬虫任务"""
    try:
        # 创建新任务ID
        task_id = firestore.SERVER_TIMESTAMP.strftime("%Y%m%d%H%M%S")
        
        # 添加到后台任务
        background_tasks.add_task(crawl_task, config, task_id)
        
        return {
            'task_id': task_id,
            'status': 'started',
            'message': '爬虫任务已启动'
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"启动任务失败: {str(e)}")

@app.get("/results", response_model=List[CrawlResult])
async def get_results(limit: int = 10, page: int = 1):
    """获取爬取结果列表"""
    try:
        offset = (page - 1) * limit
        results_ref = db.collection('crawl_results')
        query = results_ref.order_by('timestamp', direction=firestore.Query.DESCENDING).offset(offset).limit(limit)
        docs = query.stream()
        
        return [doc.to_dict() for doc in docs]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取结果失败: {str(e)}")

@app.get("/results/{result_id}", response_model=CrawlResult)
async def get_result(result_id: str):
    """获取单个爬取结果详情"""
    try:
        doc_ref = db.collection('crawl_results').document(result_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            raise HTTPException(status_code=404, detail="结果未找到")
            
        return doc.to_dict()
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取结果详情失败: {str(e)}")

@app.get("/tasks", response_model=List[Dict])
async def get_tasks(limit: int = 10, page: int = 1):
    """获取任务列表"""
    try:
        offset = (page - 1) * limit
        tasks_ref = db.collection('crawl_tasks')
        query = tasks_ref.order_by('start_time', direction=firestore.Query.DESCENDING).offset(offset).limit(limit)
        docs = query.stream()
        
        return [doc.to_dict() for doc in docs]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取任务列表失败: {str(e)}")

@app.get("/tasks/{task_id}", response_model=Dict)
async def get_task(task_id: str):
    """获取单个任务详情"""
    try:
        doc_ref = db.collection('crawl_tasks').document(task_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            raise HTTPException(status_code=404, detail="任务未找到")
            
        return doc.to_dict()
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取任务详情失败: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
app = FastAPI(title="Web Crawler API", version="1.0.0", debug=True)
