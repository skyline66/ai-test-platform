# 环境固化：平台跑在服务器上，浏览器版本、时区、字体、代理任何一样和本地不同，用例就挂给你看。
# 所以基础镜像、系统包、浏览器修订号全部锁死；不要在服务器上现装浏览器。

FROM python:3.12-slim

ENV TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    ATP_ARTIFACTS=/app/artifacts

# tzdata + 中文字体：缺字体时中文会渲染成方块，
# 有些用例靠「文案可见」断言，方块会直接把断言搞挂。
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata fonts-noto-cjk curl \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖，利用镜像层缓存
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 浏览器单独一层：playwright==1.55.0 决定 chromium 的修订号
RUN python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY . .

EXPOSE 8077

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD curl -fsS http://127.0.0.1:8077/api/health || exit 1

CMD ["python", "-m", "atp", "serve", "--host", "0.0.0.0"]