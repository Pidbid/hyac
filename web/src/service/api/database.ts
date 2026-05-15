import { request } from '../request';

/**
 * GetCollectionData
 *
 * @param appId
 * @param page
 * @param length
 */
export function GetCollectionData(appId: string) {
  return request<Api.Database.GetCollectionData>({
    url: '/database/collections',
    method: 'post',
    data: {
      appId
    }
  });
}

/**
 * GetDocumentData
 *
 * @param appId
 * @param name
 * @param page
 * @param length
 */
export function GetDocumentData(appId: string, colName: string, page: number, length: number) {
  return request<Api.Function.GetFunctionData>({
    url: '/database/documents',
    method: 'post',
    data: {
      appId,
      colName,
      page,
      length
    }
  });
}

/**
 * GetDocumentData
 *
 * @param appId
 * @param name
 * @param page
 * @param length
 */
export function DeleteDocument(appId: string, colName: string, docId: string) {
  return request<Api.Function.GetFunctionData>({
    url: '/database/delete_document',
    method: 'post',
    data: {
      appId,
      colName,
      docId
    }
  });
}

/**
 * DeleteDocuments
 *
 * @param appId
 * @param colName
 * @param docIds
 */
export function DeleteDocuments(appId: string, colName: string, docIds: string[]) {
  return request<Api.Function.GetFunctionData>({
    url: '/database/delete_documents',
    method: 'post',
    data: {
      appId,
      colName,
      docIds
    }
  });
}

/**
 * DeleteCollection
 *
 * @param appId
 * @param name
 * @param page
 * @param length
 */
export function DeleteCollection(appId: string, colName: string) {
  return request<Api.Function.GetFunctionData>({
    url: '/database/delete_collection',
    method: 'post',
    data: {
      appId,
      colName
    }
  });
}

/**
 * DeleteCollection
 *
 * @param appId
 * @param name
 * @param page
 * @param length
 */
export function ClearCollection(appId: string, colName: string) {
  return request<Api.Function.GetFunctionData>({
    url: '/database/clear_collection',
    method: 'post',
    data: {
      appId,
      colName
    }
  });
}

/**
 * DeleteCollection
 *
 * @param appId
 * @param name
 * @param page
 * @param length
 */
export function CreateCollection(appId: string, colName: string) {
  return request<Api.Function.GetFunctionData>({
    url: '/database/create_collection',
    method: 'post',
    data: {
      appId,
      colName
    }
  });
}

/**
 * DeleteCollection
 *
 * @param appId
 * @param name
 * @param page
 * @param length
 */
export function CreateDocument(appId: string, colName: string, docData: object) {
  return request<Api.Function.GetFunctionData>({
    url: '/database/insert_document',
    method: 'post',
    data: {
      appId,
      colName,
      docData
    }
  });
}

/**
 * DeleteCollection
 *
 * @param appId
 * @param name
 * @param page
 * @param length
 */
export function UpdateDocument(appId: string, colName: string, docId: string, docData: object) {
  return request<Api.Function.GetFunctionData>({
    url: '/database/update_document',
    method: 'post',
    data: {
      appId,
      colName,
      docId,
      docData
    }
  });
}

export interface IndexPayload {
  keys: Api.Database.IndexField[];
  unique?: boolean;
  sparse?: boolean;
  expireAfterSeconds?: number | null;
}

export function GetIndexData(appId: string, colName: string) {
  return request<Api.Database.GetIndexData>({
    url: '/database/indexes',
    method: 'post',
    data: {
      appId,
      colName
    }
  });
}

export function CreateIndex(appId: string, colName: string, payload: IndexPayload) {
  return request<Api.Database.IndexMutationResult>({
    url: '/database/create_index',
    method: 'post',
    data: {
      appId,
      colName,
      ...payload
    }
  });
}

export function DropIndex(appId: string, colName: string, indexName: string) {
  return request<Record<string, never>>({
    url: '/database/drop_index',
    method: 'post',
    data: {
      appId,
      colName,
      indexName
    }
  });
}

export function UpdateIndex(appId: string, colName: string, oldIndexName: string, payload: IndexPayload) {
  return request<Api.Database.IndexMutationResult>({
    url: '/database/update_index',
    method: 'post',
    data: {
      appId,
      colName,
      oldIndexName,
      ...payload
    }
  });
}
