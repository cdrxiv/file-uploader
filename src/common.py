import httpx
from fastapi import HTTPException, Request

from .config import get_settings
from .log import get_logger

logger = get_logger()


def check_user(request: Request):
    if 'Bearer' not in request.headers.get('Authorization', ''):
        raise HTTPException(status_code=401, detail='Janeway Bearer token is missing')

    settings = get_settings()
    headers = {'Authorization': request.headers.get('Authorization')}

    # Check if the token is valid by making a request to Janeway
    with httpx.Client(timeout=None) as client:
        response = client.get(
            f'{settings.JANEWAY_URL}/api/user_info/',
            headers=headers,
        )
        if response.status_code != 200:
            error = response.json()
            logger.error(f'Failed to fetch user info: {error}')
            raise HTTPException(
                status_code=response.status_code, detail=error['detail']
            )
    return True
