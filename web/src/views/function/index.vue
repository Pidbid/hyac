<script setup lang="ts">
/* eslint-disable @typescript-eslint/no-use-before-define, no-underscore-dangle */
import { computed, h, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { useStorage } from '@vueuse/core';
import {
  NButton,
  NButtonGroup,
  NDataTable,
  NEmpty,
  NForm,
  NFormItem,
  NIcon,
  NInput,
  NInputNumber,
  NList,
  NListItem,
  NRadio,
  NRadioGroup,
  NScrollbar,
  NSelect,
  NSpace,
  NSpin,
  NSplit,
  NSwitch,
  NTabPane,
  NTabs,
  NThing,
  type SelectOption,
  useDialog,
  useMessage
} from 'naive-ui';
import dayjs from 'dayjs';
import {
  AddOutline,
  BeakerOutline,
  BrushOutline,
  CloseOutline,
  LinkOutline,
  SearchOutline,
  SparklesOutline,
  TimerOutline
} from '@vicons/ionicons5';
import {
  CreateFunction,
  DeleteFunction,
  FunctionHistory,
  GetFunctionData,
  UpdateFunctionCode,
  UpdateFunctionMeta,
  addEnv,
  dependenceSearch,
  dependenciesData,
  getDomain,
  getEnvsData,
  getFunctionTags,
  getFunctionTemplates,
  packageAdd,
  packageInfo,
  packageRemove,
  removeEnv,
  restartApp
} from '@/service/api';
import { useApplicationStore } from '@/store/modules/application';
import { useFunctionStore } from '@/store/modules/function';
import { useAppStore } from '@/store/modules/app';
import { $t } from '@/locales';
import FunctionList from './modules/FunctionList.vue';
import FunctionEditorPanel from './modules/FunctionEditorPanel.vue';
import FunctionLogPanel from './modules/FunctionLogPanel.vue';
import FunctionTestPanel from './modules/FunctionTestPanel.vue';
import FunctionCronPanel from './modules/FunctionCronPanel.vue';
import FunctionHistoryModal from './modules/FunctionHistoryModal.vue';
import AiAssistantWindow from './modules/AiAssistantWindow.vue';

const message = useMessage();
const dialog = useDialog();
const applicationStore = useApplicationStore();
const functionStore = useFunctionStore();
const appStore = useAppStore();
const router = useRouter();

const isDependenceLoading = ref(false);
const dependenceTabsRef = ref<undefined | HTMLElement>(undefined);
const packageSelectInput = ref({
  name: '',
  version: ''
});
const packageResult = ref<Api.Settings.PackageInfo[]>([]);
let addDependenceDialogRef: any = null;
const commonDependencies = ref<Api.Settings.Dependency[]>([]);
const systemDependencies = ref<Api.Settings.Dependency[]>([]);
const userEnv = ref<Api.Settings.EnvInfo[]>([]);
const systemEnv = ref<Api.Settings.EnvInfo[]>([]);
const storedEditorConfig = localStorage.getItem('editorConfig');
const editorConfig = ref(
  storedEditorConfig
    ? JSON.parse(storedEditorConfig)
    : {
        language: 'python',
        fontSize: 14,
        minimap: true,
        themeName: 'vs-dark',
        lineNumbers: true
      }
);

watch(
  () => editorConfig.value,
  newValue => {
    localStorage.setItem('editorConfig', JSON.stringify(newValue));
  },
  { deep: true }
);

// State
const functions = ref<Api.Function.FunctionInfo[]>([]);
const selectedFunction = ref<Api.Function.FunctionInfo>({
  id: '',
  name: '',
  type: 'endpoint',
  status: 'unpublished',
  description: '',
  tags: [],
  code: ''
});
const originalCode = ref('');
const codeChanged = ref(false);
const codeDrafts = reactive<Record<string, { code: string; originalCode: string }>>({});
const isSaving = ref(false);
const functionRequestData = ref({ page: 1, length: 50 });
const tags = ref<string[]>([]);
const selectedTag = ref('all');
const sidebarCollapsed = ref(false);

const showHistoryModel = ref(false);
const historyData = ref<Api.Function.FunctionHistoryInfo[]>([]);
const showAiWindow = ref(false);
const pageSplitSize = useStorage('function-page-split-size', 0.12);
const workspaceSplitSize = useStorage('function-workspace-split-size', 0.82);
const editorLogSplitSize = useStorage('function-editor-log-split-size', 0.7);
const activePanel = useStorage<'test' | 'cron'>('function-active-panel', 'test');
const logCollapsed = useStorage('function-log-collapsed', false);
const logAnimState = ref<'idle' | 'collapsing' | 'expanding'>('idle');
let logAnimTimer: number | null = null;
let editorLayoutTimer: number | null = null;
const editorPanelRef = ref<InstanceType<typeof FunctionEditorPanel> | null>(null);

function scheduleEditorLayout(delay: number) {
  if (editorLayoutTimer !== null) {
    window.clearTimeout(editorLayoutTimer);
  }
  editorLayoutTimer = window.setTimeout(() => {
    nextTick(() => {
      editorPanelRef.value?.layoutEditor();
      window.requestAnimationFrame(() => {
        editorPanelRef.value?.layoutEditor();
      });
    });
    editorLayoutTimer = null;
  }, delay);
}

function clearLogAnimTimer() {
  if (logAnimTimer !== null) {
    window.clearTimeout(logAnimTimer);
    logAnimTimer = null;
  }
  if (editorLayoutTimer !== null) {
    window.clearTimeout(editorLayoutTimer);
    editorLayoutTimer = null;
  }
}

function handleCollapseLog() {
  clearLogAnimTimer();
  logAnimState.value = 'collapsing';
  logAnimTimer = window.setTimeout(() => {
    logCollapsed.value = true;
    logAnimState.value = 'idle';
    logAnimTimer = null;
    scheduleEditorLayout(50);
  }, 300);
}

function handleExpandLog() {
  clearLogAnimTimer();
  logCollapsed.value = false;
  logAnimState.value = 'expanding';
  scheduleEditorLayout(50);
  logAnimTimer = window.setTimeout(() => {
    logAnimState.value = 'idle';
    logAnimTimer = null;
  }, 350);
}

function handleSplitDragMove() {
  scheduleEditorLayout(0);
}

function handleSplitDragEnd() {
  scheduleEditorLayout(80);
}

// Computed
const functionAddress = computed(() => {
  const domain = localStorage.getItem('hyac_domain');
  if (selectedFunction.value.id !== '' && domain) {
    return `https://${applicationStore.appId}.${domain}/${selectedFunction.value.id}`;
  }
  return '';
});

function cloneFunctionInfo(func: Api.Function.FunctionInfo): Api.Function.FunctionInfo {
  return {
    ...func,
    tags: [...func.tags]
  };
}

function cacheCurrentCodeDraft() {
  const { id, code } = selectedFunction.value;
  if (!id) return;

  if (code !== originalCode.value) {
    codeDrafts[id] = { code, originalCode: originalCode.value };
  } else {
    delete codeDrafts[id];
  }
}

function setSelectedFunction(func: Api.Function.FunctionInfo) {
  const draft = codeDrafts[func.id];
  const nextFunction = cloneFunctionInfo(func);

  if (draft) {
    nextFunction.code = draft.code;
  }

  selectedFunction.value = nextFunction;
  originalCode.value = draft?.originalCode ?? func.code;
  codeChanged.value = selectedFunction.value.code !== originalCode.value;
  functionStore.setFuncInfo(cloneFunctionInfo(selectedFunction.value));
}

// Watchers
watch(
  () => selectedFunction.value.code,
  newCode => {
    codeChanged.value = newCode !== originalCode.value;
  }
);

// Methods
const getFunctionData = async () => {
  let type: string | undefined;
  let tag: string | undefined;

  if (selectedTag.value === 'api') {
    type = 'endpoint';
  } else if (selectedTag.value === 'common') {
    type = 'common';
  } else if (selectedTag.value !== 'all') {
    tag = selectedTag.value;
  }

  const { data, error } = await GetFunctionData(
    applicationStore.appId,
    functionRequestData.value.page,
    functionRequestData.value.length,
    type,
    tag
  );

  if (!error) {
    cacheCurrentCodeDraft();
    functions.value = data.data.map((func: Api.Function.FunctionRecord) => ({
      id: func.function_id,
      name: func.function_name,
      type: func.function_type,
      status: func.status,
      description: func.description,
      tags: func.tags,
      code: func.code
    }));
    if (functions.value.length > 0) {
      const selectedId = selectedFunction.value.id || functionStore.funcInfo?.id;
      const funcToSelect = functions.value.find(f => f.id === selectedId) ?? functions.value[0];
      setSelectedFunction(funcToSelect);
    } else {
      selectedFunction.value = {
        id: '',
        name: '',
        type: 'endpoint',
        status: 'unpublished',
        description: '',
        tags: [],
        code: ''
      };
      originalCode.value = '';
      codeChanged.value = false;
      functionStore.setFuncInfo(null);
    }
  }
};

const fetchTags = async () => {
  const { data, error } = await getFunctionTags(applicationStore.appId);
  if (!error) {
    tags.value = data;
  }
};

const handleTagSelect = (tag: string) => {
  selectedTag.value = tag;
  getFunctionData();
};

const functionSelect = (func: Api.Function.FunctionInfo) => {
  cacheCurrentCodeDraft();
  setSelectedFunction(func);
};

const handleCreateFunction = () => {
  const formRef = ref<any>(null);
  const localCreateData = reactive({
    name: '',
    description: '',
    type: 'endpoint',
    template_id: '',
    tags: [] as string[],
    templateOptions: [] as SelectOption[]
  });

  const rules = {
    name: { required: true, message: $t('page.function.functionNamePlaceholder'), trigger: 'blur' },
    template_id: { required: true, message: $t('page.function.functionTemplatePlaceholder'), trigger: 'change' }
  };

  const fetchLocalTemplates = async (functionType: string) => {
    const { data, error } = await getFunctionTemplates(applicationStore.appId, 1, 100, functionType);
    if (!error) {
      localCreateData.templateOptions = data.data.map((template: Api.FunctionTemplate.FunctionTemplateRecord) => ({
        label: template.name,
        value: template._id
      }));
    }
  };

  fetchLocalTemplates(localCreateData.type);

  const d = dialog.info({
    title: $t('page.function.createFunction'),
    content: () =>
      h(
        NForm,
        {
          ref: formRef,
          model: localCreateData,
          rules,
          labelPlacement: 'left',
          labelWidth: 80,
          onKeyup: (e: KeyboardEvent) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              (d.onPositiveClick as any)();
            }
          }
        },
        {
          default: () => [
            h(
              NFormItem,
              { label: $t('page.function.functionName'), path: 'name' },
              {
                default: () =>
                  h(NInput, {
                    placeholder: $t('page.function.functionNamePlaceholder'),
                    value: localCreateData.name,
                    onUpdateValue: value => (localCreateData.name = value)
                  })
              }
            ),
            h(
              NFormItem,
              { label: $t('page.function.functionType') },
              {
                default: () =>
                  h(
                    NRadioGroup,
                    {
                      value: localCreateData.type,
                      onUpdateValue: value => {
                        localCreateData.type = value;
                        localCreateData.template_id = '';
                        fetchLocalTemplates(value);
                      }
                    },
                    {
                      default: () => [
                        h(NRadio, { label: $t('page.function.apiFunction'), value: 'endpoint' }),
                        h(NRadio, { label: $t('page.function.commonFunction'), value: 'common' })
                      ]
                    }
                  )
              }
            ),
            h(
              NFormItem,
              { label: $t('page.function.functionTemplate'), path: 'template_id' },
              {
                default: () =>
                  h(NSelect, {
                    placeholder: $t('page.function.functionTemplatePlaceholder'),
                    options: localCreateData.templateOptions,
                    value: localCreateData.template_id,
                    onUpdateValue: value => (localCreateData.template_id = value)
                  })
              }
            ),
            h(
              NFormItem,
              { label: $t('page.function.functionDescription') },
              {
                default: () =>
                  h(NInput, {
                    type: 'textarea',
                    placeholder: $t('page.function.functionDescriptionPlaceholder'),
                    value: localCreateData.description,
                    onUpdateValue: value => (localCreateData.description = value)
                  })
              }
            ),
            h(
              NFormItem,
              { label: $t('page.function.tags') },
              {
                default: () =>
                  h(NInput, {
                    placeholder: $t('page.function.tagsPlaceholder'),
                    value: localCreateData.tags.join(','),
                    onUpdateValue: value => (localCreateData.tags = value.split(',').map(tag => tag.trim()))
                  })
              }
            )
          ]
        }
      ),
    positiveText: $t('common.confirm'),
    negativeText: $t('common.cancel'),
    onNegativeClick: () => {
      localCreateData.name = '';
      localCreateData.description = '';
      localCreateData.type = 'endpoint';
      localCreateData.template_id = '';
      localCreateData.tags = [];
    },
    onPositiveClick: () => {
      formRef.value?.validate(async (errors: any) => {
        if (!errors) {
          const { error } = await CreateFunction(
            applicationStore.appId,
            localCreateData.name,
            localCreateData.type,
            localCreateData.description,
            localCreateData.tags,
            appStore.locale,
            localCreateData.template_id
          );
          if (!error) {
            message.success($t('page.function.createSuccess'));
            await getFunctionData();
            const newFunc = functions.value.find(func => func.name === localCreateData.name);
            localCreateData.name = '';
            localCreateData.description = '';
            localCreateData.type = 'endpoint';
            localCreateData.template_id = '';
            localCreateData.tags = [];
            if (newFunc) {
              functionSelect(newFunc);
            }
          } else {
            message.error($t('page.function.createFailed'));
          }
        }
      });
    }
  });
};

