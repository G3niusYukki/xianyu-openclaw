"""Web服务API接口"""

from typing import Dict, List, Any, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio

from src.core.config import Config
from src.core.logger import get_logger
from src.modules.listing.service import ListingService
from src.modules.operations.service import OperationsService
from src.modules.analytics.service import AnalyticsService
from src.modules.accounts.service import AccountsService

logger = get_logger(__name__)

app = FastAPI(title="闲鱼自动化工具API", version="1.0.0")

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 数据模型
class ProductInfo(BaseModel):
    name: str
    category: str
    price: float
    condition: str
    reason: str
    features: List[str] = []

class PriceUpdate(BaseModel):
    product_id: str
    new_price: float
    original_price: Optional[float] = None

# 服务初始化
config = Config()
listing_service = ListingService()
operations_service = OperationsService()
analytics_service = AnalyticsService()
accounts_service = AccountsService()

@app.get("/")
async def root():
    return {"message": "闲鱼自动化工具API", "version": "1.0.0"}

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "timestamp": asyncio.get_event_loop().time()}

@app.get("/api/dashboard/stats")
async def get_dashboard_stats():
    try:
        stats = await analytics_service.get_dashboard_stats()
        return {"success": True, "data": stats}
    except Exception as e:
        logger.error(f"获取仪表盘数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/accounts")
async def list_accounts():
    try:
        accounts = accounts_service.get_accounts()
        return {"success": True, "data": accounts}
    except Exception as e:
        logger.error(f"获取账号列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/accounts/{account_id}/health")
async def get_account_health(account_id: str):
    try:
        health = accounts_service.get_account_health(account_id)
        return {"success": True, "data": health}
    except Exception as e:
        logger.error(f"获取账号健康度失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/products/publish")
async def publish_product(product: ProductInfo):
    try:
        result = await listing_service.create_listing(product)
        return {"success": result.success, "data": {"url": result.product_url}, "error": result.error_message}
    except Exception as e:
        logger.error(f"发布商品失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/operations/polish/{product_id}")
async def polish_product(product_id: str):
    try:
        result = await operations_service.polish_listing(product_id)
        return {"success": result.get('success', False)}
    except Exception as e:
        logger.error(f"擦亮商品失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/operations/polish/batch")
async def batch_polish(max_items: int = 50):
    try:
        result = await operations_service.batch_polish(max_items=max_items)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"批量擦亮失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/operations/price")
async def update_price(update: PriceUpdate):
    try:
        result = await operations_service.update_price(
            product_id=update.product_id,
            new_price=update.new_price,
            original_price=update.original_price
        )
        return {"success": result.get('success', False)}
    except Exception as e:
        logger.error(f"更新价格失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analytics/report/daily")
async def get_daily_report():
    try:
        report = await analytics_service.get_daily_report()
        return {"success": True, "data": report}
    except Exception as e:
        logger.error(f"获取日报失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analytics/report/weekly")
async def get_weekly_report():
    try:
        from src.modules.analytics.report_generator import ReportGenerator
        report = await ReportGenerator().generate_weekly_report()
        return {"success": True, "data": report}
    except Exception as e:
        logger.error(f"获取周报失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analytics/trend")
async def get_trend_data(days: int = 30):
    try:
        trends = await analytics_service.get_trend_data("views", days=days)
        return {"success": True, "data": trends}
    except Exception as e:
        logger.error(f"获取趋势数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/alerts")
async def get_alerts():
    try:
        from src.modules.accounts.monitor import Monitor
        monitor = Monitor()
        alerts = monitor.get_active_alerts()
        return {"success": True, "data": [alert.__dict__ for alert in alerts]}
    except Exception as e:
        logger.error(f"获取告警失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8501)
