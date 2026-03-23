from rest_framework import permissions


class IsAdminUserOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow admins to delete objects.
    All authenticated users can create and edit.
    """

    def has_permission(self, request, view):
        # Allow any authenticated user for non-destructive actions
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request,
        if request.method in permissions.SAFE_METHODS:
            return True

        # Admins can delete anything; Subadmins can delete their own submissions
        if request.method == "DELETE":
            if request.user.is_staff:
                return True
            # Allow deletion if the user submitted this object
            return hasattr(obj, "submittedBy") and obj.submittedBy == request.user.username

        # Admin and Subadmin (regular authenticated staff-like users) can edit/create
        return request.user and request.user.is_authenticated