const handleDeleteFunction = (func: Api.Function.FunctionInfo) => {
  dialog.warning({
    title: $t('page.function.confirmDelete'),
    content: $t('page.function.deleteConfirm', { name: func.name }),
    positiveText: $t('common.delete'),
    negativeText: $t('common.cancel'),
    onPositiveClick: async () => {
      const { error } = await DeleteFunction(applicationStore.appId, func.id);
      if (!error) {
        message.success($t('page.function.deleteSuccess'));
        await getFunctionData();
        if (selectedFunction.value.id === func.id) {
          if (functions.value.length > 0) {
            functionSelect(functions.value[0]);
          } else {
            selectedFunction.value = {
              id: '',
              name: '',
              type: 'endpoint',
              status: 'published',
              description: '',
              tags: [],
              code: ''
            };
            originalCode.value = '';
            codeChanged.value = false;
          }
        }
      }
    }
  });
};

const handleSaveCode = async () => {
  if (!codeChanged.value || isSaving.value) return;
  const savingFunctionId = selectedFunction.value.id;
  const savedCode = selectedFunction.value.code;

  isSaving.value = true;
  try {
    const { error } = await UpdateFunctionCode(applicationStore.appId, savingFunctionId, savedCode);
    if (!error) {
      message.success($t('page.function.saveSuccess'));

      if (selectedFunction.value.id === savingFunctionId) {
        originalCode.value = savedCode;
        codeChanged.value = selectedFunction.value.code !== savedCode;
        if (codeChanged.value) {
          codeDrafts[savingFunctionId] = { code: selectedFunction.value.code, originalCode: savedCode };
        } else {
          delete codeDrafts[savingFunctionId];
        }
        functionStore.setFuncInfo(cloneFunctionInfo(selectedFunction.value));
      } else if (codeDrafts[savingFunctionId]?.code === savedCode) {
        delete codeDrafts[savingFunctionId];
      } else if (codeDrafts[savingFunctionId]) {
        codeDrafts[savingFunctionId].originalCode = savedCode;
      }

      await getFunctionData();
    } else {
      message.error($t('page.function.saveFailed'));
    }
  } finally {
    isSaving.value = false;
  }
};

