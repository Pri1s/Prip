"""Source-level mutation operators for single-module Verilog-2005 designs.

Each operator finds sites in the golden RTL's syntax tree (pyslang) and proposes a Mutation:
replace one byte span of the golden text with new text. Everything outside the span stays
byte-identical, so the answer key (where the bug is, and the exact edit that undoes it) is exact.

Operators are grouped by VeriBugBench family (Expression, Bit-vector & access, Assignment).
Not generated: clock-edge flips (Timing; the grader can't compare circuits clocked on different
edges) and port changes (Port; they change the interface, so there is no miter to filter with).
"""

import hashlib
import random
import re
from dataclasses import dataclass

from pyslang.syntax import SyntaxTree

FAMILY = {
    "arith_swap": "Expression", "relational_swap": "Expression", "logic_swap": "Expression",
    "shift_swap": "Expression", "negation_drop": "Expression", "negation_insert": "Expression",
    "unary_minus_drop": "Expression", "constant_change": "Expression", "ternary_swap": "Expression",
    "wrong_signal": "Expression",
    "bit_index_shift": "Bit-vector & access", "part_select_shift": "Bit-vector & access",
    "concat_swap": "Bit-vector & access", "decl_width_shrink": "Bit-vector & access",
    "stmt_delete": "Assignment", "branch_delete": "Assignment", "elseif_arm_delete": "Assignment",
    "case_item_delete": "Assignment", "nb_to_blocking": "Assignment", "blocking_to_nb": "Assignment",
}

# Binary operator kind -> replacement operators.
SWAPS = {
    "AddExpression": ("arith_swap", ["-"]),
    "SubtractExpression": ("arith_swap", ["+"]),
    "LessThanExpression": ("relational_swap", ["<=", ">"]),
    "LessThanEqualExpression": ("relational_swap", ["<", ">="]),
    "GreaterThanExpression": ("relational_swap", [">=", "<"]),
    "GreaterThanEqualExpression": ("relational_swap", [">", "<="]),
    "EqualityExpression": ("relational_swap", ["!="]),
    "InequalityExpression": ("relational_swap", ["=="]),
    "LogicalAndExpression": ("logic_swap", ["||"]),
    "LogicalOrExpression": ("logic_swap", ["&&"]),
    "BinaryAndExpression": ("logic_swap", ["|", "^"]),
    "BinaryOrExpression": ("logic_swap", ["&", "^"]),
    "BinaryXorExpression": ("logic_swap", ["|", "~^"]),
    "BinaryXnorExpression": ("logic_swap", ["^"]),
    "LogicalShiftLeftExpression": ("shift_swap", [">>"]),
    "LogicalShiftRightExpression": ("shift_swap", ["<<", ">>>"]),
    "ArithmeticShiftRightExpression": ("shift_swap", [">>"]),
}
NEGATIONS = {"UnaryLogicalNotExpression", "UnaryBitwiseNotExpression"}
DECLS = {"DataDeclaration", "NetDeclaration"}
# Nodes whose line range is reported as the "enclosing block" of an edit.
SCOPES = {"SequentialBlockStatement", "ConditionalStatement", "CaseStatement", "AlwaysBlock",
          "ContinuousAssign", "DataDeclaration", "NetDeclaration", "ParameterDeclarationStatement",
          "StandardCaseItem", "DefaultCaseItem"}
WRONG_SIGNAL_PER_SITE = 2


@dataclass(frozen=True)
class Mutation:
    operator: str
    start: int          # golden byte span replaced
    end: int
    replacement: str
    scope: tuple        # (start, end) golden span of the enclosing block
    note: str           # e.g. "'<' -> '<='"

    @property
    def family(self) -> str:
        return FAMILY[self.operator]

    @property
    def is_deletion(self) -> bool:
        return self.replacement == ""

    def apply(self, text: str) -> str:
        return text[:self.start] + self.replacement + text[self.end:]


def _span(x):
    """Byte span of a syntax node or token (tokens exclude their leading whitespace/comments)."""
    r = x.sourceRange if hasattr(x, "sourceRange") else x.range
    return r.start.offset, r.end.offset


def _nodes(seq):
    """Child syntax nodes of a separated list (skips comma tokens)."""
    return [x for x in seq if x is not None and hasattr(x, "sourceRange")]


def _ancestors(n):
    p = n.parent
    while p is not None:
        yield p
        p = p.parent


def _int(tok_text: str):
    t = tok_text.strip().replace("_", "")
    return int(t) if t.isdigit() else None


