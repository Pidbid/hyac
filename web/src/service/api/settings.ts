import { request } from '../request';

/**
 * 搜索依赖
 * @param appId - 应用ID
 * @param name - 依赖名称
 * @param forceUpdate - 是否强制更新
 */
export function dependenceSearch(appId: string, name:string, forceUpdate: boolean = false) {
  return request<Api.Settings.PackageInfo[]>({
    url: '/settings/dependence_search',
    method: 'post',
    data: {
      appId,
      name,
      forceUpdate
    }
  });
}

/**
 * 获取包信息
 * @param appId - 应用ID
 * @param name - 包名称
 */
export function packageInfo(appId: string, name: string) {
  return request<Api.Settings.PackageInfo>({
    url: '/settings/package_info',
    method: 'post',
    data: {
      appId,
      name
    }
  });
}

/**
 * 添加包
 * @param appId - 应用ID
 * @param name - 包名称
 * @param version - 包版本
 * @param restart - 是否重启容器
 */
export function packageAdd(appId: string, name: string, version: string, restart: boolean = false) {
  return request<Api.Base.SuccessResponse>({
    url: '/settings/package_add',
    method: 'post',
    data: {
      appId,
      name,
      version,
      restart
    }
  });
}

/**
 * 移除包
 * @param appId - 应用ID
 * @param name - 包名称
 * @param restart - 是否重启容器
 */
export function packageRemove(appId: string, name: string, restart: boolean = false) {
  return request<Api.Base.SuccessResponse>({
    url: '/settings/package_remove',
    method: 'post',
    data: {
      appId,
      name,
      restart
    }
  });
}

/**
 * 更新依赖
 * @param appId - 应用ID
 */
export function dependenceUpdate(appId: string) {
  return request<Api.Base.SuccessResponse>({
    url: '/settings/dependence_update',
    method: 'post',
    data: {
      appId
    }
  });
}

/**
 * 获取应用依赖数据
 * @param appId - 应用ID
 */
export function dependenciesData(appId: string) {
  return request<Api.Settings.DependenciesData>({
    url: '/settings/dependencies_data',
    method: 'post',
    data: { appId }
  });
}

/**
 * Get environment variables for an application.
 * @param appId - The ID of the application.
 */
export function getEnvsData(appId: string) {
  return request<Api.Settings.EnvsData>({
    url: '/settings/envs_data',
    method: 'post',
    data: { appId }
  });
}

/**
 * Add or update an environment variable for an application.
 * @param appId - The ID of the application.
 * @param key - The key of the environment variable.
 * @param value - The value of the environment variable.
 */
export function addEnv(appId: string, key: string, value: string) {
  return request<Api.Base.SuccessResponse>({
    url: '/settings/env_add',
    method: 'post',
    data: { appId, key, value }
  });
}

/**
 * Remove an environment variable from an application.
 * @param appId - The ID of the application.
 * @param key - The key of the environment variable to remove.
 */
export function removeEnv(appId: string, key: string) {
  return request<Api.Base.SuccessResponse>({
    url: '/settings/env_remove',
    method: 'post',
    data: { appId, key }
  });
}

/**
 * 获取CORS配置
 * @param appId - 应用ID
 */
export function corsData(data: { appId: string }) {
  return request<Api.Settings.CorsConfig>({
    url: '/settings/cors_data',
    method: 'post',
    data
  });
}

/**
 * 更新CORS配置
 * @param appId - 应用ID
 * @param config - CORS配置
 */
export function corsUpdate(data: { appId: string; config: Api.Settings.CorsConfig }) {
  return request<Api.Base.SuccessResponse>({
    url: '/settings/cors_update',
    method: 'post',
    data
  });
}

/**
 * 获取通知配置
 * @param data - 请求数据
 */
export function notificationData(data: { appId: string }) {
  return request<Api.Settings.NotificationConfig>({
    url: '/settings/notification_data',
    method: 'post',
    data
  });
}

/**
 * 更新通知配置
 * @param data - 请求数据
 */
export function notificationUpdate(data: { appId: string; config: Api.Settings.NotificationConfig }) {
  return request<Api.Base.SuccessResponse>({
    url: '/settings/notification_update',
    method: 'post',
    data
  });
}

/**
 * 获取APP状态
 * @param data - 请求数据
 */
export function applicationStatus(appId: string) {
  return request<Api.Settings.ApplicationStatus>({
    url: '/settings/application_status',
    method: 'post',
    data:{
      appId
    }
  });
}

/**
 * 获取域名
 */
export function getDomain() {
  return request<string>({
    url: '/settings/domain',
    method: 'get'
  });
}

/**
 * 获取AI配置
 * @param data - 请求数据
 */
export function fetchAiConfig(data: { appId: string }) {
  return request<Api.Settings.AIConfig>({
    url: '/settings/ai_config_data',
    method: 'post',
    data
  });
}

/**
 * 更新AI配置
 * @param data - 请求数据
 */
export function updateAiConfig(data: { appId: string; config: Api.Settings.AIConfig }) {
  return request<Api.Base.SuccessResponse>({
    url: '/settings/ai_config_update',
    method: 'post',
    data
  });
}

/**
 * Check for system updates.
 * @returns
 */
export function fetchCheckForUpdates(params?: { proxy?: string }) {
  return request<Api.Settings.UpdateStatus>({
    method:"post",
    url:"/settings/system/check_update",
    data: params
  })
}

/**
 * Trigger system update.
 * @returns
 */
export function fetchUpdateSystem(tags?: Api.Settings.ManualUpdateTags) {
  return request<Api.Base.SuccessResponse>({
    method:"post",
    url:"/settings/system/update",
    data: tags
  })
}

/**
 * Fetch system changelogs.
 * @returns
 */
export function fetchChangelogs(params?: { proxy?: string }) {
  return request<Api.Settings.ChangelogData>({
    method: "post",
    url: "/settings/system/changelogs",
    data: params
  })
}
