/**
 * Namespace Api
 *
 * All backend api type
 */
declare namespace Api {
  interface BaseResponse<T = any> {
    code: number;
    msg: string;
    data: T;
  }

  namespace Common {
    /** common params of paginating */
    interface PaginatingCommonParams {
      /** current page number */
      current: number;
      /** page size */
      size: number;
      /** total count */
      total: number;
    }

    /** common params of paginating query list data */
    interface PaginatingQueryRecord<T = any> extends PaginatingCommonParams {
      records: T[];
    }

    /** common search params of table */
    type CommonSearchParams = Pick<
      Common.PaginatingCommonParams,
      "current" | "size"
    >;

    /**
     * enable status
     *
     * - "1": enabled
     * - "2": disabled
     */
    type EnableStatus = "1" | "2";

    /** common record */
    type CommonRecord<T = any> = {
      /** record id */
      id: number;
      /** record creator */
      createBy: string;
      /** record create time */
      createTime: string;
      /** record updater */
      updateBy: string;
      /** record update time */
      updateTime: string;
      /** record status */
      status: EnableStatus | null;
    } & T;
  }

  /**
   * namespace Auth
   *
   * backend api module: "auth"
   */
  namespace Auth {
    interface LoginToken {
      token: string;
      refreshToken: string;
    }

    interface UserInfo {
      userid: string;
      username: string;
      nickname: string;
      avatar: string;
      roles: string[];
      buttons: string[];
    }
  }

  /**
   * namespace application
   *
   * backend api module: "application"
   */
  namespace Application {
    interface AppInfo {
      appId: string;
      appName: string;
    }
  }

  /**
   * namespace database
   *
   * backend api module: "database"
   */
  namespace Database {
    interface GetCollectionData {
      data: string[];
    }
  }

  /**
   * namespace App
   *
   * backend api module: "app"
   */
  namespace App {
    interface AppRecord {
      app_id: string;
      app_name: string;
      description: string;
      status: string; // Assuming status is a string, adjust if it's an enum or number
      id: number; // Assuming id is a number
    }

    interface GetAppData {
      data: AppRecord[];
      total: number;
      pageNum: number;
      pageSize: number;
    }

    interface GetAppInfo {
      app_id: string;
      app_name: string;
    }

    interface CreateAppResponse {
      app_id: string;
    }

    interface DeleteAppResponse {}

    interface StartAppResponse {
      app_id: string;
    }

    interface StopAppResponse {
      app_id: string;
    }
  }

  /**
   * namespace Function
   *
   * backend api module: "function"
   */
  namespace Function {
    /**
     * function status
     *
     * - "unpublished": unpublished
     * - "published": published
     */
    type FunctionStatus = "unpublished" | "published";
    type FunctionType = "endpoint" | "common";

    type LogType = "function" | "system";

    type LogLevel = "info" | "warn" | "error" | "debug";

    /** function record (full backend data) */
    interface FunctionRecord {
      /** mongodb id */
      _id: string;
      /** function id */
      function_id: string;
      /** function name */
      function_name: string;
      /** app name */
      app_name: string;
      /** function code */
      code: string;
      /** function dependencies */
      dependencies: string[];
      /** function description */
      description: string;
      /** function type */
      function_type: FunctionType;
      /** function status */
      status: FunctionStatus;
      /** memory limit (MB) */
      memory_limit: number;
      /** timeout (seconds) */
      timeout: number;
      /** requires authentication */
      requires_auth: boolean;
      /** create time */
      created_at: string;
      /** update time */
      updated_at: string;
      /** function tags */
      tags: string[];
    }

    /** function info for list display (frontend simplified) */
    interface FunctionInfo {
      /** function id (mapped from func_id) */
      id: FunctionRecord["function_id"];
      /** function name (mapped from function_id) */
      name: FunctionRecord["function_name"];
      /** function type */
      type: FunctionType;
      /** function description (mapped from code) */
      description: FunctionRecord["description"];
      /** function method (e.g., GET, POST) */
      code: FunctionRecord["code"];
      /** function tags */
      tags: FunctionRecord["tags"];
      /** function status */
      status: FunctionRecord["status"];
    }

    interface GetFunctionData {
      data: FunctionRecord[];
      total: number;
      pageNum: number;
      pageSize: number;
    }

    interface GetFunctionInfo {
      app_id: string;
      app_name: string;
    }

    interface FunctionHistoryInfo {
      _id: string;
      function_id: string;
      old_code: string;
      new_code: string;
      version: number;
      updated_at: string;
      updated_by: string;
    }
    interface FunctionHistory {
      data: FunctionHistoryInfo[];
      total: number;
      pageNum: number;
      pageSize: number;
    }

    interface FunctionLogsInfo {
      _id:string;
      app_id: string;
      function_id: string;
      level: LogLevel;
      logtype: "function" | "system";
      message: string;
      timestamp: string;
    }
  }

  /**
   * namespace Route
   *
   * backend api module: "route"
   */
  namespace Route {
    type ElegantConstRoute = import("@elegant-router/types").ElegantConstRoute;

