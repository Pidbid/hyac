<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch, h, reactive, nextTick } from 'vue';
import { useDialog, useMessage, NForm, NInput, NRadioGroup, NRadio, NSelect, NSplit, NFormItem, type SelectOption, NInputNumber, NButtonGroup, NButton, NTabs, NTabPane, NScrollbar, NList, NListItem, NThing, NEmpty, NDataTable, NSpin, NIcon, NSwitch, NSpace } from 'naive-ui';
import { AddOutline, CloseOutline, SearchOutline, BrushOutline, SparklesOutline, LinkOutline } from '@vicons/ionicons5';
import dayjs from 'dayjs';
import { $t } from '@/locales';
import { useApplicationStore } from '@/store/modules/application';
import { useFunctionStore } from '@/store/modules/function';
import { useLogStore } from '@/store/modules/log';
import { useThemeStore } from '@/store/modules/theme';
import { useAppStore } from '@/store/modules/app';
import {
  CreateFunction,
  GetFunctionData,
  UpdateFunctionCode,
  UpdateFunctionMeta,
  DeleteFunction,
  FunctionHistory,
  getFunctionTemplates,
  dependenciesData,
  dependenceSearch,
  packageAdd,
  packageInfo,
  packageRemove,
  getEnvsData,
  addEnv,
  removeEnv,
  getDomain,
  getFunctionTags
} from '@/service/api';

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
const logStore = useLogStore();
const themeStore = useThemeStore();

const isDependenceLoading = ref(false)
const dependenceTabsRef = ref<undefined | HTMLElement>(undefined)
const packageSelectInput = ref({
  name: "",
  version: ""
})
const packageResult = ref<Api.Settings.PackageInfo[]>([])
let addDependenceDialogRef: any = null;
const commonDependencies = ref<Api.Settings.Dependency[]>([]);
const systemDependencies = ref<Api.Settings.Dependency[]>([]);
const userEnv = ref<Api.Settings.EnvInfo[]>([]);
const systemEnv = ref<Api.Settings.EnvInfo[]>([]);
const storedEditorConfig = localStorage.getItem('editorConfig');
const editorConfig = ref(storedEditorConfig ? JSON.parse(storedEditorConfig) : {
  language: 'python',
  fontSize: 14,
  minimap: true,
  themeName: 'github',
  lineNumbers: true,
});

watch(() => editorConfig.value, (newValue) => {
  localStorage.setItem('editorConfig', JSON.stringify(newValue));
}, { deep: true });

// State
const functions = ref<Api.Function.FunctionInfo[]>([]);
const selectedFunction = ref<Api.Function.FunctionInfo>({ id: '', name: '', type: 'endpoint', status: 'unpublished', description: '', tags: [], code: '' });
const originalCode = ref('');
const codeChanged = ref(false);
const isSaving = ref(false);
const functionRequestData = ref({ page: 1, length: 50 });
const tags = ref<string[]>([]);
const selectedTag = ref('all');

const showHistoryModel = ref(false);
const historyData = ref<Api.Function.FunctionHistoryInfo[]>([]);
const showAiWindow = ref(false);

// Computed
const functionAddress = computed(() => {
  const domain = localStorage.getItem('hyac_domain');
  if (selectedFunction.value.id !== '' && domain) {
    return `https://${applicationStore.appId}.${domain}/${selectedFunction.value.id}`;
  }
  return '';
});

// Watchers
watch(() => selectedFunction.value.code, (newCode) => {
  codeChanged.value = newCode !== originalCode.value;
});

