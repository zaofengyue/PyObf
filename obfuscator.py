"""
pyobf - a lightweight, in-browser Python source obfuscator engine.

Design goals:
  * Pure standard library (ast / tokenize / keyword / base64) so it can run
    unmodified inside Pyodide (WebAssembly Python) in the browser - no
    server-side execution required.
  * Conservative, scope-aware local-variable renaming (never touches
    globals, class attributes, imported names, dunder names, or anything
    reached through dynamic features like eval/exec/getattr/globals()).
  * Optional comment/docstring stripping, string-literal encoding and
    whitespace compaction.

This module exposes a single entry point: obfuscate(source, options) -> dict
"""

from __future__ import annotations

import ast
import base64
import builtins
import keyword
import random
import string
import textwrap
import zlib

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BUILTIN_NAMES = set(dir(builtins))
KEYWORDS = set(keyword.kwlist) | set(keyword.softkwlist)

# Calls that make identifier renaming unsafe anywhere in the module because
# they can reference names dynamically by string.
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
        else:  # "il1" confusable style
            name = "".join(random.choice("Il1") for _ in range(max(length, 6)))
        if name not in used and not keyword.iskeyword(name) and name not in BUILTIN_NAMES:
            return name


class DynamicUsageScanner(ast.NodeVisitor):
    """Detects whole-module use of dynamic name access, which disables
    identifier renaming for safety."""

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
    """Collects candidate local-variable / parameter names bound within a
    single function scope. Does NOT descend into nested function/class defs
    or lambdas - those get their own independent scope."""

    def __init__(self):
        self.locals: set[str] = set()
        self.globals_declared: set[str] = set()
        self.nonlocals_declared: set[str] = set()

    # stop at nested scopes
    def visit_FunctionDef(self, node):
        return

    def visit_AsyncFunctionDef(self, node):
        return

    def visit_ClassDef(self, node):
        return

    def visit_Lambda(self, node):
        return

    def visit_Global(self, node: ast.Global):
        self.globals_declared.update(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal):
        self.nonlocals_declared.update(node.names)

    def visit_Name(self, node: ast.Name):
        if isinstance(node.ctx, ast.Store):
            self.locals.add(node.id)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        if node.name:
            self.locals.add(node.name)
        self.generic_visit(node)

    def visit_NamedExpr(self, node):  # walrus operator :=
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
    """Collects every name that appears in ANY global/nonlocal statement
    anywhere in the module. A variable referenced via nonlocal/global from
    one function is bound in a *different* function's scope than the one
    that sees the declaration, so it can't be safely renamed by a purely
    local, per-scope pass - we exclude these names from renaming everywhere
    to guarantee correctness."""

    def __init__(self):
        self.names: set[str] = set()

    def visit_Global(self, node: ast.Global):
        self.names.update(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal):
        self.names.update(node.names)


class Renamer(ast.NodeTransformer):
    """Scope-aware renamer for function-local variables and parameters.
    Module-level names, class attributes, function/class names themselves,
    imported names, and any name touched by global/nonlocal are always left
    untouched."""

    def __init__(self, style: str, length: int, protected: set | None = None):
        self.style = style
        self.length = length
        self.protected = protected or set()
        # stack of dict: original name -> new name (module scope = empty dict)
        self.stack: list[dict] = [{}]

    def _push_scope(self, node) -> dict:
        collector = ScopeCollector()
        for stmt in node.body:
            collector.visit(stmt)
        params = _collect_params(node.args) if hasattr(node, "args") else set()
        # Parameter names are part of the function's calling convention: any
        # caller elsewhere in the codebase may invoke it with keyword
        # arguments (f(a=..., b=...)), so renaming them would silently break
        # those call sites. We only rename names that are purely local to
        # the function body and never appear as a parameter.
        candidates = collector.locals - params - collector.globals_declared - collector.nonlocals_declared
        candidates = {n for n in candidates if not DUNDER(n) and n not in self.protected}
        mapping = {}
        used_new = set()
        for n in sorted(candidates):
            new = _rand_name(used_new, self.style, self.length)
            mapping[n] = new
            used_new.add(new)
        self.stack.append(mapping)
        return mapping

    def _pop_scope(self):
        self.stack.pop()

    def _lookup(self, name: str):
        # search innermost -> outermost so parameters/locals shadow correctly;
        # a name only renames if it was bound in that specific scope.
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
        # decorators & default values evaluate in the ENCLOSING scope
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

    def visit_FunctionDef(self, node):
        return self._visit_function(node)

    def visit_AsyncFunctionDef(self, node):
        return self._visit_function(node)

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
        # class body is its own namespace (attribute names must stay as-is);
        # only descend into methods, whose own scopes are independently safe.
        node.bases = [self.visit(b) for b in node.bases]
        node.decorator_list = [self.visit(d) for d in node.decorator_list]
        new_body = []
        for stmt in node.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                new_body.append(self.visit(stmt))
            else:
                new_body.append(stmt)  # leave class-level attrs untouched
        node.body = new_body
        return node

    # Attribute access (obj.attr) - never rename the attribute part, only
    # the object expression if it's a renameable Name.
    def visit_Attribute(self, node: ast.Attribute):
        node.value = self.visit(node.value)
        return node

    # dict/keyword-argument keys must not be renamed
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
    """Replaces plain string constants with a base64-decode expression,
    e.g. "hi" -> __pyobf_d('aGk=').  Skips docstring position(0) exprs,
    f-strings, bytes, and non-string constants."""

    def __init__(self):
        self.count = 0

    def _is_docstring_slot(self, parent_body, node):
        return parent_body and parent_body[0] is node

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
        for stmt in body:
            self.generic_visit(stmt)

    def visit_JoinedStr(self, node: ast.JoinedStr):
        # f-strings: only encode the *expression* parts, never the literal
        # text segments (those are plain ast.Constant chunks that ast.unparse
        # requires to stay as raw Constant nodes inside a JoinedStr).
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
            encoded = base64.b64encode(node.value.encode("utf-8")).decode("ascii")
            self.count += 1
            call = ast.Call(
                func=ast.Name(id="__pyobf_d", ctx=ast.Load()),
                args=[ast.Constant(value=encoded)],
                keywords=[],
            )
            return ast.copy_location(call, node)
        return node


