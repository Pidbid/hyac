import os
import sys
import json
from minio import Minio
from minio.error import S3Error


def main():
    MINIO_ENDPOINT = "minio:9000"
    MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
    MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY")
    BUCKET_NAME = "console"

    if not MINIO_ACCESS_KEY or not MINIO_SECRET_KEY:
        print("Error: MinIO access key or secret key is not set.", file=sys.stderr)
        sys.exit(1)

    try:
        client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=False,
        )
    except Exception as e:
        print(f"Error connecting to MinIO: {e}", file=sys.stderr)
        sys.exit(1)

    # 1. Check if bucket exists
    try:
        found = client.bucket_exists(BUCKET_NAME)
        if not found:
            print(f"Bucket '{BUCKET_NAME}' does not exist yet.", file=sys.stderr)
            sys.exit(1)
        print(f"Bucket '{BUCKET_NAME}' exists.")
    except S3Error as e:
        print(f"Error checking bucket existence: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Check bucket policy
    try:
        policy_str = client.get_bucket_policy(BUCKET_NAME)
        policy = json.loads(policy_str)

        is_public_read = False
        for stmt in policy.get("Statement", []):
            if (
                stmt.get("Effect") == "Allow"
                and stmt.get("Principal") == {"AWS": ["*"]}
                and "s3:GetObject" in stmt.get("Action", [])
                and f"arn:aws:s3:::{BUCKET_NAME}/*" in stmt.get("Resource", [])
            ):
                is_public_read = True
                break

        if is_public_read:
            print(f"Bucket '{BUCKET_NAME}' has a public read policy.")
            sys.exit(0)
        else:
            print(f"Bucket '{BUCKET_NAME}' policy is not public yet.", file=sys.stderr)
            sys.exit(1)

    except S3Error as e:
        if e.code == "NoSuchBucketPolicy":
            print(f"No policy found for bucket '{BUCKET_NAME}'.", file=sys.stderr)
            sys.exit(1)
        else:
            print(f"Error getting bucket policy: {e}", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
