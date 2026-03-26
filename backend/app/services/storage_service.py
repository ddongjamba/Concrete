"""
MinIO / AWS S3 스토리지 추상화.

업로드 흐름:
1. generate_presigned_put() → 프론트엔드에 presigned PUT URL 전달
2. 프론트엔드가 해당 URL로 직접 S3에 파일 PUT
3. 완료 후 /confirm 호출

다운로드:
- generate_presigned_get() → 유효기간 1시간 GET URL 반환
"""
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.config import settings

_S3_CLIENT = None


def _get_client():
    global _S3_CLIENT
    if _S3_CLIENT is None:
        _S3_CLIENT = boto3.client(
            "s3",
            endpoint_url=f"{'https' if settings.minio_use_ssl else 'http'}://{settings.minio_endpoint}",
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",  # MinIO는 region 무관
        )
    return _S3_CLIENT


class StorageService:
    def __init__(self):
        self.client = _get_client()
        self.bucket = settings.minio_bucket

    async def generate_presigned_put(self, key: str, content_type: str, expires: int = 3600) -> str:
        """
        파일 업로드용 presigned PUT URL 생성.
        프론트엔드는 이 URL로 Content-Type 헤더와 함께 PUT 요청을 보낸다.
        """
        url = self.client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=expires,
        )
        return url

    async def generate_presigned_get(self, key: str, expires: int = 3600) -> str:
        """결과 이미지/리포트 다운로드용 presigned GET URL 생성."""
        url = self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires,
        )
        return url

    async def delete_object(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except ClientError:
            pass

    def get_public_url(self, key: str) -> str:
        """MinIO public 버킷용 직접 URL (어노테이션 이미지 등)"""
        proto = "https" if settings.minio_use_ssl else "http"
        return f"{proto}://{settings.minio_endpoint}/{self.bucket}/{key}"
