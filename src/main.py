from __future__ import annotations

import os
from contextlib import asynccontextmanager

import aiohttp
from fastapi import Body, Depends, FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import Settings, get_settings
from .log import get_logger

origins = ['*']
logger = get_logger()


@asynccontextmanager
async def lifespan_event(app: FastAPI):
    logger.info('⏱️ Application startup...')
    worker_num = int(os.environ.get('APP_WORKER_ID', 9999))
    logger.info(f'👷 Worker num: {worker_num}')
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


@app.get('/zenodo/create-deposition')
async def create_deposition(settings: Settings = Depends(get_settings)):
    ZENODO_DEPOSITIONS_URL = f'{settings.ZENODO_URL}/api/deposit/depositions'
    ZENODO_ACCESS_TOKEN = settings.ZENODO_ACCESS_TOKEN

    async with aiohttp.ClientSession() as session:
        async with session.post(
            ZENODO_DEPOSITIONS_URL,
            headers={
                'Authorization': f'Bearer {ZENODO_ACCESS_TOKEN}',
                'Content-Type': 'application/json',
            },
            json={
                'metadata': {
                    'upload_type': 'dataset',
                    'communities': [{'identifier': 'cdrxiv'}],
                },
            },
        ) as resp:
            if not resp.ok:
                error = await resp.json()
                logger.error(f'Failed to create deposition: {error}')
                return {'error': error}
            deposition_data = await resp.json()
            return deposition_data


@app.get('/zenodo/fetch-deposition')
async def fetch_deposition(
    deposition_id: int, settings: Settings = Depends(get_settings)
):
    ZENODO_DEPOSITIONS_URL = f'{settings.ZENODO_URL}/api/deposit/depositions'
    ZENODO_ACCESS_TOKEN = settings.ZENODO_ACCESS_TOKEN

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f'{ZENODO_DEPOSITIONS_URL}/{deposition_id}',
            headers={'Authorization': f'Bearer {ZENODO_ACCESS_TOKEN}'},
        ) as resp:
            if resp.status != 200:
                error = await resp.json()
                logger.error(f'Failed to fetch deposition: {error}')
                return {'error': error}
            deposition_data = await resp.json()
            return deposition_data


@app.put('/zenodo/update-deposition')
async def update_deposition(
    deposition_id: int,
    params: dict = Body(default=..., example={'metadata': {'title': 'New title'}}),
    settings: Settings = Depends(get_settings),
):
    ZENODO_DEPOSITIONS_URL = f'{settings.ZENODO_URL}/api/deposit/depositions'
    ZENODO_ACCESS_TOKEN = settings.ZENODO_ACCESS_TOKEN
    logger.info(f'Updating deposition {deposition_id} with params: {params}')

    async with aiohttp.ClientSession() as session:
        async with session.put(
            f'{ZENODO_DEPOSITIONS_URL}/{deposition_id}',
            headers={'Authorization': f'Bearer {ZENODO_ACCESS_TOKEN}'},
            json=params,
        ) as resp:
            if resp.status != 200:
                error = await resp.json()
                logger.error(f'Failed to update deposition: {error}')
                return {'error': error}
            deposition_data = await resp.json()
            return deposition_data


@app.post('/zenodo/create-deposition-version')
async def create_deposition_version(
    deposition_id: int, settings: Settings = Depends(get_settings)
):
    ZENODO_DEPOSITIONS_URL = f'{settings.ZENODO_URL}/api/deposit/depositions'
    ZENODO_ACCESS_TOKEN = settings.ZENODO_ACCESS_TOKEN

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f'{ZENODO_DEPOSITIONS_URL}/{deposition_id}/actions/newversion',
            headers={'Authorization': f'Bearer {ZENODO_ACCESS_TOKEN}'},
        ) as resp:
            if resp.status != 201:
                error = await resp.json()
                logger.error(f'Failed to create new version: {error}')
                return {'error': error}
            deposition_data = await resp.json()
            return deposition_data


@app.post('/zenodo/upload-file')
async def upload_file(
    deposition_id: int,
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'{settings.ZENODO_URL}/api/deposit/depositions/{deposition_id}',
                headers={'Authorization': f'Bearer {settings.ZENODO_ACCESS_TOKEN}'},
            ) as resp:
                if resp.status != 200:
                    error = await resp.json()
                    logger.error(f'Failed to fetch deposition: {error}')
                    return {'error': error}
                deposition_data = await resp.json()
                bucket_url = deposition_data['links']['bucket']

            file_content = await file.read()
            url = f'{bucket_url}/{file.filename}'
            async with session.put(
                url,
                headers={'Authorization': f'Bearer {settings.ZENODO_ACCESS_TOKEN}'},
                data=file_content,
            ) as upload_resp:
                if upload_resp.status not in (200, 201):
                    error = await upload_resp.json()
                    logger.error(f'Failed to upload file to Zenodo: {error}')
                    return {'error': error}
                logger.info(f'Successfully uploaded {file.filename} to Zenodo.')
                async with session.get(
                    f'{settings.ZENODO_URL}/api/deposit/depositions/{deposition_id}',
                    headers={'Authorization': f'Bearer {settings.ZENODO_ACCESS_TOKEN}'},
                ) as resp:
                    deposition_data = await resp.json()
                    return deposition_data

    except Exception as error:
        logger.error(f'Error uploading file: {str(error)}')
        return JSONResponse(status_code=500, content={'error': 'Internal server error'})
