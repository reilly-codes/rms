import pandas as pd

from fastapi import Depends, APIRouter, HTTPException, UploadFile, File
from sqlmodel import select
from typing import List
from datetime import datetime

from app.db import SessionDep
from app.routers.users import active_user
from app.models.transaction import Transaction
from app.schemas.transaction import TransactionStatus

router = APIRouter(
    prefix="/transactions",
    tags=["Transactions"],
    dependencies=[Depends(active_user)]
)

@router.get("/all", response_model=List[Transaction])
async def get_all_transactions(
    session: SessionDep,
    status: TransactionStatus | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None
):
    query = select(Transaction)
    
    if status:
        query = query.where(Transaction.transaction_status == status)
        
    if date_from:
        query = query.where(Transaction.transaction_date >= date_from)
    elif date_from and date_to:
        query = query.where(Transaction.transaction_date >= date_from and Transaction.transaction_date <= date_to)
        
    query = query.order_by(Transaction.transaction_date)
    
    transactions = session.exec(query).all()
    
    return transactions
        
    
@router.post("/upload")
async def upload_bank_statement(
    session: SessionDep,
    file: UploadFile = File(...)
):
    if not file.filename.endswith(('.csv', '.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="Invalid File format. Please upload CSV or Excel")
    
    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file.file)
        else:
            df = pd.read_excel(file.file)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read file: {str(e)}")
    
    required_cols = ["Date", "Amount", "Reference"]
    if not all(col in df.columns for col in required_cols):
        raise HTTPException(status_code=400, detail=f"Missing required columns. Found: {df.columns}")
    
    try: 
        new_transactions = []
        for index, row in df.iterrows():
            existing_qry = select(Transaction).where(Transaction.transaction_reference == str(row["Reference"]))
            existing = session.exec(existing_qry).first()
            
            if existing:
                continue
            
            txn = Transaction(
                transaction_reference=str(row["Reference"]),
                transaction_date=pd.to_datetime(row["Date"]),
                amount=float(row["Amount"])
            )
            
            session.add(txn)
            new_transactions.append(txn)
        
        session.commit()
        return {"message": "Success", "count": len(new_transactions)}
    
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Error processing row {index}: {str(e)}")