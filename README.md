<p align='left'>
  <a href='https://cdrxiv.org/#gh-light-mode-only'>
    <img
      src='https://avatars.githubusercontent.com/u/169473259?s=400&u=71ee6cf9499fb57b602af2c8467ad9a8f98a1042&v=4'
      height='48px'
    />
  </a>
  <a href='https://cdrxiv.org/#gh-dark-mode-only'>
    <img
      src='https://avatars.githubusercontent.com/u/169473259?s=400&u=71ee6cf9499fb57b602af2c8467ad9a8f98a1042&v=4'
      height='48px'
    />
  </a>
</p>

# cdrxiv / file-uploader

A minimal file uploader service built with FastAPI. Currently, this service has two main endpoints:

- `/zenodo/upload-file`: used to upload files to Zenodo
- `/myst/upload-file`: used to upload latex source files

[![Fly.io Deployment](https://github.com/cdrxiv/file-uploader/actions/workflows/fly.yml/badge.svg)](https://github.com/cdrxiv/file-uploader/actions/workflows/fly.yml)

- staging instance: [cdrxiv-file-uploader-staging.fly.dev](https://cdrxiv-file-uploader-staging.fly.dev/docs)
- production instance: [cdrxiv-file-uploader.fly.dev](https://cdrxiv-file-uploader.fly.dev/docs)

## installation

To install and run this service locally, you can use the following commands:

```bash
git clone https://github.com/cdrxiv/file-uploader
cd file-uploader
python -m pip install -r requirements.txt
```

## running the service

To run the service locally, you can use the following command:

```bash
uvicorn src.main:app --reload
```

## license

All the code in this repository is [MIT](https://choosealicense.com/licenses/mit/) licensed.

CDRXIV is a registered trademark (application pending). CDRXIV’s digital assets (graphics, logo, etc) are licensed as [CC-BY](https://creativecommons.org/licenses/by/4.0/deed.en).

> [!IMPORTANT]
> Content and data associated with this repository and hosted on CDRXIV are subject to additional [terms of use](https://cdrxiv.org/terms-of-use). See the [FAQ](https://cdrxiv.org/about/faq) for more information on how CDRXIV content is licensed.
