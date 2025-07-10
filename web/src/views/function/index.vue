<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch, h, reactive, nextTick } from 'vue';
import { useDialog, useMessage, NForm, NInput, NRadioGroup, NRadio, NSelect, NSplit, NFormItem, type SelectOption, NInputNumber, NButtonGroup, NButton, NTabs, NTabPane, NScrollbar, NList, NListItem, NThing, NEmpty, NDataTable, NSpin, NIcon, NSwitch } from 'naive-ui';
import { AddOutline, CloseOutline, SearchOutline, BrushOutline } from '@vicons/ionicons5';
import dayjs from 'dayjs';
import { useApplicationStore } from '@/store/modules/application';
import { useFunctionStore } from '@/store/modules/function';
import { useLogStore } from '@/store/modules/log';
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
  removeEnv
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

const isDependenceLoading = ref(false)
const dependenceTabsRef = ref<undefined | HTMLElement>(undefined)
const packageSelectInput = ref({
  name: "",
  version: ""
})
const packageResult = ref<string[]>([])
let addDependenceDialogRef: any = null;
const commonDependencies = ref<Api.Settings.DependenceInfo[]>([]);
const systemDependencies = ref<Api.Settings.DependenceInfo[]>([]);
const userEnv = ref<Api.Settings.EnvInfo[]>([]);
const systemEnv = ref<Api.Settings.EnvInfo[]>([]);
const storedEditorConfig = localStorage.getItem('editorConfig');
const editorConfig = ref(storedEditorConfig ? JSON.parse(storedEditorConfig) : {
  language: 'python',
  fontSize: 14,
  minimap: true
});

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
  if (selectedFunction.value.id !== '') {
    return `http://${applicationStore.appId}.hyacos.top/${selectedFunction.value.id}`;
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
    const localCreateData = reactive({
    name: '',
    description: '',
    type: "endpoint",
    template_id: "",
    tags: [] as string[],
    templateOptions: [] as SelectOption[]
  });

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

  dialog.info({
    title: '创建函数',
    content: () => h(NForm, { labelPlacement: 'left', labelWidth: 80 }, {
      default: () => [
        h(NFormItem, { label: '函数名称' }, {
          default: () => h(NInput, {
            placeholder: '请输入函数名称',
            value: localCreateData.name,
            onUpdateValue: (value) => localCreateData.name = value
          })
        }),
        h(NFormItem, { label: '函数类型' }, {
          default: () => h(NRadioGroup, {
            value: localCreateData.type,
            onUpdateValue: (value) => {
              localCreateData.type = value;
              fetchLocalTemplates(value);
            }
          }, {
            default: () => [
              h(NRadio, { label: "API 函数", value: 'endpoint' }),
              h(NRadio, { label: "公共函数", value: 'common' })
            ]
          })
        }),
        h(NFormItem, { label: '函数模板' }, {
          default: () => h(NSelect, {
            placeholder: '请选择函数模板',
            options: localCreateData.templateOptions,
            value: localCreateData.template_id,
            onUpdateValue: (value) => localCreateData.template_id = value
          })
        }),
        h(NFormItem, { label: '函数描述' }, {
          default: () => h(NInput, {
            type: 'textarea',
            placeholder: '请输入函数描述',
            value: localCreateData.description,
            onUpdateValue: (value) => localCreateData.description = value
          })
        }),
        h(NFormItem, { label: '标签' }, {
          default: () => h(NInput, {
            placeholder: '请输入标签（逗号分隔）',
            value: localCreateData.tags.join(','),
            onUpdateValue: (value) => localCreateData.tags = value.split(',').map(tag => tag.trim())
          })
        }),
      ]
    }),
    positiveText: '确定',
    negativeText: '取消',
    onPositiveClick: async () => {
      const { data, error } = await CreateFunction(
        applicationStore.appId,
        localCreateData.name,
        localCreateData.type,
        localCreateData.description,
        localCreateData.tags,
        appStore.locale,
        localCreateData.template_id
      );
      if (!error) {
        message.success('创建成功');
        await getFunctionData();
        const newFunc = functions.value.find(func => func.name === localCreateData.name);
        if (newFunc) {
          functionSelect(newFunc);
        }
      } else {
        message.error('创建失败，请稍后重试');
      }
    }
  });
};

