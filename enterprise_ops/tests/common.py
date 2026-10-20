# -*- coding: utf-8 -*-
"""Shared test helpers (T21: request lines now require a real product)."""


def get_test_product(env):
    """One shared, purchasable, company-independent product per database."""
    Product = env['product.product']
    product = Product.search([('default_code', '=', 'ENT-OPS-TEST')], limit=1)
    return product or Product.create({
        'name': 'Enterprise Ops Test Item',
        'default_code': 'ENT-OPS-TEST',
    })


def with_implied(groups):
    """Transitive closure over implied_ids: a user saved from the UI holds
    its role plus everything the role implies (the ORM does not expand)."""
    result = groups
    todo = groups
    while todo:
        todo = todo.implied_ids - result
        result |= todo
    return result