/** The global namespace for the app */
declare namespace App {
  /** Theme namespace */
  namespace Theme {
    type ColorPaletteNumber = import('@sa/color').ColorPaletteNumber;

    /** Theme setting */
    interface ThemeSetting {
      /** Theme scheme */
      themeScheme: UnionKey.ThemeScheme;
      /** grayscale mode */
      grayscale: boolean;
      /** colour weakness mode */
      colourWeakness: boolean;
      /** Whether to recommend color */
      recommendColor: boolean;
      /** Theme color */
      themeColor: string;
      /** Other color */
      otherColor: OtherColor;
      /** Whether info color is followed by the primary color */
      isInfoFollowPrimary: boolean;
      /** Reset cache strategy */
      resetCacheStrategy: UnionKey.ResetCacheStrategy;
      /** Layout */
      layout: {
        /** Layout mode */
        mode: UnionKey.ThemeLayoutMode;
        /** Scroll mode */
        scrollMode: UnionKey.ThemeScrollMode;
        /**
         * Whether to reverse the horizontal mix
         *
         * if true, the vertical child level menus in left and horizontal first level menus in top
         */
        reverseHorizontalMix: boolean;
      };
      /** Page */
      page: {
        /** Whether to show the page transition */
        animate: boolean;
        /** Page animate mode */
        animateMode: UnionKey.ThemePageAnimateMode;
      };
      /** Header */
      header: {
        /** Header height */
        height: number;
        /** Header breadcrumb */
        breadcrumb: {
          /** Whether to show the breadcrumb */
          visible: boolean;
          /** Whether to show the breadcrumb icon */
          showIcon: boolean;
        };
        /** Multilingual */
        multilingual: {
          /** Whether to show the multilingual */
          visible: boolean;
        };
        globalSearch: {
          /** Whether to show the GlobalSearch */
          visible: boolean;
        };
      };
      /** Tab */
      tab: {
        /** Whether to show the tab */
        visible: boolean;
        /**
         * Whether to cache the tab
         *
         * If cache, the tabs will get from the local storage when the page is refreshed
         */
        cache: boolean;
        /** Tab height */
        height: number;
        /** Tab mode */
        mode: UnionKey.ThemeTabMode;
      };
      /** Fixed header and tab */
      fixedHeaderAndTab: boolean;
      /** Sider */
      sider: {
        /** Inverted sider */
        inverted: boolean;
        /** Sider width */
        width: number;
        /** Collapsed sider width */
        collapsedWidth: number;
        /** Sider width when the layout is 'vertical-mix' or 'horizontal-mix' */
        mixWidth: number;
        /** Collapsed sider width when the layout is 'vertical-mix' or 'horizontal-mix' */
        mixCollapsedWidth: number;
        /** Child menu width when the layout is 'vertical-mix' or 'horizontal-mix' */
        mixChildMenuWidth: number;
      };
      /** Footer */
      footer: {
        /** Whether to show the footer */
        visible: boolean;
        /** Whether fixed the footer */
        fixed: boolean;
        /** Footer height */
        height: number;
        /** Whether float the footer to the right when the layout is 'horizontal-mix' */
        right: boolean;
      };
      /** Watermark */
      watermark: {
        /** Whether to show the watermark */
        visible: boolean;
        /** Watermark text */
        text: string;
      };
      /** define some theme settings tokens, will transform to css variables */
      tokens: {
        light: ThemeSettingToken;
        dark?: {
          [K in keyof ThemeSettingToken]?: Partial<ThemeSettingToken[K]>;
        };
      };
    }

    interface OtherColor {
      info: string;
      success: string;
      warning: string;
      error: string;
    }

    interface ThemeColor extends OtherColor {
      primary: string;
    }

    type ThemeColorKey = keyof ThemeColor;

    type ThemePaletteColor = {
      [key in ThemeColorKey | `${ThemeColorKey}-${ColorPaletteNumber}`]: string;
    };

    type BaseToken = Record<string, Record<string, string>>;

    interface ThemeSettingTokenColor {
      /** the progress bar color, if not set, will use the primary color */
      nprogress?: string;
      container: string;
      layout: string;
      inverted: string;
      'base-text': string;
    }

    interface ThemeSettingTokenBoxShadow {
      header: string;
      sider: string;
      tab: string;
    }

