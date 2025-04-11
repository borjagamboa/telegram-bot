import requests
from config.secrets import get_config

telegram_token, wp_url, wp_user, wp_password, _ = get_config()

def publish_to_wordpress(title, content, status='publish'):
    token_resp = requests.post(f"{wp_url}/wp-json/jwt-auth/v1/token", data={
        'username': wp_user,
        'password': wp_password
    })
    token = token_resp.json().get('token')
    headers = {'Authorization': f'Bearer {token}'}
    post = {'title': title, 'status': status, 'content': content}
    response = requests.post(f"{wp_url}/wp-json/wp/v2/posts", headers=headers, json=post)
    if response.status_code == 201:
        return True, response.json()
    return False, response.text
