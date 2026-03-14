from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


class UserAdmin(BaseUserAdmin):
    """
    Custom User Admin
    """
    list_display = [
        'username', 
        'email', 
        'first_name', 
        'last_name', 
        'role', 
        'is_active', 
        'is_staff',
        'created_at'
    ]
    list_filter = ['role', 'is_active', 'is_staff', 'created_at']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering = ['username']
    
    fieldsets = (
        (None, {
            'fields': ('username', 'password')
        }),
        ('Personal Info', {
            'fields': ('first_name', 'last_name', 'email', 'phone')
        }),
        ('Role & Permissions', {
            'fields': ('role', 'is_active', 'is_staff', 'is_superuser')
        }),
        ('Important Dates', {
            'fields': ('last_login', 'date_joined', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['created_at', 'updated_at', 'last_login', 'date_joined']
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'username', 
                'email', 
                'first_name', 
                'last_name', 
                'role', 
                'phone',
                'password1', 
                'password2',
                'is_active',
            ),
        }),
    )
    
    def get_queryset(self, request):
        """
        Admin can see all users
        Super User can see all users except admin
        """
        qs = super().get_queryset(request)
        
        if request.user.role == 'admin':
            return qs
        elif request.user.role == 'super_user':
            return qs.exclude(role='admin')
        
        return qs.filter(id=request.user.id)


# Register User model
admin.site.register(User, UserAdmin)

# Customize admin site header
admin.site.site_header = "Godamwale ERP Administration"
admin.site.site_title = "Godamwale ERP Admin"
admin.site.index_title = "Welcome to Godamwale ERP Administration"