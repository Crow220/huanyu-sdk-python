"""API 业务异常。"""


class HuanyuApiError(Exception):
    """平台响应信封 code != 1 时抛出，携带业务码与平台时间。"""

    def __init__(self, message, api_code, api_time=None):
        # 只把 message 传给基类，保证 str(e) 即业务消息（不拼参数元组）
        super().__init__(message)
        self.message = message
        self.api_code = api_code
        self.api_time = api_time

    def __str__(self):
        return self.message
