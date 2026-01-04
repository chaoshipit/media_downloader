# ==============================================================================
# Cloudflare R2 视频上传 API
# 从抖音 URL 解析视频信息，下载视频并上传到 R2 存储
# ==============================================================================

import os
from datetime import datetime

import boto3
import httpx
import yaml
from botocore.config import Config
from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.models.APIResponseModel import ErrorResponseModel, ResponseModel
from crawlers.hybrid.hybrid_crawler import HybridCrawler

# 固定认证 Token
AUTH_TOKEN = "shipit2026"

# 读取配置文件
config_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../config.yaml")
)
with open(config_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# 获取 R2 配置
r2_config = config.get("R2", {})

router = APIRouter()
HybridCrawler = HybridCrawler()


def verify_auth(auth: str = Header(None, alias="Auth")):
    """验证 Auth Header"""
    if auth != AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="未认证：无效的 Auth Token")
    return auth


# 请求模型
class ParseAndUploadRequest(BaseModel):
    url: str = Field(
        ...,
        description="抖音视频链接或分享文本",
        example="https://v.douyin.com/L4FJNR3/",
    )
    quality: str = Field(default="high", description="视频质量: high/low/watermark")


def get_r2_client():
    """
    创建并返回 R2 S3 客户端
    """
    return boto3.client(
        "s3",
        endpoint_url=r2_config.get("endpoint_url"),
        aws_access_key_id=r2_config.get("access_key_id"),
        aws_secret_access_key=r2_config.get("secret_access_key"),
        region_name=r2_config.get("region", "auto"),
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


async def download_video(url: str, headers: dict = None) -> bytes:
    """
    下载视频文件

    Args:
        url: 视频 URL
        headers: 可选的请求头

    Returns:
        视频文件的字节内容
    """
    default_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Referer": "https://www.douyin.com/",
    }
    if headers:
        default_headers.update(headers)

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        response = await client.get(url, headers=default_headers)
        response.raise_for_status()
        return response.content


def upload_to_r2(
    file_content: bytes, object_key: str, content_type: str = "video/mp4"
) -> str:
    """
    上传文件到 R2

    Args:
        file_content: 文件内容
        object_key: R2 中的对象路径
        content_type: 文件 MIME 类型

    Returns:
        上传后的对象路径
    """
    s3_client = get_r2_client()
    bucket_name = r2_config.get("bucket_name", "douyin-videos")

    s3_client.put_object(
        Bucket=bucket_name, Key=object_key, Body=file_content, ContentType=content_type
    )

    return object_key


def generate_presigned_url(object_key: str, expires_in: int = 3600) -> str:
    """
    生成预签名下载 URL

    Args:
        object_key: R2 中的对象路径
        expires_in: URL 有效期（秒），默认 1 小时

    Returns:
        预签名 URL
    """
    s3_client = get_r2_client()
    bucket_name = r2_config.get("bucket_name", "douyin-videos")

    url = s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket_name, "Key": object_key},
        ExpiresIn=expires_in,
    )
    return url


def sanitize_filename(desc: str, max_length: int = 50) -> str:
    """
    清理描述文本，生成安全的文件名

    Args:
        desc: 视频描述
        max_length: 最大长度

    Returns:
        安全的文件名
    """
    if not desc:
        return "video"

    # 移除不安全的字符
    unsafe_chars = ["/", "\\", ":", "*", "?", '"', "<", ">", "|", "\n", "\r", "#", "@"]
    safe_desc = desc
    for char in unsafe_chars:
        safe_desc = safe_desc.replace(char, "_")

    # 移除连续的下划线和空格
    while "__" in safe_desc:
        safe_desc = safe_desc.replace("__", "_")
    safe_desc = safe_desc.strip("_ ")

    # 截断到最大长度
    if len(safe_desc) > max_length:
        safe_desc = safe_desc[:max_length]

    return safe_desc if safe_desc else "video"


