from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class TelegramAuthRequest(BaseModel):
    init_data: str = Field(alias="initData", min_length=1)


class RegisterRequest(BaseModel):
    personal_number: str = Field(alias="personalNumber", min_length=4, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    password_confirmation: str = Field(alias="passwordConfirmation", min_length=1, max_length=256)


class LoginRequest(BaseModel):
    personal_number: str = Field(alias="personalNumber", min_length=4, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    remember_me: bool = Field(default=False, alias="rememberMe")


class LogoutRequest(BaseModel):
    all_devices: bool = Field(default=False, alias="allDevices")


class StudentVerificationRequest(BaseModel):
    personal_number: str = Field(alias="personalNumber", min_length=4, max_length=64)


class VerificationResponse(BaseModel):
    verified: bool
    verification_token: str | None = Field(default=None, alias="verificationToken")
    student: dict[str, Any] | None = None
    error: str | None = None


class ConfirmVerificationRequest(BaseModel):
    verification_token: str = Field(alias="verificationToken", min_length=16)


class NotificationRequest(BaseModel):
    type: str = Field(default="schedule_changes", min_length=1, max_length=64)


class FriendRequestCreate(BaseModel):
    user_id: int = Field(alias="userId", gt=0)


class ScheduleItem(BaseModel):
    date: date
    start_time: str = Field(alias="startTime")
    end_time: str = Field(alias="endTime")
    subject: str
    lesson_type: str = Field(alias="lessonType")
    room: str | None = None
    teacher: str | None = None
    subgroup: int | None = None
    note: str | None = None
    changed: bool = False
    announcement: bool = False
    exam: bool = False


class ScheduleResponse(BaseModel):
    date: date
    week_number: int | None = Field(alias="weekNumber")
    group_number: str = Field(alias="groupNumber")
    items: list[ScheduleItem]
    source: str
    stale: bool = False
    message: str | None = None
