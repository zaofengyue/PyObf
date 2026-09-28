# PyObf

在浏览器里混淆 Python 代码的小工具。纯静态网页，混淆引擎跑在 [Pyodide](https://pyodide.org)（WebAssembly 版 Python）里，代码不会上传到任何服务器。

## 功能

- 局部变量重命名（三种命名风格：`_0x1a2b` / `_abcdef` / `Il1lI`）
- 移除注释和文档字符串
- 字符串常量 Base64 + 动态 XOR 掩码加密
- 数值与布尔值混淆（位运算异或 / 算术恒等式 / 动态比对）
- 不透明谓词与干扰死代码注入（混淆控制流）
- 压缩缩进
- 可选打包成单行 `exec()` 引导代码（zlib 压缩 + base64）
- 遇到 `eval` / `exec` / `getattr` / `globals()` 等动态代码会自动跳过重命名并提示，避免混淆后代码跑不起来

## 部署

纯静态文件，Cloudflare Pages / GitHub Pages / AlwaysData / CT8 都能直接托管，详见 [DEPLOY.md](./DEPLOY.md)。

## 参考

功能思路参考自 [weijarz/oxyry-python-obfuscator](https://github.com/weijarz/oxyry-python-obfuscator)，引擎基于 Python 标准库 `ast` 重新实现。

## License

MIT
