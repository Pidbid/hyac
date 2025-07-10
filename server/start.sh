#!/bin/sh

# Check the TZ environment variable to determine which pip mirror to use.
if [ "$TZ" = "Asia/Shanghai" ]; then
  echo "Timezone is Asia/Shanghai, using Aliyun mirror for pip."
  uv pip install --system --no-cache -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt
else
  echo "Using default pip mirror."
  uv pip install --system --no-cache -r requirements.txt
fi

uvicorn main:app --host 0.0.0.0 --port 8000 --reload
