from fastapi import APIRouter

from app.api.endpoints import (
    bilibili_web,
    douyin_web,
    download,
    hybrid_parsing,
    ios_shortcut,
    r2_upload,
    tiktok_app,
    tiktok_web,
)

router = APIRouter()

# # TikTok routers
# router.include_router(tiktok_web.router, prefix="/tiktok/web", tags=["TikTok-Web-API"])
# router.include_router(tiktok_app.router, prefix="/tiktok/app", tags=["TikTok-App-API"])

# # Douyin routers
# router.include_router(douyin_web.router, prefix="/douyin/web", tags=["Douyin-Web-API"])

# # Bilibili routers
# router.include_router(
#     bilibili_web.router, prefix="/bilibili/web", tags=["Bilibili-Web-API"]
# )

# # Hybrid routers
# router.include_router(hybrid_parsing.router, prefix="/hybrid", tags=["Hybrid-API"])

# # iOS_Shortcut routers
# router.include_router(ios_shortcut.router, prefix="/ios", tags=["iOS-Shortcut"])

# # Download routers
# router.include_router(download.router, tags=["Download"])

# R2 Upload routers
router.include_router(r2_upload.router, prefix="/r2", tags=["R2-Storage"])


# curl -X POST "http://localhost:80/api/r2/parse_and_upload" \
#   -H "Content-Type: application/json" \
#   -H "Auth: shipit2026" \
#   -d '{
#     "url": "https://v.douyin.com/rRPkf-1UKtg/",
#     "quality": "high"
#   }'