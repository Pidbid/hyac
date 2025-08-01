import { request } from '@/service/request';

/** 获取统计摘要 */
export function fetchStatisticsSummary(appId: string) {
  return request<Api.Statistics.Summary>({
    url: '/statistics/summary',
    method: 'post',
    data: { appId }
  });
}

/** 获取函数请求 */
export function fetchFunctionRequests(appId: string, days?: number, functionId?: string) {
  return request<Api.Statistics.FunctionRequestsResponse[]>({
    url: '/statistics/function_requests',
    method: 'get',
    params: { appId, days, functionId }
  });
}

/** 获取热门函数 */
export function fetchTopFunctions(params: { appId: string; limit?: number }) {
  return request<Api.Statistics.TopFunctionResponse[]>({
    url: '/statistics/top_functions',
    method: 'get',
    params
  });
}
