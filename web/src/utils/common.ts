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
