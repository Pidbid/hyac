import * as Minio from 'minio';
import * as fs from 'fs';
import * as path from 'path';
import { execSync } from 'child_process';

class Uploader {
    constructor(minioConfig) {
        this.minioClient = new Minio.Client(minioConfig);
        this.sourceRoot = '/web/dist'; // Default to dist for built files
    }

    async uploadFile(bucket, objectName, filePath) {
        try {
            await this.minioClient.fPutObject(bucket, objectName, filePath, {});
            console.log(`File ${filePath} uploaded as ${objectName} to bucket ${bucket}`);
        } catch (err) {
            console.error(`Error uploading file ${filePath}:`, err);
        }
    }

    async uploadDirectory(bucket, dirPath, targetDir = '') {
        const absolutePath = path.resolve(this.sourceRoot, dirPath);
        if (!fs.existsSync(absolutePath)) {
            console.warn(`Directory not found, skipping: ${absolutePath}`);
            return;
        }
        const files = fs.readdirSync(absolutePath);

        for (const file of files) {
            const filePath = path.join(absolutePath, file);
            const objectName = path.join(targetDir, dirPath, file).replace(/\\/g, '/');
            const stat = fs.statSync(filePath);

            if (stat.isDirectory()) {
                await this.uploadDirectory(bucket, path.join(dirPath, file), targetDir);
            } else {
                await this.uploadFile(bucket, objectName, filePath);
            }
        }
    }

    async runUpload(bucketName, dirsToUpload, filesToUpload) {
        try {
            const exists = await this.minioClient.bucketExists(bucketName);
            if (!exists) {
                await this.minioClient.makeBucket(bucketName, 'us-east-1');
                console.log(`Bucket ${bucketName} created.`);
            } else {
                console.log(`Bucket ${bucketName} already exists.`);
            }

            for (const dir of dirsToUpload) {
                await this.uploadDirectory(bucketName, dir);
            }

            for (const file of filesToUpload) {
                const filePath = path.join(this.sourceRoot, file);
                if (fs.existsSync(filePath)) {
                    await this.uploadFile(bucketName, file, filePath);
                } else {
                    console.warn(`File not found, skipping: ${filePath}`);
                }
            }
            console.log('Upload process finished.');
        } catch (err) {
            console.error('An error occurred during upload:', err);
            throw err;
        }
    }
}

function buildProject() {
    try {
        console.log('Starting project build...');
        // Navigate to the /web directory where the web source is
        process.chdir('/web');
        console.log('Installing dependencies with pnpm...');
        execSync('pnpm install', { stdio: 'inherit' });
        console.log('Building project with pnpm...');
        execSync('pnpm build', { stdio: 'inherit' });
        console.log('Build finished successfully.');
    } catch (error) {
        console.error('An error occurred during the build process:', error);
        throw error;
    }
}

async function main() {
    const shouldBuild = process.env.BUILD === 'true';

    if (shouldBuild) {
        try {
            buildProject();
        } catch (error) {
            console.error('Build failed. Aborting upload.');
            process.exit(1);
        }
    } else {
        console.log('Skipping build process.');
    }

    const minioConfig = {
        endPoint: 'minio',
        port: 9000,
        useSSL: false,
        accessKey: process.env.MINIO_ACCESS_KEY,
        secretKey: process.env.MINIO_SECRET_KEY,
    };

    const uploader = new Uploader(minioConfig);
    const bucketName = 'console';
    const filesToUpload = ['favicon.svg', 'index.html'];
    const dirsToUpload = ['assets', 'monacoeditorwork'];

    try {
        await uploader.runUpload(bucketName, dirsToUpload, filesToUpload);
    } catch (err) {
        console.error('Upload failed.');
        process.exit(1);
    }
}

main();
