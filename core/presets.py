# -*- coding: utf-8 -*-
"""部署环境预设：能力矩阵 + 依赖清单 + 生成产物集合 + 逐步指引。

面板选择环境后，前端只显示该环境支持的配置分组，后端据此决定要生成哪些文件。
"""
import os
import sys

ENVS = [
    {
        "id": "local",
        "name": "本地测试环境（本机）",
        "summary": "在自己电脑上跑 demo，绑定 127.0.0.1，不上公网。",
        "caps": {
            "nginx": False, "mysql": True, "service": True, "auto_sync": True,
            "systemd": False, "static_only": False, "needs_remote_account": False,
        },
        "deps": ["python", "pip"],
        "optional_deps": ["nginx", "git", "mysql"],
        "artifacts": ["run_local"],
        "notes": [
            "本地环境不需要 Nginx，直接用应用端口访问即可。",
            "Windows 下没有 nginx/git 是正常的，不影响本地部署。",
        ],
    },
    {
        "id": "ubuntu",
        "name": "Ubuntu 轻量云服务器（阿里云/腾讯轻量）",
        "summary": "正式上线用，Nginx 反代 + gunicorn 常驻 + systemd 守护。",
        "caps": {
            "nginx": True, "mysql": True, "service": True, "auto_sync": True,
            "systemd": True, "static_only": False, "needs_remote_account": True,
        },
        "deps": ["python3", "pip", "nginx", "git"],
        "optional_deps": ["mysql"],
        "artifacts": ["nginx", "systemd", "gunicorn", "deploy_sh", "mysql_sql"],
        "notes": [
            "面板生成 nginx.conf / systemd unit / 部署脚本，复制到服务器执行即可。",
            "需要自己在云控制台放行安全组端口，面板不代管服务器与备案。",
        ],
    },
    {
        "id": "pythonanywhere",
        "name": "PythonAnywhere 免费托管",
        "summary": "免费额度跑后端原型，通过 WSGI 文件接入。",
        "caps": {
            "nginx": False, "mysql": True, "service": False, "auto_sync": False,
            "systemd": False, "static_only": False, "needs_remote_account": True,
        },
        "deps": ["python"],
        "optional_deps": [],
        "artifacts": ["pa_wsgi", "requirements"],
        "notes": [
            "免费版禁止任意出站请求，定时同步不可用。",
            "把生成的 WSGI 文件内容粘贴到 Web 面板的 WSGI configuration file 里。",
        ],
    },
    {
        "id": "render",
        "name": "Render 部署",
        "summary": "免费全栈演示，用 render.yaml 一键建服务。",
        "caps": {
            "nginx": False, "mysql": False, "service": False, "auto_sync": True,
            "systemd": False, "static_only": False, "needs_remote_account": True,
        },
        "deps": ["python"],
        "optional_deps": [],
        "artifacts": ["render_yaml", "gunicorn", "requirements"],
        "notes": [
            "免费实例使用 SQLite + 临时磁盘，重启会丢数据，仅适合演示。",
            "把仓库连到 Render 后会自动读取 render.yaml。",
        ],
    },
    {
        "id": "vercel",
        "name": "Vercel（仅前端静态页面）",
        "summary": "只发布静态页面，后端接口不在此环境运行。",
        "caps": {
            "nginx": False, "mysql": False, "service": False, "auto_sync": True,
            "systemd": False, "static_only": True, "needs_remote_account": True,
        },
        "deps": [],
        "optional_deps": [],
        "artifacts": ["vercel_json", "static_export"],
        "notes": [
            "Vercel 只托管静态文件，面板会禁用后端启动按钮并导出 static 目录。",
            "接口地址请在导出的前端配置里指向你另外部署的后端域名。",
        ],
    },
]

ENVS_BY_ID = {e["id"]: e for e in ENVS}

DEFAULT_ENV = "local"


def env_options():
    return [[e["id"], e["name"]] for e in ENVS]


def get_env(env_id):
    return ENVS_BY_ID.get(env_id or DEFAULT_ENV) or ENVS_BY_ID[DEFAULT_ENV]


def caps(env_id):
    return dict(get_env(env_id)["caps"])


def supports(env_id, cap):
    return bool(caps(env_id).get(cap))


def all_presets():
    """完整预设，供 /api/presets 返回。"""
    return [dict(e) for e in ENVS]


def preset_for(env_id):
    e = get_env(env_id)
    out = dict(e)
    out["platform"] = platform_summary()
    return out


def platform_summary():
    if os.name == "nt":
        return {
            "id": "windows", "name": "Windows",
            "service_hint": "面板用独立进程方式启动，支持停止/重启；安装服务需管理员权限。",
        }
    if sys.platform.startswith("linux"):
        return {
            "id": "linux", "name": "Linux",
            "service_hint": "优先使用 systemd 守护；无权限时回退到独立进程方式。",
        }
    return {
        "id": "macos", "name": "macOS",
        "service_hint": "使用独立进程方式启动，日志写入工作目录。",
    }


def artifacts_for(env_id):
    return list(get_env(env_id)["artifacts"])


def deps_for(env_id):
    e = get_env(env_id)
    return {"required": list(e["deps"]), "optional": list(e["optional_deps"])}
