"""
pyobf - a lightweight, in-browser Python source obfuscator engine.
Production-hardened version with exhaustive AST boundary checks.
"""

from __future__ import annotations

import ast
import base64
import builtins
import keyword
import random
import string
import zlib

BUILTIN_NAMES = set(dir(builtins))
KEYWORDS = set(keyword.kwlist) | set(keyword.softkwlist)

DYNAMIC_CALL_NAMES = {
    "eval", "exec", "globals", "locals", "vars",
    "getattr", "setattr", "hasattr", "delattr",
    "__import__", "compile",
}

DUNDER = lambda n: n.startswith("__") and n.endswith("__")


def _rand_name(used: set, style: str, length: int) -> str:
    while True:
        if style == "hex":
            body = "".join(random.choice("0123456789abcdef") for _ in range(length))
            name = "_0x" + body
        elif style == "letters":
            name = "_" + "".join(random.choice(string.ascii_lowercase) for _ in range(length))
        else:
            name = "".join(random.choice("Il1") for _ in range(max(length, 6)))
        if name not in used and not keyword.iskeyword(name) and name not in BUILTIN_NAMES:
            return name


class DynamicUsageScanner(ast.NodeVisitor):
    def __init__(self):
        self.found = False
        self.reasons = set()

    def visit_Call(self, node: ast.Call):
        name = None
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr
        if name in DYNAMIC_CALL_NAMES:
            self.found = True
            self.reasons.add(name)
        self.generic_visit(node)


class ScopeCollector(ast.NodeVisitor):
    def __init__(self):
        self.locals: set[str] = set()
        self.globals_declared: set[str] = set()
        self.nonlocals_declared: set[str] = set()
        self.imported_names: set[str] = set()

    def visit_FunctionDef(self, node): return
    def visit_AsyncFunctionDef(self, node): return
    def visit_ClassDef(self, node): return
    def visit_Lambda(self, node): return

    def visit_Global(self, node: ast.Global):
        self.globals_declared.update(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal):
        self.nonlocals_declared.update(node.names)

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imported_names.add(alias.asname or alias.name.split('.')[0])

    def visit_ImportFrom(self, node: ast.ImportFrom):
        for alias in node.names:
            self.imported_names.add(alias.asname or alias.name)

    def visit_Name(self, node: ast.Name):
        if isinstance(node.ctx, ast.Store):
            self.locals.add(node.id)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        if node.name:
            self.locals.add(node.name)
        self.generic_visit(node)

    def visit_NamedExpr(self, node):
        if isinstance(node.target, ast.Name):
            self.locals.add(node.target.id)
        self.generic_visit(node)


def _collect_params(args: ast.arguments) -> set[str]:
    names = set()
    for a in list(getattr(args, "posonlyargs", [])) + list(args.args) + list(args.kwonlyargs):
        names.add(a.arg)
    if args.vararg:
        names.add(args.vararg.arg)
    if args.kwarg:
        names.add(args.kwarg.arg)
    return names


class ProtectedNameScanner(ast.NodeVisitor):
    def __init__(self):
        self.names: set[str] = set()

    def visit_Global(self, node: ast.Global):
        self.names.update(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal):
        self.names.update(node.names)


