# PyObf

在浏览器里混淆 Python 代码的小工具。纯静态网页，混淆引擎跑在 [Pyodide](https://pyodide.org)（WebAssembly 版 Python）里，代码不会上传到任何服务器。

## 功能

- 局部变量重命名（三种命名风格：`_0x1a2b` / `_abcdef` / `Il1lI`）
- 移除注释和文档字符串
- 字符串常量 base64 编码
- 压缩缩进
- 打包成单行 `exec()` 引导代码（zlib 压缩 + base64，最强混淆）
- 遇到 `eval` / `exec` / `getattr` / `globals()` 等动态代码会自动跳过重命名并提示，避免混淆后代码跑不起来

## 用法

**在线使用**：打开 `index.html`，粘贴代码，选好选项，点"混淆代码"，复制或下载结果。

**本地跑一下**：

```bash
python3 -m http.server 8000
# 打开 http://localhost:8000
```

**独立用混淆引擎**（不经过浏览器）：

```python
from obfuscator import safe_obfuscate

result = safe_obfuscate(open("your_script.py").read(), {
    "rename_locals": True,
    "strip_docstrings": True,
    "encode_strings": True,
    "compact_indent": True,
    "payload_mode": True,
})
print(result["code"])
```

## 部署

纯静态文件，Cloudflare Pages / GitHub Pages / AlwaysData / CT8 都能直接托管，详见 [DEPLOY.md](./DEPLOY.md)。

## 参考

功能思路参考自 [weijarz/oxyry-python-obfuscator](https://github.com/weijarz/oxyry-python-obfuscator)，引擎基于 Python 标准库 `ast` 重新实现。

## License

MIT
