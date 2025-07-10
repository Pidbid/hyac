<script setup lang="ts">
import { ref, computed, h } from 'vue';
import {
  NLayout,
  NLayoutSider,
  NLayoutContent,
  NMenu,
  NCard,
  NForm,
  NFormItem,
  NInput,
  NSelect,
  NSwitch,
  NButton,
  NInputNumber,
  NSplit,
  NTabs,
  NTabPane,
  NDynamicTags,
  NCollapse,
  NCollapseItem,
  NGrid,
  NFormItemGi,
  NImage
} from 'naive-ui';
import { $t } from '@/locales';
import {
  SettingsOutline,
  ServerOutline,
  FlashOutline,
  CloudUploadOutline,
  PersonOutline,
  NotificationsOutline,
  GlobeOutline
} from '@vicons/ionicons5';
import { useApplicationStore } from '@/store/modules/application';
import { corsData, corsUpdate, notificationData, notificationUpdate } from '@/service/api/settings';
import { onMounted } from 'vue';

const applicationStore = useApplicationStore();

defineOptions({
  name: 'SettingIndex'
});

const corsConfig = ref<Api.Settings.CorsConfig>({
  allow_origins: [],
  allow_credentials: true,
  allow_methods: [],
  allow_headers: []
});

const notificationSettingsData = ref<Api.Settings.NotificationConfig>({
  email: {
    enabled: false,
    smtpServer: '',
    port: 465,
    username: '',
    password: '',
    fromAddress: ''
  },
  webhook: {
    enabled: false,
    url: '',
    method: 'POST',
    template: ''
  },
  wechat: {
    enabled: false,
    notificationId: ''
  }
});

async function fetchCorsData() {
  const appId = applicationStore.appInfo.appId;
  if (appId) {
    const { data, error } = await corsData({ appId });
    if (!error) {
      corsConfig.value = data;
    }
  }
}

async function saveCorsSettings() {
  const appId = applicationStore.appInfo.appId;
  if (appId) {
    const { error } = await corsUpdate({ appId, config: corsConfig.value });
    if (!error) {
      window.$message?.success($t('common.saveSuccess' as any));
    } else {
      window.$message?.error($t('common.saveFailed' as any));
    }
  }
}

async function fetchNotificationData() {
  const appId = applicationStore.appInfo.appId;
  if (appId) {
    const { data, error } = await notificationData({ appId });
    if (!error) {
      notificationSettingsData.value = data;
    }
  }
}

async function saveNotificationSettings() {
  const appId = applicationStore.appInfo.appId;
  if (appId) {
    const { error } = await notificationUpdate({ appId, config: notificationSettingsData.value });
    if (!error) {
      window.$message?.success($t('common.saveSuccess' as any));
    } else {
      window.$message?.error($t('common.saveFailed' as any));
    }
  }
}

onMounted(() => {
  fetchCorsData();
  fetchNotificationData();
});

// Application Settings
const appActiveKey = ref('functions');
const appMenuOptions = computed(() => [
  {
    label: $t('page.setting.functions' as any),
    key: 'functions',
    icon: () => h(FlashOutline)
  },
  {
    label: $t('page.setting.users' as any),
    key: 'users',
    icon: () => h(PersonOutline)
  },
  {
    label: 'CORS',
    key: 'cors',
    icon: () => h(GlobeOutline)
  },
  {
    label: $t('page.setting.notifications' as any),
    key: 'notifications',
    icon: () => h(NotificationsOutline)
  }
]);
function handleAppMenuUpdate(key: string) {
  appActiveKey.value = key;
}

// --- Component Definitions ---

const GeneralSettings = {
  render: () =>
    h(
      NCard,
      { title: $t('page.setting.general' as any), bordered: false },
      {
        default: () =>
          h('div', [
            h(
              NForm,
              { labelPlacement: 'left', labelWidth: 'auto' },
              {
                default: () => [
                  h(
                    NFormItem,
                    { label: $t('page.setting.appName' as any) },
                    {
                      default: () => h(NInput, { value: applicationStore.appInfo.appName, readonly: true, disabled: true })
                    }
                  ),
                  h(
                    NFormItem,
                    { label: $t('page.setting.defaultLanguage' as any) },
                    {
                      default: () =>
                        h(NSelect, {
                          options: [
                            { label: '中文', value: 'zh-CN' },
                            { label: 'English', value: 'en-US' }
                          ],
                          placeholder: $t('page.setting.selectLanguage' as any)
                        })
                    }
                  ),
                  h(NFormItem, { label: $t('page.setting.themeMode' as any) }, { default: () => h(NSwitch, {}) })
                ]
              }
            ),
            h(
              NButton,
              { type: 'primary', class: 'mt-16px', onClick: () => console.log('General Settings Saved!') },
              { default: () => $t('common.save' as any) }
            )
          ])
      }
    )
};

