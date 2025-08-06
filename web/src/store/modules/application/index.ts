/**
 * @file Application store
 */

import { computed, reactive, ref } from "vue";
import { useRoute } from "vue-router";
import { defineStore } from "pinia";
import { useLoading } from "@sa/hooks";
import { AppInfo } from "@/service/api";
import { useRouterPush } from "@/hooks/common/router";
import { localStg } from "@/utils/storage";
import { SetupStoreId } from "@/enum";
import { $t } from "@/locales";
import { useRouteStore } from "../route";
import { useTabStore } from "../tab";
import { clearAuthStorage, getToken } from "./shared";

export const useApplicationStore = defineStore(SetupStoreId.Application, () => {
  const route = useRoute();
  const routeStore = useRouteStore();
  const tabStore = useTabStore();
  const { toLogin, redirectFromLogin } = useRouterPush(false);
  const { loading: loginLoading, startLoading, endLoading } = useLoading();

  const token = ref(getToken());

  const appInfo: Api.Application.AppInfo = reactive({
    appId: localStg.get("appId") || "",
    appName: "",
    status: "running",
  });

  /** current appid */
  const appId = computed(() => localStg.get("appId") || "");

  const getApplicationInfo = async () => {
    const { data: appInfoData, error } = await AppInfo(appId.value);
    if (!error) {
      appInfo.appName = appInfoData.app_name;
    }
  };

  const setAppStatus = (status: Api.Settings.ApplicationStatus) => {
    appInfo.status = status;
  };

  return {
    token,
    appId,
    appInfo,
    loginLoading,
    getApplicationInfo,
    setAppStatus,
  };
});
