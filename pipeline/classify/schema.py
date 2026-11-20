"""Classification output contract: enums, Pydantic model, and provider JSON schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ROLES = [
    "Frontend Developer", "Backend Developer", "Full Stack Developer", "Software Engineer",
    "Data Analyst", "Data Scientist", "Machine Learning Engineer", "AI Engineer",
    "DevOps Engineer", "QA Engineer", "UI UX Designer", "Product Manager", "Other", "Unknown",
]
JOB_TYPES = ["Full-time", "Part-time", "Internship", "Contract", "Temporary", "Unknown"]
EXPERIENCE_LEVELS = ["Internship", "Fresher", "Junior", "Mid", "Senior", "Unknown"]
CONFIDENCE = ["high", "medium", "low"]

Role = Literal[tuple(ROLES)]  # type: ignore[valid-type]
JobType = Literal[tuple(JOB_TYPES)]  # type: ignore[valid-type]
Experience = Literal[tuple(EXPERIENCE_LEVELS)]  # type: ignore[valid-type]
Confidence = Literal[tuple(CONFIDENCE)]  # type: ignore[valid-type]


class LLMClassification(BaseModel):
    """Exactly what the model must return. Extra keys are rejected."""
    model_config = ConfigDict(extra="forbid")

    role: Role
    cities: list[str] = Field(max_length=15)
    is_remote: bool
    job_type: JobType
    experience_level: Experience
    confidence: Confidence


def json_schema_openai() -> dict:
    """Strict JSON schema for OpenAI structured outputs."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["role", "cities", "is_remote", "job_type", "experience_level", "confidence"],
        "properties": {
            "role": {"type": "string", "enum": ROLES},
            "cities": {"type": "array", "items": {"type": "string"}},
            "is_remote": {"type": "boolean"},
            "job_type": {"type": "string", "enum": JOB_TYPES},
            "experience_level": {"type": "string", "enum": EXPERIENCE_LEVELS},
            "confidence": {"type": "string", "enum": CONFIDENCE},
        },
    }


def json_schema_gemini() -> dict:
    """Same contract in the OpenAPI subset Gemini's responseSchema accepts."""
    return {
        "type": "object",
        "required": ["role", "cities", "is_remote", "job_type", "experience_level", "confidence"],
        "propertyOrdering": ["role", "cities", "is_remote", "job_type", "experience_level", "confidence"],
        "properties": {
            "role": {"type": "string", "enum": ROLES},
            "cities": {"type": "array", "items": {"type": "string"}},
            "is_remote": {"type": "boolean"},
            "job_type": {"type": "string", "enum": JOB_TYPES},
            "experience_level": {"type": "string", "enum": EXPERIENCE_LEVELS},
            "confidence": {"type": "string", "enum": CONFIDENCE},
        },
    }
