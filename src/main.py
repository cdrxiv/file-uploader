from __future__ import annotations

import os
import tempfile
from contextlib import asynccontextmanager

from fastapi import FastAPI, staticfiles
from fastapi.middleware.cors import CORSMiddleware

from .config import latex_source_directory
from .latex import router as latex_router
from .log import get_logger
from .zenodo import router as zenodo_router

origins = ['*']
logger = get_logger()


directory = latex_source_directory()
directory.mkdir(parents=True, exist_ok=True)
logger.info(
    f'Resolved directory: {directory} | {directory.exists()} | {list(directory.iterdir())}'
)


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


def create_application() -> FastAPI:
    app = FastAPI(lifespan=lifespan_event)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )
    app.include_router(zenodo_router, tags=['zenodo'])
    app.include_router(latex_router, tags=['latex'])
    app.mount(
        '/myst',
        staticfiles.StaticFiles(directory=directory, html=True),
        name='myst',
    )
    return app


app = create_application()


@app.get('/health')
async def health_check():
    return {'status': 'healthy'}
