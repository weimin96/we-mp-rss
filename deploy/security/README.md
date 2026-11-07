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
- 安全复核（2026-11-07）：Nginx 已额外封闭匿名可访问的 Git 更新/回滚、通用代理、远程图片代理、导出下载接口；文章详情及公众号详情恢复鉴权依赖，防止绕过入口密码读取业务数据。宿主机 CentOS 7 已结束常规安全维护，不应认定为生产安全审计通过。
- 实际匿名验收：`/api/v1/wx/articles/{article_id}` 和 `/api/v1/wx/mps/{mp_id}` 均返回 401；Nginx 已禁止匿名暴露的 `/api/v1/wx/github/`、`/api/v1/wx/proxy/`、`/api/v1/wx/tools/image/proxy`、`/api/v1/wx/tools/image/download/`、`/api/v1/wx/tools/export/download` 及 `/api/v1/wx/auth/password/` 路由。Nginx 阻断规则位于服务器原有配置中，需在重建 Nginx 部署时保留。
- 受限数据卷权限已设为目录 `0700`、`wx.lic` 与 SQLite 数据库 `0600`。密钥轮换、禁用特权容器、Capabilities 全部移除和禁止提权仍然不足以抵御已获执行权限的容器进程。
- **剩余重要风险**：容器内 TCP 测试能够连接宿主机私有地址 `172.22.25.205:6379` 的 Redis；当前 Docker 网络仍可出站访问内网。应迁移至单独安全维护的虚拟机/主机或设置经过验证的单向出站 ACL，禁止访问宿主机、内部数据库、元数据服务。宿主机 CentOS 7 已 EOL，运行服务前需有操作系统迁移/补丁计划。运行容器 `ReadonlyRootfs=false`，应在确认文件写入范围后启用只读根文件系统。
- **匿名 RSS 白名单（2026-11-07）**：仅 `GET/HEAD https://werss.wiblog.cn/feed/MP_WXS_2391391020.xml` 免 Basic Auth；`/feed/all.xml`、其他 Feed、后台及 API 继续受现有策略保护。Nginx 把此地址固定代理至 `is_update=true`，覆盖客户端任意查询参数以避免将 RSS 订阅链接当作昂贵查询接口，并以 `application/rss+xml` 响应。每 IP 限制 10 次/分钟，突发 10 次；规则见 `deploy/security/nginx-public-douban-feed.conf`，Nginx 重新部署时需要保留并安装该片段及对应全局 rate-limit zone。
- **全文持久化修复（2026-11-07）**：微信读书 cover 兜底模式取正文失败时不再写入空正文或推进同步完成时间；已入库但 `has_content=0` 的文章在后续采集时允许再次请求正文，采集成功时只补充正文、正文 HTML 和完整状态，不覆盖已存元数据。`RSS_FULLTEXT_ONLY=True` 使当前部署的 RSS 只发布已持久化完整正文的条目，避免订阅器收到空正文。已知「看一些新疆店名，感受到了直白的可爱」的正文接口返回 `-2012`（微信读书账号配额耗尽），数据库保留该记录，暂不发布，待接口可用时自动补抓。此选项属于部署级配置，不默认影响其他安装环境。

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
