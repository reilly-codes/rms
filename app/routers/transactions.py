# app/routers/transactions.py
import pandas as pd
from fastapi import Depends, APIRouter, HTTPException, UploadFile, File, status
from sqlmodel import select
from typing import List, Annotated
from datetime import datetime

# Core config, DB, roles, and auth dependencies
from app.core.database import SessionDep
from app.core.roles import require_landlord
from app.services.auth_service import get_current_active_user

# Models and Schemas
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.transaction import TransactionStatus

router = APIRouter(
    prefix="/transactions",
    tags=["Transactions"],
    dependencies=[Depends(require_landlord)]  # Strictly locked to Landlords only
)

@router.get("/all", response_model=List[Transaction])
async def get_all_transactions(
    session: SessionDep,
    current_user: Annotated[User, Depends(require_landlord)],
    status_filter: TransactionStatus | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None
):
    """Retrieve all loaded financial transactions, with optional filtering."""
    query = select(Transaction)
    
    if status_filter:
        query = query.where(Transaction.transaction_status == status_filter)
        
    if date_from:
        query = query.where(Transaction.transaction_date >= date_from)

    if date_to:
        query = query.where(Transaction.transaction_date <= date_to)
        
    query = query.order_by(Transaction.transaction_date)
    
    transactions = session.exec(query).all()
    return transactions
        
@router.post("/upload")
async def upload_bank_statement(
    session: SessionDep,
    current_user: Annotated[User, Depends(require_landlord)],
    file: UploadFile = File(...)
):
    """
    Upload and parse bank/M-Pesa statements (CSV or Excel).
    Duplicates are automatically skipped based on transaction reference identifiers.
    """
    if not file.filename.endswith(('.csv', '.xlsx', '.xls')):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Invalid File format. Please upload CSV or Excel"
        )
    
    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file.file)
        else:
            df = pd.read_excel(file.file)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Could not read file: {str(e)}"
        )
    
    required_cols = ["Date", "Amount", "Reference"]
    if not all(col in df.columns for col in required_cols):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Missing required columns. Found: {list(df.columns)}"
        )

    # This is the primary auto-match key: M-Pesa paybill statements carry
    # whatever the payer typed as the "Account Number", and landlords here
    # near-universally have tenants use their house/unit number for that.
    house_col = next((c for c in df.columns if c.strip().lower() in (
        "house", "house number", "house no", "unit", "unit number",
        "account number", "account no", "acc no", "acc number",
    )), None)
    phone_col = next((c for c in df.columns if c.strip().lower() in ("phone", "phone number", "msisdn")), None)
    payer_col = next((c for c in df.columns if c.strip().lower() in ("payer", "name", "customer", "details", "narrative")), None)
    
    try: 
        new_transactions = []
        for index, row in df.iterrows():
            ref_str = str(row["Reference"]).strip()
            existing_qry = select(Transaction).where(Transaction.transaction_reference == ref_str)
            existing = session.exec(existing_qry).first()
            
            if existing:
                continue
            
            txn = Transaction(
                transaction_reference=ref_str,
                transaction_date=pd.to_datetime(row["Date"]),
                amount=float(row["Amount"]),
                house_number=(str(row[house_col]).strip() if house_col and pd.notna(row.get(house_col)) else None),
                phone_number=(str(row[phone_col]).strip() if phone_col and pd.notna(row.get(phone_col)) else None),
                payer_name=(str(row[payer_col]).strip() if payer_col and pd.notna(row.get(payer_col)) else None),
                raw_narrative=(str(row[payer_col]).strip() if payer_col and pd.notna(row.get(payer_col)) else None),
            )
            
            session.add(txn)
            new_transactions.append(txn)
        
        session.commit()
        return {"message": "Success", "count": len(new_transactions)}
    
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Error processing row {index}: {str(e)}"
        )