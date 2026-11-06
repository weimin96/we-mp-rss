# WeRSS 源码构建与受限部署记录（未通过生产安全审计）

源码版本：`9fd4edb2a9311bffa571db050f53f415705db294`（2026-10-21）。

## 已确认的问题

- `compose/docker-compose-sqlite.yaml` 使用公开默认凭据 `admin/admin@123`，并暴露所有网络接口。
- `main.py` 曾打印所有环境变量；`apis/auth.py` 曾打印微信 Token。当前安全分支已移除日志泄露。
- `web.py` 曾使用 `CORS allow_origins=["*"]`；安全分支改为显式允许域名，默认不允许跨域。
- `init_sys.py` 曾允许公开默认密码且吞掉创建管理员失败异常；安全分支已经修改为至少 16 字符的非默认密码，并明确抛错。
- `core/lax/template_parser.py` 原来允许 Python `eval`/`exec`，且文件包含无目录边界。安全分支用受限 AST 表达式校验、禁止执行多行语句、将包含限制于模板目录并限制展开次数。仍需进一步审计，不代表已经证明不存在其他代码执行入口。
- 官方 Dockerfile 使用 `ghcr.io/rachelos/base-full:latest` 不透明可变基础镜像，并以 root 运行。本目录提供仅从公开 Python 基础镜像和源码构建的候选替代 Dockerfile，使用非 root 用户。
- `requirements.txt` 版本固定但未锁定下载文件 SHA256；基础镜像尚未固定 digest，供应链完整性仍未完全验证。
- 源码构建上下文必须排除 `deploy/security/.env.source`、`.edge-pass` 等凭证；安全分支 `.dockerignore` 已新增排除规则，Dockerfile 带有文件缺席断言。曾使用未排除凭证的旧构建需要移除旧镜像及其未使用的构建缓存。
- GitHub Issue #485 报告容器内挖矿与持久化后门。入侵根因和镜像污染与否尚无公开定论；不能把本地静态扫描视为安全证明。

## 当前状态与边界

- 2026-11-07 已通过 Workdev 从源码构建并在 `8.138.90.56` 上启动**受限测试实例**，未完成生产安全审计；域名为 `https://werss.wiblog.cn`，通过 Nginx Basic Auth + WeRSS 后台登录保护。
- Gateway runner 无 Docker API 权限；源码从 Workdev SSH 传入测试机并构建，不应扩张 Gateway Docker/root 权限。
- `compose/docker-compose.source.yaml` 只绑定 `127.0.0.1:18001`；不挂载 Docker Socket，不使用现有 Redis/MySQL，定时采集默认关闭。Web 管理入口通过现有 Nginx HTTPS 代理发布。
- 即使本配置限制能力，容器仍有网络出站访问：必须在单独 VM 上阻断对生产内网和元数据地址的访问，或先关闭网络进行无网络测试。
- 微信公众平台扫码授权和「每日豆瓣」订阅已完成。旧版 `appmsgpublish` 返回 `200013` 频率限制，0 篇文章入库；单测 `free_publish` 未返回可用文章。
- 改用 `weread_mp` 低频增量采集，需要到 `/weread` **另行扫码微信读书**。只抓最新一篇，不支持微信公众平台历史文章批量回补。
- `GATHER.CONTENT_AUTO_CHECK=False` 禁止原有自动补抓进入耗时的浏览器提取逻辑；`ENABLE_JOB=False` 在微信读书授权和单篇采集验收完成前维持关闭。
- 微信读书授权就绪后，先手动采集目标 Feed 验证全文、图片和 RSS，再添加合适的低频定时任务；不要在风控后进行密集重试。
- 对微信文章 `img[data-src]` 缺少 `src` 的情况，已增加 RSS/HTML 图片修复；在已通过源码审核的本机基础镜像上，可使用 `deploy/security/Dockerfile.incremental` 快速叠加相关 Python 源码。迁移到新机器时仍使用完整的 `deploy/security/Dockerfile` 构建。
- 自动增量：使用 `systemd` 的 `we-mp-rss-daily-douban.timer`，北京时间每天 02:10、06:10、10:10、14:10、18:10、22:10 查询一次最新文章（4 小时一次），`flock` 防重入，100 秒超时。不依赖 WeRSS Webhook 调度，内置 `ENABLE_JOB=False` 不变。微信读书 Cookie 过期时需在后台重新扫码；未配置任何自动绕过风控策略。

## 具备隔离环境与 Docker 时的人工构建步骤

从项目根目录执行，先创建位于 Git 忽略范围内的专用 `.env` 文件；其键来自 `.env.source.example`，不要在命令行回显真实值。

```shell
# 仅在隔离 VM 执行；需要内存及磁盘空间用于 Playwright Chromium/WebKit
# docker compose -f compose/docker-compose.source.yaml --env-file ./deploy/security/.env.source build --no-cache
# docker compose -f compose/docker-compose.source.yaml --env-file ./deploy/security/.env.source up -d
# docker compose -f compose/docker-compose.source.yaml --env-file ./deploy/security/.env.source ps
# curl -i http://127.0.0.1:18001/
```

正式对外部署前：修复并测试模板表达式/文件包含边界；审核依赖与基础镜像 digest；使用隔离网络、强认证和 TLS；对一次真实文章抓取、容器进程、异常网络连接、持久化文件做验收；不要仅验证 HTTP 200。
