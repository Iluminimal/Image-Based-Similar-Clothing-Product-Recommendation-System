from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class TwoFactorStatus(BaseModel):
    enabled: bool
    # True бол тохируулах хүртэл ажилтны API хаалттай.
    required: bool
    recovery_codes_left: int


class TwoFactorSetupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: Annotated[str, Field(min_length=1, max_length=128)]


class TwoFactorSetup(BaseModel):
    secret: str
    otpauth_uri: str
    qr_image: str = Field(description="SVG data URI of the QR code")


class TwoFactorEnableRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Annotated[str, Field(pattern=r"^[0-9]{6}$")]


class RecoveryCodes(BaseModel):
    codes: list[str]
