# PyObf — 纯前端 Python 代码混淆工具

在浏览器里混淆 Python 源码，代码永远不离开你的设备。

在线体验（部署后替换为你的地址）：`https://pyobf.pages.dev`

![license](https://img.shields.io/badge/license-MIT-f2b705)

## 这是什么

一个单页 Web 应用：

- 前端是纯静态 HTML/CSS/JS（`index.html`），没有任何构建步骤。
- 混淆逻辑是一段普通的 Python 代码（`obfuscator.py`），只使用标准库
  (`ast` / `tokenize` / `base64` / `keyword`)。
- 页面加载时通过 [Pyodide](https://pyodide.org)（WebAssembly 版 CPython）
  在浏览器里直接运行这段 Python 代码——**没有任何服务器端处理**，
  用户粘贴的代码永远不会离开浏览器标签页。

这意味着整个项目可以部署到**任意静态文件托管**：Cloudflare Pages、
GitHub Pages、Vercel、Netlify，或者 AlwaysData / CT8 这类传统虚拟主机
的"静态网站"目录，都不需要服务端运行 Python。

参考了 [weijarz/oxyry-python-obfuscator](https://github.com/weijarz/oxyry-python-obfuscator)
的功能定位（Python 源码混淆），但引擎是基于 `ast` 重新实现的，逻辑更简单、
更容易审计和二次开发。

## 功能

| 功能 | 说明 |
|---|---|
| 局部变量重命名 | 基于作用域分析，只重命名函数体内纯局部的变量；函数参数、全局名、类属性、导入名保持不变（否则会破坏用关键字参数调用该函数的地方，例如 `f(a=1)`） |
| 危险代码检测 | 检测到 `eval` / `exec` / `getattr` / `globals()` 等动态特性时自动跳过重命名并提示，而不是生成一个运行不了的脚本 |
| 移除注释 & 文档字符串 | 源码经 AST 往返后注释天然消失；文档字符串单独检测移除 |
| 字符串常量编码 | 普通字符串替换为 base64 解码调用；f-string 的静态文本片段保持不变，只转换其中的表达式 |
| 压缩缩进 | 可将 4 空格缩进压缩为 1 空格，减小体积 |
| 命名风格 | `_0x1a2b`（十六进制）/ `_abcxyz`（字母）/ `Il1lI`（易混淆字符） |

## 本地开发

不需要任何构建工具，直接起一个静态服务器即可（不能用 `file://` 打开，
因为 `fetch('obfuscator.py')` 和 WASM 加载需要 http(s) 协议）：

```bash
python3 -m http.server 8000
# 打开 http://localhost:8000
```

## 目录结构

```
.
├── index.html       # 页面 + 样式 + 交互逻辑（含 Pyodide 引导代码）
├── obfuscator.py     # 混淆引擎（纯标准库，可独立于浏览器使用/测试）
├── DEPLOY.md         # Cloudflare Pages / AlwaysData / CT8 部署步骤（Dashboard 操作，无需命令行）
├── LICENSE
└── README.md
```

## 独立使用混淆引擎（不经过浏览器）

`obfuscator.py` 本身是一个普通的 Python 模块，也可以直接在本地 CPython
里用，方便写测试或集成到 CI：

```python
from obfuscator import safe_obfuscate

source = open("your_script.py").read()
result = safe_obfuscate(source, {
    "rename_locals": True,
    "strip_docstrings": True,
    "encode_strings": False,
    "compact_indent": False,
    "name_style": "hex",
    "name_length": 6,
    "seed": None,
})

if "error" in result:
    print("失败:", result["error"])
else:
    print(result["code"])
```

## 部署

见 [DEPLOY.md](./DEPLOY.md)：Cloudflare Pages（Dashboard 拖拽/Git 集成，
无需 Wrangler 命令行）、AlwaysData、CT8 三种方式的详细步骤。

## 局限性 & 注意事项

这是一个**代码混淆工具**，不是加密/DRM工具——目标是提高人工阅读理解的
成本，而不是防止专业逆向工程。请注意：

- 重命名只覆盖函数体内纯局部的变量，**函数参数不会被重命名**（否则会破坏
  任何用关键字参数调用它的地方，例如 `f(a=1, b=2)`），模块级全局名、类属性、
  导出的公共 API 名称默认也不会被重命名（否则会破坏被其他模块 import 的代码）。
- 一旦检测到 `eval`/`exec`/`getattr`/`globals()` 等动态特性，会**自动禁用**
  重命名以保证程序仍可正常运行——这是刻意的保守设计，正确性优先于混淆强度。
- 字符串编码只是 base64 编码，不是加密，任何人都可以直接解码还原，
  它的作用只是让 `grep`/静态阅读变得不直接，不能视为安全措施。
- 建议：混淆后务必运行一遍你的测试套件，确认行为与原始代码一致。

## License

MIT，见 [LICENSE](./LICENSE)。
