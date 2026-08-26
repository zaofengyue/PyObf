# 部署指南

---

## 方式一：Cloudflare Pages

1. 把项目代码推到你的 GitHub 仓库（在 GitHub 网页上直接
   "Add file → Upload files" 拖拽上传也可以，完全不用 git 命令行）。
2. 登录 [Cloudflare Dashboard](https://dash.cloudflare.com)。
3. 左侧菜单进入 **Workers & Pages**。
4. 点击 **Create application** → 选择 **Pages** 标签页 → **Connect to Git**。
5. 授权并选择你的 GitHub 账号/组织，选中刚才的仓库。
6. 进入 "Set up builds and deployments" 配置页，按如下填写：
   - **Production branch**：`main`（或你的默认分支）
   - **Framework preset**：选择 **None**
   - **Build command**：留空（不需要构建）
   - **Build output directory**：`/`（项目根目录，因为 `index.html` 就在根目录）
7. 点击 **Save and Deploy**。
8. 等待几十秒，Cloudflare 会给你一个
   `https://<项目名>.pages.dev` 的地址，打开即可访问。
9. 之后每次你往 `main` 分支推送新提交，Cloudflare 会自动重新部署——
   不需要再手动操作。

**自定义域名（可选）**：进入项目 → **Custom domains** → **Set up a custom domain**，
按提示添加你已经在 Cloudflare 管理的域名即可。

---

## 方式二：Cloudflare Pages（Direct Upload，拖拽上传）

如果你不想连接 GitHub，也可以直接把文件拖进 Dashboard：

1. 登录 Cloudflare Dashboard → **Workers & Pages**。
2. **Create application** → **Pages** 标签页 → **Upload assets**
   （即 Direct Upload / "Get started" 里的 "Drag and drop your files"）。
3. 输入项目名称，例如 `pyobf`。
4. 把项目文件夹（包含 `index.html`、`obfuscator.py`、`README.md` 等）
   整个拖到上传框里 —— 支持直接拖一个文件夹，或者先打包成一个 `.zip`
   再拖进去，两种都可以。
5. 点击 **Deploy site**。
6. 部署完成后同样会得到 `https://<项目名>.pages.dev` 地址。
7. 以后要更新，回到该项目页面，点击 **Create deployment**，
   重新拖拽最新的文件夹/压缩包即可。

---

## 方式三：AlwaysData

AlwaysData 是通用虚拟主机，静态站点直接放进站点目录即可，不需要
配置任何 Python 后端。

1. 登录 [AlwaysData 管理后台](https://admin.alwaysdata.com)。
2. 左侧 **Web** → **Sites**，点击新建一个站点（或使用注册时自带的默认站点）。
3. 站点类型选择 **Static** / 静态文件，指向你账号下的一个目录，
   例如 `www/pyobf`。
4. 用后台自带的 **File Manager**（或者 SFTP 客户端，用后台提供的
   SFTP 账号密码，仍然不需要在本地跑任何命令）把 `index.html`、
   `obfuscator.py`、`README.md` 等文件上传到上一步的目录下，
   确保 `index.html` 直接在该目录根部（不要多套一层子目录）。
5. 保存后，AlwaysData 会给你一个类似
   `https://<你的账号>.alwaysdata.net/pyobf/` 的地址，打开即可访问。
6. 如需绑定自定义域名，在同一个 Sites 配置页里添加域名并按提示
   完成 DNS 解析。

---

## 方式四：CT8

CT8 的后台和常见的虚拟主机面板类似，同样只需要把静态文件放进网站根目录：

1. 登录 CT8 用户面板。
2. 找到 **文件管理器 / File Manager**，进入你的网站根目录
   （通常是 `public_html` 或类似名称的目录）。
3. 把项目里的 `index.html`、`obfuscator.py`、`README.md` 等文件
   上传到该目录（File Manager 一般支持直接拖拽上传，或者用面板提供的
   FTP/SFTP 账号，用图形化 FTP 客户端如 FileZilla 连接上传，
   同样不需要本地命令行）。
4. 确认 `index.html` 就在网站根目录下，这样访问你的域名
   （或 CT8 分配的子域名）就能直接打开首页。
5. 打开浏览器访问你的站点地址，确认 Pyodide 能正常加载
   （首次加载需要下载几 MB 的 WebAssembly 运行时，稍等几秒）。

---

## 通用检查清单

不管部署到哪个平台，上线后建议检查：

- [ ] 打开首页，右上角状态灯应该从黄色（加载中）变成绿色（就绪）。
- [ ] 页面顶部的"混淆前 / 混淆后"演示区能自动跑出结果。
- [ ] 粘贴一段自己的 Python 代码，点击"混淆代码"能正常输出。
- [ ] `obfuscator.py` 能被浏览器直接访问到（比如
      `https://你的域名/obfuscator.py` 能看到源码文本），
      这是页面通过 `fetch('obfuscator.py')` 加载引擎所必需的——
      如果这个文件和 `index.html` **不在同一目录**，需要把
      `index.html` 里的 `fetch('obfuscator.py')` 改成正确的相对/绝对路径。
- [ ] 浏览器控制台没有 CORS / MIME 类型报错（正常的静态托管，包括本
      文档提到的所有平台，默认都不会有这个问题）。