    interface MenuRoute extends ElegantConstRoute {
      id: string;
    }

    interface UserRoute {
      routes: MenuRoute[];
      home: import("@elegant-router/types").LastLevelRouteKey;
    }
  }

  /**
   * namespace Base
   *
   * backend api module: "base"
   */
  namespace Base {
    interface SuccessResponse {
      code: number;
      msg: string;
      data?: any;
    }
  }

  /**
   * namespace Storage
   *
   * backend api module: "storage"
   */
  namespace Storage {
    interface MinioObject {
      name: string;
      is_dir: boolean;
      size: number;
      last_modified: string;
    }

    interface ObjectList {
      data: MinioObject[];
    }

    interface DownloadUrl {
      url: string;
    }
  }

  /**
   * namespace Log
   *
   * backend api module: "log"
   */
  namespace Log {
    /**
     * log level
     *
     * - "info": info
     * - "warning": warning
     * - "error": error
     * - "debug": debug
     */
    type LogLevel = 'info' | 'warning' | 'error' | 'debug';

    /**
     * log type
     *
     * - "system": system log
     * - "function": function call log
     */
    type LogType = 'system' | 'function';

    interface LogsExtra {
      function_id: string;
      function_name: string;
      app_id: string;
    }
    /** log entry record */
    interface LogEntry {
      _id: string;
      app_id: string;
      function_id?: string;
      level: LogLevel;
      logtype: LogType;
      message: string;
      timestamp: string;
      extra:LogsExtra;
    }

    /** extra params for log query */
    interface LogQueryExtra {
      level?: LogLevel;
      logtype?: LogType;
      dateStart?: string; // ISO 8601 format
      dateEnd?: string; // ISO 8601 format
    }

    /** paged log entry response */
    interface PagedLogEntry {
      data: LogEntry[];
      total: number;
      pageNum: number;
      pageSize: number;
    }
  }

  /**
   * namespace Statistics
   *
   * backend api module: "statistics"
   */
  namespace Statistics {
    interface RequestStats {
      total: number;
      success: number;
      error: number;
    }

    interface FunctionStats {
      count: number;
      requests: RequestStats;
    }

    interface CollectionStats {
      name: string;
      count: number;
    }

    interface DatabaseStats {
      count: number;
      collections: CollectionStats[];
    }

    interface StorageStats {
      total_usage_mb: number;
    }

    interface Summary {
      functions: FunctionStats;
      database: DatabaseStats;
      storage: StorageStats;
    }

    interface FunctionRequestsResponse {
      date: string;
      count: number;
    }

    interface TopFunctionResponse {
      function_name: string;
      count: number;
    }
  }

  /**
   * namespace FunctionTemplate
   *
   * backend api module: "function_template"
   */
  namespace FunctionTemplate {
    type TemplateType = 'system' | 'user';

    interface FunctionTemplateRecord {
      id: string;
      _id: string;
      name: string;
      description: string;
      code: string;
      type: TemplateType;
      function_type: Api.Function.FunctionType;
      created_at: string;
      shared: boolean;
    }

    interface GetFunctionTemplatesRequest {
      appId:string;
      page?: number;
      length?: number;
    }

    interface GetFunctionTemplatesResponse {
      data: FunctionTemplateRecord[];
      total: number;
      pageNum: number;
      pageSize: number;
    }

    interface CreateFunctionTemplateRequest {
      appId: string;
      name: string;
      code: string;
      type?: TemplateType;
      shared?: boolean;
    }

    interface UpdateFunctionTemplateRequest {
      id: string;
      name?: string;
      code?: string;
      type?: TemplateType;
      shared?: boolean;
    }

    interface GetFunctionTemplateResponse extends FunctionTemplateRecord {}
  }

  /**
   * namespace FunctionTemplate
   *
   * backend api module: "function_template"
   */
  namespace Settings {
    type ApplicationStatus = "starting" | "running" | "stopping" | "stopped" | "error";

    interface Dependency {
      name: string;
      version: string;
    }

    interface DependenciesData {
      common: Dependency[];
      system: Dependency[];
    }

    interface EnvInfo {
      key: string;
      value: string;
    }

    interface EnvsData {
      user: EnvInfo[];
      system: EnvInfo[];
    }

    interface PackageInfo {
      name: string;
      author: string;
      description: string;
      description_type: string;
      versions: string[];
    }

    interface CorsConfig {
      allow_origins: string[];
      allow_credentials: boolean;
      allow_methods: string[];
      allow_headers: string[];
    }

    interface EmailNotification {
      enabled: boolean;
      smtpServer: string;
      port: number;
      username: string;
      password?: string;
      fromAddress: string;
    }

    interface WebhookNotification {
      enabled: boolean;
      url: string;
      method: string;
      template: string;
    }

    interface WeChatNotification {
      enabled: boolean;
      notificationId: string;
    }

    interface NotificationConfig {
      email: EmailNotification;
      webhook: WebhookNotification;
      wechat: WeChatNotification;
    }
  }
}
