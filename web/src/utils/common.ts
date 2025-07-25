import { $t } from '@/locales';

/**
 * Transform record to option
 *
 * @example
 *   ```ts
 *   const record = {
 *     key1: 'label1',
 *     key2: 'label2'
 *   };
 *   const options = transformRecordToOption(record);
 *   // [
 *   //   { value: 'key1', label: 'label1' },
 *   //   { value: 'key2', label: 'label2' }
 *   // ]
 *   ```;
 *
 * @param record
 */
export function transformRecordToOption<T extends Record<string, string>>(record: T) {
  return Object.entries(record).map(([value, label]) => ({
    value,
    label
  })) as CommonType.Option<keyof T, T[keyof T]>[];
}

/**
 * Translate options
 *
 * @param options
 */
export function translateOptions(options: CommonType.Option<string, App.I18n.I18nKey>[]) {
  return options.map(option => ({
    ...option,
    label: $t(option.label)
  }));
}

/**
 * Toggle html class
 *
 * @param className
 */
export function toggleHtmlClass(className: string) {
  function add() {
    document.documentElement.classList.add(className);
  }

  function remove() {
    document.documentElement.classList.remove(className);
  }

  return {
    add,
    remove
  };
}

/**
 * 将 server.domain.name/ 格式的域名转换为指定协议和前缀的格式
 * @param originalDomain - 原始域名，格式如 server.domain.name/ 或 http://server.domain.name/
 * @param protocol - 请求方式 http https ws wss
 * @param prefix - 前缀
 * @returns 转换后的域名
 */
export function convertDomain(originalDomain: string, protocol: string, prefix: string): string {
    const domainWithoutProtocol = originalDomain.replace(/^[a-zA-Z]+:\/\//, '');
    const domainWithoutSlash = domainWithoutProtocol.replace(/\/$/, '');
    const parts = domainWithoutSlash.split('.');
    if (parts.length < 3) {
        throw new Error('Invalid domain format. Expected at least 3 parts (e.g., server.domain.name)');
    }
    if (!/^[a-zA-Z]+$/.test(protocol)) {
        throw new Error('Invalid protocol format. Should be like http, https, ws, wss');
    }
    const domainParts = parts.slice(1).join('.');
    const convertedDomain = `${protocol}://${prefix}.${domainParts}`;
    return convertedDomain;
}

/**
 * 获取后端服务的 Base URL。
 * 在生产环境中，它会从 window.APP_CONFIG 读取（由 Docker entrypoint 注入）。
 * 在开发环境中，它会回退到 Vite 的 import.meta.env。
 * @returns 后端服务的 URL
 */
export function getServiceBaseUrl(): string {
  // 生产环境：window.APP_CONFIG 存在且 VITE_SERVICE_BASE_URL 有效
  if (
    (window as any).APP_CONFIG &&
    (window as any).APP_CONFIG.VITE_SERVICE_BASE_URL &&
    (window as any).APP_CONFIG.VITE_SERVICE_BASE_URL !== '${VITE_SERVICE_BASE_URL}'
  ) {
    return (window as any).APP_CONFIG.VITE_SERVICE_BASE_URL;
  }
  // 开发环境或备用方案
  return import.meta.env.VITE_SERVICE_BASE_URL;
}