watch(() => selectedFunction.value.id, (newId, oldId) => {
  if (newId && newId !== oldId) {
    originalCode.value = selectedFunction.value.code;
    codeChanged.value = false;
    logStore.subscribe(newId);
  }
});

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
    functions.value = data.data.map((func: Api.Function.FunctionRecord) => ({
      id: func.function_id,
      name: func.function_name,
      type: func.function_type,
      status: func.status,
      description: func.description,
      tags: func.tags,
      code: func.code,
    }));
    if (functions.value.length > 0) {
      const funcToSelect = functionStore.funcInfo && functions.value.some(f => f.id === functionStore.funcInfo?.id)
        ? functionStore.funcInfo
        : functions.value[0];
      functionSelect(funcToSelect);
    } else {
      selectedFunction.value = { id: '', name: '', type: 'endpoint', status: 'unpublished', description: '', tags: [], code: '' };
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
  selectedFunction.value = func;
  originalCode.value = func.code;
  codeChanged.value = false;
  functionStore.setFuncInfo(func);
};

const handleCreateFunction = () => {
  const formRef = ref<any>(null);
  const localCreateData = reactive({
    name: '',
    description: '',
    type: "endpoint",
    template_id: "",
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
    content: () => h(NForm, { ref: formRef, model: localCreateData, rules: rules, labelPlacement: 'left', labelWidth: 80, onKeyup: (e: KeyboardEvent) => { if (e.key === 'Enter') { e.preventDefault(); (d.onPositiveClick as any)(); } } }, {
      default: () => [
        h(NFormItem, { label: $t('page.function.functionName'), path: 'name' }, {
          default: () => h(NInput, {
            placeholder: $t('page.function.functionNamePlaceholder'),
            value: localCreateData.name,
            onUpdateValue: (value) => localCreateData.name = value
          })
        }),
        h(NFormItem, { label: $t('page.function.functionType') }, {
          default: () => h(NRadioGroup, {
            value: localCreateData.type,
            onUpdateValue: (value) => {
              localCreateData.type = value;
              localCreateData.template_id = '';
              fetchLocalTemplates(value);
            }
          }, {
            default: () => [
              h(NRadio, { label: $t('page.function.apiFunction'), value: 'endpoint' }),
              h(NRadio, { label: $t('page.function.commonFunction'), value: 'common' })
            ]
          })
        }),
        h(NFormItem, { label: $t('page.function.functionTemplate'), path: 'template_id' }, {
          default: () => h(NSelect, {
            placeholder: $t('page.function.functionTemplatePlaceholder'),
            options: localCreateData.templateOptions,
            value: localCreateData.template_id,
            onUpdateValue: (value) => localCreateData.template_id = value
          })
        }),
        h(NFormItem, { label: $t('page.function.functionDescription') }, {
          default: () => h(NInput, {
            type: 'textarea',
            placeholder: $t('page.function.functionDescriptionPlaceholder'),
            value: localCreateData.description,
            onUpdateValue: (value) => localCreateData.description = value
          })
        }),
        h(NFormItem, { label: $t('page.function.tags') }, {
          default: () => h(NInput, {
            placeholder: $t('page.function.tagsPlaceholder'),
            value: localCreateData.tags.join(','),
            onUpdateValue: (value) => localCreateData.tags = value.split(',').map(tag => tag.trim())
          })
        }),
      ]
    }),
    positiveText: $t('common.confirm'),
    negativeText: $t('common.cancel'),
    onNegativeClick: () => {
      // Reset form data on cancellation
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
            // Reset form data after successful creation
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
            selectedFunction.value = { id: '', name: '', type: 'endpoint', status: 'published', description: '', tags: [], code: '' };
            originalCode.value = '';
            codeChanged.value = false;
          }
        }
        logStore.unsubscribe();
      }
    }
  });
};