class Design:
    """Parsed golden RTL plus the context the operators need (widths, block kinds)."""

    def __init__(self, text: str, name: str = "golden.v"):
        self.text = text
        self.tree = SyntaxTree.fromText(text, name)
        if self.tree.diagnostics:
            raise ValueError(f"{name}: parse diagnostics: {len(self.tree.diagnostics)}")
        self.nodes = []
        self.tree.root.visit(lambda n: self.nodes.append(n) if hasattr(n, "sourceRange") else None)
        self.signals: dict[str, tuple[int, int] | None] = {}   # name -> (msb, lsb), None = memory
        self.params: dict[str, int | None] = {}                # localparam name -> width
        self.ports: set[str] = set()
        self._collect_declarations()

    def src(self, n) -> str:
        s, e = _span(n)
        return self.text[s:e]

    # ---- declarations -------------------------------------------------------------------
    def _range_of(self, n):
        """(msb, lsb) of the first packed range under n, (0, 0) if none, None if not literal."""
        for d in self._descendants(n):
            if d.kind.name == "RangeDimensionSpecifier":
                sel = d.selector
                l, r = _int(self.src(sel.left)), _int(self.src(sel.right))
                return (l, r) if l is not None and r is not None else None
        return (0, 0)

    def _descendants(self, n):
        out = []
        n.visit(lambda x: out.append(x) if hasattr(x, "sourceRange") and x is not n else None)
        return out

    def _collect_declarations(self):
        for n in self.nodes:
            k = n.kind.name
            if k == "ImplicitAnsiPort":
                name = n.declarator.name.valueText
                self.ports.add(name)
                self.signals[name] = self._range_of(n.header)
            elif k in DECLS:
                # integer/time variables (loop counters) get no width, so no operator touches them.
                rng = None if self.src(n.type).split()[:1] in (["integer"], ["time"]) else self._range_of(n.type)
                for d in _nodes(n.declarators):
                    memory = len(list(_nodes(d.dimensions))) > 0
                    self.signals[d.name.valueText] = None if memory else rng
            elif k == "ParameterDeclaration":
                for d in _nodes(n.declarators):
                    expr = d.initializer.expr
                    width = _int(self.src(expr.size)) if expr.kind.name == "IntegerVectorExpression" else None
                    self.params[d.name.valueText] = width

    def width(self, name):
        if name in self.params:
            return self.params[name]
        r = self.signals.get(name)
        return None if r is None else abs(r[0] - r[1]) + 1

    # ---- context ------------------------------------------------------------------------
    def in_header(self, n):
        return any(a.kind.name == "ModuleHeader" for a in _ancestors(n))

    def in_decl_type(self, n):
        """Inside the type/range part of a declaration (not its initializer expression)."""
        for a in _ancestors(n):
            k = a.kind.name
            if k == "EqualsValueClause":
                return False
            if k in DECLS or k in ("ParameterDeclaration", "VariableDimension"):
                return True
        return False

    def in_event_control(self, n):
        return any(a.kind.name in ("EventControlWithExpression", "ImplicitEventControl") for a in _ancestors(n))

    def always_kind(self, n):
        """'clocked', 'comb', or None (not inside an always block)."""
        for a in _ancestors(n):
            if a.kind.name == "AlwaysBlock":
                return "clocked" if re.search(r"\b(posedge|negedge)\b", self.src(a).split("begin")[0]) else "comb"
        return None

    def is_lhs(self, n):
        s, _ = _span(n)
        for a in _ancestors(n):
            if a.kind.name in ("NonblockingAssignmentExpression", "AssignmentExpression"):
                ls, le = _span(a.left)
                if ls <= s < le:
                    return True
        return False

    def in_for_header(self, n):
        """Inside a for loop's init/condition/step (a mutation there can make the loop endless)."""
        s, _ = _span(n)
        for a in _ancestors(n):
            if a.kind.name == "ForLoopStatement":
                bs, be = _span(a.statement)
                if not bs <= s < be:
                    return True
        return False

    def in_select_index(self, n):
        return any(a.kind.name == "ElementSelect" for a in _ancestors(n))

    def scope(self, n, strict=False):
        """Span of the nearest enclosing block-like construct (n itself counts unless strict)."""
        for a in ([] if strict else [n]) + list(_ancestors(n)):
            if a.kind.name in SCOPES:
                return _span(a)
        return _span(n)

    def reset_registers(self, reset_port: str) -> set[str]:
        """Registers assigned in an `if (<reset>)` branch of a clocked always block."""
        regs = set()
        for n in self.nodes:
            if n.kind.name == "ConditionalStatement" and self.always_kind(n) == "clocked":
                if self.src(n.predicate).strip() == reset_port:
                    for d in [n.statement] + self._descendants(n.statement):
                        if d.kind.name == "NonblockingAssignmentExpression":
                            regs.add(re.split(r"[\s\[]", self.src(d.left).strip())[0])
        return regs

    # ---- deletion spans -----------------------------------------------------------------
    def deletion_span(self, s, e):
        """Whole lines if the construct sits alone on its lines (a trailing // comment goes
        too), else just the construct plus the spaces after it."""
        t = self.text
        ls = t.rfind("\n", 0, s) + 1
        le = t.find("\n", e)
        le = len(t) if le < 0 else le
        before, after = t[ls:s], t[e:le]
        if not before.strip() and (not after.strip() or after.strip().startswith("//")):
            return ls, min(le + 1, len(t))
        while e < len(t) and t[e] in " \t":
            e += 1
        return s, e


