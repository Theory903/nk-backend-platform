"""ERP domain services."""

from {{cookiecutter.project_name}}.erp.services.assets import AssetsService
from {{cookiecutter.project_name}}.erp.services.billing import BillingService
from {{cookiecutter.project_name}}.erp.services.crm import CrmService
from {{cookiecutter.project_name}}.erp.services.documents import DocumentService
from {{cookiecutter.project_name}}.erp.services.ledger import LedgerService
from {{cookiecutter.project_name}}.erp.services.manufacturing import ManufacturingService
from {{cookiecutter.project_name}}.erp.services.masters import MastersService
from {{cookiecutter.project_name}}.erp.services.pricing import PricingService
from {{cookiecutter.project_name}}.erp.services.projects import ProjectsService
from {{cookiecutter.project_name}}.erp.services.reports import ReportsService
from {{cookiecutter.project_name}}.erp.services.stock import StockService
from {{cookiecutter.project_name}}.erp.services.support import SupportService
from {{cookiecutter.project_name}}.erp.services.valuation import FIFOValuation, LIFOValuation

__all__ = [
    "AssetsService",
    "BillingService",
    "CrmService",
    "DocumentService",
    "FIFOValuation",
    "LedgerService",
    "LIFOValuation",
    "ManufacturingService",
    "MastersService",
    "PricingService",
    "ProjectsService",
    "ReportsService",
    "StockService",
    "SupportService",
]
