import { request } from '../request';

/**
 * Login
 *
 * @param username User name
 * @param password Password
 * @param captcha captcha
 */
export function fetchLogin(username: string, password: string, captcha: string) {
  return request<Api.Auth.LoginToken>({
    url: '/users/login',
    method: 'post',
    data: {
      username,
      password,
      captcha
    }
  });
}

/** Get user info */
export function fetchGetUserInfo() {
  return request<Api.Auth.UserInfo>({ url: '/users/info' });
}

/**
 * Refresh token
 *
 * @param refreshToken Refresh token
 */
export function fetchRefreshToken(refreshToken: string) {
  return request<Api.Auth.LoginToken>({
    url: '/users/refreshToken',
    method: 'post',
    data: {
      refreshToken
    }
  });
}

/**
 * return custom backend error
 *
 * @param code error code
 * @param msg error message
 */
export function fetchCustomBackendError(code: string, msg: string) {
  return request({ url: '/auth/error', params: { code, msg } });
}

/**
 * return a cature image
 */
export function fetchCaptcha() {
  return request({ url: '/users/captcha', method: 'get' });
}

/**
 * Update current user info
 * @param username - new username
 * @param password - new password
 */
export function fetchUpdateMe(data: Partial<Api.Auth.UpdateMePayload>) {
  return request({
    url: '/users/me',
    method: 'post',
    data
  });
}