def _fmt_like(original_value: str, base: str, value: int) -> str:
    """Formats value in the literal's base, zero-padded to the original digit count."""
    digits = {"d": str(value), "h": format(value, "x"), "b": format(value, "b"), "o": format(value, "o")}[base]
    if base != "d" or original_value.startswith("0"):
        digits = digits.rjust(len(original_value.replace("_", "")), "0")
    if any(c.isupper() for c in original_value):
        digits = digits.upper()
    return digits


def enumerate_mutations(d: Design, seed_key: str = "") -> list[Mutation]:
    muts: list[Mutation] = []
    seen = set()

    def add(op, s, e, rep, scope, note):
        if d.text[s:e] == rep:
            return
        m = Mutation(op, s, e, rep, scope, note)
        result = m.apply(d.text)
        if result in seen:
            return
        seen.add(result)
        muts.append(m)

    for n in d.nodes:
        k = n.kind.name
        if d.in_header(n) or d.in_for_header(n):
            continue
        scope = d.scope(n)

        # ---- Expression ----
        if k in SWAPS and not d.in_decl_type(n):
            op, reps = SWAPS[k]
            s, e = _span(n.operatorToken)
            for r in reps:
                add(op, s, e, r, scope, f"'{d.text[s:e]}' -> '{r}'")
        elif k in NEGATIONS:
            s, e = _span(n)
            add("negation_drop", s, e, d.src(n.operand), scope, f"drop '{d.text[s:s + 1]}'")
        elif k == "UnaryMinusExpression":
            s, e = _span(n)
            add("unary_minus_drop", s, e, d.src(n.operand), scope, "drop unary '-'")
        elif k == "ConditionalExpression":
            s, e = _span(n)
            pred, left, right = d.src(n.predicate), d.src(n.left), d.src(n.right)
            add("ternary_swap", s, e, f"{pred} ? {right} : {left}", scope, "swap ?: arms")
            ps, pe = _span(n.predicate)
            add("negation_insert", ps, pe, f"!({pred.strip()})", scope, "negate ?: condition")
        elif k == "ConditionalStatement":
            ps, pe = _span(n.predicate)
            add("negation_insert", ps, pe, f"!({d.src(n.predicate).strip()})", scope, "negate if condition")
        elif k == "IntegerVectorExpression" and not d.in_decl_type(n) and not d.in_select_index(n):
            size = _int(d.src(n.size))
            base_txt = d.src(n.base).strip()
            base = base_txt[-1].lower()
            raw = d.src(n.value).strip()
            try:
                v = int(raw.replace("_", ""), {"d": 10, "h": 16, "b": 2, "o": 8}[base])
            except ValueError:
                continue   # x/z digits
            if size is None:
                continue
            s, e = _span(n.value)
            for nv in (v + 1, v - 1):
                if 0 <= nv < 2 ** size:
                    add("constant_change", s, e, _fmt_like(raw, base, nv), scope, f"{size}'{base}{raw} -> {nv}")
        elif k == "IntegerLiteralExpression" and not d.in_decl_type(n) and not d.in_select_index(n):
            v = _int(d.src(n))
            if v is None:
                continue
            s, e = _span(n)
            for nv in (v + 1, v - 1):
                if nv >= 0:
                    add("constant_change", s, e, str(nv), scope, f"{v} -> {nv}")
        elif k == "IdentifierName" and not d.in_decl_type(n) and not d.in_event_control(n) and not d.is_lhs(n):
            name = n.identifier.valueText
            pool = d.params if name in d.params else d.signals
            w = d.width(name)
            if w is None or name not in pool:
                continue
            alts = sorted(o for o in pool if o != name and d.width(o) == w and o not in ("clk",))
            s, e = _span(n)
            rng = random.Random(hashlib.sha256(f"{seed_key}:{s}".encode()).hexdigest())
            for o in rng.sample(alts, min(WRONG_SIGNAL_PER_SITE, len(alts))):
                add("wrong_signal", s, e, o, scope, f"{name} -> {o}")

        # ---- Bit-vector & access ----
        elif k == "ElementSelect" and not d.in_decl_type(n):
            parent = n.parent
            if parent is None or parent.kind.name != "IdentifierSelectName":
                continue
            rng_ = d.signals.get(parent.identifier.valueText)
            if not rng_:
                continue
            lo, hi = min(rng_), max(rng_)
            sel = n.selector
            if sel.kind.name == "BitSelect":
                i = _int(d.src(sel.expr))
                if i is None:
                    continue
                s, e = _span(sel.expr)
                for ni in (i + 1, i - 1):
                    if lo <= ni <= hi:
                        add("bit_index_shift", s, e, str(ni), scope, f"[{i}] -> [{ni}]")
            elif sel.kind.name == "SimpleRangeSelect":
                m, l = _int(d.src(sel.left)), _int(d.src(sel.right))
                if m is None or l is None:
                    continue
                s, e = _span(sel)
                for dlt in (1, -1):
                    if lo <= min(m, l) + dlt and max(m, l) + dlt <= hi:
                        add("part_select_shift", s, e, f"{m + dlt}:{l + dlt}", scope, f"[{m}:{l}] -> [{m + dlt}:{l + dlt}]")
        elif k == "ConcatenationExpression":
            parts = _nodes(n.expressions)
            for a, b in list(zip(parts, parts[1:]))[:3]:
                s, _ = _span(a)
                _, e = _span(b)
                add("concat_swap", s, e, f"{d.src(b)}{d.text[_span(a)[1]:_span(b)[0]]}{d.src(a)}", scope,
                    f"swap {d.src(a).strip()} and {d.src(b).strip()}")
        elif k in DECLS:
            for dd in d._descendants(n.type):
                if dd.kind.name == "RangeDimensionSpecifier":
                    m, l = _int(d.src(dd.selector.left)), _int(d.src(dd.selector.right))
                    if m is not None and l == 0 and m >= 1:
                        s, e = _span(dd.selector.left)
                        add("decl_width_shrink", s, e, str(m - 1), scope, f"[{m}:0] -> [{m - 1}:0]")
                    break

        # ---- Assignment ----
        # Only statements inside begin/end: deleting the sole statement of an if/case arm leaves
        # a syntax error (whole missing branches come from the branch/arm deletes).
        if k == "ExpressionStatement" and d.always_kind(n) is not None and \
                n.parent.kind.name == "SequentialBlockStatement" and \
                n.expr.kind.name in ("NonblockingAssignmentExpression", "AssignmentExpression"):
            s, e = d.deletion_span(*_span(n))
            add("stmt_delete", s, e, "", d.scope(n, strict=True), f"delete '{d.src(n).strip()}'")
        if k == "ConditionalStatement" and n.elseClause is not None:
            clause = n.elseClause.clause
            if clause.kind.name != "ConditionalStatement" or clause.elseClause is None:
                _, ts = _span(n.statement)
                _, ee = _span(n.elseClause)
                add("branch_delete", ts, ee, "", scope, "delete final else branch")
            if n.parent is not None and n.parent.kind.name == "ElseClause":
                s, e = _span(n)
                add("elseif_arm_delete", s, e, d.src(n.elseClause.clause), d.scope(n, strict=True),
                    f"delete 'else if ({d.src(n.predicate).strip()})' arm")
        if k in ("StandardCaseItem", "DefaultCaseItem"):
            s, e = d.deletion_span(*_span(n))
            add("case_item_delete", s, e, "", d.scope(n, strict=True), f"delete case item '{d.src(n).split(':')[0].strip()}'")
        is_stmt = n.parent is not None and n.parent.kind.name == "ExpressionStatement"
        if k == "NonblockingAssignmentExpression" and is_stmt and d.always_kind(n) == "clocked":
            s, e = _span(n.operatorToken)
            add("nb_to_blocking", s, e, "=", scope, "'<=' -> '='")
        if k == "AssignmentExpression" and is_stmt and d.always_kind(n) == "comb":
            s, e = _span(n.operatorToken)
            add("blocking_to_nb", s, e, "<=", scope, "'=' -> '<='")
    return muts


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def localization(golden: str, m: Mutation) -> dict:
    """Where the bug is, in golden and buggy line numbers (1-based)."""
    buggy = m.apply(golden)
    shift = len(m.replacement) - (m.end - m.start)

    def to_buggy(off):
        return off if off <= m.start else off + shift

    out = {"golden_lines": [line_of(golden, m.start), line_of(golden, max(m.start, m.end - 1))]}
    if m.is_deletion:
        out["buggy_lines"] = []
        out["missing_at_line"] = line_of(buggy, m.start)   # deleted code belonged just before this point
    else:
        end = m.start + len(m.replacement)
        out["buggy_lines"] = [line_of(buggy, m.start), line_of(buggy, max(m.start, end - 1))]
    s, e = m.scope
    out["enclosing_lines"] = [line_of(buggy, to_buggy(s)), line_of(buggy, max(to_buggy(s), to_buggy(e) - 1))]
    return out
