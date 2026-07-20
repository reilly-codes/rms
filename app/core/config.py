# app/core/config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "your-fallback-super-secret-key-for-dev")
    ALGORITHM: str = "HS256"
    
    # Expirations (in minutes)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12   # 12 hours
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    
    # Cookie Configurations
    ACCESS_COOKIE_NAME: str = "access_token"
    REFRESH_COOKIE_NAME: str = "refresh_token"
    COOKIE_SECURE: bool = os.getenv("ENVIRONMENT", "development") == "production"

    # Media / uploaded files (expense receipts, mpesa screenshots, etc.)
    MEDIA_ROOT: str = os.getenv("MEDIA_ROOT", "media")
    MEDIA_URL_PREFIX: str = "/media"
    MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", 8))

    # M-Pesa Daraja
    MPESA_ENV: str = os.getenv("MPESA_ENV", "sandbox")  # "sandbox" | "production"
    MPESA_CONSUMER_KEY: str = os.getenv("MPESA_CONSUMER_KEY", "")
    MPESA_CONSUMER_SECRET: str = os.getenv("MPESA_CONSUMER_SECRET", "")
    MPESA_SHORTCODE: str = os.getenv("MPESA_SHORTCODE", "")
    MPESA_PASSKEY: str = os.getenv("MPESA_PASSKEY", "")
    # Base public URL Safaricom can reach, e.g. https://api.rms.oduorys.co.ke
    MPESA_CALLBACK_BASE_URL: str = os.getenv("MPESA_CALLBACK_BASE_URL", "")

    # Subscription billing (mirrors the pattern already proven on ONA24:
    # billing day fixed at onboarding, grace period only on first onboarding,
    # renewals get no grace period)
    SUBSCRIPTION_TRIAL_DAYS: int = int(os.getenv("SUBSCRIPTION_TRIAL_DAYS", 30))
    SUBSCRIPTION_PERIOD_DAYS: int = int(os.getenv("SUBSCRIPTION_PERIOD_DAYS", 30))
    SUBSCRIPTION_ONBOARDING_GRACE_DAYS: int = int(os.getenv("SUBSCRIPTION_ONBOARDING_GRACE_DAYS", 7))
    SUBSCRIPTION_SUSPEND_AFTER_DAYS: int = int(os.getenv("SUBSCRIPTION_SUSPEND_AFTER_DAYS", 60))  # ~2 months unpaid
    SUBSCRIPTION_DELETE_AFTER_SUSPENDED_DAYS: int = int(os.getenv("SUBSCRIPTION_DELETE_AFTER_SUSPENDED_DAYS", 30))

settings = Settings()