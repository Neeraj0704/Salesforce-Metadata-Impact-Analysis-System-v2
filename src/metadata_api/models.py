"""Pydantic models for Metadata API requests and responses."""

from pydantic import BaseModel, Field


class MetadataType(BaseModel):
    """Metadata type with members (e.g. CustomObject with ['*'])."""

    name: str = Field(..., description="Metadata type name (e.g. 'CustomObject')")
    members: list[str] = Field(..., description="Component names or ['*'] for all")


class UnpackagedMetadata(BaseModel):
    """Unpackaged metadata types (not in a package)."""

    types: list[MetadataType] = Field(..., description="List of metadata types to retrieve")


class RetrieveRequest(BaseModel):
    """Metadata API retrieve request body."""

    single_package: bool = Field(True, alias="singlePackage", description="Single package retrieve")
    unpackaged: UnpackagedMetadata = Field(..., description="Unpackaged metadata types")
    api_version: str | None = Field(None, alias="apiVersion", description="API version override")

    model_config = {"populate_by_name": True}


class RetrieveStatusResponse(BaseModel):
    """Retrieve job status response."""

    id: str = Field(..., description="Retrieve job ID")
    status: str = Field(..., description="Status: Pending | InProgress | Succeeded | Failed")
    done: bool = Field(False, description="Whether job is complete")
    success: bool | None = Field(None, description="Success flag (if done)")
    error_message: str | None = Field(None, alias="errorMessage", description="Error message if failed")

    model_config = {"populate_by_name": True}


class RetrieveResultResponse(BaseModel):
    """Retrieve job result response (includes ZIP)."""

    id: str = Field(..., description="Retrieve job ID")
    status: str = Field(..., description="Status")
    success: bool = Field(..., description="Whether retrieve succeeded")
    zip_file: str = Field(..., alias="zipFile", description="Base64-encoded ZIP file")
    file_properties: list[dict] | None = Field(None, alias="fileProperties", description="File properties list")

    model_config = {"populate_by_name": True}