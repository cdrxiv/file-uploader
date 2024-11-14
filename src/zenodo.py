import httpx
import pydantic
from fastapi import APIRouter, Body, Depends, File, HTTPException, Request, UploadFile

from .common import check_user
from .config import Settings, format_bytes, get_settings
from .log import get_logger

logger = get_logger()
router = APIRouter()


class Creator(pydantic.BaseModel):
    name: str
    affiliation: str | None = None
    orcid: str | None = None
    gnd: str | None = None


class RelatedIdentifier(pydantic.BaseModel):
    identifier: str
    relation: str
    resource_type: str | None = None


class Subject(pydantic.BaseModel):
    term: str
    identifier: str


class DepositionFileLinks(pydantic.BaseModel):
    self: str
    discard: str


class DepositionFile(pydantic.BaseModel):
    id: str
    filename: str
    filesize: int
    checksum: str
    links: DepositionFileLinks


class Metadata(pydantic.BaseModel):
    upload_type: str
    title: str
    creators: list[Creator]
    description: str
    doi: str | None = None
    keywords: list[str] | None = None
    related_identifiers: list[RelatedIdentifier] | None = None
    communities: list[dict]
    subjects: list[Subject] | None = None
    license: str


class DepositionLInks(pydantic.BaseModel):
    self: str
    newversion: str


class Deposition(pydantic.BaseModel):
    created: str
    id: int
    metadata: Metadata | None = None
    files: list[DepositionFile]
    links: DepositionLInks
    submitted: bool


@router.get('/zenodo/create-deposition')
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


@router.get('/zenodo/fetch-deposition')
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


@router.put('/zenodo/update-deposition', response_model=Deposition)
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


@router.post('/zenodo/create-deposition-version')
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


@router.post('/zenodo/upload-file', response_model=Deposition)
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
