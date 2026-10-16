# 免费上线：GitHub Pages

这个仓库有两种东西，托管方式不一样，先分清：

| 内容 | 位置 | 免费托管 |
| --- | --- | --- |
| **查询站点**（静态） | `docs/` | ✅ GitHub Pages，免费、自带域名 |
| **Flask 后端**（动态） | `projects/打工避雷平台/` | ❌ Pages 跑不了 Python，需 Render / PythonAnywhere / 自建服务器 |
| **部署面板**（Flask） | `tools/deploy_panel/` 或仓库根的 `core/`、`app.py` | ❌ 同上；本地运行最方便 |

---

## 一、你的免费域名（不需要注册）

仓库名直接变成域名：

```
https://waxjgn.github.io/job-radar-panel/
```

这个地址由 GitHub 免费提供、长期有效、无需备案、无需 DNS 配置。

## 二、开启 Pages（二选一）

### 方式 A：用仓库自带的 Action（推荐）

仓库里已有 `.github/workflows/pages.yml`，推送后自动发布。首次需要打开开关：

1. 打开 https://github.com/waxjgn/job-radar-panel/settings/pages
2. **Build and deployment → Source** 选 **GitHub Actions**
3. 回到 https://github.com/waxjgn/job-radar-panel/actions 等 `Deploy static site to GitHub Pages` 跑完（约 40 秒）
4. 访问 https://waxjgn.github.io/job-radar-panel/

以后只要改 `docs/` 里的文件并推送，站点自动更新。

### 方式 B：不用 Action，直接指目录

1. 打开 https://github.com/waxjgn/job-radar-panel/settings/pages
2. **Source** 选 **Deploy from a branch**
3. **Branch** 选 `main`，目录选 `/docs`，Save
4. 等 1 分钟左右，访问 https://waxjgn.github.io/job-radar-panel/

## 三、本地预览（还没上线也能看）

`docs/` 是纯静态站，用任意静态服务器打开即可：

```bash
cd docs
python -m http.server 8080
# 浏览器打开 http://127.0.0.1:8080
```

> 直接双击 `index.html` 用 `file://` 打开会读不到 `data/companies.json`（浏览器安全限制），必须走本地服务器。

## 四、自定义域名（可选，这一步才需要注册）

想让站点挂在 `job-radar.xyz` 这类域名上：

1. **注册域名**：Cloudflare Registrar、Namecheap、阿里云/腾讯云都可以。免费域名可用 Freenom 之类，但稳定性与续期风险较高，长期用建议直接买（年付通常几十元）。
2. **在仓库里放 CNAME 文件**：在 `docs/` 下新建文件 `CNAME`，内容只有一行你的域名，例如：
   ```
   job-radar.example.com
   ```
   （注意：文件名叫 `CNAME`，无扩展名，不要换行成多行）
3. **配 DNS**：在域名商控制台加记录
   - 子域名（如 `job-radar.example.com`）：`CNAME` → `waxjgn.github.io`
   - 根域名（如 `example.com`）：加 4 条 `A`，指向 `185.199.108.153`、`185.199.109.153`、`185.199.110.153`、`185.199.111.153`
4. **在 Pages 设置里填域名**：https://github.com/waxjgn/job-radar-panel/settings/pages → Custom domain 填入域名 → Save
5. **勾选 Enforce HTTPS**（等证书签发完成后可用，通常几分钟到一小时）

DNS 生效后，站点同时可通过自定义域名和 `waxjgn.github.io` 访问。

## 五、把 Flask 后端也放到公网（Pages 做不到的部分）

| 平台 | 免费额度 | 怎么做 |
| --- | --- | --- |
| **Render** | 免费 Web Service（实例会休眠、磁盘临时） | 仓库连到 Render，选 Blueprint，会自动读 `deploy/render.yaml`；SQLite 重启会丢数据，仅适合演示 |
| **PythonAnywhere** | 免费额度（禁止任意出站请求） | 把 `deploy/pythonanywhere_wsgi.py` 内容粘到 Web → WSGI configuration file，Reload |
| **Vercel** | 免费静态托管 | 只放静态页；后端要另找地方 |
| **自建 Ubuntu 轻量云** | 付费（几十元/月） | 用部署面板「导出部署脚本+配置」，把 `deploy/` 拷到服务器执行 `sudo bash deploy/deploy.sh` |

用仓库里的可视化面板可以图形化完成上面这些配置与导出：

```bash
python -m pip install -r requirements.txt   # 仓库根（面板本体）
python app.py                               # 打开 http://127.0.0.1:8765
```

## 六、常见问题

**Pages 显示 404**
确认 `docs/index.html` 存在；用方式 B 时务必把目录选成 `/docs`（不是 `/`）。

**页面样式丢失或数据加载失败**
检查 `docs/assets/` 与 `docs/data/` 是否一起推送了；路径是相对路径，站点必须挂在仓库子路径下访问（即 `…/job-radar-panel/`）。

**Action 报 `Pages not enabled` / `Get Pages site failed`**
到 Settings → Pages 把 Source 切成 **GitHub Actions**，再重新跑一次 workflow。

**改了 docs 但线上没变**
浏览器缓存：强制刷新（Ctrl+F5）；或到 Actions 看这一次部署是否成功。