class Renamer(ast.NodeTransformer):
    def __init__(self, style: str, length: int, protected: set | None = None):
        self.style = style
        self.length = length
        self.protected = protected or set()
        self.stack: list[dict] = [{}]

    def _push_scope(self, node) -> dict:
        collector = ScopeCollector()
        for stmt in node.body:
            collector.visit(stmt)
        params = _collect_params(node.args) if hasattr(node, "args") else set()
        # 保护 5 排除局部导入别名，防止局部变量随机命名后与 import 库名冲突
        candidates = (collector.locals - params - collector.globals_declared 
                      - collector.nonlocals_declared - collector.imported_names)
        candidates = {n for n in candidates if not DUNDER(n) and n not in self.protected}
        mapping = {}
        used_new = set(collector.imported_names)
        for n in sorted(candidates):
            new = _rand_name(used_new, self.style, self.length)
            mapping[n] = new
            used_new.add(new)
        self.stack.append(mapping)
        return mapping

    def _pop_scope(self):
        self.stack.pop()

    def _lookup(self, name: str):
        for frame in reversed(self.stack):
            if name in frame:
                return frame[name]
        return None

    def visit_Name(self, node: ast.Name):
        new = self._lookup(node.id)
        if new:
            node.id = new
        return node

    def visit_arg(self, node: ast.arg):
        new = self._lookup(node.arg)
        if new:
            node.arg = new
        return node

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        if node.name:
            new = self._lookup(node.name)
            if new:
                node.name = new
        self.generic_visit(node)
        return node

    def _visit_function(self, node):
        node.decorator_list = [self.visit(d) for d in node.decorator_list]
        for default_list in (node.args.defaults, node.args.kw_defaults):
            for i, d in enumerate(default_list):
                if d is not None:
                    default_list[i] = self.visit(d)
        if getattr(node, "returns", None):
            node.returns = self.visit(node.returns)

        self._push_scope(node)
        node.args.posonlyargs = [self.visit(a) for a in getattr(node.args, "posonlyargs", [])]
        node.args.args = [self.visit(a) for a in node.args.args]
        node.args.kwonlyargs = [self.visit(a) for a in node.args.kwonlyargs]
        if node.args.vararg:
            node.args.vararg = self.visit(node.args.vararg)
        if node.args.kwarg:
            node.args.kwarg = self.visit(node.args.kwarg)
        node.body = [self.visit(s) for s in node.body]
        self._pop_scope()
        return node

    def visit_FunctionDef(self, node): return self._visit_function(node)
    def visit_AsyncFunctionDef(self, node): return self._visit_function(node)

    def visit_Lambda(self, node: ast.Lambda):
        for default_list in (node.args.defaults, node.args.kw_defaults):
            for i, d in enumerate(default_list):
                if d is not None:
                    default_list[i] = self.visit(d)
        self._push_scope(node)
        node.args.args = [self.visit(a) for a in node.args.args]
        node.args.kwonlyargs = [self.visit(a) for a in node.args.kwonlyargs]
        node.body = self.visit(node.body)
        self._pop_scope()
        return node

    def visit_ClassDef(self, node: ast.ClassDef):
        node.bases = [self.visit(b) for b in node.bases]
        node.decorator_list = [self.visit(d) for d in node.decorator_list]
        new_body = []
        for stmt in node.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                new_body.append(self.visit(stmt))
            else:
                new_body.append(stmt)
        node.body = new_body
        return node

    def visit_Attribute(self, node: ast.Attribute):
        node.value = self.visit(node.value)
        return node

    def visit_keyword(self, node: ast.keyword):
        if node.value is not None:
            node.value = self.visit(node.value)
        return node


class DocstringStripper(ast.NodeTransformer):
    def _strip(self, body):
        if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
                and isinstance(body[0].value.value, str):
            body = body[1:]
        if not body:
            body = [ast.Pass()]
        return body

    def visit_Module(self, node: ast.Module):
        node.body = self._strip(node.body)
        self.generic_visit(node)
        return node

    def visit_FunctionDef(self, node):
        node.body = self._strip(node.body)
        self.generic_visit(node)
        return node

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        node.body = self._strip(node.body)
        self.generic_visit(node)
        return node


