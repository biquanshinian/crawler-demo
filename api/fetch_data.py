import os, json
import firebase_admin
from firebase_admin import credentials, firestore

if not firebase_admin._apps:
    cred = credentials.Certificate(json.loads(os.environ['FIREBASE_SERVICE_ACCOUNT']))
    firebase_admin.initialize_app(cred)
db = firestore.client()

async def handler(request):
    docs = db.collection('crawl_results').order_by('url').limit(10).stream()
    results = [doc.to_dict() for doc in docs]
    return {'statusCode': 200, 'body': json.dumps({'results': results}, ensure_ascii=False)} 