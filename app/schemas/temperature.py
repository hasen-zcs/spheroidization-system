# app/schemas/temperature.py

from pydantic import BaseModel, ConfigDict, field_validator

from app.domain.temperature.entities import TemperatureRecord


class TemperatureCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gun_no: int
    temperature: float
    measured_at: str
    spheroidization_record_id: int | None = None

    @field_validator("measured_at")
    @classmethod
    def validate_measured_at(cls, value: str) -> str:
        from datetime import datetime

        try:
            parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except ValueError as exc:
            raise ValueError(
                "measured_at 必须符合 YYYY-MM-DD HH:MM:SS 格式"
            ) from exc

        if parsed.strftime("%Y-%m-%d %H:%M:%S") != value:
            raise ValueError(
                "measured_at 必须符合 YYYY-MM-DD HH:MM:SS 格式"
            )

        return value


def to_response(record: TemperatureRecord) -> dict:
    return {
        "id": record.temperature_record_id,
        "gun_no": record.gun_no,
        "temperature": record.temperature,
        "measured_at": record.measured_at,
        "spheroidization_record_id": record.spheroidization_record_id,
        "created_at": record.created_at,
    }