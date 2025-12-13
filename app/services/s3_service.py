"""S3 Service - Handle file uploads and downloads to AWS S3"""

import os
from datetime import timedelta
from uuid import UUID

import boto3
from botocore.exceptions import ClientError


class S3Service:
    """Service for handling S3 file operations

    S3 Structure:
    - Documents (hierarchical): users/{user_id}/conversations/{conversation_id}/documents/{document_id}/{filename}
    - Summaries (flat): summaries/{reference_number}.pdf and summaries/{reference_number}.md
    """

    def __init__(self):
        """Initialize S3 client

        Environment variables:
        - AWS_ACCESS_KEY_ID
        - AWS_SECRET_ACCESS_KEY
        - AWS_REGION
        - S3_BUCKET_NAME
        """
        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=os.getenv("AWS_REGION", "eu-central-1"),
        )
        self.bucket_name = os.getenv("S3_BUCKET_NAME", "sumii-mobile-api-local")

    def upload_document(
        self,
        file_content: bytes,
        user_id: UUID,
        conversation_id: UUID,
        document_id: UUID,
        filename: str,
        content_type: str,
    ) -> tuple[str, str]:
        """Upload document to S3 (hierarchical structure)

        Args:
            file_content: File bytes
            user_id: User UUID
            conversation_id: Conversation UUID
            document_id: Document UUID
            filename: Original filename
            content_type: MIME type (server-side detected)

        Returns:
            Tuple of (s3_key, s3_url)
            - s3_key: S3 object key
                (e.g., "users/{user_id}/conversations/{conversation_id}/documents/{document_id}/contract.pdf")
            - s3_url: Pre-signed URL (expires after 7 days)
        """
        # Build hierarchical S3 key
        s3_key = f"users/{user_id}/conversations/{conversation_id}/documents/{document_id}/{filename}"

        # Upload to S3
        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=s3_key,
            Body=file_content,
            ContentType=content_type,
        )

        # Generate pre-signed URL (expires in 7 days)
        s3_url = self.generate_presigned_url(s3_key, expiration_days=7)

        return s3_key, s3_url

    def upload_summary(
        self,
        file_content: bytes,
        reference_number: str,
        file_extension: str,  # "pdf" or "md"
        content_type: str,
    ) -> tuple[str, str]:
        """Upload summary to S3 (flat structure)

        Args:
            file_content: File bytes
            reference_number: Sumii reference number (e.g., "SUM-20250127-ABC12")
            file_extension: "pdf" or "md"
            content_type: MIME type

        Returns:
            Tuple of (s3_key, s3_url)
            - s3_key: S3 object key (e.g., "summaries/SUM-20250127-ABC12.pdf")
            - s3_url: Pre-signed URL (expires after 7 days)
        """
        # Build flat S3 key
        s3_key = f"summaries/{reference_number}.{file_extension}"

        # Upload to S3
        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=s3_key,
            Body=file_content,
            ContentType=content_type,
        )

        # Generate pre-signed URL (expires in 7 days)
        s3_url = self.generate_presigned_url(s3_key, expiration_days=7)

        return s3_key, s3_url

    def generate_presigned_url(self, s3_key: str, expiration_days: int = 7) -> str:
        """Generate pre-signed URL for downloading file

        Args:
            s3_key: S3 object key
            expiration_days: URL expiration in days (default: 7)

        Returns:
            Pre-signed URL string
        """
        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": s3_key},
                ExpiresIn=int(timedelta(days=expiration_days).total_seconds()),
            )
            return url
        except ClientError as e:
            raise Exception(f"Failed to generate pre-signed URL: {e}")

    def delete_object(self, s3_key: str) -> None:
        """Delete object from S3

        Args:
            s3_key: S3 object key to delete
        """
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
        except ClientError as e:
            raise Exception(f"Failed to delete S3 object: {e}")

    def delete_user_data(self, user_id: UUID) -> None:
        """Delete all user data from S3 (GDPR compliance)

        Deletes:
        - All documents: users/{user_id}/**
        - Summaries require separate deletion (need DB query for reference numbers)

        Args:
            user_id: User UUID
        """
        prefix = f"users/{user_id}/"

        # List all objects with this prefix
        try:
            response = self.s3_client.list_objects_v2(Bucket=self.bucket_name, Prefix=prefix)

            if "Contents" in response:
                # Delete all objects
                objects_to_delete = [{"Key": obj["Key"]} for obj in response["Contents"]]
                self.s3_client.delete_objects(Bucket=self.bucket_name, Delete={"Objects": objects_to_delete})
        except ClientError as e:
            raise Exception(f"Failed to delete user data from S3: {e}")


# Dependency injection
def get_s3_service() -> S3Service:
    """FastAPI dependency for S3 service"""
    return S3Service()
