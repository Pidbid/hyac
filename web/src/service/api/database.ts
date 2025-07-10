import { request } from "../request";

/**
 * GetCollectionData
 *
 * @param appId
 * @param page
 * @param length
 */
export function GetCollectionData(appId: string) {
  return request<Api.Database.GetCollectionData>({
    url: "/database/collections",
    method: "post",
    data: {
      appId,
    },
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
export function GetDocumentData(
  appId: string,
  colName: string,
  page: number,
  length: number,
) {
  return request<Api.Function.GetFunctionData>({
    url: "/database/documents",
    method: "post",
    data: {
      appId,
      colName,
      page,
      length,
    },
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
    url: "/database/delete_document",
    method: "post",
    data: {
      appId,
      colName,
      docId,
    },
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
    url: "/database/delete_collection",
    method: "post",
    data: {
      appId,
      colName,
    },
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
    url: "/database/clear_collection",
    method: "post",
    data: {
      appId,
      colName,
    },
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
    url: "/database/create_collection",
    method: "post",
    data: {
      appId,
      colName,
    },
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
export function CreateDocument(
  appId: string,
  colName: string,
  docData: object,
) {
  return request<Api.Function.GetFunctionData>({
    url: "/database/insert_document",
    method: "post",
    data: {
      appId,
      colName,
      docData,
    },
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
export function UpdateDocument(
  appId: string,
  colName: string,
  docId: string,
  docData: object,
) {
  return request<Api.Function.GetFunctionData>({
    url: "/database/update_document",
    method: "post",
    data: {
      appId,
      colName,
      docId,
      docData,
    },
  });
}
