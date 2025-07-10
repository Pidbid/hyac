import { request } from '../request';
import axios from 'axios';

/**
 * GetFunctionData
 *
 * @param appId
 * @param page
 * @param length
 */
export function GetFunctionData(appId: string, page: number, length: number) {
  return request<Api.Function.GetFunctionData>({
    url: '/function/data',
    method: 'post',
    data: {
      appId,
      page,
      length
    }
  });
}

/**
 * UpdateFunctionCode
 *
 * @param appId
 * @param id
 * @param code
 */
export function UpdateFunctionCode(appId: string, id: string, code: string) {
  return request<Api.Function.GetFunctionData>({
    url: '/function/update_code',
    method: 'post',
    data: {
      appId,
      id,
      code
    }
  });
}

/**
 * CreateFunction
 *
 * @param appId
 * @param functionName
 * @param description
 * @param tags
 */
export function CreateFunction(appId: string, name:string, type:string, description: string, tags: string[], language: string, template_id?: string) {
  return request<Api.Function.GetFunctionData>({
    url: '/function/create',
    method: 'post',
    data: {
      appId,
      name,
      type,
      description,
      tags,
      language,
      template_id
    }
  });
}

/**
 * DeleteFunction
 *
 * @param appId
 * @param id
 */
export function DeleteFunction(appId: string, id: string) {
  return request<Api.Function.GetFunctionData>({
    url: '/function/delete',
    method: 'post',
    data: {
      appId,
      id
    }
  });
}


export async function functionTest(url: string, method: string, headers: object, query: object = {}, body: object = {}) {
  if (method === 'GET') {
    return await axios.get(url, {
      headers,
      params: query
    });
  }
  else if (method === 'POST') {
    return await axios.post(url, body, {
      headers,
    });
  }
}


/**
 * Function history
 *
 * @param id
 */
export function FunctionHistory(appId: string, id: string) {
  return request<Api.Function.FunctionHistory>({
    url: '/function/function_history',
    method: 'post',
    data: {
      appId,
      id
    }
  });
}
