# 公共函数

当您的业务逻辑变得复杂时，将所有代码都放在一个 API 函数中会变得难以维护。这时，您可以将可复用的部分抽离到**公共函数 (Common Function)** 中。

公共函数类似于可复用的代码库，它们不能直接通过 API 调用，但可以被任何 API 函数引用，从而实现代码复用和逻辑解耦。

一个公共函数模块可以包含任意数量的函数和类。

## 1. 创建公共函数

首先，创建一个公共函数模块。例如，我们创建一个名为 `math_utils` 的模块，用于执行数学运算。

```python
# 公共函数模块: math_utils
from loguru import logger

def add(a, b):
    """简单的加法函数"""
    logger.info(f"执行 add({a}, {b})")
    return a + b

class AdvancedCalculator:
    """一个支持设置精度的计算器类"""
    def __init__(self, precision: int = 2):
        self.precision = precision
        logger.info(f"AdvancedCalculator 初始化，精度为 {self.precision}")

    def multiply(self, a, b):
        return a * b
```

## 2. 在 API 函数中调用

然后，在您的 API 函数中，通过 `context.common` 对象来调用这个公共函数模块。

```python
# API 函数
from loguru import logger

async def handler(context, x: int = 10, y: int = 3):
    """
    一个调用公共函数的 API 函数示例。
    此示例假设存在一个名为 'math_utils' 的公共函数。
    """
    
    # 通过 context.common.math_utils 调用公共函数
    simple_sum = context.common.math_utils.add(x, y)
    logger.info(f"调用 'math_utils.add'，结果: {simple_sum}")

    # 使用公共模块中的类
    Calculator = context.common.math_utils.AdvancedCalculator
    calc_instance = Calculator(precision=4)
    product = calc_instance.multiply(x, y)
    
    return {
        "code": 0,
        "msg": "计算成功",
        "data": {
            "simple_addition": simple_sum,
            "product": product
        }
    }
```

通过这种方式，您可以将复杂的业务逻辑拆分成多个可维护的公共模块，使您的 API 函数保持简洁和清晰。