const handleOpenHistory = async () => {
  const { data, error } = await FunctionHistory(applicationStore.appId, selectedFunction.value.id);
  if (!error) {
    historyData.value = data.data;
    if (data.data.length > 0) {
      showHistoryModel.value = true;
    } else {
      message.warning($t('page.function.noHistory'));
    }
  }
};

const handleRollback = async (history: Api.Function.FunctionHistoryInfo) => {
  dialog.warning({
    title: $t('page.function.confirmRollback'),
    content: $t('page.function.rollbackConfirm', { date: dayjs(history.updated_at).format('YYYY-MM-DD HH:mm:ss') }),
    positiveText: $t('page.function.rollback'),
    negativeText: $t('common.cancel'),
    onPositiveClick: async () => {
      selectedFunction.value.code = history.old_code;
      await nextTick();
      showHistoryModel.value = false;
      message.success($t('page.function.rollbackSuccess'));
    }
  });
};

const handleCloseAiWindow = () => {
  showAiWindow.value = false;
};

const toggleAiWindow = () => {
  showAiWindow.value = !showAiWindow.value;
};

const handleFunctionEditorSetting = () => {
  const tempConfig = reactive({
    fontSize: editorConfig.value.fontSize,
    language: 'python',
    minimap: editorConfig.value.minimap,
    lineNumbers: editorConfig.value.lineNumbers,
    themeName: editorConfig.value.themeName
  });

  const themeOptions = [
    { label: 'Visual Studio', value: 'vs' },
    { label: 'Visual Studio Dark', value: 'vs-dark' },
    { label: 'High Contrast', value: 'hc-black' }
  ];

  const d = dialog.info({
    title: $t('page.function.editorSettings'),
    content: () =>
      h(
        NForm,
        {
          labelPlacement: 'left',
          labelWidth: 80,
          onKeyup: (e: KeyboardEvent) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              (d.onPositiveClick as any)();
            }
          }
        },
        {
          default: () => [
            h(
              NFormItem,
              { label: $t('page.function.fontSize') },
              {
                default: () =>
                  h(NInputNumber, {
                    placeholder: '16',
                    value: tempConfig.fontSize,
                    onUpdateValue: value => {
                      if (value) tempConfig.fontSize = value;
                    }
                  })
              }
            ),
            h(
              NFormItem,
              { label: $t('page.function.codePreview') },
              {
                default: () =>
                  h(NSwitch, {
                    value: tempConfig.minimap,
                    onUpdateValue: value => {
                      tempConfig.minimap = value;
                    }
                  })
              }
            ),
            h(
              NFormItem,
              { label: $t('page.function.lineNumbers') },
              {
                default: () =>
                  h(NSwitch, {
                    value: tempConfig.lineNumbers,
                    onUpdateValue: value => {
                      tempConfig.lineNumbers = value;
                    }
                  })
              }
            ),
            h(
              NFormItem,
              { label: $t('page.function.theme') },
              {
                default: () =>
                  h(
                    NRadioGroup,
                    {
                      value: tempConfig.themeName,
                      onUpdateValue: value => {
                        tempConfig.themeName = value;
                      }
                    },
                    {
                      default: () => themeOptions.map(opt => h(NRadio, { label: opt.label, value: opt.value }))
                    }
                  )
              }
            )
          ]
        }
      ),
    positiveText: $t('common.confirm'),
    negativeText: $t('common.cancel'),
    onPositiveClick: () => {
      editorConfig.value.fontSize = tempConfig.fontSize;
      editorConfig.value.minimap = tempConfig.minimap;
      editorConfig.value.lineNumbers = tempConfig.lineNumbers;
      editorConfig.value.themeName = tempConfig.themeName;
      message.success($t('page.function.settingsSuccess'));
    }
  });
};