DECODE_HELPER = (
    "import base64 as __pyobf_b64\n"
    "def __pyobf_d(__s):\n"
    "    return __pyobf_b64.b64decode(__s.encode('ascii')).decode('utf-8')\n"
)


def _compact_indent(source: str, indent: int) -> str:
    if indent == 4:
        return source
    out_lines = []
    for line in source.split("\n"):
        stripped = line.lstrip(" ")
        depth4 = len(line) - len(stripped)
        depth = depth4 // 4
        out_lines.append((" " * indent * depth) + stripped)
    return "\n".join(out_lines)


def wrap_as_payload(code: str, reverse: bool = True, compress_level: int = 9) -> str:
    """Compresses the whole source with zlib, base64-encodes it (optionally
    reversing the string for an extra cosmetic layer), and emits a single
    line that decompresses and exec()s it at runtime - the same style used
    by tools like the referenced obf.eooce.com."""
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
    """
    options:
      rename_locals: bool
      strip_docstrings: bool
      encode_strings: bool
      compact_indent: bool
      name_style: "hex" | "letters" | "il1"
      name_length: int (4-16)
      seed: int | None
      payload_mode: bool   - wrap the whole result as a single-line
                             zlib+base64 exec() bootstrap (strongest,
                             least readable; matches the "obf.eooce.com"
                             style). Applied last, after everything else.
      payload_reverse: bool - also reverse the base64 string as a cheap
                             extra cosmetic layer (default True)
    """
    warnings = []
    opts = {
        "rename_locals": True,
        "strip_docstrings": True,
        "encode_strings": False,
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

    if opts["rename_locals"]:
        scanner = DynamicUsageScanner()
        scanner.visit(tree)
        if scanner.found:
            warnings.append(
                "Detected dynamic name access (%s); identifier renaming was "
                "skipped to avoid breaking the program." % ", ".join(sorted(scanner.reasons))
            )
        else:
            protected_scanner = ProtectedNameScanner()
            protected_scanner.visit(tree)
            tree = Renamer(
                opts["name_style"], int(opts["name_length"]), protected_scanner.names
            ).visit(tree)
            ast.fix_missing_locations(tree)

    if opts["strip_docstrings"]:
        tree = DocstringStripper().visit(tree)
        ast.fix_missing_locations(tree)

    string_count = 0
    if opts["encode_strings"]:
        encoder = StringEncoder()
        tree = encoder.visit(tree)
        ast.fix_missing_locations(tree)
        string_count = encoder.count

    result = ast.unparse(tree)

    if opts["encode_strings"] and string_count > 0:
        result = DECODE_HELPER + "\n" + result

    if opts["compact_indent"]:
        result = _compact_indent(result, 1)

    if opts["payload_mode"]:
        result = wrap_as_payload(result, reverse=bool(opts["payload_reverse"]))

    # Comments and blank-line noise are removed automatically because
    # ast.unparse regenerates source purely from the AST (comments are not
    # part of the AST at all).
    return {
        "code": result,
        "warnings": warnings,
        "original_size": len(source.encode("utf-8")),
        "obfuscated_size": len(result.encode("utf-8")),
    }


def safe_obfuscate(source: str, options: dict) -> dict:
    """Boundary-safe wrapper for the JS <-> Pyodide bridge: never raises,
    always returns a JSON-serialisable dict, with an 'error' key on failure."""
    try:
        return obfuscate(source, options)
    except SyntaxError as e:
        return {"error": "语法错误 SyntaxError: %s (line %s, col %s)" % (e.msg, e.lineno, e.offset)}
    except RecursionError:
        return {"error": "代码过大/嵌套过深，无法处理 (RecursionError)"}
    except Exception as e:  # noqa: BLE001 - deliberate catch-all at the JS boundary
        return {"error": "%s: %s" % (type(e).__name__, e)}