const handleSaveCode = async () => {
  if (!codeChanged.value || isSaving.value) return;
  isSaving.value = true;
  try {
    const { error } = await UpdateFunctionCode(applicationStore.appId, selectedFunction.value.id, selectedFunction.value.code);
    if (!error) {
      const currentEditFunctionId = selectedFunction.value.id;
      message.success($t('page.function.saveSuccess'));
      originalCode.value = selectedFunction.value.code;
      codeChanged.value = false;
      await getFunctionData();
      const updatedFunc = functions.value.find(f => f.id === currentEditFunctionId);
      if (updatedFunc) {
        selectedFunction.value = updatedFunc;
      }
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
    themeName: editorConfig.value.themeName,
  });

  const themeOptions = [
    { label: 'GitHub', value: 'github' },
    { label: 'Basic', value: 'basic' },
    { label: 'Gruvbox', value: 'gruvbox' },
    { label: 'Material', value: 'material' },
    { label: 'Solarized', value: 'solarized' },
    { label: 'Tokyo Night', value: 'tokyoNight' },
    { label: 'VSCode', value: 'vscode' },
  ];

  const d = dialog.info({
    title: $t('page.function.editorSettings'),
    content: () => h(NForm, { labelPlacement: 'left', labelWidth: 80, onKeyup: (e: KeyboardEvent) => { if (e.key === 'Enter') { e.preventDefault(); (d.onPositiveClick as any)(); } } }, {
      default: () => [
        h(NFormItem, { label: $t('page.function.fontSize') }, {
          default: () => h(NInputNumber, {
            placeholder: '16',
            value: tempConfig.fontSize,
            onUpdateValue: (value) => { if (value) tempConfig.fontSize = value; }
          })
        }),
        h(NFormItem, { label: $t('page.function.codePreview') }, {
          default: () => h(NSwitch, {
            value: tempConfig.minimap,
            onUpdateValue: (value) => { tempConfig.minimap = value; }
          })
        }),
        h(NFormItem, { label: $t('page.function.lineNumbers') }, {
          default: () => h(NSwitch, {
            value: tempConfig.lineNumbers,
            onUpdateValue: (value) => { tempConfig.lineNumbers = value; }
          })
        }),
        h(NFormItem, { label: $t('page.function.theme') }, {
          default: () => h(NRadioGroup, {
            value: tempConfig.themeName,
            onUpdateValue: (value) => { tempConfig.themeName = value; }
          }, {
            default: () => themeOptions.map(opt => h(NRadio, { label: opt.label, value: opt.value }))
          })
        }),
      ]
    }),
    positiveText: $t('common.confirm'),
    negativeText: $t('common.cancel'),
    onPositiveClick: () => {
      editorConfig.value.fontSize = tempConfig.fontSize;
      editorConfig.value.minimap = tempConfig.minimap;
      editorConfig.value.lineNumbers = tempConfig.lineNumbers;
      editorConfig.value.themeName = tempConfig.themeName;
      message.success($t('page.function.settingsSuccess'));
    },
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
    content: () => h(NForm, { ref: formRef, model: localEditData, rules: rules, labelPlacement: 'left', labelWidth: 80, onKeyup: (e: KeyboardEvent) => { if (e.key === 'Enter') { e.preventDefault(); (d.onPositiveClick as any)(); } } }, {
      default: () => [
        h(NFormItem, { label: $t('page.function.functionName'), path: 'name' }, {
          default: () => h(NInput, {
            placeholder: $t('page.function.functionNamePlaceholder'),
            value: localEditData.name,
            onUpdateValue: (value) => localEditData.name = value
          })
        }),
        h(NFormItem, { label: $t('page.function.functionDescription') }, {
          default: () => h(NInput, {
            type: 'textarea',
            placeholder: $t('page.function.functionDescriptionPlaceholder'),
            value: localEditData.description,
            onUpdateValue: (value) => localEditData.description = value
          })
        }),
        h(NFormItem, { label: $t('page.function.tags') }, {
          default: () => h(NInput, {
            placeholder: $t('page.function.tagsPlaceholder'),
            value: localEditData.tags.join(','),
            onUpdateValue: (value) => localEditData.tags = value.split(',').map(tag => tag.trim())
          })
        }),
      ]
    }),
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
      h(NForm, { labelPlacement: 'left', labelWidth: 80, onKeyup: (e: KeyboardEvent) => { if (e.key === 'Enter') { e.preventDefault(); (d.onPositiveClick as any)(); } } }, {
        default: () => [
          h(NFormItem, { label: $t('page.function.version') }, {
            default: () => h(NSelect, {
              value: editPackageVersion.value,
              options: editVersionOptions.value,
              loading: editVersionLoading.value,
              onUpdateValue: value => {
                editPackageVersion.value = value;
              }
            })
          })
        ]
      }),
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
}

const handleDeleteDependence = (dep: Api.Settings.Dependency) => {
  dialog.warning({
    title: $t('page.function.confirmDeleteDependence'),
    content: $t('page.function.deleteDependenceConfirm', { name: dep.name }),
    action: () => h(NButtonGroup, { class: "flex justify-end gap-2 w-full" }, {
      default: () => [
        h(NButton, { type: "default", size: "small", onClick: () => dialog.destroyAll() }, { default: () => $t('common.cancel') }),
        h(NButton, {
          type: "error", size: "small", onClick: async () => {
            const { error } = await packageRemove(applicationStore.appId, dep.name, false);
            if (!error) {
              message.success($t('page.function.dependenceDeleted'));
              await handleDependence(false); // Refresh list without closing dialog
            } else {
              message.error($t('page.function.deleteFailed'));
            }
            dialog.destroyAll();
          }
        }, { default: () => $t('page.function.deleteOnly') }),
        h(NButton, {
          type: "warning", size: "small", onClick: async () => {
            const { error } = await packageRemove(applicationStore.appId, dep.name, true);
            if (!error) {
              message.success($t('page.function.dependenceDeletedAndRestarting'));
              await handleDependence(false); // Refresh list without closing dialog
            } else {
              message.error($t('page.function.deleteFailed'));
            }
            dialog.destroyAll();
          }
        }, { default: () => $t('page.function.deleteAndRestart') })
      ]
    })
  });
};


const handlePackageAdd = async (restart: boolean = false) => {
  const { data, error } = await packageAdd(applicationStore.appId, packageSelectInput.value.name, packageSelectInput.value.version, restart);
  if (!error) {
    message.success(restart ? $t('page.function.addDependenceSuccessAndRestarting') : $t('page.function.addDependenceSuccess'));
    await handleDependence(false); // Refresh list without closing dialog
  }else{
    message.error($t('page.function.addDependenceFailed'));
  }
  packageSelectInput.value = {name:'',version: ''}
  packageResult.value = []
  addDependenceDialogRef.destroy();
}

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
  }, 500); // 500ms debounce
};

