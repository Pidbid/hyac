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
 * UpdateFunctionMeta
 *
 * @param params
 * @param params.appId
 * @param params.id
 * @param params.name
 * @param params.description
 * @param params.tags
 * @param params.requiresAuth
 */
interface UpdateFunctionMetaParams {
  appId: string;
  id: string;
  name: string;
  description: string;
  tags: string[];
  requiresAuth?: boolean;
}

export function UpdateFunctionMeta(params: UpdateFunctionMetaParams) {
  const { appId, id, name, description, tags, requiresAuth } = params;

  return request<Api.Function.GetFunctionData>({
    url: '/function/update_meta',
    method: 'post',
    data: {
      appId,
      id,
      name,
      description,
      tags,
      requires_auth: requiresAuth
    }
  });
}

/**
 * CreateFunction
 *
 * @param params
 * @param params.appId
 * @param params.name
 * @param params.type
 * @param params.description
 * @param params.tags
 * @param params.language
 * @param params.templateId
 * @param params.requiresAuth
 */
interface CreateFunctionParams {
  appId: string;
  name: string;
  type: string;
  description: string;
  tags: string[];
  language: string;
  templateId?: string;
  requiresAuth?: boolean;
}

export function CreateFunction(params: CreateFunctionParams) {
  const { appId, name, type, description, tags, language, templateId, requiresAuth = false } = params;

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
      template_id: templateId,
      requires_auth: requiresAuth
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
