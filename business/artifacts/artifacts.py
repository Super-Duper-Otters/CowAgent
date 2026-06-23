# encoding:utf-8
from business.constants import ServiceType


def archive_business_output_files(
    owner_id: str,
    output_files: list[str],
    service_type: ServiceType,
    **options,
):
    from business.artifact_service import archive_output_files

    return archive_output_files(owner_id, output_files, service_type, **options)


def record_business_artifact(
    owner_id: str,
    file_path: str,
    artifact_role: str,
    service_type: ServiceType,
    **options,
) -> None:
    from business.artifact_service import record_artifact

    record_artifact(owner_id, file_path, artifact_role, service_type, **options)
