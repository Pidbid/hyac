<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch, h, reactive, nextTick } from 'vue';
import { useDialog, useMessage, NForm, NInput, NRadioGroup, NRadio, NSelect, NSplit, NFormItem, type SelectOption, NInputNumber, NButtonGroup, NButton, NTabs, NTabPane, NScrollbar, NList, NListItem, NThing, NEmpty, NDataTable, NSpin, NIcon, NSwitch } from 'naive-ui';
import { AddOutline, CloseOutline, SearchOutline, BrushOutline } from '@vicons/ionicons5';
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
  getDomain
} from '@/service/api';

import FunctionList from './modules/FunctionList.vue';
import FunctionEditorPanel from './modules/FunctionEditorPanel.vue';
import FunctionLogPanel from './modules/FunctionLogPanel.vue';
import FunctionTestPanel from './modules/FunctionTestPanel.vue';
import FunctionHistoryModal from './modules/FunctionHistoryModal.vue';

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
const packageResult = ref<string[]>([])
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
  theme: 'github-light'
});

watch(() => themeStore.darkMode, (isDark) => {
  editorConfig.value.theme = isDark ? 'github-dark' : 'github-light';
}, { immediate: true });

watch(editorConfig, (newValue) => {
  localStorage.setItem('editorConfig', JSON.stringify(newValue));
}, { deep: true });

// State
const functions = ref<Api.Function.FunctionInfo[]>([]);
const selectedFunction = ref<Api.Function.FunctionInfo>({ id: '', name: '', type: 'endpoint', status: 'unpublished', description: '', tags: [], code: '' });
const originalCode = ref('');
const codeChanged = ref(false);
const functionRequestData = ref({ page: 1, length: 50 });

const showHistoryModel = ref(false);
const historyData = ref<Api.Function.FunctionHistoryInfo[]>([]);

// Computed
const functionAddress = computed(() => {
  const domain = localStorage.getItem('hyac_domain');
  if (selectedFunction.value.id !== '' && domain) {
    return `http://${applicationStore.appId}.${domain}/${selectedFunction.value.id}`;
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
  const { data, error } = await GetFunctionData(applicationStore.appId, functionRequestData.value.page, functionRequestData.value.length);
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
      const funcToSelect = functionStore.funcInfo || functions.value[0];
      functionSelect(funcToSelect);
    } else {
        selectedFunction.value = { id: '', name: '', type: 'endpoint', status: 'unpublished', description: '', tags: [], code: '' };
    }
  }
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
        logStore.logs = [];
      }
    }
  });
};

const handleSaveCode = async () => {
  if (!codeChanged.value) return;
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
      selectedFunction.value.code = history.new_code;
      await nextTick();
      await handleSaveCode();
      showHistoryModel.value = false;
      message.success($t('page.function.rollbackSuccess'));
    }
  });
};

const handleFunctionEditorSetting = () => {
  const tempConfig = reactive({
    fontSize: editorConfig.value.fontSize,
    language: 'python',
    minimap: editorConfig.value.minimap,
  });
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
        })
      ]
    }),
    positiveText: $t('common.confirm'),
    negativeText: $t('common.cancel'),
    onPositiveClick: () => {
      editorConfig.value.fontSize = tempConfig.fontSize;
      editorConfig.value.minimap = tempConfig.minimap;
      message.success($t('page.function.settingsSuccess'));
    },
  });
};


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

const handlePackageSearch = async () => {
  isDependenceLoading.value = true;
  const { data, error } = await dependenceSearch(applicationStore.appId, packageSelectInput.value.name, false);
  isDependenceLoading.value = false;
  if (!error) {
    packageResult.value = data
  }
}

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
                  default: () => h(NThing, { title: dep.name, description: dep.version }, {
                    "header-extra": () => h(NButton, { quaternary: true, circle: true, type: 'error', onClick: () => handleDeleteDependence(dep) }, {
                      default: () => h(NIcon, { component: CloseOutline, size: 22 })
                    })
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
              h(NInput, { value: packageSelectInput.value.name, placeholder: $t('page.function.dependenceNamePlaceholder'), onUpdateValue: (value) => { packageSelectInput.value.name = value; } }, {
                suffix: () => h(NButton, { size: 'small', loading: isDependenceLoading.value, onClick: handlePackageSearch }, {
                  default: () => h(NIcon, { component: SearchOutline })
                })
              }),
              h(NDataTable, { columns: [{ title: $t('page.function.dependenceName'), key: "name" }, { title: $t('common.action._self'), key: 'operation', width: 100, ellipsis: true, render: (row) => { return h(NButton, { type: "primary", size: "small", onClick: () => handleAddDependence(row) }, { default: () => h(NIcon, { component: AddOutline }) }) } }], data: packageResult.value.map(r => ({ name: r })), class: 'mt-2', maxHeight: '400px' })
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
  await getFunctionData();
  logStore.connect();
  if (selectedFunction.value.id) {
    logStore.subscribe(selectedFunction.value.id);
  }
});

onBeforeUnmount(() => {
  logStore.disconnect();
});

</script>

<template>
  <div class="h-full flex w-full">
    <NSplit class="h-full" :size="0.1" :min="0.1" :max="0.6">
            <template #1>
        <FunctionList :functions="functions" :selected-function-id="selectedFunction.id"
          @create-function="handleCreateFunction" @select-function="functionSelect"
          @delete-function="handleDeleteFunction" @open-env-settings="handleEnvSetting(true)"
          @open-dependency-manager="handleDependence(true)" />
      </template>
      <template #2>
        <div v-if="functions.length > 0" class="w-full h-full">
          <NSplit :size="0.85">
            <template #1>
              <NSplit :size="0.8" direction="vertical">
                <template #1>
                  <FunctionEditorPanel :func="selectedFunction" :code-changed="codeChanged" @save-code="handleSaveCode" :editor-config="editorConfig"
                    @open-history="handleOpenHistory" @update:code="selectedFunction.code = $event" @open-editor-settings="handleFunctionEditorSetting" />
                </template>
                <template #2>
                  <FunctionLogPanel :logs="logStore.logs" />
                </template>
              </NSplit>
            </template>
            <template #2>
              <FunctionTestPanel :function-address="functionAddress" />
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
