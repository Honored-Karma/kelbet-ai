from kelbet.catalog.pricing import compute_user_credit_price
from kelbet.catalog.seeds import catalog_model_rows, feature_flag_rows


def test_veo_extended_catalog_is_off_by_default_and_truthful() -> None:
    flag = next(row for row in feature_flag_rows() if row["key"] == "veo_extended")
    assert flag["enabled"] is False

    model = next(
        row
        for row in catalog_model_rows()
        if row["slug"] == "google-veo31-fast-extended-video"
    )
    assert model["feature_flag"] == "veo_extended"
    assert model["provider_model_id"] == "veo-3.1-fast-generate-preview"
    assert model["capabilities"]["durations_sec"] == [8, 15, 22, 29]
    assert model["capabilities"]["resolutions"] == ["720p"]
    assert model["capabilities"]["supports_seed"] is False
    assert model["capabilities"]["workflow"] == {
        "type": "veo_extend",
        "initial_duration_sec": 8,
        "extension_duration_sec": 7,
        "cumulative_durations_sec": [8, 15, 22, 29],
        "final_output_only": True,
        "fallback": False,
    }
    assert "fallback" not in model["capabilities"]

    pricing = model["pricing_rules"]
    for duration, multiplier in ((8, 1), (15, 2), (22, 3), (29, 4)):
        assert compute_user_credit_price(
            model["user_credit_price"],
            params={"duration_sec": duration},
            pricing_rules=pricing,
        ) == 100 * multiplier
