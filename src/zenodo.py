import asyncio
import traceback
from concurrent.futures import ThreadPoolExecutor

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .common import check_user
from .config import Settings, format_bytes, get_settings
from .log import get_logger

logger = get_logger()
router = APIRouter()


executor = ThreadPoolExecutor(max_workers=2)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type(
        (httpx.RemoteProtocolError, httpx.ReadTimeout, httpx.ConnectTimeout)
    ),
)
def upload_file_sync(client, url, headers, file):
    response = client.put(url, headers=headers, content=file.file)
    response.raise_for_status()
    return response


@router.post('/zenodo/upload-file')
async def upload_file(
    request: Request,
    deposition_id: int,
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
    authorized: bool = Depends(check_user),
):
    logger.info(
        f'🚀 Uploading file {file.filename} with size: {format_bytes(file.size)} to deposition {deposition_id}'
    )

    if file.size > settings.ZENODO_MAX_FILE_SIZE:
        logger.error(f'❌ File size exceeds the limit: {settings.ZENODO_MAX_FILE_SIZE}')
        raise HTTPException(
            status_code=413,
            detail=f'📁 File size: {format_bytes(file.size)} exceeds the limit: {format_bytes(settings.ZENODO_MAX_FILE_SIZE)}',
        )

    try:
        with httpx.Client(timeout=None) as client:
            # Fetch deposition
            response = client.get(
                f'{settings.ZENODO_URL}/api/deposit/depositions/{deposition_id}',
                headers={'Authorization': f'Bearer {settings.ZENODO_ACCESS_TOKEN}'},
            )
            response.raise_for_status()
            deposition_data = response.json()
            bucket_url = deposition_data['links']['bucket']

            # Upload file in a separate thread
            url = f'{bucket_url}/{file.filename}'
            file.file.seek(0)

            loop = asyncio.get_event_loop()
            upload_future = loop.run_in_executor(
                executor,
                upload_file_sync,
                client,
                url,
                {'Authorization': f'Bearer {settings.ZENODO_ACCESS_TOKEN}'},
                file,
            )

            # Monitor for cancellation
            while not upload_future.done():
                await asyncio.sleep(1)
                if await request.is_disconnected():
                    logger.warning(
                        f'🚫 Request to upload {file.filename} to Zenodo was cancelled due to client disconnection.'
                    )
                    # Cancel the future (though it may not stop immediately)
                    upload_future.cancel()
                    raise HTTPException(
                        status_code=499,
                        detail='Client Closed Request',
                    )

            upload_response = await upload_future

            logger.info(f'✅ Successfully uploaded {file.filename} to Zenodo.')

            # Fetch updated deposition data
            resp = client.get(
                f'{settings.ZENODO_URL}/api/deposit/depositions/{deposition_id}',
                headers={'Authorization': f'Bearer {settings.ZENODO_ACCESS_TOKEN}'},
            )
            resp.raise_for_status()
            deposition_data = resp.json()
            return deposition_data

    except httpx.HTTPStatusError as e:
        logger.error(
            f'❌ HTTP error occurred: {e.response.status_code} - {e.response.text}: {traceback.format_exc()}'
        )
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f'🔥 Zenodo API error: {e.response.json().get("message", str(e))}',
        )

    except (httpx.RemoteProtocolError, httpx.ReadTimeout, httpx.ConnectTimeout):
        logger.error(f'❌ Network error occurred: {traceback.format_exc()}')
        raise HTTPException(
            status_code=503,
            detail='🌐 Network error: Unable to communicate with Zenodo. Please try again later.',
        )

    except Exception as e:
        logger.error(f'❌ Unexpected error occurred: {traceback.format_exc()}')
        raise HTTPException(
            status_code=500,
            detail=f'💥 An unexpected error occurred: {str(e)}. Please contact support if the issue persists.',
        )
