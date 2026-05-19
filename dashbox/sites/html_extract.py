from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser


VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


@dataclass
class HtmlNode:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list["HtmlNode | str"] = field(default_factory=list)

    def attr(self, name: str) -> str:
        return self.attrs.get(name.lower(), "")

    def has_class(self, value: str) -> bool:
        return value in self.attr("class").split()

    def text(self) -> str:
        parts: list[str] = []
        for child in self.children:
            if isinstance(child, HtmlNode):
                parts.append(child.text())
            else:
                parts.append(child)
        return "".join(parts)

    def descendants(self, tag: str | None = None) -> list["HtmlNode"]:
        out: list[HtmlNode] = []
        wanted = tag.lower() if tag else None
        for child in self.children:
            if not isinstance(child, HtmlNode):
                continue
            if wanted is None or child.tag == wanted:
                out.append(child)
            out.extend(child.descendants(wanted))
        return out


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = HtmlNode("document")
        self._stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        node = HtmlNode(name, {key.lower(): value or "" for key, value in attrs})
        self._stack[-1].children.append(node)
        if name not in VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        node = HtmlNode(name, {key.lower(): value or "" for key, value in attrs})
        self._stack[-1].children.append(node)

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == name:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self._stack[-1].children.append(data)


def parse_html(value: str) -> HtmlNode:
    parser = _Parser()
    parser.feed(value)
    parser.close()
    return parser.root


def first_descendant(node: HtmlNode, tag: str, *, class_name: str = "") -> HtmlNode | None:
    for item in node.descendants(tag):
        if not class_name or item.has_class(class_name):
            return item
    return None