const handleEditMeta = () => {
  const formRef = ref<any>(null);
  const localEditData = reactive({
    name: selectedFunction.value.name,
    description: selectedFunction.value.description,
    tags: selectedFunction.value.tags
  });

  const rules = {
    name: { required: true, message: $t('page.function.functionNamePlaceholder'), trigger: 'blur' }
  };

  const d = dialog.info({
    title: $t('page.function.editFunction'),
    content: () =>
      h(
        NForm,
        {
          ref: formRef,
          model: localEditData,
          rules,
          labelPlacement: 'left',
          labelWidth: 80,
          onKeyup: (e: KeyboardEvent) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              (d.onPositiveClick as any)();
            }
          }
        },
        {
          default: () => [
            h(
              NFormItem,
              { label: $t('page.function.functionName'), path: 'name' },
              {
                default: () =>
                  h(NInput, {
                    placeholder: $t('page.function.functionNamePlaceholder'),
                    value: localEditData.name,
                    onUpdateValue: value => (localEditData.name = value)
                  })
              }
            ),
            h(
              NFormItem,
              { label: $t('page.function.functionDescription') },
              {
                default: () =>
                  h(NInput, {
                    type: 'textarea',
                    placeholder: $t('page.function.functionDescriptionPlaceholder'),
                    value: localEditData.description,
                    onUpdateValue: value => (localEditData.description = value)
                  })
              }
            ),
            h(
              NFormItem,
              { label: $t('page.function.tags') },
              {
                default: () =>
                  h(NInput, {
                    placeholder: $t('page.function.tagsPlaceholder'),
                    value: localEditData.tags.join(','),
                    onUpdateValue: value => (localEditData.tags = value.split(',').map(tag => tag.trim()))
                  })
              }
            )
          ]
        }
      ),
    positiveText: $t('common.confirm'),
    negativeText: $t('common.cancel'),
    onPositiveClick: () => {
      formRef.value?.validate(async (errors: any) => {
        if (!errors) {
          const { error } = await UpdateFunctionMeta(
            applicationStore.appId,
            selectedFunction.value.id,
            localEditData.name,
            localEditData.description,
            localEditData.tags
          );
          if (!error) {
            message.success($t('page.function.updateSuccess'));
            selectedFunction.value.name = localEditData.name;
            selectedFunction.value.description = localEditData.description;
            selectedFunction.value.tags = localEditData.tags;
            const index = functions.value.findIndex(f => f.id === selectedFunction.value.id);
            if (index !== -1) {
              functions.value[index].name = localEditData.name;
              functions.value[index].description = localEditData.description;
              functions.value[index].tags = localEditData.tags;
            }
            await fetchTags();
          } else {
            message.error($t('page.function.updateFailed'));
          }
        }
      });
    }
  });
};

const handleEditDependence = (dep: Api.Settings.Dependency) => {
  const editPackageName = ref(dep.name);
  const editPackageVersion = ref(dep.version);
  const editVersionOptions = ref<any[]>([]);
  const editVersionLoading = ref(true);

  const fetchVersions = async () => {
    const appId = applicationStore.appId;
    const { data, error } = await packageInfo(appId, editPackageName.value);
    if (!error && data?.versions) {
      editVersionOptions.value = data.versions.map((v: string) => ({ label: v, value: v }));
    } else {
      message.error($t('page.function.getPackageInfoFailed'));
    }
    editVersionLoading.value = false;
  };

  fetchVersions();

  const d = dialog.info({
    title: `${$t('common.action.edit')} - ${dep.name}`,
    content: () =>
      h(
        NForm,
        {
          labelPlacement: 'left',
          labelWidth: 80,
          onKeyup: (e: KeyboardEvent) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              (d.onPositiveClick as any)();
            }
          }
        },
        {
          default: () => [
            h(
              NFormItem,
              { label: $t('page.function.version') },
              {
                default: () =>
                  h(NSelect, {
                    value: editPackageVersion.value,
                    options: editVersionOptions.value,
                    loading: editVersionLoading.value,
                    onUpdateValue: value => {
                      editPackageVersion.value = value;
                    }
                  })
              }
            )
          ]
        }
      ),
    positiveText: $t('common.confirm'),
    negativeText: $t('common.cancel'),
    onPositiveClick: async () => {
      const appId = applicationStore.appId;
      if (appId && editPackageName.value) {
        const { error } = await packageAdd(appId, editPackageName.value, editPackageVersion.value);
        if (!error) {
          message.success($t('common.editSuccess'));
          await handleDependence(false);
        } else {
          message.error($t('common.editFailed'));
        }
      }
    }
  });
};

const handleDeleteDependence = (dep: Api.Settings.Dependency) => {
  dialog.warning({
    title: $t('page.function.confirmDeleteDependence'),
    content: $t('page.function.deleteDependenceConfirm', { name: dep.name }),
    action: () =>
      h(
        NButtonGroup,
        { class: 'flex justify-end gap-2 w-full' },
        {
          default: () => [
            h(
              NButton,
              { type: 'default', size: 'small', onClick: () => dialog.destroyAll() },
              { default: () => $t('common.cancel') }
            ),
            h(
              NButton,
              {
                type: 'error',
                size: 'small',
                onClick: async () => {
                  const { error } = await packageRemove(applicationStore.appId, dep.name, false);
                  if (!error) {
                    message.success($t('page.function.dependenceDeleted'));
                    await handleDependence(false);
                  } else {
                    message.error($t('page.function.deleteFailed'));
                  }
                  dialog.destroyAll();
                }
              },
              { default: () => $t('page.function.deleteOnly') }
            ),
            h(
              NButton,
              {
                type: 'warning',
                size: 'small',
                onClick: async () => {
                  const { error: removeError } = await packageRemove(applicationStore.appId, dep.name, true);
                  if (!removeError) {
                    const { error: restartError } = await restartApp(applicationStore.appId);
                    if (!restartError) {
                      message.success($t('page.function.dependenceDeletedAndRestarting'));
                      applicationStore.setAppStatus('starting');
                      router.push({ name: 'home' });
                    } else {
                      message.error($t('page.function.restartFailed'));
                    }
                  } else {
                    message.error($t('page.function.deleteFailed'));
                  }
                  dialog.destroyAll();
                }
              },
              { default: () => $t('page.function.deleteAndRestart') }
            )
          ]
        }
      )
  });
};