const DatabaseSettings = {
  render: () =>
    h(
      NCard,
      { title: $t('page.setting.database' as any), bordered: false },
      {
        default: () =>
          h('div', [
            h(
              NForm,
              { labelPlacement: 'left', labelWidth: 'auto' },
              {
                default: () => [
                  h(
                    NFormItem,
                    { label: $t('page.setting.dbConnectionString' as any) },
                    { default: () => h(NInput, { placeholder: $t('page.setting.dbConnectionStringPlaceholder' as any) }) }
                  ),
                  h(
                    NFormItem,
                    { label: $t('page.setting.dbBackupRestore' as any) },
                    { default: () => h(NButton, { type: 'primary' }, { default: () => $t('page.setting.backupNow' as any) }) }
                  )
                ]
              }
            ),
            h(
              NButton,
              { type: 'primary', class: 'mt-16px', onClick: () => console.log('Database Settings Saved!') },
              { default: () => $t('common.save' as any) }
            )
          ])
      }
    )
};

const StorageSettings = {
  render: () =>
    h(
      NCard,
      { title: $t('page.setting.storage' as any), bordered: false },
      {
        default: () =>
          h('div', [
            h(
              NForm,
              { labelPlacement: 'left', labelWidth: 'auto' },
              {
                default: () => [
                  h(
                    NFormItem,
                    { label: $t('page.setting.storagePath' as any) },
                    { default: () => h(NInput, { placeholder: $t('page.setting.storagePathPlaceholder' as any) }) }
                  ),
                  h(
                    NFormItem,
                    { label: $t('page.setting.fileSizeLimit' as any) },
                    { default: () => h(NInputNumber, { placeholder: $t('page.setting.fileSizeLimitPlaceholder' as any) }) }
                  )
                ]
              }
            ),
            h(
              NButton,
              { type: 'primary', class: 'mt-16px', onClick: () => console.log('Storage Settings Saved!') },
              { default: () => $t('common.save' as any) }
            )
          ])
      }
    )
};

