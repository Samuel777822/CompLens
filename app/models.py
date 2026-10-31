from typing import Dict, List, Literal, Optional

from pydantic import BaseModel

Status = Literal["PASS", "FAIL", "REVIEW", "NOT_APPLICABLE", "EXEMPT"]
ViolationCode = Literal[
    "MISSING",
    "FORMAT_ERROR",
    "UNIT_ERROR",
    "NONSTANDARD_PACK",
    "VAGUE_LANGUAGE",
    "LANGUAGE_ERROR",
    "LOW_CONFIDENCE",
]
Verdict = Literal["COMPLIANT", "NON_COMPLIANT", "NEEDS_REVIEW", "EXEMPT"]


class FieldResult(BaseModel):
    """Superset of the per-field schema in the rulebook (Part D)."""

    field: str
    status: Status
    violation_code: Optional[ViolationCode] = None
    detected_text: Optional[str] = None
    rule_reference: str
    detail: Optional[str] = None
    sub_case: Optional[str] = None
    confidence: Optional[float] = None


class ScanResult(BaseModel):
    scan_id: Optional[str] = None
    input_mode: Literal["image", "text"]
    category: str
    pack_type: Optional[str] = None
    verdict: Verdict
    summary: Dict[str, int]
    exemption: Optional[Dict[str, str]] = None
    fields: List[FieldResult]
    limitations: List[str]
    raw_text: str
    avg_ocr_confidence: Optional[float] = None
    # things the user should know about the scan itself (blurry photo, rotated, part of the label only...)
    warnings: List[str] = []
    images_used: int = 1
    # what the checker decided the product is and how its net quantity is measured
    product: Optional[Dict[str, str]] = None


class TextCheckRequest(BaseModel):
    text: str
    category: str = "other"
    pack_type: Optional[str] = None
