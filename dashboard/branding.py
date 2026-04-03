from dashboard.models import LibraryBranding


def get_library_branding():
    branding = LibraryBranding.objects.order_by("id").first()
    if branding:
        return branding

    return LibraryBranding(name="نظام إدارة المكتبة", tagline="")

