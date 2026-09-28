# 更新日志 (CHANGELOG)

## [2026-09-28] - 混淆强度重大升级与架构加固

### 1. 新增功能特性 (New Features)

- **数值与布尔值混淆 (Number & Boolean Obfuscation)**：
  - 新增 `NumberAndBoolEncoder` AST 节点转换器。
  - 将整数常量自动转换为等价的位运算异或表达式（如 `(mask ^ (mask ^ val))`）或动态算术恒等式，破除硬编码数字特征。
  - 将 `True` 转换为动态比对表达式 `(1 < 2)`，将 `False` 转换为 `(0 == 1)`。
- **动态异或字符串加密 (Dynamic XOR String Encryption)**：
  - 改造 `StringEncoder`，在原纯 Base64 的基础上引入随机字节密钥动态异或（XOR Cipher）机制。
  - 运行时解密辅助函数支持逐字节异或还原，彻底阻断常规自动化 Base64 正则抓取脚本。
  - 解密辅助函数名随所选命名风格随机生成，与混淆后的普通变量融为一体，隐藏特征调用名。
- **不透明谓词与死代码干扰注入 (Opaque Predicates & Junk Code)**：
  - 新增 `JunkCodeInjector` AST 转换器。
  - 在函数体中随机安全注入动态计算恒为 `False` 的不透明谓词分支（如 `if (a * b) == (a * b + delta):`）及哑变量赋值。
  - 混淆控制流图（CFG），大幅提高逆向人员的人工阅读难度与自动化反编译器分析成本，且执行期 100% 无副作用。

### 2. 界面与交互升级 (UI & UX)

- **前端工具栏扩展 (`index.html`)**：
  - 新增 `[x] 数值与布尔混淆 (位运算/算术等价)` 控制开关。
  - 新增 `[ ] 注入干扰死代码与不透明谓词` 控制开关。
  - 字符串加密项更新为 `[x] 编码字符串 (Base64 + XOR 动态混淆)`。
  - 为 `打包为单行 exec (加载器模式)` 添加安全气泡提示，默认取消自动勾选，降低用户在云服务器部署时触发主机安全/EDR/杀软误报的风险。
- **Pyodide 交互对接**：
  - 前端 `getOptions()` 完整同步收集新混淆参数，并透明传递给 WebAssembly 中的 `obfuscator.py`。

### 3. 兼容性与安全指标 (Compatibility & Security)

- **零依赖原则**：所有新增实现 100% 依托 Python 标准库 `ast`、`base64`、`random`，未引入任何第三方依赖。
- **部署方式无缝兼容**：依然保持纯静态结构，无需构建打包，随时支持直接推送到 Cloudflare Pages、GitHub Pages、AlwaysData、CT8 等静态平台。
- **运行期零破坏**：严格遵循作用域隔离准则，生成代码支持标准 Python 3.8+ 解释器直接运行。