const handlePackageAdd = async (restart: boolean = false) => {
  const { error } = await packageAdd(
    applicationStore.appId,
    packageSelectInput.value.name,
    packageSelectInput.value.version,
    restart
  );
  if (!error) {
    if (restart) {
      const { error: restartError } = await restartApp(applicationStore.appId);
      if (!restartError) {
        message.success($t('page.function.addDependenceSuccessAndRestarting'));
        applicationStore.setAppStatus('starting');
        router.push({ name: 'home' });
      } else {
        message.error($t('page.function.restartFailed'));
      }
      dialog.destroyAll();
      return;
    }
    message.success($t('page.function.addDependenceSuccess'));
    await handleDependence(false);
  } else {
    message.error($t('page.function.addDependenceFailed'));
  }
  packageSelectInput.value = { name: '', version: '' };
  packageResult.value = [];
  addDependenceDialogRef.destroy();
};

let searchTimeout: number | null = null;

const handlePackageSearch = (query: string) => {
  if (!query) {
    packageResult.value = [];
    return;
  }
  if (searchTimeout) {
    clearTimeout(searchTimeout);
  }
  isDependenceLoading.value = true;
  searchTimeout = window.setTimeout(async () => {
    const { data, error } = await dependenceSearch(applicationStore.appId, query, false);
    if (!error) {
      packageResult.value = data || [];
    }
    isDependenceLoading.value = false;
  }, 500);
};

const handleAddDependence = async (row: { name: string }) => {
  packageSelectInput.value.name = row.name;
  isDependenceLoading.value = true;
  const { data, error } = await packageInfo(applicationStore.appId, packageSelectInput.value.name);
  if (error) {
    message.error($t('page.function.getPackageInfoFailed'));
    isDependenceLoading.value = false;
    return;
  }
  packageSelectInput.value.version = data?.versions?.[0] ?? '';
  isDependenceLoading.value = false;
  const formRef = ref<any>(null);
  const rules = {
    name: { required: true, message: $t('page.function.dependenceNamePlaceholder'), trigger: 'blur' }
  };
  addDependenceDialogRef = dialog.info({
    title: $t('page.function.add'),
    content: () =>
      h(
        NForm,
        {
          ref: formRef,
          model: packageSelectInput.value,
          rules,
          onKeyup: (e: KeyboardEvent) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              handlePackageAdd(false);
            }
          }
        },
        {
          default: () => [
            h(
              NFormItem,
              { label: $t('page.function.dependenceName'), path: 'name' },
              {
                default: () =>
                  h(NInput, {
                    value: packageSelectInput.value.name,
                    onUpdateValue: v => (packageSelectInput.value.name = v)
                  })
              }
            ),
            h(
              NFormItem,
              { label: $t('page.function.version') },
              {
                default: () =>
                  h(NSelect, {
                    value: packageSelectInput.value.version,
                    onUpdateValue: v => (packageSelectInput.value.version = v),
                    options: data?.versions?.map((v: string) => ({ label: v, value: v })) ?? []
                  })
              }
            )
          ]
        }
      ),
    action: () =>
      h(
        NButtonGroup,
        { class: 'flex justify-end gap-2 w-full' },
        {
          default: () => [
            h(
              NButton,
              {
                type: 'default',
                size: 'small',
                onClick: () => {
                  addDependenceDialogRef.destroy();
                  packageSelectInput.value = { name: '', version: '' };
                }
              },
              { default: () => $t('common.cancel') }
            ),
            h(
              NButton,
              { type: 'success', size: 'small', onClick: () => handlePackageAdd(false) },
              { default: () => $t('page.function.install') }
            ),
            h(
              NButton,
              { type: 'info', size: 'small', onClick: () => handlePackageAdd(true) },
              { default: () => $t('page.function.installAndRestart') }
            )
          ]
        }
      ),
    onPositiveClick: async () => {
      // placeholder
    }
  });
};

