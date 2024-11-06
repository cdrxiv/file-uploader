from __future__ import annotations

import os
from contextlib import asynccontextmanager

import aiohttp
from fastapi import Depends, FastAPI, File, UploadFile
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


@app.post('/zenodo/')
async def zenodo(
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
):
    logger.info(f'Received file: {file.filename}')

    ZENODO_DEPOSITIONS_URL = f'{settings.ZENODO_URL}/api/deposit/depositions'
    ZENODO_ACCESS_TOKEN = settings.ZENODO_ACCESS_TOKEN

    async with aiohttp.ClientSession() as session:
        # Step 1: Create a new deposition to get the bucket URL
        async with session.post(
            ZENODO_DEPOSITIONS_URL,
            headers={'Authorization': f'Bearer {ZENODO_ACCESS_TOKEN}'},
            json={},
        ) as resp:
            if resp.status != 201:
                error = await resp.json()
                logger.error(f'Failed to create deposition: {error}')
                return {'error': error}
            deposition_data = await resp.json()
            bucket_url = deposition_data['links']['bucket']

        # Step 2: Upload file directly with correct content type
        file_url = f'{bucket_url}/{file.filename}'
        headers = {
            'Authorization': f'Bearer {ZENODO_ACCESS_TOKEN}',
            'Content-Type': 'application/octet-stream',
        }

        # Read file content
        file_content = await file.read()

        # Step 3: Upload to Zenodo's bucket URL
        async with session.put(
            file_url, headers=headers, data=file_content
        ) as upload_resp:
            if upload_resp.status not in (200, 201):
                error = await upload_resp.json()
                logger.error(f'Failed to upload file to Zenodo: {error}')
                return {'error': error}
            logger.info(f'Successfully uploaded {file.filename} to Zenodo.')

        # Step 4: Get the deposition info
        async with session.get(
            f"{ZENODO_DEPOSITIONS_URL}/{deposition_data['id']}",
            headers={'Authorization': f'Bearer {ZENODO_ACCESS_TOKEN}'},
        ) as resp:
            deposition_data = await resp.json()

            return deposition_data
