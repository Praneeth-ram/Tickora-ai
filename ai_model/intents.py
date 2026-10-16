from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, model_validator

IntentName = Literal[
    "attendance_records",
    "attendance_summary",
    "timesheet_lookup",
    "leave_status",
    "wfh_status",
    "holiday_lookup",
    "schedule_lookup",
]

PeriodName = Literal[
    "today",
    "yesterday",
    "this_week",
    "this_month",
    "last_month",
    "custom",
]

StatusName = Literal[
    "PRESENT",
    "ABSENT",
    "LATE",
    "HALF_DAY",
    "ON_LEAVE",
    "HOLIDAY",
    "WEEKEND",
    "DRAFT",
    "SUBMITTED",
    "APPROVED",
    "REJECTED",
    "PENDING",
    "CANCELLED",
]


class IntentRequest(BaseModel):
    # Validated structure predicted by the intent model.

    model_config = ConfigDict(extra="forbid")

    intent: IntentName
    period: PeriodName | None = None

    start_date: date | None = None
    end_date: date | None = None
    on_date: date | None = None

    status: StatusName | None = None
    region: str | None = None
    requested_metric: str | None = None

    @model_validator(mode="after")
    def validate_parameters(self):
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.start_date > self.end_date
        ):
            raise ValueError(
                "start_date cannot be after end_date"
            )

        if self.period == "custom":
            if self.start_date is None or self.end_date is None:
                raise ValueError(
                    "Custom period requires start_date and end_date"
                )

        if self.intent == "schedule_lookup" and self.on_date is None:
            if self.period not in {"today", "yesterday"}:
                raise ValueError(
                    "Schedule lookup requires on_date "
                    "or a supported single-day period"
                )

        if self.region is not None and not self.region.strip():
            raise ValueError("region cannot be empty")

        return self