const handleDependence = async (showDialog: boolean = true) => {
  packageSelectInput.value = { name: '', version: '' };
  packageResult.value = [];
  isDependenceLoading.value = true;
  const { data, error } = await dependenciesData(applicationStore.appId);
  isDependenceLoading.value = false;

  if (error) {
    message.error($t('page.function.getDependenceListFailed'));
    return;
  }
  commonDependencies.value = data.common;
  systemDependencies.value = data.system;

  if (!showDialog) return;

  dialog.info({
    title: $t('page.function.dependenceManagement'),
    content: () =>
      h(
        NSpin,
        { show: isDependenceLoading.value },
        {
          default: () =>
            h(
              NTabs,
              { type: 'segment', animated: true, style: 'height:500px;', ref: dependenceTabsRef },
              {
                default: () => [
                  h(
                    NTabPane,
                    { name: $t('page.function.installed'), tab: $t('page.function.installed') },
                    {
                      default: () =>
                        h(
                          NScrollbar,
                          { style: 'max-height: 450px' },
                          {
                            default: () =>
                              commonDependencies.value.length > 0
                                ? h(
                                    NList,
                                    { hoverable: true, clickable: true, bordered: true },
                                    {
                                      default: () =>
                                        commonDependencies.value.map(dep =>
                                          h(
                                            NListItem,
                                            {},
                                            {
                                              default: () =>
                                                h(
                                                  NThing,
                                                  { description: dep.version },
                                                  {
                                                    header: () =>
                                                      h(NSpace, { align: 'center' }, () => [
                                                        h('span', dep.name),
                                                        h(
                                                          'a',
                                                          {
                                                            href: `https://pypi.org/project/${dep.name}`,
                                                            target: '_blank',
                                                            class: 'text-gray-400 hover:text-primary flex items-center'
                                                          },
                                                          h(NIcon, { component: LinkOutline, size: 22 })
                                                        )
                                                      ]),
                                                    'header-extra': () =>
                                                      h(NButtonGroup, {}, () => [
                                                        h(
                                                          NButton,
                                                          {
                                                            quaternary: true,
                                                            circle: true,
                                                            type: 'primary',
                                                            onClick: () => handleEditDependence(dep)
                                                          },
                                                          {
                                                            default: () =>
                                                              h(NIcon, { component: BrushOutline, size: 18 })
                                                          }
                                                        ),
                                                        h(
                                                          NButton,
                                                          {
                                                            quaternary: true,
                                                            circle: true,
                                                            type: 'error',
                                                            onClick: () => handleDeleteDependence(dep)
                                                          },
                                                          {
                                                            default: () =>
                                                              h(NIcon, { component: CloseOutline, size: 22 })
                                                          }
                                                        )
                                                      ])
                                                  }
                                                )
                                            }
                                          )
                                        )
                                    }
                                  )
                                : h(NEmpty, {
                                    description: $t('page.function.noDependence'),
                                    class: 'h-full flex items-center justify-center'
                                  })
                          }
                        )
                    }
                  ),
                  h(
                    NTabPane,
                    { name: $t('page.function.systemDependence'), tab: $t('page.function.systemDependence') },
                    {
                      default: () =>
                        h(
                          NScrollbar,
                          { style: 'max-height: 450px' },
                          {
                            default: () =>
                              systemDependencies.value.length > 0
                                ? h(
                                    NList,
                                    { hoverable: true, bordered: true },
                                    {
                                      default: () =>
                                        systemDependencies.value.map(dep =>
                                          h(
                                            NListItem,
                                            {},
                                            {
                                              default: () => h(NThing, { title: dep.name, description: dep.version })
                                            }
                                          )
                                        )
                                    }
                                  )
                                : h(NEmpty, {
                                    description: $t('page.function.noSystemDependence'),
                                    class: 'h-full flex items-center justify-center'
                                  })
                          }
                        )
                    }
                  ),
                  h(
                    NTabPane,
                    { name: $t('page.function.add'), tab: $t('page.function.add') },
                    {
                      default: () => [
                        h(
                          NInput,
                          {
                            value: packageSelectInput.value.name,
                            placeholder: $t('page.function.dependenceNamePlaceholder'),
                            loading: isDependenceLoading.value,
                            clearable: true,
                            onUpdateValue: value => {
                              packageSelectInput.value.name = value;
                              handlePackageSearch(value);
                            }
                          },
                          {
                            suffix: () => h(NIcon, { component: SearchOutline })
                          }
                        ),
                        h(NDataTable, {
                          columns: [
                            { title: $t('page.function.dependenceName'), key: 'name' },
                            { title: $t('page.function.tags'), key: 'author' },
                            {
                              title: $t('page.function.functionDescription'),
                              key: 'description',
                              ellipsis: { tooltip: true }
                            },
                            {
                              title: $t('common.action._self'),
                              key: 'operation',
                              width: 100,
                              render: (row: Api.Settings.PackageInfo) => {
                                return h(
                                  NButton,
                                  { type: 'primary', size: 'small', onClick: () => handleAddDependence(row) },
                                  { default: () => h(NIcon, { component: AddOutline }) }
                                );
                              }
                            }
                          ],
                          data: packageResult.value,
                          class: 'mt-2',
                          maxHeight: '400px'
                        })
                      ]
                    }
                  )
                ]
              }
            )
        }
      )
  });
};

const handleEnvSetting = async (showDialog: boolean = true) => {
  const { data, error } = await getEnvsData(applicationStore.appId);
  if (error) {
    message.error($t('page.function.getEnvFailed'));
    return;
  }
  userEnv.value = data.user;
  systemEnv.value = data.system;

  if (!showDialog) return;

  dialog.info({
    title: $t('page.function.envManagement'),
    content: () =>
      h(
        NTabs,
        { type: 'segment', animated: true, style: 'height:500px;' },
        {
          default: () => [
            h(
              NTabPane,
              { name: $t('page.function.custom'), tab: $t('page.function.custom') },
              {
                default: () =>
                  h(
                    NScrollbar,
                    { style: 'max-height: 450px' },
                    {
                      default: () =>
                        userEnv.value.length > 0
                          ? h(
                              NList,
                              { hoverable: true, clickable: true, bordered: true },
                              {
                                default: () =>
                                  userEnv.value.map(dep =>
                                    h(
                                      NListItem,
                                      {},
                                      {
                                        default: () =>
                                          h(
                                            NThing,
                                            { title: dep.key, description: dep.value },
                                            {
                                              'header-extra': () =>
                                                h(
                                                  NButtonGroup,
                                                  {},
                                                  {
                                                    default: () => [
                                                      h(
                                                        NButton,
                                                        {
                                                          quaternary: true,
                                                          circle: true,
                                                          type: 'primary',
                                                          onClick: () => handleEditEnv(dep)
                                                        },
                                                        {
                                                          default: () => h(NIcon, { component: BrushOutline, size: 22 })
                                                        }
                                                      ),
                                                      h(
                                                        NButton,
                                                        {
                                                          quaternary: true,
                                                          circle: true,
                                                          type: 'error',
                                                          onClick: () => handleDeleteEnv(dep)
                                                        },
                                                        {
                                                          default: () => h(NIcon, { component: CloseOutline, size: 22 })
                                                        }
                                                      )
                                                    ]
                                                  }
                                                )
                                            }
                                          )
                                      }
                                    )
                                  )
                              }
                            )
                          : h(NEmpty, {
                              description: $t('page.function.noCustomEnv'),
                              class: 'h-full flex items-center justify-center'
                            })
                    }
                  )
              }
            ),
            h(
              NTabPane,
              { name: $t('page.function.systemBuiltin'), tab: $t('page.function.systemBuiltin') },
              {
                default: () =>
                  h(
                    NScrollbar,
                    { style: 'max-height: 450px' },
                    {
                      default: () =>
                        systemEnv.value.length > 0
                          ? h(
                              NList,
                              { hoverable: true, bordered: true },
                              {
                                default: () =>
                                  systemEnv.value.map(dep =>
                                    h(
                                      NListItem,
                                      {},
                                      {
                                        default: () => h(NThing, { title: dep.key, description: dep.value })
                                      }
                                    )
                                  )
                              }
                            )
                          : h(NEmpty, {
                              description: $t('page.function.noSystemBuiltinEnv'),
                              class: 'h-full flex items-center justify-center'
                            })
                    }
                  )
              }
            )
          ]
        }
      ),
    action: () =>
      h(NButton, { type: 'primary', onClick: () => handleAddEnv() }, { default: () => $t('page.function.addEnv') })
  });
};

