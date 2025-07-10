import { request } from '../request';

/**
 * Query application logs with pagination and filters.
 *
 * @param appId - The ID of the application.
 * @param page - The page number to retrieve.
 * @param length - The number of logs per page.
 * @param extra - Optional filters for the log query.
 */
export function getAppLogs(appId: string, page: number, length: number, extra?: Api.Log.LogQueryExtra) {
  return request<Api.Log.PagedLogEntry>({
    url: '/logs/app_logs',
    method: 'post',
    data: {
      appId,
      page,
      length,
      extra
    }
  });
}

/**
 * Query function logs with pagination and filters.
 *
 * @param appId - The ID of the application.
 * @param funcId - The ID of the function.
 * @param page - The page number to retrieve.
 * @param length - The number of logs per page.
 * @param extra - Optional filters for the log query.
 */
export function getFunctionLogs(
  appId: string,
  funcId: string,
  page: number,
  length: number,
  extra?: Api.Log.LogQueryExtra
) {
  return request<Api.Log.PagedLogEntry>({
    url: '/logs/function_logs',
    method: 'post',
    data: {
      appId,
      funcId,
      page,
      length,
      extra
    }
  });
}
