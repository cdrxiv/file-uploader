from __future__ import annotations

import os
import traceback
from contextlib import asynccontextmanager

import httpx
from fastapi import Body, Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

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

        if not response.status_code not in (200, 201):
            error = response.json()
            logger.error(f'Failed to create deposition: {error}')
            return HTTPException(status_code=response.status_code, detail=error)
        deposition_data = response.json()
        return deposition_data


@app.get('/zenodo/fetch-deposition')
async def fetch_deposition(
    deposition_id: int, settings: Settings = Depends(get_settings)
):
    ZENODO_DEPOSITIONS_URL = f'{settings.ZENODO_URL}/api/deposit/depositions'

    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.get(
            f'{ZENODO_DEPOSITIONS_URL}/{deposition_id}',
            headers={'Authorization': f'Bearer {settings.ZENODO_ACCESS_TOKEN}'},
        )
        if response.status_code != 200:
            error = response.json()
            logger.error(f'Failed to fetch deposition: {error}')
            return HTTPException(status_code=response.status_code, detail=error)
        deposition_data = response.json()
        return deposition_data


@app.put('/zenodo/update-deposition')
async def update_deposition(
    deposition_id: int,
    params: dict = Body(default=..., example={'metadata': {'title': 'New title'}}),
    settings: Settings = Depends(get_settings),
):
    ZENODO_DEPOSITIONS_URL = f'{settings.ZENODO_URL}/api/deposit/depositions'
    logger.info(f'Updating deposition {deposition_id} with params: {params}')

    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.put(
            f'{ZENODO_DEPOSITIONS_URL}/{deposition_id}',
            headers={'Authorization': f'Bearer {settings.ZENODO_ACCESS_TOKEN}'},
            json=params,
        )
        if response.status_code != 200:
            error = response.json()
            logger.error(f'Failed to update deposition: {error}')
            return HTTPException(status_code=response.status_code, detail=error)
        deposition_data = response.json()
        return deposition_data


@app.post('/zenodo/create-deposition-version')
async def create_deposition_version(
    deposition_id: int, settings: Settings = Depends(get_settings)
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
            return HTTPException(status_code=response.status_code, detail=error)
        deposition_data = response.json()
        return deposition_data


@app.post('/zenodo/upload-file')
async def upload_file(
    deposition_id: int,
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
):
    logger.info(f'Uploading file {file.filename} to deposition {deposition_id}')
    try:
        with httpx.Client(timeout=None) as client:
            response = client.get(
                f'{settings.ZENODO_URL}/api/deposit/depositions/{deposition_id}',
                headers={'Authorization': f'Bearer {settings.ZENODO_ACCESS_TOKEN}'},
            )
            if response.status_code != 200:
                error = response.json()
                logger.error(f'Failed to fetch deposition: {error}')
                return HTTPException(status_code=response.status_code, detail=error)
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
                return HTTPException(
                    status_code=upload_response.status_code, detail=error
                )
            logger.info(f'Successfully uploaded {file.filename} to Zenodo.')
            resp = client.get(
                f'{settings.ZENODO_URL}/api/deposit/depositions/{deposition_id}',
                headers={'Authorization': f'Bearer {settings.ZENODO_ACCESS_TOKEN}'},
            )
            deposition_data = resp.json()
            return deposition_data

    except Exception as error:
        logger.error(f'Error uploading file: {traceback.format_exc()}')
        return HTTPException(status_code=500, detail=str(error))
