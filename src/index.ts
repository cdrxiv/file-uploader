import { GetObjectCommand, S3Client } from '@aws-sdk/client-s3'
import { S3Event } from 'aws-lambda'
import fetch from 'node-fetch'
import { Readable } from 'stream'
import { Deposition } from './types'

// Initialize clients and constants
const s3Client = new S3Client({})
const ZENODO_ACCESS_TOKEN = process.env.ZENODO_ACCESS_TOKEN
const ZENODO_URL = process.env.ZENODO_URL!
const CHUNK_SIZE = 100 * 1024 * 1024 // 100MB chunks
const MAX_RETRIES = 3
const RETRY_DELAY = 5000 // 5 seconds

// Helper function to fetch with retry logic
async function fetchWithRetry(
  url: string,
  options: any,
  retries = MAX_RETRIES,
): Promise<import('node-fetch').Response> {
  try {
    return await fetch(url, options)
  } catch (error) {
    if (retries > 0) {
      console.log(
        `🔄 Retry attempt ${MAX_RETRIES - retries + 1}. Retrying in ${
          RETRY_DELAY / 1000
        } seconds...`,
      )
      await new Promise((resolve) => setTimeout(resolve, RETRY_DELAY))
      return fetchWithRetry(url, options, retries - 1)
    }
    throw error
  }
}

// Function to upload large files to Zenodo in chunks
async function uploadLargeFileToZenodo(
  deposition: Deposition,
  fileName: string,
  bucket: string,
  key: string,
  fileSize: number,
): Promise<void> {
  const url = `${deposition.links.bucket}/${encodeURIComponent(fileName)}`
  let start = 0

  while (start < fileSize) {
    const end = Math.min(start + CHUNK_SIZE - 1, fileSize - 1)
    const chunkSize = end - start + 1

    const { Body } = await s3Client.send(
      new GetObjectCommand({
        Bucket: bucket,
        Key: key,
        Range: `bytes=${start}-${end}`,
      }),
    )

    if (!(Body instanceof Readable)) {
      throw new Error('Failed to get file chunk from S3')
    }

    const response = await fetchWithRetry(url, {
      method: 'PUT',
      headers: {
        Authorization: `Bearer ${ZENODO_ACCESS_TOKEN}`,
        'Content-Type': 'application/octet-stream',
        'Content-Length': chunkSize.toString(),
        'Content-Range': `bytes ${start}-${end}/${fileSize}`,
      },
      body: Body,
      timeout: 0,
    })

    if (!response.ok) {
      throw new Error(`Failed to upload file chunk: ${response.statusText}`)
    }

    start = end + 1
    console.log(
      `📤 Uploaded ${start}/${fileSize} bytes (${(
        (start / fileSize) *
        100
      ).toFixed(2)}%)`,
    )
  }
}

// Function to convert a readable stream to a buffer
async function streamToBuffer(stream: Readable): Promise<Buffer> {
  const chunks: Uint8Array[] = []
  for await (const chunk of stream) {
    chunks.push(chunk)
  }
  return Buffer.concat(chunks)
}

// Function to create a new deposition on Zenodo
async function createDataDeposition(): Promise<Deposition> {
  const res = await fetchWithRetry(`${ZENODO_URL}/api/deposit/depositions`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${ZENODO_ACCESS_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      metadata: {
        upload_type: 'dataset',
        communities: [{ identifier: 'cdrxiv' }],
      },
    }),
  })

  if (!res.ok) {
    throw new Error(`Failed to create deposition: ${res.statusText}`)
  }

  const result = await res.json()
  return result as Deposition
}

// Main Lambda handler function
export const handler = async (event: S3Event) => {
  const record = event.Records[0]
  const bucketName = record.s3.bucket.name
  const objectKey = decodeURIComponent(record.s3.object.key.replace(/\+/g, ' '))
  const fileName = objectKey.split('/').pop()

  if (!fileName) {
    throw new Error('File name is required')
  }

  console.log(`🚀 Processing file: ${objectKey} | Filename: ${fileName}`)

  try {
    // Get the file stream from S3
    const { Body, ContentLength } = await s3Client.send(
      new GetObjectCommand({
        Bucket: bucketName,
        Key: objectKey,
      }),
    )

    if (!(Body instanceof Readable) || !ContentLength) {
      throw new Error('Failed to get file stream from S3')
    }

    console.log(`📊 File size: ${ContentLength} bytes`)

    // Create deposition on Zenodo
    console.log('📝 Creating deposition on Zenodo')
    const deposition = await createDataDeposition()
    console.log(`✅ Deposition created with ID: ${deposition.id}`)

    // Upload file to Zenodo
    console.log('📤 Starting file upload to Zenodo')
    await uploadLargeFileToZenodo(
      deposition,
      fileName,
      bucketName,
      objectKey,
      ContentLength,
    )

    console.log(
      `🎉 File ${objectKey} successfully uploaded and published to Zenodo.`,
    )
    console.log(`🔗 Zenodo URL: ${deposition.links.html}`)

    return {
      statusCode: 200,
      body: 'File processed and published successfully',
    }
  } catch (error) {
    console.error('❌ Error processing file:', error)
    return { statusCode: 500, body: 'Error processing file' }
  }
}
