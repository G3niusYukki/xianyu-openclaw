"""Web服务API接口"""

import os
import time
import asyncio
from typing import Dict, List, Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.core.config import Config
from src.core.logger import get_logger
from src.modules.listing.service import ListingService
from src.modules.listing.models import Listing
from src.modules.operations.service import OperationsService
from src.modules.analytics.service import AnalyticsService
from src.modules.accounts.service import AccountsService
from src.modules.accounts.scheduler import Scheduler, TaskType

logger = get_logger(__name__)

app = FastAPI(title="闲鱼自动化工具API", version="1.0.0")

ALLOWED_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:8501,http://localhost:3000,http://127.0.0.1:8501,http://127.0.0.1:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


class RateLimiter:
    """简易内存速率限制器，按客户端 IP 限制请求频率"""

    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self._max = max_requests
        self._window = window_seconds
        self._requests: Dict[str, list] = {}

    def is_allowed(self, client_ip: str) -> bool:
        now = time.time()
        timestamps = self._requests.get(client_ip, [])
        timestamps = [t for t in timestamps if now - t < self._window]
        if len(timestamps) >= self._max:
            self._requests[client_ip] = timestamps
            return False
        timestamps.append(now)
        self._requests[client_ip] = timestamps
        return True


_rate_limiter = RateLimiter(
    max_requests=int(os.getenv("RATE_LIMIT_MAX", "30")),
    window_seconds=int(os.getenv("RATE_LIMIT_WINDOW", "60")),
)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path in ("/api/health", "/"):
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    if not _rate_limiter.is_allowed(client_ip):
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Please try again later."},
        )
    return await call_next(request)

# 数据模型
class ProductInfo(BaseModel):
    name: str
    category: str = "General"
    price: float
    condition: Optional[str] = None
    reason: Optional[str] = None
    features: List[str] = Field(default_factory=list)
    images: List[str] = Field(default_factory=list)
    title: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)

class PriceUpdate(BaseModel):
    product_id: str
    new_price: float
    original_price: Optional[float] = None

class AccountInfo(BaseModel):
    id: str
    name: str
    cookie: str
    priority: int = 1
    enabled: bool = True


class TaskInfo(BaseModel):
    task_type: str
    name: Optional[str] = None
    cron_expression: Optional[str] = None
    interval: Optional[int] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True

# 服务初始化
config = Config()
listing_service = ListingService()
operations_service = OperationsService()
analytics_service = AnalyticsService()
accounts_service = AccountsService()
scheduler_service = Scheduler()

@app.get("/")
async def root():
    return {"message": "闲鱼自动化工具API", "version": "1.0.0"}

@app.get("/api/health")
async def health_check():
    from src.core.startup_checks import run_all_checks
    results = run_all_checks(skip_browser=True)
    failed_critical = [r for r in results if not r.passed and r.critical]
    warnings = [r for r in results if not r.passed and not r.critical]
    return {
        "status": "healthy" if not failed_critical else "degraded",
        "timestamp": time.time(),
        "checks": {r.name: {"ok": r.passed, "message": r.message} for r in results},
        "warnings": len(warnings),
        "errors": len(failed_critical),
    }

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

@app.get("/api/accounts/health")
async def get_all_accounts_health():
    try:
        health = accounts_service.get_all_accounts_health()
        return {"success": True, "data": health}
    except Exception as e:
        logger.error(f"获取全部账号健康度失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/accounts")
async def create_account(account: AccountInfo):
    try:
        ok = accounts_service.add_account(
            account_id=account.id,
            cookie=account.cookie,
            name=account.name,
            priority=account.priority,
        )
        if not ok:
            raise HTTPException(status_code=400, detail="Account already exists")
        if not account.enabled:
            accounts_service.disable_account(account.id)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建账号失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/accounts/{account_id}")
async def update_account(account_id: str, account: AccountInfo):
    try:
        ok = accounts_service.update_account(
            account_id=account_id,
            name=account.name,
            cookie=account.cookie,
            priority=account.priority,
            enabled=account.enabled,
        )
        if not ok:
            raise HTTPException(status_code=404, detail="Account not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新账号失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/accounts/{account_id}")
