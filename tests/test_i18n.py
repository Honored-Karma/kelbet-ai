from string import Formatter

from kelbet.domain.enums import Language
from kelbet.i18n import kk, ru, t
from kelbet.i18n.keys import Msg


def _message_keys() -> set[str]:
    return {value for name, value in vars(Msg).items() if name.isupper() and isinstance(value, str)}


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


def test_referral_terms_render_in_ru_and_kk() -> None:
    link = "https://t.me/kelbet_test_bot?start=ref_KELBET01"
    values: dict[str, str | int] = {
        "link": link,
        "invited": 2,
        "pending": 1,
        "credited": 5,
        "inviter_bonus": 5,
        "minimum": 50,
        "waiting": 72,
    }
    for language in (Language.RU, Language.KK):
        rendered = t(Msg.INVITE_SUMMARY, language, **values)
        assert link in rendered
        assert "{link}" not in rendered
        assert "50" in rendered
        assert "72" in rendered