    interface ThemeSettingToken {
      colors: ThemeSettingTokenColor;
      boxShadow: ThemeSettingTokenBoxShadow;
    }

    type ThemeTokenColor = ThemePaletteColor & ThemeSettingTokenColor;

    /** Theme token CSS variables */
    type ThemeTokenCSSVars = {
      colors: ThemeTokenColor & { [key: string]: string };
      boxShadow: ThemeSettingTokenBoxShadow & { [key: string]: string };
    };
  }

  /** Global namespace */
  namespace Global {
    type VNode = import('vue').VNode;
    type RouteLocationNormalizedLoaded = import('vue-router').RouteLocationNormalizedLoaded;
    type RouteKey = import('@elegant-router/types').RouteKey;
    type RouteMap = import('@elegant-router/types').RouteMap;
    type RoutePath = import('@elegant-router/types').RoutePath;
    type LastLevelRouteKey = import('@elegant-router/types').LastLevelRouteKey;

    /** The router push options */
    type RouterPushOptions = {
      query?: Record<string, string>;
      params?: Record<string, string>;
    };

    /** The global header props */
    interface HeaderProps {
      /** Whether to show the logo */
      showLogo?: boolean;
      /** Whether to show the menu toggler */
      showMenuToggler?: boolean;
      /** Whether to show the menu */
      showMenu?: boolean;
    }

    /** The global menu */
    type Menu = {
      /**
       * The menu key
       *
       * Equal to the route key
       */
      key: string;
      /** The menu label */
      label: string;
      /** The menu i18n key */
      i18nKey?: I18n.I18nKey | null;
      /** The route key */
      routeKey: RouteKey;
      /** The route path */
      routePath: RoutePath;
      /** The menu icon */
      icon?: () => VNode;
      /** The menu children */
      children?: Menu[];
    };

    type Breadcrumb = Omit<Menu, 'children'> & {
      options?: Breadcrumb[];
    };

    /** Tab route */
    type TabRoute = Pick<RouteLocationNormalizedLoaded, 'name' | 'path' | 'meta'> &
      Partial<Pick<RouteLocationNormalizedLoaded, 'fullPath' | 'query' | 'matched'>>;

    /** The global tab */
    type Tab = {
      /** The tab id */
      id: string;
      /** The tab label */
      label: string;
      /**
       * The new tab label
       *
       * If set, the tab label will be replaced by this value
       */
      newLabel?: string;
      /**
       * The old tab label
       *
       * when reset the tab label, the tab label will be replaced by this value
       */
      oldLabel?: string;
      /** The tab route key */
      routeKey: LastLevelRouteKey;
      /** The tab route path */
      routePath: RouteMap[LastLevelRouteKey];
      /** The tab route full path */
      fullPath: string;
      /** The tab fixed index */
      fixedIndex?: number | null;
      /**
       * Tab icon
       *
       * Iconify icon
       */
      icon?: string;
      /**
       * Tab local icon
       *
       * Local icon
       */
      localIcon?: string;
      /** I18n key */
      i18nKey?: I18n.I18nKey | null;
    };

    /** Form rule */
    type FormRule = import('naive-ui').FormItemRule;

    /** The global dropdown key */
    type DropdownKey = 'closeCurrent' | 'closeOther' | 'closeLeft' | 'closeRight' | 'closeAll';
  }

  /**
   * I18n namespace
   *
   * Locales type
   */
  namespace I18n {
    type RouteKey = import('@elegant-router/types').RouteKey;

    type LangType = 'en-US' | 'zh-CN';

    type LangOption = {
      label: string;
      key: LangType;
    };

    type I18nRouteKey = Exclude<RouteKey, 'root' | 'not-found'>;

    type FormMsg = {
      required: string;
      invalid: string;
    };