async def delete_account(account_id: str):
    try:
        ok = accounts_service.remove_account(account_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Account not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除账号失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/accounts/{account_id}/toggle")
async def toggle_account(account_id: str, enabled: bool = True):
    try:
        ok = accounts_service.enable_account(account_id) if enabled else accounts_service.disable_account(account_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Account not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"切换账号状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tasks")
async def list_tasks(enabled_only: bool = False):
    try:
        tasks = [task.to_dict() for task in scheduler_service.list_tasks(enabled_only=enabled_only)]
        return {"success": True, "data": tasks}
    except Exception as e:
        logger.error(f"获取任务列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tasks/status")
async def get_tasks_status():
    try:
        status = scheduler_service.get_scheduler_status()
        return {"success": True, "data": status}
    except Exception as e:
        logger.error(f"获取任务状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tasks")
async def create_task(task: TaskInfo):
    try:
        if task.task_type not in {TaskType.POLISH, TaskType.PUBLISH, TaskType.METRICS, TaskType.CUSTOM}:
            raise HTTPException(status_code=400, detail=f"Invalid task_type: {task.task_type}")

        created = scheduler_service.create_task(
            task_type=task.task_type,
            name=task.name,
            cron_expression=task.cron_expression,
            interval=task.interval,
            params=task.params,
        )
        if not task.enabled:
            scheduler_service.update_task(created.task_id, enabled=False)
            created.enabled = False

        return {"success": True, "data": created.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建任务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/tasks/{task_id}")
async def update_task(task_id: str, task: TaskInfo):
    try:
        existing = scheduler_service.get_task(task_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Task not found")

        ok = scheduler_service.update_task(
            task_id,
            task_type=task.task_type,
            name=task.name or existing.name,
            cron_expression=task.cron_expression,
            interval=task.interval,
            params=task.params,
            enabled=task.enabled,
        )
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to update task")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新任务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tasks/{task_id}/toggle")
async def toggle_task(task_id: str, enabled: bool = True):
    try:
        if not scheduler_service.get_task(task_id):
            raise HTTPException(status_code=404, detail="Task not found")
        ok = scheduler_service.update_task(task_id, enabled=enabled)
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to toggle task")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"切换任务状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tasks/{task_id}/run")
async def run_task(task_id: str):
    try:
        result = await scheduler_service.run_task_now(task_id)
        if not result.get("success", False):
            raise HTTPException(status_code=400, detail=result.get("message", "Run task failed"))
        return {"success": True, "data": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"立即执行任务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str):
    try:
        ok = scheduler_service.delete_task(task_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除任务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/products/publish")
async def publish_product(product: ProductInfo):
    try:
        description = product.description or (
            f"成色：{product.condition or '未提供'}\n"
            f"转手原因：{product.reason or '未提供'}\n"
            f"商品特性：{', '.join(product.features) if product.features else '未提供'}"
        )
        listing = Listing(
            title=product.title or product.name,
            description=description,
            price=product.price,
            category=product.category,
            images=product.images,
            tags=product.tags or ([product.condition] if product.condition else []),
        )
        result = await listing_service.create_listing(listing)
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

@app.get("/api/operations/logs")
async def get_operation_logs(limit: int = 50):
    try:
        logs = await analytics_service.get_operation_logs(limit=limit)
        return {"success": True, "data": logs}
    except Exception as e:
        logger.error(f"获取操作日志失败: {e}")
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
async def get_trend_data(metric: str = "views", days: int = 30):
    try:
        trends = await analytics_service.get_trend_data(metric, days=days)
        return {"success": True, "data": trends}
    except Exception as e:
        logger.error(f"获取趋势数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analytics/products/performance")
async def get_product_performance(days: int = 30):
    try:
        performance = await analytics_service.get_product_performance(days=days)
        return {"success": True, "data": performance}
    except Exception as e:
        logger.error(f"获取商品表现失败: {e}")
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
