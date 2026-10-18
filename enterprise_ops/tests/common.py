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