    type Schema = {
      system: {
        title: string;
        updateTitle: string;
        updateContent: string;
        updateConfirm: string;
        updateCancel: string;
      };
      common: {
        action: {
          _self: string;
          select: string;
        };
        add: string;
        addSuccess: string;
        backToHome: string;
        batchDelete: string;
        cancel: string;
        close: string;
        check: string;
        expandColumn: string;
        columnSetting: string;
        config: string;
        confirm: string;
        delete: string;
        deleteSuccess: string;
        confirmDelete: string;
        edit: string;
        warning: string;
        error: string;
        index: string;
        keywordSearch: string;
        logout: string;
        logoutConfirm: string;
        lookForward: string;
        modify: string;
        modifySuccess: string;
        noData: string;
        operate: string;
        pleaseCheckValue: string;
        refresh: string;
        reset: string;
        search: string;
        save: string;
        switch: string;
        tip: string;
        trigger: string;
        update: string;
        updateSuccess: string;
        addFailed: string;
        deleteFailed: string;
        fetchFailed: string;
        saveFailed: string;
        saveSuccess: string;
        userCenter: string;
        yesOrNo: {
          yes: string;
          no: string;
        };
      };
      request: {
        logout: string;
        logoutMsg: string;
        logoutWithModal: string;
        logoutWithModalMsg: string;
        refreshToken: string;
        tokenExpired: string;
      };
      theme: {
        themeSchema: { title: string } & Record<UnionKey.ThemeScheme, string>;
        grayscale: string;
        colourWeakness: string;
        layoutMode: { title: string; reverseHorizontalMix: string } & Record<UnionKey.ThemeLayoutMode, string>;
        recommendColor: string;
        recommendColorDesc: string;
        themeColor: {
          title: string;
          followPrimary: string;
        } & Theme.ThemeColor;
        scrollMode: { title: string } & Record<UnionKey.ThemeScrollMode, string>;
        page: {
          animate: string;
          mode: { title: string } & Record<UnionKey.ThemePageAnimateMode, string>;
        };
        fixedHeaderAndTab: string;
        header: {
          height: string;
          breadcrumb: {
            visible: string;
            showIcon: string;
          };
          multilingual: {
            visible: string;
          };
          globalSearch: {
            visible: string;
          };
        };
        tab: {
          visible: string;
          cache: string;
          height: string;
          mode: { title: string } & Record<UnionKey.ThemeTabMode, string>;
        };
        sider: {
          inverted: string;
          width: string;
          collapsedWidth: string;
          mixWidth: string;
          mixCollapsedWidth: string;
          mixChildMenuWidth: string;
        };
        footer: {
          visible: string;
          fixed: string;
          height: string;
          right: string;
        };
        watermark: {
          visible: string;
          text: string;
        };
        themeDrawerTitle: string;
        pageFunTitle: string;
        resetCacheStrategy: { title: string } & Record<UnionKey.ResetCacheStrategy, string>;
        configOperation: {
          copyConfig: string;
          copySuccessMsg: string;
          resetConfig: string;
          resetSuccessMsg: string;
        };
      };
      route: Record<I18nRouteKey, string>;
      page: {
        login: {
          common: {
            loginOrRegister: string;
            userNamePlaceholder: string;
            phonePlaceholder: string;
            codePlaceholder: string;
            passwordPlaceholder: string;
            confirmPasswordPlaceholder: string;
            codeLogin: string;
            confirm: string;
            back: string;
            validateSuccess: string;
            loginSuccess: string;
            welcomeBack: string;
            captchaPlaceholder: string;
          };
          pwdLogin: {
            title: string;
            rememberMe: string;
            forgetPassword: string;
            register: string;
            otherAccountLogin: string;
            otherLoginMode: string;
            superAdmin: string;
            admin: string;
            user: string;
          };
          codeLogin: {
            title: string;
            getCode: string;
            reGetCode: string;
            sendCodeSuccess: string;
            imageCodePlaceholder: string;
          };
          register: {
            title: string;
            agreement: string;
            protocol: string;
            policy: string;
          };
          resetPwd: {
            title: string;
          };
          bindWeChat: {
            title: string;
          };
        };
        home: {
          search: string;
          searchPlaceholder: string;
          appName: string;
          appDesc: string;
          appStatus: string;
          appId: string;
          emptyApp: string;
          createApp: string;
          welcome: string;
          welcomeDescription: string;
          miniProgram: string;
          androidOrIos: string;
          blogOrWebsite: string;
          enterpriseInfo: string;
          handyCloud: string;
          explore: string;
          createYourApp: string;
          newApplication: string;
          pause: string;
          start: string;
          restart: string;
          deleteConfirm: string;
          appNamePlaceholder: string;
          appDescPlaceholder: string;
          create: string;
          appCreationRequestSent: string;
          appNowRunning: string;
          stopCheckingStatus: string;
          failedToCreateApp: string;
          errorCreatingApp: string;
          fillInCompletely: string;
          appDeleted: string;
          failedToDeleteApp: string;
          errorDeletingApp: string;
          appStarting: string;
          failedToStartApp: string;
          errorStartingApp: string;
          appStopping: string;
          failedToStopApp: string;
          errorStoppingApp: string;
          appRestarting: string;
          failedToRestartApp: string;
          errorRestartingApp: string;
        };
        apps: {
          functionCount: string;
          databaseCount: string;
          storageCount: string;
          requestCount: string;
          requestCountUnit: string;
          functionCountUnit: string;
          databaseCountUnit: string;
          storageCountUnit: string;
          top5Functions: string;
          unknown: string;
        };
        database: {
          collection: string;
          createCollection: string;
          collectionNamePlaceholder: string;
          createSuccess: string;
          insertDocument: string;
          createDocumentSuccess: string;
          jsonFormatError: string;
          confirmDelete: string;
          deleteDocumentConfirm: string;
          deleteSuccess: string;
          deleteCancelled: string;
          deleteCollectionConfirm: string;
          confirmClear: string;
          clearCollectionConfirm: string;
          clearSuccess: string;
          saveSuccess: string;
          saveFailed: string;
          cancelEdit: string;
          refreshSuccess: string;
          document: string;
          documentOperations: string;
          editContent: string;
          save: string;
          cancel: string;
          emptyDescription: string;
          idColumn: string;
          contentColumn: string;
          actionsColumn: string;
        };
        function: {
          createFunction: string;
          functionName: string;
          functionNamePlaceholder: string;
          functionType: string;
          apiFunction: string;
          commonFunction: string;
          functionTemplate: string;
          functionTemplatePlaceholder: string;
          functionDescription: string;
          functionDescriptionPlaceholder: string;
          tags: string;
          tagsPlaceholder: string;
          createSuccess: string;
          createFailed: string;
          confirmDelete: string;
          deleteConfirm: string;
          delete: string;
          deleteSuccess: string;
          saveSuccess: string;
          saveFailed: string;
          noHistory: string;
          confirmRollback: string;
          rollbackConfirm: string;
          rollback: string;
          rollbackSuccess: string;
          editorSettings: string;
          fontSize: string;
          codePreview: string;
          settingsSuccess: string;
          confirmDeleteDependence: string;
          deleteDependenceConfirm: string;
          deleteOnly: string;
          deleteAndRestart: string;
          dependenceDeleted: string;
          dependenceDeletedAndRestarting: string;
          deleteFailed: string;
          addDependenceSuccessAndRestarting: string;
          addDependenceSuccess: string;
          addDependenceFailed: string;
          getPackageInfoFailed: string;
          add: string;
          dependenceName: string;
          version: string;
          install: string;
          installAndRestart: string;
          dependenceManagement: string;
          getDependenceListFailed: string;
          installed: string;
          noDependence: string;
          systemDependence: string;
          noSystemDependence: string;
          dependenceNamePlaceholder: string;
          actions: string;
          envManagement: string;
          getEnvFailed: string;
          custom: string;
          noCustomEnv: string;
          systemBuiltin: string;
          noSystemBuiltinEnv: string;
          addEnv: string;
          key: string;
          value: string;
          addSuccess: string;
          addFailed: string;
          editEnv: string;
          updateSuccess: string;
          updateFailed: string;
          confirmDeleteEnv: string;
          deleteEnvConfirm: string;
          emptyDescription: string;
          functionEditor: string;
          publish: string;
          published: string;
          functionHistory: string;
          selectHistory: string;
          rollbackToThisVersion: string;
          functionList: string;
          envVariables: string;
          noFunctions: string;
          log: string;
          allLogs: string;
          functionLogs: string;
          systemLogs: string;
          functionTest: string;
          clickToSend: string;
          postFormatError: string;
          requesting: string;
          requestSuccessNoData: string;
          requestFailed: string;
          duplicateHeader: string;
          fillBlankHeader: string;
          cannotDeleteHeader: string;
          fillBlankQuery: string;
          addressCopied: string;
          copyFailed: string;
          responseCopied: string;
          headerPlaceholder: string;
          headerValuePlaceholder: string;
          queryParameters: string;
          keyPlaceholder: string;
          valuePlaceholder: string;
          bodyJson: string;
          sendRequest: string;
          response: string;
          responsePlaceholder: string;
        };
        log: {
          loadFunctionListFailed: string;
          requestFunctionListError: string;
          selectAppFirst: string;
          loadLogFailed: string;
          requestLogError: string;
          allFunctions: string;
          allLevels: string;
          allTypes: string;
          query: string;
          logDetail: string;
          time: string;
          level: string;
          type: string;
          functionName: string;
          selectLogToView: string;
          system: string;
          function: string;
          info: string;
          warning: string;
          error: string;
          debug: string;
          logContent: string;
          source: string;
        };
        storage: {
          root: string;
          newFolder: string;
          uploadFile: string;
          detail: string;
          preview: string;
          type: string;
          size: string;
          modifiedDate: string;
          download: string;
          folder: string;
          file: string;
          selectFileOrFolder: string;
          loadFailed: string;
          requestError: string;
          previewLinkFailed: string;
          loadJsonFailed: string;
          previewFailed: string;
          uploading: string;
          uploadFailed: string;
          uploadSuccess: string;
          uploadError: string;
          folderNamePlaceholder: string;
          confirm: string;
          cancel: string;
          folderNameEmpty: string;
          creatingFolder: string;
          createFailed: string;
          createSuccess: string;
          createError: string;
          enterFolder: string;
          backTo: string;
          confirmDelete: string;
          deleteConfirm: string;
          deleting: string;
          deleteFailed: string;
          deleteSuccess: string;
          deleteError: string;
          generatingLink: string;
          generateLinkFailed: string;
          downloadStarted: string;
          downloadFailed: string;
          name: string;
          actions: string;
        };
        setting: {
          dependencies: string;
          dependenciesTipTitle: string;
          dependenciesTipContent: string;
          userDependencies: string;
          systemDependencies: string;
          addDependency: string;
          dependencyName: string;
          dependencyNamePlaceholder: string;
          dependencyVersionPlaceholder: string;
          confirmDelete: string;
          deleteDependencyConfirm: string;
          restartRequired: string;
          dependencyChangeRestartPrompt: string;
          restartNow: string;
          restarting: string;
          restartingTip: string;
          restartInitiated: string;
          restartFailed: string;
          key: string;
          value: string;
          envTipTitle: string;
          envTipContent: string;
          userEnv: string;
          systemEnv: string;
          addEnv: string;
          editEnv: string;
          keyPlaceholder: string;
          valuePlaceholder: string;
          deleteEnvConfirm: string;
          envChangeRestartPrompt: string;
          corsTipTitle: string;
          corsTipContent: string;
          corsTipDynamicInput: string;
          originPlaceholder: string;
          methodPlaceholder: string;
          headerPlaceholder: string;
          notificationTipTitle: string;
          notificationTipContent: string;
          sendTest: string;
          dangerZone: string;
          confirmRestart: string;
          restartAppConfirm: string;
          restartApp: string;
          restartAppDesc: string;
          confirmStop: string;
          stopAppConfirm: string;
          stopApp: string;
          stopAppDesc: string;
          stopInitiated: string;
          stopFailed: string;
          confirmDeleteApp: string;
          deleteApp: string;
          deleteAppDesc: string;
          deleteAppConfirm1: string;
          deleteAppConfirm2: string;
          deleteAppConfirm3: string;
          deleteAppConfirm4: string;
          deleteInitiated: string;
          deleteFailed: string;
          general: string;
          api: string;
          database: string;
          functions: string;
          storage: string;
          users: string;
          notifications: string;
          appName: string;
          appNamePlaceholder: string;
          defaultLanguage: string;
          selectLanguage: string;
          themeMode: string;
          apiKeyManagement: string;
          manageApiKeys: string;
          corsConfig: string;
          corsPlaceholder: string;
          rateLimit: string;
          rateLimitPlaceholder: string;
          dbConnectionString: string;
          dbConnectionStringPlaceholder: string;
          dbBackupRestore: string;
          backupNow: string;
          runtimeEnvironment: string;
          selectRuntime: string;
          logLevel: string;
          selectLogLevel: string;
          timeout: string;
          timeoutPlaceholder: string;
          environmentVariables: string;
          envVarsPlaceholder: string;
          storagePath: string;
          storagePathPlaceholder: string;
          fileSizeLimit: string;
          fileSizeLimitPlaceholder: string;
          userRegistration: string;
          permissionManagement: string;
          managePermissions: string;
          smtpConfig: string;
          smtpConfigPlaceholder: string;
          webhookConfig: string;
          webhookConfigPlaceholder: string;
          cors: string;
          allowOrigins: string;
          allowCredentials: string;
          allowMethods: string;
          allowHeaders: string;
          emailNotifications: string;
          server: string;
          port: string;
          username: string;
          password: string;
          senderEmail: string;
          webhookNotifications: string;
          url: string;
          requestMethod: string;
          requestBodyTemplate: string;
          wechatNotifications: string;
          notificationId: string;
        };
        index: {
          branchDesc: string;
          greeting: string;
          weatherDesc: string;
          projectCount: string;
          todo: string;
          message: string;
          downloadCount: string;
          registerCount: string;
          schedule: string;
          study: string;
          work: string;
          rest: string;
          entertainment: string;
          visitCount: string;
          turnover: string;
          dealCount: string;
          projectNews: {
            title: string;
            moreNews: string;
            desc1: string;
            desc2: string;
            desc3: string;
            desc4: string;
            desc5: string;
          };
          creativity: string;
        };
      };
      form: {
        required: string;
        userName: FormMsg;
        phone: FormMsg;
        pwd: FormMsg;
        confirmPwd: FormMsg;
        code: FormMsg;
        email: FormMsg;
      };
      dropdown: Record<Global.DropdownKey, string>;
      icon: {
        themeConfig: string;
        themeSchema: string;
        lang: string;
        fullscreen: string;
        fullscreenExit: string;
        reload: string;
        collapse: string;
        expand: string;
        pin: string;
        unpin: string;
      };
      datatable: {
        itemCount: string;
      };
    };