const NotificationsSettings = {
  render: () =>
    h(
      NCard,
      { title: $t('page.setting.notifications' as any), bordered: false },
      {
        default: () =>
          h('div', [
            h(
              NCollapse,
              { defaultExpandedNames: ['email'] },
              {
                default: () => [
                  // Email Settings
                  h(
                    NCollapseItem,
                    { name: 'email' },
                    {
                      header: () => h('div', { class: 'font-bold' }, 'EMail ' + $t('page.setting.notifications' as any)),
                      'header-extra': () =>
                        h(NSwitch, {
                          value: notificationSettingsData.value.email.enabled,
                          'on-update:value': (val: boolean) => (notificationSettingsData.value.email.enabled = val)
                        }),
                      default: () =>
                        h(
                          NForm,
                          { model: notificationSettingsData.value.email, labelPlacement: 'left', labelWidth: 'auto' },
                          {
                            default: () =>
                              h(
                                NGrid,
                                { xGap: 24, yGap: 12, cols: 1 },
                                {
                                  default: () => [
                                    h(
                                      NFormItemGi,
                                      { label: 'SMTP ' + $t('page.setting.server' as any) },
                                      {
                                        default: () =>
                                          h(NInput, {
                                            value: notificationSettingsData.value.email.smtpServer,
                                            'on-update:value': (val: string) =>
                                              (notificationSettingsData.value.email.smtpServer = val)
                                          })
                                      }
                                    ),
                                    h(
                                      NFormItemGi,
                                      { label: $t('page.setting.port' as any) },
                                      {
                                        default: () =>
                                          h(NInputNumber, {
                                            value: notificationSettingsData.value.email.port,
                                            'on-update:value': (val: number | null) =>
                                              (notificationSettingsData.value.email.port = val ?? 0)
                                          })
                                      }
                                    ),
                                    h(
                                      NFormItemGi,
                                      { label: $t('page.setting.username' as any) },
                                      {
                                        default: () =>
                                          h(NInput, {
                                            value: notificationSettingsData.value.email.username,
                                            'on-update:value': (val: string) =>
                                              (notificationSettingsData.value.email.username = val)
                                          })
                                      }
                                    ),
                                    h(
                                      NFormItemGi,
                                      { label: $t('page.setting.password' as any) },
                                      {
                                        default: () =>
                                          h(NInput, {
                                            type: 'password',
                                            showPasswordOn: 'click',
                                            value: notificationSettingsData.value.email.password,
                                            'on-update:value': (val: string) =>
                                              (notificationSettingsData.value.email.password = val)
                                          })
                                      }
                                    ),
                                    h(
                                      NFormItemGi,
                                      { label: $t('page.setting.senderEmail' as any) },
                                      {
                                        default: () =>
                                          h(NInput, {
                                            value: notificationSettingsData.value.email.fromAddress,
                                            'on-update:value': (val: string) =>
                                              (notificationSettingsData.value.email.fromAddress = val)
                                          })
                                      }
                                    )
                                  ]
                                }
                              )
                          }
                        )
                    }
                  ),
                  // Webhook Settings
                  h(
                    NCollapseItem,
                    { name: 'webhook' },
                    {
                      header: () => h('div', { class: 'font-bold' }, 'WebHook ' + $t('page.setting.notifications' as any)),
                      'header-extra': () =>
                        h(NSwitch, {
                          value: notificationSettingsData.value.webhook.enabled,
                          'on-update:value': (val: boolean) => (notificationSettingsData.value.webhook.enabled = val)
                        }),
                      default: () =>
                        h(
                          NForm,
                          { model: notificationSettingsData.value.webhook, labelPlacement: 'left', labelWidth: 'auto' },
                          {
                            default: () =>
                              h(
                                NGrid,
                                { xGap: 24, yGap: 12, cols: 1 },
                                {
                                  default: () => [
                                    h(
                                      NFormItemGi,
                                      { label: 'URL' },
                                      {
                                        default: () =>
                                          h(NInput, {
                                            value: notificationSettingsData.value.webhook.url,
                                            'on-update:value': (val: string) => (notificationSettingsData.value.webhook.url = val)
                                          })
                                      }
                                    ),
                                    h(
                                      NFormItemGi,
                                      { label: $t('page.setting.requestMethod' as any) },
                                      {
                                        default: () =>
                                          h(NSelect, {
                                            options: [
                                              { label: 'POST', value: 'POST' },
                                              { label: 'GET', value: 'GET' }
                                            ],
                                            value: notificationSettingsData.value.webhook.method,
                                            'on-update:value': (val: string) =>
                                              (notificationSettingsData.value.webhook.method = val)
                                          })
                                      }
                                    ),
                                    h(
                                      NFormItemGi,
                                      { label: $t('page.setting.requestBodyTemplate' as any) },
                                      {
                                        default: () =>
                                          h(NInput, {
                                            type: 'textarea',
                                            value: notificationSettingsData.value.webhook.template,
                                            'on-update:value': (val: string) =>
                                              (notificationSettingsData.value.webhook.template = val)
                                          })
                                      }
                                    )
                                  ]
                                }
                              )
                          }
                        )
                    }
                  ),
                  // WeChat Settings
                  h(
                    NCollapseItem,
                    { name: 'wechat' },
                    {
                      header: () => h('div', { class: 'font-bold' }, $t('page.setting.wechatNotifications' as any)),
                      'header-extra': () =>
                        h(NSwitch, {
                          value: notificationSettingsData.value.wechat.enabled,
                          'on-update:value': (val: boolean) => (notificationSettingsData.value.wechat.enabled = val)
                        }),
                      default: () =>
                        h(
                          NGrid,
                          { xGap: 24, yGap: 12, cols: 1, class: 'mt-4' },
                          {
                            default: () => [
                              h(
                                NFormItemGi,
                                { span: 1 },
                                {
                                  default: () =>
                                    h(NImage, {
                                      width: '100',
                                      src: 'https://07akioni.oss-cn-beijing.aliyuncs.com/07akioni.jpeg'
                                    })
                                }
                              ),
                              h(
                                NFormItemGi,
                                { label: '通知ID', span: 1 },
                                {
                                  default: () =>
                                    h(NInput, {
                                      value: notificationSettingsData.value.wechat.notificationId,
                                      'on-update:value': (val: string) =>
                                        (notificationSettingsData.value.wechat.notificationId = val)
                                    })
                                }
                              )
                            ]
                          }
                        )
                    }
                  )
                ]
              }
            ),
            h(
              NButton,
              {
                type: 'primary',
                class: 'mt-16px',
                onClick: saveNotificationSettings
              },
              { default: () => $t('common.save' as any) }
            )
          ])
      }
    )
};

