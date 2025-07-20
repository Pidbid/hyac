import { request } from '../request';

/**
 * GetFunctionData
 *
 * @param appId
 * @param page
 * @param length
 * @param type
 * @param tag
 */
export function GetFunctionData(appId: string, page: number, length: number, type?: string, tag?: string) {
  return request<Api.Function.GetFunctionData>({
    url: '/function/data',
    method: 'post',
    data: {
      appId,
      page,
      length,
      ...(type && { type }),
      ...(tag && { tag })
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


export function functionTest(url: string, method: string, headers: object, query: object = {}, body: object = {}) {
  return request({
    url: '/function/proxy_test',
    method: 'post',
    data: {
      target_url: url,
      method,
      headers,
      query_params: query,
      body
    }
  });
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

/**
 * Get function tags
 *
 * @param appId
 */
export function getFunctionTags(appId: string) {
  return request<string[]>({
    url: '/function/tags',
    method: 'post',
    data: {
      appId
    }
  });
}
