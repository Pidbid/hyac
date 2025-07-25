# server/core/rate_limiter.py
from datetime import datetime, timedelta
from typing import Dict, Callable

from fastapi import Request, Depends

from core.exceptions import APIException

# --- 登录失败限制器 ---

LOGIN_ATTEMPT_LIMIT = 5
LOGIN_LOCKOUT_MINUTES = 15

login_attempts: Dict[str, Dict] = {}


class LoginRateLimiter:
    """
    一个处理登录失败频率的限制器.
    """

    def __init__(self, request: Request):
        self.client_ip = request.client.host if request.client else "unknown"

    def check_rate_limit(self):
        """
        检查IP是否因为失败次数过多而被锁定.
        """
        attempt_info = login_attempts.get(self.client_ip)
        if not attempt_info:
            return

        if attempt_info["count"] >= LOGIN_ATTEMPT_LIMIT:
            lockout_time = attempt_info["timestamp"] + timedelta(
                minutes=LOGIN_LOCKOUT_MINUTES
            )
            if datetime.now() < lockout_time:
                raise APIException(
                    code=113, msg="The request is too frequent, please try again later."
                )
            else:
                # 如果锁定期已过，则重置计数器
                self.reset_attempts()

    def record_failed_attempt(self):
        """
        记录一次失败的登录尝试.
        """
        if self.client_ip not in login_attempts:
            login_attempts[self.client_ip] = {"count": 0, "timestamp": datetime.now()}
        login_attempts[self.client_ip]["count"] += 1
        login_attempts[self.client_ip]["timestamp"] = datetime.now()

    def reset_attempts(self):
        """
        登录成功后重置尝试次数.
        """
        if self.client_ip in login_attempts:
            del login_attempts[self.client_ip]


# --- 通用请求频率限制器 ---

request_counts: Dict[str, Dict] = {}


def get_request_limiter(limit: int, period: timedelta) -> Callable[[Request], None]:
    """
    一个可配置的FastAPI依赖，用于限制API请求频率.

    Args:
        limit (int): 在时间周期内的最大请求数.
        period (timedelta): 时间周期.

    Returns:
        Callable: 一个FastAPI依赖项.
    """

    def limiter(request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        now = datetime.now()

        if client_ip not in request_counts:
            request_counts[client_ip] = {"count": 1, "start_time": now}
            return

        request_info = request_counts[client_ip]
        if now - request_info["start_time"] > period:
            # 如果时间周期已过，重置计数器
            request_info["count"] = 1
            request_info["start_time"] = now
        else:
            if request_info["count"] >= limit:
                raise APIException(
                    code=113, msg="The request is too frequent, please try again later."
                )
            request_info["count"] += 1

    return limiter
