"""Pydantic schemas for ERP domain documents."""

from {{cookiecutter.project_name}}.erp.schemas.crm import LeadCreate, LeadRead, OpportunityCreate, OpportunityRead
from {{cookiecutter.project_name}}.erp.schemas.masters import CustomerCreate, CustomerRead, ItemCreate, ItemRead, SupplierCreate, SupplierRead
from {{cookiecutter.project_name}}.erp.schemas.support import IssueCreate, IssueRead, IssueStatusUpdate
from {{cookiecutter.project_name}}.erp.schemas.transaction import ItemLine, TaxLine, TransactionDocument, TransactionTotals

__all__ = [
    "CustomerCreate",
    "CustomerRead",
    "IssueCreate",
    "IssueRead",
    "IssueStatusUpdate",
    "ItemCreate",
    "ItemLine",
    "ItemRead",
    "LeadCreate",
    "LeadRead",
    "OpportunityCreate",
    "OpportunityRead",
    "SupplierCreate",
    "SupplierRead",
    "TaxLine",
    "TransactionDocument",
    "TransactionTotals",
]