class StringEncoder(ast.NodeTransformer):
    def __init__(self, use_xor: bool = True, func_name: str = "__pyobf_d"):
        self.count = 0
        self.use_xor = use_xor
        self.func_name = func_name
        self._stack: list[ast.AST] = []

    def visit(self, node):
        self._stack.append(node)
        try:
            return super().visit(node)
        finally:
            self._stack.pop()

    def _is_protected_string_context(self, node: ast.Constant) -> bool:
        if len(self._stack) < 2:
            return False
        parent = self._stack[-2]

        # 1. 字典键保护
        if isinstance(parent, ast.Dict):
            for k in parent.keys:
                if k is node:
                    return True

        # 保护 1: 装饰器内部的所有字符串参数不编码，避免破坏框架静态路由和预导入时序
        for p in self._stack:
            if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if any(node is d or any(node is sub for sub in ast.walk(d)) for d in p.decorator_list):
                    return True

        # 2. 模式匹配保护 (Match)
        for i in range(len(self._stack) - 1):
            ancestor = self._stack[i]
            if type(ancestor).__name__ == "match_case":
                child = self._stack[i + 1]
                if child is not getattr(ancestor, "guard", None) and child not in getattr(ancestor, "body", []):
                    return True
            if type(ancestor).__name__.startswith("Match"):
                return True

        # 保护 3: 全局及特殊导出名单全链路保护（修复 BinOp 等复杂声明下的 __all__ / __slots__）
        for p in reversed(self._stack[:-1]):
            if isinstance(p, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = p.targets if isinstance(p, ast.Assign) else [p.target]
                for t in targets:
                    if isinstance(t, ast.Name) and t.id in ("__all__", "__slots__"):
                        return True
            elif isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                break

        # 4. 类型注解保护 (Type Annotations)
        for i in range(len(self._stack) - 2, -1, -1):
            ancestor = self._stack[i]
            child = self._stack[i + 1]
            if isinstance(ancestor, ast.AnnAssign) and ancestor.annotation is child:
                return True
            if isinstance(ancestor, (ast.FunctionDef, ast.AsyncFunctionDef)) and ancestor.returns is child:
                return True
            if isinstance(ancestor, ast.arg) and ancestor.annotation is child:
                return True
            if isinstance(ancestor, ast.stmt) and not isinstance(ancestor, (ast.AnnAssign, ast.FunctionDef, ast.AsyncFunctionDef)):
                break

        return False

    def visit_Module(self, node):
        self._encode_body(node.body)
        return node

    def visit_FunctionDef(self, node):
        self._encode_body(node.body)
        return node

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self._encode_body(node.body)
        return node

    def _encode_body(self, body):
        # 修复 Docstring 遗漏：若第一条语句是纯 docstring，明确跳过编码
        start_idx = 0
        if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
                and isinstance(body[0].value.value, str):
            start_idx = 1
        for stmt in body[start_idx:]:
            self.generic_visit(stmt)

    def visit_JoinedStr(self, node: ast.JoinedStr):
        new_values = []
        for v in node.values:
            if isinstance(v, ast.FormattedValue):
                v.value = self.visit(v.value)
                new_values.append(v)
            else:
                new_values.append(v)
        node.values = new_values
        return node

    def visit_Constant(self, node: ast.Constant):
        if isinstance(node.value, str) and node.value != "":
            if self._is_protected_string_context(node):
                return node
            try:
                raw_bytes = node.value.encode("utf-8", errors="surrogatepass")
            except Exception:
                return node
            self.count += 1
            if self.use_xor:
                key = random.randint(1, 255)
                xored = bytes(b ^ key for b in raw_bytes)
                encoded = base64.b64encode(xored).decode("ascii")
                call = ast.Call(
                    func=ast.Name(id=self.func_name, ctx=ast.Load()),
                    args=[ast.Constant(value=encoded), ast.Constant(value=key)],
                    keywords=[],
                )
            else:
                encoded = base64.b64encode(raw_bytes).decode("ascii")
                call = ast.Call(
                    func=ast.Name(id=self.func_name, ctx=ast.Load()),
                    args=[ast.Constant(value=encoded)],
                    keywords=[],
                )
            return ast.copy_location(call, node)
        return node


class NumberAndBoolEncoder(ast.NodeTransformer):
    def __init__(self, encode_numbers: bool = True, encode_booleans: bool = True):
        self.encode_numbers = encode_numbers
        self.encode_booleans = encode_booleans
        self._stack: list[ast.AST] = []

    def visit(self, node):
        self._stack.append(node)
        try:
            return super().visit(node)
        finally:
            self._stack.pop()

    def _is_in_match_pattern(self) -> bool:
        for i in range(len(self._stack) - 1):
            ancestor = self._stack[i]
            if type(ancestor).__name__ == "match_case":
                child = self._stack[i + 1]
                if child is not getattr(ancestor, "guard", None) and child not in getattr(ancestor, "body", []):
                    return True
            if type(ancestor).__name__.startswith("Match"):
                return True
        return False

    def visit_Constant(self, node: ast.Constant):
        if self._is_in_match_pattern():
            return node

        if isinstance(node.value, bool):
            if not self.encode_booleans:
                return node
            cmp = ast.Compare(
                left=ast.Constant(value=1 if node.value else 0),
                ops=[ast.Lt() if node.value else ast.Eq()],
                comparators=[ast.Constant(value=2 if node.value else 1)],
            )
            return ast.copy_location(cmp, node)

        # 保护 2: 仅混淆非负整数，彻底杜绝负数常量在复杂运算中优先级倒置导致的数学错误
        if isinstance(node.value, int) and not isinstance(node.value, bool) and self.encode_numbers:
            val = node.value
            if 0 <= val <= 1000000000:
                mask = random.randint(100, 9999)
                xor_val = mask ^ val
                binop = ast.BinOp(
                    left=ast.Constant(value=mask),
                    op=ast.BitXor(),
                    right=ast.Constant(value=xor_val),
                )
                return ast.copy_location(binop, node)
        return node


class JunkCodeInjector(ast.NodeTransformer):
    def __init__(self, style: str = "hex", length: int = 6):
        self.style = style
        self.length = length

    def _generate_junk_stmt(self) -> ast.stmt:
        a = random.randint(11, 49)
        b = random.randint(11, 49)
        delta = random.randint(1, 99)
        target = (a * b) + delta
        cond = ast.Compare(
            left=ast.BinOp(
                left=ast.Constant(value=a),
                op=ast.Mult(),
                right=ast.Constant(value=b)
            ),
            ops=[ast.Eq()],
            comparators=[ast.Constant(value=target)]
        )
        dummy_var = _rand_name(set(), self.style, self.length)
        body = [
            ast.Assign(
                targets=[ast.Name(id=dummy_var, ctx=ast.Store())],
                value=ast.Constant(value=None)
            )
        ]
        return ast.If(test=cond, body=body, orelse=[])

    def _is_stub_body(self, body: list[ast.stmt]) -> bool:
        if len(body) <= 1:
            return True
        meaningful = sum(1 for s in body if not (isinstance(s, ast.Pass) or 
                         (isinstance(s, ast.Expr) and isinstance(getattr(s, "value", None), ast.Constant))))
        return meaningful <= 1

    def _inject_body(self, body: list[ast.stmt]) -> list[ast.stmt]:
        if not body or self._is_stub_body(body):
            return body
        new_body = []
        max_injections = min(2, max(1, len(body) // 3))
        injected_count = 0
        for stmt in body:
            new_body.append(self.visit(stmt))
            if injected_count < max_injections:
                # 保护 4: 严格排除 Yield / YieldFrom 等生成器状态语句，防止破坏协程调用
                is_yield = isinstance(stmt, ast.Expr) and isinstance(getattr(stmt, "value", None), (ast.Yield, ast.YieldFrom))
                if not isinstance(stmt, (ast.Return, ast.Raise, ast.Break, ast.Continue, ast.Pass, ast.Try, ast.With)) and not is_yield:
                    if random.random() < 0.4:
                        junk = self._generate_junk_stmt()
                        ast.copy_location(junk, stmt)
                        new_body.append(junk)
                        injected_count += 1
        return new_body

    def visit_FunctionDef(self, node: ast.FunctionDef):
        node.body = self._inject_body(node.body)
        self.generic_visit(node)
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        node.body = self._inject_body(node.body)
        self.generic_visit(node)
        return node


DECODE_HELPER_XOR = (
    "import base64 as __pyobf_b64\n"
    "{cache_name} = {{}}\n"
    "def {func_name}(__s, __k):\n"
    "    if __s not in {cache_name}:\n"
    "        {cache_name}[__s] = bytes(__b ^ __k for __b in __pyobf_b64.b64decode(__s)).decode('utf-8', errors='surrogatepass')\n"
    "    return {cache_name}[__s]\n"
)

DECODE_HELPER_PLAIN = (
    "import base64 as __pyobf_b64\n"
    "{cache_name} = {{}}\n"
    "def {func_name}(__s):\n"
    "    if __s not in {cache_name}:\n"
    "        {cache_name}[__s] = __pyobf_b64.b64decode(__s.encode('ascii')).decode('utf-8', errors='surrogatepass')\n"
    "    return {cache_name}[__s]\n"
)


def _compact_indent(source: str, indent: int) -> str:
    if indent == 4:
        return source
    out_lines = []
    for line in source.split("\n"):
        stripped = line.lstrip(" ")
        depth = (len(line) - len(stripped)) // 4
        out_lines.append((" " * indent * depth) + stripped)
    return "\n".join(out_lines)


def wrap_as_payload(code: str, reverse: bool = True, compress_level: int = 9) -> str:
    raw = code.encode("utf-8")
    compressed = zlib.compress(raw, compress_level)
    b64 = base64.b64encode(compressed).decode("ascii")
    if reverse:
        b64 = b64[::-1]
        return (
            "_ = (lambda __: __import__('zlib').decompress(__import__('base64')"
            ".b64decode(__[::-1]))); exec(_('%s'))" % b64
        )
    return (
        "_ = (lambda __: __import__('zlib').decompress(__import__('base64')"
        ".b64decode(__))); exec(_('%s'))" % b64
    )


def obfuscate(source: str, options: dict) -> dict:
    warnings = []
    opts = {
        "rename_locals": True,
        "strip_docstrings": True,
        "encode_strings": False,
        "string_xor": True,
        "encode_numbers": False,
        "encode_booleans": False,
        "insert_junk": False,
        "compact_indent": False,
        "name_style": "hex",
        "name_length": 6,
        "seed": None,
        "payload_mode": False,
        "payload_reverse": True,
    }
    opts.update(options or {})

    if opts["seed"] is not None:
        random.seed(opts["seed"])

    tree = ast.parse(source)

    helper_name = "__pyobf_d"
    cache_name = "__pyobf_c"
    if opts["rename_locals"]:
        scanner = DynamicUsageScanner()
        scanner.visit(tree)
        if scanner.found:
            warnings.append(
                "Detected dynamic name access (%s); identifier renaming was "
                "skipped to avoid breaking the program." % ", ".join(sorted(scanner.reasons))
            )
        else:
            helper_name = _rand_name(set(), opts["name_style"], int(opts["name_length"]))
            cache_name = _rand_name({helper_name}, opts["name_style"], int(opts["name_length"]))
            protected_scanner = ProtectedNameScanner()
            protected_scanner.visit(tree)
            tree = Renamer(
                opts["name_style"], int(opts["name_length"]), protected_scanner.names
            ).visit(tree)
            ast.fix_missing_locations(tree)

    if opts["strip_docstrings"]:
        tree = DocstringStripper().visit(tree)
        ast.fix_missing_locations(tree)

    if opts.get("insert_junk", False):
        tree = JunkCodeInjector(opts["name_style"], int(opts["name_length"])).visit(tree)
        ast.fix_missing_locations(tree)

    string_count = 0
    use_xor = bool(opts.get("string_xor", True))
    if opts["encode_strings"]:
        encoder = StringEncoder(use_xor=use_xor, func_name=helper_name)
        tree = encoder.visit(tree)
        ast.fix_missing_locations(tree)
        string_count = encoder.count

    if opts.get("encode_numbers", False) or opts.get("encode_booleans", False):
        tree = NumberAndBoolEncoder(
            encode_numbers=bool(opts.get("encode_numbers", False)),
            encode_booleans=bool(opts.get("encode_booleans", False)),
        ).visit(tree)
        ast.fix_missing_locations(tree)

    result = ast.unparse(tree)

    if opts["encode_strings"] and string_count > 0:
        if use_xor:
            helper_code = DECODE_HELPER_XOR.format(func_name=helper_name, cache_name=cache_name)
        else:
            helper_code = DECODE_HELPER_PLAIN.format(func_name=helper_name, cache_name=cache_name)
        result = helper_code + "\n" + result

    if opts["compact_indent"]:
        result = _compact_indent(result, 1)

    if opts["payload_mode"]:
        result = wrap_as_payload(result, reverse=bool(opts["payload_reverse"]))

    return {
        "code": result,
        "warnings": warnings,
        "original_size": len(source.encode("utf-8")),
        "obfuscated_size": len(result.encode("utf-8")),
    }


def safe_obfuscate(source: str, options: dict) -> dict:
    try:
        return obfuscate(source, options)
    except SyntaxError as e:
        return {"error": "语法错误 SyntaxError: %s (line %s, col %s)" % (e.msg, e.lineno, e.offset)}
    except RecursionError:
        return {"error": "代码过大/嵌套过深，无法处理 (RecursionError)"}
    except Exception as e:
        return {"error": "%s: %s" % (type(e).__name__, e)}