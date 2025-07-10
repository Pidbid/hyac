import { request } from "../request";

/**
 * Get function templates
 * @param data - The request data
 */
export function getFunctionTemplates(
  appId: string,
  page: number,
  length: number,
  function_type?: string,
) {
  return request<Api.FunctionTemplate.GetFunctionTemplatesResponse>({
    url: "/function_templates/data",
    method: "post",
    data: {
      appId,
      page,
      length,
      function_type,
    },
  });
}

/**
 * Create a function template
 * @param data - The request data
 */
export function createFunctionTemplate(
  appId: string,
  name: string,
  code: string,
  type: string,
  shared: boolean,
) {
  return request<Api.Base.SuccessResponse>({
    url: "/function_templates/create",
    method: "post",
    data: {
      appId,
      name,
      code,
      type,
      shared,
    },
  });
}

/**
 * Delete a function template
 * @param id - The ID of the template
 */
export function deleteFunctionTemplate(id: string) {
  return request<Api.Base.SuccessResponse>({
    url: "/function_templates/delete",
    method: "post",
    data: { id },
  });
}

/**
 * Update a function template
 * @param data - The request data
 */
export function updateFunctionTemplate(
  data: Api.FunctionTemplate.UpdateFunctionTemplateRequest,
) {
  return request<Api.Base.SuccessResponse>({
    url: "/function_templates/update",
    method: "post",
    data,
  });
}

/**
 * Get a single function template's info
 * @param id - The ID of the template
 */
export function getFunctionTemplate(id: string) {
  return request<Api.FunctionTemplate.GetFunctionTemplateResponse>({
    url: "/function_templates/info",
    method: "post",
    data: { id },
  });
}
