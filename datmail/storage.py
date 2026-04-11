import boto3
import datetime
from emailtunnel import logger
from datmail.config import S3_ENDPOINT_URL, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY

class Storage:
    def __init__(self, bucket_name, region):
        self.bucket_name = bucket_name
        self.s3_client = boto3.client(
            's3',
            endpoint_url=S3_ENDPOINT_URL,
            aws_access_key_id=S3_ACCESS_KEY_ID,
            aws_secret_access_key=S3_SECRET_ACCESS_KEY,
            region_name=region
        )

    def upload_object(self, body, object_name):
        try:
            self.s3_client.put_object(
                Body=body,
                Bucket=self.bucket_name,
                Key=object_name,
                Expires=datetime.datetime.now() + datetime.timedelta(days=90)
            )

            logger.info(f"File {object_name} uploaded to {self.bucket_name}/{object_name} with expiration in 90 days.")
        except Exception as e:
            logger.error(f"Error uploading file: {e}")