    type GetI18nKey<T extends Record<string, unknown>, K extends keyof T = keyof T> = K extends string
      ? T[K] extends Record<string, unknown>
        ? `${K}.${GetI18nKey<T[K]>}`
        : K
      : never;

    type I18nKey = GetI18nKey<Schema>;

    type TranslateOptions<Locales extends string> = import('vue-i18n').TranslateOptions<Locales>;

    interface $T {
      (key: I18nKey): string;
      (key: I18nKey, plural: number, options?: TranslateOptions<LangType>): string;
      (key: I18nKey, defaultMsg: string, options?: TranslateOptions<I18nKey>): string;
      (key: I18nKey, list: unknown[], options?: TranslateOptions<I18nKey>): string;
      (key: I18nKey, list: unknown[], plural: number): string;
      (key: I18nKey, list: unknown[], defaultMsg: string): string;
      (key: I18nKey, named: Record<string, unknown>, options?: TranslateOptions<LangType>): string;
      (key: I18nKey, named: Record<string, unknown>, plural: number): string;
      (key: I18nKey, named: Record<string, unknown>, defaultMsg: string): string;
    }
  }

  /** Service namespace */
  namespace Service {
    /** Other baseURL key */
    type OtherBaseURLKey = 'demo';

    interface ServiceConfigItem {
      /** The backend service base url */
      baseURL: string;
      /** The proxy pattern of the backend service base url */
      proxyPattern: string;
    }

    interface OtherServiceConfigItem extends ServiceConfigItem {
      key: OtherBaseURLKey;
    }

    /** The backend service config */
    interface ServiceConfig extends ServiceConfigItem {
      /** Other backend service config */
      other: OtherServiceConfigItem[];
    }

    interface SimpleServiceConfig extends Pick<ServiceConfigItem, 'baseURL'> {
      other: Record<OtherBaseURLKey, string>;
    }

    /** The backend service response data */
    type Response<T = unknown> = {
      /** The backend service response code */
      code: string;
      /** The backend service response message */
      msg: string;
      /** The backend service response data */
      data: T;
    };

    /** The demo backend service response data */
    type DemoResponse<T = unknown> = {
      /** The backend service response code */
      status: string;
      /** The backend service response message */
      message: string;
      /** The backend service response data */
      result: T;
    };
  }
}
