import typing

import httpx
import pydantic
import pydantic.generics
from fastapi import APIRouter, Depends, HTTPException, Request

from .config import Settings, get_settings
from .log import get_logger

router = APIRouter()
logger = get_logger()


class Preprint(pydantic.BaseModel):
    title: str = 'Placeholder'
    abstract: str | None = None
    stage: typing.Literal['preprint_unsubmitted'] = 'preprint_unsubmitted'
    license: str | None = None
    keywords: list[str] = []
    date_submitted: str | None = None
    date_accepted: str | None = None
    date_published: str | None = None
    doi: str | None = None
    preprint_doi: str | None = None
    authors: list[str] = []
    subject: list[str] = []
    versions: list[str] = []
    supplementary_files: list[str] = []
    additional_field_answers: list[str] = []
    repository: typing.Literal[1] = 1


class Author(pydantic.BaseModel):
    pk: int
    email: str
    first_name: str
    middle_name: str | None = None
    last_name: str
    salutation: str | None = None
    orcid: str | None = None
    institution: str | None = None


T = typing.TypeVar('T')


class Pagination(pydantic.generics.GenericModel, typing.Generic[T]):
    count: int
    next: str | None = None
    previous: str | None = None
    results: list[T]


class License(pydantic.BaseModel):
    pk: int
    name: str
    short_name: str
    text: str
    url: str


class Subject(pydantic.BaseModel):
    name: str


class Keyword(pydantic.BaseModel):
    word: str


class Version(pydantic.BaseModel):
    version: int
    date_time: str
    title: str
    abstract: str | None = None
    public_download_url: str


class SupplementaryFile(pydantic.BaseModel):
    url: str
    label: str


class Field(pydantic.BaseModel):
    pk: int | None = None
    name: str


class AdditionalFieldAnswer(pydantic.BaseModel):
    pk: int | None = None
    answer: str
    field: Field | None = None


class Funder(pydantic.BaseModel):
    funder: str
    award: str | None = None


Stage = typing.Literal[
    'preprint_unsubmitted',
    'preprint_review',
    'preprint_published',
]


class CommonPreprintFields(pydantic.BaseModel):
    pk: int
    keywords: list[Keyword]
    doi: str | None = None
    preprint_doi: str | None = None
    authors: list[Author]
    subject: list[Subject]
    versions: list[Version]
    supplementary_files: list[SupplementaryFile]
    additional_field_answers: list[AdditionalFieldAnswer]
    owner: int


class UnsubmittedPreprint(CommonPreprintFields):
    stage: typing.Literal['preprint_unsubmitted'] = 'preprint_unsubmitted'
    title: str | None = None
    abstract: str | None = None
    license: License | None = None
    date_submitted: None = None
    date_accepted: None = None
    date_published: None = None


class ReviewPreprint(CommonPreprintFields):
    stage: typing.Literal['preprint_review'] = 'preprint_review'
    title: str
    abstract: str
    license: License
    date_submitted: str
    date_accepted: None = None
    date_published: None = None


class PublishedPreprint(CommonPreprintFields):
    stage: typing.Literal['preprint_published'] = 'preprint_published'
    title: str
    abstract: str
    license: License
    date_submitted: str
    date_accepted: str
    date_published: str


PreprintType = UnsubmittedPreprint | ReviewPreprint | PublishedPreprint
UpdateType = typing.Literal['correction', 'metadata_correction', 'version']


class VersionQueue(pydantic.BaseModel):
    preprint: int
    update_type: UpdateType
    title: str
    abstract: str
    date_submitted: str
    date_decision: str | None = None
    published_doi: str | None = None
    approved: bool
    file: int | None = None


class PreprintFile(pydantic.BaseModel):
    pk: int
    preprint: int
    mime_type: str
    original_filename: str
    public_download_url: str
    manager_download_url: str


@router.post('/janeway/create-preprint')
async def create_preprint(
    request: Request, user_id: int, settings: Settings = Depends(get_settings)
):
    headers = {'Authorization': request.headers.get('Authorization')}
    logger.info(f'🚀 Janeway endpoint hit! {headers}')
    async with httpx.AsyncClient(timeout=None) as client:
        data = Preprint().model_dump()
        data['owner'] = user_id
        response = await client.post(
            f'{settings.JANEWAY_URL}/api/user_preprints/', headers=headers, data=data
        )
        if response.status_code not in (200, 201):
            error = response.json()
            logger.error(f'Failed to create preprint: {error}')
            raise HTTPException(status_code=response.status_code, detail=error)
        preprint_data = response.json()
        return preprint_data


@router.post('/janeway/create-author')
async def create_author(
    request: Request, author: Author, settings: Settings = Depends(get_settings)
):
    headers = {'Authorization': request.headers.get('Authorization')}
    logger.info('🚀 Creating author')
    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.post(
            f'{settings.JANEWAY_URL}/api/account/register/',
            headers=headers,
            data=author.model_dump(),
        )
        if response.status_code not in (200, 201):
            error = response.json()
            logger.error(f'Failed to create author: {error}')
            raise HTTPException(status_code=response.status_code, detail=error)
        author_data = response.json()
        return author_data


@router.get('/janeway/search-author')
async def search_author(
    request: Request,
    search: str,
    settings: Settings = Depends(get_settings),
) -> Pagination[Author]:
    headers = {'Authorization': request.headers.get('Authorization')}
    logger.info(f'🚀 Searching author with search = {search}')
    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.get(
            f'{settings.JANEWAY_URL}/api/submission_account_search/?search={search}',
            headers=headers,
        )
        if response.status_code != 200:
            error = response.json()
            logger.error(f'Failed to search author: {error}')
            raise HTTPException(status_code=response.status_code, detail=error)
        author_data = response.json()
        return author_data
