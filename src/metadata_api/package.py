"""Package definitions for Metadata API retrieve."""

from src.metadata_api.models import MetadataType, RetrieveRequest, UnpackagedMetadata


# Initial retrieve: high-signal types for impact analysis.
INITIAL_RETRIEVE_TYPES: list[MetadataType] = [
    MetadataType(name="CustomObject", members=["*"]),
    MetadataType(name="ApexClass", members=["*"]),
    MetadataType(name="ApexTrigger", members=["*"]),
    MetadataType(name="Flow", members=["*"]),
    MetadataType(name="PermissionSet", members=["*"]),
]


def build_initial_retrieve_request(api_version: str | None = None) -> RetrieveRequest:
    """Build request body for REST Metadata retrieve (unpackaged, initial set)."""
    return RetrieveRequest(
        single_package=True,
        unpackaged=UnpackagedMetadata(types=INITIAL_RETRIEVE_TYPES),
        api_version=api_version,
    )