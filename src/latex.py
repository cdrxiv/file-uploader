import asyncio
import mimetypes
import shutil

import yaml
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from .config import Settings, get_settings
from .log import get_logger

logger = get_logger()
router = APIRouter()


def validate_file(file: UploadFile):
    mime_type, _ = mimetypes.guess_type(file.filename)
    if mime_type is None:
        raise HTTPException(
            status_code=400, detail='Could not determine mime type of file'
        )

    if mime_type != 'application/zip':
        raise HTTPException(
            status_code=400,
            detail=f'Invalid file type: {mime_type} for LaTeX source: {file.filename}. Must be a ZIP archive',
        )


@router.post('/latex/upload-file')
async def upload_file(
    request: Request,
    preprint_id: str,
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
):
    logger.info('Uploading file')
    validate_file(file)
    file_path = settings.LATEX_SOURCE_DIRECTORY / preprint_id / file.filename
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open('wb') as buffer:
        shutil.copyfileobj(file.file, buffer)

    # unzip the file
    logger.info(f'Unzipping file: {file_path}')
    shutil.unpack_archive(file_path, file_path.parent)
    # get the path to the unzipped directory
    unzipped_directory = file_path.parent / file.filename.replace('.zip', '')

    # write a yaml file (myst.ym) in the same directory. This file will contain the metadata for the preprint as following

    myst_file = unzipped_directory / 'myst.yml'
    with myst_file.open('w') as buffer:
        yaml.dump(
            {
                'version': 1,
                'project': {
                    'id': preprint_id,
                    'title': '',
                    'description': '',
                    'keywords': [],
                    'authors': [],
                    'subject': 'Article',
                    'open_access': True,
                    'license': '',
                },
                'site': {'template': 'article-theme'},
            },
            buffer,
        )

    myst_executable = shutil.which('myst')
    if myst_executable is None:
        raise HTTPException(status_code=500, detail='myst executable not found in PATH')

    # run myst to convert the latex source to html
    logger.info(f'Converting LaTeX source to HTML: {unzipped_directory}')

    myst_command = [myst_executable, 'build', '--site', '--ci']
    logger.info(f'Running myst command: {myst_command}')
    process = await asyncio.create_subprocess_exec(
        *myst_command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(unzipped_directory),
    )
    stdout, stderr = await process.communicate()
    logger.info(f'myst stdout: {stdout.decode()}')
    logger.info(f'myst stderr: {stderr.decode()}')
    if process.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f'myst command failed with return code: {process.returncode}',
        )

    build_directory = unzipped_directory / '_build' / 'site'
    parent_directory = unzipped_directory.parent / 'site'
    parent_directory.mkdir(parents=True, exist_ok=True)

    # Now we need to move the contents of the _build directory to the parent directory
    for item in build_directory.iterdir():
        logger.info(f'Moving item: {item} to {parent_directory}')
        shutil.move(item, parent_directory)

    return {
        'status': 'ok',
        'filename': file.filename,
        'path': parent_directory,
    }
