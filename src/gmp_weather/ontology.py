"""Small controlled vocabulary for the prototype."""

RECORD_TYPE_LABELS = {
    "deviation": "Deviation",
    "capa": "CAPA",
    "change_control": "Change Control",
    "audit_observation": "Audit Observation",
    "training_event": "Training Event",
    "complaint": "Complaint",
}

PROCESS_AREA_DESCRIPTIONS = {
    "sterile manufacturing": "Activities related to aseptic or sterile production controls.",
    "quality control": "Laboratory testing, review, and analytical controls.",
    "packaging": "Packaging operations, labeling, and line clearance activities.",
    "validation": "Qualification, process validation, and computerized system validation.",
    "warehouse": "Material receipt, storage, and distribution controls.",
}

RECORD_TYPE_WEIGHTS = {
    "deviation": 1.10,
    "capa": 1.05,
    "change_control": 0.95,
    "audit_observation": 1.00,
    "training_event": 0.85,
    "complaint": 1.05,
}
