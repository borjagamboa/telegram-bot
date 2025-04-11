import os
from google.cloud import secretmanager

def access_secret(secret_id):
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{os.environ.get('PROJECT_ID')}/secrets/{secret_id}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

def get_config():
    try:
        return (
            access_secret('TELEGRAM_TOKEN'),
            access_secret('WORDPRESS_URL'),
            access_secret('WORDPRESS_USER'),
            access_secret('WORDPRESS_PASSWORD'),
            access_secret('OPENAI_API_KEY')
        )
    except Exception:
        return (
            os.getenv('TELEGRAM_TOKEN'),
            os.getenv('WORDPRESS_URL'),
            os.getenv('WORDPRESS_USER'),
            os.getenv('WORDPRESS_PASSWORD'),
            os.getenv('OPENAI_API_KEY')
        )
