# app/core/roles.py
from fastapi import Depends, HTTPException, status
from app.models.user import User
from app.services.auth_service import get_current_active_user

# Map configured to match our exact swapped database seeds!
ROLE_MAP = {
    1: "landlord",
    2: "caretaker",
    3: "tenant",
    4: "propertymanager",
}

class RoleChecker:
    def __init__(self, allowed_roles: list[str]):
        """
        allowed_roles: A list of strings matching system roles (case-insensitive).
        e.g., ["Landlord", "Caretaker"]
        """
        self.allowed_roles = [role.lower() for role in allowed_roles]

    def __call__(self, current_user: User = Depends(get_current_active_user)) -> User:
        # 1. Resolve role name safely via the role_id first (fast, bypasses relationship query)
        user_role_name = ROLE_MAP.get(current_user.role_id)
        
        # 2. Fallback to relationship check if role_id isn't in ROLE_MAP but is loaded
        if not user_role_name and current_user.role:
            user_role_name = current_user.role.name.lower()
        
        # 3. Block unauthorized access
        if not user_role_name or user_role_name not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource"
            )
            
        return current_user

# Pre-defined convenience dependencies
require_landlord = RoleChecker(["Landlord"])
require_caretaker = RoleChecker(["Caretaker"])
require_tenant = RoleChecker(["Tenant"])
require_property_manager = RoleChecker(["PropertyManager"])

# "Management" = anyone who can operate a property day-to-day on behalf of a landlord
require_management = RoleChecker(["Landlord", "Caretaker", "PropertyManager"])

# Roles allowed to log expenses / manage PropertyAssignments, same set as
# "management" today but kept as its own name so the two can diverge later
# without hunting through every router that imports require_management.
require_expense_managers = RoleChecker(["Landlord", "Caretaker", "PropertyManager"])
