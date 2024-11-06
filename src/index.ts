import { GetObjectCommand, S3Client } from '@aws-sdk/client-s3'
import { S3Event } from 'aws-lambda'
import fetch from 'node-fetch'
import { pipeline, Readable } from 'stream'
import { promisify } from 'util'
import { Deposition } from './types'
const s3Client = new S3Client({})
const streamPipeline = promisify(pipeline)
const ZENODO_ACCESS_TOKEN = process.env.ZENODO_ACCESS_TOKEN
const ZENODO_URL = process.env.ZENODO_URL!

async function streamToBuffer(stream: Readable): Promise<Buffer> {
  const chunks: Uint8Array[] = []
  for await (const chunk of stream) {
    chunks.push(chunk)
  }
  return Buffer.concat(chunks)
}

async function createDataDeposition(): Promise<Deposition> {
  const res = await fetch(process.env.ZENODO_URL + '/api/deposit/depositions', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${process.env.ZENODO_ACCESS_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      metadata: {
        upload_type: 'dataset',
        communities: [{ identifier: 'cdrxiv' }],
      },
    }),
  })

  const result = await res.json()
  return result as Deposition
}
export async function updateDataDeposition(
  url: string,
  params: Partial<Deposition>,
): Promise<Deposition> {
  if (process.env.ZENODO_URL && !url.startsWith(process.env.ZENODO_URL)) {
    throw new Error(`Invalid data URL: ${url}`)
  }
  const res = await fetch(url, {
    method: 'PUT',
    headers: {
      Authorization: `Bearer ${process.env.ZENODO_ACCESS_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(params),
  })

  if (res.status !== 200) {
    throw new Error(
      `Status ${res.status}: Unable to update deposition. ${res.statusText}`,
    )
  }

  const result = await res.json()
  return result as Deposition
}

export async function deleteZenodoEntity(url: string): Promise<true> {
  if (process.env.ZENODO_URL && !url.startsWith(process.env.ZENODO_URL)) {
    throw new Error(`Invalid data URL: ${url}`)
  }

  const res = await fetch(url, {
    method: 'DELETE',
    headers: {
      Authorization: `Bearer ${process.env.ZENODO_ACCESS_TOKEN}`,
    },
  })

  if (res.status === 204 || res.status === 404) {
    // 204: Successful deletion
    // 404: Entity not found (consider it already deleted)
    return true
  }

  throw new Error(
    `Status ${res.status}: Unable to delete deposition. ${res.statusText}`,
  )
}

export async function fetchDataDeposition(url: string): Promise<Deposition> {
  if (process.env.ZENODO_URL && !url.startsWith(process.env.ZENODO_URL)) {
    throw new Error(`Invalid data URL: ${url}`)
  }
  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${process.env.ZENODO_ACCESS_TOKEN}`,
    },
  })

  if (res.status !== 200) {
    throw new Error(
      `Status ${res.status}: Unable to fetch deposition. ${res.statusText}`,
    )
  }

  const result = await res.json()
  return result as Deposition
}

export async function createDataDepositionVersion(
  url: string,
): Promise<Deposition> {
  if (process.env.ZENODO_URL && !url.startsWith(process.env.ZENODO_URL)) {
    throw new Error(`Invalid data URL: ${url}`)
  }
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${process.env.ZENODO_ACCESS_TOKEN}`,
    },
  })

  if (res.status !== 201) {
    throw new Error(
      `Status ${res.status}: Unable to create new version of deposition. ${res.statusText}`,
    )
  }

  const result = await res.json()
  return result as Deposition
}

export const handler = async (event: S3Event) => {
  const record = event.Records[0]
  const bucketName = record.s3.bucket.name
  const objectKey = decodeURIComponent(record.s3.object.key.replace(/\+/g, ' '))
  // Extract the filename from the objectKey
  const fileName = objectKey.split('/').pop()
  if (!fileName) {
    throw new Error('File name is required')
  }

  console.log(`Processing object file: ${objectKey} | filename: ${fileName}`)

  try {
    // Get the file stream from S3
    const { Body, ContentType } = await s3Client.send(
      new GetObjectCommand({
        Bucket: bucketName,
        Key: objectKey,
      }),
    )

    if (!(Body instanceof Readable)) {
      throw new Error('Failed to get file stream from S3')
    }
    // Convert stream to buffer
    const fileBuffer = await streamToBuffer(Body)

    console.log('Creating deposition on Zenodo')

    // Create deposition
    const deposition = await createDataDeposition()

    console.log('Deposition response:', deposition)

    // Upload the file to Zenodo using streaming
    const url = `${deposition.links.bucket ?? ''}/${encodeURIComponent(
      fileName,
    )}`
    const uploadResponse = await fetch(url, {
      method: 'PUT',
      headers: {
        Authorization: `Bearer ${ZENODO_ACCESS_TOKEN}`,
        'Content-Length': fileBuffer.length.toString(),
      },
      body: fileBuffer,
    })

    console.log('Upload response status:', uploadResponse.status)

    if (!uploadResponse.ok) {
      throw new Error(
        `Failed to upload file to Zenodo: ${uploadResponse.statusText}`,
      )
    }

    console.log(
      `File ${objectKey} successfully uploaded to Zenodo. The zenodo URL is ${deposition.links.html}`,
    )
    return { statusCode: 200, body: 'File processed successfully' }
  } catch (error) {
    console.error('Error processing file:', error)
    return { statusCode: 500, body: 'Error processing file' }
  }
}
