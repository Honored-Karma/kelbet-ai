from string import Formatter

from kelbet.i18n import kk, ru
from kelbet.i18n.keys import Msg


def _message_keys() -> set[str]:
    return {
        value
        for name, value in vars(Msg).items()
        if name.isupper() and isinstance(value, str)
    }


def _placeholders(template: str) -> set[str]:
    return {
        field_name
        for _literal, field_name, _format_spec, _conversion in Formatter().parse(template)
        if field_name is not None
    }


def test_ru_and_kk_catalogs_cover_every_message_key() -> None:
    keys = _message_keys()

    assert keys - ru.TEXTS.keys() == set()
    assert keys - kk.TEXTS.keys() == set()


def test_localized_templates_use_the_same_placeholders() -> None:
    for key in _message_keys():
        assert _placeholders(ru.TEXTS[key]) == _placeholders(kk.TEXTS[key]), key