const handleAddDependence = async (row: { name: string }) => {
  packageSelectInput.value.name = row.name
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
    content: () => h(NForm, { ref: formRef, model: packageSelectInput.value, rules: rules, onKeyup: (e: KeyboardEvent) => { if (e.key === 'Enter') { e.preventDefault(); handlePackageAdd(false); } } }, {
      default: () => [
        h(NFormItem, { label: $t('page.function.dependenceName'), path: "name" }, {
          default:
            () => h(NInput, { value: packageSelectInput.value.name, onUpdateValue: (v) => packageSelectInput.value.name = v })
        }),
        h(NFormItem, { label: $t('page.function.version') }, {
          default:
            () => h(NSelect, { value: packageSelectInput.value.version, onUpdateValue: (v) => packageSelectInput.value.version = v, options: data?.versions?.map((v: string) => ({ label: v, value: v })) ?? [] })
        }),
      ]
    }),
    action: () => h(NButtonGroup, { class: "flex justify-end gap-2 w-full" }, {
      default: () => [
        h(NButton, { type: "default", size: "small", onClick: () => {
          addDependenceDialogRef.destroy();
          packageSelectInput.value = { name: '', version: '' };
         } }, { default: () => $t('common.cancel') }),
        h(NButton, { type: "success", size: "small", onClick: () => handlePackageAdd(false) }, { default: () => $t('page.function.install') }),
        h(NButton, { type: "info", size: "small", onClick: () => handlePackageAdd(true) }, { default: () => $t('page.function.installAndRestart') })
      ]
    }),
    onPositiveClick: async () => {
      // const { error } = await AddDependence(applicationStore.appId, packageSelectInput.value.name.value);
      // if (!error) {
      //   message.success('添加依赖成功');
      //   await handleDependence();
      // }
    }
  })
}

