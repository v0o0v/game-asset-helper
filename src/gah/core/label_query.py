"""M4 — 자연어 라벨 부울 파서 (label_query → ParsedLabelQuery).

문법 (EBNF 근접):

    expr     = or_expr
    or_expr  = and_expr ('OR' and_expr)*
    and_expr = not_expr (('AND' | implicit_and) not_expr)*
    not_expr = 'NOT'? atom
    atom     = '(' or_expr ')'
             | axis_label
             | bare_label
             | free_token
    axis_label = IDENT ':' IDENT
    bare_label = IDENT
    free_token = QUOTED_STRING | TOKEN

키워드 `AND`/`OR`/`NOT` 은 **대문자 전체 일치** 만 (사용자가 ``and`` 를 라벨로
쓸 가능성 보호).  bare label 은 LabelRegistry 에서 axis 자동 매칭 — 같은 token
이 여러 axis 에 있으면 ``AmbiguousLabel`` 예외 (후보 axis 동봉).  미지 토큰은
``free_text`` 로 분리 (semantic 쿼리로 흐름).

DNF 정규화 — 순수 AND (또는 NOT 만 추가) → ``labels_all`` / ``labels_none``,
순수 OR (또는 NOT 추가) → ``labels_any`` / ``labels_none``.  AND/OR 혼합은 v1
한계라 ``UnsupportedExpression``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


# ── 데이터클래스 + 예외 ──────────────────────────────────────────────


@dataclass(frozen=True)
class LabelFilter:
    """label_query 결과의 단일 라벨 (search.LabelFilter 와 별개 — 순환 회피)."""
    axis: str
    label: str


@dataclass(frozen=True)
class ParsedLabelQuery:
    labels_all: list[LabelFilter] = field(default_factory=list)
    labels_any: list[LabelFilter] = field(default_factory=list)
    labels_none: list[LabelFilter] = field(default_factory=list)
    free_text: str = ""
    original_expr: str = ""


class LabelQueryError(ValueError):
    """파서 베이스 예외."""


class AmbiguousLabel(LabelQueryError):
    def __init__(self, label: str, candidates: list[str]) -> None:
        super().__init__(
            f"라벨 '{label}' 모호 — 가능한 axis: {', '.join(candidates)}",
        )
        self.label = label
        self.candidates = list(candidates)


class UnsupportedExpression(LabelQueryError):
    """v1 한계 — 순수 AND 또는 순수 OR 만 정확 매핑.  혼합은 미지원."""


# ── Registry 인터페이스 (Protocol) ───────────────────────────────────


@runtime_checkable
class _RegistryLike(Protocol):
    def list_labels(self, axis=None, *, enabled_only: bool = True,
                    with_description: bool = False): ...

    def list_axes(self) -> list[str]: ...


# ── 토크나이저 ───────────────────────────────────────────────────────


_KEYWORDS = {"AND", "OR", "NOT"}


@dataclass(frozen=True)
class _Token:
    text: str
    kind: str   # 'LPAREN'/'RPAREN'/'AND'/'OR'/'NOT'/'AXIS_LABEL'/'LABEL'/'FREE'


def _tokenize(text: str, registry: _RegistryLike) -> list[_Token]:
    """공백 + 따옴표 + 괄호 분리 → 분류 (registry 매칭).

    - "..." 따옴표 안 내용은 단일 FREE 토큰.
    - `(` / `)` 단독 토큰.
    - 그 외 — 공백 분리. `AXIS:LABEL` 매칭 우선 → `LABEL` (등록된 token) 또는
      `FREE` (미지).
    """
    out: list[_Token] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if c == "(":
            out.append(_Token("(", "LPAREN"))
            i += 1
            continue
        if c == ")":
            out.append(_Token(")", "RPAREN"))
            i += 1
            continue
        if c == '"':
            # 따옴표 안 내용을 단일 FREE 토큰.
            end = text.find('"', i + 1)
            if end == -1:
                # 닫는 따옴표 없으면 그냥 끝까지 잡는다.
                end = n
            inner = text[i + 1: end]
            out.append(_Token(inner, "FREE"))
            i = end + 1
            continue
        # 일반 토큰 — 공백/괄호/따옴표 만나기 전까지.
        m = re.match(r'[^\s()"]+', text[i:])
        if not m:
            i += 1
            continue
        tok = m.group(0)
        i += len(tok)
        # 분류
        if tok in _KEYWORDS:
            out.append(_Token(tok, tok))
            continue
        if ":" in tok:
            axis, label = tok.split(":", 1)
            if axis and label:
                out.append(_Token(tok, "AXIS_LABEL"))
                continue
        # bare label → LabelRegistry 매칭
        out.append(_Token(tok, "LABEL"))
    return out


# ── 분류기 (LABEL → axis 매핑) ───────────────────────────────────────


def _axes_for_label(registry: _RegistryLike, label: str) -> list[str]:
    """label token 이 등록된 axis 들 — 동일 token 중복 가능."""
    out: list[str] = []
    for ax in registry.list_axes():
        if label in registry.list_labels(axis=ax, enabled_only=True):
            out.append(ax)
    return sorted(out)


# ── AST + 재귀하강 파서 ─────────────────────────────────────────────


@dataclass(frozen=True)
class _AtomNode:
    label: LabelFilter


@dataclass(frozen=True)
class _NotNode:
    child: "_Node"


@dataclass(frozen=True)
class _AndNode:
    children: tuple["_Node", ...]


@dataclass(frozen=True)
class _OrNode:
    children: tuple["_Node", ...]


_Node = _AtomNode | _NotNode | _AndNode | _OrNode  # type: ignore[name-defined]


class _Parser:
    def __init__(self, tokens: list[_Token], registry: _RegistryLike) -> None:
        self.tokens = tokens
        self.pos = 0
        self.registry = registry
        # 파싱 중 누적되는 free_text 토큰.
        self.free_tokens: list[str] = []

    def _peek(self) -> _Token | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _consume(self) -> _Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def _eat(self, kind: str) -> _Token | None:
        tok = self._peek()
        if tok is not None and tok.kind == kind:
            self.pos += 1
            return tok
        return None

    # -- atom ---------------------------------------------------------

    def parse_atom(self) -> _Node | None:
        tok = self._peek()
        if tok is None:
            return None
        if tok.kind == "LPAREN":
            self._consume()
            inner = self.parse_or()
            if self._eat("RPAREN") is None:
                # unclosed paren — 허용 (tolerant).
                pass
            return inner
        if tok.kind == "AXIS_LABEL":
            self._consume()
            axis, label = tok.text.split(":", 1)
            return _AtomNode(LabelFilter(axis=axis, label=label))
        if tok.kind == "LABEL":
            self._consume()
            # registry 에서 axis 자동 매칭
            axes = _axes_for_label(self.registry, tok.text)
            if len(axes) == 1:
                return _AtomNode(LabelFilter(axis=axes[0], label=tok.text))
            if len(axes) >= 2:
                raise AmbiguousLabel(tok.text, axes)
            # 0 → 미지 토큰 → free_text
            self.free_tokens.append(tok.text)
            return None
        if tok.kind == "FREE":
            self._consume()
            self.free_tokens.append(tok.text)
            return None
        # 키워드를 atom 위치에서 만나면 — 잘못된 위치, 그냥 consume + 무시.
        if tok.kind in _KEYWORDS:
            self._consume()
            return None
        # 알 수 없는 토큰 — consume + 무시.
        self._consume()
        return None

    # -- NOT ----------------------------------------------------------

    def parse_not(self) -> _Node | None:
        tok = self._peek()
        if tok is not None and tok.kind == "NOT":
            self._consume()
            inner = self.parse_atom()
            if inner is None:
                return None
            return _NotNode(inner)
        return self.parse_atom()

    # -- AND ----------------------------------------------------------

    def parse_and(self) -> _Node | None:
        left = self.parse_not()
        children: list[_Node] = []
        if left is not None:
            children.append(left)
        while True:
            tok = self._peek()
            if tok is None:
                break
            if tok.kind == "AND":
                self._consume()
                right = self.parse_not()
                if right is not None:
                    children.append(right)
                continue
            if tok.kind == "OR" or tok.kind == "RPAREN":
                break
            # implicit AND — 다음 토큰이 atom-like 이면 묵시 AND.
            if tok.kind in ("LPAREN", "AXIS_LABEL", "LABEL", "FREE", "NOT"):
                right = self.parse_not()
                if right is not None:
                    children.append(right)
                continue
            # 알 수 없는 토큰 — 더 못 진행.
            break
        if not children:
            return None
        if len(children) == 1:
            return children[0]
        return _AndNode(tuple(children))

    # -- OR -----------------------------------------------------------

    def parse_or(self) -> _Node | None:
        left = self.parse_and()
        children: list[_Node] = []
        if left is not None:
            children.append(left)
        while True:
            tok = self._peek()
            if tok is None or tok.kind != "OR":
                break
            self._consume()
            right = self.parse_and()
            if right is not None:
                children.append(right)
        if not children:
            return None
        if len(children) == 1:
            return children[0]
        return _OrNode(tuple(children))


# ── DNF 정규화 ───────────────────────────────────────────────────────


def _is_pure_and(node: _Node) -> bool:
    """노드가 AtomNode/NotNode(AtomNode)/AndNode(of those) 인지 검사."""
    if isinstance(node, _AtomNode):
        return True
    if isinstance(node, _NotNode):
        return isinstance(node.child, _AtomNode)
    if isinstance(node, _AndNode):
        return all(_is_pure_and(c) for c in node.children)
    return False


def _is_pure_or(node: _Node) -> bool:
    """노드가 AtomNode/NotNode(AtomNode)/OrNode(of those) 인지 검사 (AND 없이)."""
    if isinstance(node, _AtomNode):
        return True
    if isinstance(node, _NotNode):
        return isinstance(node.child, _AtomNode)
    if isinstance(node, _OrNode):
        return all(_is_pure_or(c) for c in node.children)
    return False


def _flatten_and(node: _Node) -> tuple[list[LabelFilter], list[LabelFilter]]:
    """순수 AND 트리 → (positive, negative) 리스트."""
    pos: list[LabelFilter] = []
    neg: list[LabelFilter] = []
    if isinstance(node, _AtomNode):
        pos.append(node.label)
    elif isinstance(node, _NotNode) and isinstance(node.child, _AtomNode):
        neg.append(node.child.label)
    elif isinstance(node, _AndNode):
        for c in node.children:
            p, n = _flatten_and(c)
            pos.extend(p)
            neg.extend(n)
    return pos, neg


def _flatten_or(node: _Node) -> tuple[list[LabelFilter], list[LabelFilter]]:
    """순수 OR 트리 → (positive any, negative none)."""
    pos: list[LabelFilter] = []
    neg: list[LabelFilter] = []
    if isinstance(node, _AtomNode):
        pos.append(node.label)
    elif isinstance(node, _NotNode) and isinstance(node.child, _AtomNode):
        neg.append(node.child.label)
    elif isinstance(node, _OrNode):
        for c in node.children:
            p, n = _flatten_or(c)
            pos.extend(p)
            neg.extend(n)
    return pos, neg


def _map_ast(node: _Node) -> tuple[list[LabelFilter], list[LabelFilter], list[LabelFilter]]:
    """AST → (labels_all, labels_any, labels_none).

    v1 한계 — 순수 AND 트리 또는 순수 OR 트리만 정확 매핑.  AND/OR 혼합은
    ``UnsupportedExpression``.
    """
    if _is_pure_and(node):
        pos, neg = _flatten_and(node)
        return pos, [], neg
    if _is_pure_or(node):
        pos, neg = _flatten_or(node)
        return [], pos, neg
    raise UnsupportedExpression(
        "v1 한계 — 순수 AND 또는 순수 OR 표현만 지원합니다 "
        "(예: 'a AND b AND NOT c' 또는 'a OR b OR NOT c'). "
        "혼합 (AND/OR 동시) 은 미지원."
    )


# ── 공개 API ─────────────────────────────────────────────────────────


def parse_label_query(text: str, registry: _RegistryLike) -> ParsedLabelQuery:
    """`text` → `ParsedLabelQuery` (labels_all/any/none + free_text).

    빈 입력 또는 라벨 0개 → 빈 ParsedLabelQuery (free_text = text 잔여).
    """
    original = text or ""
    if not original.strip():
        return ParsedLabelQuery(original_expr=original)

    tokens = _tokenize(original, registry)
    parser = _Parser(tokens, registry)
    ast = parser.parse_or()
    free_text = " ".join(parser.free_tokens).strip()

    if ast is None:
        return ParsedLabelQuery(free_text=free_text, original_expr=original)

    labels_all, labels_any, labels_none = _map_ast(ast)
    return ParsedLabelQuery(
        labels_all=labels_all,
        labels_any=labels_any,
        labels_none=labels_none,
        free_text=free_text,
        original_expr=original,
    )
