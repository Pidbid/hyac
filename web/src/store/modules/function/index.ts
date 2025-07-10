import { ref } from 'vue';
import { defineStore } from 'pinia';
import { SetupStoreId } from '@/enum';

export const useFunctionStore = defineStore(SetupStoreId.Function, () => {
  const funcInfo = ref<Api.Function.FunctionInfo | null>(null);

  /**
   * Set function info
   *
   * @param info function info
   */
  function setFuncInfo(info: Api.Function.FunctionInfo | null) {
    funcInfo.value = info;
  }

  /**
   * Clear function info
   */
  function clearFunctionInfo() {
    funcInfo.value = null;
  }

  return {
    funcInfo,
    setFuncInfo,
    clearFunctionInfo
  };
});
