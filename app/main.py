# app/main.py
import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Import core lifespans and configurations cleanly
from app.core.database import lifespan
from app.core.config import settings
from app.api import api_router

# 1. Environment and App Setup
load_dotenv()
env_mode = os.getenv("ENVIRONMENT", "development")

app_kwargs = {
    "lifespan": lifespan,
    "title": "Property Management System API",
    "version": "1.0.0"
}

# Production adjustments
if env_mode == "production":
    app_kwargs["root_path"] = "/api"
    app_kwargs["servers"] = [
        {"url": "https://rms.oduorys.co.ke/api", "description": "Production"}
    ]

app = FastAPI(**app_kwargs)

# 2. Clean CORS Configuration
origin_strings = os.getenv("ALLOWED_FRONTENDS", "http://142.93.101.12")
origins = [origin.strip() for origin in origin_strings.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,   
    allow_credentials=True,  
    allow_methods=["*"],     
    allow_headers=["*"],     
)

# 3. Mount all API Routes
app.include_router(api_router)

# 4. Serve uploaded receipt/expense photos (relative paths stored in DB,
#    e.g. "expenses/ab12cd.jpg" -> served at /media/expenses/ab12cd.jpg)
os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
app.mount(settings.MEDIA_URL_PREFIX, StaticFiles(directory=settings.MEDIA_ROOT), name="media")