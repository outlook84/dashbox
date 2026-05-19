from dashbox import i18n
from dashbox.adapters import client_text
from dashbox.core.client_model import ClientItem


def test_subtitle_renders_explicit_zero_item_count() -> None:
    item = ClientItem("empty", "Empty", subtitle_key="item_count", item_count=0)

    assert client_text.subtitle(item) == i18n.item_count(0)
