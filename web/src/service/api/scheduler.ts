import { request } from '../request';

/**
 * Get the scheduled task for a specific function.
 * @param appId - The ID of the application.
 * @param functionId - The ID of the function.
 */
export function getTaskForFunction(appId: string, functionId: string) {
  return request<Api.Scheduler.ScheduledTask | null>({
    url: '/scheduler/get',
    method: 'post',
    data: { appId, functionId }
  });
}

/**
 * Create or update the scheduled task for a specific function.
 * @param data - The task data to upsert.
 */
export function upsertTaskForFunction(data: Api.Scheduler.ScheduledTaskUpsert) {
  return request<Api.Scheduler.ScheduledTask>({
    url: '/scheduler/upsert',
    method: 'post',
    data
  });
}

/**
 * Delete the scheduled task for a specific function.
 * @param appId - The ID of the application.
 * @param functionId - The ID of the function.
 */
export function deleteTaskForFunction(appId: string, functionId: string) {
  return request({
    url: '/scheduler/delete',
    method: 'post',
    data: { appId, functionId }
  });
}

/**
 * Manually trigger the scheduled task for a function.
 * @param appId - The ID of the application.
 * @param functionId - The ID of the function.
 */
export function triggerTaskForFunction(appId: string, functionId: string) {
    return request({
        url: '/scheduler/trigger',
        method: 'post',
        data: { appId, functionId }
    });
}
