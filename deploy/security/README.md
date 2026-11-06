# WeRSS 源码构建安全审查（未批准上线）

源码版本：`9fd4edb2a9311bffa571db050f53f415705db294`（2026-10-21）。

## 已确认的问题

- `compose/docker-compose-sqlite.yaml` 使用公开默认凭据 `admin/admin@123`，并暴露所有网络接口。
- `main.py` 曾打印所有环境变量；`apis/auth.py` 曾打印微信 Token。当前安全分支已移除日志泄露。
- `web.py` 曾使用 `CORS allow_origins=["*"]`；安全分支改为显式允许域名，默认不允许跨域。
- `init_sys.py` 曾允许公开默认密码且吞掉创建管理员失败异常；安全分支已经修改为至少 16 字符的非默认密码，并明确抛错。
- `core/lax/template_parser.py` 原来允许 Python `eval`/`exec`，且文件包含无目录边界。安全分支用受限 AST 表达式校验、禁止执行多行语句、将包含限制于模板目录并限制展开次数。仍需进一步审计，不代表已经证明不存在其他代码执行入口。
- 官方 Dockerfile 使用 `ghcr.io/rachelos/base-full:latest` 不透明可变基础镜像，并以 root 运行。本目录提供仅从公开 Python 基础镜像和源码构建的候选替代 Dockerfile，使用非 root 用户。
- `requirements.txt` 版本固定但未锁定下载文件 SHA256；基础镜像尚未固定 digest，供应链完整性仍未完全验证。
- GitHub Issue #485 报告容器内挖矿与持久化后门。入侵根因和镜像污染与否尚无公开定论；不能把本地静态扫描视为安全证明。

## 当前状态与边界

- **未构建、未运行、未部署**。Gateway runner 无 Docker API 权限；已登记 Worker 不提供 Docker CLI。按 Gateway 规则，不应赋予 runner docker/root 权限来绕过限制。
- `compose/docker-compose.source.yaml` 仅用于单独、无生产数据的隔离测试主机，绑定 `127.0.0.1:18001`；不挂载宿主 Docker Socket，不连接已有 Redis/MySQL，默认关闭抓取与后台任务。
- 即使本配置限制能力，容器仍有网络出站访问：必须在单独 VM 上阻断对生产内网和元数据地址的访问，或先关闭网络进行无网络测试。
- 不提供扫码、业务数据或常用微信凭证给尚未审查完的实例。

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
