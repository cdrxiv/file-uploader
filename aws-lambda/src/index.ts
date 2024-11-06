import { GetObjectCommand, S3Client } from '@aws-sdk/client-s3'
import { S3Event } from 'aws-lambda'
import fetch from 'node-fetch'
import { Readable } from 'stream'
import { Deposition } from './types'

const s3Client = new S3Client({})
const ZENODO_ACCESS_TOKEN = process.env.ZENODO_ACCESS_TOKEN
const ZENODO_URL = process.env.ZENODO_URL!
const MAX_RETRIES = 3
const RETRY_DELAY = 5000 // 5 seconds

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

async function uploadFileToZenodo(
  deposition: Deposition,
  fileName: string,
  fileStream: Readable,
  fileSize: number,
): Promise<void> {
  const url = `${deposition.links.bucket}/${encodeURIComponent(fileName)}`

  const response = await fetchWithRetry(url, {
    method: 'PUT',
    headers: {
      Authorization: `Bearer ${ZENODO_ACCESS_TOKEN}`,
      'Content-Type': 'application/octet-stream',
      'Content-Length': fileSize.toString(),
    },
    body: fileStream,
    timeout: 0, // Disable timeout
  })

  if (!response.ok) {
    throw new Error(`Failed to upload file: ${response.statusText}`)
  }

  // Verify final file size
  const finalResponse = await fetch(
    `${url}?${new URLSearchParams({
      access_token: ZENODO_ACCESS_TOKEN as string,
    })}`,
    {
      method: 'HEAD',
    },
  )

  if (!finalResponse.ok) {
    throw new Error(
      `Failed to verify final file size: ${finalResponse.statusText}`,
    )
  }

  const finalSize = parseInt(
    finalResponse.headers.get('Content-Length') || '0',
    10,
  )
  if (finalSize !== fileSize) {
    throw new Error(
      `Final file size mismatch. Expected: ${fileSize}, Actual: ${finalSize}`,
    )
  }

  console.log(`✅ File upload verified. Final size: ${finalSize} bytes`)
}

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
    await uploadFileToZenodo(deposition, fileName, Body, ContentLength)

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
    if (error instanceof Error) {
      console.error('Error details:', error.message)
      console.error('Stack trace:', error.stack)
    }
    return {
      statusCode: 500,
      body: `Error processing file: ${
        error instanceof Error ? error.message : String(error)
      }`,
    }
  }
}