const handleAddEnv = () => {
  const formRef = ref<any>(null);
  const newEnv = reactive({ key: '', value: '' });
  const rules = {
    key: { required: true, message: $t('page.function.keyPlaceholder'), trigger: 'blur' },
    value: { required: true, message: $t('page.function.valuePlaceholder'), trigger: 'blur' }
  };
  const d = dialog.info({
    title: $t('page.function.addEnv'),
    content: () =>
      h(
        NForm,
        {
          ref: formRef,
          model: newEnv,
          rules,
          onKeyup: (e: KeyboardEvent) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              (d.onPositiveClick as any)();
            }
          }
        },
        {
          default: () => [
            h(
              NFormItem,
              { label: $t('page.function.key'), path: 'key' },
              {
                default: () => h(NInput, { value: newEnv.key, onUpdateValue: v => (newEnv.key = v) })
              }
            ),
            h(
              NFormItem,
              { label: $t('page.function.value'), path: 'value' },
              {
                default: () => h(NInput, { value: newEnv.value, onUpdateValue: v => (newEnv.value = v) })
              }
            )
          ]
        }
      ),
    positiveText: $t('common.confirm'),
    negativeText: $t('common.cancel'),
    onNegativeClick: () => {
      newEnv.key = '';
      newEnv.value = '';
    },
    onPositiveClick: () => {
      formRef.value?.validate(async (errors: any) => {
        if (!errors) {
          const { error } = await addEnv(applicationStore.appId, newEnv.key, newEnv.value);
          if (!error) {
            message.success($t('page.function.addSuccess'));
            await handleEnvSetting(false);
            newEnv.key = '';
            newEnv.value = '';
          } else {
            message.error($t('page.function.addFailed'));
          }
        }
      });
    }
  });
};

const handleEditEnv = (env: Api.Settings.EnvInfo) => {
  const formRef = ref<any>(null);
  const editEnv = reactive({ ...env });
  const rules = {
    value: { required: true, message: $t('page.function.valuePlaceholder'), trigger: 'blur' }
  };
  const d = dialog.info({
    title: $t('page.function.editEnv'),
    content: () =>
      h(
        NForm,
        {
          ref: formRef,
          model: editEnv,
          rules,
          onKeyup: (e: KeyboardEvent) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              (d.onPositiveClick as any)();
            }
          }
        },
        {
          default: () => [
            h(
              NFormItem,
              { label: $t('page.function.key') },
              {
                default: () => h(NInput, { value: editEnv.key, disabled: true })
              }
            ),
            h(
              NFormItem,
              { label: $t('page.function.value'), path: 'value' },
              {
                default: () => h(NInput, { value: editEnv.value, onUpdateValue: v => (editEnv.value = v) })
              }
            )
          ]
        }
      ),
    positiveText: $t('common.confirm'),
    negativeText: $t('common.cancel'),
    onPositiveClick: () => {
      formRef.value?.validate(async (errors: any) => {
        if (!errors) {
          const { error } = await addEnv(applicationStore.appId, editEnv.key, editEnv.value);
          if (!error) {
            message.success($t('page.function.updateSuccess'));
            await handleEnvSetting(false);
          } else {
            message.error($t('page.function.updateFailed'));
          }
        }
      });
    }
  });
};

const handleDeleteEnv = (env: Api.Settings.EnvInfo) => {
  dialog.warning({
    title: $t('page.function.confirmDeleteEnv'),
    content: $t('page.function.deleteEnvConfirm', { key: env.key }),
    positiveText: $t('common.delete'),
    negativeText: $t('common.cancel'),
    onPositiveClick: async () => {
      const { error } = await removeEnv(applicationStore.appId, env.key);
      if (!error) {
        message.success($t('page.function.deleteSuccess'));
        await handleEnvSetting(false);
      } else {
        message.error($t('page.function.deleteFailed'));
      }
    }
  });
};

// Lifecycle
onMounted(async () => {
  const { data: domain, error } = await getDomain();
  if (!error) {
    localStorage.setItem('hyac_domain', domain);
  }
  await fetchTags();
  await getFunctionData();
});

onBeforeUnmount(() => {
  clearLogAnimTimer();
});
</script>

<template>
  <div class="function-page">
    <NSplit
      v-model:size="pageSplitSize"
      class="page-split"
      :min="0.12"
      :max="0.34"
      @drag-move="handleSplitDragMove"
      @drag-end="handleSplitDragEnd"
    >
      <template #1>
        <aside class="sidebar-container" :class="{ collapsed: sidebarCollapsed }">
          <FunctionList
            :functions="functions"
            :selected-function-id="selectedFunction.id"
            :tags="tags"
            :selected-tag="selectedTag"
            @create-function="handleCreateFunction"
            @select-function="functionSelect"
            @delete-function="handleDeleteFunction"
            @open-env-settings="handleEnvSetting(true)"
            @open-dependency-manager="handleDependence(true)"
            @select-tag="handleTagSelect"
          />
        </aside>
      </template>

      <template #2>
        <main class="main-container">
          <template v-if="functions.length > 0">
            <NSplit
              v-model:size="workspaceSplitSize"
              class="workspace-split"
              :min="0.42"
              :max="0.86"
              @drag-move="handleSplitDragMove"
              @drag-end="handleSplitDragEnd"
            >
              <template #1>
                <section class="primary-column">
                  <NSplit
                    v-model:size="editorLogSplitSize"
                    class="editor-log-split"
                    :class="{ 'log-collapsed': logCollapsed }"
                    direction="vertical"
                    :min="0.35"
                    :max="0.86"
                    @drag-move="handleSplitDragMove"
                    @drag-end="handleSplitDragEnd"
                  >
                    <template #1>
                      <div class="editor-section">
                        <FunctionEditorPanel
                          ref="editorPanelRef"
                          :func="selectedFunction"
                          :code-changed="codeChanged"
                          :is-saving="isSaving"
                          :editor-config="editorConfig"
                          @save-code="handleSaveCode"
                          @open-history="handleOpenHistory"
                          @update:code="selectedFunction.code = $event"
                          @open-editor-settings="handleFunctionEditorSetting"
                          @edit-meta="handleEditMeta"
                        />
                      </div>
                    </template>
                    <template #2>
                      <div
                        class="log-container"
                        :class="{
                          compact: logCollapsed,
                          'log-anim-collapsing': logAnimState === 'collapsing',
                          'log-anim-expanding': logAnimState === 'expanding'
                        }"
                      >
                        <FunctionLogPanel
                          :app-id="applicationStore.appId"
                          :func-id="selectedFunction.id"
                          :compact="logCollapsed"
                          @collapse="handleCollapseLog"
                          @expand="handleExpandLog"
                        />
                      </div>
                    </template>
                  </NSplit>
                </section>
              </template>

              <template #2>
                <aside class="panel-container">
                  <div class="panel-tabs">
                    <button class="panel-tab" :class="{ active: activePanel === 'test' }" @click="activePanel = 'test'">
                      <NIcon :component="BeakerOutline" :size="15" />
                      <span>{{ $t('page.function.functionTest') }}</span>
                    </button>
                    <button class="panel-tab" :class="{ active: activePanel === 'cron' }" @click="activePanel = 'cron'">
                      <NIcon :component="TimerOutline" :size="15" />
                      <span>{{ $t('page.function.cronJobs') }}</span>
                    </button>
                  </div>
                  <div class="panel-content">
                    <FunctionTestPanel
                      v-if="activePanel === 'test' && selectedFunction.type === 'endpoint'"
                      :key="selectedFunction.id"
                      :function-address="functionAddress"
                    />
                    <FunctionCronPanel
                      v-else-if="activePanel === 'cron' && selectedFunction.type === 'endpoint'"
                      :func="selectedFunction"
                    />
                    <div v-else class="empty-panel">
                      <NEmpty :description="$t('page.function.commonFunctionTestHint')" />
                    </div>
                  </div>
                </aside>
              </template>
            </NSplit>
          </template>

          <div v-else class="empty-state">
            <div class="empty-content">
              <div class="empty-icon-large">ƒ</div>
              <h2>{{ $t('page.function.emptyDescription') }}</h2>
              <button class="create-btn" @click="handleCreateFunction">
                <NIcon :component="AddOutline" :size="18" />
                <span>{{ $t('page.function.createFunction') }}</span>
              </button>
            </div>
          </div>
        </main>
      </template>
    </NSplit>

    <FunctionHistoryModal v-model:show="showHistoryModel" :history-data="historyData" @rollback="handleRollback" />
    <AiAssistantWindow :show="showAiWindow" @close="handleCloseAiWindow" />

    <button class="ai-fab" @click="toggleAiWindow">
      <NIcon :component="SparklesOutline" :size="22" />
    </button>
  </div>
