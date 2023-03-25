from django.contrib import admin

# Register your models here.
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext as _
from .models import CustomUser, Company, InviteToken, Franchise


class CustomUserAdmin(UserAdmin):
    """Define admin model for custom User model with no username field."""
    fieldsets = (
        (None, {'fields': ('first_name',
                           'last_name',
                           'status',
                           'email',
                           'phone',    
                           'company',
                           'isVerified',
                           'otp_enabled',
                            'otp_base32',
                            'otp_auth_url',  
                                                  
                           )}),
        (_('Permissions'), {'fields': ('is_active', 'is_staff',
         'is_superuser', 'groups', 'user_permissions')}),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('first_name', 'last_name', 'is_staff', 'password1', 'password2'),
        }),
    )

    list_display = ('first_name', 'last_name', 'email',
                    'isVerified', 'company__name')
    search_fields = ('id', 'first_name', 'last_name', 'email')
    ordering = ('id',)
    list_filter = ('is_staff', 'isVerified',)

    def company__name(self, obj):
        return obj.company.name

class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'accessToken')

class InviteTokenAdmin(admin.ModelAdmin):
    list_display = ('id', 'email', 'company')
    search_fields = ['id', 'email', 'company']

class FranchiseAdmin(admin.ModelAdmin):
    list_display = ('name', 'mainCompany')
    search_fields = ['name', 'mainCompany']

admin.site.register(Company, CompanyAdmin)
admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(InviteToken, InviteTokenAdmin)
admin.site.register(Franchise, FranchiseAdmin)
