"""Identidade privilegiada criada exclusivamente pelo comando administrativo CLI."""

def is_superadmin(user):
    """Perfil exclusivo, independente de limites e valida????es da licen??a.

    A fun????o exige o marcador do provisionamento CLI; administradores
    cadastrados pela interface t??m role=technician, mesmo com permiss??o admin.
    """
    return bool(
        user
        and user.is_active
        and user.permission_level == "admin"
        and user.role == "admin"
        and user.job_title == "Superadmin"
    )
