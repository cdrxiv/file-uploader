from __future__ import annotations

import os
import tempfile
from contextlib import asynccontextmanager

import httpx
from fastapi import Body, Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, format_bytes, get_settings
from .log import get_logger

origins = ['*']
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


@asynccontextmanager
async def lifespan_event(app: FastAPI):
    logger.info('⏱️ Application startup...')
    worker_num = int(os.environ.get('APP_WORKER_ID', 9999))
    logger.info(f'👷 Worker num: {worker_num}')
    tmp_dir = tempfile.gettempdir()
    tmp_dir_env = os.environ.get('TMPDIR', '')
    logger.info(
        f'📂 Temp directory: {tmp_dir} | $TMPDIR: {tmp_dir_env} | {tmp_dir.strip() == tmp_dir_env.strip()}'
    )
    yield
    logger.info('Application shutdown...')
    logger.info('👋 Goodbye!')


app = FastAPI(lifespan=lifespan_event)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.get('/health')
async def health_check():
    return {'status': 'healthy'}


@app.get('/zenodo/create-deposition')
async def create_deposition(
    request: Request,
    settings: Settings = Depends(get_settings),
    authorized: bool = Depends(check_user),
):
    logger.info('Creating zenodo deposition')
    ZENODO_DEPOSITIONS_URL = f'{settings.ZENODO_URL}/api/deposit/depositions'

    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.post(
            ZENODO_DEPOSITIONS_URL,
            headers={
                'Authorization': f'Bearer {settings.ZENODO_ACCESS_TOKEN}',
                'Content-Type': 'application/json',
            },
            json={
                'metadata': {
                    'upload_type': 'dataset',
                    'communities': [{'identifier': 'cdrxiv'}],
                },
            },
        )

        if response.status_code not in (200, 201):
            error = response.json()
            logger.info(
                f'Found error Status code: {response.status_code} in response: {error}'
            )
            logger.error(f'Failed to create deposition: {error}')
            raise HTTPException(
                status_code=response.status_code, detail=error['message']
            )
        deposition_data = response.json()
        return deposition_data


@app.get('/zenodo/fetch-deposition')
async def fetch_deposition(
    request: Request,
    deposition_id: int,
    settings: Settings = Depends(get_settings),
    authorized: bool = Depends(check_user),
):
    logger.info(f'Fetching deposition with deposition_id: {deposition_id}')
    ZENODO_DEPOSITIONS_URL = f'{settings.ZENODO_URL}/api/deposit/depositions'

    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.get(
            f'{ZENODO_DEPOSITIONS_URL}/{deposition_id}',
            headers={'Authorization': f'Bearer {settings.ZENODO_ACCESS_TOKEN}'},
        )
        if response.status_code != 200:
            error = response.json()
            logger.error(f'Failed to fetch deposition: {error}')
            raise HTTPException(
                status_code=response.status_code, detail=error['message']
            )
        deposition_data = response.json()
        return deposition_data


@app.put('/zenodo/update-deposition')
async def update_deposition(
    request: Request,
    deposition_id: int,
    params: dict = Body(default=..., example={'metadata': {'title': 'New title'}}),
    settings: Settings = Depends(get_settings),
    authorized: bool = Depends(check_user),
):
    logger.info(f'Updating deposition {deposition_id} with params: {params}')
    ZENODO_DEPOSITIONS_URL = f'{settings.ZENODO_URL}/api/deposit/depositions'

    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.put(
            f'{ZENODO_DEPOSITIONS_URL}/{deposition_id}',
            headers={'Authorization': f'Bearer {settings.ZENODO_ACCESS_TOKEN}'},
            json=params,
        )
        if response.status_code != 200:
            error = response.json()
            logger.error(f'Failed to update deposition: {error}')
            raise HTTPException(
                status_code=response.status_code, detail=error['message']
            )
        deposition_data = response.json()
        return deposition_data


@app.post('/zenodo/create-deposition-version')
async def create_deposition_version(
    request: Request,
    deposition_id: int,
    settings: Settings = Depends(get_settings),
    authorized: bool = Depends(check_user),
):
    ZENODO_DEPOSITIONS_URL = f'{settings.ZENODO_URL}/api/deposit/depositions'

    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.post(
            f'{ZENODO_DEPOSITIONS_URL}/{deposition_id}/actions/newversion',
            headers={'Authorization': f'Bearer {settings.ZENODO_ACCESS_TOKEN}'},
        )
        if response.status_code != 201:
            error = response.json()
            logger.error(f'Failed to create new version: {error}')
            raise HTTPException(
                status_code=response.status_code, detail=error['message']
            )
        deposition_data = response.json()
        return deposition_data


@app.post('/zenodo/upload-file')
async def upload_file(
    request: Request,
    deposition_id: int,
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
    authorized: bool = Depends(check_user),
):
    logger.info(
        f'Uploading file {file.filename} with size: {format_bytes(file.size)} to deposition {deposition_id}'
    )
    if file.size > settings.ZENODO_MAX_FILE_SIZE:
        logger.error(f'File size exceeds the limit: {settings.ZENODO_MAX_FILE_SIZE}')
        raise HTTPException(
            status_code=413,
            detail=f'File size: {format_bytes(file.size)} exceeds the limit: {format_bytes(settings.ZENODO_MAX_FILE_SIZE)}',
        )
    with httpx.Client(timeout=None) as client:
        response = client.get(
            f'{settings.ZENODO_URL}/api/deposit/depositions/{deposition_id}',
            headers={'Authorization': f'Bearer {settings.ZENODO_ACCESS_TOKEN}'},
        )
        if response.status_code != 200:
            error = response.json()
            logger.error(f'Failed to fetch deposition: {error}')
            raise HTTPException(
                status_code=response.status_code, detail=error['message']
            )
        deposition_data = response.json()
        bucket_url = deposition_data['links']['bucket']

        url = f'{bucket_url}/{file.filename}'
        file.file.seek(0)

        upload_response = client.put(
            url,
            headers={'Authorization': f'Bearer {settings.ZENODO_ACCESS_TOKEN}'},
            content=file.file,
        )
        if upload_response.status_code not in (200, 201):
            error = upload_response.json()
            logger.error(f'Failed to upload file to Zenodo: {error}')
            raise HTTPException(
                status_code=upload_response.status_code, detail=error['message']
            )
        logger.info(f'Successfully uploaded {file.filename} to Zenodo.')
        resp = client.get(
            f'{settings.ZENODO_URL}/api/deposit/depositions/{deposition_id}',
            headers={'Authorization': f'Bearer {settings.ZENODO_ACCESS_TOKEN}'},
        )
        deposition_data = resp.json()
        return deposition_data
