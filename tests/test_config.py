from gmp_weather.config import SCORING_CONFIG_PATH, load_scoring_config


def test_load_scoring_config_reads_yaml_weights():
    config = load_scoring_config(SCORING_CONFIG_PATH)

    assert config.model_version == "rules-v0.1"
    assert config.risk_bands["clear_max"] == 29
    assert config.risk_bands["severe_storm_min"] == 85
    assert config.deviation_recurrence["severity_critical"] > config.deviation_recurrence["severity_minor"]
    assert config.deviation_recurrence["linked_capa_overdue"] > 0
    assert config.capa_failure["retraining_only_action"] > 0
    assert config.training_drift["overdue_training_per_record"] > 0
    assert config.audit_readiness_gap["open_major_critical_deviation_per_record"] > 0
    assert config.backlog_pressure["overdue_item_per_record"] > 0
    assert config.confidence_penalties["missing_field_penalty"] > 0