</template>

<style scoped>
.function-page {
  --function-panel-gap: 6px;

  flex: 1;
  height: 100%;
  min-height: 0;
  width: 100%;
  background: #f5f5f7;
  overflow: hidden;
  padding: 8px;
}

.page-split,
.workspace-split,
.editor-log-split {
  height: 100%;
  min-height: 0;
}

.page-split :deep(.n-split-pane),
.workspace-split :deep(.n-split-pane),
.editor-log-split :deep(.n-split-pane) {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.sidebar-container {
  height: 100%;
  flex-shrink: 0;
  padding-right: var(--function-panel-gap);
  transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.sidebar-container.collapsed {
  width: 0;
}

.main-container {
  height: 100%;
  min-width: 0;
  min-height: 0;
  padding-left: var(--function-panel-gap);
}

.primary-column {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-width: 0;
  min-height: 0;
  padding-right: var(--function-panel-gap);
}

.editor-section {
  height: 100%;
  min-height: 0;
}

.log-container {
  height: 100%;
  min-width: 0;
  min-height: 0;
}

.editor-log-split.log-collapsed :deep(.n-split-pane-1) {
  flex-basis: calc(100% - 48px) !important;
  max-height: calc(100% - 48px) !important;
}

.editor-log-split.log-collapsed :deep(.n-split-pane-2) {
  flex-basis: 48px !important;
  max-height: 48px !important;
}

.log-container.compact {
  height: 48px;
  max-height: 48px;
}

.log-container.log-anim-collapsing {
  animation: log-collapse 300ms cubic-bezier(0.6, 0, 0.4, 1) forwards;
}

.log-container.log-anim-expanding {
  animation: log-expand 350ms cubic-bezier(0.175, 0.885, 0.32, 1.1) forwards;
}

@keyframes log-collapse {
  0% {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
  100% {
    opacity: 0;
    transform: translateY(6px) scale(0.98);
  }
}

@keyframes log-expand {
  0% {
    opacity: 0;
    transform: translateY(8px) scale(0.98);
  }
  60% {
    opacity: 1;
  }
  100% {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@media (prefers-reduced-motion: reduce) {
  .log-container.log-anim-collapsing,
  .log-container.log-anim-expanding {
    animation: none;
  }
}

.panel-container {
  height: 100%;
  min-width: 0;
  margin-left: var(--function-panel-gap);
  display: flex;
  flex-direction: column;
  background: #ffffff;
  border-radius: 12px;
  overflow: hidden;
}

.panel-tabs {
  display: flex;
  gap: 2px;
  padding: 6px 8px;
  background: rgba(0, 0, 0, 0.02);
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

.panel-tab {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 500;
  border-radius: 6px;
  background: transparent;
  color: #6e6e73;
  border: none;
  cursor: pointer;
  transition: all 0.2s ease;
}

.panel-tab:hover {
  color: #1d1d1f;
}

.panel-tab.active {
  background: #ffffff;
  color: #007aff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.panel-content {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.empty-panel {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.empty-content {
  text-align: center;
}

.empty-icon-large {
  font-size: 64px;
  font-weight: 700;
  color: #c7c7cc;
  margin-bottom: 16px;
}

.empty-content h2 {
  font-size: 18px;
  font-weight: 600;
  color: #1d1d1f;
  margin: 0 0 24px;
}

.create-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 12px 24px;
  font-size: 15px;
  font-weight: 600;
  border-radius: 12px;
  background: #007aff;
  color: white;
  border: none;
  cursor: pointer;
  transition: all 0.2s ease;
}

.create-btn:hover {
  background: #0066d6;
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(0, 122, 255, 0.3);
}

.ai-fab {
  position: fixed;
  right: 20px;
  bottom: 20px;
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: linear-gradient(135deg, #007aff, #5856d6);
  color: white;
  border: none;
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(0, 122, 255, 0.3);
  transition: all 0.3s ease;
  z-index: 1000;
}

.ai-fab:hover {
  transform: scale(1.1);
  box-shadow: 0 6px 24px rgba(0, 122, 255, 0.4);
}

@media (max-width: 1100px) {
  .panel-container {
    margin-left: 4px;
  }
}
</style>
