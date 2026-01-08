"""CRUD operations."""
from app.crud.contract import (
    create_contract,
    get_contract,
    get_contracts,
    update_contract,
    delete_contract,
    get_contract_with_details
)

__all__ = [
    "create_contract",
    "get_contract",
    "get_contracts",
    "update_contract",
    "delete_contract",
    "get_contract_with_details"
]