@router.post(
    "/parse_and_upload",
    response_model=ResponseModel,
    summary="解析抖音视频并上传到R2/Parse Douyin video and upload to R2",
)
async def parse_and_upload_to_r2(
    request: Request,
    body: ParseAndUploadRequest,
    auth: str = Header(..., alias="Auth", description="认证 Token"),
):
    """
    # [中文]
    ### 用途:
    - 解析抖音视频链接，下载视频并上传到 Cloudflare R2 存储
    - 返回视频信息和私有下载链接

    ### 参数:
    - url: 抖音视频链接或分享文本
    - quality: 视频质量选择
      - high: 高清无水印
      - low: 普通无水印
      - watermark: 有水印
    - expires_in: 预签名URL有效期(秒)

    ### 返回:
    - video_info: 视频基本信息
    - r2_path: R2 存储路径
    - download_url: 预签名下载链接

    # [English]
    ### Purpose:
    - Parse Douyin video link, download and upload to Cloudflare R2
    - Return video info and private download URL

    ### Parameters:
    - url: Douyin video link or share text
    - quality: Video quality (high/low/watermark)
    - expires_in: Presigned URL expiration time (seconds)

    ### Returns:
    - video_info: Basic video information
    - r2_path: R2 storage path
    - download_url: Presigned download URL

    # [示例/Example]
    url = "https://v.douyin.com/L4FJNR3/"
    """
    # 验证认证
    if auth != AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="未认证：无效的 Auth Token")

    try:
        # 1. 解析视频信息
        video_data = await HybridCrawler.hybrid_parsing_single_video(
            url=body.url, minimal=True
        )

        # 检查是否解析成功
        if not video_data:
            raise ValueError("无法解析视频信息")

        # 检查是否是视频类型
        if video_data.get("type") != "video":
            raise ValueError(
                f"当前仅支持视频类型，检测到类型: {video_data.get('type')}"
            )

        # 2. 获取视频下载链接
        video_urls = video_data.get("video_data", {})
        if body.quality == "high":
            download_url = video_urls.get("nwm_video_url_HQ") or video_urls.get(
                "nwm_video_url"
            )
        elif body.quality == "low":
            download_url = video_urls.get("nwm_video_url") or video_urls.get(
                "nwm_video_url_HQ"
            )
        else:  # watermark
            download_url = video_urls.get("wm_video_url_HQ") or video_urls.get(
                "wm_video_url"
            )

        if not download_url:
            raise ValueError("无法获取视频下载链接")

        # 3. 下载视频
        video_content = await download_video(download_url)

        if not video_content:
            raise ValueError("视频下载失败")

        # 4. 生成 R2 存储路径 (年/月/日/video_id.mp4)
        now = datetime.now()
        date_path = now.strftime("%Y/%m/%d")

        video_id = video_data.get("video_id", "unknown")
        desc = video_data.get("desc", "")

        # 生成文件名
        filename = f"{video_id}.mp4"
        object_key = f"douyin/{date_path}/{filename}"

        # 5. 上传到 R2
        upload_to_r2(video_content, object_key)

        # 6. 构建返回数据
        result = {
            "video_info": {
                "video_id": video_id,
                "desc": desc,
                "platform": video_data.get("platform"),
                "type": video_data.get("type"),
                "create_time": video_data.get("create_time"),
                "author": video_data.get("author", {}).get("nickname")
                if isinstance(video_data.get("author"), dict)
                else None,
                "statistics": video_data.get("statistics"),
                "cover": video_data.get("cover_data", {}).get("cover"),
            },
            "r2_storage": {
                "bucket": r2_config.get("bucket_name"),
                "path": object_key,
                "file_size": len(video_content),
                "file_size_mb": round(len(video_content) / 1024 / 1024, 2),
            },
            "quality": body.quality,
        }

        return ResponseModel(code=200, router=request.url.path, data=result)

    except ValueError as e:
        status_code = 400
        detail = ErrorResponseModel(
            code=status_code,
            router=request.url.path,
            params=dict(request.query_params),
        )
        raise HTTPException(status_code=status_code, detail=str(e))

    except Exception as e:
        status_code = 500
        detail = ErrorResponseModel(
            code=status_code,
            router=request.url.path,
            params=dict(request.query_params),
        )
        raise HTTPException(status_code=status_code, detail=f"处理失败: {str(e)}")


@router.get(
    "/list_videos",
    response_model=ResponseModel,
    summary="列出R2中的视频/List videos in R2",
)
async def list_r2_videos(
    request: Request,
    prefix: str = Query(default="douyin/", description="路径前缀，用于筛选"),
    max_keys: int = Query(default=100, description="最大返回数量"),
):
    """
    # [中文]
    ### 用途:
    - 列出 R2 存储中的视频文件

    ### 参数:
    - prefix: 路径前缀筛选
    - max_keys: 最大返回数量

    ### 返回:
    - 视频文件列表
    """
    try:
        s3_client = get_r2_client()
        bucket_name = r2_config.get("bucket_name", "douyin-videos")

        response = s3_client.list_objects_v2(
            Bucket=bucket_name, Prefix=prefix, MaxKeys=max_keys
        )

        videos = []
        for obj in response.get("Contents", []):
            videos.append(
                {
                    "key": obj["Key"],
                    "size": obj["Size"],
                    "size_mb": round(obj["Size"] / 1024 / 1024, 2),
                    "last_modified": obj["LastModified"].isoformat(),
                }
            )

        return ResponseModel(
            code=200,
            router=request.url.path,
            data={"count": len(videos), "videos": videos},
        )

    except Exception as e:
        status_code = 500
        raise HTTPException(status_code=status_code, detail=f"获取列表失败: {str(e)}")


@router.get(
    "/get_download_url",
    response_model=ResponseModel,
    summary="获取视频下载链接/Get video download URL",
)
async def get_video_download_url(
    request: Request,
    path: str = Query(
        example="douyin/2026/01/04/7298145681699622182_视频描述_120000.mp4",
        description="R2 中的视频路径",
    ),
    expires_in: int = Query(default=3600, description="预签名URL有效期(秒)"),
):
    """
    # [中文]
    ### 用途:
    - 根据 R2 路径生成预签名下载链接

    ### 参数:
    - path: R2 中的视频路径
    - expires_in: URL 有效期(秒)

    ### 返回:
    - 预签名下载链接
    """
    try:
        presigned_url = generate_presigned_url(path, expires_in)

        return ResponseModel(
            code=200,
            router=request.url.path,
            data={
                "path": path,
                "download_url": presigned_url,
                "expires_in": expires_in,
            },
        )

    except Exception as e:
        status_code = 500
        raise HTTPException(status_code=status_code, detail=f"生成链接失败: {str(e)}")
