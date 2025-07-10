import { request } from '../request';

/**
 * AppInfo
 *
 * @param id id of app
 */
export function AppInfo(appId: string) {
  return request<Api.App.GetAppInfo>({
    url: '/applications/info',
    method: 'post',
    data: {
      appId
    }
  });
}


/**
 * getApps
 *
 * @param length Number of apps to fetch
 */
export function getApps(data: any) {
  return request<Api.App.GetAppData>({
    url: '/applications/data',
    method: 'post',
    data
  });
}


/**
 * CreateApp
 *
 * @param appName Name of the application
 * @param description Description of the application
 */
export function createApp(appName: string, description: string) {
  return request<Api.App.CreateAppResponse>({
    url: '/applications/create',
    method: 'post',
    data: {
      appName,
      description
    }
  });
}


/**
 * DeleteApp
 *
 * @param appId id of app
 */
export function deleteApp(appId: string) {
  return request<Api.App.DeleteAppResponse>({
    url: '/applications/delete',
    method: 'post',
    data: {
      appId
    }
  });
}

/**
 * StartApp
 *
 * @param appId id of app
 */
export function startApp(appId: string) {
  return request<Api.App.StartAppResponse>({
    url: '/applications/start',
    method: 'post',
    data: {
      appId
    }
  });
}

/**
 * StopApp
 *
 * @param appId id of app
 */
export function stopApp(appId: string) {
  return request<Api.App.StopAppResponse>({
    url: '/applications/stop',
    method: 'post',
    data: {
      appId
    }
  });
}
