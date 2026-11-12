"""A small HTML allowlist shared by the native editor and submission client."""
from __future__ import annotations

from html import escape
from html.parser import HTMLParser
import re
from urllib.parse import urlsplit


class CleanHTML(HTMLParser):
    tags = {"p", "div", "span", "br", "b", "strong", "i", "em", "u", "s", "ul", "ol", "li", "a", "img", "pre", "code", "blockquote", "table", "tbody", "tr", "td", "th", "h1", "h2", "h3", "h4", "hr", "sub", "sup"}
    void = {"img", "br", "hr"}

    def __init__(self, *, preserve_qt_empty=True):
        super().__init__(convert_charrefs=True)
        self.output = []
        self.skip = 0
        self.preserve_qt_empty = preserve_qt_empty

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "head", "iframe", "object", "svg"}:
            self.skip += 1
            return
        if self.skip or tag not in self.tags:
            return
        safe = []
        for key, value in attrs:
            if value is None:
                continue
            if key == "style":
                styles = []
                for declaration in value.split(";"):
                    name, _, setting = declaration.partition(":")
                    # Qt serializes an empty paragraph with <br> plus this
                    # marker. Dropping it turns an empty block into a literal
                    # line break on restore, making blank drafts nonempty and
                    # inserting extra newlines between real answer paragraphs.
                    if self.preserve_qt_empty and tag == "p" and name.strip().lower() == "-qt-paragraph-type" and setting.strip().lower() == "empty":
                        styles.append("-qt-paragraph-type:empty")
                    elif name.strip().lower() in {"font-weight", "font-style", "text-decoration", "text-align", "color", "background-color", "font-size", "white-space"} and re.fullmatch(r"[\w\s#.,()%+-]+", setting):
                        styles.append(name.strip() + ":" + setting.strip())
                if styles:
                    safe.append((key, ";".join(styles)))
            elif (tag, key) in {("a", "href"), ("img", "src")}:
                scheme = urlsplit(value).scheme.lower()
                if scheme in {"https", "http"} or value.startswith("/") and not value.startswith("//") or tag == "img" and re.match(r"^data:image/(png|jpeg|gif|webp);base64,[A-Za-z0-9+/=]+$", value):
                    safe.append((key, value))
            elif key in {"alt", "title"} or key in {"width", "height", "colspan", "rowspan"} and value.isdigit():
                safe.append((key, value))
        self.output.append("<" + tag + "".join(f' {key}="{escape(value, quote=True)}"' for key, value in safe) + ">")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.void:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in {"script", "style", "head", "iframe", "object", "svg"}:
            self.skip = max(0, self.skip - 1)
        elif not self.skip and tag in self.tags and tag not in self.void:
            self.output.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.skip:
            self.output.append(escape(data))


def clean_html(value, *, preserve_qt_empty=True):
    parser = CleanHTML(preserve_qt_empty=preserve_qt_empty)
    parser.feed(value or "")
    parser.close()
    return "".join(parser.output)


def _has_visible_content(cleaned):
    class VisibleContent(HTMLParser):
        meaningful = False

        def handle_data(self, data):
            if data.replace("\u200b", "").replace("\ufeff", "").strip():
                self.meaningful = True

        def handle_starttag(self, tag, attrs):
            if tag == "img" and dict(attrs).get("src"):
                self.meaningful = True
    probe = VisibleContent(convert_charrefs=True)
    probe.feed(cleaned)
    return probe.meaningful


def editor_html(value):
    """Restore visible answers while clearing legacy blank-only draft markup."""
    cleaned = clean_html(value)
    return cleaned if _has_visible_content(cleaned) else ""


def submission_html(value):
    """Send blank answers as empty comments and exclude private Qt styling."""
    cleaned = clean_html(value, preserve_qt_empty=False)
    return cleaned if _has_visible_content(cleaned) else ""
