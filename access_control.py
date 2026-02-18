from flask import session, redirect, url_for
from typing import Dict, Set

ROLE_DEFAULT_ENDPOINTS = {
    'Guest': 'login.login',
    'Customer': 'products.index',
    'Staff': 'main.pos',
    'Admin': 'main.dashboard',
}

# Map endpoints to the roles that are allowed to visit them. A missing entry means the endpoint is open to every role.
ROLE_RESTRICTED_ENDPOINTS: Dict[str, Set[str]] = {
    'login.login': {'Guest'},  # Only guests can access login
    'register.register': {'Guest'},  # Only guests can access register
    'main.dashboard': {'Admin'},
    'main.pos': {'Staff'},  # Changed to Staff only
    'main.setup_products_table': {'Admin'},
    'main.debug_db': {'Admin'},
    'main.demand_forecasting': {'Staff', 'Admin'},
    'main.stock': {'Staff', 'Admin'},
    'main.add_product': {'Staff', 'Admin'},
    'main.orders': {'Staff', 'Admin'},
    'main.users': {'Admin'},
    'main.notifications': {'Admin'},
    'main.maintenance': {'Admin'},
    'main.mytask': {'Staff'},
    'main.task': {'Admin'},
    'main.sales': {'Admin'},
    'main.cart': {'Customer'},
    'main.checkout': {'Staff'},
    # Products blueprint routes
    'products.index': {'Guest', 'Customer'},
    'products.products': {'Guest', 'Customer'},
    'products.test_cart_db': {'Customer', 'Staff', 'Admin'},
    'products.add_to_cart': {'Customer'},
    'products.get_cart': {'Customer'},
    'products.remove_from_cart': {'Customer'},
    'products.create_store_order': {'Customer'},
}

# Additional restrictions for direct URLs
DIRECT_URL_RESTRICTIONS = {
    '/register': {'Guest'},  # Direct /register URL
    '/auth/register': {'Guest'},  # Auth prefixed register URL
}

def get_role_default_endpoint() -> str:
    role = session.get('role', 'Guest')
    return ROLE_DEFAULT_ENDPOINTS.get(role, ROLE_DEFAULT_ENDPOINTS['Guest'])


def redirect_by_role():
    return redirect(url_for(get_role_default_endpoint()))


def is_authorized(endpoint: str, role: str) -> bool:
    # Check endpoint restrictions first
    allowed_roles = ROLE_RESTRICTED_ENDPOINTS.get(endpoint)
    if allowed_roles is not None:
        return role in allowed_roles
    
    # Check direct URL restrictions
    from flask import request
    url_path = request.path
    allowed_url_roles = DIRECT_URL_RESTRICTIONS.get(url_path)
    if allowed_url_roles is not None:
        return role in allowed_url_roles
    
    # If no restrictions found, allow access
    return True
