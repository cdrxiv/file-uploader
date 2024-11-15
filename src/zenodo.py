import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from .common import check_user
from .config import Settings, format_bytes, get_settings
from .log import get_logger

logger = get_logger()
router = APIRouter()


@router.post('/zenodo/upload-file')
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

    try:
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

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f'Failed to upload file to Zenodo: {e}')
        raise HTTPException(
            status_code=500, detail=f'Failed to upload file to Zenodo: {str(e)}'
        )