const FunctionsSettings = {
  render: () =>
    h(
      NCard,
      { title: $t('page.setting.functions' as any), bordered: false },
      {
        default: () =>
          h('div', [
            h(
              NForm,
              { labelPlacement: 'left', labelWidth: 'auto' },
              {
                default: () => [
                  h(
                    NFormItem,
                    { label: $t('page.setting.runtimeEnvironment' as any) },
                    {
                      default: () =>
                        h(NSelect, {
                          options: [
                            { label: 'Python 3.9', value: 'python3.9' },
                            { label: 'Python 3.10', value: 'python3.10' }
                          ],
                          placeholder: $t('page.setting.selectRuntime' as any)
                        })
                    }
                  ),
                  h(
                    NFormItem,
                    { label: $t('page.setting.logLevel' as any) },
                    {
                      default: () =>
                        h(NSelect, {
                          options: [
                            { label: 'INFO', value: 'INFO' },
                            { label: 'DEBUG', value: 'DEBUG' },
                            { label: 'ERROR', value: 'ERROR' }
                          ],
                          placeholder: $t('page.setting.selectLogLevel' as any)
                        })
                    }
                  ),
                  h(
                    NFormItem,
                    { label: $t('page.setting.timeout' as any) },
                    { default: () => h(NInputNumber, { placeholder: $t('page.setting.timeoutPlaceholder' as any) }) }
                  ),
                  h(
                    NFormItem,
                    { label: $t('page.setting.environmentVariables' as any) },
                    { default: () => h(NInput, { type: 'textarea', placeholder: $t('page.setting.envVarsPlaceholder' as any) }) }
                  )
                ]
              }
            ),
            h(
              NButton,
              { type: 'primary', class: 'mt-16px', onClick: () => console.log('Functions Settings Saved!') },
              { default: () => $t('common.save' as any) }
            )
          ])
      }
    )
};

const UsersSettings = {
  render: () =>
    h(
      NCard,
      { title: $t('page.setting.users' as any), bordered: false },
      {
        default: () =>
          h('div', [
            h(
              NForm,
              { labelPlacement: 'left', labelWidth: 'auto' },
              {
                default: () => [
                  h(NFormItem, { label: $t('page.setting.userRegistration' as any) }, { default: () => h(NSwitch, {}) }),
                  h(
                    NFormItem,
                    { label: $t('page.setting.permissionManagement' as any) },
                    { default: () => h(NButton, { type: 'primary' }, { default: () => $t('page.setting.managePermissions' as any) }) }
                  )
                ]
              }
            ),
            h(
              NButton,
              { type: 'primary', class: 'mt-16px', onClick: () => console.log('Users Settings Saved!') },
              { default: () => $t('common.save' as any) }
            )
          ])
      }
    )
};

const CorsSettings = {
  render: () =>
    h(
      NCard,
      { title: 'CORS', bordered: false },
      {
        default: () =>
          h('div', [
            h(
              NForm,
              { model: corsConfig.value, labelPlacement: 'left', labelWidth: 'auto' },
              {
                default: () => [
                  h(
                    NFormItem,
                    { label: 'Allow Origins' },
                    {
                      default: () =>
                        h(NDynamicTags, {
                          value: corsConfig.value.allow_origins,
                          'on-update:value': (val: string[]) => {
                            corsConfig.value.allow_origins = val;
                          }
                        })
                    }
                  ),
                  h(
                    NFormItem,
                    { label: 'Allow Credentials' },
                    {
                      default: () =>
                        h(NSwitch, {
                          value: corsConfig.value.allow_credentials,
                          'on-update:value': (val: boolean) => {
                            corsConfig.value.allow_credentials = val;
                          }
                        })
                    }
                  ),
                  h(
                    NFormItem,
                    { label: 'Allow Methods' },
                    {
                      default: () =>
                        h(NDynamicTags, {
                          value: corsConfig.value.allow_methods,
                          'on-update:value': (val: string[]) => {
                            corsConfig.value.allow_methods = val;
                          }
                        })
                    }
                  ),
                  h(
                    NFormItem,
                    { label: 'Allow Headers' },
                    {
                      default: () =>
                        h(NDynamicTags, {
                          value: corsConfig.value.allow_headers,
                          'on-update:value': (val: string[]) => {
                            corsConfig.value.allow_headers = val;
                          }
                        })
                    }
                  )
                ]
              }
            ),
            h(
              NButton,
              { type: 'primary', class: 'mt-16px', onClick: saveCorsSettings },
              { default: () => $t('common.save' as any) }
            )
          ])
      }
    )
};

const appCurrentComponent = computed(() => {
  switch (appActiveKey.value) {
    case 'functions':
      return FunctionsSettings;
    case 'users':
      return UsersSettings;
    case 'cors':
      return CorsSettings;
    case 'notifications':
      return NotificationsSettings;
    default:
      return FunctionsSettings;
  }
});
</script>

<template>
  <NCard :bordered="false" class="h-full" content-style="padding: 0; height: 100%;">
    <NSplit direction="horizontal" :default-size="0.1" class="h-full">
      <template #1>
        <div class="h-full">
          <NMenu
            :value="appActiveKey"
            :options="appMenuOptions"
            :collapsed-width="64"
            :collapsed-icon-size="22"
            :on-update:value="handleAppMenuUpdate"
          />
        </div>
      </template>
      <template #2>
        <div class="p-16px h-full">
          <component :is="appCurrentComponent" />
        </div>
      </template>
    </NSplit>
  </NCard>
</template>

<style scoped>
:deep(.n-split__pane-1) {
  background-color: var(--n-color);
}
</style>
