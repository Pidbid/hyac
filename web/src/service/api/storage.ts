import { request } from '../request';
import { getToken } from '@/store/modules/auth/shared';
import axios from 'axios';

/**
 * Create a folder in a bucket
 * @param appId - The application ID (bucket name).
 * @param folderName - The name of the folder to create.
 */
export function createFolder(appId: string, folderName: string) {
  return request<Api.Base.SuccessResponse>({
    url: '/storage/create_folder',
    method: 'post',
    data: { appId, folder_name: folderName }
  });
}

/**
 * Delete a folder from a bucket
 * @param appId - The application ID (bucket name).
 * @param folderName - The name of the folder to delete.
 */
export function deleteFolder(appId: string, folderName: string) {
  return request<Api.Base.SuccessResponse>({
    url: '/storage/delete_folder',
    method: 'post',
    data: { appId, folder_name: folderName }
  });
}

/**
 * Delete a file from a bucket.
 * @param appId - The application ID (bucket name).
 * @param objectName - The name of the object to delete.
 */
export function deleteFile(appId: string, objectName: string) {
  return request<Api.Base.SuccessResponse>({
    url: '/storage/delete_file',
    method: 'post',
    data: { appId, object_name: objectName }
  });
}

/**
 * List objects (files and folders) in a bucket/prefix.
 * @param appId - The application ID (bucket name).
 * @param prefix - The prefix to filter objects (optional).
 */
export async function listObjects(appId: string, prefix?: string) {
  return request<Api.Storage.MinioObject[]>({
    url: '/storage/list_objects',
    method: 'post',
    data: { appId, prefix }
  });
}

/**
 * Upload a file to a bucket.
 * @param appId - The application ID (bucket name).
 * @param objectName - The full path and name of the object in the bucket.
 * @param file - The file to upload.
 */
export function uploadFile(appId: string, objectName: string, file: File) {
  const formData = new FormData();
  formData.append('appId', appId);
  formData.append('object_name', objectName);
  formData.append('file', file);

  return request<Api.Base.SuccessResponse>({
    url: '/storage/upload_file',
    method: 'post',
    data: formData,
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  });
}

/**
 * Download a file from a bucket.
 * @param appId - The application ID (bucket name).
 * @param objectName - The name of the object to download.
 */
export function downloadFile(appId: string, objectName: string) {
  const token = getToken();
  return axios.post(
    '/storage/download_file',
    { appId, object_name: objectName },
    {
      headers: {
        Authorization: `Bearer ${token}`
      },
      responseType: 'blob'
    }
  );
}

/**
 * Get a presigned download URL for a file.
 * @param appId - The application ID (bucket name).
 * @param objectName - The name of the object to get the URL for.
 */
export function getDownloadUrl(appId: string, objectName: string) {
  return request<Api.Storage.DownloadUrl>({
    url: '/storage/get_download_url',
    method: 'post',
    data: { appId, object_name: objectName }
  });
}