const handleDependence = async (showDialog: boolean = true) => {
  packageSelectInput.value = { name: "", version: "" };
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
    content: () => h(NSpin, { show: isDependenceLoading.value }, {
      default: () => h(NTabs, { type: 'segment', animated: true, style: 'height:500px;', ref: dependenceTabsRef }, {
        default: () => [
          h(NTabPane, { name: $t('page.function.installed'), tab: $t('page.function.installed') }, {
            default: () => h(NScrollbar, { style: 'max-height: 450px' }, {
              default: () => commonDependencies.value.length > 0 ? h(NList, { hoverable: true, clickable: true, bordered: true }, {
                default: () => commonDependencies.value.map((dep) => h(NListItem, {}, {
                  default: () => h(NThing, { description: dep.version }, {
                    header: () => h(NSpace, { align: 'center' }, () => [
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
                    "header-extra": () => h(NButtonGroup, {}, () => [
                      h(NButton, { quaternary: true, circle: true, type: 'primary', onClick: () => handleEditDependence(dep) }, {
                        default: () => h(NIcon, { component: BrushOutline, size: 18 })
                      }),
                      h(NButton, { quaternary: true, circle: true, type: 'error', onClick: () => handleDeleteDependence(dep) }, {
                        default: () => h(NIcon, { component: CloseOutline, size: 22 })
                      })
                    ])
                  })
                }))
              }) : h(NEmpty, { description: $t('page.function.noDependence'), class: "h-full flex items-center justify-center" })
            })
          }),
          h(NTabPane, { name: $t('page.function.systemDependence'), tab: $t('page.function.systemDependence') }, {
            default: () => h(NScrollbar, { style: 'max-height: 450px' }, {
              default: () => systemDependencies.value.length > 0 ? h(NList, { hoverable: true, bordered: true }, {
                default: () => systemDependencies.value.map((dep) => h(NListItem, {}, {
                  default: () => h(NThing, { title: dep.name, description: dep.version })
                }))
              }) : h(NEmpty, { description: $t('page.function.noSystemDependence'), class: "h-full flex items-center justify-center" })
            })
          }),
          h(NTabPane, { name: $t('page.function.add'), tab: $t('page.function.add') }, {
            default: () => [
              h(NInput, {
                value: packageSelectInput.value.name,
                placeholder: $t('page.function.dependenceNamePlaceholder'),
                loading: isDependenceLoading.value,
                clearable: true,
                onUpdateValue: (value) => {
                  packageSelectInput.value.name = value;
                  handlePackageSearch(value);
                }
              }, {
                suffix: () => h(NIcon, { component: SearchOutline })
              }),
              h(NDataTable, {
                columns: [
                  { title: $t('page.function.dependenceName'), key: "name" },
                  { title: $t('page.function.tags'), key: "author" },
                  { title: $t('page.function.functionDescription'), key: "description", ellipsis: { tooltip: true } },
                  {
                    title: $t('common.action._self'),
                    key: 'operation',
                    width: 100,
                    render: (row: Api.Settings.PackageInfo) => {
                      return h(NButton, { type: "primary", size: "small", onClick: () => handleAddDependence(row) }, { default: () => h(NIcon, { component: AddOutline }) })
                    }
                  }
                ],
                data: packageResult.value,
                class: 'mt-2',
                maxHeight: '400px'
              })
            ]
          })
        ]
      })
    })
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
    content: () => h(NTabs, { type: 'segment', animated: true, style: 'height:500px;' }, {
      default: () => [
        h(NTabPane, { name: $t('page.function.custom'), tab: $t('page.function.custom') }, {
          default: () => h(NScrollbar, { style: 'max-height: 450px' }, {
            default: () => userEnv.value.length > 0 ? h(NList, { hoverable: true, clickable: true, bordered: true }, {
              default: () => userEnv.value.map((dep) => h(NListItem, {}, {
                default: () => h(NThing, { title: dep.key, description: dep.value }, {
                  "header-extra": () => h(NButtonGroup, {}, {
                    default: () => [
                      h(NButton, { quaternary: true, circle: true, type: 'primary', onClick: () => handleEditEnv(dep) }, {
                        default: () => h(NIcon, { component: BrushOutline, size: 22 })
                      }),
                      h(NButton, { quaternary: true, circle: true, type: 'error', onClick: () => handleDeleteEnv(dep) }, {
                        default: () => h(NIcon, { component: CloseOutline, size: 22 })
                      })
                    ]
                  })
                })
              }))
            }) : h(NEmpty, { description: $t('page.function.noCustomEnv'), class: "h-full flex items-center justify-center" })
          })
        }),
        h(NTabPane, { name: $t('page.function.systemBuiltin'), tab: $t('page.function.systemBuiltin') }, {
          default: () => h(NScrollbar, { style: 'max-height: 450px' }, {
            default: () => systemEnv.value.length > 0 ? h(NList, { hoverable: true, bordered: true }, {
              default: () => systemEnv.value.map((dep) => h(NListItem, {}, {
                default: () => h(NThing, { title: dep.key, description: dep.value })
              }))
            }) : h(NEmpty, { description: $t('page.function.noSystemBuiltinEnv'), class: "h-full flex items-center justify-center" })
          })
        }),
      ]
    }),
    action: () => h(NButton, { type: 'primary', onClick: () => handleAddEnv() }, { default: () => $t('page.function.addEnv') })
  })
}

