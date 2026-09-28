# PyObf

在浏览器里混淆 Python 代码的小工具。纯静态网页，混淆引擎跑在 [Pyodide](https://pyodide.org)（WebAssembly 版 Python）里，代码不会上传到任何服务器。

## 功能

- **局部变量重命名**（支持三种命名风格：`_0x1a2b` / `_abcdef` / `Il1lI`）
- **移除注释和文档字符串**
- **字符串常量加密**（Base64 + 随机密钥逐字节 XOR 异或加密，带全局解密缓存）
- **数值与布尔值混淆**（位运算异或恒等式 / 动态布尔比对）
- **不透明谓词与死代码干扰**（注入恒假分支混淆控制流图，执行期无副作用）
- **语法与现代特性全兼容**（深度适配 Python 3.8 ~ 3.12+，完美支持 `match-case` 模式、类型注解前向引用、装饰器路由参数与生成器协程隔离）
- **压缩缩进**
- **单行打包**（可选打包成单行 `exec()` 引导代码，基于 zlib 压缩 + Base64）
- **动态语法安全监测**（遇到 `eval` / `exec` / `getattr` / `globals()` 等动态代码自动跳过重命名并提示，避免破坏功能）

## 部署

本项目为纯静态前端结构，无需配置任何后端服务器：
- **开箱即用（极简部署）**：直接前往 [Releases](https://github.com/zaofengyue/PyObf/releases) 下载官方自动打包的 `pyobf-pages.zip`（仅含网页和混淆引擎，体积精简），拖拽即可部署到 Cloudflare Pages 或解压到虚拟主机。
- **自定义部署**：支持 Cloudflare Pages (Git联动 / Direct Upload)、GitHub Pages、AlwaysData、CT8 等，详见 [DEPLOY.md](./DEPLOY.md)。

## 参考

功能思路参考自 [weijarz/oxyry-python-obfuscator](https://github.com/weijarz/oxyry-python-obfuscator)，引擎基于 Python 标准库 `ast` 重新实现与全方位加固。

## License

MIT
