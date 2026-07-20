from datetime import datetime
from uuid import UUID
from sqlmodel import Session, select
from fastapi import HTTPException, status

from app.models.user import User
from app.models.property import Property
from app.models.property_assignment import PropertyAssignment


class PropertyAssignmentService:

    @staticmethod
    def assign(session: Session, landlord: User, target_user_id: UUID, property_id: UUID) -> PropertyAssignment:
        target = session.get(User, target_user_id)
        if not target or target.role_id not in (2, 4):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Caretaker or Property Manager not found")

        # A Caretaker only ever belongs to the landlord who created them —
        # a landlord can't assign someone else's caretaker to their property.
        if target.role_id == 2 and target.landlord_id != landlord.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This caretaker does not belong to you")

        prop = session.exec(
            select(Property).where(Property.id == property_id, Property.landlord_id == landlord.id)
        ).first()
        if not prop:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")

        existing = session.exec(
            select(PropertyAssignment)
            .where(PropertyAssignment.user_id == target_user_id)
            .where(PropertyAssignment.property_id == property_id)
            .where(PropertyAssignment.revoked_at == None)  # noqa: E711
        ).first()
        if existing:
            return existing

        assignment = PropertyAssignment(
            user_id=target_user_id,
            property_id=property_id,
            assigned_by_id=landlord.id,
        )
        session.add(assignment)
        session.commit()
        session.refresh(assignment)
        return assignment

    @staticmethod
    def assign_property_manager_by_email(session: Session, landlord: User, email: str, property_id: UUID) -> PropertyAssignment:
        """The multi-landlord path: grant an *existing* Property Manager
        (created by any landlord) access to one of your properties."""
        pm = session.exec(select(User).where(User.email == email, User.role_id == 4)).first()
        if not pm:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No Property Manager account found with that email")

        return PropertyAssignmentService.assign(session, landlord, pm.id, property_id)

    @staticmethod
    def revoke(session: Session, landlord: User, assignment_id: UUID) -> None:
        assignment = session.get(PropertyAssignment, assignment_id)
        if not assignment or assignment.assigned_by_id != landlord.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")

        assignment.revoked_at = datetime.now()
        session.add(assignment)
        session.commit()

    @staticmethod
    def revoke_all_for_user(session: Session, user_id: UUID) -> None:
        """Used when a Caretaker/Property Manager account is deleted."""
        rows = session.exec(
            select(PropertyAssignment)
            .where(PropertyAssignment.user_id == user_id)
            .where(PropertyAssignment.revoked_at == None)  # noqa: E711
        ).all()
        for row in rows:
            row.revoked_at = datetime.now()
            session.add(row)
        session.commit()

    @staticmethod
    def list_for_landlord(session: Session, landlord: User):
        return session.exec(
            select(PropertyAssignment).where(PropertyAssignment.assigned_by_id == landlord.id)
        ).all()

    @staticmethod
    def list_for_user(session: Session, user_id: UUID):
        """All active assignments for a Caretaker/Property Manager — useful
        for a Property Manager who needs to see every landlord's property
        they currently have access to."""
        return session.exec(
            select(PropertyAssignment)
            .where(PropertyAssignment.user_id == user_id)
            .where(PropertyAssignment.revoked_at == None)  # noqa: E711
        ).all()