const handleAddEnv = () => {
  const formRef = ref<any>(null);
  const newEnv = reactive({ key: '', value: '' });
  const rules = {
    key: { required: true, message: $t('page.function.keyPlaceholder'), trigger: 'blur' },
    value: { required: true, message: $t('page.function.valuePlaceholder'), trigger: 'blur' }
  };
  const d = dialog.info({
    title: $t('page.function.addEnv'),
    content: () => h(NForm, { ref: formRef, model: newEnv, rules: rules, onKeyup: (e: KeyboardEvent) => { if (e.key === 'Enter') { e.preventDefault(); (d.onPositiveClick as any)(); } } }, {
      default: () => [
        h(NFormItem, { label: $t('page.function.key'), path: 'key' }, {
          default: () => h(NInput, { value: newEnv.key, onUpdateValue: (v) => newEnv.key = v })
        }),
        h(NFormItem, { label: $t('page.function.value'), path: 'value' }, {
          default: () => h(NInput, { value: newEnv.value, onUpdateValue: (v) => newEnv.value = v })
        })
      ]
    }),
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
}

const handleEditEnv = (env: Api.Settings.EnvInfo) => {
  const formRef = ref<any>(null);
  const editEnv = reactive({ ...env });
  const rules = {
    value: { required: true, message: $t('page.function.valuePlaceholder'), trigger: 'blur' }
  };
  const d = dialog.info({
    title: $t('page.function.editEnv'),
    content: () => h(NForm, { ref: formRef, model: editEnv, rules: rules, onKeyup: (e: KeyboardEvent) => { if (e.key === 'Enter') { e.preventDefault(); (d.onPositiveClick as any)(); } } }, {
      default: () => [
        h(NFormItem, { label: $t('page.function.key') }, {
          default: () => h(NInput, { value: editEnv.key, disabled: true })
        }),
        h(NFormItem, { label: $t('page.function.value'), path: 'value' }, {
          default: () => h(NInput, { value: editEnv.value, onUpdateValue: (v) => editEnv.value = v })
        })
      ]
    }),
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
}

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
}

// Lifecycle
onMounted(async () => {
  const { data: domain, error } = await getDomain();
  if (!error) {
    localStorage.setItem('hyac_domain', domain);
  }
  await fetchTags();
  await getFunctionData();
  logStore.connect();
});

onBeforeUnmount(() => {
  logStore.disconnect();
});

</script>

<template>
  <div class="h-full flex w-full">
    <NSplit class="h-full" :size="0.1" :min="0.1" :max="0.6">
            <template #1>
        <FunctionList :functions="functions" :selected-function-id="selectedFunction.id" :tags="tags"
          :selected-tag="selectedTag" @create-function="handleCreateFunction" @select-function="functionSelect"
          @delete-function="handleDeleteFunction" @open-env-settings="handleEnvSetting(true)"
          @open-dependency-manager="handleDependence(true)" @select-tag="handleTagSelect" />
      </template>
      <template #2>
        <div v-if="functions.length > 0" class="w-full h-full">
          <NSplit :default-size="0.85" :min="0.1" :max="0.85">
            <template #1>
              <NSplit :default-size="0.85" :min="0.1" :max="0.85" direction="vertical">
                <template #1>
                  <FunctionEditorPanel :func="selectedFunction" :code-changed="codeChanged" :is-saving="isSaving" @save-code="handleSaveCode" :editor-config="editorConfig"
                    @open-history="handleOpenHistory" @update:code="selectedFunction.code = $event" @open-editor-settings="handleFunctionEditorSetting" @edit-meta="handleEditMeta" />
                </template>
                <template #2>
                  <FunctionLogPanel :logs="logStore.logs" />
                </template>
              </NSplit>
            </template>
            <template #2>
               <NTabs type="line" animated class="h-full" style="padding-left: 16px;">
                  <NTabPane name="test" :tab="$t('page.function.functionTest')">
                    <FunctionTestPanel v-if="selectedFunction.type === 'endpoint'" :key="selectedFunction.id" :function-address="functionAddress" />
                   <div v-else class="h-full w-full flex items-center justify-center">
                     <NEmpty :description="$t('page.function.commonFunctionTestHint')"></NEmpty>
                   </div>
                 </NTabPane>
                 <NTabPane name="cron" :tab="$t('page.function.cronJobs')">
                    <div v-if="selectedFunction.type === 'endpoint'">
                      <FunctionCronPanel :func="selectedFunction" />
                    </div>
                    <div v-else class="h-full w-full flex items-center justify-center">
                      <NEmpty :description="$t('page.function.commonFunctionCronHint')"></NEmpty>
                    </div>
                  </NTabPane>
               </NTabs>
              <div v-if="selectedFunction.type !== 'endpoint'" class="h-full w-full flex items-center justify-center">
                <NEmpty :description="$t('page.function.commonFunctionTestHint')">
                </NEmpty>
              </div>
            </template>
          </NSplit>
        </div>
        <div v-else class="h-full w-full flex items-center justify-center">
          <NEmpty :description="$t('page.function.emptyDescription')">
            <template #extra>
              <NButton type="primary" @click="handleCreateFunction">
                {{ $t('page.function.createFunction') }}
              </NButton>
            </template>
          </NEmpty>
        </div>
      </template>
    </NSplit>

    <FunctionHistoryModal v-model:show="showHistoryModel" :history-data="historyData" @rollback="handleRollback" />
    <AiAssistantWindow :show="showAiWindow" @close="handleCloseAiWindow" />
    <NButton
      circle
      type="primary"
      style="position: fixed; right: 20px; bottom: 20px; z-index: 1000;"
      @click="toggleAiWindow"
    >
      <template #icon>
        <NIcon :component="SparklesOutline" />
      </template>
    </NButton>
  </div>
</template>

<style scoped>
.bg-primary_hover {
  background-color: var(--primary-color-hover);
}

.n-card__content {
  height: 100% !important;
}
</style>
