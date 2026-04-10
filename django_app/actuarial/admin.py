from django.contrib import admin

from .models import OrganizationProfile


@admin.register(OrganizationProfile)
class OrganizationProfileAdmin(admin.ModelAdmin):
    """Single workspace organization record (pk=1)."""

    list_display = ('company_name', 'city', 'updated_at')
    readonly_fields = ('updated_at',)

    def has_add_permission(self, request) -> bool:
        return not OrganizationProfile.objects.filter(pk=1).exists()
