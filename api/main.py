"""NFPC Reports - FastAPI Backend."""
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from api.warmup import start_warmup_thread

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: pre-warm query cache in background
    start_warmup_thread()
    yield
    # Shutdown: nothing to clean up

from api.routes import (
    dashboard, sales_performance, top_customers, top_products,
    market_sales, target_achievement, endorsement, daily_sales_overview,
    mtd_wastage, weekly_sales_returns, brand_wise_sales, mtd_sales_overview,
    log_report, time_management, customer_attendance, mtd_attendance,
    journey_plan_compliance, outstanding_collection, eot_status,
    productivity_coverage, salesman_journey, revenue_dispersion,
    monthly_sales_stock, filters
)

app = FastAPI(title="NFPC Reports API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Filter dropdown data
app.include_router(filters.router, prefix="/api", tags=["Filters"])

# Report endpoints
app.include_router(dashboard.router, prefix="/api", tags=["Dashboard"])
app.include_router(sales_performance.router, prefix="/api", tags=["Sales Performance"])
app.include_router(top_customers.router, prefix="/api", tags=["Top Customers"])
app.include_router(top_products.router, prefix="/api", tags=["Top Products"])
app.include_router(market_sales.router, prefix="/api", tags=["Market Sales"])
app.include_router(target_achievement.router, prefix="/api", tags=["Target vs Achievement"])
app.include_router(endorsement.router, prefix="/api", tags=["Endorsement"])
app.include_router(daily_sales_overview.router, prefix="/api", tags=["Daily Sales Overview"])
app.include_router(mtd_wastage.router, prefix="/api", tags=["MTD Wastage"])
app.include_router(weekly_sales_returns.router, prefix="/api", tags=["Weekly Sales Returns"])
app.include_router(brand_wise_sales.router, prefix="/api", tags=["Brand Wise Sales"])
app.include_router(mtd_sales_overview.router, prefix="/api", tags=["MTD Sales Overview"])
app.include_router(log_report.router, prefix="/api", tags=["Log Report"])
app.include_router(time_management.router, prefix="/api", tags=["Time Management"])
app.include_router(customer_attendance.router, prefix="/api", tags=["Customer Attendance"])
app.include_router(mtd_attendance.router, prefix="/api", tags=["MTD Attendance"])
app.include_router(journey_plan_compliance.router, prefix="/api", tags=["Journey Plan Compliance"])
app.include_router(outstanding_collection.router, prefix="/api", tags=["Outstanding Collection"])
app.include_router(eot_status.router, prefix="/api", tags=["EOT Status"])
app.include_router(productivity_coverage.router, prefix="/api", tags=["Productivity & Coverage"])
app.include_router(salesman_journey.router, prefix="/api", tags=["Salesman Journey"])
app.include_router(revenue_dispersion.router, prefix="/api", tags=["Revenue Dispersion"])
app.include_router(monthly_sales_stock.router, prefix="/api", tags=["Monthly Sales Stock"])

@app.get("/api/health")
def health():
    return {"status": "ok"}

# Serve frontend static files (after all API routes)
_frontend_dir = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'dist')
if os.path.isdir(_frontend_dir):
    _frontend_dir = os.path.abspath(_frontend_dir)
    app.mount("/assets", StaticFiles(directory=os.path.join(_frontend_dir, "assets")), name="static-assets")

    @app.get("/{path:path}")
    async def serve_spa(path: str):
        file_path = os.path.join(_frontend_dir, path)
        if path and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(_frontend_dir, "index.html"))
