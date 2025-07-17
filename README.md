# Web Crawler Demo (Vercel + Firebase)

## 项目结构

```
├── api/
│   ├── crawler.py      # 定时爬虫 Serverless Function
│   └── fetch_data.py   # API 查询 Serverless Function
├── index.html          # 前端页面
├── requirements.txt    # Python 依赖
├── vercel.json         # Vercel 配置
└── README.md           # 项目说明
```

## 功能说明
- `crawler.py`：定时爬取目标网页，解析内容并写入 Firebase Firestore。
- `fetch_data.py`：提供 API 查询接口，从 Firestore 读取数据。
- `index.html`：通过 API 获取数据并展示。

## 部署与运行

### 1. Firebase 配置
- 在 Firebase 控制台创建项目，生成服务账号密钥。
- 在 Vercel 项目环境变量中添加 `FIREBASE_SERVICE_ACCOUNT`，内容为服务账号 JSON 字符串。

### 2. Vercel 配置
- `vercel.json` 已配置好定时任务和 API 路由。
- 部署到 Vercel 即可自动定时运行爬虫。

### 3. 本地开发
- 安装依赖：`pip install -r requirements.txt`
- 手动运行爬虫：`python api/crawler.py`
- 本地测试 API：可用 Vercel CLI 或自行实现 FastAPI 版本

### 4. 前端对接
- `index.html` 通过 `/api/fetch_data` 获取数据，渲染到页面。

## 注意事项
- 不要将密钥文件上传到仓库，全部用环境变量管理。
- 如需自定义爬取内容，请修改 `crawler.py` 的 `get_xpath_selectors`。 