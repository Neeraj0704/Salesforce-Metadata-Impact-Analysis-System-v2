from pydantic import BaseModel, ConfigDict, HttpUrl


class TokenPayload(BaseModel):
    """OAuth tokens returned by Salesforce after authorization."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    access_token: str
    refresh_token: str
    instance_url: HttpUrl