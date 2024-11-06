# cdrxiv-file-uploader

This AWS Lambda function automatically uploads files from an S3 bucket to Zenodo when new files are added to the bucket.

## Setup

1. Clone this repository
2. Install dependencies: `npm install`
3. Copy `.env.example` to `.env` and fill in your Zenodo API token
4. Build the project: `npm run build`
5. Deploy the Lambda function: `npm run deploy`

## Testing

Run tests with: `npm test`

## Configuration

The Lambda function is configured using environment variables:

- `ZENODO_ACCESS_TOKEN`: Your Zenodo API token

## License

This project is licensed under the MIT License - see the LICENSE file for details.
