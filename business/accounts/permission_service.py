# encoding:utf-8
from business.config.constants import ServiceType, normalize_service


def verify_customer_access(openid: str):
    from business.accounts.user_service import verify_user_access

    return verify_user_access(openid)


def verify_customer_business_access(
    openid: str,
    service_type: ServiceType | str | None = None,
    *,
    business_key: str = "",
):
    from business.accounts.user_service import verify_permission

    resolved_service = service_type
    if resolved_service is None and business_key:
        from business.components.registry import get_business_definition

        resolved_service = get_business_definition(business_key).service_type
    return verify_permission(openid, normalize_service(resolved_service or ServiceType.UNMATCHED))


def verify_admin_permission(admin, permission: str):
    from business.accounts.auth_service import require_permission

    return require_permission(admin, permission)
