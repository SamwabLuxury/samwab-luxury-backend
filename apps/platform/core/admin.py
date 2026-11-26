"""Site-wide admin wording (build E16). Django's default home heading is
"Site administration"; staff see "Home". The look and menu are in settings (UNFOLD)."""

from django.contrib import admin

admin.site.index_title = "Home"
admin.site.site_title = "Samwab admin"
admin.site.site_header = "Samwab"