const handleDeleteFunction = (func: Api.Function.FunctionInfo) => {
  dialog.warning({
    title: '确认删除吗',
    content: `确定要删除函数 "${func.name}" 吗？删除后不可恢复！`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      const { error } = await DeleteFunction(applicationStore.appId, func.id);
      if (!error) {
        message.success('函数已删除');
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
    message.success('代码已保存');
    originalCode.value = selectedFunction.value.code;
    codeChanged.value = false;
    await getFunctionData();
    const updatedFunc = functions.value.find(f => f.id === currentEditFunctionId);
    if (updatedFunc) {
        selectedFunction.value = updatedFunc;
    }
  } else {
    message.error('保存代码失败，请稍后重试');
  }
};

const handleOpenHistory = async () => {
  const { data, error } = await FunctionHistory(applicationStore.appId, selectedFunction.value.id);
  if (!error) {
    historyData.value = data.data;
    if (data.data.length > 0) {
      showHistoryModel.value = true;
    } else {
      message.warning("该函数没有历史记录");
    }
  }
};

const handleRollback = async (history: Api.Function.FunctionHistoryInfo) => {
  dialog.warning({
    title: '确认回退代码',
    content: `确定要将当前代码回退到 ${dayjs(history.updated_at).format('YYYY-MM-DD HH:mm:ss')} 的版本吗？`,
    positiveText: '确定回退',
    negativeText: '取消',
    onPositiveClick: async () => {
      selectedFunction.value.code = history.new_code;
      await nextTick();
      await handleSaveCode();
      showHistoryModel.value = false;
      message.success('代码已成功回退并保存');
    }
  });
};

const handleFunctionEditorSetting = () => {
  const tempConfig = reactive({
    fontSize: editorConfig.value.fontSize,
    language: 'python',
    minimap: editorConfig.value.minimap,
  });
  dialog.info({
    title: '编辑器设置',
    content: () => h(NForm, { labelPlacement: 'left', labelWidth: 80 }, {
      default: () => [
        h(NFormItem, { label: '字体大小' }, {
          default: () => h(NInputNumber, {
            placeholder: '16',
            value: tempConfig.fontSize,
            onUpdateValue: (value) => { if (value) tempConfig.fontSize = value; }
          })
        }),
        h(NFormItem, { label: '代码预览' }, {
          default: () => h(NSwitch, {
            value: tempConfig.minimap,
            onUpdateValue: (value) => { tempConfig.minimap = value; }
          })
        })
      ]
    }),
    positiveText: '确定',
    negativeText: '取消',
    onPositiveClick: () => {
      editorConfig.value.fontSize = tempConfig.fontSize;
      editorConfig.value.minimap = tempConfig.minimap;
      message.success('设置成功');
    },
  });
};


const handleDeleteDependence = (dep: Api.Settings.DependenceInfo) => {
  dialog.warning({
    title: '确认删除依赖',
    content: `确定要删除依赖 "${dep.name}" 吗？`,
    action: () => h(NButtonGroup, { class: "flex justify-end gap-2 w-full" }, {
      default: () => [
        h(NButton, { type: "default", size: "small", onClick: () => dialog.destroyAll() }, { default: () => "取消" }),
        h(NButton, {
          type: "error", size: "small", onClick: async () => {
            const { error } = await packageRemove(applicationStore.appId, dep.name, false);
            if (!error) {
              message.success('依赖已删除');
              await handleDependence(false); // Refresh list without closing dialog
            } else {
              message.error('删除失败');
            }
            dialog.destroyAll();
          }
        }, { default: () => "仅删除" }),
        h(NButton, {
          type: "warning", size: "small", onClick: async () => {
            const { error } = await packageRemove(applicationStore.appId, dep.name, true);
            if (!error) {
              message.success('依赖已删除，容器正在重启...');
              await handleDependence(false); // Refresh list without closing dialog
            } else {
              message.error('删除失败');
            }
            dialog.destroyAll();
          }
        }, { default: () => "删除并重启" })
      ]
    })
  });
};


const handlePackageAdd = async (restart: boolean = false) => {
  const { data, error } = await packageAdd(applicationStore.appId, packageSelectInput.value.name, packageSelectInput.value.version, restart);
  if (!error) {
    message.success(restart ? '依赖添加成功，容器正在重启...' : '依赖添加成功');
    await handleDependence(false); // Refresh list without closing dialog
  }else{
    message.error('依赖添加失败');
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
    message.error("获取包信息失败");
    isDependenceLoading.value = false;
    return;
  }
  packageSelectInput.value.version = data?.versions?.[0] ?? '';
  isDependenceLoading.value = false;
  addDependenceDialogRef = dialog.info({
    title: '添加',
    content: () => h(NForm, {}, {
      default: () => [
        h(NFormItem, { label: "依赖名称" }, {
          default:
            () => h(NInput, { value: packageSelectInput.value.name, disabled: true })
        }),
        h(NFormItem, { label: "版本" }, {
          default:
            () => h(NSelect, { defaultValue: packageSelectInput.value.version, options: data?.versions?.map((v: string) => ({ label: v, value: v })) ?? [] })
        }),
      ]
    }),
    action: () => h(NButtonGroup, { class: "flex justify-end gap-2 w-full" }, {
      default: () => [
        h(NButton, { type: "default", size: "small", onClick: () => { addDependenceDialogRef.destroy() } }, { default: () => "取消" }),
        h(NButton, { type: "success", size: "small", onClick: () => handlePackageAdd(false) }, { default: () => "安装" }),
        h(NButton, { type: "info", size: "small", onClick: () => handlePackageAdd(true) }, { default: () => "安装并重启" })
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
  isDependenceLoading.value = true;
  const { data, error } = await dependenciesData(applicationStore.appId);
  isDependenceLoading.value = false;

  if (error) {
    message.error("获取依赖列表失败");
    return;
  }
  commonDependencies.value = data.common;
  systemDependencies.value = data.system;

  if (!showDialog) return;

  dialog.info({
    title: '依赖管理',
    content: () => h(NSpin, { show: isDependenceLoading.value }, {
      default: () => h(NTabs, { type: 'segment', animated: true, style: 'height:500px;', ref: dependenceTabsRef }, {
        default: () => [
          h(NTabPane, { name: '已安装', tab: '已安装' }, {
            default: () => h(NScrollbar, { style: 'max-height: 450px' }, {
              default: () => commonDependencies.value.length > 0 ? h(NList, { hoverable: true, clickable: true, bordered: true }, {
                default: () => commonDependencies.value.map((dep) => h(NListItem, {}, {
                  default: () => h(NThing, { title: dep.name, description: dep.version }, {
                    "header-extra": () => h(NButton, { quaternary: true, circle: true, type: 'error', onClick: () => handleDeleteDependence(dep) }, {
                      default: () => h(NIcon, { component: CloseOutline, size: 22 })
                    })
                  })
                }))
              }) : h(NEmpty, { description: "暂无依赖", class: "h-full flex items-center justify-center" })
            })
          }),
          h(NTabPane, { name: '系统依赖', tab: '系统依赖' }, {
            default: () => h(NScrollbar, { style: 'max-height: 450px' }, {
              default: () => systemDependencies.value.length > 0 ? h(NList, { hoverable: true, bordered: true }, {
                default: () => systemDependencies.value.map((dep) => h(NListItem, {}, {
                  default: () => h(NThing, { title: dep.name, description: dep.version })
                }))
              }) : h(NEmpty, { description: "暂无系统依赖", class: "h-full flex items-center justify-center" })
            })
          }),
          h(NTabPane, { name: '添加', tab: '添加' }, {
            default: () => [
              h(NInput, { value: packageSelectInput.value.name, placeholder: '请输入依赖名称', onUpdateValue: (value) => { packageSelectInput.value.name = value; } }, {
                suffix: () => h(NButton, { size: 'small', loading: isDependenceLoading.value, onClick: handlePackageSearch }, {
                  default: () => h(NIcon, { component: SearchOutline })
                })
              }),
              h(NDataTable, { columns: [{ title: "依赖名称", key: "name" }, { title: '操作', key: 'operation', width: 100, ellipsis: true, render: (row) => { return h(NButton, { type: "primary", size: "small", onClick: () => handleAddDependence(row) }, { default: () => h(NIcon, { component: AddOutline }) }) } }], data: packageResult.value.map(r => ({ name: r })), class: 'mt-2', maxHeight: '400px' })
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
    message.error("获取环境变量失败");
    return;
  }
  userEnv.value = data.user;
  systemEnv.value = data.system;

  if (!showDialog) return;

  dialog.info({
    title: '环境变量管理',
    content: () => h(NTabs, { type: 'segment', animated: true, style: 'height:500px;' }, {
      default: () => [
        h(NTabPane, { name: '自定义', tab: '自定义' }, {
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
            }) : h(NEmpty, { description: "暂无自定义环境变量", class: "h-full flex items-center justify-center" })
          })
        }),
        h(NTabPane, { name: '系统内置', tab: '系统内置' }, {
          default: () => h(NScrollbar, { style: 'max-height: 450px' }, {
            default: () => systemEnv.value.length > 0 ? h(NList, { hoverable: true, bordered: true }, {
              default: () => systemEnv.value.map((dep) => h(NListItem, {}, {
                default: () => h(NThing, { title: dep.key, description: dep.value })
              }))
            }) : h(NEmpty, { description: "暂无系统内置环境变量", class: "h-full flex items-center justify-center" })
          })
        }),
      ]
    }),
    action: () => h(NButton, { type: 'primary', onClick: () => handleAddEnv() }, { default: () => "添加环境变量" })
  })
}

const handleAddEnv = () => {
  const newEnv = reactive({ key: '', value: '' });
  dialog.info({
    title: '添加环境变量',
    content: () => h(NForm, { model: newEnv }, {
      default: () => [
        h(NFormItem, { label: 'Key' }, {
          default: () => h(NInput, { value: newEnv.key, onUpdateValue: (v) => newEnv.key = v })
        }),
        h(NFormItem, { label: 'Value' }, {
          default: () => h(NInput, { value: newEnv.value, onUpdateValue: (v) => newEnv.value = v })
        })
      ]
    }),
    positiveText: '确定',
    negativeText: '取消',
    onPositiveClick: async () => {
      const { error } = await addEnv(applicationStore.appId, newEnv.key, newEnv.value);
      if (!error) {
        message.success('添加成功');
        await handleEnvSetting(false);
      } else {
        message.error('添加失败');
      }
    }
  });
}

const handleEditEnv = (env: Api.Settings.EnvInfo) => {
  const editEnv = reactive({ ...env });
  dialog.info({
    title: '编辑环境变量',
    content: () => h(NForm, { model: editEnv }, {
      default: () => [
        h(NFormItem, { label: 'Key' }, {
          default: () => h(NInput, { value: editEnv.key, disabled: true })
        }),
        h(NFormItem, { label: 'Value' }, {
          default: () => h(NInput, { value: editEnv.value, onUpdateValue: (v) => editEnv.value = v })
        })
      ]
    }),
    positiveText: '确定',
    negativeText: '取消',
    onPositiveClick: async () => {
      const { error } = await addEnv(applicationStore.appId, editEnv.key, editEnv.value);
      if (!error) {
        message.success('修改成功');
        await handleEnvSetting(false);
      } else {
        message.error('修改失败');
      }
    }
  });
}

const handleDeleteEnv = (env: Api.Settings.EnvInfo) => {
  dialog.warning({
    title: '确认删除环境变量',
    content: `确定要删除环境变量 "${env.key}" 吗？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      const { error } = await removeEnv(applicationStore.appId, env.key);
      if (!error) {
        message.success('删除成功');
        await handleEnvSetting(false);
      } else {
        message.error('删除失败');
      }
    }
  });
}

// Lifecycle
onMounted(async () => {
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
